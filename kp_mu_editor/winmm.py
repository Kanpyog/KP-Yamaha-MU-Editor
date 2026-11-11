"""WinMM transport. Native callbacks only copy bytes; a worker recycles buffers.

No MIDI reset or initialization is sent when opening or closing a connection.
"""
from __future__ import annotations
import ctypes as C
from ctypes import wintypes as W
import queue
import sys
import threading
import time

MAX_INPUT_MESSAGES = 512
LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x00000800

class MidiError(RuntimeError):
    pass


class MIDIHDR(C.Structure):
    _fields_ = [("lpData", C.c_void_p), ("dwBufferLength", W.DWORD),
                ("dwBytesRecorded", W.DWORD), ("dwUser", C.c_size_t),
                ("dwFlags", W.DWORD), ("lpNext", C.c_void_p),
                ("reserved", C.c_size_t), ("dwOffset", W.DWORD),
                ("dwReserved", C.c_size_t * 8)]


class INCAPS(C.Structure):
    _fields_ = [("mid", W.WORD), ("pid", W.WORD), ("version", W.DWORD),
                ("name", W.WCHAR * 32), ("support", W.DWORD)]


class OUTCAPS(C.Structure):
    _fields_ = [("mid", W.WORD), ("pid", W.WORD), ("version", W.DWORD),
                ("name", W.WCHAR * 32), ("technology", W.WORD),
                ("voices", W.WORD), ("notes", W.WORD), ("channels", W.WORD),
                ("support", W.DWORD)]


def library():
    if sys.platform != "win32":
        raise MidiError("MIDI通信はWindows専用です。オフライン編集は利用できます。")
    dll = C.WinDLL("winmm.dll", winmode=LOAD_LIBRARY_SEARCH_SYSTEM32)
    ptr = C.c_void_p
    signatures = {
        "midiInGetNumDevs": ([], W.UINT), "midiOutGetNumDevs": ([], W.UINT),
        "midiInGetDevCapsW": ([C.c_size_t, C.POINTER(INCAPS), W.UINT], W.UINT),
        "midiOutGetDevCapsW": ([C.c_size_t, C.POINTER(OUTCAPS), W.UINT], W.UINT),
        "midiInOpen": ([C.POINTER(ptr), W.UINT, C.c_size_t, C.c_size_t, W.DWORD], W.UINT),
        "midiOutOpen": ([C.POINTER(ptr), W.UINT, C.c_size_t, C.c_size_t, W.DWORD], W.UINT),
        "midiOutShortMsg": ([ptr, W.DWORD], W.UINT),
    }
    for prefix in ("midiIn", "midiOut"):
        for suffix in ("PrepareHeader", "UnprepareHeader"):
            signatures[prefix + suffix] = ([ptr, C.POINTER(MIDIHDR), W.UINT], W.UINT)
        signatures[prefix + "Close"] = ([ptr], W.UINT)
        signatures[prefix + "Reset"] = ([ptr], W.UINT)
        signatures[prefix + "GetErrorTextW"] = ([W.UINT, W.LPWSTR, W.UINT], W.UINT)
    for name in ("midiInStart", "midiInStop"):
        signatures[name] = ([ptr], W.UINT)
    for name in ("midiInAddBuffer", "midiOutLongMsg"):
        signatures[name] = ([ptr, C.POINTER(MIDIHDR), W.UINT], W.UINT)
    for name, (args, result) in signatures.items():
        getattr(dll, name).argtypes = args
        getattr(dll, name).restype = result
    return dll


def ports():
    dll = library()
    result = {"inputs": [], "outputs": []}
    for kind, caps_cls, prefix in (("inputs", INCAPS, "midiIn"), ("outputs", OUTCAPS, "midiOut")):
        for index in range(getattr(dll, prefix + "GetNumDevs")()):
            caps = caps_cls()
            if not getattr(dll, prefix + "GetDevCapsW")(index, C.byref(caps), C.sizeof(caps)):
                result[kind].append({"id": index, "name": caps.name, "manufacturer": caps.mid,
                                     "product": caps.pid,"driver_version_raw":int(caps.version)})
    return result


class Transport:
    def __init__(self,diagnostics=None):
        self.dll = library()
        self.inputs = []
        self.outputs = {}
        self.messages = queue.Queue(maxsize=MAX_INPUT_MESSAGES)
        self._recycle = queue.Queue()
        self._stop = threading.Event()
        self._worker = None
        self._buffers = []
        self._input_headers = {}
        self._callback = None
        self._lock = threading.RLock()
        self._input_lock=threading.RLock()
        self._held_outputs = []
        self._fragments = {}
        self.diagnostics=diagnostics;self._faults=queue.Queue(maxsize=32)
        self._stats={'long_callbacks':0,'long_errors':0,'short_callbacks':0,'callback_errors':0,'buffers_recycled':0,'buffer_errors':0,'framing_errors':0}
        self._stats['input_dropped'] = 0
        self._input_drops_seen = 0

    def _input_fault(self, message):
        try:
            self._faults.put_nowait(message)
        except queue.Full:
            pass

    def _queue_input(self, source, raw, timestamp):
        try:
            self.messages.put_nowait((source, raw, timestamp))
        except queue.Full:
            self._stats['input_dropped'] += 1

    def diagnose(self,event,detail=False,**values):
        if self.diagnostics:self.diagnostics.record(event,detail=detail,**values)

    def diagnostic_snapshot(self):
        return {**self._stats,'rx_queue':self.messages.qsize(),'recycle_queue':self._recycle.qsize(),'input_buffers':len(self._buffers)}

    def check(self, code, direction="Out"):
        if code:
            buf = C.create_unicode_buffer(256)
            getattr(self.dll, "midi" + direction + "GetErrorTextW")(code, buf, len(buf))
            raise MidiError(f"MIDI {code}: {buf.value}")

    @property
    def connected(self):
        return bool(self.outputs)

    def open(self, input_ids, output_ids):
        self.close()
        self._stop.clear()
        callback_type = C.WINFUNCTYPE(None, C.c_void_p, W.UINT, C.c_size_t, C.c_size_t, C.c_size_t)

        def callback(handle, message, instance, param1, param2):
            try:
                if self._stop.is_set():return
                if message in (0x3C4, 0x3C6):  # MIM_LONGDATA / LONGERROR
                    allocated = self._input_headers.get(param1)
                    if allocated is None or allocated[0].value != handle:
                        self._stats['callback_errors'] += 1
                        self.diagnose('driver_unknown_buffer')
                        self._input_fault('MIDIドライバーから不明な受信バッファが返されました。')
                        return
                    _, header, buffer = allocated
                    if header.dwBufferLength != len(buffer) or header.lpData != C.addressof(buffer):
                        self._stats['callback_errors'] += 1
                        self.diagnose('driver_invalid_buffer')
                        self._input_fault('MIDIドライバーから不明な受信バッファが返されました。')
                        return
                    if header.dwBytesRecorded > len(buffer):
                        self._stats['callback_errors']+=1
                        self.diagnose('driver_invalid_recorded_length',recorded=int(header.dwBytesRecorded),capacity=int(header.dwBufferLength))
                        self._input_fault('MIDIドライバーから不正な受信バッファ長が返されました。再接続してください。')
                        self._recycle.put((handle,param1));return
                    raw=C.string_at(header.lpData,header.dwBytesRecorded) if header.dwBytesRecorded else b''
                    stamp=time.monotonic()
                    self._stats['long_callbacks' if message==0x3C4 else 'long_errors']+=1
                    self.diagnose('driver_rx_chunk' if message==0x3C4 else 'driver_long_error',detail=message==0x3C4,
                                  source=int(instance),raw=raw,recorded=int(header.dwBytesRecorded),capacity=int(header.dwBufferLength),
                                  flags=int(header.dwFlags),callback_time=stamp,driver_timestamp_ms=int(param2))
                    if message == 0x3C4 and raw:self._queue_input(int(instance),raw,stamp)
                    self._recycle.put((handle, param1))
                elif message in (0x3C3, 0x3CC):  # MIM_DATA / MOREDATA
                    self._stats['short_callbacks']+=1
                    status = param1 & 255
                    size = 2 if status & 0xF0 in (0xC0, 0xD0) else (1 if status >= 0xF8 else 3)
                    raw=bytes((param1 >> (8*i)) & 255 for i in range(size))
                    self.diagnose('driver_short',detail=True,source=int(instance),raw=raw,driver_timestamp_ms=int(param2),message=int(message))
                    self._queue_input(int(instance),raw,time.monotonic())
                elif message==0x3C5:self.diagnose('driver_short_error',source=int(instance),packed=int(param1),driver_timestamp_ms=int(param2))
            except Exception as exc:
                self._stats['callback_errors']+=1
                self.diagnose('driver_callback_error',error=str(exc),message=int(message))

        self._callback = callback_type(callback)
        try:
            for logical, index in enumerate(output_ids):
                if index is None or index < 0:
                    continue
                handle = C.c_void_p()
                self.check(self.dll.midiOutOpen(C.byref(handle), index, 0, 0, 0))
                self.outputs[logical] = handle
            for index in dict.fromkeys(input_ids):
                handle = C.c_void_p()
                self.check(self.dll.midiInOpen(C.byref(handle), index,
                    C.cast(self._callback, C.c_void_p).value, index, 0x30000), "In")
                self.inputs.append(handle)
                for _ in range(32):
                    data = C.create_string_buffer(16384)
                    header = MIDIHDR(lpData=C.addressof(data), dwBufferLength=len(data))
                    self.check(self.dll.midiInPrepareHeader(handle, C.byref(header), C.sizeof(header)), "In")
                    allocated = (handle, header, data)
                    self._buffers.append(allocated)
                    self._input_headers[C.addressof(header)] = allocated
                    self.check(self.dll.midiInAddBuffer(handle, C.byref(header), C.sizeof(header)), "In")
                self.check(self.dll.midiInStart(handle), "In")
            self._worker = threading.Thread(target=self._recycle_loop, daemon=True, name="MU-MIDI-input")
            self._worker.start()
            available=ports()
            self.diagnose('transport_open',selected_inputs=[p for p in available['inputs'] if p['id'] in input_ids],
                          selected_outputs=[p for p in available['outputs'] if p['id'] in output_ids])
        except Exception:
            self.close()
            raise

    def _recycle_loop(self):
        while not self._stop.is_set():
            try:
                handle, address = self._recycle.get(timeout=0.01)
            except queue.Empty:
                continue
            # Input buffers must not wait behind a long outgoing SysEx.
            with self._input_lock:
                if not self._stop.is_set():
                    header = C.cast(address, C.POINTER(MIDIHDR))
                    header.contents.dwBytesRecorded = 0
                    code=self.dll.midiInAddBuffer(handle,header,C.sizeof(MIDIHDR))
                    if code:
                        self._stats['buffer_errors']+=1
                        self.diagnose('driver_buffer_error',code=int(code),header=int(address))
                        self._input_fault(f'MIDI入力バッファの再登録に失敗しました（{code}）。接続を解除して再接続してください。')
                    else:self._stats['buffers_recycled']+=1

    def send(self, data: bytes, port=0):
        data = bytes(data)
        with self._lock:
            if port not in self.outputs:
                raise MidiError(f"出力ポート{'ABCD'[port] if port < 4 else port}が接続されていません。")
            handle = self.outputs[port]
            if data[:1] == b"\xf0":
                if not data.endswith(b"\xf7") or len(data) > 262144:
                    raise MidiError("不正なSysExデータです。")
                buf = C.create_string_buffer(data)
                header = MIDIHDR(lpData=C.addressof(buf), dwBufferLength=len(data))
                self.check(self.dll.midiOutPrepareHeader(handle, C.byref(header), C.sizeof(header)))
                code = self.dll.midiOutLongMsg(handle, C.byref(header), C.sizeof(header))
                if code:
                    self.dll.midiOutUnprepareHeader(handle, C.byref(header), C.sizeof(header))
                    self.check(code)
                deadline = time.monotonic() + max(3, len(data) / 2500)
                while not header.dwFlags & 1 and time.monotonic() < deadline:
                    time.sleep(0.001)
                code = self.dll.midiOutUnprepareHeader(handle, C.byref(header), C.sizeof(header))
                if code == 65:  # Driver still owns memory. Keep it alive until close.
                    self._held_outputs.append((handle, header, buf))
                    raise MidiError("SysEx送信がタイムアウトしました。接続を解除して再接続してください。")
                self.check(code)
            else:
                if not 1 <= len(data) <= 3 or data[0] < 0x80 or any(x > 127 for x in data[1:]):
                    raise MidiError("不正なMIDIメッセージです。")
                packed = sum(b << (i * 8) for i, b in enumerate(data))
                self.check(self.dll.midiOutShortMsg(handle, packed))

    def poll(self):
        dropped = self._stats['input_dropped']
        if dropped != self._input_drops_seen:
            self._input_drops_seen = dropped
            self._fragments.clear()
            for _ in range(MAX_INPUT_MESSAGES):
                try:
                    self.messages.get_nowait()
                except queue.Empty:
                    break
            self.diagnose('midi_input_overflow', dropped_total=dropped)
            raise MidiError('MIDI受信が上限を超えました。入力を確認してください。')
        try:fault=self._faults.get_nowait()
        except queue.Empty:pass
        else:raise MidiError(fault)
        result = []
        for _ in range(MAX_INPUT_MESSAGES):
            try:
                source, raw, timestamp = self.messages.get_nowait()
            except queue.Empty:
                break
            if raw and 0x80<=raw[0]<0xf0 and len(raw)<=3:
                interrupted=self._fragments.pop(source,None)
                if interrupted:
                    self._stats['framing_errors']+=1;self.diagnose('sysex_interrupted',source=source,raw=bytes(interrupted),status=raw[0])
                result.append((source,raw,timestamp));continue
            if raw[:1] != b"\xf0" and source not in self._fragments:
                if raw and raw[0]>=0xf8:result.append((source,raw,timestamp))
                else:
                    self._stats['framing_errors']+=1
                    self.diagnose('orphan_sysex_chunk',source=source,raw=raw)
                continue
            fragment = self._fragments.setdefault(source, bytearray())
            for b in raw:
                if b >= 0xF8:
                    continue
                if b == 0xF0:
                    if fragment:
                        self._stats['framing_errors']+=1;self.diagnose('sysex_restarted',source=source,raw=bytes(fragment))
                    fragment.clear()
                    fragment.append(b)
                elif b == 0xF7 and fragment:
                    fragment.append(b)
                    result.append((source, bytes(fragment), timestamp))
                    fragment.clear()
                elif b>=0x80:
                    if fragment:
                        self._stats['framing_errors']+=1;self.diagnose('sysex_interrupted',source=source,raw=bytes(fragment),status=b)
                    fragment.clear()
                elif fragment:fragment.append(b)
                if len(fragment) > 1048576:
                    fragment.clear()
            if not fragment:
                self._fragments.pop(source, None)
        return result

    def close(self):
        self.diagnose('transport_closing',**self.diagnostic_snapshot())
        with self._lock:
            self._stop.set()
        if self._worker and self._worker is not threading.current_thread():
            self._worker.join(timeout=2)
        self._worker = None
        for handle in self.inputs:
            self.dll.midiInStop(handle)
            self.dll.midiInReset(handle)
        retained = []
        for handle, header, data in self._buffers:
            code = self.dll.midiInUnprepareHeader(handle, C.byref(header), C.sizeof(header))
            if code:
                retained.append((handle, header, data))
        self._buffers = retained
        self._input_headers.clear()
        for handle in self.inputs:
            self.dll.midiInClose(handle)
        self.inputs.clear()
        for handle in self.outputs.values():
            # Reset only if an outstanding asynchronous buffer must be released.
            if any(h.value == handle.value for h, _, _ in self._held_outputs):
                self.dll.midiOutReset(handle)
            for h, header, _ in self._held_outputs:
                if h.value == handle.value:
                    self.dll.midiOutUnprepareHeader(h, C.byref(header), C.sizeof(header))
            self.dll.midiOutClose(handle)
        self.outputs.clear()
        self._held_outputs.clear()
        self._fragments.clear()
        self._input_drops_seen = self._stats['input_dropped']
        # Reset callbacks can return old headers; never reuse them on reopen.
        for pending in (self.messages,self._recycle,self._faults):
            while True:
                try:pending.get_nowait()
                except queue.Empty:break

