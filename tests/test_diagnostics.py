"""Local diagnostic capture must stay bounded and independent of MIDI I/O."""
import json,tempfile,threading,time,unittest,zipfile,os
from pathlib import Path
from unittest.mock import patch
from kp_mu_editor.diagnostics import Diagnostics


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.log=None

    def tearDown(self):
        if self.log:self.log.close()
        self.temp.cleanup()

    def start(self,**kwargs):
        self.log=Diagnostics(self.root,**kwargs);return self.log

    def entries(self):
        self.assertTrue(self.log.flush())
        return [json.loads(line) for p in sorted(self.log.folder.glob('session_*.jsonl')) for line in p.read_text(encoding='utf-8').splitlines()]

    def test_normal_summaries_debug_raw_bytes_and_runtime_mode_change(self):
        d=self.start();d.record('summary',elapsed_s=3);d.record('hidden_raw',detail=True,raw=b'\xf0\xf7')
        d.set_mode('debug');d.record('visible_raw',detail=True,raw=b'\xf0\x43\xf7')
        entries=self.entries();events=[e['event'] for e in entries]
        self.assertIn('summary',events);self.assertNotIn('hidden_raw',events)
        self.assertEqual(next(e for e in entries if e['event']=='visible_raw')['raw'],'f0 43 f7')
        self.assertIn('windows_midi_environment',events)
        self.assertIn('python',entries[0]);self.assertIn('monotonic',entries[0]);self.assertIn('time',entries[0])

    def test_export_includes_legacy_read_trace_and_complete_lines_only(self):
        d=self.start();d.record('test_marker');folder=self.root/'logs';folder.mkdir()
        (folder/'read_test.jsonl').write_bytes(b'{"event":"rx","raw":"f0 f7"}\n{"partial":')
        path=d.export_bundle(self.root/'bundle.zip')
        with zipfile.ZipFile(path) as z:
            manifest=json.loads(z.read('manifest.json'))
            self.assertTrue(manifest['flush_completed']);self.assertEqual(manifest['writer_error'],'')
            self.assertEqual(z.read('logs/read_test.jsonl'),b'{"event":"rx","raw":"f0 f7"}\n')
            session=next(n for n in z.namelist() if n.startswith('diagnostics/'))
            self.assertIn('test_marker',z.read(session).decode())
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_logging_failure_is_reported_without_raising_into_caller(self):
        (self.root/'diagnostics').write_text('occupied',encoding='utf-8')
        d=self.start();d._thread.join(2)
        self.assertTrue(d.error);self.assertFalse(d.flush(.01));d.record('still_safe')
        path=d.export_bundle(self.root/'failed.zip')
        with zipfile.ZipFile(path) as z:self.assertTrue(json.loads(z.read('manifest.json'))['writer_error'])

    def test_queue_and_memory_limits_do_not_block_producer(self):
        gate=threading.Event();writer=Diagnostics._writer
        def blocked(instance):gate.wait(3);writer(instance)
        with patch.object(Diagnostics,'_writer',blocked):
            d=self.start()
            try:
                for n in range(5200):d.record('busy',index=n)
                self.assertLessEqual(d.queue.qsize(),5000);self.assertGreater(d.dropped,0)
                before=d.dropped;d.record('oversize',raw=b'x'*(8*1024*1024))
                self.assertEqual(d.dropped,before+1);self.assertLessEqual(d._pending_bytes,8*1024*1024)
            finally:gate.set()
        self.assertTrue(d.flush(5));self.assertEqual(d._pending_bytes,0)

    def test_rotation_prunes_only_generated_diagnostics(self):
        folder=self.root/'diagnostics';folder.mkdir();user=folder/'session_user.jsonl';user.write_text('keep')
        old=folder/'session_20200101_000000_000001_123_000.jsonl';old.write_text('old')
        os.utime(old,(1,1));logs=self.root/'logs';logs.mkdir();legacy=logs/'read_keep.jsonl';legacy.write_text('keep')
        d=self.start(max_bytes=1024,keep_bytes=4096)
        for n in range(150):d.record('rotate',index=n,payload='x'*100)
        self.assertTrue(d.flush(5));self.assertFalse(old.exists())
        self.assertEqual(user.read_text(),'keep');self.assertEqual(legacy.read_text(),'keep')
        generated=[p for p in folder.glob('session_*.jsonl') if p!=user]
        self.assertLessEqual(sum(p.stat().st_size for p in generated),5500)
        self.assertTrue(d.path.exists())


if __name__=='__main__':unittest.main()
