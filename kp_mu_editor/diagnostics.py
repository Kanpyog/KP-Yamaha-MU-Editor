"""Bounded asynchronous local diagnostics. MIDI/GUI threads never write files."""
from datetime import datetime
from pathlib import Path
import importlib.metadata
import json,os,platform,queue,sys,threading,time,zipfile,re
from stat import S_ISREG
from . import __version__


def windows_midi_environment():
    if sys.platform!='win32':return {}
    import winreg
    result={'drivers':[],'midi_registry':{}}
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Windows NT\CurrentVersion') as key:
            result['windows']={name:winreg.QueryValueEx(key,name)[0] for name in ('DisplayVersion','CurrentBuild','UBR')}
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Drivers32') as key:
            for i in range(winreg.QueryInfoKey(key)[1]):
                name,value,_=winreg.EnumValue(key,i)
                if name.lower().startswith('midi'):result['midi_registry'][name]=value
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,r'SYSTEM\CurrentControlSet\Control\Class\{4d36e96c-e325-11ce-bfc1-08002be10318}') as key:
            for i in range(winreg.QueryInfoKey(key)[0]):
                name=winreg.EnumKey(key,i)
                if not name.isdigit():continue
                with winreg.OpenKey(key,name) as sub:
                    values={}
                    for label in ('DriverDesc','DriverVersion','DriverDate','ProviderName','InfPath'):
                        try:values[label]=winreg.QueryValueEx(sub,label)[0]
                        except OSError:pass
                    if any(word in values.get('DriverDesc','').lower() for word in ('yamaha','roland','midi')):
                        result['drivers'].append(values)
    except OSError as exc:result['query_error']=str(exc)
    return result


class Diagnostics:
    def __init__(self,data_dir,mode='normal',max_bytes=8*1024*1024,keep_bytes=200*1024*1024):
        self.folder=Path(data_dir)/'diagnostics';self.mode=mode if mode in ('normal','debug') else 'normal'
        self.run_id=datetime.now().strftime('%Y%m%d_%H%M%S_%f')+f'_{os.getpid()}'
        self.path=self.folder/f'session_{self.run_id}_000.jsonl'
        self.max_bytes=max_bytes;self.keep_bytes=keep_bytes
        self.queue=queue.Queue(maxsize=5000);self.error='';self.dropped=0;self._pending_bytes=0
        self._lock=threading.Lock();self._closed=False;self._stop=threading.Event()
        self._thread=threading.Thread(target=self._writer,daemon=True,name='MU-diagnostics');self._thread.start()
        versions={}
        for name in ('PySide6','mido'):
            try:versions[name]=importlib.metadata.version(name)
            except importlib.metadata.PackageNotFoundError:versions[name]='missing'
        self.record('startup',version=__version__,python=sys.executable,python_version=sys.version,
                    platform=platform.platform(),bits=64 if sys.maxsize>2**32 else 32,packages=versions,mode=self.mode)
        if self.debug:self.record('windows_midi_environment',**windows_midi_environment())

    @property
    def debug(self):return self.mode=='debug'

    def set_mode(self,mode):
        self.mode=mode if mode in ('normal','debug') else 'normal'
        self.record('diagnostic_mode',mode=self.mode)
        if self.debug:self.record('windows_midi_environment',**windows_midi_environment())

    def record(self,event,detail=False,**values):
        if self._closed or self.error or detail and not self.debug:return
        size=256+sum(len(v) if isinstance(v,(bytes,str)) else 32 for v in values.values())
        with self._lock:
            if self._pending_bytes+size>8*1024*1024:self.dropped+=1;return
            self._pending_bytes+=size
        entry={'timestamp':time.time(),'monotonic':time.perf_counter(),'event':event,**values}
        try:self.queue.put_nowait(('event',entry,size))
        except queue.Full:
            with self._lock:self._pending_bytes-=size;self.dropped+=1

    def flush(self,timeout=2):
        if self.error or not self._thread.is_alive():return False
        if self._closed:return not self.error
        done=threading.Event()
        try:self.queue.put(('flush',done,0),timeout=timeout)
        except queue.Full:return False
        return done.wait(timeout) and not self.error

    def _prune(self):
        files=[]
        for path in self.folder.glob('session_*.jsonl'):
            if not re.fullmatch(r'session_\d{8}_\d{6}_\d{6}_\d+_\d+\.jsonl',path.name):continue
            try:files.append((path,path.stat()))
            except OSError:continue
        files.sort(key=lambda pair:pair[1].st_mtime,reverse=True)
        total=0;cutoff=time.time()-14*86400
        for path,stat in files:
            total+=stat.st_size
            if path==self.path:continue
            if stat.st_mtime<cutoff or total>self.keep_bytes:
                try:
                    if path.resolve().parent==self.folder.resolve():path.unlink()
                except OSError:pass

    def _writer(self):
        file=None;segment=0;written=0;last_flush=time.perf_counter()
        try:
            self.folder.mkdir(parents=True,exist_ok=True);self._prune()
            file=self.path.open('x',encoding='utf-8')
            while not self._stop.is_set() or not self.queue.empty():
                try:kind,value,size=self.queue.get(timeout=.2)
                except queue.Empty:
                    file.flush();continue
                try:
                    if kind=='flush':file.flush();value.set();continue
                    entry=dict(value);entry['time']=datetime.fromtimestamp(entry.pop('timestamp')).astimezone().isoformat()
                    if self.dropped:entry['diagnostic_events_dropped_total']=self.dropped
                    line=json.dumps(entry,ensure_ascii=False,default=lambda v:v.hex(' ') if isinstance(v,bytes) else str(v))+'\n'
                    file.write(line);written+=len(line.encode('utf-8'))
                    if written>=self.max_bytes:
                        file.close();segment+=1;written=0
                        self.path=self.folder/f'session_{self.run_id}_{segment:03d}.jsonl';file=self.path.open('x',encoding='utf-8')
                        self._prune()
                    if time.perf_counter()-last_flush>=1:file.flush();last_flush=time.perf_counter()
                finally:
                    if size:
                        with self._lock:self._pending_bytes-=size
        except Exception as exc:self.error=str(exc)
        finally:
            if file:
                try:file.close()
                except OSError as exc:self.error=str(exc)
            while not self.queue.empty():
                try:kind,value,size=self.queue.get_nowait()
                except queue.Empty:break
                if kind=='flush':value.set()

    def export_bundle(self,destination):
        flushed=self.flush()
        candidates=[];excluded=[]
        data_dir = self.folder.parent.resolve()
        for path in [*self.folder.glob('session_*.jsonl'),*(self.folder.parent/'logs').glob('read_*.jsonl')]:
            try:
                stat = path.lstat()
                if not S_ISREG(stat.st_mode) or path.resolve().parent != data_dir / path.parent.name:
                    excluded.append(path.name)
                    continue
            except OSError:excluded.append(path.name);continue
            candidates.append((stat.st_mtime,path,stat.st_size))
        candidates.sort(key=lambda entry:entry[0],reverse=True)
        selected=[];total=0
        for _,path,size in candidates:
            if total+size>50*1024*1024 or len(selected)>=100:excluded.append(path.name);continue
            selected.append((path,size));total+=size
        destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
        temporary=destination.with_name(destination.name+f'.{time.time_ns()}.tmp')
        try:
            with zipfile.ZipFile(temporary,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
                manifest={'version':__version__,'run_id':self.run_id,'mode':self.mode,'flush_completed':flushed,
                          'writer_error':self.error,'dropped':self.dropped,'files':[],'excluded':excluded}
                for path,size in selected:
                    try:
                        with path.open('rb') as source:data=source.read(size)
                    except OSError:
                        manifest['excluded'].append(path.name);continue
                    # A currently active file may end with a partial JSON line.
                    complete=data[:data.rfind(b'\n')+1]
                    name=path.parent.name+'/'+path.name;bundle.writestr(name,complete)
                    manifest['files'].append({'name':name,'bytes':len(complete),'snapshot_bytes':size})
                bundle.writestr('manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
            os.replace(temporary,destination)
        finally:
            if temporary.exists():temporary.unlink()
        return destination

    def close(self):
        if self._closed:return
        self.record('shutdown');self.flush();self._closed=True;self._stop.set();self._thread.join(timeout=3)
