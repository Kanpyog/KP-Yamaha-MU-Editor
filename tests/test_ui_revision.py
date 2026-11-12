"""GUI behavior with a recording MIDI engine; never opens hardware ports."""
import tempfile,unittest,json
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt,QPointF,QEvent
from PySide6.QtGui import QMouseEvent,QPalette
from PySide6.QtWidgets import QApplication,QMessageBox
from kp_mu_editor.app import MainWindow,configure_application
from kp_mu_editor.schema import PART_BY_KEY,PROFILES,DRUM,Param
from kp_mu_editor.session import Session
from kp_mu_editor.protocol import parse,change,bulk
from kp_mu_editor.engine import write_midi,load_midi

class RecordingEngine:
    connected=True;playing=False;device=0;transport=None;thru=False;thru_port=0
    def __init__(self):self.sent=[];self.commands=[];self.stopped=False
    def send(self,messages,label='send',interval=.005):self.sent.extend(messages)
    def submit(self,kind,payload=None):self.commands.append((kind,payload))
    def stop(self):self.stopped=True
    def close(self):pass

class RevisionDefaults(unittest.TestCase):
    def test_mu500_default_drum_modes_and_names(self):
        s=Session()
        self.assertEqual([s.get(PART_BY_KEY['mode'],n) for n in (9,25,41,57)],[2,4,1,1])
        self.assertEqual([s.get(PART_BY_KEY['bank_msb'],n) for n in (9,25,41,57)],[127]*4)
        self.assertEqual(s.memory,{})
        self.assertEqual(s.get(PART_BY_KEY['receive'],63),63)

    def test_factory_drums_are_per_note(self):
        s=Session();level=next(p for p in DRUM if p.key=='level')
        self.assertFalse(s.is_modified(level,38,0))
        original=s.get(level,38,0);s.set(level,0 if original else 1,38,0)
        self.assertTrue(s.is_modified(level,38,0));s.set(level,original,38,0);self.assertFalse(s.is_modified(level,38,0))

    def test_format_one_tracks_and_global_restore_order(self):
        import mido
        messages=[change((0,0,4),[127]),change((8,0,11),[99]),change((8,63,11),[88]),bulk((0x30,38,0),[64,64,100])]
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'folder'/'setup.mid';write_midi(path,messages)
            midi=mido.MidiFile(path)
            self.assertEqual(midi.type,1)
            names=[m.name for t in midi.tracks for m in t if m.type=='track_name']
            self.assertIn('Part A01',names);self.assertIn('Part D16',names);self.assertIn('Drum Setup 1',names)
            events=load_midi(path,True)
            self.assertEqual([x[3] for x in events],messages)
            self.assertTrue(all(b[0]>a[0] for a,b in zip(events,events[1:])))

class RevisionGui(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application=QApplication.instance() or QApplication([]);configure_application(cls.application)

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        (Path(self.temp.name)/'preferences.json').write_text(json.dumps({'theme':'light'}),encoding='utf-8')
        self.w=MainWindow(self.temp.name)
        self.w.engine.close();self.w.engine=RecordingEngine();self.w.detected_name='MU500'
        self.w.show();self.application.processEvents();self.w.refresh();self.w.engine.sent.clear()

    def tearDown(self):
        self.w.close();self.application.processEvents();self.w.deleteLater();self.application.processEvents();self.temp.cleanup()

    def packets(self):return [parse(raw) for port,raw in self.w.engine.sent if raw[:2]==b'\xf0\x43']

    def test_partial_read_is_visible_in_status_and_logged_with_details(self):
        self.w.on_finished('全設定取得',{'count':1,'missing':[[76,[8,0,0]]],'invalid':1,'cancelled':False})
        message=self.w.statusBar().currentMessage()
        self.assertIn('未取得 1件',message)
        self.assertIn('前回値または初期値',message)
        log=self.w.settings.monitor.toPlainText()
        self.assertIn('READ SUMMARY',log);self.assertIn('UNREAD BLOCKS',log)

    def test_mode_change_queues_reset_with_settling_time_before_read(self):
        with (patch('kp_mu_editor.app.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes),
              patch.object(self.w.engine,'send') as send,
              patch.object(self.w,'read_all') as read_all):
            self.w.mode_changed('GM2')
            send.assert_called_once_with([(0,bytes.fromhex('F0 7E 7F 09 03 F7'))],'モード切替',interval=.1)
            read_all.assert_called_once_with()

    def test_preferences_and_prominent_master_fields(self):
        w=self.w;self.assertEqual(w.nav.count(),7);self.assertFalse(hasattr(w,'live'))
        self.assertEqual(set(w.master.controls),{'master_volume','transpose','master_tune'})
        w.master.controls['master_volume'].setValue(101)
        self.assertEqual(self.packets()[-1].address,(0,0,4));self.assertEqual(self.packets()[-1].data,bytes([101]))
        w.open_preferences();self.application.processEvents();self.assertTrue(w.preferences_dialog.isVisible())
        self.assertNotIn('master_volume',w.settings.system.controls)
        w.panic_button.click();self.assertTrue(w.engine.stopped)

    def test_native_basic_changes_are_sent_and_do_not_echo(self):
        w=self.w;self.assertEqual(w.voice_map.currentData(),1)
        w.voice_map.setCurrentIndex(w.voice_map.findData(0))
        self.assertEqual(self.packets()[-1].model,0x49);self.assertEqual(self.packets()[-1].address,(0,0,18));self.assertEqual(self.packets()[-1].data,b'\x00')
        w.engine.sent.clear();w.refresh();self.assertEqual(w.engine.sent,[])
        self.assertIn('MU500',w.detected_label.text())

    def test_bend_highlight_returns_to_normal_and_receive_does_not_send(self):
        w=self.w;w.navigate(2);control=w.pages[2].form.controls['bend_pitch']
        self.assertEqual(control.value(),2)
        control.setValue(12);w.refresh();self.assertTrue(control.property('modified'));self.assertTrue(control.font().bold())
        form=w.pages[2].form;form.setCurrentIndex(next(i for i in range(form.count()) if form.tabText(i)=='割当'));self.application.processEvents()
        self.assertEqual(control.lineEdit().palette().color(QPalette.ColorRole.Text).name(),'#486313')
        self.assertTrue(control.lineEdit().font().bold())
        self.assertEqual(self.packets()[-1].data,bytes([76]))
        control.setValue(2);w.refresh();self.assertFalse(control.property('modified'));self.assertFalse(control.font().bold())
        w.engine.sent.clear();w.on_received(change((8,0,0x23),[76]));w.refresh()
        self.assertTrue(control.property('modified'));self.assertEqual(w.engine.sent,[])

    def test_first_edit_undo_transmits_the_initial_value(self):
        w=self.w;w.edit(PART_BY_KEY['volume'],89,0);w.undo()
        self.assertEqual(w.session.get(PART_BY_KEY['volume']),100)
        self.assertEqual(self.packets()[-1].data,bytes([100]))

    def test_shared_drums_and_exclusive_effect_resource(self):
        w=self.w;w.assign_part_mode(0,2)
        self.assertEqual(w.session.get(PART_BY_KEY['mode'],9),2)
        self.assertEqual(w.session.get(PART_BY_KEY['mode'],0),2)
        w.assign_insertion(0,0);w.assign_insertion(1,0)
        self.assertEqual(w.insertion_slots(0),[]);self.assertEqual(w.insertion_slots(1),[0])
        w.refresh();box=w.pages[0].efx_boxes[1]
        self.assertEqual(box.currentText(),'EFX1');self.assertEqual(box.findText('EFX3'),-1)
        w.assign_insertion(1,None);self.assertEqual(w.insertion_slots(1),[])

    def test_mixer_bank_tabs_and_default_drum(self):
        w=self.w;mixer=w.pages[0]
        self.assertEqual(mixer.bank.count(),4)
        self.assertEqual(mixer.mode_boxes[9].currentText(),'DRUM1')
        self.assertIn('Kit',mixer.grid.item(9,1).text())
        mixer.bank.setCurrentIndex(1);self.application.processEvents();w.refresh()
        self.assertEqual(w.selected_part,16);self.assertFalse(mixer.grid.isRowHidden(25));self.assertTrue(mixer.grid.isRowHidden(9))
        self.assertEqual(mixer.mode_boxes[25].currentText(),'DRUM3')

    def test_effect_tabs_and_named_part_assignment(self):
        w=self.w;w.navigate(4);fx=w.pages[4]
        self.assertEqual([fx.block.tabText(i) for i in range(fx.block.count())],['Reverb','Chorus','Variation','EFX 1','EFX 2','Multi EQ'])
        fx.block.setCurrentIndex(3);control=fx.routing.controls['part']
        self.assertEqual(control.itemText(control.findData(127)),'Off')
        self.assertEqual(control.itemText(control.findData(0)),'A1');self.assertEqual(control.itemText(control.findData(63)),'D16')
        control.setCurrentIndex(control.findData(31))
        self.assertEqual(self.packets()[-1].address,(3,0,12));self.assertEqual(self.packets()[-1].data,bytes([31]))
        self.assertNotIn('part',fx.form.controls)

    def test_effect_number_fields_do_not_overlap_in_a_small_window(self):
        w=self.w;w.resize(1120,760);w.navigate(4);fx=w.pages[4];fx.block.setCurrentIndex(3)
        fx.form.setCurrentIndex(next(i for i in range(fx.form.count()) if fx.form.tabText(i)=='パラメーター'));self.application.processEvents()
        controls=[fx.form.controls[p.key] for p in fx.form.params if p.group=='パラメーター']
        for previous,current in zip(controls,controls[1:]):self.assertGreaterEqual(current.y(),previous.y()+previous.height())

    def test_envelope_and_filter_are_linked(self):
        w=self.w;w.navigate(2);page=w.pages[2];form=page.form
        self.assertIn('ADSR',[form.tabText(i) for i in range(form.count())]);self.assertFalse(form.sustain.isEnabled())
        before=page.graph.envelope_points();form.controls['attack'].setValue(20);w.refresh()
        self.assertNotEqual(page.graph.envelope_points(),before)
        before=page.graph.filter_points();form.controls['resonance'].setValue(30);w.refresh()
        self.assertNotEqual(page.graph.filter_points(),before)

    def send_drag(self,target,steps):
        center=target.rect().center();global_point=target.mapToGlobal(center)
        def event(kind,dy,button,buttons):
            local=QPointF(center.x(),center.y()+dy);global_pos=QPointF(global_point.x(),global_point.y()+dy)
            return QMouseEvent(kind,local,global_pos,button,buttons,Qt.KeyboardModifier.NoModifier)
        self.application.sendEvent(target,event(QEvent.Type.MouseButtonPress,0,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton))
        for step in steps:self.application.sendEvent(target,event(QEvent.Type.MouseMove,step,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton))
        self.assertTrue(self.w.engine.sent,'The parameter must transmit during the drag, before release')
        self.application.sendEvent(target,event(QEvent.Type.MouseButtonRelease,steps[-1],Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton))

    def test_drag_spin_transmits_while_moving_and_groups_undo(self):
        w=self.w;w.navigate(2);control=w.pages[2].form.controls['volume'];before=control.value();history=len(w.session.undo_stack)
        self.send_drag(control.lineEdit(),[-3,-6,-9])
        self.assertEqual(control.value(),before+3);self.assertEqual(len(w.session.undo_stack),history+1)
        self.assertEqual([p.data[0] for p in self.packets()],[before+1,before+2,before+3])
        w.undo();self.assertEqual(w.session.get(PART_BY_KEY['volume']),before)

    def test_table_drag_transmits_without_opening_an_editor(self):
        w=self.w;mixer=w.pages[0];g=mixer.grid;target=g.viewport()
        rect=g.visualItemRect(g.item(0,6));center=rect.center();global_point=target.mapToGlobal(center)
        for kind,dy,button,buttons in [(QEvent.Type.MouseButtonPress,0,Qt.MouseButton.LeftButton,Qt.MouseButton.LeftButton),(QEvent.Type.MouseMove,-9,Qt.MouseButton.NoButton,Qt.MouseButton.LeftButton),(QEvent.Type.MouseButtonRelease,-9,Qt.MouseButton.LeftButton,Qt.MouseButton.NoButton)]:
            event=QMouseEvent(kind,QPointF(center.x(),center.y()+dy),QPointF(global_point.x(),global_point.y()+dy),button,buttons,Qt.KeyboardModifier.NoModifier)
            self.application.sendEvent(target,event)
        self.assertEqual(w.session.get(PART_BY_KEY['volume']),103);self.assertEqual(self.packets()[-1].data,bytes([103]))

    def test_keyboard_reaches_snare_and_releases_the_held_note_on_octave_change(self):
        w=self.w;w.select_part(9);w.octave.setValue(1);key=w.keyboard_keys[2]
        self.assertEqual(key.property('note'),38);w.press_key(key)
        self.assertEqual(w.engine.sent[-1][1][:2],bytes([0x99,38]))
        w.octave.setValue(0);self.assertEqual(w.engine.sent[-1][1][:2],bytes([0x89,38]))

    def test_layer_changes_apply_immediately(self):
        w=self.w;w.navigate(5);layers=w.pages[5]
        layers.preset('split')
        self.assertEqual(w.session.get(PART_BY_KEY['receive'],1),0)
        self.assertEqual(w.session.get(PART_BY_KEY['note_high'],0),59)
        w.engine.sent.clear();layers.grid.item(0,3).setText('82')
        self.assertEqual(w.session.get(PART_BY_KEY['volume']),82);self.assertEqual(self.packets()[-1].data,b'R')

    def test_cc_updates_all_parts_on_the_same_channel_without_duplicate_sysex(self):
        w=self.w;w.navigate(5);w.pages[5].preset('layer');w.engine.sent.clear()
        w.send_cc(7,80)
        self.assertEqual(w.engine.sent,[(0,bytes([0xb0,7,80]))])
        self.assertEqual(w.session.get(PART_BY_KEY['volume'],0),80);self.assertEqual(w.session.get(PART_BY_KEY['volume'],1),80)

    def test_part_editor_mode_selection_also_changes_the_bank(self):
        w=self.w;w.navigate(2);mode=w.pages[2].form.controls['mode'];mode.setCurrentIndex(mode.findData(2))
        self.assertEqual(w.session.get(PART_BY_KEY['bank_msb']),127)
        self.assertEqual(w.session.get(PART_BY_KEY['mode']),2)

if __name__=='__main__':unittest.main()
