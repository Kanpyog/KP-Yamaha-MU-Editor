"""Presentation changes must not edit or transmit musical settings."""
import copy,json,tempfile,unittest
from pathlib import Path
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import QApplication
from kp_mu_editor.app import MainWindow,configure_application
from kp_mu_editor.protocol import change,cc
from kp_mu_editor.theme import LIGHT,DARK


class RecordingTransport:
    def __init__(self):self.sent=[];self.fail=False
    def send(self,raw,port=0):
        if self.fail:raise RuntimeError('not sent')
        self.sent.append((port,raw))


class PresentationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        (self.folder/'preferences.json').write_text(json.dumps({'theme':'light','favorites':['0:0:0'],'learn_map':{'7':'volume'},'custom':{'keep':True}}),encoding='utf-8')
        configure_application(self.app)
        self.w=MainWindow(self.folder);self.w.engine.close()
        self.transport=RecordingTransport();self.w.engine.transport=self.transport;self.w.engine.connected=True
        self.w.detected_name='MU500';self.w.show();self.app.processEvents()

    def tearDown(self):
        self.w.close();self.w.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);self.app.processEvents()
        self.temp.cleanup()

    def test_theme_round_trip_preserves_notes_settings_and_midi(self):
        w=self.w;w.on_received(change((8,0,11),[89]));w.refresh();w.navigate(3);w.navigate(0)
        key=w.keyboard_keys[0];key.setProperty('held_note',60)
        before=copy.deepcopy(w.session.memory);queued=w.engine.commands.qsize();changed=[]
        for grid in (w.pages[0].grid,w.pages[3].grid):grid.cellChanged.connect(lambda *args:changed.append(args))
        for expected in ('dark','light'):
            w.theme_button.click();self.app.processEvents()
            self.assertEqual(w.theme,expected);self.assertEqual(w.session.memory,before)
            self.assertEqual(key.property('held_note'),60)
            self.assertEqual(w.engine.commands.qsize(),queued);self.assertEqual(self.transport.sent,[])
            self.assertEqual(changed,[])

    def test_theme_restores_after_restart_and_keeps_existing_preferences(self):
        self.w.theme_button.click()
        preferences=json.loads((self.folder/'preferences.json').read_text(encoding='utf-8'))
        self.assertEqual(preferences['theme'],'dark');self.assertEqual(preferences['custom'],{'keep':True})
        self.assertEqual(preferences['favorites'],['0:0:0']);self.assertEqual(preferences['learn_map'],{'7':'volume'})
        other=MainWindow(self.folder)
        try:
            self.assertEqual(other.theme,'dark');self.assertEqual(other.theme_button.text(),'ライトモード')
            self.assertEqual(other.palette().color(QPalette.ColorRole.Window).name(),DARK['window'])
        finally:
            other.close();other.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_modified_value_and_graph_follow_theme_without_editing(self):
        w=self.w;w.on_received(change((8,0,0x23),[76]));w.navigate(2)
        form=w.pages[2].form;form.setCurrentIndex(next(i for i in range(form.count()) if form.tabText(i)=='割当'))
        control=form.controls['bend_pitch'];before=w.pages[2].graph.values
        for palette in (DARK,LIGHT):
            w.theme_button.click();self.app.processEvents()
            self.assertEqual(control.lineEdit().palette().color(QPalette.ColorRole.Text).name(),palette['modified'])
            self.assertTrue(control.lineEdit().font().bold());self.assertEqual(control.value(),12)
            self.assertEqual(w.pages[2].graph.values,before)

    def test_midi_log_button_opens_correct_tab_and_preserves_log(self):
        w=self.w;w.log('retain this entry');w.settings.tabs.setCurrentIndex(0)
        w.midi_log_button.click();self.app.processEvents()
        self.assertTrue(w.preferences_dialog.isVisible())
        self.assertIs(w.settings.tabs.currentWidget(),w.settings.log_page)
        self.assertIn('retain this entry',w.settings.monitor.toPlainText())
        self.assertEqual(self.transport.sent,[])

    def test_sysex_is_shown_after_actual_send_with_real_device_number(self):
        w=self.w;self.assertFalse(w.copy_sysex_button.isEnabled())
        w.engine.device=5;w.engine._send(change((0,0,4),[100]))
        expected='F0 43 15 4C 00 00 04 64 F7'
        self.assertEqual(w.sysex_display.text(),expected)
        self.assertEqual(self.transport.sent[-1][1].hex(' ').upper(),expected)
        w.copy_sysex_button.click();self.assertEqual(self.app.clipboard().text(),expected)

    def test_long_sysex_copy_has_no_truncation_or_log_prefix(self):
        raw=b'\xf0\x7d'+bytes([64])*12000+b'\xf7';self.w.engine._send(raw)
        expected=raw.hex(' ').upper();self.assertGreater(len(expected),32767)
        self.assertEqual(self.w.sysex_display.text(),expected)
        self.w.copy_sysex_button.click();self.assertEqual(self.app.clipboard().text(),expected)
        self.assertNotIn('TX',expected);self.assertNotIn('\n',expected)

    def test_failed_send_short_messages_and_receive_do_not_replace_last_sysex(self):
        w=self.w;w.engine._send(change((0,0,4),[100]));before=w.last_sysex
        w.engine._send(cc(0,7,90));w.on_received(change((8,0,11),[90]))
        self.assertEqual(w.last_sysex,before)
        self.transport.fail=True
        with self.assertRaisesRegex(RuntimeError,'not sent'):w.engine._send(change((0,0,4),[99]))
        self.assertEqual(w.last_sysex,before)


if __name__=='__main__':unittest.main()
