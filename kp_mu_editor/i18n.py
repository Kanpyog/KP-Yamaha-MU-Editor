"""Live UI translations; canonical parameter names and MIDI data stay unchanged."""
from functools import lru_cache
from pathlib import Path
import json,re,weakref
from PySide6 import QtWidgets as W
from PySide6.QtCore import Qt,QLocale,QTranslator,QLibraryInfo
from PySide6.QtGui import QAction as NativeAction
from shiboken6 import isValid

_language='ja'
_bindings=weakref.WeakValueDictionary()
_qt_translator=None
_translations=json.loads((Path(__file__).parent/'data'/'i18n_en.json').read_text(encoding='utf-8'))
_japanese=re.compile(r'[\u3000-\u9fff\uff00-\uffef]')
_fragments=re.compile('|'.join(re.escape(s) for s in sorted(_translations,key=len,reverse=True)))


@lru_cache(maxsize=12000)
def tr(text):
    text=str(text)
    if _language!='en' or not _japanese.search(text):return text
    if text in _translations:return _translations[text]
    return _fragments.sub(lambda match:_translations[match.group()],text)


def language():return _language


def _register(obj):_bindings[id(obj)]=obj


def set_language(value,app=None):
    global _language,_qt_translator
    _language=value if value in ('ja','en') else 'ja';tr.cache_clear()
    if app is not None:
        if _qt_translator is not None:app.removeTranslator(_qt_translator);_qt_translator.deleteLater()
        _qt_translator=None
        if _language=='ja':
            translator=QTranslator(app)
            if translator.load('qtbase_ja',QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
                _qt_translator=translator;app.installTranslator(translator)
        QLocale.setDefault(QLocale(QLocale.Language.Japanese if _language=='ja' else QLocale.Language.English))
        app.setProperty('mu_language',_language)
    for obj in list(_bindings.values()):
        if isValid(obj):obj._retranslate()


class _LiveText:
    def _remember(self,key,text):
        if not hasattr(self,'_sources'):self._sources={}
        self._sources[key]=str(text);_register(self)

    def _set(self,method,text):
        self._remember(method,text);getattr(super(),method)(tr(text))

    def setText(self,text):self._set('setText',text)
    def setTitle(self,text):self._set('setTitle',text)
    def setToolTip(self,text):self._set('setToolTip',text)
    def setWindowTitle(self,text):self._set('setWindowTitle',text)
    def setPlaceholderText(self,text):self._set('setPlaceholderText',text)
    def setPrefix(self,text):self._set('setPrefix',text)
    def setSuffix(self,text):self._set('setSuffix',text)

    def _retranslate(self):
        blocked=self.blockSignals(True)
        try:
            for method,text in getattr(self,'_sources',{}).items():getattr(super(),method)(tr(text))
            self._translate_items()
        finally:self.blockSignals(blocked)
        if isinstance(self,W.QWidget):self.update()

    def _translate_items(self):pass


class QLabel(_LiveText,W.QLabel):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.setTextFormat(Qt.TextFormat.PlainText)
        if args and isinstance(args[0],str):self.setText(args[0])


class QPushButton(_LiveText,W.QPushButton):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if args and isinstance(args[0],str):self.setText(args[0])


class QCheckBox(_LiveText,W.QCheckBox):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if args and isinstance(args[0],str):self.setText(args[0])


class QGroupBox(_LiveText,W.QGroupBox):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if args and isinstance(args[0],str):self.setTitle(args[0])


class QDialog(_LiveText,W.QDialog):pass
class QSpinBox(_LiveText,W.QSpinBox):pass


class QLineEdit(_LiveText,W.QLineEdit):
    # Contents are user input / device data; only its placeholder is translated.
    def setText(self,text):W.QLineEdit.setText(self,str(text))


class QAction(_LiveText,NativeAction):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if args and isinstance(args[0],str):self.setText(args[0])


class QMenu(_LiveText,W.QMenu):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if args and isinstance(args[0],str):self.setTitle(args[0])


class QComboBox(_LiveText,W.QComboBox):
    source_role=Qt.ItemDataRole.UserRole+93
    def addItem(self,*args):
        super().addItem(*args);index=self.count()-1
        text=args[0] if isinstance(args[0],str) else args[1]
        self.setItemText(index,text)
    def addItems(self,texts):
        for text in texts:self.addItem(text)
    def setItemText(self,index,text):
        self.setItemData(index,str(text),self.source_role);_register(self)
        W.QComboBox.setItemText(self,index,tr(text))
    def setCurrentText(self,text):W.QComboBox.setCurrentText(self,tr(text))
    def sourceText(self):return self.itemData(self.currentIndex(),self.source_role) or self.currentText()
    def _translate_items(self):
        for i in range(self.count()):
            source=self.itemData(i,self.source_role)
            if source is not None:W.QComboBox.setItemText(self,i,tr(source))


class QTabWidget(_LiveText,W.QTabWidget):
    def addTab(self,widget,*args):
        index=super().addTab(widget,*args);widget.setProperty('mu_tab_source',str(args[-1]));_register(self)
        W.QTabWidget.setTabText(self,index,tr(args[-1]));return index
    def setTabText(self,index,text):
        self.widget(index).setProperty('mu_tab_source',str(text));_register(self)
        W.QTabWidget.setTabText(self,index,tr(text))
    def _translate_items(self):
        for i in range(self.count()):
            source=self.widget(i).property('mu_tab_source')
            if source is not None:W.QTabWidget.setTabText(self,i,tr(source))


class QTabBar(_LiveText,W.QTabBar):
    def __init__(self,*args,**kwargs):super().__init__(*args,**kwargs);self._tab_sources=[]
    def addTab(self,*args):
        index=super().addTab(*args);self._tab_sources.insert(index,str(args[-1]));_register(self)
        W.QTabBar.setTabText(self,index,tr(args[-1]));return index
    def removeTab(self,index):
        if 0<=index<len(self._tab_sources):self._tab_sources.pop(index)
        super().removeTab(index)
    def _translate_items(self):
        for i,source in enumerate(self._tab_sources):W.QTabBar.setTabText(self,i,tr(source))


class _LiveItem:
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs);self._sources={}
        if args and isinstance(args[0],str):self.setText(args[0])
    def setText(self,text):self._sources['setText']=str(text);_register(self);super().setText(tr(text))
    def setToolTip(self,text):self._sources['setToolTip']=str(text);_register(self);super().setToolTip(tr(text))
    def _retranslate(self):
        owner=self.tableWidget() if isinstance(self,W.QTableWidgetItem) else self.listWidget()
        blocked=owner.blockSignals(True) if owner is not None else False
        try:
            for method,source in self._sources.items():getattr(super(),method)(tr(source))
        finally:
            if owner is not None:owner.blockSignals(blocked)


class QTableWidgetItem(_LiveItem,W.QTableWidgetItem):pass
class QListWidgetItem(_LiveItem,W.QListWidgetItem):pass


class QListWidget(_LiveText,W.QListWidget):
    def addItem(self,item):super().addItem(QListWidgetItem(item) if isinstance(item,str) else item)
    def addItems(self,items):
        for item in items:self.addItem(item)


class QTableWidget(_LiveText,W.QTableWidget):
    def setHorizontalHeaderLabels(self,labels):
        for i,text in enumerate(labels):self.setHorizontalHeaderItem(i,QTableWidgetItem(str(text)))


class QFormLayout(W.QFormLayout):
    def addRow(self,*args):
        if args and isinstance(args[0],str):args=(QLabel(args[0]),*args[1:])
        return super().addRow(*args)
    def insertRow(self,index,*args):
        if args and isinstance(args[0],str):args=(QLabel(args[0]),*args[1:])
        return super().insertRow(index,*args)


class QMessageBox(W.QMessageBox):
    @staticmethod
    def question(parent,title,text,*args,**kwargs):return W.QMessageBox.question(parent,tr(title),tr(text),*args,**kwargs)
    @staticmethod
    def information(parent,title,text,*args,**kwargs):return W.QMessageBox.information(parent,tr(title),tr(text),*args,**kwargs)
    @staticmethod
    def warning(parent,title,text,*args,**kwargs):return W.QMessageBox.warning(parent,tr(title),tr(text),*args,**kwargs)


class QInputDialog(W.QInputDialog):
    @staticmethod
    def getText(parent,title,label,*args,**kwargs):return W.QInputDialog.getText(parent,tr(title),tr(label),*args,**kwargs)


class QFileDialog(W.QFileDialog):
    @staticmethod
    def getOpenFileName(parent=None,caption='',directory='',filter='',*args,**kwargs):
        return W.QFileDialog.getOpenFileName(parent,tr(caption),directory,tr(filter),*args,**kwargs)
    @staticmethod
    def getSaveFileName(parent=None,caption='',directory='',filter='',*args,**kwargs):
        return W.QFileDialog.getSaveFileName(parent,tr(caption),directory,tr(filter),*args,**kwargs)
