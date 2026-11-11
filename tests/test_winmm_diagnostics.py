"""Exercise native callback contracts against a fake DLL; no device is opened."""
import ctypes as C,threading,time,unittest
from unittest.mock import patch
from kp_mu_editor.winmm import Transport,MIDIHDR,MidiError


class Log:
    debug=True
    def __init__(self):self.events=[]
    def record(self,event,**values):self.events.append((event,values))


class NativeFake:
    def __init__(self):self.added=0;self.fail_add=False;self.recycled=threading.Event()
    def midiInOpen(self,handle,*args):C.cast(handle,C.POINTER(C.c_void_p))[0]=101;return 0
    def midiInAddBuffer(self,*args):
        self.added+=1
        if self.added>32:self.recycled.set()
        return 7 if self.fail_add else 0
    def __getattr__(self,name):return lambda *args:0


class NativeDiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.dll=NativeFake();self.log=Log()
        self.patch=patch('kp_mu_editor.winmm.library',return_value=self.dll);self.patch.start()
        self.ports=patch('kp_mu_editor.winmm.ports',return_value={'inputs':[],'outputs':[]});self.ports.start()
        self.t=Transport(self.log);self.t.open([6],[])

    def tearDown(self):self.t.close();self.ports.stop();self.patch.stop()

    def callback(self,raw,message=0x3c4,invalid=False):
        handle,header,data=self.t._buffers[0];C.memmove(data,raw,len(raw))
        header.dwBytesRecorded=header.dwBufferLength+1 if invalid else len(raw)
        self.t._callback(handle,message,6,C.addressof(header),456)

    def test_raw_callback_precedes_framing_and_recycling_does_not_wait_for_output_lock(self):
        raw=b'\xf0\x43\x00\xf7'
        with self.t._lock:
            self.callback(raw)
            self.assertTrue(self.dll.recycled.wait(1),'Input recycling was blocked by output lock')
        entry=next(v for name,v in self.log.events if name=='driver_rx_chunk')
        self.assertEqual(entry['raw'],raw);self.assertEqual(entry['recorded'],4)
        self.assertEqual(entry['driver_timestamp_ms'],456);self.assertIn('callback_time',entry)
        self.assertEqual(self.t.poll()[0][1],raw)

    def test_driver_longerror_is_visible_and_not_imported(self):
        self.callback(b'\xf0\x43',0x3c6)
        self.assertEqual(self.t.poll(),[])
        self.assertEqual(self.t.diagnostic_snapshot()['long_errors'],1)
        self.assertIn('driver_long_error',[e[0] for e in self.log.events])

    def test_failed_buffer_requeue_becomes_actionable_error(self):
        self.dll.fail_add=True;self.callback(b'\xf0\xf7')
        self.assertTrue(self.dll.recycled.wait(1))
        deadline=time.monotonic()+1
        while not self.t.diagnostic_snapshot()['buffer_errors'] and time.monotonic()<deadline:time.sleep(.001)
        with self.assertRaisesRegex(MidiError,'再登録'):self.t.poll()
        self.assertIn('driver_buffer_error',[e[0] for e in self.log.events])

    def test_invalid_native_length_is_not_read_and_fault_is_reported(self):
        with patch('kp_mu_editor.winmm.C.string_at',side_effect=AssertionError('unsafe read')):
            self.callback(b'',invalid=True)
        with self.assertRaisesRegex(MidiError,'不正な受信バッファ長'):self.t.poll()
        self.assertIn('driver_invalid_recorded_length',[e[0] for e in self.log.events])

    def test_fragmented_sysex_realtime_and_noteoff_keep_separate_frames(self):
        for raw in (b'\xf0\x43\x00',b'\xf8',b'\x4c\xf7',b'\xf0\x43',b'\x80\x3c\x00',b'\xf0\x43\xf7'):
            self.t.messages.put((6,raw,time.monotonic()))
        frames=[raw for _,raw,_ in self.t.poll()]
        self.assertEqual(frames,[b'\xf0\x43\x00\x4c\xf7',b'\x80\x3c\x00',b'\xf0\x43\xf7'])
        self.assertEqual(self.t.diagnostic_snapshot()['framing_errors'],1)

    def test_close_clears_old_headers_and_late_callback_is_ignored(self):
        self.t._recycle.put((C.c_void_p(101),C.addressof(self.t._buffers[0][1])))
        self.t.close();self.t._callback(C.c_void_p(101),0x3c4,6,0,0)
        self.assertTrue(self.t._recycle.empty());self.assertEqual(self.t.poll(),[])
        self.t.open([6],[]);self.assertEqual(len(self.t._buffers),32)


if __name__=='__main__':unittest.main()
