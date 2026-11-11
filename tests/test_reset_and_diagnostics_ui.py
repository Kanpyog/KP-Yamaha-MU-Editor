"""Reset confirmation, saved snapshot and diagnostic preferences, without hardware."""
import json,tempfile,time,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QMessageBox
from kp_mu_editor.app import MainWindow
from kp_mu_editor.session import Session
from kp_mu_editor.schema import PART_BY_KEY
from kp_mu_editor.protocol import change


class ResetUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        (self.root/'preferences.json').write_text('{"custom":{"keep":true}}')
        self.w=MainWindow(self.root,offline=True);self.w.engine.close()
        self.w.engine.connected=True;self.w.detected_name='MU500';self.w.refresh()

    def tearDown(self):
        self.w.close();self.w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.app.processEvents();self.temp.cleanup()

    def test_reset_requires_confirmation_and_cancel_sends_nothing(self):
        with patch('kp_mu_editor.app.QMessageBox.question',return_value=QMessageBox.StandardButton.No) as ask,patch.object(self.w.engine,'reset_xg') as reset:
            self.w.reset_button.click();ask.assert_called_once();reset.assert_not_called()
            self.assertEqual(ask.call_args.args[-1],QMessageBox.StandardButton.No)
        self.assertFalse(self.w._reset_pending);self.assertFalse((self.root/'backups').exists())

    def test_snapshot_precedes_reset_then_session_rebuilt_from_received_values(self):
        w=self.w;w.on_received(change((8,0,11),[81]));w.muted.add(0)
        def reset(blocks):
            saved=list((self.root/'backups').glob('before_xg_reset_*.mu.json'))
            self.assertEqual(len(saved),1);self.assertEqual(Session.load(saved[0]).memory,w.session.memory)
            self.assertEqual(w.session.get(PART_BY_KEY['volume'],0),81)
            self.assertGreater(len(blocks),1000);self.assertTrue(w._reset_pending)
        with patch('kp_mu_editor.app.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes),patch.object(w.engine,'reset_xg',side_effect=reset) as call:
            w.xg_reset();call.assert_called_once()
        self.assertFalse(w.model.isEnabled());self.assertTrue(w.panic_button.isEnabled())
        self.assertTrue(all(not a.isEnabled() for a in w.reset_sensitive_actions))
        w.refresh();self.assertFalse(w.voice_map.isEnabled())
        w.on_xg_reset_applied();self.assertEqual(w.session.memory,{});self.assertFalse(w.muted)
        w.on_received(change((8,0,11),[100]));w.on_finished('XG初期化後取得',{'count':1,'expected':1,'elapsed_s':.1})
        self.assertEqual(w.session.get(PART_BY_KEY['volume'],0),100);self.assertFalse(w._reset_pending)
        self.assertTrue(w.model.isEnabled());self.assertTrue(all(a.isEnabled() for a in w.reset_sensitive_actions))

    def test_backup_failure_stops_reset(self):
        with patch('kp_mu_editor.app.QMessageBox.question',return_value=QMessageBox.StandardButton.Yes),patch.object(self.w.session,'save',side_effect=OSError('disk full')),patch.object(self.w.engine,'reset_xg') as call:
            self.w.xg_reset();call.assert_not_called()
        self.assertFalse(self.w._reset_pending);self.assertIn('退避できない',self.w.statusBar().currentMessage())

    def test_system_on_disabled_blocks_reset(self):
        self.w.on_received(change((0,0,3),[0],model=0x49))
        with patch('kp_mu_editor.app.QMessageBox.question') as ask,patch.object(self.w.engine,'reset_xg') as reset:
            self.w.xg_reset();ask.assert_not_called();reset.assert_not_called()
        self.assertIn('System On',self.w.statusBar().currentMessage())

    def test_debug_mode_persists_and_keeps_other_preferences_after_restart(self):
        self.w.settings.diagnostic_mode.setCurrentIndex(1)
        self.assertTrue(self.w.diagnostics.debug)
        prefs=json.loads((self.root/'preferences.json').read_text(encoding='utf-8'))
        self.assertEqual(prefs['diagnostic_mode'],'debug');self.assertEqual(prefs['custom'],{'keep':True})
        other=MainWindow(self.root,offline=True)
        try:
            self.assertTrue(other.diagnostics.debug);self.assertEqual(other.settings.diagnostic_mode.currentIndex(),1)
        finally:other.close();other.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_unrelated_error_does_not_unlock_reset_but_engine_failure_does(self):
        self.w.set_reset_busy(True);self.w.error('ZIP export error');self.assertTrue(self.w._reset_pending)
        self.w.on_engine_error('MIDI disconnected');self.assertFalse(self.w._reset_pending)

    def test_zip_export_uses_ui_button_and_completes_without_blocking_or_midi(self):
        path=self.root/'ui_bundle.zip';self.w.diagnostics.record('ui_export_marker')
        with patch('kp_mu_editor.app.QFileDialog.getSaveFileName',return_value=(str(path),'')):
            self.w.settings.export_diagnostics_button.click()
        self.assertFalse(self.w.settings.export_diagnostics_button.isEnabled())
        deadline=time.monotonic()+5
        while not self.w.settings.export_diagnostics_button.isEnabled() and time.monotonic()<deadline:
            self.app.processEvents();time.sleep(.005)
        self.assertTrue(self.w.settings.export_diagnostics_button.isEnabled())
        with zipfile.ZipFile(path) as bundle:
            self.assertIn('manifest.json',bundle.namelist())
            self.assertIn('ui_export_marker',b''.join(bundle.read(n) for n in bundle.namelist()).decode('utf-8'))
        self.assertTrue(self.w.engine.commands.empty())


if __name__=='__main__':unittest.main()
