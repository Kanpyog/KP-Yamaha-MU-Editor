"""Main window arrangement; preferences stay outside the editing navigation."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QComboBox,QListWidget,QStackedWidget,
 QSplitter,QCheckBox,QPushButton,QProgressBar,QDialog,QDialogButtonBox,QLineEdit,QSizePolicy)
from .schema import PROFILES
from .widgets import button,label,InlineParams,DragSpinBox
from .pages import Mixer,Voices,Parts,Drums,Effects,Layers,Library,Settings
from . import __version__
from .theme import style_widget
from .i18n import QAction,QMenu,QComboBox,QListWidget,QCheckBox,QPushButton,QDialog,QLineEdit

def build_window(a):
    a.reset_sensitive_actions=[]
    filemenu=QMenu('ファイル',a);a.menuBar().addMenu(filemenu)
    for text,shortcut,fn in [('新しいセット','Ctrl+N',a.new_session),('開く','Ctrl+O',a.load_session),
                             ('保存（JSON / SMF 1）','Ctrl+S',a.save_session),('SMF Format 1を書き出す','',a.save_midi),('終了','Ctrl+Q',a.close)]:
        action=QAction(text,a)
        if shortcut:action.setShortcut(shortcut)
        action.triggered.connect(fn);filemenu.addAction(action)
        if text!='終了':a.reset_sensitive_actions.append(action)
    editmenu=QMenu('編集',a);a.menuBar().addMenu(editmenu)
    for text,shortcut,fn in [('元に戻す','Ctrl+Z',a.undo),('やり直す','Ctrl+Y',lambda:a.undo(True)),
                             ('コピー','Ctrl+Shift+C',a.copy_part),('音作りを貼付','Ctrl+Shift+V',a.paste_part),('環境設定','Ctrl+,',a.open_preferences)]:
        action=QAction(text,a);action.setShortcut(shortcut);action.triggered.connect(fn);editmenu.addAction(action)
        if text!='環境設定':a.reset_sensitive_actions.append(action)
    helpmenu=QMenu('ヘルプ',a);a.menuBar().addMenu(helpmenu)
    for text,callback in [('使い方',a.help),('バージョン',a.about)]:
        action=QAction(text,a);action.triggered.connect(callback);helpmenu.addAction(action)
    central=QWidget();layout=QVBoxLayout(central);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0);a.setCentralWidget(central)
    header=QWidget();header.setObjectName('header')
    hl=QHBoxLayout(header);hl.setContentsMargins(16,10,16,10);hl.setSpacing(9)
    hl.addWidget(label('KP / YAMAHA MU','font-size:18px;font-weight:800;color:@title@;'))
    a.model=QComboBox();a.model.addItems(PROFILES);a.model.setCurrentText('MU500');a.model.setMaximumWidth(135);a.model.currentTextChanged.connect(a.model_changed);hl.addWidget(a.model)
    a.mode=QComboBox();a.mode.setMaximumWidth(100);a.mode.currentTextChanged.connect(a.mode_changed);hl.addWidget(a.mode)
    a.voice_map=QComboBox();a.voice_map.addItem('Native',1);a.voice_map.addItem('Basic',0)
    a.voice_map.setToolTip('MU100 Native / MU Basic 音色マップ');a.voice_map.currentIndexChanged.connect(a.voice_map_changed);hl.addWidget(a.voice_map)
    a.detected_label=label('検出した本体：未検出','font-size:12px;color:@muted@;');a.detected_label.setWordWrap(False);hl.addWidget(a.detected_label)
    hl.addStretch()
    a.theme_button=button('',a.toggle_theme);a.theme_button.setCheckable(True);a.update_theme_button();hl.addWidget(a.theme_button)
    a.midi_log_button=button('MIDIログ',a.open_midi_log);a.midi_log_button.setToolTip('環境設定のMIDIログを直接開きます。');hl.addWidget(a.midi_log_button)
    layout.addWidget(header)

    selected=QWidget();sl=QHBoxLayout(selected);sl.setContentsMargins(18,9,18,9);sl.setSpacing(12)
    sl.addWidget(label('選択パート','font-size:14px;font-weight:600;'))
    a.part=QComboBox();a.part.setStyleSheet('font-size:26px;font-weight:700;');a.part.setMinimumWidth(115);a.part.currentIndexChanged.connect(a.select_part);sl.addWidget(a.part)
    a.part_voice=label('','font-size:25px;font-weight:700;color:@title@;');a.part_voice.setWordWrap(False);a.part_voice.setMinimumWidth(0);a.part_voice.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Preferred);sl.addWidget(a.part_voice,1)
    a.connect_button=button('接続',a.connect_dialog);sl.addWidget(a.connect_button)
    sl.addWidget(button('本体から取得',a.read_from_device));sl.addWidget(button('本体へ送信',a.send_to_device,True));sl.addWidget(button('保存',a.save_session))
    a.panic_button=button('ALL NOTES OFF',a.all_notes_off)
    style_widget(a.panic_button,'QPushButton {color:@danger@;border:1px solid @danger_border@;background:@danger_bg@;font-weight:700;padding:10px;} QPushButton:hover {border-color:@danger@;}')
    a.panic_button.setToolTip('全出力・全チャンネルへAll Notes Offを送信し、保持ペダルと発音を解除します。再生も停止します。')
    sl.addWidget(a.panic_button)
    a.reset_button=button('XG RESET',a.xg_reset)
    a.reset_button.setToolTip('確認後、本体をXG初期状態に戻し、設定を再取得します。')
    sl.addWidget(a.reset_button);layout.addWidget(selected)
    monitor_row=QWidget();ml=QHBoxLayout(monitor_row);ml.setContentsMargins(18,0,18,8);ml.setSpacing(18)
    a.sysex_panel=QWidget();a.sysex_panel.setObjectName('sysexPanel')
    sysex_layout=QVBoxLayout(a.sysex_panel);sysex_layout.setContentsMargins(12,6,10,6);sysex_layout.setSpacing(2)
    sysex_layout.addWidget(label('最後に送信したSysEx','font-size:11px;'))
    sysex_row=QHBoxLayout();sysex_row.setContentsMargins(0,0,0,0);sysex_row.setSpacing(8)
    a.sysex_display=QLineEdit();a.sysex_display.setObjectName('lastSysex');a.sysex_display.setReadOnly(True)
    a.sysex_display.setMaxLength(262144*3);a.sysex_display.setMinimumWidth(100);a.sysex_display.setPlaceholderText('未送信')
    sysex_row.addWidget(a.sysex_display,1)
    a.copy_sysex_button=button('コピー',a.copy_last_sysex);a.copy_sysex_button.setEnabled(False)
    a.copy_sysex_button.setToolTip('F0～F7の16進データだけをコピーします。');sysex_row.addWidget(a.copy_sysex_button)
    sysex_layout.addLayout(sysex_row);ml.addWidget(a.sysex_panel,1)
    a.master=InlineParams();a.master.changed.connect(lambda p,v:a.edit(p,v,0));ml.addWidget(a.master)
    layout.addWidget(monitor_row)
    state=QWidget();state_row=QHBoxLayout(state);state_row.setContentsMargins(18,0,18,6)
    a.connection_label=label('未接続','font-size:11px;color:@muted@;');a.connection_label.setWordWrap(False);state_row.addWidget(a.connection_label)
    state_row.addStretch();a.validation=label('MU500：実機検証基準','font-size:11px;color:@muted@;');a.validation.setWordWrap(False);state_row.addWidget(a.validation);layout.addWidget(state)

    body=QSplitter();navpanel=QWidget();navpanel.setObjectName('navigationPanel');nl=QVBoxLayout(navpanel);nl.setContentsMargins(0,0,0,12)
    a.nav=QListWidget();a.nav.setObjectName('navigation');a.nav.addItems(['01  ミキサー','02  音色','03  パート編集','04  ドラム','05  エフェクト','06  レイヤー','07  ライブラリー'])
    a.nav.setCurrentRow(0);nl.addWidget(a.nav);nl.addWidget(label(f'   MU EDITOR\n   {__version__}  ·  Windows','color:@nav_muted@;font-size:11px;'))
    navpanel.setMinimumWidth(175);navpanel.setMaximumWidth(205);body.addWidget(navpanel)
    a.stack=QStackedWidget();a.pages=[Mixer(a),Voices(a),Parts(a),Drums(a),Effects(a),Layers(a),Library(a)]
    for page in a.pages:a.stack.addWidget(page)
    body.addWidget(a.stack);body.setStretchFactor(1,1);a.nav.currentRowChanged.connect(a.navigate);layout.addWidget(body,1)

    footer=QWidget();footer.setObjectName('footer');fl=QVBoxLayout(footer);fl.setContentsMargins(16,7,16,7)
    row=QHBoxLayout();row.setSpacing(5);row.addWidget(label('試聴'))
    a.octave=DragSpinBox();a.octave.setRange(-2,7);a.octave.setValue(2);a.octave.setPrefix('Oct ');a.octave.setFixedWidth(84);a.octave.valueChanged.connect(a.update_keyboard);row.addWidget(a.octave)
    a.velocity=DragSpinBox();a.velocity.setRange(1,127);a.velocity.setValue(90);a.velocity.setPrefix('Vel ');a.velocity.setFixedWidth(84);row.addWidget(a.velocity)
    a.keyboard_keys=[]
    for offset in range(25):
        key=QPushButton();key.setFixedWidth(28);key.setProperty('offset',offset)
        key.pressed.connect(lambda b=key:a.press_key(b));key.released.connect(lambda b=key:a.release_key(b))
        a.keyboard_keys.append(key);row.addWidget(key)
    row.addStretch();fl.addLayout(row);a.update_keyboard()
    row=QHBoxLayout();row.addWidget(button('MIDIファイル',a.open_midi));a.midi_label=label('ファイル未選択');row.addWidget(a.midi_label,1)
    a.keep_setup=QCheckBox('曲の音色・設定を反映');row.addWidget(a.keep_setup)
    a.loop=QCheckBox('ループ');row.addWidget(a.loop);row.addWidget(button('再生',a.play));row.addWidget(button('停止',a.engine.stop));fl.addLayout(row);layout.addWidget(footer)
    a.progress=QProgressBar();a.progress.setMaximumWidth(210);a.progress.setVisible(False);a.statusBar().addPermanentWidget(a.progress)

    a.preferences_dialog=QDialog(a);a.preferences_dialog.setWindowTitle('環境設定');a.preferences_dialog.resize(1020,760)
    preferences_layout=QVBoxLayout(a.preferences_dialog);preferences_layout.setContentsMargins(0,0,0,10)
    a.settings=Settings(a);preferences_layout.addWidget(a.settings)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Close);buttons.rejected.connect(a.preferences_dialog.hide);preferences_layout.addWidget(buttons)
    a.status('接続中はパラメーター変更を即時送信します。数値は上下ドラッグで変更できます。')
