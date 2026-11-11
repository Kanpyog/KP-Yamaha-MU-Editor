from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QTabBar,QCheckBox,QSplitter,QComboBox,QAbstractItemView
from .widgets import page,button,label,table,NumericDelegate,style_cell,value_style
from .schema import part_params,PART_BY_KEY
from .i18n import QTabBar,QCheckBox,QComboBox

class Mixer(QWidget):
    keys=('volume','pan','reverb','chorus','variation','shift','cutoff','resonance','hpf','attack','decay','release','receive')
    def __init__(self,app):
        super().__init__();self.app=app;self.guard=False;self.signature=None;self.mode_boxes={};self.efx_boxes={}
        w,l=page('ミキサー','数値は上下ドラッグで変更。緑・太字は起動時の値との差分です。')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(w)
        row=QHBoxLayout();self.bank=QTabBar();self.bank.setExpanding(False);self.bank.currentChanged.connect(self.bank_changed);row.addWidget(self.bank)
        self.advanced=QCheckBox('音作り・受信先も表示');self.advanced.toggled.connect(self.refresh);row.addWidget(self.advanced)
        row.addStretch();row.addWidget(button('コピー',app.copy_part));row.addWidget(button('音作りを貼付',app.paste_part));l.addLayout(row)
        split=QSplitter();self.grid=table(['Part','音色','Mode','EFX','Mute','Solo']+[{'volume':'Volume','pan':'Pan','shift':'Transpose','cutoff':'LPF','resonance':'Resonance'}.get(k,PART_BY_KEY[k].label) for k in self.keys])
        self.grid.setItemDelegate(NumericDelegate(self.grid));self.grid.cellChanged.connect(self.changed)
        self.grid.verticalHeader().setDefaultSectionSize(28)
        self.grid.cellClicked.connect(lambda r,c:app.select_part(r))
        self.grid.cellDoubleClicked.connect(lambda r,c:app.navigate(1) if c==1 else None)
        for col,width in enumerate((58,225,118,88,48,48,*([75]*len(self.keys)))):self.grid.setColumnWidth(col,width)
        split.addWidget(self.grid)
        details=QWidget();dl=QVBoxLayout(details);dl.setContentsMargins(12,5,0,0)
        self.title=label('','font-size:27px;font-weight:700;');dl.addWidget(self.title)
        self.voice=label('','font-size:17px;font-weight:600;');dl.addWidget(self.voice)
        dl.addWidget(button('音色を選ぶ',lambda:app.navigate(1),True));dl.addWidget(button('パートを編集',lambda:app.navigate(2)))
        dl.addWidget(button('EFXを編集',self.edit_efx));self.info=label('','color:@muted@;');dl.addWidget(self.info);dl.addStretch()
        details.setMinimumWidth(190);details.setMaximumWidth(245);split.addWidget(details);split.setStretchFactor(0,5);split.setStretchFactor(1,1);l.addWidget(split)

    def bank_changed(self,index):
        if index<0 or self.guard:return
        if self.app.selected_part//16!=index:self.app.select_part(index*16)
        self.refresh()

    def edit_efx(self):
        slots=self.app.insertion_slots(self.app.selected_part);self.app.navigate(4)
        if self.app.session.profile.insertions:self.app.pages[4].block.setCurrentIndex(3+(slots[0] if slots else 0))

    def refresh(self,*_):
        a=self.app;s=a.session;p=s.profile;params={x.key:x for x in part_params(p)};g=self.grid
        self.title.setText('Part '+a.part_name(a.selected_part));self.voice.setText(a.voice_name(a.selected_part))
        mode=params.get('mode');value=s.get(mode,a.selected_part) if mode else 0
        users=[a.part_name(n) for n in range(p.parts) if mode and s.get(mode,n)==value] if value>=2 else []
        self.info.setText((f'DRUM{value-1} を共有：\n'+', '.join(users)+'\n\nキット・ノート別編集は共有先すべてへ反映します。' if users else 'DRUM（標準）は編集用のDrum Setupを使用しません。' if value==1 else 'PART：通常音色')+'\n\nEFXは各系統につき1パート。同じEFXを別パートで選ぶと割当が移動します。')
        if g.numeric_dragging or g.state()==QAbstractItemView.State.EditingState:return
        self.guard=True;g.blockSignals(True)
        try:
            if self.signature!=p.name:
                self.bank.blockSignals(True)
                while self.bank.count():self.bank.removeTab(0)
                for n in range((p.parts+15)//16):self.bank.addTab('PART '+chr(65+n))
                self.bank.blockSignals(False);g.setRowCount(0);g.setRowCount(p.parts);self.mode_boxes={};self.efx_boxes={};self.signature=p.name
            self.bank.blockSignals(True);self.bank.setCurrentIndex(a.selected_part//16);self.bank.blockSignals(False)
            for n in range(p.parts):g.setRowHidden(n,n//16!=self.bank.currentIndex())
            start=self.bank.currentIndex()*16
            for n in range(start,min(start+16,p.parts)):
                def put(col,text,editable=False):
                    from .pages import item
                    cell=g.item(n,col)
                    if cell is None:cell=item(text,editable);g.setItem(n,col,cell)
                    elif cell.text()!=str(text):cell.setText(str(text))
                    return cell
                put(0,a.part_name(n));put(1,a.voice_name(n))
                if n not in self.mode_boxes:
                    box=QComboBox();box.setProperty('compact',True);box.setFixedHeight(26)
                    if mode:
                        for value in range(p.drums+2):box.addItem('PART' if value==0 else 'DRUM（標準）' if value==1 else f'DRUM{value-1}',value)
                    else:box.addItem('GM / Drum',0);box.setEnabled(False)
                    box.currentIndexChanged.connect(lambda _,part=n,c=box:self.change_mode(part,c.currentData()));self.mode_boxes[n]=box;g.setCellWidget(n,2,box)
                box=self.mode_boxes[n];box.blockSignals(True);box.setCurrentIndex(box.findData(s.get(mode,n) if mode else 0));box.blockSignals(False)
                if mode:value_style(box,s.is_modified(mode,n),s.origin(mode,n).startswith('未取得'))
                box.setToolTip('PART / DRUM（標準）/ 共有Drum Setup。\n同じDRUM1～4は複数パートに割当可能で、キット・編集内容を共有します。')
                if n not in self.efx_boxes:
                    box=QComboBox();box.setProperty('compact',True);box.setFixedHeight(26);box.currentIndexChanged.connect(lambda _,part=n,c=box:self.change_efx(part,c.currentData()));self.efx_boxes[n]=box;g.setCellWidget(n,3,box)
                box=self.efx_boxes[n];slots=a.insertion_slots(n);box.blockSignals(True);box.clear();box.addItem('Off',-1)
                for slot in range(p.insertions):box.addItem(f'EFX{slot+1}',slot)
                if len(slots)>1:box.addItem(' + '.join(f'EFX{i+1}' for i in slots),tuple(slots));selected=box.count()-1
                else:selected=box.findData(slots[0] if slots else -1)
                box.setCurrentIndex(selected);box.setEnabled(bool(p.insertions));box.blockSignals(False);value_style(box,bool(slots),False)
                box.setToolTip('各EFXは1パート専用。同じEFXを選ぶと割当先を移動します。\n同一パートへの複数EFX割当はエフェクト画面から設定できます。')
                for col,checked in ((4,s.get(params['rcv_5'],n)==0 and n not in a.soloed),(5,n in a.soloed)):
                    cell=put(col,'');cell.setFlags(cell.flags()|Qt.ItemFlag.ItemIsUserCheckable);cell.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
                for col,key in enumerate(self.keys,6):
                    param=params.get(key);cell=put(col,s.get(param,n)-param.offset if param else '—',bool(param))
                    if param:
                        cell.setData(Qt.ItemDataRole.UserRole,(param.minimum-param.offset,param.maximum-param.offset));style_cell(cell,s,param,n)
            for col,key in enumerate(self.keys,6):g.setColumnHidden(col,key not in params or key not in ('volume','pan','reverb','chorus','variation') and not self.advanced.isChecked())
        finally:g.blockSignals(False);self.guard=False

    def change_mode(self,part,value):
        if not self.guard and value is not None:self.app.assign_part_mode(part,value)

    def change_efx(self,part,value):
        if not self.guard and isinstance(value,int):self.app.assign_insertion(part,None if value<0 else value)

    def changed(self,row,col):
        if self.guard:return
        if col==4:self.app.toggle_mute(row,self.grid.item(row,col).checkState()==Qt.CheckState.Checked);return
        if col==5:self.app.toggle_solo(row,self.grid.item(row,col).checkState()==Qt.CheckState.Checked);return
        if col<6:return
        param=next((p for p in part_params(self.app.session.profile) if p.key==self.keys[col-6]),None)
        if param:
            try:
                self.app.edit(param,int(self.grid.item(row,col).text())+param.offset,row)
                self.guard=True;style_cell(self.grid.item(row,col),self.app.session,param,row);self.guard=False
            except ValueError as exc:self.app.error(str(exc));self.guard=False;self.refresh()
