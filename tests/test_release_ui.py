"""Release behavior: persistent presentation settings and unchanged MIDI state."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QLabel,QPushButton,QCheckBox
from kp_mu_editor.app import MainWindow
from kp_mu_editor.i18n import tr
from kp_mu_editor.protocol import change,parse
from kp_mu_editor.schema import PART_BY_KEY
from kp_mu_editor.voice_catalog import display_voice_name
from kp_mu_editor import __version__


class ReleaseUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.w=MainWindow(self.root,offline=True);self.w.engine.close()

    def tearDown(self):
        self.w.close();self.w.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.app.processEvents();self.temp.cleanup()

    def english(self):self.w.settings.language.setCurrentIndex(0);self.app.processEvents()

    def test_first_launch_is_dark_and_user_light_choice_survives_restart(self):
        self.assertEqual(self.w.theme,'dark');self.w.toggle_theme()
        other=MainWindow(self.root,offline=True)
        try:self.assertEqual(other.theme,'light')
        finally:other.close();other.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def test_language_changes_live_and_persists_without_losing_preferences(self):
        self.w.preferences['custom']={'keep':True};self.english()
        self.assertEqual([a.text() for a in self.w.menuBar().actions()],['File','Edit','Help'])
        self.assertEqual(self.w.nav.item(0).text(),'01  Mixer')
        other=MainWindow(self.root,offline=True)
        try:
            self.assertEqual(other.language,'en');self.assertEqual(other.preferences['custom'],{'keep':True})
            self.assertEqual(other.nav.item(1).text(),'02  Voices')
        finally:other.close();other.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.w.settings.language.setCurrentIndex(1)
        self.assertEqual(self.w.nav.item(0).text(),'01  ミキサー')

    def test_language_switch_preserves_values_selection_notes_and_midi_queue(self):
        w=self.w;w.engine.connected=True;w.detected_name='MU500'
        w.on_received(change((8,0,11),[83]));w.keyboard_keys[0].setProperty('held_note',60)
        w.navigate(2);form=w.pages[2].form;form.controls['attack'].setValue(13)
        state=copy.deepcopy(w.session.snapshot());queued=w.engine.commands.qsize();selected=w.selected_part
        self.english();w.settings.language.setCurrentIndex(1)
        self.assertEqual(w.session.snapshot(),state);self.assertEqual(w.engine.commands.qsize(),queued)
        self.assertEqual(w.selected_part,selected);self.assertEqual(w.keyboard_keys[0].property('held_note'),60)
        self.assertEqual(form.controls['attack'].value(),13)

    def test_numbered_voice_labels_and_requested_examples(self):
        self.assertEqual(display_voice_name('GrandP #',0,0,0),'1-0-0 GrandP#')
        self.assertEqual(display_voice_name('TremStr #',44,0,126),'45-0-126 TremStr#')
        self.assertEqual(display_voice_name('Dry Kit',2,127,0),'3-127-0 Dry Kit')
        self.assertEqual(self.w.voice_name(0),'1-0-0 GrandP#')
        self.w.refresh();self.assertEqual(self.w.part_voice.text(),self.w.voice_name(0))
        self.assertEqual(self.w.pages[0].grid.item(0,1).text(),self.w.voice_name(0))

    def test_voice_columns_filter_and_double_click_keep_correct_bank_messages(self):
        w=self.w;self.english();w.navigate(1);page=w.pages[1]
        headers=[page.grid.horizontalHeaderItem(i).text() for i in range(7)]
        self.assertEqual(headers,['Favorite','Program','MSB','LSB','Voice name','Category','Elements'])
        row=next(i for i,v in enumerate(page.rows) if v['name']=='ChorBell')
        v=page.rows[row];self.assertEqual([page.grid.item(row,i).text() for i in range(1,4)],['99','0','42'])
        self.assertEqual(page.grid.item(row,4).text(),'99-0-42 ChorBell')
        page.search.setText('99-0-42');self.assertFalse(page.grid.isRowHidden(row))
        w.engine.connected=True;w.detected_name='MU500';page.grid.setCurrentCell(row,4);page.grid.cellDoubleClicked.emit(row,4)
        command=w.engine.commands.get_nowait();self.assertEqual(command[0],'send')
        packets=[parse(raw) for port,raw in command[1][0]]
        self.assertEqual([p.address[2] for p in packets],[1,2,3]);self.assertEqual([p.data[0] for p in packets],[0,42,98])

    def test_english_drum_group_filter_uses_canonical_group_values(self):
        self.english();w=self.w;w.navigate(3);drum=w.pages[3];drum.group.setCurrentIndex(4)
        self.assertEqual(drum.group.currentText(),'Filter / EG')
        for i,param in enumerate(drum.params,2):self.assertEqual(drum.grid.isColumnHidden(i),param.group!='フィルター・EG')
        w.settings.language.setCurrentIndex(1)
        for i,param in enumerate(drum.params,2):self.assertEqual(drum.grid.isColumnHidden(i),param.group!='フィルター・EG')

    def test_help_has_requested_scope_and_about_has_author_and_licenses(self):
        with patch('kp_mu_editor.app.QMessageBox.information') as info:
            self.w.help();text=info.call_args.args[2]
            self.assertIn('本ソフトはMU500での動作確認、開発を行っています。',text)
            self.assertIn('サンプラーの編集・波形転送は非対応です。',text)
            self.assertNotIn('Sustain',text);self.assertNotIn('環境設定',text);self.assertNotIn('PySide',text)
            self.w.about();text=info.call_args.args[2]
            for token in (__version__,'干瓢碁 2026','GPL-3.0-or-later','mido: MIT','Python: PSF','PySide6','QXGEdit'):
                self.assertIn(token,text)
            self.english();self.w.help();text=info.call_args.args[2]
            self.assertIn('developed and tested with the MU500',text);self.assertNotIn('本ソフト',text)

    def test_user_text_and_saved_filenames_are_not_translated(self):
        w=self.w;folder=self.root/'sessions';folder.mkdir();path=folder/'音色の保存.mu.json'
        w.session.save(path);w.navigate(6);page=w.pages[6];page.name.setText('自分の音色 保存')
        self.english()
        self.assertEqual(page.name.text(),'自分の音色 保存');self.assertEqual(page.files.item(0,0).text(),path.name)

    def test_english_error_and_dynamic_labels_translate(self):
        self.english();self.w.error('バルクデータの長さまたはチェックサムが一致しません。')
        self.assertIn('Bulk data length or checksum does not match.',self.w.statusBar().currentMessage())
        self.w.detected_name='MU500';self.w.refresh();self.assertEqual(self.w.detected_label.text(),'Detected device: MU500')
        self.assertEqual(tr('XG RESETと再取得が終わるまでお待ちください。'),'Please wait for XG reset and the settings read to finish.')


if __name__=='__main__':unittest.main()
