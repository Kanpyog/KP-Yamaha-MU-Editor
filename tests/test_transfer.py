import tempfile,unittest,itertools
from unittest.mock import patch
from kp_mu_editor.engine import Engine,write_midi,load_midi
from kp_mu_editor.protocol import bulk,parse
from kp_mu_editor.catalog import Catalog
from kp_mu_editor.schema import PROFILES

class FakeTransport:
    def __init__(self,reply=True,wrong=False):self.sent=[];self.reply=reply;self.wrong=wrong;self.pending=[];self.last=None
    def send(self,raw,port=0):
        self.sent.append(raw)
        p=parse(raw)
        if p and p.bulk:self.last=p
        elif len(raw)>3 and raw[2]&0xf0==0x20 and self.reply:
            data=bytes([1])+self.last.data[1:] if self.wrong else self.last.data
            self.pending.append((0,bulk(self.last.address,data,model=self.last.model),0))
    def poll(self):result=self.pending;self.pending=[];return result

class TransferTests(unittest.TestCase):
    def test_bulk_setup_midi_can_be_played_back(self):
        from pathlib import Path
        raw=bulk((8,0,0),[2,0,0,0])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'setup.mid';write_midi(path,[raw]);schedule=load_midi(path,True)
            self.assertEqual(schedule[0][3],raw);self.assertGreaterEqual(schedule[0][0],.16)
            self.assertEqual(load_midi(path,False),[])

    def test_each_bulk_waits_for_readback(self):
        with tempfile.TemporaryDirectory() as directory:
            e=Engine(directory,start_worker=False);e.transport=FakeTransport();e.connected=True
            raw=bulk((8,0,0),[2,0,0,0])
            with patch('kp_mu_editor.engine.time.sleep') as sleep:e._send_batch([(0,raw)],'test',.003)
            self.assertGreaterEqual(sleep.call_args_list[0].args[0],.15)
            self.assertEqual(len(e.transport.sent),2);self.assertEqual(e.transport.sent[1][2],0x20)
            e.close()

    def test_lost_reply_stops_before_next_write(self):
        with tempfile.TemporaryDirectory() as directory:
            e=Engine(directory,start_worker=False);e.transport=FakeTransport(False);e.connected=True
            raw=bulk((8,0,0),[2,0,0,0])
            with patch('kp_mu_editor.engine.time.sleep'),patch('kp_mu_editor.engine.time.monotonic',side_effect=itertools.count(0,.2)):
                with self.assertRaises(RuntimeError):e._send_batch([(0,raw),(0,raw)],'test',.003)
            self.assertEqual(sum(bool(parse(x) and parse(x).bulk) for x in e.transport.sent),1);e.close()

    def test_changed_real_data_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            e=Engine(directory,start_worker=False);e.transport=FakeTransport(wrong=True);e.connected=True
            with patch('kp_mu_editor.engine.time.sleep'):
                with self.assertRaises(RuntimeError):e._send_batch([(0,bulk((8,0,0),[2,0,0,0]))],'test',.15)
            e.close()

    def test_documented_unused_effect_byte(self):
        c=Catalog();p=parse(bulk((3,1,0x20),[120,0,0,79,0,0]))
        self.assertEqual(c.readback_offsets(p,(0x49,0)),{0})

    def test_kit_banks_and_gm2(self):
        c=Catalog();profile=PROFILES['MU500'];kits=c.kits(profile)
        self.assertTrue(any(x['msb']==126 and x['program']==0 and x['name']=='SFX Kit 1' for x in kits))
        self.assertEqual(len({(x['msb'],x['lsb'],x['program']) for x in kits}),len(kits))
        self.assertEqual({x['program'] for x in c.voices(profile,mode='GM2') if x['lsb']==0},set(range(128)))
        self.assertFalse(PROFILES['MU100B'].performance);self.assertTrue(PROFILES['MU90'].hpf)

if __name__=='__main__':unittest.main()
