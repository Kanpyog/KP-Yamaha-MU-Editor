import tempfile,unittest,itertools
from pathlib import Path
from unittest.mock import patch
from kp_mu_editor.engine import Engine,write_midi,load_midi
from kp_mu_editor.protocol import bulk,parse
from kp_mu_editor.catalog import Catalog
from kp_mu_editor.schema import PROFILES,SetupScope,read_blocks,setup_read_blocks
from kp_mu_editor.session import Session

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


def mixed_session(model='MU500'):
    session=Session(model)
    session.receive(bulk((8,0,0),range(21)))
    session.receive(bulk((8,0,0x70),[0,0,63,65]))
    session.receive(bulk((8,0,0x74),[0,0,12,54]))
    session.receive(bulk((2,1,0),[1,0,56]))
    session.receive(bulk((2,0x40,0),[0,64,12]))
    session.receive(bulk((3,1,0),[0x49,0]))
    session.receive(bulk((0x30,38,0),[64,64,100,0,64,127,127,127]))
    return session


class TransferTests(unittest.TestCase):
    def test_scopes_keep_patch_bytes_out_of_partial_midi(self):
        session=mixed_session()
        all_packets={parse(raw).address:parse(raw) for raw in session.export_messages()}
        self.assertIn((8,0,0),all_packets)
        self.assertEqual(all_packets[(8,0,0)].data[1:4],b'\x01\x02\x03')
        expected_part={0x11:17,0x12:18,0x13:19,0x14:20,0x72:63,0x73:65,0x76:12,0x77:54}
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'scope.mid'
            for scope in (SetupScope.EFFECTS,SetupScope.DRUM_MAP):
                with self.subTest(scope=scope):
                    write_midi(path,session.export_messages(scope))
                    self.assertEqual(path.read_bytes()[8:10],b'\x00\x01')
                    packets={parse(raw).address:parse(raw) for _,_,_,raw in load_midi(path)}
                    if scope is SetupScope.DRUM_MAP:
                        self.assertEqual(list(packets),[(0x30,38,0)])
                        self.assertEqual(packets[(0x30,38,0)].data,all_packets[(0x30,38,0)].data)
                    else:
                        self.assertEqual(set(packets),{(2,1,0),(2,0x40,0),(3,1,0)}
                                         | {(8,0,low) for low in expected_part})
                        for low,value in expected_part.items():
                            packet=packets[(8,0,low)]
                            self.assertFalse(packet.bulk)
                            self.assertEqual(packet.data,bytes([value]))

    def test_read_plans_use_individual_part_effect_fields_and_model_limits(self):
        profile=PROFILES['MU500']
        self.assertEqual(setup_read_blocks(profile,SetupScope.ALL),read_blocks(profile))
        effects=setup_read_blocks(profile,SetupScope.EFFECTS)
        self.assertEqual({entry[1][2] for entry in effects if entry[1][:2]==(8,0)},
                         {0x11,0x12,0x13,0x14,0x72,0x73,0x76,0x77})
        self.assertTrue(all(len(entry)==3 and entry[2] for entry in effects if entry[1][0]==8))
        self.assertFalse(any(entry[1][0] in (0,1,0x30,0x31,0x32,0x33) for entry in effects))
        drums=setup_read_blocks(profile,SetupScope.DRUM_MAP)
        self.assertEqual({entry[1][0] for entry in drums},{0x30,0x31,0x32,0x33})
        self.assertEqual(len(drums),1264)
        for scope in (SetupScope.EFFECTS,SetupScope.DRUM_MAP):
            self.assertEqual(setup_read_blocks(PROFILES['MU5'],scope),[])
        ad=mixed_session('MU100')
        ad.receive(bulk((0x10,1,0),range(21)))
        packets=[parse(raw) for raw in ad.export_messages(SetupScope.EFFECTS)]
        self.assertEqual([p.address for p in packets if p.address[0]==0x10],
                         [(0x10,1,low) for low in range(0x11,0x15)])

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


class ScopedTransferUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def test_scope_is_used_by_read_send_and_both_smf_actions(self):
        from kp_mu_editor.app import MainWindow,QInputDialog,QFileDialog
        from kp_mu_editor.i18n import set_language
        with tempfile.TemporaryDirectory() as directory:
            w=MainWindow(directory,offline=True)
            w.engine.close()
            w.engine.connected=True
            w.session=mixed_session()
            w.detected_name='MU500'
            set_language('en',self.app)
            effects=setup_read_blocks(w.session.profile,SetupScope.EFFECTS)
            drums=setup_read_blocks(w.session.profile,SetupScope.DRUM_MAP)
            try:
                with patch.object(w.engine,'submit') as submit:
                    with patch.object(QInputDialog,'getItem',return_value=('Effects only',True)) as picker:
                        w.read_from_device()
                    self.assertEqual(picker.call_args.args[3],['All','Effects only','Drum map only'])
                    submit.assert_called_once_with('read',(effects,'エフェクト設定取得'))
                    submit.reset_mock()
                    with patch.object(QInputDialog,'getItem',return_value=('Drum map only',True)):
                        w.send_to_device()
                    messages=[(0,raw) for raw in w.session.export_messages(SetupScope.DRUM_MAP)]
                    submit.assert_called_once_with('send_set',(messages,drums))
                    submit.reset_mock()
                    with patch.object(QInputDialog,'getItem',return_value=('',False)):
                        w.read_from_device()
                        w.send_to_device()
                    submit.assert_not_called()
                for action in (w.save_midi,w.save_session):
                    path=Path(directory)/(action.__name__+'.mid')
                    with patch.object(QFileDialog,'getSaveFileName',return_value=(str(path),'SMF Format 1')):
                        with patch.object(QInputDialog,'getItem',return_value=('Drum map only',True)):
                            action()
                    self.assertEqual([raw for _,_,_,raw in load_midi(path)],[raw for _,raw in messages])
                json_path=Path(directory)/'set.mu.json'
                with patch.object(QFileDialog,'getSaveFileName',return_value=(str(json_path),'MU Set JSON')):
                    with patch.object(QInputDialog,'getItem') as picker:
                        w.save_session()
                picker.assert_not_called()
                self.assertEqual(Session.load(json_path).memory,w.session.memory)
            finally:
                w.engine.connected=False
                w.close()
                w.deleteLater()
                self.app.processEvents()


if __name__=='__main__':unittest.main()
