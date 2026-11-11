from __future__ import annotations
import argparse,json,os,sys,time,traceback,threading
from pathlib import Path
from datetime import datetime
from PySide6.QtCore import Qt,QTimer,Signal
from PySide6.QtGui import QAction,QKeySequence,QFont,QColor,QPalette
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,QLabel,
 QComboBox,QListWidget,QStackedWidget,QSplitter,QCheckBox,QSpinBox,QProgressBar,QMessageBox,
 QFileDialog,QDialog,QDialogButtonBox,QFormLayout,QGroupBox,QScrollArea,QLineEdit,QPushButton)
from . import __version__
from .session import Session,atomic_write,read_bounded_file
from .schema import PROFILES,PART_BY_KEY,part_params,read_blocks,CC_PART,Param
from .protocol import change,cc,parse,encode,TG300B_SYSTEM_ON
from .catalog import Catalog
from .engine import Engine,load_midi,write_midi
from .widgets import button,label,GESTURES,value_style,DragSpinBox as QSpinBox
from .pages import Mixer,Voices,Parts,Drums,Effects,Layers,Library,Settings
from .winmm import ports
from .dependencies import midi_library
from .diagnostics import Diagnostics
from .i18n import (tr,set_language,QAction,QLabel,QComboBox,QListWidget,QCheckBox,
 QGroupBox,QLineEdit,QPushButton,QDialog,QFormLayout,QMessageBox,QFileDialog)
from .voice_catalog import display_voice_name

from .theme import STYLE,configure_application,style_widget


class MainWindow(QMainWindow):
    diagnostic_exported=Signal(str,str)
    def __init__(self,data_dir,offline=False):
        super().__init__();self.data_dir=Path(data_dir);self.data_dir.mkdir(parents=True,exist_ok=True)
        self.session=Session();self.catalog=Catalog();self.selected_part=0;self.unsaved=False
        self.muted=set();self.soloed=set();self.solo_original={};self.part_clipboard=None;self.cell_clipboard=[]
        self.detected_name='';self.a_snapshot=None;self.refresh_pending=False;self.midi_file=None
        self._master_model=None;self._gesture_active=False;self._gesture_checkpoint=False
        self.favorites=set();self.learn_map={};self.preferences={};self.load_preferences()
        self.language=self.preferences.get('language','ja')
        if self.language not in ('ja','en'):self.language='ja'
        set_language(self.language,QApplication.instance())
        self._reset_pending=False;self._last_tick=None;self._last_heartbeat=0
        self.diagnostics=Diagnostics(self.data_dir,self.preferences.get('diagnostic_mode','normal'))
        self.diagnostic_exported.connect(self.on_diagnostic_exported)
        self.theme=self.preferences.get('theme','dark')
        if self.theme not in ('light','dark'):self.theme='dark'
        self.last_sysex=''
        configure_application(QApplication.instance(),self.theme)
        self.engine=Engine(self.data_dir,diagnostics=self.diagnostics);self.engine.received.connect(self.on_received)
        self.engine.short_received.connect(self.on_short);self.engine.progress.connect(self.on_progress)
        self.engine.finished.connect(self.on_finished);self.engine.failed.connect(self.on_engine_error)
        self.engine.connection.connect(self.on_connection);self.engine.activity.connect(self.log)
        self.engine.sysex_sent.connect(self.on_sysex_sent)
        self.engine.reset_applied.connect(self.on_xg_reset_applied)
        self.build();self.setWindowTitle(f'KP YAMAHA MU Editor {__version__}');self.resize(1480,950);self.setMinimumSize(1120,760)
        screen=QApplication.primaryScreen()
        if screen:
            available=screen.availableGeometry();self.setMinimumSize(1120,700)
            self.resize(max(1120,min(1480,available.width()-40)),max(700,min(950,available.height()-70)))
        self.timer=QTimer(self);self.timer.setInterval(40);self.timer.timeout.connect(self.tick);self.timer.start()
        self.recovery_timer=QTimer(self);self.recovery_timer.setSingleShot(True);self.recovery_timer.setInterval(1800);self.recovery_timer.timeout.connect(self.save_recovery)
        GESTURES.started.connect(self.begin_gesture);GESTURES.finished.connect(self.end_gesture)
        self.refresh()
        self.offline=offline

    def build(self):
        from .layout import build_window
        build_window(self)

    def toggle_theme(self):
        self.theme='light' if self.theme=='dark' else 'dark'
        configure_application(QApplication.instance(),self.theme)
        self.update_theme_button();self.save_preferences()

    def update_theme_button(self):
        self.theme_button.setText('ライトモード' if self.theme=='dark' else 'ダークモード')
        self.theme_button.setChecked(self.theme=='dark')
        self.theme_button.setToolTip('現在：'+('ダーク' if self.theme=='dark' else 'ライト')+' / クリックして切り替え')

    def open_midi_log(self):
        self.open_preferences();self.settings.tabs.setCurrentWidget(self.settings.log_page)

    def change_language(self,index):
        self.language='en' if index==0 else 'ja'
        set_language(self.language,QApplication.instance())
        self.save_preferences()
        self.status(getattr(self,'_status_source',''))
        self.diagnostics.record('language_changed',language=self.language)

    def on_sysex_sent(self,raw):
        if raw[:1]!=b'\xf0' or raw[-1:]!=b'\xf7':return
        self.last_sysex=raw.hex(' ').upper()
        if self.session.profile.tg300b_catalog and raw==TG300B_SYSTEM_ON and self.session.mode!='TG300B':
            self.session.mode='TG300B'
            self.mark_changed()
        elif (self.session.profile.tg300b_catalog and self.session.mode=='TG300B'
              and len(raw)==9 and raw==change((0,0,0x7e),[0],device=raw[2]&15)):
            self.session.mode='XG'
            self.mark_changed()
        self.sysex_display.setText(self.last_sysex);self.sysex_display.setCursorPosition(0)
        self.sysex_display.setToolTip(self.last_sysex)
        self.copy_sysex_button.setEnabled(True)

    def copy_last_sysex(self):
        if self.last_sysex:
            QApplication.clipboard().setText(self.last_sysex)
            self.status('最後に送信したSysExの16進データをコピーしました。')

    def part_name(self,n):
        if n<0:return 'OFF'
        return f'{chr(65+n//16)}{n%16+1:02d}'

    def voice_name(self,n):
        params={p.key:p for p in part_params(self.session.profile)}
        if 'program' not in params:return '—'
        msb=self.session.get(params['bank_msb'],n);lsb=self.session.get(params['bank_lsb'],n) if 'bank_lsb' in params else 0
        program=self.session.get(params['program'],n)
        drum=False
        if self.session.profile.tg300b_catalog and self.session.mode=='TG300B':
            drum=bool(self.session.get(params['mode'],n))
            lsb=0
            if drum:msb=0
        name=self.catalog.voice_name(self.session.profile,msb,lsb,program,
             self.session.get_bytes(0x49,(0,0,0x12),1)!=b'\x00',self.session.mode,drum=drum)
        return display_voice_name(name,program,msb,lsb)

    def status(self,text):
        self._status_source=text;self.statusBar().showMessage(tr(text),18000)
    def error(self,text):
        self.diagnostics.record('ui_error',error=str(text),page=self.stack.currentIndex() if hasattr(self,'stack') else None)
        self.status('エラー：'+str(text));self.progress.setVisible(False)
        self.log('ERROR '+str(text))

    def on_engine_error(self,text):
        if self._reset_pending:self.set_reset_busy(False)
        self.error(text)

    def log(self,text):
        self.diagnostics.record('ui_log',detail=True,text=text)
        if hasattr(self,'pages'):self.settings.monitor.appendPlainText(datetime.now().strftime('%H:%M:%S.%f')[:-3]+'  '+text)

    def navigate(self,index):
        if not 0<=index<len(self.pages):return
        self.nav.blockSignals(True);self.nav.setCurrentRow(index);self.nav.blockSignals(False)
        self.stack.setCurrentIndex(index);self.pages[index].refresh()

    def select_part(self,index):
        if index<0 or index>=self.session.profile.parts:return
        self.selected_part=index;self.part.blockSignals(True);self.part.setCurrentIndex(index);self.part.blockSignals(False);self.refresh_pending=True

    def tick(self):
        now=time.monotonic()
        if self._last_tick is not None and now-self._last_tick>.25:
            self.diagnostics.record('ui_stall',elapsed_ms=(now-self._last_tick)*1000,page=self.stack.currentIndex())
        self._last_tick=now
        if now-self._last_heartbeat>=5:
            self._last_heartbeat=now
            self.diagnostics.record('ui_heartbeat',detail=True,page=self.stack.currentIndex(),connected=self.engine.connected,playing=self.engine.playing)
            if self.preferences_dialog.isVisible():self.settings.refresh_diagnostics()
        if self.refresh_pending:self.refresh_pending=False;self.refresh()

    def refresh(self):
        p=self.session.profile
        if self.part.count()!=p.parts:
            self.part.blockSignals(True);self.part.clear();self.part.addItems([self.part_name(n) for n in range(p.parts)]);self.part.setCurrentIndex(min(self.selected_part,p.parts-1));self.part.blockSignals(False)
        self.mode.blockSignals(True)
        if [self.mode.itemText(n) for n in range(self.mode.count())]!=list(p.modes):self.mode.clear();self.mode.addItems(p.modes)
        self.mode.setCurrentText(self.session.mode);self.mode.blockSignals(False)
        self.part_voice.setText(self.voice_name(self.selected_part))
        self.part_voice.setToolTip(self.part_voice.text())
        self.detected_label.setText('検出した本体：'+(self.detected_name or '未検出'))
        mapping=self.session.get(self.voice_map_param()) if p.generation>=4 else 0
        self.voice_map.blockSignals(True);self.voice_map.setCurrentIndex(self.voice_map.findData(mapping));self.voice_map.setEnabled(not self._reset_pending and p.generation>=4 and self.session.mode in ('XG','Performance'));self.voice_map.blockSignals(False)
        value_style(self.voice_map,mapping!=1 and p.generation>=4,False)
        if self._master_model!=p.name:
            self.master.build(self.master_params());self._master_model=p.name
            for control in self.master.controls.values():control.setFixedWidth(100)
            self.master.controls['master_tune'].setFixedWidth(120)
        self.master.refresh(self.session,0)
        self.validation.setText('実機未検証・サポート外' if p.unsupported else 'MU500：実機検証基準' if p.name=='MU500' else '仕様書対応・実機未検証')
        self.reset_button.setEnabled(self.engine.connected and not p.native5 and not self._reset_pending and self.device_matches())
        self.pages[self.stack.currentIndex()].refresh()
        if self.preferences_dialog.isVisible():self.settings.refresh()
        self.setWindowTitle(f'{"● " if self.unsaved else ""}KP YAMAHA MU Editor {__version__}  ·  {p.name}')

    def mark_changed(self):
        self.unsaved=True;self.refresh_pending=True;self.recovery_timer.start()

    def edit(self,param,value,index=None,drum_set=None):
        if drum_set is None and param.key in ('bank_msb','bank_lsb','program'):
            n=self.selected_part if index is None else index
            params={p.key:p for p in part_params(self.session.profile)}
            values={key:self.session.get(params[key],n) if key in params else 0 for key in ('bank_msb','bank_lsb','program')}
            values[param.key]=value
            self.assign_voice(values['bank_msb'],values['bank_lsb'],values['program'],n);return
        if param.key=='mode' and param.model==0x4c and param.high==8 and drum_set is None:
            self.assign_part_mode(self.selected_part if index is None else index,value);return
        self.edit_many([(param,value,self.selected_part if index is None else index,drum_set)],param.label)

    def edit_many(self,changes,label_text,transmit=True,force=False):
        if self._reset_pending:return
        try:
            for param,value,index,drum_set in changes:
                if not param.minimum<=value<=param.maximum:raise ValueError(param.label+'：値が範囲外です。')
                if not param.allowed(self.session.profile):raise ValueError('機種に対応しない項目です。')
                if param.model==0x44 and param.high==2 and not 0<=index<16:raise ValueError('パートが範囲外です。')
                if drum_set is not None and (not 0<=drum_set<self.session.profile.drums or not 13<=index<=91):raise ValueError('ドラムセットまたはノートが範囲外です。')
            if not force:changes=[x for x in changes if self.session.get(x[0],x[2],x[3])!=x[1]]
            if not changes:return
            # Retain a typed initial value so Undo of the first edit can send it back.
            for param,value,index,drum_set in changes:
                addr=param.address(index) if drum_set is None else (0x30+drum_set,index,param.low)
                if self.session.get_bytes(param.model,addr,param.size) is None:
                    self.session.put(param.model,addr,encode(self.session.get(param,index,drum_set),param.size,param.nibble),'未取得 / 初期値',False)
                    self.session.fields[(param.model,*addr)]=param.size
            if not self._gesture_active or not self._gesture_checkpoint:
                self.session.checkpoint(label_text);self._gesture_checkpoint=self._gesture_active
            messages=[(0,self.session.set(param,value,index,drum_set)) for param,value,index,drum_set in changes]
            self.mark_changed()
            if transmit and self.can_send():self.send_messages(messages,label_text)
        except Exception as exc:self.error(str(exc))

    def send_messages(self,messages,label_text):
        if self._reset_pending:self.status('XG RESETと再取得が終わるまでお待ちください。');return
        if not self.engine.connected:self.status('未接続：PC上の設定を変更しました。接続すると編集した値を即時送信します。');return
        if not self.device_matches():self.error('選択機種と検出した本体が異なります。機種と接続先を確認してください。');return
        self.engine.send(messages,label_text,interval=.005)

    def channel(self,n=None):
        n=self.selected_part if n is None else n
        param=next(p for p in part_params(self.session.profile) if p.key=='receive')
        value=self.session.get(param,n)
        # Unread receive-channel defaults follow the physical part number.
        if self.session.get_bytes(param.model,param.address(n),param.size) is None:value=n
        if value>=self.session.profile.parts:raise ValueError('このパートは受信OFFです。')
        return value//16,value%16

    def note_on(self,note):
        try:
            port,ch=self.channel();self.send_messages([(port,bytes((0x90|ch,note,self.velocity.value())))],'試聴')
        except ValueError as exc:self.error(str(exc))

    def note_off(self,note):
        try:
            port,ch=self.channel();self.send_messages([(port,bytes((0x80|ch,note,0)))],'試聴停止')
        except ValueError:pass

    def audition(self,note):
        self.note_on(note);QTimer.singleShot(450,lambda:self.note_off(note))

    def send_cc(self,number,value):
        try:
            port,ch=self.channel();raw=cc(ch,number,value)
            params={p.key:p for p in part_params(self.session.profile)};key=CC_PART.get(number)
            if key in params and params[key].minimum<=value<=params[key].maximum:
                receive=params['receive']
                changes=[(params[key],value,n,None) for n in range(self.session.profile.parts) if self.session.get(receive,n)==port*16+ch]
                self.edit_many(changes,f'CC {number}',transmit=False)
            self.send_messages([(port,raw)],f'CC {number}')
            self.session.realtime[(port,ch,number)]=value
            self.refresh_pending=True
        except ValueError as exc:self.error(str(exc))

    def assign_voice(self,msb,lsb,program,index=None,*,drum=None):
        p=self.session.profile;params={x.key:x for x in part_params(p)};n=self.selected_part if index is None else index
        if not 0<=n<p.parts or any(not isinstance(value,int) or not 0<=value<=127 for value in (msb,lsb,program)):
            self.error('音色のパートまたはバンク・プログラム番号が範囲外です。');return
        changes=[]
        setup=None
        shared_parts=[]
        tg300b=p.tg300b_catalog and self.session.mode=='TG300B'
        if not p.native5:
            mode=self.session.get(params['mode'],n)
            if tg300b:
                is_kit=bool(mode) if drum is None else drum
                lsb=0
            else:
                is_kit=msb in (120,126,127) and self.session.mode in ('XG','GM','GM2')
            target_mode=(mode if mode else 1) if is_kit else 0
            if tg300b and is_kit:
                msb=0
                # MU500 maps generic DRUM to DRUM1 in TG300B.
                part_modes=[self.session.get(params['mode'],part) for part in range(p.parts)]
                occupied={2 if value==1 else value for value in part_modes}
                if mode==0:target_mode=next((value for value in range(2,p.drums+2) if value not in occupied),2)
                elif mode==1:target_mode=2
                shared_parts=[part for part,value in enumerate(part_modes)
                              if part!=n and (2 if value==1 else value)==target_mode]
                setup=target_mode-2
            if mode!=target_mode:changes.append((params['mode'],target_mode,n,None))
        tone=[(params['bank_msb'],msb,n,None)]
        if 'bank_lsb' in params:tone.append((params['bank_lsb'],lsb,n,None))
        tone.append((params['program'],program,n,None))
        known=all(self.session.get_bytes(param.model,param.address(n),param.size) is not None for param,_,_,_ in tone)
        same=not changes and all(self.session.get(param,n)==value for param,value,_,_ in tone)
        if same and known and (not tg300b or is_kit):
            self.status('この音色はすでに選択されています。');return
        if not p.native5 and is_kit and (mode>=2 or shared_parts):
            message='キットを変更すると、共有するDrum Setupの編集が初期化されます。変更しますか？'
            if shared_parts:
                message=tr('このDrum Setupを共有するパートのキットも変更され、ノート別設定が初期化されます。変更しますか？')
                message+='\n'+', '.join(self.part_name(part) for part in shared_parts)
            if QMessageBox.question(self,'ドラムキットの変更',message)!=QMessageBox.StandardButton.Yes:return
            if setup is None:setup=mode-2
        # Bank changes are completed by PROGRAM NUMBER, even when its value
        # equals the previous voice. Keep all fields for Undo and SMF export too.
        self.edit_many(changes+tone,'音色変更',force=True)
        for part in shared_parts:self.session.set(params['program'],program,part)
        if setup is not None:
            self.session.invalidate_drums(setup)
            if self.can_send():self.read_addresses([x for x in read_blocks(p) if x[1][0]==0x30+setup],'ドラム再取得')

    def copy_part(self):
        self.part_clipboard={p.key:self.session.get(p,self.selected_part) for p in part_params(self.session.profile)}
        self.status('選択パートの設定をコピーしました。')

    def paste_part(self):
        if not self.part_clipboard:self.status('先にパートをコピーしてください。');return
        exclude={'bank_msb','bank_lsb','program','receive','mode','reserve'}
        changes=[(p,self.part_clipboard[p.key],self.selected_part,None) for p in part_params(self.session.profile)
                 if p.key in self.part_clipboard and p.key not in exclude and p.minimum<=self.part_clipboard[p.key]<=p.maximum]
        self.edit_many(changes,'音作りを貼付')

    def toggle_mute(self,n,checked):
        param=next(p for p in part_params(self.session.profile) if p.key=='rcv_5')
        if checked:self.muted.add(n)
        else:self.muted.discard(n)
        self.edit(param,0 if checked else 1,n)

    def toggle_solo(self,n,checked):
        param=next(p for p in part_params(self.session.profile) if p.key=='rcv_5')
        if not self.soloed:self.solo_original={i:self.session.get(param,i) for i in range(self.session.profile.parts)}
        if checked:self.soloed.add(n)
        else:self.soloed.discard(n)
        changes=[(param,(int(i in self.soloed) if self.soloed else self.solo_original.get(i,1)),i,None) for i in range(self.session.profile.parts)]
        self.edit_many(changes,'Solo')

    def undo(self,redo=False):
        previous_memory=dict(self.session.memory);previous_fields=dict(self.session.fields)
        label_text=self.session.restore_history(redo)
        if label_text:
            self.mark_changed();self.refresh()
            self.soloed.clear()
            if self.can_send():
                if label_text in ('音色変更','エフェクト種類変更','SysExを取り込み'):
                    messages=self.session.export_messages()
                else:
                    messages=[]
                    for key,size in (previous_fields|self.session.fields).items():
                        raw=self.session.get_bytes(key[0],key[1:],size)
                        old=bytes(previous_memory.get((key[0],key[1],key[2],key[3]+i),255) for i in range(size))
                        if raw is not None and raw!=old:messages.append(change(key[1:],raw,model=key[0]))
                self.send_messages([(0,x) for x in messages],'やり直し' if redo else '元に戻す')
            self.status(('やり直し：' if redo else '元に戻す：')+label_text)

    def store_a(self):self.a_snapshot=self.session.snapshot();self.status('比較 A を記憶しました。')
    def swap_a(self):
        if self.a_snapshot is None:self.store_a();return
        previous=self.session.snapshot();self.session.checkpoint('A/B比較')
        self.session.memory,self.session.origins,self.session.dirty,self.session.blocks,self.session.fields=self.a_snapshot
        self.a_snapshot=previous;self.mark_changed();self.refresh()
        if self.can_send():self.send_messages([(0,x) for x in self.session.export_messages()],'A/B比較')

    def model_changed(self,name):
        if not name or name==self.session.profile.name:return
        if self.unsaved and QMessageBox.question(self,'機種の変更','現在のセットを閉じて機種を変更しますか？未保存の編集は自動復旧ファイルに退避します。')!=QMessageBox.StandardButton.Yes:
            self.model.blockSignals(True);self.model.setCurrentText(self.session.profile.name);self.model.blockSignals(False);return
        self.save_recovery();self.engine.submit('close')
        self.session=Session(name);self.selected_part=0;self.unsaved=False;self.muted.clear();self.soloed.clear();self.detected_name='';self.refresh()

    def mode_changed(self,mode):
        if not mode or mode==self.session.mode:return
        old=self.session.mode
        if self.engine.connected and QMessageBox.question(self,'動作モードの変更','モード切替は本体の設定を初期化する場合があります。現在のセットを保存してから切り替えてください。実行しますか？')!=QMessageBox.StandardButton.Yes:
            self.mode.blockSignals(True);self.mode.setCurrentText(old);self.mode.blockSignals(False);return
        resets={'XG':'F0 43 10 4C 00 00 7E 00 F7','GM':'F0 7E 7F 09 01 F7','GM2':'F0 7E 7F 09 03 F7','TG300B':TG300B_SYSTEM_ON.hex(),'GS':TG300B_SYSTEM_ON.hex()}
        self.session.checkpoint('モード変更');self.session.mode=mode;self.mark_changed()
        if mode in resets and self.engine.connected:self.send_messages([(0,bytes.fromhex(resets[mode]))],'モード切替');self.read_all()
        elif mode=='Performance':self.status('本体側をPerformanceモードに切り替えてください。機種固有画面から番号を呼び出せます。')

    def can_send(self):
        return self.engine.connected and self.device_matches() and not self._reset_pending

    def begin_gesture(self):
        self._gesture_active=True;self._gesture_checkpoint=False

    def end_gesture(self):
        self._gesture_active=False;self._gesture_checkpoint=False;self.refresh_pending=True

    def open_preferences(self):
        self.settings.refresh();self.preferences_dialog.show();self.preferences_dialog.raise_();self.preferences_dialog.activateWindow()

    def set_diagnostic_mode(self,index):
        self.diagnostics.set_mode('debug' if index==1 else 'normal')
        self.preferences['diagnostic_mode']=self.diagnostics.mode;self.save_preferences()
        self.settings.refresh_diagnostics()
        self.status('デバッグモード：詳細ログを自動保存します。' if self.diagnostics.debug else '通常モード：要約と異常を自動保存します。')

    def export_diagnostics(self):
        default=self.data_dir/('MU_diagnostics_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.zip')
        path,_=QFileDialog.getSaveFileName(self,'診断ログを書き出す',str(default),'診断ログ (*.zip)')
        if not path:return
        self.settings.export_diagnostics_button.setEnabled(False);self.status('診断ログをまとめています…')
        def export():
            try:self.diagnostics.export_bundle(path);message=''
            except Exception as exc:message=str(exc)
            try:self.diagnostic_exported.emit(path,message)
            except RuntimeError:pass
        threading.Thread(target=export,daemon=True,name='MU-diagnostic-export').start()

    def on_diagnostic_exported(self,path,error):
        self.settings.export_diagnostics_button.setEnabled(True)
        if error:self.error('診断ログの書き出しに失敗しました：'+error)
        else:self.status('診断ログを保存しました：'+path)

    def set_reset_busy(self,busy):
        self._reset_pending=busy
        for widget in [*self.pages,self.master,self.model,self.mode,self.voice_map,self.part]:widget.setEnabled(not busy)
        for action in self.reset_sensitive_actions:action.setEnabled(not busy)
        self.reset_button.setEnabled(not busy and self.engine.connected and not self.session.profile.native5 and self.device_matches())

    def xg_reset(self):
        if self._reset_pending:return
        if not self.engine.connected:self.status('XG RESETにはMIDI接続が必要です。');return
        if self.session.profile.native5:self.status('MU5系はXG RESETに対応していません。');return
        if not self.device_matches():self.error('選択機種と検出した本体が異なります。');return
        if self.session.get_bytes(0x49,(0,0,3),1)==b'\x00':
            self.error('本体のSystem On受信がOFFです。環境設定のシステムでONにしてから初期化してください。');return
        answer=QMessageBox.question(self,'XG RESET',
            '本体の音色・パート・エフェクトをXGの初期状態へ戻します。\n現在PCにある設定を退避してから実行し、本体から再取得します。\n未取得の本体設定は退避に含まれません。実行しますか？',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)
        if answer!=QMessageBox.StandardButton.Yes:return
        path=self.data_dir/'backups'/('before_xg_reset_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.mu.json')
        try:self.session.save(path)
        except Exception as exc:self.error('初期化前のPC設定を退避できないため停止しました：'+str(exc));return
        self.diagnostics.record('xg_reset_requested',model=self.session.profile.name,snapshot=str(path),known_bytes=len(self.session.memory))
        self.loop.setChecked(False);self.set_reset_busy(True)
        self.engine.reset_xg(read_blocks(self.session.profile));self.status('XG RESET後、本体から再取得します…')

    def on_xg_reset_applied(self):
        profile=self.session.profile.name;self.session=Session(profile);self.session.mode='XG'
        self.muted.clear();self.soloed.clear();self.solo_original.clear();self.a_snapshot=None
        for key in self.keyboard_keys:key.setProperty('held_note',None)
        self.unsaved=True;self.refresh_pending=True

    def voice_map_param(self):
        return Param('voice_map','Voice Map',0x12,'MU固有',maximum=1,default=1,high=0,model=0x49)

    def voice_map_changed(self,*_):
        if self.session.profile.generation>=4:
            self.edit(self.voice_map_param(),self.voice_map.currentData(),0)

    def master_params(self):
        old=self.session.profile.native5;model=0x44 if old else 0x4c
        return [Param('master_volume','Master Volume',3 if old else 4,default=127,high=0,model=model),
                Param('transpose','Transpose（半音）',4 if old else 6,minimum=40,maximum=88,offset=64,high=0,model=model),
                Param('master_tune','Master Tune（0.1 cent）',0,minimum=28 if old else 0,maximum=228 if old else 2047,default=128 if old else 1024,offset=128 if old else 1024,size=2 if old else 4,nibble=True,high=0,model=model)]

    def all_notes_off(self):
        self.loop.setChecked(False)
        for key in self.keyboard_keys:key.setProperty('held_note',None)
        if self.engine.connected:self.engine.stop();self.status('全チャンネルにAll Notes Offを送信しました。')
        else:self.status('All Notes Off：MIDI未接続です。')

    def press_key(self,key):
        note=key.property('note')
        if note is not None and note<=127:key.setProperty('held_note',note);self.note_on(note)

    def release_key(self,key):
        note=key.property('held_note')
        if note is not None:self.note_off(note);key.setProperty('held_note',None)

    def update_keyboard(self,*_):
        for key in getattr(self,'keyboard_keys',[]):
            self.release_key(key)
            note=(self.octave.value()+2)*12+key.property('offset')
            key.setProperty('note',note);key.setEnabled(note<=127)
            name=('C','C#','D','D#','E','F','F#','G','G#','A','A#','B')[note%12]
            key.setText(name+str(note//12-2) if note%12==0 else name)
            key.setToolTip(f'{name}{note//12-2} / MIDI Note {note}' if note<=127 else 'MIDI範囲外')
            style_widget(key,'QPushButton {padding:5px 0;background:'+('@key_dark@;color:@key_dark_text@;' if '#' in name else '@key_light@;color:@key_light_text@;')+'} QPushButton:pressed {background:@accent@;color:@accent_text@;}')

    def part_mode_param(self):
        return next((p for p in part_params(self.session.profile) if p.key=='mode'),None)

    def assign_part_mode(self,index,value):
        params={p.key:p for p in part_params(self.session.profile)}
        if 'mode' not in params:return
        tg300b=self.session.profile.tg300b_catalog and self.session.mode=='TG300B'
        if tg300b and value==1:value=2
        changes=[(params['mode'],value,index,None),(params['bank_msb'],127 if value and not tg300b else 0,index,None)]
        if 'bank_lsb' in params:changes.append((params['bank_lsb'],0,index,None))
        self.edit_many(changes,'パート / ドラム切替')
        if value>=2:
            users=[self.part_name(n) for n in range(self.session.profile.parts) if self.session.get(params['mode'],n)==value]
            self.status(f'DRUM{value-1} の共有先：'+', '.join(users)+'（キットとノート別設定を共有）')

    def insertion_part_param(self):
        return Param('insertion_part','Insertion割当',0x0c,'接続',default=127,high=3)

    def insertion_slots(self,part):
        param=self.insertion_part_param()
        return [slot for slot in range(self.session.profile.insertions) if self.session.get(param,slot)==part]

    def assign_insertion(self,part,slot):
        param=self.insertion_part_param()
        changes=[(param,127,n,None) for n in self.insertion_slots(part) if n!=slot]
        if slot is not None:
            if not 0<=slot<self.session.profile.insertions:self.error('この機種にはないEFXです。');return
            changes.append((param,part,slot,None))
        self.edit_many(changes,'インサーション割当')

    def device_matches(self):
        expected=self.session.profile.name.split(' EX')[0].replace(' V2','').upper()
        aliases={'MU5K':'MU5','MU100BS':'MU100B'}
        expected=aliases.get(expected,expected)
        return not self.detected_name or self.detected_name.strip().upper()==expected

    def connect_dialog(self):
        if self.engine.connected:
            if hasattr(self.engine,'cancel'):self.engine.cancel.set()
            self.engine.submit('close');return
        try:available=ports()
        except Exception as exc:self.error(str(exc));return
        dialog=QDialog(self);dialog.setWindowTitle('MUへのMIDI接続');dialog.resize(600,400);form=QFormLayout(dialog)
        input_box=QComboBox();input_box.addItem('入力なし（本体から取得できません）',-1)
        for entry in available['inputs']:input_box.addItem(entry['name'],entry['id'])
        preferred=next((i+1 for i,p in enumerate(available['inputs']) if 'MU' in p['name']),0);input_box.setCurrentIndex(preferred);form.addRow('本体からの入力',input_box)
        keyboard=QComboBox();keyboard.addItem('追加入力なし',-1)
        for entry in available['inputs']:keyboard.addItem(entry['name'],entry['id'])
        form.addRow('鍵盤・コントローラー入力',keyboard)
        outboxes=[];muouts=[p for p in available['outputs'] if 'MU' in p['name']]
        for port in range(4):
            combo=QComboBox();combo.addItem('未接続',-1)
            for entry in available['outputs']:combo.addItem(entry['name'],entry['id'])
            if port<len(muouts):combo.setCurrentIndex(next(i+1 for i,p in enumerate(available['outputs']) if p['id']==muouts[port]['id']))
            form.addRow(f'出力 {chr(65+port)}（Part {port*16+1}～{port*16+16}）',combo);outboxes.append(combo)
        device=QSpinBox();device.setRange(1,16);device.setValue(self.engine.device+1);form.addRow('Device Number',device)
        form.addRow(label('MU500のUSB出力1～4が音源用です。5～8はMIDI OUTへのスルー用なので、音源用として選びません。'))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel);buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);form.addRow(buttons)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            outs=[c.currentData() for c in outboxes]
            if outs[0]<0:self.error('出力 A を指定してください。');return
            used=[x for x in outs if x>=0]
            if len(used)!=len(set(used)):self.error('同じ出力をA～Dに重複して割り当てることはできません。');return
            ins=[v for v in (input_box.currentData(),keyboard.currentData()) if v>=0]
            self.engine.device=device.value()-1;self.engine.submit('open',(ins,outs))

    def on_connection(self,connected):
        self.connect_button.setText('接続解除' if connected else '接続')
        self.connection_label.setText('MIDI接続中：変更を即時送信' if connected else '未接続')
        if not connected:
            self.detected_name=''
            if self._reset_pending:self.set_reset_busy(False)
        elif not self.session.memory:self.read_all()
        self.refresh_pending=True

    def read_addresses(self,addresses,label_text,preserve_live=False):
        if self._reset_pending:self.status('XG RESETと再取得の完了を待ってください。');return
        if not self.engine.connected:self.status('本体から取得するにはMIDI接続が必要です。');return
        if self.engine.playing:self.engine.stop()
        self.engine.submit('read',(addresses,label_text));self.status(label_text+'中…')

    def read_all(self):self.read_addresses(read_blocks(self.session.profile),'全設定取得')
    def read_part(self):
        n=self.selected_part
        if self.session.profile.native5:n=next(p for p in part_params(self.session.profile) if p.key=='receive').address(n)[1]
        self.read_addresses([x for x in read_blocks(self.session.profile,False) if x[1][1]==n and x[1][0] in ((2,) if self.session.profile.native5 else (8,0x0a))],'パート取得')

    def send_all(self):
        if not self.engine.connected:self.status('本体へ送信するにはMIDI接続が必要です。');return
        if not self.device_matches():self.error('検出した本体と選択機種が異なります。機種を確認してください。');return
        if not self.session.memory:self.status('送信する設定がありません。');return
        if QMessageBox.question(self,'本体へ設定を送信','現在のセットを本体へ送信します。音色・ドラム・エフェクトが変更されます。実行しますか？')!=QMessageBox.StandardButton.Yes:return
        self.engine.submit('send_set',([(0,x) for x in self.session.export_messages()],read_blocks(self.session.profile)))

    def on_received(self,raw):
        try:
            packet=self.session.receive(raw)
            if packet and packet.model==0x4c and packet.address==(1,0,0):
                name=packet.data[:14].decode('ascii',errors='replace').strip();self.detected_name=name
                selected=self.session.profile.name.replace(' EX R1','').replace(' EX','')
                if name and not self.device_matches():
                    self.error(f'検出した本体は{name}です。選択機種{selected}を確認してください。')
            self.refresh_pending=True
        except Exception as exc:self.error(str(exc))

    def on_short(self,source,raw):
        if not raw:return
        status=raw[0]&0xf0;channel=raw[0]&15
        settings=self.settings
        if status==0xb0 and len(raw)==3:
            if settings.learn_target:
                self.learn_map[str(raw[1])]=settings.learn_target;self.status(f'CC {raw[1]} → {settings.learn_target} を割り当てました。');settings.learn_target=None;self.save_preferences()
            key=self.learn_map.get(str(raw[1]))
            if key:
                p=next((p for p in part_params(self.session.profile) if p.key==key),None)
                if p:self.edit(p,round(p.minimum+(p.maximum-p.minimum)*raw[2]/127))
        if status==0x90 and len(raw)==3 and raw[2] and self.pages[3].follow.isChecked():
            row=raw[1]-13
            if 0<=row<self.pages[3].grid.rowCount():self.pages[3].grid.setCurrentCell(row,0);self.pages[3].grid.scrollToItem(self.pages[3].grid.item(row,0))

    def on_progress(self,current,total,text):
        self.progress.setVisible(True);self.progress.setRange(0,max(1,total));self.progress.setValue(current);self.status(f'{text}  {current:,}/{total:,}')

    def on_finished(self,text,details):
        if text=='XG初期化後取得':self.set_reset_busy(False)
        self.progress.setVisible(False)
        if '取得' in text:
            self.refresh_pending=True;self.recovery_timer.start()
            missing=details.get('missing',[])
            suffix=f' / 未取得 {len(missing)}件（前回値または初期値が残ります）' if missing else ''
            if details.get('recovered'):suffix+=f' / 自動再取得 {details["recovered"]}件'
            if details.get('cancelled'):suffix+=' / 中断'
            if details.get('elapsed_s') is not None:suffix+=f' / {details["elapsed_s"]:.1f}秒'
            self.status(f'{text}：{details.get("count",0):,}ブロック取得'+suffix)
            self.log('READ SUMMARY '+json.dumps(details,ensure_ascii=False))
            if missing:self.log('NO RESPONSE '+json.dumps(missing))
        elif text=='再生完了':
            if self.loop.isChecked():self.play()
            elif self.session.profile.tg300b_catalog and self.session.mode=='TG300B' and self.keep_setup.isChecked():
                self.read_addresses([(0x4c,(8,part,0)) for part in range(self.session.profile.parts)],'パート取得')

    def open_midi(self):
        path,_=QFileDialog.getOpenFileName(self,'MIDIファイルを開く',str(self.data_dir),'MIDI (*.mid *.midi)')
        if path:self.midi_file=path;self.midi_label.setText(Path(path).name)

    def play(self):
        if self._reset_pending:self.status('XG RESETと再取得が終わるまでお待ちください。');return
        if not self.midi_file:self.open_midi()
        if not self.midi_file:return
        if not self.engine.connected:self.status('再生にはMIDI接続が必要です。');return
        started=time.perf_counter()
        try:
            schedule=load_midi(self.midi_file,self.keep_setup.isChecked(),allow_tg300b=self.session.profile.tg300b_catalog)
            self.diagnostics.record('midi_file_loaded',filename=Path(self.midi_file).name,size=Path(self.midi_file).stat().st_size,
                                    elapsed_ms=(time.perf_counter()-started)*1000,events=len(schedule),keep_setup=self.keep_setup.isChecked())
            needed={e[2] for e in schedule}
            if self.engine.transport and any(p not in self.engine.transport.outputs for p in needed):raise ValueError('曲に必要な出力ポートが未接続です。接続設定を確認してください。')
            self.engine.submit('play',schedule);self.status('MIDI再生中')
        except Exception as exc:
            self.diagnostics.record('midi_file_load_error',filename=Path(self.midi_file).name,error=str(exc),traceback=traceback.format_exc())
            self.error(str(exc))

    def save_session(self):
        default=self.data_dir/'sessions'/'MU_set.mu.json';default.parent.mkdir(exist_ok=True)
        path,kind=QFileDialog.getSaveFileName(self,'MUセットを保存',str(default),'MU Set JSON (*.mu.json);;SMF Format 1 (*.mid)')
        if not path:return
        try:
            if 'SMF' in kind or Path(path).suffix.lower() in ('.mid','.midi'):
                if not path.lower().endswith(('.mid','.midi')):path=path.removesuffix('.mu.json')+'.mid'
                write_midi(path,self.session.export_messages());self.status('SMF Format 1で設定を保存しました：'+path)
            else:self.session.save(path);self.unsaved=False;self.refresh();self.status('保存しました：'+path)
        except Exception as exc:self.error(str(exc))

    def save_midi(self,*_):
        default=self.data_dir/'sessions'/'MU_setup.mid';default.parent.mkdir(exist_ok=True)
        path,_=QFileDialog.getSaveFileName(self,'SMF Format 1で設定を保存',str(default),'SMF Format 1 (*.mid)')
        if path:
            try:write_midi(path,self.session.export_messages());self.status('SMF Format 1で設定を保存しました：'+path)
            except Exception as exc:self.error(str(exc))

    def load_session(self,path=None):
        if not isinstance(path,str):path,_=QFileDialog.getOpenFileName(self,'MUセットを開く',str(self.data_dir/'sessions'),'MU Set (*.mu.json)')
        if not path:return
        try:
            session=Session.load(path)
            if self.unsaved:self.save_recovery()
            if self.engine.connected:self.engine.submit('close')
            self.session=session;self.selected_part=0;self.unsaved=False
            self.model.blockSignals(True);self.model.setCurrentText(session.profile.name);self.model.blockSignals(False);self.refresh()
            self.status('PC上に読み込みました。本体への適用は「本体へ送信」を使います。')
        except Exception as exc:self.error(str(exc))

    def new_session(self):
        if self.unsaved:self.save_recovery()
        self.session=Session(self.session.profile.name);self.selected_part=0;self.unsaved=False;self.refresh()

    def save_recovery(self):
        if self.session.memory:
            try:self.session.save(self.data_dir/'recovery.mu.json')
            except Exception as exc:self.log('自動復旧保存エラー '+str(exc))

    def load_preferences(self):
        try:
            data = read_bounded_file(self.data_dir/'preferences.json', 1024*1024, '設定ファイルが大きすぎます。')
            obj = json.loads(data.decode('utf-8-sig'))
            if not isinstance(obj, dict):
                return
            favorites = obj.get('favorites')
            learn_map = obj.get('learn_map')
            if isinstance(favorites, list):
                self.favorites = {value for value in favorites if isinstance(value, str)}
            if isinstance(learn_map, dict):
                self.learn_map = {cc: value for cc, value in learn_map.items() if isinstance(value, str)}
            self.preferences = obj
        except (OSError, ValueError, RecursionError):
            pass

    def save_preferences(self):
        self.preferences.update({'favorites':sorted(self.favorites),'learn_map':self.learn_map,'theme':self.theme,'language':self.language})
        atomic_write(self.data_dir/'preferences.json',json.dumps(self.preferences,ensure_ascii=False,indent=2).encode('utf-8'))

    def help(self):
        QMessageBox.information(self,tr('使い方'),tr(
            '接続中のパラメーター変更は即時送信します。\n数値は上下ドラッグ、ダブルクリック、直接入力で変更できます。\n緑・太字は起動時の値との差分です。')+'\n\n'+tr(
            '本ソフトはMU500での動作確認、開発を行っています。MU1000/2000、EX、R1、プラグインボードは動作未確認です。サンプラーの編集・波形転送は非対応です。'))

    def about(self):
        QMessageBox.information(self,tr('バージョン'),
            f'KP YAMAHA MU Editor {__version__}\n干瓢碁 2026\n\n'
            'GPL-3.0-or-later\nQXGEdit-derived data: GPL-2.0-or-later (GPL v3 option)\n'
            'Python: PSF License\nPySide6 / Shiboken6 / Qt: LGPL / GPL\nmido: MIT License\n'
            'PyInstaller bootloader: GPL with bootloader exception\n\n'+tr(
            'ライセンスの全文・第三者の権利表示は、同梱のLICENSE、THIRD_PARTY_NOTICES.md、licensesフォルダーをご覧ください。'))

    def closeEvent(self,event):
        self.timer.stop();self.recovery_timer.stop();self.preferences_dialog.close()
        try:GESTURES.started.disconnect(self.begin_gesture);GESTURES.finished.disconnect(self.end_gesture)
        except RuntimeError:pass
        self.save_recovery();self.save_preferences();self.engine.close();self.diagnostics.close();event.accept()


def main():
    parser=argparse.ArgumentParser(description='KP YAMAHA MU Editor')
    parser.add_argument('--data-dir');parser.add_argument('--offline',action='store_true')
    parser.add_argument('--smoke',action='store_true');parser.add_argument('--screenshot');parser.add_argument('--load')
    args=parser.parse_args()
    root=Path(sys.executable).resolve().parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
    data_dir=Path(args.data_dir) if args.data_dir else root/'userdata'
    app=QApplication.instance() or QApplication(sys.argv[:1]);app.setApplicationName('KP YAMAHA MU Editor');app.setOrganizationName('KP Tools')
    configure_application(app)
    window=MainWindow(data_dir,args.offline)
    window.log('STARTUP Python '+sys.executable)
    if args.load:window.load_session(args.load)
    window.show()
    if args.smoke:
        def smoke():
            try:
                for i in range(7):window.navigate(i);app.processEvents()
                window.settings.refresh()
                window.navigate(0);app.processEvents()
                if args.screenshot:window.grab().save(args.screenshot)
                setup=change((0,0,4),[127]);test_midi=data_dir/'smoke_setup.mid'
                write_midi(test_midi,[setup])
                assert [item[3] for item in load_midi(test_midi)]==[setup]
                mido=midi_library();format0=mido.MidiFile(type=0,ticks_per_beat=480)
                format0.tracks.append(mido.MidiTrack([mido.Message('note_on',note=60,velocity=90,time=0),mido.Message('note_off',note=60,time=480)]))
                path0=data_dir/'smoke_format0.mid';format0.save(path0)
                assert len(load_midi(path0))==2
                original_language=window.language;before_language=window.session.snapshot();queued=window.engine.commands.qsize()
                language_views={}
                for index,lang in ((0,'en'),(1,'ja')):
                    window.settings.language.setCurrentIndex(index);window.navigate(1);app.processEvents()
                    language_views[lang]={'menus':[a.text() for a in window.menuBar().actions()],
                        'voice_columns':[window.pages[1].grid.horizontalHeaderItem(i).text() for i in range(7)],
                        'navigation':window.nav.item(0).text()}
                assert language_views['en']['menus']==['File','Edit','Help']
                assert language_views['ja']['menus']==['ファイル','編集','ヘルプ']
                assert language_views['en']['voice_columns']==['Favorite','Program','MSB','LSB','Voice name','Category','Elements']
                window.settings.language.setCurrentIndex(0 if original_language=='en' else 1);window.navigate(0);app.processEvents()
                assert window.session.snapshot()==before_language and window.engine.commands.qsize()==queued
                report={'version':__version__,'pages':7,'preferences':True,'models':len(PROFILES),'voices':len(window.catalog.data['voices']),'size':[window.width(),window.height()],
                        'python':sys.executable,'midi_roundtrip':True,'midi_formats_checked':[0,1],
                        'theme':window.theme,'language':window.language,'voice_label':window.voice_name(0),'language_views':language_views,
                        'language_switch_preserves_session_and_midi':True}
                atomic_write(data_dir/'smoke.json',json.dumps(report,indent=2).encode('utf-8'))
                window.close();app.quit()
            except Exception:
                atomic_write(data_dir/'smoke_error.txt',traceback.format_exc().encode('utf-8'));window.close();app.exit(1)
        QTimer.singleShot(600,smoke)
    return app.exec()
