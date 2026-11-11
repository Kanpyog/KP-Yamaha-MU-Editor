from __future__ import annotations
import json
from pathlib import Path
from PySide6.QtCore import Qt,QTimer,QUrl
from PySide6.QtGui import QColor,QDesktopServices
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QComboBox,
 QSpinBox,QCheckBox,QTableWidgetItem,QHeaderView,QSplitter,QMessageBox,QFileDialog,
 QFormLayout,QGroupBox,QScrollArea,QTextEdit,QPlainTextEdit,QTabWidget,QInputDialog)
from .widgets import page,button,label,table,NumericDelegate,ParamTabs,ToneGraph,DragSpinBox as QSpinBox,style_cell,value_style,ask_number
from .mixer import Mixer
from .effects import Effects
from .schema import PART_BY_KEY,part_params,DRUM,Param,CC_CONTROLS,PROFILES,CC_PART
from .protocol import change,decode,encode,cc,rpn
from .catalog import CATEGORIES
from .engine import load_midi,write_midi
from .i18n import (QLabel,QLineEdit,QComboBox,QCheckBox,QTableWidgetItem,QFormLayout,
 QGroupBox,QTabWidget,QInputDialog,QMessageBox,QFileDialog)
from .voice_catalog import display_voice_name
from .session import read_bounded_file, MAX_SYSEX_BYTES

CC_DEFAULTS={7:100,10:64,11:127,71:64,72:64,73:64,74:64,75:64,76:64,77:64,78:64,91:40}


def item(text,editable=False,translate=True):
    if translate:obj=QTableWidgetItem(str(text))
    else:
        from PySide6.QtWidgets import QTableWidgetItem as NativeItem
        obj=NativeItem(str(text))
    if not editable:obj.setFlags(obj.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return obj




class Voices(QWidget):
    def __init__(self,app):
        super().__init__();self.app=app;self.rows=[];self.signature=None
        w,l=page('音色ブラウザー','名前・バンク・カテゴリから検索。割り当て先は上部の選択パートです。')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(w)
        row=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('音色名、MSB:LSB:Program を検索');self.search.textChanged.connect(self.filter)
        self.category=QComboBox();self.category.addItems(['全カテゴリ',*CATEGORIES,'Drum / SFX Kit']);self.category.currentIndexChanged.connect(self.filter)
        self.favs=QCheckBox('お気に入り');self.favs.toggled.connect(self.filter)
        row.addWidget(self.search,3);row.addWidget(self.category,2);row.addWidget(self.favs);l.addLayout(row)
        self.grid=table(['Favorite','Program','MSB','LSB','音色名','カテゴリ','Elements']);self.grid.setSelectionBehavior(self.grid.SelectionBehavior.SelectRows)
        self.grid.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignVCenter)
        self.grid.cellDoubleClicked.connect(lambda r,c:self.apply());self.grid.cellClicked.connect(self.clicked)
        for col,width in enumerate((75,75,65,65,290,165,85)):self.grid.setColumnWidth(col,width)
        l.addWidget(self.grid)
        self.details=label('');l.addWidget(self.details)
        row=QHBoxLayout();row.addWidget(button('選択パートへ割り当て',self.apply,True));row.addWidget(button('現在のパートを試聴',lambda:app.audition(60)))
        row.addStretch();row.addWidget(button('バンク番号を直接指定',self.direct));l.addLayout(row)

    def refresh(self):
        s=self.app.session;native=s.get_bytes(0x49,(0,0,0x12),1)!=b'\x00';signature=(s.profile.name,native,s.mode)
        if self.signature==signature:self.filter();return
        self.signature=signature;self.rows=list(self.app.catalog.voices(s.profile,native,s.mode))
        kits=self.app.catalog.kits(s.profile,native,s.mode)
        for kit in kits:
            if kit.get('generation',1)<=s.profile.generation:self.rows.append(dict(kit,category='Drum / SFX Kit'))
        self.grid.setRowCount(len(self.rows));self.grid.blockSignals(True)
        for r,v in enumerate(self.rows):
            key=f"{v['msb']}:{v['lsb']}:{v['program']}"
            cat=v['category']
            values=['★' if key in self.app.favorites else '☆',v['program']+1,v['msb'],v['lsb'],display_voice_name(v['name'],v['program'],v['msb'],v['lsb']),cat,v.get('elements','—')]
            for c,val in enumerate(values):self.grid.setItem(r,c,item(val))
        self.grid.blockSignals(False);self.filter()

    def filter(self,*_):
        query=self.search.text().casefold();category=self.category.sourceText()
        for r,v in enumerate(self.rows):
            key=f"{v['msb']}:{v['lsb']}:{v['program']}";cat=v['category']
            searchkey=f"{v['msb']}:{v['lsb']}:{v['program']+1}"
            hidden=(query not in (display_voice_name(v['name'],v['program'],v['msb'],v['lsb'])+' '+searchkey).casefold() or (self.category.currentIndex()>0 and cat!=category)
                    or (self.favs.isChecked() and key not in self.app.favorites))
            self.grid.setRowHidden(r,hidden)

    def clicked(self,r,c):
        v=self.rows[r];key=f"{v['msb']}:{v['lsb']}:{v['program']}"
        self.details.setText(f"{display_voice_name(v['name'],v['program'],v['msb'],v['lsb'])}   ·   {v.get('voice_family','')} / {v.get('bank_description','')}   ·   {v.get('source','Yamaha voice list')}")
        if c==0:
            if key in self.app.favorites:self.app.favorites.remove(key)
            else:self.app.favorites.add(key)
            self.grid.item(r,0).setText('★' if key in self.app.favorites else '☆');self.app.save_preferences()

    def apply(self):
        row=self.grid.currentRow()
        if row>=0 and not self.grid.isRowHidden(row):
            v=self.rows[row];self.app.assign_voice(v['msb'],v['lsb'],v['program'])
        else:self.app.status('一覧に表示されている音色を選択してください。')

    def direct(self):
        text,ok=QInputDialog.getText(self,'音色番号を指定','MSB, LSB, Program（Programは1～128）',text='0, 0, 1')
        if ok:
            try:
                msb,lsb,program=[int(x.strip()) for x in text.split(',')]
                if not 0<=msb<=127 or not 0<=lsb<=127 or not 1<=program<=128:raise ValueError('値が範囲外です。')
                self.app.assign_voice(msb,lsb,program-1)
            except ValueError as exc:self.app.error(str(exc))


class Parts(QWidget):
    def __init__(self,app):
        super().__init__();self.app=app;self.signature=None
        w,l=page('パート編集','パートの音作り、演奏コントローラーの効き方、受信設定をまとめて編集します。')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(w)
        row=QHBoxLayout();self.title=label('','font-size:32px;font-weight:750;color:@title@;');row.addWidget(self.title,1)
        row.addWidget(button('コピー',app.copy_part));row.addWidget(button('音作りを貼り付け',app.paste_part));row.addWidget(button('このパートを取得',app.read_part));l.addLayout(row)
        self.graph=ToneGraph();l.addWidget(self.graph)
        self.form=ParamTabs();self.form.changed.connect(lambda p,v:app.edit(p,v));l.addWidget(self.form,1)

    def refresh(self):
        a=self.app;s=a.session
        if self.signature!=s.profile.name:self.form.build(part_params(s.profile));self.form.fixed_sustain();self.signature=s.profile.name
        self.title.setText(f'Part {a.part_name(a.selected_part)}  ·  {a.voice_name(a.selected_part)}')
        self.form.refresh(s,a.selected_part)
        self.graph.values=tuple(s.get(PART_BY_KEY[k],a.selected_part) for k in ('cutoff','resonance','hpf','attack','decay','release'));self.graph.update()


class Drums(QWidget):
    def __init__(self,app):
        super().__init__();self.app=app;self.guard=False;self.signature=None;self.params=[]
        w,l=page('ドラム編集','編集セットを共有するパートには、同じ編集内容が反映されます。ノートを選択して試聴できます。')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(w)
        row=QHBoxLayout();self.setup=QComboBox();self.setup.currentIndexChanged.connect(self.refresh);row.addWidget(self.setup)
        self.group=QComboBox();self.group.addItems(['すべて','基本','送り','発音','フィルター・EG','EQ','感度']);self.group.currentTextChanged.connect(self.filter);row.addWidget(self.group)
        self.search=QLineEdit();self.search.setPlaceholderText('ノート番号・楽器名');self.search.textChanged.connect(self.filter);row.addWidget(self.search)
        self.follow=QCheckBox('MIDI入力に追従');row.addWidget(self.follow);l.addLayout(row)
        self.usage=label('');l.addWidget(self.usage)
        self.grid=table([]);self.grid.setItemDelegate(NumericDelegate(self.grid));self.grid.cellChanged.connect(self.changed)
        self.grid.cellDoubleClicked.connect(lambda r,c:app.audition(r+13));l.addWidget(self.grid,1)
        row=QHBoxLayout();row.addWidget(button('選択音を試聴',self.audition));row.addWidget(button('セルをコピー',self.copy_cells));row.addWidget(button('セルを貼り付け',self.paste_cells))
        row.addStretch();row.addWidget(button('このセットを取得',self.read));row.addWidget(button('選択パートにセットを割当',self.assign,True));l.addLayout(row)
        l.addWidget(label('Single/Multi＝同音連打の重なり。Alternate Group＝異なる音同士の排他発音。Variationは接続方式によって送り量／ON-OFFとして作用します。','color:@muted@;'))

    def refresh(self,*_):
        a=self.app;s=a.session;p=s.profile
        if self.grid.numeric_dragging or self.grid.state()==self.grid.State.EditingState:return
        self.guard=True;self.grid.blockSignals(True)
        if self.signature!=p.name:
            self.setup.blockSignals(True);self.setup.clear();self.setup.addItems([f'Drum Setup {n+1}' for n in range(p.drums)]);self.setup.blockSignals(False)
            self.params=[x for x in DRUM if x.allowed(p)]
            self.grid.setColumnCount(2+len(self.params));self.grid.setHorizontalHeaderLabels(['Note','楽器名（標準キット参考）']+[x.label for x in self.params])
            self.grid.setRowCount((79 if p.generation>=3 else 72) if p.drums else 0);self.grid.setColumnWidth(0,65);self.grid.setColumnWidth(1,200)
            for i in range(2,self.grid.columnCount()):self.grid.setColumnWidth(i,100)
            self.signature=p.name
        setup=max(0,self.setup.currentIndex())
        for r in range(self.grid.rowCount()):
            note=r+13;self.grid.setItem(r,0,item(note));self.grid.setItem(r,1,item(a.catalog.data['drum_names'].get(str(note),'—')))
            for c,param in enumerate(self.params,2):
                value=s.get(param,note,setup);cell=item(value-param.offset,True)
                cell.setData(Qt.ItemDataRole.UserRole,(param.minimum-param.offset,param.maximum-param.offset));origin=s.origin(param,note,setup)
                style_cell(cell,s,param,note,setup)
                self.grid.setItem(r,c,cell)
        mode=PART_BY_KEY['mode'];users=[a.part_name(n) for n in range(p.parts) if s.get(mode,n)==setup+2]
        self.usage.setText('使用パート：'+('、'.join(users) if users else '未割当')+'    ·    キットのProgram Changeでこのセットの編集は初期化されます。')
        self.grid.blockSignals(False);self.guard=False;self.filter()

    def filter(self,*_):
        for i,param in enumerate(self.params,2):self.grid.setColumnHidden(i,self.group.currentIndex()>0 and param.group!=self.group.sourceText())
        query=self.search.text().casefold()
        for r in range(self.grid.rowCount()):self.grid.setRowHidden(r,query not in (self.grid.item(r,0).text()+' '+self.grid.item(r,1).text()).casefold())

    def changed(self,row,col):
        if self.guard or col<2:return
        param=self.params[col-2]
        try:
            self.app.edit(param,int(self.grid.item(row,col).text())+param.offset,row+13,self.setup.currentIndex())
            self.guard=True;style_cell(self.grid.item(row,col),self.app.session,param,row+13,self.setup.currentIndex());self.guard=False
        except ValueError as exc:self.app.error(str(exc));self.refresh()

    def audition(self):
        if self.grid.currentRow()>=0:self.app.audition(self.grid.currentRow()+13)

    def read(self):
        from .schema import read_blocks
        high=0x30+max(0,self.setup.currentIndex())
        self.app.read_addresses([x for x in read_blocks(self.app.session.profile) if x[1][0]==high],'ドラム取得')

    def assign(self):
        if self.app.session.profile.drums:self.app.assign_part_mode(self.app.selected_part,2+self.setup.currentIndex())

    def copy_cells(self):
        ranges=self.grid.selectedRanges()
        if not ranges:return
        rg=ranges[0];self.app.cell_clipboard=[[self.grid.item(r,c).text() for c in range(max(2,rg.leftColumn()),rg.rightColumn()+1)] for r in range(rg.topRow(),rg.bottomRow()+1)]
        self.app.status('ドラムの選択セルをコピーしました。')

    def paste_cells(self):
        data=self.app.cell_clipboard;r=self.grid.currentRow();c=self.grid.currentColumn()
        if not data or r<0 or c<2:return
        changes=[]
        try:
            for dr,row in enumerate(data):
                for dc,val in enumerate(row):
                    if r+dr>=self.grid.rowCount() or c+dc>=self.grid.columnCount():continue
                    p=self.params[c+dc-2];v=int(val)+p.offset
                    if not p.minimum<=v<=p.maximum:raise ValueError(f'{p.label}: 貼り付け値が範囲外です。')
                    changes.append((p,v,r+dr+13,self.setup.currentIndex()))
            self.app.edit_many(changes,'ドラムのセル貼付')
        except ValueError as exc:self.app.error(str(exc))




class Layers(QWidget):
    def __init__(self,app):
        super().__init__();self.app=app;self.signature=None;self.guard=True;self.selected_parts=list(range(4))
        w,l=page('レイヤー / スプリット','同じ受信先に複数パートを重ねます。音色内部のエレメント編集とは別の機能です。')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(w)
        row=QHBoxLayout();row.addWidget(label('共通の受信先'))
        self.receive=QSpinBox();self.receive.setRange(1,64);self.receive.setPrefix('A1=1 / B1=17  ·  ');row.addWidget(self.receive)
        row.addWidget(button('2音色を重ねる',lambda:self.preset('layer')));row.addWidget(button('左右スプリット',lambda:self.preset('split')))
        row.addWidget(button('ベロシティ切替',lambda:self.preset('velocity')));row.addStretch();l.addLayout(row)
        self.grid=table(['使用','Part','音色（音色画面で変更）','Volume','Pan','Transpose','Key Low','Key High','Vel Low','Vel High'])
        self.grid.setItemDelegate(NumericDelegate(self.grid));self.grid.setRowCount(4);self.grid.setColumnWidth(2,230)
        self.parts=[]
        for r in range(4):
            cell=item('');cell.setFlags(cell.flags()|Qt.ItemFlag.ItemIsUserCheckable);cell.setCheckState(Qt.CheckState.Checked if r<2 else Qt.CheckState.Unchecked);self.grid.setItem(r,0,cell)
            combo=QComboBox();combo.currentIndexChanged.connect(lambda _,row=r:self.part_changed(row));self.grid.setCellWidget(r,1,combo);self.parts.append(combo)
            for c,(value,lo,hi) in enumerate([(100,0,127),(64,0,127),(0,-24,24),(0,0,127),(127,0,127),(1,1,127),(127,1,127)],3):
                cell=item(value,True);cell.setData(Qt.ItemDataRole.UserRole,(lo,hi));self.grid.setItem(r,c,cell)
        l.addWidget(self.grid,1)
        row=QHBoxLayout();row.addWidget(button('選択行の音色を編集',self.choose_voice));row.addStretch();l.addLayout(row)
        self.info=label('有効行の変更とプリセットは即時反映します。使用をOFFにすると、そのパートのMIDI受信をOFFにします。');l.addWidget(self.info)
        self.grid.cellChanged.connect(self.changed);self.receive.valueChanged.connect(self.receive_changed);self.guard=False

    def refresh(self):
        if self.grid.numeric_dragging or self.grid.state()==self.grid.State.EditingState:return
        p=self.app.session.profile;self.guard=True;self.grid.blockSignals(True)
        if self.signature!=p.name:
            for r,combo in enumerate(self.parts):
                combo.blockSignals(True);combo.clear();combo.addItems([self.app.part_name(n) for n in range(p.parts)]);combo.setCurrentIndex(r);combo.blockSignals(False)
            self.selected_parts=[c.currentIndex() for c in self.parts];self.receive.setMaximum(p.parts);self.signature=p.name
        self.refresh_names();params={x.key:x for x in part_params(p)}
        for r,combo in enumerate(self.parts):
            n=combo.currentIndex()
            checked=self.app.session.get(params['receive'],n)==self.receive.value()-1
            self.grid.item(r,0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            for c,key in enumerate(('volume','pan','shift','note_low','note_high','velocity_low','velocity_high'),3):
                cell=self.grid.item(r,c);param=params.get(key)
                if param:
                    cell.setText(str(self.app.session.get(param,n)-param.offset));cell.setData(Qt.ItemDataRole.UserRole,(param.minimum-param.offset,param.maximum-param.offset));style_cell(cell,self.app.session,param,n)
                else:cell.setText('—');cell.setData(Qt.ItemDataRole.UserRole,None)
        self.grid.blockSignals(False);self.guard=False

    def part_changed(self,row):
        if self.guard:return
        n=self.parts[row].currentIndex();old=self.selected_parts[row]
        if any(i!=row and c.currentIndex()==n for i,c in enumerate(self.parts)):
            self.parts[row].blockSignals(True);self.parts[row].setCurrentIndex(old);self.parts[row].blockSignals(False);self.app.error('同じパートを複数行に選択できません。');return
        self.selected_parts[row]=n
        if self.grid.item(row,0).checkState()==Qt.CheckState.Checked:
            param=next(p for p in part_params(self.app.session.profile) if p.key=='receive')
            self.app.edit_many([(param,16 if self.app.session.profile.native5 else 127,old,None),(param,self.receive.value()-1,n,None)],'レイヤーのパート変更')
        self.refresh()

    def receive_changed(self,*_):
        if self.guard:return
        param=next(p for p in part_params(self.app.session.profile) if p.key=='receive')
        self.app.edit_many([(param,self.receive.value()-1,c.currentIndex(),None) for r,c in enumerate(self.parts) if self.grid.item(r,0).checkState()==Qt.CheckState.Checked],'レイヤー受信先')

    def changed(self,row,col):
        if self.guard:return
        params={p.key:p for p in part_params(self.app.session.profile)};n=self.parts[row].currentIndex()
        if col==0:
            self.app.edit(params['receive'],self.receive.value()-1 if self.grid.item(row,0).checkState()==Qt.CheckState.Checked else 16 if self.app.session.profile.native5 else 127,n);return
        if not 3<=col<10 or self.grid.item(row,0).checkState()!=Qt.CheckState.Checked:return
        key=('volume','pan','shift','note_low','note_high','velocity_low','velocity_high')[col-3]
        if key not in params:return
        try:
            value=int(self.grid.item(row,col).text())+params[key].offset;self.app.edit(params[key],value,n)
            self.guard=True;style_cell(self.grid.item(row,col),self.app.session,params[key],n);self.guard=False
        except ValueError as exc:self.app.error(str(exc));self.guard=False;self.refresh()

    def refresh_names(self,*_):
        for r,combo in enumerate(self.parts):
            n=combo.currentIndex()
            if n>=0:self.grid.setItem(r,2,item(self.app.voice_name(n)))

    def preset(self,kind):
        self.guard=True
        for r in range(4):
            self.grid.item(r,0).setCheckState(Qt.CheckState.Checked if r<2 else Qt.CheckState.Unchecked)
            values=[100,64,0,0,127,1,127]
            if kind=='split' and r<2:values[3:5]=[0,59] if r==0 else [60,127]
            if kind=='velocity' and r<2:values[5:7]=[1,79] if r==0 else [80,127]
            for c,val in enumerate(values,3):self.grid.item(r,c).setText(str(val))
        self.guard=False;self.apply()

    def apply(self):
        changes=[];used=set();s=self.app.session;params={p.key:p for p in part_params(s.profile)}
        try:
            for r,combo in enumerate(self.parts):
                if self.grid.item(r,0).checkState()!=Qt.CheckState.Checked:continue
                n=combo.currentIndex()
                if n in used:raise ValueError('同じパートが複数行に選択されています。')
                used.add(n);values=[int(self.grid.item(r,c).text()) if key in params else 1 if key=='velocity_low' else 127 for c,key in enumerate(('volume','pan','shift','note_low','note_high','velocity_low','velocity_high'),3)]
                if values[3]>values[4] or values[5]>values[6]:raise ValueError('下限は上限以下にしてください。')
                changes.append((params['receive'],self.receive.value()-1,n,None))
                for key,val in zip(('volume','pan','shift','note_low','note_high','velocity_low','velocity_high'),values):
                    if key in params:changes.append((params[key],val+params[key].offset,n,None))
            self.app.edit_many(changes,'レイヤー / スプリット')
        except ValueError as exc:self.app.error(str(exc))

    def choose_voice(self):
        row=max(0,self.grid.currentRow());self.app.select_part(self.parts[row].currentIndex());self.app.navigate(1)


class Library(QWidget):
    def __init__(self,app):
        super().__init__();self.app=app
        w,l=page('ライブラリー','セットをPCに保存し、比較・呼び出し・書き出しを行います。数値は接続中の本体へ即時反映します。')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(w)
        form=QFormLayout();self.name=QLineEdit();self.tags=QLineEdit();self.memo=QTextEdit();self.memo.setMaximumHeight(100)
        form.addRow('セット名',self.name);form.addRow('タグ',self.tags);form.addRow('メモ',self.memo);l.addLayout(form)
        row=QHBoxLayout();row.addWidget(button('セットを保存',self.save,True));row.addWidget(button('セットを開く',app.load_session));row.addWidget(button('SysExを取り込む',self.import_syx));row.addStretch();l.addLayout(row)
        row=QHBoxLayout();row.addWidget(button('SysExを書き出す',self.export_syx));row.addWidget(button('SMF Format 1で保存',self.export_mid));row.addWidget(button('比較 A を記憶',app.store_a));row.addWidget(button('A / B を切替',app.swap_a));row.addStretch();l.addLayout(row)
        self.files=table(['ファイル','更新日時','種類']);self.files.setSelectionBehavior(self.files.SelectionBehavior.SelectRows)
        self.files.cellDoubleClicked.connect(self.open_row);l.addWidget(self.files,1)
        self.summary=label('');l.addWidget(self.summary)

    def refresh(self):
        s=self.app.session
        self.name.setText(s.metadata['name']);self.tags.setText(s.metadata['tags']);self.memo.setPlainText(s.metadata['memo'])
        self.entries=sorted((self.app.data_dir/'sessions').glob('*.mu.json'),key=lambda p:p.stat().st_mtime,reverse=True) if (self.app.data_dir/'sessions').exists() else []
        self.files.setRowCount(len(self.entries))
        from datetime import datetime
        for r,path in enumerate(self.entries):
            for c,v in enumerate((path.name,datetime.fromtimestamp(path.stat().st_mtime).strftime('%Y/%m/%d %H:%M'),'MUセット')):self.files.setItem(r,c,item(v,translate=c==2))
        self.summary.setText(f'現在のセット：{s.profile.name} / {s.mode}  ·  既知の設定 {len(s.memory):,} bytes  ·  {len(s.blocks):,} blocks')

    def save(self):
        self.app.session.metadata.update(name=self.name.text(),tags=self.tags.text(),memo=self.memo.toPlainText());self.app.save_session()

    def open_row(self,r,c):
        if r<len(self.entries):self.app.load_session(str(self.entries[r]))

    def import_syx(self):
        path,_=QFileDialog.getOpenFileName(self,'SysExを取り込む',str(self.app.data_dir),'SysEx (*.syx)')
        if path:
            try:
                data = read_bounded_file(path, MAX_SYSEX_BYTES, 'SysExファイルが大きすぎます。')
                count=self.app.session.import_sysex(data);self.app.mark_changed();self.app.refresh();self.app.status(f'{count}メッセージを取り込みました。本体へはまだ送信していません。')
            except Exception as exc:self.app.error(str(exc))

    def export_syx(self):
        path,_=QFileDialog.getSaveFileName(self,'SysExを書き出す',str(self.app.data_dir/'sessions'/'setup.syx'),'SysEx (*.syx)')
        if path:
            from .session import atomic_write
            try:atomic_write(path,b''.join(self.app.session.export_messages()));self.app.status('SysExを書き出しました。')
            except Exception as exc:self.app.error(str(exc))

    def export_mid(self):
        self.app.save_midi()



class Settings(QWidget):
    def __init__(self,app):
        super().__init__();self.app=app;self.model_signature=None;self.learn_target=None
        w,l=page('環境設定','MIDI接続、演奏操作、システム設定、通信ログを確認できます。')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(w)
        self.tabs=QTabWidget();l.addWidget(self.tabs,1)
        self.make_connection();self.make_language();self.make_controls();self.make_system();self.make_extensions();self.make_monitor();self.make_diagnostics()

    def make_language(self):
        w=QWidget();layout=QVBoxLayout(w)
        layout.addWidget(label('Language','font-size:20px;font-weight:700;'))
        self.language=QComboBox();self.language.addItem('英語（Eng）','en');self.language.addItem('Japanese（日本語）','ja')
        self.language.setCurrentIndex(self.language.findData(self.app.language))
        self.language.currentIndexChanged.connect(self.app.change_language)
        layout.addWidget(self.language);layout.addWidget(label('変更はすぐに反映され、次回の起動にも引き継がれます。'))
        layout.addStretch();self.tabs.addTab(w,'Language');self.language_page=w

    def make_diagnostics(self):
        w=QWidget();l=QVBoxLayout(w);self.diagnostics_page=w
        l.addWidget(label('通信の診断ログ','font-size:20px;font-weight:700;'))
        self.diagnostic_mode=QComboBox();self.diagnostic_mode.addItems(['通常モード','デバッグモード'])
        self.diagnostic_mode.setCurrentIndex(1 if self.app.diagnostics.debug else 0)
        self.diagnostic_mode.currentIndexChanged.connect(self.app.set_diagnostic_mode);l.addWidget(self.diagnostic_mode)
        l.addWidget(label('通常モード：接続、処理時間、再試行、エラーの要約を自動保存します。\nデバッグモード：送受信したMIDI、ドライバーからの受信断片、バッファ状態、画面の処理遅延も記録します。\n問題が起きた時刻を添えて「診断ログを書き出す」のZIPを共有してください。再起動せずに切り替えられます。'))
        self.diagnostic_status=label('');self.diagnostic_status.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);l.addWidget(self.diagnostic_status)
        row=QHBoxLayout();self.export_diagnostics_button=button('診断ログを書き出す',self.app.export_diagnostics,True);row.addWidget(self.export_diagnostics_button)
        row.addWidget(button('保存フォルダーを開く',lambda:QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.app.diagnostics.folder)))));row.addStretch();l.addLayout(row)
        l.addWidget(label('診断ログは14日・合計200MBを目安に自動整理します。書き出すZIPは新しいログを優先し、最大100ファイル・50MB分を収録します。既存の設定取得ログや保存セットは自動整理の対象にしません。','color:@muted@;'))
        l.addStretch();self.tabs.addTab(w,'診断');self.refresh_diagnostics()

    def refresh_diagnostics(self):
        d=self.app.diagnostics
        text=('デバッグモード' if d.debug else '通常モード')+'\n保存先：'+str(d.folder)
        if d.error:text+='\n保存エラー：'+d.error
        if d.dropped:text+=f'\n記録が追いつかず省略したイベント：{d.dropped}件'
        self.diagnostic_status.setText(text)

    def make_connection(self):
        w=QWidget();l=QVBoxLayout(w);self.connection_info=label('');l.addWidget(self.connection_info)
        row=QHBoxLayout();row.addWidget(button('MIDI接続を設定',self.app.connect_dialog,True));row.addWidget(button('全設定を取得・退避',self.app.read_all));row.addStretch();l.addLayout(row)
        self.thru=QCheckBox('入力したチャンネルメッセージを出力へスルーする');self.thru.toggled.connect(lambda v:setattr(self.app.engine,'thru',v));l.addWidget(self.thru)
        self.thru_port=QComboBox();self.thru_port.addItems(['スルー出力 A','スルー出力 B','スルー出力 C','スルー出力 D']);self.thru_port.currentIndexChanged.connect(lambda v:setattr(self.app.engine,'thru_port',v));l.addWidget(self.thru_port)
        l.addWidget(label('本体取得は既存の設定を変更しません。接続中のパラメーター変更は即時送信されます。外部DAWの変更は、このアプリを通らない場合は再取得が必要です。'))
        self.capabilities=table(['機種','Parts','Polyphony','Insertion','Drum Setup','検証状態']);self.capabilities.setRowCount(len(PROFILES))
        for r,p in enumerate(PROFILES.values()):
            for c,v in enumerate((p.name,p.parts,p.polyphony,p.insertions,p.drums,'実機未検証・サポート外' if p.unsupported else 'MU500で検証' if p.name=='MU500' else '仕様書対応・実機未検証')):self.capabilities.setItem(r,c,item(v))
        self.capabilities.resizeColumnsToContents();l.addWidget(self.capabilities);self.tabs.addTab(w,'接続')

    def make_controls(self):
        w=QWidget();l=QVBoxLayout(w);l.addWidget(label('CCは受信チャンネル全体に作用します。同じチャンネルのレイヤーにも共通して効きます。'))
        scroll=QScrollArea();scroll.setWidgetResizable(True);body=QWidget();form=QFormLayout(body)
        self.cc_widgets={}
        for number,title in CC_CONTROLS:
            spin=QSpinBox();spin.setRange(0,127);spin.setKeyboardTracking(True);spin.setValue(CC_DEFAULTS.get(number,0))
            spin.valueChanged.connect(lambda value,num=number:self.app.send_cc(num,value));form.addRow(f'CC {number} · {title}',spin);self.cc_widgets[number]=spin
        scroll.setWidget(body);l.addWidget(scroll,1)
        row=QHBoxLayout();row.addWidget(button('ベンド幅を設定（RPN）',self.bend_range));row.addWidget(button('任意CC / NRPNを送信',self.custom_control));row.addStretch();l.addLayout(row)
        row=QHBoxLayout();self.learn=QComboBox();self.learn.addItems(['MIDI Learn対象を選択',*PART_BY_KEY]);row.addWidget(self.learn)
        row.addWidget(button('次のCCを割当',self.start_learn));row.addWidget(button('Learn割当を消去',self.clear_learn));l.addLayout(row)
        self.tabs.addTab(w,'演奏・CC')

    def make_system(self):
        self.system=ParamTabs();self.system.changed.connect(lambda p,v:self.app.edit(p,v,0));self.tabs.addTab(self.system,'システム')

    def make_extensions(self):
        w=QWidget();l=QVBoxLayout(w);self.extensions=label('');l.addWidget(self.extensions)
        self.extension_form=ParamTabs();self.extension_form.changed.connect(lambda p,v:self.app.edit(p,v,self.extension_part.value()-1));l.addWidget(self.extension_form,1)
        row=QHBoxLayout();self.extension_part=QSpinBox();self.extension_part.setRange(1,2);self.extension_part.valueChanged.connect(self.refresh_extension)
        row.addWidget(label('A/D Part'));row.addWidget(self.extension_part);row.addWidget(button('A/D設定を取得',self.read_extension));row.addStretch();l.addLayout(row)
        row=QHBoxLayout();row.addWidget(button('本体Performanceを呼び出す',self.performance));row.addWidget(button('PLGのパート割当',self.plg_assign));row.addStretch();l.addLayout(row)
        l.addWidget(label('PLG音源内部の音色編集とMU2000の波形転送は、この版の対応範囲に含みません。通常の内蔵音源編集とは独立した機能です。','color:@muted@;'))
        self.tabs.addTab(w,'機種固有')

    def make_monitor(self):
        w=QWidget();self.log_page=w;l=QVBoxLayout(w);self.monitor=QPlainTextEdit();self.monitor.setReadOnly(True);self.monitor.setMaximumBlockCount(1500);self.monitor.setStyleSheet('font-family:Consolas;font-size:11px;');l.addWidget(self.monitor)
        row=QHBoxLayout();row.addWidget(button('ログを消去',self.monitor.clear));row.addWidget(button('ログを保存',self.save_log));row.addStretch();l.addLayout(row);self.tabs.addTab(w,'MIDIログ')

    def refresh(self):
        a=self.app;s=a.session;p=s.profile
        self.refresh_diagnostics()
        self.connection_info.setText(f'{p.name}  ·  {"接続中" if a.engine.connected else "オフライン"}\n検出した本体：{a.detected_name or "未検出"}\n設定保存先：{a.data_dir}')
        if self.model_signature!=p.name:
            high=0;model=0x44 if p.native5 else 0x4c
            params=[]
            if not p.native5:
                for key,title,low in [('mute_lock','Mute Lock',0),('eq_lock','EQ Lock',2),('receive_reset','System On受信',3),('receive_bank','Bank Select受信',4)]:params.append(Param(key,title,low,'MU固有',maximum=1,default=1 if low in (3,4) else 0,high=0,model=0x49,choices=('OFF','ON')))
                params.append(Param('bulk_interval','Bulk間隔 0=50 / 1=100 / 2=150 / 3=200 / 4=300ms',5,'MU固有',maximum=4,default=2,high=0,model=0x49))
            self.system.build(params)
            adparams=[Param('ad_gain','Input Gain 0=Mic / 1=Line',0,'A/D',maximum=1,default=0,high=0x10),
                Param('ad_bank_msb','Bank MSB',1,'A/D',default=0,high=0x10),Param('ad_bank_lsb','Bank LSB',2,'A/D',default=0,high=0x10),
                Param('ad_program','Program',3,'A/D',default=0,offset=-1,high=0x10),
                Param('ad_volume','Volume',0x0b,'A/D',default=0,high=0x10),Param('ad_pan','Pan',0x0e,'A/D',minimum=1,high=0x10),
                Param('ad_dry','Dry',0x11,'A/D',default=127,high=0x10),Param('ad_chorus','Chorus',0x12,'A/D',default=0,high=0x10),
                Param('ad_reverb','Reverb',0x13,'A/D',default=40,high=0x10),Param('ad_variation','Variation',0x14,'A/D',default=0,high=0x10)]
            self.extension_form.build(adparams if p.ad else []);self.model_signature=p.name
        self.system.refresh(s,0);self.refresh_extension();self.refresh_controls()

    def refresh_controls(self):
        s=self.app.session;params={p.key:p for p in part_params(s.profile)};n=self.app.selected_part
        try:port,ch=self.app.channel()
        except ValueError:port,ch=n//16,n%16
        for number,control in self.cc_widgets.items():
            param=params.get(CC_PART.get(number));default=s.default_value(param,n) if param else CC_DEFAULTS.get(number,0)
            value=s.get(param,n) if param else s.realtime.get((port,ch,number),default)
            control.blockSignals(True);control.setValue(value);value_style(control,value!=default,False);control.blockSignals(False)

    def refresh_extension(self,*_):
        p=self.app.session.profile
        self.extensions.setText(f'A/D入力編集：{"あり" if p.ad else "なし"}  ·  PLGスロット：{p.plg}  ·  本体Performance：{"あり" if p.performance else "なし"}')
        if p.ad:self.extension_form.refresh(self.app.session,self.extension_part.value()-1)

    def read_extension(self):
        if self.app.session.profile.ad:self.app.read_addresses([(0x4c,(0x10,n,0)) for n in range(2)],'A/D取得')

    def performance(self):
        if not self.app.session.profile.performance:self.app.status('この機種には本体Performanceモードがありません。');return
        value,ok=ask_number(self,'Performanceを呼び出す','本体をPerformanceモードにしてから実行してください。番号：',1,1,100)
        if ok:
            raw=self.app.session.get_bytes(0x49,(0,0,6),1);channel=raw[0] if raw else 0
            self.app.send_messages([(0,bytes((0xc0|channel,value-1)))],'Performance呼出')

    def plg_assign(self):
        if not self.app.session.profile.plg:self.app.status('この機種にPLGスロットはありません。');return
        text,ok=QInputDialog.getText(self,'PLGパート割当','ボード種別（VL=0, SG=1, DX=2）, シリアル番号, Part 1～16（0=OFF）',text='0, 0, 1')
        if ok:
            try:
                kind,serial,part=[int(x.strip()) for x in text.split(',')]
                if kind not in (0,1,2) or not 0<=serial<=15 or not 0<=part<=16:raise ValueError('値が範囲外です。')
                addr=(0x70,kind,serial);v=part-1 if part else 127
                self.app.session.checkpoint('PLG割当');self.app.session.put(0x4c,addr,[v]);self.app.mark_changed()
                if self.app.can_send():self.app.send_messages([(0,change(addr,[v]))],'PLG割当')
            except ValueError as exc:self.app.error(str(exc))

    def bend_range(self):
        value,ok=ask_number(self,'Pitch Bend Range','半音',2,0,24)
        if ok:
            try:
                port,ch=self.app.channel();params={p.key:p for p in part_params(self.app.session.profile)}
                if 'bend_pitch' in params:
                    changes=[(params['bend_pitch'],value+64,n,None) for n in range(self.app.session.profile.parts) if self.app.session.get(params['receive'],n)==port*16+ch]
                    self.app.edit_many(changes,'RPN Bend Range',transmit=False)
                self.app.send_messages([(port,x) for x in rpn(ch,0,0,value)],'RPN Bend Range')
            except ValueError as exc:self.app.error(str(exc))

    def custom_control(self):
        text,ok=QInputDialog.getText(self,'CC / NRPN送信','CC:番号:値 または NRPN:MSB:LSB:値',text='CC:11:127')
        if not ok:return
        try:
            fields=text.split(':');port,ch=self.app.channel()
            if fields[0].upper()=='CC' and len(fields)==3:messages=[cc(ch,int(fields[1]),int(fields[2]))]
            elif fields[0].upper()=='NRPN' and len(fields)==4:messages=rpn(ch,int(fields[1]),int(fields[2]),int(fields[3]),True)
            else:raise ValueError('入力形式を確認してください。')
            self.app.send_messages([(port,x) for x in messages],'CC / NRPN送信')
        except ValueError as exc:self.app.error(str(exc))

    def start_learn(self):
        if self.learn.currentIndex()>0:self.learn_target=self.learn.currentText();self.app.status('次に受信するCCを待っています。')

    def clear_learn(self):
        self.app.learn_map.clear();self.app.save_preferences();self.app.status('MIDI Learn割当を消去しました。')

    def save_log(self):
        path,_=QFileDialog.getSaveFileName(self,'ログを保存',str(self.app.data_dir/'midi_log.txt'),'Text (*.txt)')
        if path:Path(path).write_text(self.monitor.toPlainText(),encoding='utf-8')
