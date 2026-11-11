from dataclasses import replace
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QTabBar,QComboBox,QInputDialog
from .widgets import page,button,label,ParamTabs,InlineParams,value_style
from .schema import read_blocks
from .protocol import change
from .effect_parameters import build_effect_parameters
from .i18n import QTabBar,QComboBox,QInputDialog

class Effects(QWidget):
    def __init__(self,app):
        super().__init__();self.app=app;self.signature=None;self.kind='reverb';self.slot=0
        w,l=page('エフェクト','ブロックをタブで選択。種類・数値・割当の変更は、接続中の本体へ即時反映します。')
        outer=QVBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.addWidget(w)
        self.block=QTabBar();self.block.setExpanding(False);self.block.currentChanged.connect(self.block_changed);l.addWidget(self.block)
        row=QHBoxLayout();self.type=QComboBox();self.type.setMinimumWidth(280);self.type.currentIndexChanged.connect(self.apply_type);row.addWidget(self.type,1)
        self.raw_type=button('番号指定',self.direct_type);row.addWidget(self.raw_type);row.addWidget(button('エフェクトを取得',self.read));l.addLayout(row)
        self.routing=InlineParams();self.routing.changed.connect(self.changed);l.addWidget(self.routing)
        self.flow=label('','background:@hover@;border-radius:8px;padding:9px;color:@accent_ink@;');l.addWidget(self.flow)
        self.form=ParamTabs();self.form.changed.connect(self.changed);l.addWidget(self.form,1)

    def block_changed(self,index):
        data=self.block.tabData(index)
        if data:self.kind,self.slot=data
        self.signature=None;self.refresh()

    def address(self):
        return (2,1,0) if self.kind=='reverb' else (2,1,0x20) if self.kind=='chorus' else (2,1,0x40) if self.kind=='variation' else (3,self.slot,0) if self.kind=='insertion' else (2,0x40,0)

    def default_type(self):
        raw=self.app.session.initial_bytes(0x4c,self.address(),2)
        return tuple(raw) if raw else (1,0) if self.kind=='reverb' else (0x41,0) if self.kind=='chorus' else (5,0) if self.kind=='variation' else (0x49,0)

    def effect_value(self):
        raw=self.app.session.get_bytes(0x4c,self.address(),2)
        return tuple(raw) if raw is not None else self.default_type()

    def refresh(self):
        a=self.app;s=a.session;p=s.profile
        if self.block.property('model')!=p.name:
            self.block.blockSignals(True)
            while self.block.count():self.block.removeTab(0)
            if not p.native5:
                for name,kind,slot in [('Reverb','reverb',0),('Chorus','chorus',0),('Variation','variation',0)]+[(f'EFX {i+1}','insertion',i) for i in range(p.insertions)]+([('Multi EQ','eq',0)] if p.eq else []):
                    index=self.block.addTab(name);self.block.setTabData(index,(kind,slot))
            self.block.setProperty('model',p.name);self.block.blockSignals(False)
            if self.block.count():self.kind,self.slot=self.block.tabData(self.block.currentIndex())
            self.signature=None
        if p.native5:
            self.form.build([]);self.routing.build([]);self.type.setEnabled(False);self.raw_type.setEnabled(False);self.flow.setText('MU5系には、このエフェクトブロックはありません。');return
        value=self.effect_value();sig=(p.name,self.kind,self.slot,value if self.kind!='eq' else None)
        if self.signature!=sig:
            self.type.blockSignals(True);self.type.clear();self.effects=a.catalog.effects(p,self.kind) if self.kind!='eq' else []
            for fx in self.effects:self.type.addItem(f"{fx['name']}  [{fx['msb']:02X}:{fx['lsb']:02X}]",fx)
            selected=next((i for i,fx in enumerate(self.effects) if (fx['msb'],fx['lsb'])==value),-1)
            if selected<0 and self.kind!='eq':self.type.addItem(f'現在値 {value[0]:02X}:{value[1]:02X}',{'msb':value[0],'lsb':value[1],'name':'未定義タイプ','params':None});selected=self.type.count()-1
            self.type.setCurrentIndex(selected);self.type.blockSignals(False)
            params=self.make_params(self.type.currentData() or {})
            routes=[x for x in params if x.group=='接続・送り' or x.key=='eqtype']
            self.routing.build(routes);self.form.build([x for x in params if x not in routes]);self.signature=sig
        self.type.setVisible(self.kind!='eq');self.raw_type.setVisible(self.kind!='eq');self.raw_type.setEnabled(True);self.type.setEnabled(True)
        value_style(self.type,value!=self.default_type(),s.get_bytes(0x4c,self.address(),2) is None)
        self.form.refresh(s,self.address()[1]);self.routing.refresh(s,self.address()[1])
        if self.kind=='insertion':
            assignment=s.get(next(x for x in self.routing.params if x.key=='part'),self.slot)
            source=a.part_name(assignment) if assignment<p.parts else f'A/D {assignment-63}' if p.ad and assignment in (64,65) else ''
            route=f'{source} → EFX{self.slot+1} → 出力' if source else f'EFX{self.slot+1}：Off（割当なし）'
        elif self.kind=='variation':
            connection=next(x for x in self.routing.params if x.key=='connection')
            route='各PartのVariation → Variation → Return → 出力' if s.get(connection,1) else 'Insertion接続：選択した割当Partへ適用します。'
        else:route='各Part → システムエフェクト → Multi EQ → 出力'
        self.flow.setText(route)

    def make_params(self,fx):
        params=build_effect_parameters(self,fx);result=[];profile=self.app.session.profile
        for param in params:
            if param.key=='part':
                values=(127,*range(profile.parts),*((64,65) if profile.ad else ()))
                names=('Off',*(f'{chr(65+n//16)}{n%16+1}' for n in range(profile.parts)),*(('A/D 1','A/D 2') if profile.ad else ()))
                param=replace(param,label='割当Part',choices=tuple(names),choice_values=tuple(values))
            if param.key=='connection':param=replace(param,label='接続方式',choices=('Insertion','System'))
            result.append(param)
        return result

    def changed(self,param,value):
        self.app.edit(param,value,self.address()[1])

    def apply_type(self,*_):
        fx=self.type.currentData()
        if not fx or self.kind=='eq':return
        a=self.app;address=self.address();old=self.effect_value();new=(fx['msb'],fx['lsb'])
        if old==new:return
        if a.session.get_bytes(0x4c,address,2) is None:
            a.session.put(0x4c,address,old,'未取得 / 初期値',False);a.session.fields[(0x4c,*address)]=2
        a.session.checkpoint('エフェクト種類変更');a.session.invalidate_effect(address);a.session.put(0x4c,address,new);a.mark_changed()
        if a.can_send():a.send_messages([(0,change(address,new))],'エフェクト種類変更');self.read()
        self.signature=None;self.refresh()

    def direct_type(self):
        text,ok=QInputDialog.getText(self,'エフェクト番号を指定','Type MSB, LSB（16進数、各00～7F）',text='49, 00')
        if not ok:return
        try:
            msb,lsb=[int(x.strip(),16) for x in text.split(',')]
            if not 0<=msb<=127 or not 0<=lsb<=127:raise ValueError('番号は00～7Fで指定してください。')
            self.type.blockSignals(True);self.type.addItem(f'番号指定 {msb:02X}:{lsb:02X}',{'msb':msb,'lsb':lsb,'name':'番号指定','params':None});self.type.setCurrentIndex(self.type.count()-1);self.type.blockSignals(False);self.apply_type()
        except ValueError as exc:self.app.error(str(exc))

    def read(self):
        addr=self.address();blocks=[x for x in read_blocks(self.app.session.profile,False) if x[1][:2]==addr[:2]]
        self.app.read_addresses(blocks,'エフェクト取得')
