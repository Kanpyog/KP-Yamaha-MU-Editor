"""Bank-only selections must commit; SFX families are not GM program families."""
import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from kp_mu_editor.app import MainWindow
from kp_mu_editor.catalog import Catalog
from kp_mu_editor.engine import write_midi,load_midi
from kp_mu_editor.protocol import parse,change
from kp_mu_editor.schema import PROFILES,PART_BY_KEY,DRUM,part_params
from kp_mu_editor.session import Session


class RecordingEngine:
    connected=True;playing=False;device=0;transport=None;thru=False;thru_port=0
    def __init__(self):self.sent=[];self.commands=[]
    def send(self,messages,*args,**kwargs):self.sent.extend(messages)
    def submit(self,*args):self.commands.append(args)
    def close(self):pass


class VoiceCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.catalog=Catalog()

    def test_sfx_noise_rain_and_car_are_sfx_with_clean_names(self):
        rows={(v['msb'],v['lsb'],v['program']):v for v in self.catalog.voices(PROFILES['MU500'])}
        for program,name in ((0,'CuttngNz'),(32,'Shower'),(83,'CarCrash')):
            v=rows[(64,0,program)];self.assertEqual(v['category'],'SFX');self.assertEqual(v['name'],name)
        self.assertTrue(all(v['category']=='SFX' for v in rows.values() if v['msb']==64))

    def test_model_exclusive_families_follow_bank_headings(self):
        rows={(v['msb'],v['lsb'],v['program']):v for v in self.catalog.voices(PROFILES['MU500'])}
        for lsb,category in ((0,'MU100 Exclusive'),(8,'MU100 Exclusive'),(48,'Phrase / Loop'),(64,'SFX'),(72,'SFX'),(88,'SFX'),(96,'Rhythm / Loop')):
            self.assertEqual(rows[(48,lsb,0)]['category'],category)
        self.assertEqual(rows[(0,0,0)]['category'],'Piano')
        self.assertEqual(rows[(0,0,32)]['category'],'Bass')

    def test_categories_keep_mode_model_and_native_map_filters(self):
        for native in (False,True):
            voices=self.catalog.voices(PROFILES['MU500'],native)
            self.assertEqual(len(voices),1224)
            self.assertEqual(len(voices),len({(v['msb'],v['lsb'],v['program']) for v in voices}))
        self.assertNotEqual(self.catalog.voice_name(PROFILES['MU500'],0,0,0,True),self.catalog.voice_name(PROFILES['MU500'],0,0,0,False))
        self.assertTrue(all(v['msb']==v['lsb']==0 for v in self.catalog.voices(PROFILES['MU50'],mode='GM')))
        self.assertTrue(all(v['msb']==121 and v['category'] for v in self.catalog.voices(PROFILES['MU500'],mode='GM2')))


class VoiceSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.temp=tempfile.TemporaryDirectory();self.w=MainWindow(self.temp.name);self.w.engine.close()
        self.w.engine=RecordingEngine();self.w.detected_name='MU500'
        self.w.show();self.app.processEvents();self.set_voice(0,0,48)

    def tearDown(self):
        self.w.close();self.w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.temp.cleanup()

    def set_voice(self,msb,lsb,program,index=0):
        for key,value in [('bank_msb',msb),('bank_lsb',lsb),('program',program)]:
            self.w.session.set(next(p for p in part_params(self.w.session.profile) if p.key==key),value,index)

    def packets(self):return [parse(raw) for port,raw in self.w.engine.sent]

    def test_lsb_only_selection_commits_all_three_fields_in_order(self):
        self.w.assign_voice(0,40,48)
        packets=self.packets()
        self.assertEqual([p.address for p in packets],[(8,0,1),(8,0,2),(8,0,3)])
        self.assertEqual([p.data for p in packets],[b'\x00',b'\x28',b'\x30'])
        # Model the MU's pending-bank behavior: only PROGRAM commits a bank.
        pending=[0,0];actual=(0,0,48)
        for p in packets:
            if p.address[2] in (1,2):pending[p.address[2]-1]=p.data[0]
            else:actual=(*pending,p.data[0])
        self.assertEqual(actual,(0,40,48))

    def test_bank_field_editor_uses_the_same_commit_path(self):
        self.w.edit(PART_BY_KEY['bank_lsb'],64)
        self.assertEqual([p.address[2] for p in self.packets()],[1,2,3])
        self.assertEqual(self.packets()[-1].data,b'\x30')

    def test_nondefault_part_and_receive_off_still_target_physical_part(self):
        self.set_voice(0,0,48,63);self.w.session.set(PART_BY_KEY['receive'],127,63)
        self.w.assign_voice(0,40,48,index=63)
        self.assertEqual([p.address for p in self.packets()],[(8,63,1),(8,63,2),(8,63,3)])
        self.assertTrue(all(port==0 for port,raw in self.w.engine.sent))

    def test_normal_voice_leaves_shared_drum_setup_intact(self):
        w=self.w;w.selected_part=9;self.set_voice(127,0,0,9)
        level=next(p for p in DRUM if p.key=='level');w.session.set(level,91,38,0)
        with patch.object(QMessageBox,'question',side_effect=AssertionError('normal voice must not ask to reset a drum setup')):
            w.assign_voice(0,0,0)
        self.assertEqual(w.session.get(PART_BY_KEY['mode'],9),0)
        self.assertEqual(w.session.get(level,38,0),91)
        self.assertEqual([p.address[2] for p in self.packets()],[7,1,2,3])

    def test_selecting_kit_on_normal_part_sets_mode_before_tone(self):
        self.w.assign_voice(127,0,8)
        self.assertEqual(self.w.session.get(PART_BY_KEY['mode']),1)
        self.assertEqual([p.address[2] for p in self.packets()],[7,1,2,3])

    def test_reselecting_same_shared_kit_does_not_reset_edits(self):
        w=self.w;w.selected_part=9;self.set_voice(127,0,0,9)
        level=next(p for p in DRUM if p.key=='level');w.session.set(level,91,38,0)
        before=w.session.snapshot()
        with patch.object(QMessageBox,'question',side_effect=AssertionError('same kit must not reset')):w.assign_voice(127,0,0)
        self.assertEqual(w.session.snapshot(),before);self.assertEqual(w.engine.sent,[]);self.assertEqual(w.engine.commands,[])

    def test_cancel_shared_kit_change_preserves_values_and_sends_nothing(self):
        w=self.w;w.selected_part=9;self.set_voice(127,0,0,9);before=w.session.snapshot()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No):w.assign_voice(127,0,8)
        self.assertEqual(w.session.snapshot(),before);self.assertEqual(w.engine.sent,[])

    def test_undo_redo_and_smf_retain_bank_and_program_commit(self):
        w=self.w;w.assign_voice(0,40,48);w.engine.sent.clear();w.undo()
        self.assertEqual(w.session.get(PART_BY_KEY['bank_lsb']),0)
        self.assertEqual([p.address[2] for p in self.packets()],[1,2,3])
        w.engine.sent.clear();w.undo(True)
        self.assertEqual(w.session.get(PART_BY_KEY['bank_lsb']),40)
        path=Path(self.temp.name)/'voice.mid';write_midi(path,w.session.export_messages())
        packets=[parse(raw) for seconds,order,port,raw in load_midi(path)]
        self.assertEqual([p.address[2] for p in packets],[1,2,3])
        self.assertEqual(packets[-1].data,b'\x30')

    def test_export_sets_part_mode_before_bank_and_program(self):
        self.w.assign_voice(127,0,8)
        self.assertEqual([parse(raw).address[2] for raw in self.w.session.export_messages()],[7,1,2,3])

    def test_sfx_filter_shows_real_sfx_and_does_not_apply_hidden_selection(self):
        w=self.w;w.navigate(1);page=w.pages[1]
        piano=next(i for i,v in enumerate(page.rows) if (v['msb'],v['lsb'],v['program'])==(0,0,0))
        page.grid.setCurrentCell(piano,1)
        page.category.setCurrentText('SFX');page.apply()
        self.assertEqual(w.engine.sent,[])
        visible=[v for i,v in enumerate(page.rows) if not page.grid.isRowHidden(i)]
        self.assertTrue(visible);self.assertTrue(all(v['category']=='SFX' for v in visible))
        self.assertTrue(any(v['msb']==64 for v in visible));self.assertTrue(any(v['msb']==48 for v in visible))

    def test_mu5_keeps_native_protocol_and_has_no_lsb_message(self):
        w=self.w;w.session=Session('MU5');w.detected_name='MU5';w.assign_voice(0,0,4)
        packets=self.packets();self.assertEqual(len(packets),2)
        self.assertTrue(all(p.model==0x44 for p in packets))
        self.assertEqual([p.address[2] for p in packets],[0,1])


if __name__=='__main__':unittest.main()
