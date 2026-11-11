"""Serialized I/O worker: GUI stays responsive during dumps and file playback."""
from __future__ import annotations
from pathlib import Path
from datetime import datetime
import heapq,json,queue,threading,time,itertools,traceback
from io import BytesIO
from PySide6.QtCore import QObject, Signal
from .winmm import Transport
from .protocol import parse, request, is_setup_packet, TG300B_SYSTEM_ON
from .smf import read_smf
from .schema import CC_PART
from .catalog import Catalog
from .read_trace import ReadTrace
from .dependencies import midi_library


class Engine(QObject):
    received=Signal(bytes)
    sysex_sent=Signal(bytes)
    short_received=Signal(int,bytes)
    activity=Signal(str)
    progress=Signal(int,int,str)
    finished=Signal(str,object)
    failed=Signal(str)
    connection=Signal(bool)
    reset_applied=Signal()

    def __init__(self,data_dir,start_worker=True,diagnostics=None):
        super().__init__()
        self.data_dir=Path(data_dir)
        self.commands=queue.Queue()
        self.transport=None
        self.connected=False
        self.cancel=threading.Event()
        self.shutdown=threading.Event()
        self.device=0
        self.thru=False
        self.thru_port=0
        self.schedule=[];self.play_start=0;self.playing=False
        self.catalog=Catalog();self.effect_types={}
        self._read_trace=None;self._read_stats=None
        self.diagnostics=diagnostics;self._command_ids=itertools.count(1);self._health_at=0
        self._thread=threading.Thread(target=self._run,daemon=True,name='MU-MIDI-output') if start_worker else None
        if self._thread:self._thread.start()

    def submit(self,kind,payload=None):
        identifier=next(self._command_ids)
        self.commands.put((kind,payload,time.monotonic(),identifier))
        self.diagnose('command_queued',kind=kind,command_id=identifier,queue_depth=self.commands.qsize())

    def diagnose(self,event,detail=False,**values):
        if self.diagnostics:self.diagnostics.record(event,detail=detail,**values)

    def reset_xg(self,blocks):
        self.cancel.set();self.submit('xg_reset',list(blocks))

    def send(self,messages,label='送信',interval=.015):
        self.submit('send',(list(messages),label,interval))

    def stop(self):
        self.cancel.set();self.submit('stop')

    def _poll(self,captured=None,notify=True):
        rejected=set()
        if not self.transport:return rejected
        if self.diagnostics and self.diagnostics.debug and time.monotonic()-self._health_at>=5:
            self._health_at=time.monotonic()
            snapshot=getattr(self.transport,'diagnostic_snapshot',lambda:{})()
            self.diagnose('midi_health',detail=True,command_queue=self.commands.qsize(),playing=self.playing,**snapshot)
        for source,raw,stamp in self.transport.poll():
            self.diagnose('rx_frame',detail=True,source=source,raw=raw,driver_time=stamp,
                          dispatch_delay_ms=max(0,(time.monotonic()-stamp)*1000))
            if raw[:1]==b'\xf0':
                # A damaged manufacturer/checksum can still be identified as a
                # rejected response candidate. Never fix or import its bytes.
                candidate=(raw[3],tuple(raw[6:9])) if len(raw)>=11 and raw[3] in (0x4c,0x49,0x44) and raw[2]&0xf0==0 and raw[2]&15==self.device else None
                try:
                    packet=parse(raw)
                except ValueError as exc:
                    if candidate:rejected.add(candidate)
                    self.diagnose('rx_invalid',source=source,raw=raw,error=str(exc))
                    # Reject before notifying the GUI. Previously both the GUI and
                    # this worker reported the same bad packet, hiding progress.
                    if self._read_stats is not None:self._read_stats['invalid']+=1
                    if self._read_trace:
                        self._read_trace.record('rx',source=source,raw=raw.hex(' '),valid=False,error=str(exc),driver_time=stamp)
                    self.activity.emit('RX INVALID '+raw.hex(' ')[:180]+' / '+str(exc))
                    continue
                if packet is None and self._read_stats is not None:self._read_stats['unrecognized']+=1
                if packet is None and candidate:
                    rejected.add(candidate);self.diagnose('rx_unrecognized_candidate',source=source,raw=raw,model=candidate[0],address=candidate[1])
                if self._read_trace:
                    self._read_trace.record('rx',source=source,raw=raw.hex(' '),valid=packet is not None,driver_time=stamp)
                if packet and packet.device==self.device:
                    if notify:self.received.emit(raw)
                    if captured is not None and packet.data:captured[(packet.model,packet.address)]=raw
                    if packet.model==0x4c and len(packet.data)>=2 and ((packet.address[0]==3 and packet.address[2]==0) or (packet.address[:2]==(2,1) and packet.address[2] in (0,0x20,0x40))):
                        self.effect_types[packet.address]=tuple(packet.data[:2])
                self.activity.emit('RX '+raw.hex(' ')[:180])
            elif raw:
                if self._read_trace:self._read_trace.record('rx_short',source=source,raw=raw.hex(' '),driver_time=stamp)
                self.short_received.emit(source,raw)
                if self.thru and raw[0]<0xf0:
                    self.transport.send(raw,self.thru_port)
        return rejected

    def _send(self,raw,port=0):
        if not self.transport or not self.connected:raise RuntimeError('MUを接続してください。')
        if len(raw)>4 and raw[:2]==b'\xf0\x43':
            raw=raw[:2]+bytes(((raw[2]&0xf0)|self.device,))+raw[3:]
        started=time.perf_counter();self.transport.send(raw,port)
        elapsed=(time.perf_counter()-started)*1000
        self.diagnose('tx',detail=True,port=port,raw=raw,send_ms=elapsed)
        if elapsed>50:self.diagnose('slow_send',port=port,raw=raw,send_ms=elapsed)
        if raw[:1]==b'\xf0' and raw[-1:]==b'\xf7':self.sysex_sent.emit(raw)
        if self._read_trace:self._read_trace.record('tx',port=port,raw=raw.hex(' '),send_ms=elapsed)
        self.activity.emit('TX '+raw.hex(' ')[:180])
        return elapsed

    def _read(self,blocks,label,notify=True,clear_cancel=True):
        blocks=list(blocks)
        captured={};pending=[];skipped=0;retry_requests=0;recovered=0
        gap=.008;last_request=0.;good_streak=0;read_started=time.monotonic()
        if clear_cancel:self.cancel.clear()
        timings={'pacing_wait_s':0.,'retry_wait_s':0.,'send_ms':0.,'response_wait_s':0.,'timeouts':0,'rejected_responses':0}
        slowest=[]
        self.diagnose('read_started',label=label,blocks=len(blocks),device=self.device,playing=self.playing)
        trace=None
        try:trace=ReadTrace(self.data_dir,label)
        except OSError as exc:self.activity.emit('取得診断ログを保存できません：'+str(exc))
        self._read_trace=trace
        stats={'invalid':0,'unrecognized':0};self._read_stats=stats

        def wait(seconds,replies=None,key=None):
            deadline=time.monotonic()+max(0,seconds)
            while not self.cancel.is_set() and time.monotonic()<deadline:
                # Continue draining input during backoff, without treating late
                # replies as the response to a different requested block.
                self._poll(replies,notify=notify)
                if replies is not None and key in replies:break
                time.sleep(min(.003,max(0,deadline-time.monotonic())))

        def read_block(block,attempts,recovery=False):
            nonlocal gap,last_request,good_streak,retry_requests,recovered
            model,address=block[:2];address=tuple(address)
            parameter=bool(len(block)>2 and block[2]);key=(model,address)
            replies={}
            def accept(attempt,waiting,late=False):
                nonlocal gap,good_streak,recovered
                captured[key]=replies[key]
                if attempt or recovery:recovered+=1
                good_streak+=1
                if good_streak>=8:gap=max(.008,gap/2);good_streak=0
                elapsed=time.monotonic()-waiting
                self.diagnose('read_response',detail=True,model=model,address=address,attempt=attempt+1,recovery=recovery,
                              response_ms=elapsed*1000,gap_ms=gap*1000,late=late)
                slowest.append({'model':model,'address':list(address),'response_ms':round(elapsed*1000,3),'attempt':attempt+1})
                slowest.sort(key=lambda x:x['response_ms'],reverse=True);del slowest[20:]
                return True
            for attempt in range(attempts):
                if self.cancel.is_set():return False
                if attempt or recovery:
                    delay=max(.025,gap)*(attempt+1)
                    waiting=time.monotonic();wait(delay,replies,key)
                    timings['retry_wait_s']+=time.monotonic()-waiting
                    if key in replies:return accept(attempt,waiting,True)
                else:
                    delay=max(0,gap-(time.monotonic()-last_request));waiting=time.monotonic();wait(delay)
                    timings['pacing_wait_s']+=time.monotonic()-waiting
                if self.cancel.is_set():return False
                if attempt or recovery:retry_requests+=1
                last_request=time.monotonic()
                timings['send_ms']+=self._send(request(address,model=model,parameter=parameter)) or 0
                deadline=time.monotonic()+(.35 if recovery else .20)
                waiting=time.monotonic();reason='timeout'
                while time.monotonic()<deadline and not self.cancel.is_set():
                    rejected=self._poll(replies,notify)
                    if key in replies:
                        elapsed=time.monotonic()-waiting;timings['response_wait_s']+=elapsed
                        return accept(attempt,waiting)
                    if key in rejected:reason='rejected';break
                    time.sleep(.002)
                timings['response_wait_s']+=time.monotonic()-waiting
                if not self.cancel.is_set():timings['timeouts' if reason=='timeout' else 'rejected_responses']+=1
                good_streak=0;gap=min(.05,max(.025,gap*2))
                self.diagnose('read_retry',model=model,address=address,attempt=attempt+1,recovery=recovery,reason=reason,gap_ms=gap*1000)
                if trace:trace.record('retry',model=model,address=list(address),attempt=attempt+1,recovery=recovery,reason=reason,gap_ms=gap*1000)
            return False

        completed=False
        try:
            for i,block in enumerate(blocks):
                model,address=block[:2]
                if self.cancel.is_set():break
                if model==0x4c and address[0]==3 and 0x30<=address[2]<=0x42:
                    type_packet=captured.get((0x4c,(3,address[1],0)))
                    if type_packet and parse(type_packet).data[0] not in (5,6,7,8):skipped+=1;continue
                if not read_block(block,3):pending.append(block)
                if i%8==0:self.progress.emit(i+1,len(blocks),label)
            # One slower recovery pass. Only validated responses to the exact
            # requested address enter the backup; never repair bytes by guessing.
            for i,block in enumerate(pending):
                if self.cancel.is_set():break
                gap=.05
                self.progress.emit(i+1,len(pending),label+'・未取得を再試行')
                read_block(block,2,True)
            completed=True
        finally:
            if trace:
                trace.record('end',count=len(captured),cancelled=self.cancel.is_set(),completed=completed,
                             retry_requests=retry_requests,recovered=recovered,
                             missing=[[b[0],list(b[1])] for b in pending if (b[0],tuple(b[1])) not in captured],
                             elapsed_s=time.monotonic()-read_started,timings=timings,**stats)
                trace.close()
                if trace.error:self.activity.emit('取得診断ログの保存エラー：'+trace.error)
            self._read_trace=None;self._read_stats=None
        missing=[[block[0],list(block[1])] for block in pending if (block[0],tuple(block[1])) not in captured]
        self.progress.emit(len(captured),len(blocks)-skipped,label)
        if captured:
            folder=self.data_dir/'backups';folder.mkdir(parents=True,exist_ok=True)
            stamp=datetime.now().strftime('%Y%m%d_%H%M%S_%f')
            path=folder/f'{stamp}.syx';path.write_bytes(b''.join(captured.values()))
        else:path=None
        report={'count':len(captured),'missing':missing,'cancelled':self.cancel.is_set(),'backup':str(path) if path else '',
                'expected':len(blocks)-skipped,'retry_requests':retry_requests,'recovered':recovered,
                **stats,
                'diagnostic_log':str(trace.path) if trace else '',
                'elapsed_s':round(time.monotonic()-read_started,3),'timings':timings,'slowest_responses':slowest}
        self.diagnose('read_finished',label=label,**report)
        if notify:self.finished.emit(label,report)
        return report

    def _send_batch(self,messages,label,interval):
        self.cancel.clear()
        for i,(port,raw) in enumerate(messages):
            if self.cancel.is_set():break
            self._send(raw,port)
            packet=parse(raw) if raw[:2]==b'\xf0\x43' else None
            if packet and packet.bulk:
                # Each bulk write is paced and acknowledged before advancing.
                time.sleep(max(.15,interval))
                captured={};key=(packet.model,packet.address)
                for attempt in range(2):
                    self._send(request(packet.address,model=packet.model),port)
                    deadline=time.monotonic()+.5
                    while time.monotonic()<deadline:
                        self._poll(captured)
                        if key in captured:break
                        time.sleep(.003)
                    if key in captured:break
                if key not in captured:
                    raise RuntimeError(f'本体の応答がないため送信を停止しました（{packet.model:02X} {packet.address}）。再接続してバックアップを確認してください。')
                actual=parse(captured[key])
                h,m,low=packet.address
                base=0 if h==3 or low<0x20 else 0x20 if low<0x40 else 0x40
                effect_type=self.effect_types.get((h,m,base))
                offsets=self.catalog.readback_offsets(packet,effect_type)
                match=len(actual.data)==len(packet.data) and all(actual.data[n]==packet.data[n] for n in (offsets if offsets is not None else range(len(packet.data))))
                if not match:
                    raise RuntimeError(f'本体の読み戻し値が一致しないため送信を停止しました（{packet.address}）。')
            else:
                self._poll()
                if interval:time.sleep(max(.012,interval))
            if len(messages)>20 and i%4==0:self.progress.emit(i+1,len(messages),label)
        self.finished.emit(label,{'cancelled':self.cancel.is_set()})

    def _panic(self):
        if not self.transport:return
        for port in self.transport.outputs:
            for channel in range(16):
                for number in (64,66,123,120):
                    self._send(bytes((0xb0|channel,number,0)),port)

    def _run(self):
        while not self.shutdown.is_set():
            command=None
            try:
                if self.commands.empty():
                    self._poll()
                if self.playing and not self.cancel.is_set():
                    elapsed=time.monotonic()-self.play_start
                    for _ in range(128):
                        if (not self.schedule or self.schedule[0][0] > elapsed
                                or self.cancel.is_set() or self.shutdown.is_set()):
                            break
                        _,order,port,raw=heapq.heappop(self.schedule)
                        self._send(raw,port)
                    if not self.schedule:
                        self.playing=False;self._panic();self.finished.emit('再生完了',{})
                try:command=self.commands.get(timeout=.003);kind,payload=command[:2]
                except queue.Empty:continue
                command_started=time.monotonic()
                self.diagnose('command_started',kind=kind,command_id=command[3] if len(command)>3 else None,
                              queue_wait_ms=(command_started-command[2])*1000 if len(command)>2 else None)
                if kind=='open':
                    if self.transport:self.transport.close()
                    self.transport=Transport(diagnostics=self.diagnostics);self.transport.open(*payload)
                    self.diagnose('midi_connected',inputs=list(payload[0]),outputs=list(payload[1]),device=self.device)
                    self.connected=True;self.connection.emit(True)
                    self._send(bytes.fromhex('F0 7E 7F 06 01 F7'))
                    self._send(request((1,0,0)))
                elif kind=='close':
                    self.diagnose('midi_disconnected')
                    self.playing=False;self.schedule.clear()
                    if self.transport:self.transport.close()
                    self.transport=None;self.connected=False;self.connection.emit(False)
                elif kind=='read':
                    if self.playing:
                        self.playing=False;self.schedule.clear();self._panic()
                        self.diagnose('play_stopped_for_read')
                        self.activity.emit('本体取得のため、このアプリのMIDI再生を停止しました。')
                    self._read(*payload)
                elif kind=='xg_reset':
                    self.playing=False;self.schedule.clear();self.cancel.clear();self._panic()
                    self._send(bytes.fromhex('F0 43 10 4C 00 00 7E 00 F7'))
                    self.effect_types.clear();self.reset_applied.emit();self.diagnose('xg_reset_sent')
                    self.cancel.wait(.1)
                    self._read(payload,'XG初期化後取得',clear_cancel=False)
                elif kind=='send':
                    self._send_batch(*payload)
                elif kind=='send_set':
                    messages,blocks=payload
                    backup=self._read(blocks,'送信前バックアップ',False)
                    if backup['cancelled']:continue
                    if not backup['count'] or backup['missing']:
                        raise RuntimeError('送信前のバックアップに未取得項目があるため、一括送信を停止しました。接続と機種を確認してください。')
                    self._send_batch(messages,'セット送信・読み戻し照合',.15)
                elif kind=='play':
                    self.cancel.clear();self.schedule=list(payload);heapq.heapify(self.schedule)
                    self.play_start=time.monotonic();self.playing=True
                elif kind=='stop':
                    self.playing=False;self.schedule.clear();self._panic()
                elif kind=='panic':self._panic()
            except Exception as exc:
                self.diagnose('engine_error',command=command[0] if command else None,error=str(exc),traceback=traceback.format_exc())
                self.failed.emit(str(exc));self.playing=False;self.schedule.clear()
                if command and command[0]=='open':
                    self.connected=False;self.connection.emit(False)
            finally:
                if command:self.diagnose('command_finished',kind=command[0],elapsed_ms=(time.monotonic()-command_started)*1000,cancelled=self.cancel.is_set())
        if self.transport:self.transport.close()

    def close(self):
        self.cancel.set();self.shutdown.set()
        if self._thread:self._thread.join(timeout=4)


def load_midi(path,keep_setup=True,*,allow_tg300b=False):
    mido=midi_library()
    from mido.messages.specs import SPEC_BY_STATUS
    lengths = {status: spec['length'] for status, spec in SPEC_BY_STATUS.items()}
    file = mido.MidiFile(file=BytesIO(read_smf(path, lengths)))
    events=[];order=0
    for track in file.tracks:
        tick=0;port=0
        for msg in track:
            tick+=msg.time
            if msg.type=='midi_port':
                port=msg.port
                if not 0<=port<4:raise ValueError(f'ポート{port+1}が含まれています。A～DのSMFに対応します。')
            elif msg.type=='set_tempo':events.append((tick,order,-1,msg.tempo))
            elif not msg.is_meta:
                raw=bytes(msg.bytes())
                if msg.type=='sysex':
                    if not keep_setup:continue
                    standard=raw in (bytes.fromhex('F0 7E 7F 09 01 F7'),bytes.fromhex('F0 7E 7F 09 03 F7'))
                    packet = parse(raw) if len(raw) > 7 and raw[1] == 0x43 and raw[3] in (0x4C, 0x49, 0x44) else None
                    xg_reset = (packet is not None and packet.model == 0x4C
                                and not packet.bulk and packet.address == (0, 0, 0x7E)
                                and packet.data == b'\x00')
                    gs_reset=allow_tg300b and raw==TG300B_SYSTEM_ON
                    if not (standard or xg_reset or gs_reset or is_setup_packet(packet)):continue
                if not keep_setup and (msg.type=='program_change' or (msg.type=='control_change' and msg.control in (0,32,5,6,38,7,10,65,71,72,73,74,75,76,77,78,84,91,93,94,96,97,98,99,100,101))):continue
                events.append((tick,order,port,raw))
            order+=1
    events.sort(key=lambda x:(x[0],x[1]));tempo=500000;last_tick=0;seconds=0;result=[]
    for tick,order,port,raw in events:
        seconds+=mido.tick2second(tick-last_tick,file.ticks_per_beat,tempo);last_tick=tick
        if port==-1:tempo=raw
        else:result.append((seconds,order,port,raw))
    return result


def write_midi(path,messages):
    mido=midi_library()
    import io
    from .session import atomic_write
    midi=mido.MidiFile(type=1,ticks_per_beat=480)
    conductor=mido.MidiTrack();midi.tracks.append(conductor)
    conductor.append(mido.MetaMessage('track_name',name='KP YAMAHA MU Editor setup',time=0))
    conductor.append(mido.MetaMessage('set_tempo',tempo=500000,time=0))
    conductor.append(mido.MetaMessage('time_signature',numerator=4,denominator=4,time=0))
    tracks={};last={};tick=0
    for raw in messages:
        packet=parse(raw)
        if not is_setup_packet(packet):raise ValueError('設定MIDIにはMUパラメーターメッセージを指定してください。')
        h,m,l=packet.address
        if packet.model==0x4c and h in (8,0x0a):key=('part',m);name=f'Part {chr(65+m//16)}{m%16+1:02d}'
        elif packet.model==0x4c and 0x30<=h<0x34:key=('drum',h-0x30);name=f'Drum Setup {h-0x2f}'
        elif packet.model==0x44 and h==2:
            n=m-1 if 1<=m<=9 else 9 if m==0 else m
            key=('part',n);name=f'Part A{n+1:02d}'
        else:key=('system',0);name='System and Effects'
        if key not in tracks:
            track=mido.MidiTrack();midi.tracks.append(track);tracks[key]=track;last[key]=0
            track.append(mido.MetaMessage('track_name',name=name,time=0))
            track.append(mido.MetaMessage('midi_port',port=0,time=0))
        # A global cursor preserves the restore order across all parallel tracks.
        tick+=160 if packet.bulk else 24
        tracks[key].append(mido.Message('sysex',data=raw[1:-1],time=tick-last[key]));last[key]=tick
    conductor.append(mido.MetaMessage('end_of_track',time=tick))
    for key,track in tracks.items():track.append(mido.MetaMessage('end_of_track',time=tick-last[key]))
    out=io.BytesIO();midi.save(file=out);atomic_write(path,out.getvalue())
