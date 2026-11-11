from PySide6.QtCore import Qt,Signal,QPointF,QObject
from PySide6.QtGui import QColor,QPainter,QPen,QPainterPath
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QSpinBox,
 QComboBox,QFormLayout,QScrollArea,QTabWidget,QStyledItemDelegate,QAbstractItemView,QTableWidget,QSizePolicy,QGridLayout,QDialog,QDialogButtonBox,QLayout)

from .theme import colors,style_widget,CELL_THEME_ROLE
from .i18n import (tr,QLabel,QPushButton,QSpinBox,QComboBox,QFormLayout,QTabWidget,QTableWidget,QDialog)

class ParameterGestures(QObject):
    started=Signal()
    finished=Signal()
GESTURES=ParameterGestures()

def button(text,fn,primary=False):
    widget=QPushButton(text)
    if primary:widget.setProperty('primary',True)
    widget.clicked.connect(fn)
    return widget

def label(text,style=''):
    widget=QLabel(text);widget.setWordWrap(True)
    widget.setAlignment(Qt.AlignmentFlag.AlignLeft|Qt.AlignmentFlag.AlignTop)
    widget.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Maximum)
    if style:style_widget(widget,style)
    return widget

def page(title,description):
    widget=QWidget();layout=QVBoxLayout(widget);layout.setContentsMargins(22,16,22,16);layout.setSpacing(12)
    layout.addWidget(label(title,'font-size:23px;font-weight:700;color:@title@;'))
    layout.addWidget(label(description,'color:@muted@;'))
    return widget,layout

def value_style(control,modified=False,unknown=False):
    control.setProperty('modified',bool(modified))
    control.setProperty('unknown',bool(unknown))
    color='@modified@' if modified else '@unknown@' if unknown else '@text@'
    style=f'QSpinBox,QSpinBox QLineEdit,QComboBox {{color:{color};font-weight:{700 if modified else 400};}}'
    style_widget(control,style)
    font=control.font()
    if font.bold()!=bool(modified):font.setBold(bool(modified));control.setFont(font)
    if isinstance(control,QSpinBox):
        child_font=control.lineEdit().font()
        if child_font.bold()!=bool(modified):child_font.setBold(bool(modified));control.lineEdit().setFont(child_font)

def style_cell(cell,session,param,index=0,drum_set=None):
    modified=session.is_modified(param,index,drum_set);origin=session.origin(param,index,drum_set)
    font=cell.font();font.setBold(modified);cell.setFont(font)
    unknown=origin.startswith('未取得');cell.setData(CELL_THEME_ROLE,(modified,unknown))
    cell.setForeground(QColor(colors()['modified' if modified else 'unknown' if unknown else 'text']))
    cell.setToolTip(f'{origin}\n起動時の値: {param.display(session.default_value(param,index,drum_set))}\n上下ドラッグで変更（Shift:細かく / Ctrl:速く）')

class DragSpinBox(QSpinBox):
    """Editable by typing, wheel or vertical drag, including the text area."""
    def __init__(self,parent=None):
        super().__init__(parent);self._press=None;self._dragging=False
        self.setKeyboardTracking(True);self.setAccelerated(True)
        self.setButtonSymbols(QSpinBox.ButtonSymbols.NoButtons)
        self.setFixedSize(140,34)
        editor=self.lineEdit()
        editor.setTextMargins(5,0,5,0)
        editor.installEventFilter(self)
        self.setToolTip('上下にドラッグして変更 / ダブルクリックで数値入力 / Shift:細かく / Ctrl:速く')
        self.setCursor(Qt.CursorShape.SizeVerCursor)

    def eventFilter(self,obj,event):
        from PySide6.QtCore import QEvent
        if obj is self.lineEdit():
            kind=event.type()
            if kind==QEvent.Type.MouseButtonPress and event.button()==Qt.MouseButton.LeftButton:
                self._press=(event.globalPosition().y(),self.value());self._dragging=False
            elif kind==QEvent.Type.MouseMove and self._press is not None and event.buttons()&Qt.MouseButton.LeftButton:
                delta=self._press[0]-event.globalPosition().y()
                if abs(delta)>=3 or self._dragging:
                    if not self._dragging:self._dragging=True;GESTURES.started.emit()
                    divisor=10 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else 3
                    multiplier=10 if event.modifiers()&Qt.KeyboardModifier.ControlModifier else 1
                    self.setValue(self._press[1]+int(delta/divisor)*multiplier*self.singleStep())
                    return True
            elif kind==QEvent.Type.MouseButtonRelease and self._press is not None:
                dragged=self._dragging;self._press=None;self._dragging=False
                if dragged:GESTURES.finished.emit();return True
        return super().eventFilter(obj,event)

def ask_number(parent,title,prompt,value,minimum,maximum):
    dialog=QDialog(parent);dialog.setWindowTitle(title);layout=QVBoxLayout(dialog);layout.addWidget(label(prompt))
    editor=DragSpinBox();editor.setRange(minimum,maximum);editor.setValue(value);layout.addWidget(editor)
    buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
    buttons.accepted.connect(dialog.accept);buttons.rejected.connect(dialog.reject);layout.addWidget(buttons)
    accepted=dialog.exec()==QDialog.DialogCode.Accepted
    return editor.value(),accepted

class ParameterTable(QTableWidget):
    def __init__(self,rows,columns):
        super().__init__(rows,columns);self._numeric_press=None;self.numeric_dragging=False

    def mousePressEvent(self,event):
        self._numeric_press=None
        if event.button()==Qt.MouseButton.LeftButton and not event.modifiers():
            index=self.indexAt(event.position().toPoint());spec=index.data(Qt.ItemDataRole.UserRole)
            if isinstance(spec,(tuple,list)) and len(spec)==2:
                try:self._numeric_press=(index.row(),index.column(),event.globalPosition().y(),int(index.data()),spec)
                except (ValueError,TypeError):pass
        super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self._numeric_press and event.buttons()&Qt.MouseButton.LeftButton:
            row,col,y,value,spec=self._numeric_press;delta=y-event.globalPosition().y()
            if abs(delta)>=3 or self.numeric_dragging:
                if not self.numeric_dragging:self.numeric_dragging=True;GESTURES.started.emit()
                divisor=10 if event.modifiers()&Qt.KeyboardModifier.ShiftModifier else 3
                multiplier=10 if event.modifiers()&Qt.KeyboardModifier.ControlModifier else 1
                new=max(spec[0],min(spec[1],value+int(delta/divisor)*multiplier))
                if self.item(row,col).text()!=str(new):self.item(row,col).setText(str(new))
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        dragged=self.numeric_dragging;self._numeric_press=None;self.numeric_dragging=False
        if dragged:GESTURES.finished.emit();return
        super().mouseReleaseEvent(event)

def table(headers):
    widget=ParameterTable(0,len(headers));widget.setHorizontalHeaderLabels(headers)
    widget.setAlternatingRowColors(True);widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    widget.verticalHeader().setVisible(False);widget.setShowGrid(False)
    widget.horizontalHeader().setStretchLastSection(True);widget.setWordWrap(False)
    widget.verticalHeader().setDefaultSectionSize(34)
    return widget

class NumericDelegate(QStyledItemDelegate):
    def createEditor(self,parent,option,index):
        spec=index.data(Qt.ItemDataRole.UserRole)
        if not spec:return super().createEditor(parent,option,index)
        editor=DragSpinBox(parent);editor.setRange(spec[0],spec[1])
        editor.setProperty('compact',True)
        editor.setMinimumWidth(0);editor.setMaximumWidth(16777215)
        editor.setMinimumHeight(0);editor.setMaximumHeight(16777215)
        editor.valueChanged.connect(lambda _:self.commitData.emit(editor))
        return editor

    def setEditorData(self,editor,index):
        if isinstance(editor,QSpinBox):
            editor.blockSignals(True)
            try:editor.setValue(int(index.data()))
            except (ValueError,TypeError):editor.setValue(0)
            font=index.data(Qt.ItemDataRole.FontRole);state=index.data(CELL_THEME_ROLE)
            value_style(editor,bool(font and font.bold()),bool(state and state[1]))
            editor.blockSignals(False)
        else:super().setEditorData(editor,index)

    def setModelData(self,editor,model,index):
        if isinstance(editor,QSpinBox):model.setData(index,str(editor.value()))
        else:super().setModelData(editor,model,index)

def parameter_editor(param,changed):
    if param.choices:
        editor=QComboBox()
        values=param.choice_values or tuple(range(len(param.choices)))
        for text,value in zip(param.choices,values):editor.addItem(str(text),value)
        editor.currentIndexChanged.connect(lambda _,p=param,c=editor:changed(p,c.currentData()) if c.currentData() is not None else None)
        editor.setMinimumWidth(140);editor.setMaximumWidth(240)
    else:
        editor=DragSpinBox();editor.setRange(param.minimum-param.offset,param.maximum-param.offset)
        editor.valueChanged.connect(lambda v,p=param:changed(p,v+p.offset))
    return editor

def refresh_editor(control,session,param,index=0,drum_set=None):
    control.blockSignals(True);value=session.get(param,index,drum_set)
    if isinstance(control,QComboBox):
        pos=control.findData(value)
        if pos<0:control.addItem(str(value),value);pos=control.count()-1
        control.setCurrentIndex(pos)
    elif not getattr(control,'_dragging',False):control.setValue(value-param.offset)
    origin=session.origin(param,index,drum_set)
    value_style(control,session.is_modified(param,index,drum_set),origin.startswith('未取得'))
    control.setToolTip(f'{param.label}\n{origin}\n起動時の値: {param.display(session.default_value(param,index,drum_set))}\n上下ドラッグで変更（Shift:細かく / Ctrl:速く）')
    control.blockSignals(False)

class ParamTabs(QTabWidget):
    changed=Signal(object,int)
    def __init__(self):
        super().__init__();self.controls={};self.params=[];self.forms={}

    def build(self,params):
        while self.count():self.widget(0).deleteLater();self.removeTab(0)
        self.controls={};self.params=params;self.forms={}
        for param in params:
            if param.group not in self.forms:
                container=QWidget();form=QFormLayout(container);form.setSpacing(10);form.setContentsMargins(18,18,18,18)
                form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.FieldsStayAtSizeHint)
                form.setFormAlignment(Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft)
                form.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
                scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(container)
                self.addTab(scroll,param.group);self.forms[param.group]=form
            editor=parameter_editor(param,self.changed.emit)
            self.forms[param.group].addRow(param.label,editor);self.controls[param.key]=editor
        for form in self.forms.values():
            form.invalidate();form.activate();form.parentWidget().setMinimumHeight(form.sizeHint().height())

    def fixed_sustain(self):
        if 'ADSR' in self.forms:
            self.sustain=QLabel('音色内固定（変更不可）');self.sustain.setEnabled(False)
            self.sustain.setToolTip('MUのパートEGには独立したSustain Levelパラメーターがありません。')
            self.forms['ADSR'].insertRow(min(2,self.forms['ADSR'].rowCount()),'Sustain',self.sustain)
            form=self.forms['ADSR'];form.invalidate();form.activate();form.parentWidget().setMinimumHeight(form.sizeHint().height())

    def refresh(self,session,index=0,drum_set=None):
        for param in self.params:refresh_editor(self.controls[param.key],session,param,index,drum_set)

class InlineParams(QWidget):
    changed=Signal(object,int)
    def __init__(self,columns=3):
        super().__init__();self.columns=columns;self.controls={};self.params=[];self.row=QGridLayout(self);self.row.setContentsMargins(0,0,0,0);self.row.setHorizontalSpacing(18);self.row.setVerticalSpacing(7)

    def build(self,params):
        while self.row.count():
            entry=self.row.takeAt(0)
            if entry.widget():entry.widget().deleteLater()
        self.controls={};self.params=params
        for number,param in enumerate(params):
            box=QWidget();layout=QVBoxLayout(box);layout.setContentsMargins(0,0,0,0);layout.setSpacing(3)
            layout.addWidget(label(param.label,'color:@muted@;font-size:11px;'))
            editor=parameter_editor(param,self.changed.emit);layout.addWidget(editor)
            self.controls[param.key]=editor;self.row.addWidget(box,number//self.columns,number%self.columns)
        self.row.setColumnStretch(self.columns,1)

    def refresh(self,session,index=0):
        for param in self.params:refresh_editor(self.controls[param.key],session,param,index)

class ToneGraph(QWidget):
    def __init__(self):
        super().__init__();self.setMinimumHeight(165);self.setMaximumHeight(205);self.values=(64,64,64,64,64,64)

    def envelope_points(self):
        _,_,_,attack,decay,release=self.values
        a=.035+.245*(max(0,min(127,attack))/127)**1.7
        d=.04+.19*(max(0,min(127,decay))/127)**1.7
        r=.035+.235*(max(0,min(127,release))/127)**1.7
        return [(0,0),(a,1),(a+d,.58),(.72,.58),(.72+r,0)]

    def filter_points(self):
        cutoff,res,hpf,*_=self.values
        result=[];cut=.10+.80*cutoff/127;hp=.02+.72*hpf/127
        for i in range(160):
            x=i/159
            high=1/(1+max(0,x-cut)*28)
            low=min(1,max(0,(x-hp+.08)*15))
            peak=max(0,res-64)/63*.30*max(0,1-abs(x-cut)/.06)
            result.append((x,min(1.15,.77*high*low+peak)))
        return result

    def paintEvent(self,event):
        palette=colors()
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(palette['graph']));p.drawRoundedRect(self.rect().adjusted(1,1,-1,-1),10,10)
        w,h=self.width(),self.height();left=(18,38,w*.43,h-73);right=(w*.53,38,w*.43,h-73)
        for x,y,ww,hh in (left,right):
            p.setPen(QPen(QColor(palette['graph_grid']),1))
            for k in range(5):p.drawLine(QPointF(x+ww*k/4,y),QPointF(x+ww*k/4,y+hh))
            p.drawLine(QPointF(x,y+hh),QPointF(x+ww,y+hh))
        p.setPen(QColor(palette['muted']));p.drawText(18,22,'FILTER  ·  LPF / HPF / Resonance')
        p.drawText(int(right[0]),22,tr('ADSR  ·  パラメーターに連動する相対カーブ'))
        for rect,points,color in ((left,self.filter_points(),palette['graph_line']),(right,self.envelope_points(),palette['graph_eg'])):
            x,y,ww,hh=rect;path=QPainterPath();path.moveTo(x+points[0][0]*ww,y+hh-points[0][1]*hh*.86)
            for xx,yy in points[1:]:path.lineTo(x+xx*ww,y+hh-yy*hh*.86)
            p.setPen(QPen(QColor(color),2.6));p.drawPath(path)
        p.setPen(QColor(palette['muted']));p.drawText(18,h-13,tr('低域 → 高域（相対表示）'))
        for name,(xx,yy) in zip(('','A','D / S','Note Off','R'),self.envelope_points()):
            p.drawText(QPointF(right[0]+xx*right[2]-8,right[1]+right[3]-yy*right[3]*.86-8),name)
        p.drawText(int(right[0]),h-13,tr('Sustain Level：音色内固定  ·  時間は相対表示'))
