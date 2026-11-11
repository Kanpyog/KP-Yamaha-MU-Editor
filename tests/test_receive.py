"""Synthetic MU500 frames for retries, cancellation and diagnostics."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from kp_mu_editor.engine import Engine
from kp_mu_editor.protocol import bulk, parse, split_sysex


ADDRESS = (0x32, 0x1a, 0)
GOOD = bulk(ADDRESS, [64] * 16)
BAD = GOOD[:-2] + bytes(((GOOD[-2] + 1) & 0x7f, 0xf7))
_REPLY = bulk((0x32, 0x18, 0x50), [64, 64])
FOREIGN = _REPLY[:1] + b'\x47' + _REPLY[2:]


class Clock:
    def __init__(self):self.now=100.
    def monotonic(self):return self.now
    def sleep(self,seconds):self.now+=max(.0001,seconds)


class ReadTransport:
    def __init__(self,policy):self.policy=policy;self.sent=[];self.pending=[];self.counts={}
    def send(self,raw,port=0):
        self.sent.append(raw)
        address=tuple(raw[4:7]);n=self.counts.get(address,0)+1;self.counts[address]=n
        self.pending.extend((4,x,0) for x in self.policy(address,n))
    def poll(self):result=self.pending;self.pending=[];return result


class ReceiveTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.e=Engine(self.folder.name,start_worker=False)
        self.e.connected=True;self.received=[];self.activity=[]
        self.e.received.connect(self.received.append);self.e.activity.connect(self.activity.append)
        self.clock=Clock()
        self.time_patch=patch('kp_mu_editor.engine.time.monotonic',self.clock.monotonic)
        self.sleep_patch=patch('kp_mu_editor.engine.time.sleep',self.clock.sleep)
        self.time_patch.start();self.sleep_patch.start()

    def tearDown(self):
        self.e.close();self.sleep_patch.stop();self.time_patch.stop();self.folder.cleanup()

    def read(self,blocks=None):
        return self.e._read(blocks or [(0x4c,ADDRESS)],'全設定取得')

    def trace(self,report):
        return [json.loads(line) for line in Path(report['diagnostic_log']).read_text(encoding='utf-8').splitlines()]

    def test_real_bad_frame_is_rejected_once_before_gui_then_retried(self):
        self.e.transport=ReadTransport(lambda addr,n:[BAD if n==1 else GOOD])
        result=self.read()
        self.assertEqual(self.received,[GOOD])
        self.assertEqual(result['count'],1);self.assertEqual(result['missing'],[])
        self.assertEqual(result['invalid'],1);self.assertEqual(result['retry_requests'],1)
        self.assertEqual(result['recovered'],1)
        self.assertEqual(sum('チェックサム' in text for text in self.activity),1)
        self.assertEqual(Path(result['backup']).read_bytes(),GOOD)
        rx=[r for r in self.trace(result) if r['event']=='rx']
        self.assertEqual([r['valid'] for r in rx],[False,True])
        self.assertEqual(rx[0]['raw'],BAD.hex(' '))

    def test_final_recovery_pass_recovers_after_three_failed_requests(self):
        self.e.transport=ReadTransport(lambda addr,n:[BAD if n<=3 else GOOD])
        result=self.read()
        self.assertEqual(result['missing'],[]);self.assertEqual(result['count'],1)
        self.assertEqual(result['invalid'],3);self.assertEqual(result['retry_requests'],3)
        self.assertEqual(len(self.e.transport.sent),4)
        self.assertGreater(self.clock.now-100.,.2)
        self.assertLess(self.clock.now-100.,.6)

    def test_permanent_corruption_is_reported_and_never_imported_or_backed_up(self):
        self.e.transport=ReadTransport(lambda addr,n:[BAD])
        result=self.read()
        self.assertEqual(self.received,[]);self.assertEqual(result['count'],0)
        self.assertEqual(result['missing'],[[0x4c,list(ADDRESS)]])
        self.assertEqual(result['backup'],'');self.assertEqual(result['invalid'],5)
        self.assertEqual(len(self.e.transport.sent),5)

    def test_corrupt_manufacturer_is_recorded_without_repairing_it(self):
        good=bytes([0xf0,0x43])+FOREIGN[2:]
        self.e.transport=ReadTransport(lambda addr,n:[FOREIGN if n==1 else good])
        result=self.read([(0x4c,(0x32,0x18,0x50))])
        self.assertEqual(self.received,[good]);self.assertEqual(result['unrecognized'],1)
        self.assertEqual(result['count'],1)
        self.assertIn(FOREIGN.hex(' '),Path(result['diagnostic_log']).read_text(encoding='utf-8'))

    def test_unrelated_valid_addresses_and_devices_do_not_complete_request(self):
        unrelated=bulk((8,0,0),[64]);wrong_device=bulk(ADDRESS,parse(GOOD).data,device=1)
        self.e.transport=ReadTransport(lambda addr,n:[unrelated,wrong_device] if n==1 else [GOOD])
        result=self.read()
        self.assertEqual(result['count'],1);self.assertEqual(result['retry_requests'],1)
        self.assertNotIn(wrong_device,self.received)
        self.assertEqual(split_sysex(Path(result['backup']).read_bytes()),[GOOD])

    def test_notify_false_keeps_session_untouched_but_creates_backup(self):
        self.e.transport=ReadTransport(lambda addr,n:[GOOD])
        result=self.e._read([(0x4c,ADDRESS)],'送信前バックアップ',False)
        self.assertEqual(self.received,[]);self.assertEqual(result['count'],1)

    def test_cancel_during_wait_stops_retries(self):
        self.e.transport=ReadTransport(lambda addr,n:[])
        original_sleep=self.clock.sleep
        def cancel(seconds):
            original_sleep(seconds);self.e.cancel.set()
        with patch('kp_mu_editor.engine.time.sleep',cancel):result=self.read()
        self.assertTrue(result['cancelled']);self.assertEqual(len(self.e.transport.sent),1)
        self.assertIsNone(self.e._read_trace)
        self.assertEqual(self.trace(result)[-1]['event'],'end')

    def test_diagnostics_keep_entire_long_reply(self):
        raw=bulk(ADDRESS,[64]*256)
        self.e.transport=ReadTransport(lambda addr,n:[raw])
        result=self.read()
        record=next(r for r in self.trace(result) if r['event']=='rx')
        self.assertEqual(record['raw'],raw.hex(' '));self.assertGreater(len(record['raw']),180)

    def test_request_failure_closes_trace(self):
        self.e.transport=ReadTransport(lambda addr,n:[])
        with patch.object(self.e.transport,'send',side_effect=RuntimeError('disconnected')):
            with self.assertRaisesRegex(RuntimeError,'disconnected'):self.read()
        self.assertIsNone(self.e._read_trace)
        path=next((Path(self.folder.name)/'logs').glob('read_*.jsonl'))
        self.assertEqual(json.loads(path.read_text(encoding='utf-8').splitlines()[-1])['event'],'end')

    def test_log_write_failure_does_not_prevent_receiving_settings(self):
        self.e.transport=ReadTransport(lambda addr,n:[GOOD])
        with patch('kp_mu_editor.engine.ReadTrace',side_effect=OSError('read only')):result=self.read()
        self.assertEqual(result['count'],1);self.assertEqual(result['diagnostic_log'],'')

    def test_silent_dropout_is_retried_without_misreporting_corruption(self):
        self.e.transport=ReadTransport(lambda addr,n:[] if n==1 else [GOOD])
        result=self.read()
        self.assertEqual(self.received,[GOOD]);self.assertEqual(result['invalid'],0)
        self.assertEqual(result['retry_requests'],1);self.assertEqual(result['missing'],[])

    def test_valid_late_response_during_backoff_avoids_needless_retransmission(self):
        transport=ReadTransport(lambda addr,n:[BAD]);original=transport.poll
        sent_late=False
        def poll():
            nonlocal sent_late
            packets=original()
            if self.clock.now>=100.01 and not sent_late:
                packets.append((4,GOOD,self.clock.now));sent_late=True
            return packets
        transport.poll=poll;self.e.transport=transport
        result=self.read()
        self.assertEqual(result['count'],1);self.assertEqual(result['retry_requests'],0)
        self.assertEqual(len(transport.sent),1);self.assertEqual(self.received,[GOOD])
        self.assertLess(result['timings']['retry_wait_s'],.025)

    def test_worker_reset_orders_panic_reset_wait_and_read_without_real_midi(self):
        class Fake:
            outputs={0:1}
            def __init__(inner):inner.sent=[];inner.pending=[];inner.closed=False
            def send(inner,raw,port=0):
                inner.sent.append((raw,self.clock.now))
                if raw[:4]==bytes.fromhex('f0 43 34 4c'):
                    inner.pending.append((4,bulk(ADDRESS,parse(GOOD).data,device=4),self.clock.now))
            def poll(inner):result=inner.pending;inner.pending=[];return result
            def close(inner):inner.closed=True
        fake=Fake();self.e.transport=fake;self.e.device=4
        self.e.schedule=[(1,1,0,b'\x90\x3c\x60')];self.e.effect_types[(3,0,0)]=(5,0)
        applied=[];self.e.reset_applied.connect(lambda:applied.append(True))
        self.e.finished.connect(lambda *args:self.e.shutdown.set())
        self.e.reset_xg([(0x4c,ADDRESS)])
        class Cancel:
            def __init__(inner):inner.value=True
            def clear(inner):inner.value=False
            def is_set(inner):return inner.value
            def wait(inner,seconds):self.clock.sleep(seconds);return inner.value
        self.e.cancel=Cancel();self.e._run()
        reset=bytes.fromhex('f0 43 14 4c 00 00 7e 00 f7')
        self.assertEqual([raw for raw,stamp in fake.sent if raw==reset],[reset])
        i=next(i for i,(raw,_) in enumerate(fake.sent) if raw==reset)
        self.assertEqual(i,64);self.assertGreaterEqual(fake.sent[i+1][1]-fake.sent[i][1],.099)
        self.assertEqual(applied,[True]);self.assertEqual(self.e.effect_types,{})
        self.assertEqual(self.e.schedule,[]);self.assertTrue(fake.closed)
        self.e.cancel=self.e.shutdown # teardown needs an Event with set()

    def test_read_stops_local_playback_instead_of_resuming_overdue_notes(self):
        transport=ReadTransport(lambda addr,n:[GOOD]);transport.outputs={}
        transport.close=lambda:None;self.e.transport=transport
        self.e.playing=True;self.e.play_start=self.clock.now
        self.e.schedule=[(10,0,0,b'\x90\x3c\x60')]
        self.e.finished.connect(lambda *args:self.e.shutdown.set())
        self.e.submit('read',([(0x4c,ADDRESS)],'全設定取得'));self.e._run()
        self.assertFalse(self.e.playing);self.assertEqual(self.e.schedule,[])
        self.assertEqual(len(transport.sent),1)


if __name__=='__main__':unittest.main()
