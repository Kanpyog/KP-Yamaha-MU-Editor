"""MU LCD inspired colors shared by native controls and custom drawings."""
from pathlib import Path
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QTableWidget
from PySide6.QtCore import Qt

LIGHT = dict(
    window='#f3f5f0', surface='#ffffff', input='#ffffff', raised='#e9ede3',
    alternate='#f7f9f3', text='#293226', title='#26341b', muted='#67735e',
    unknown='#8b9680', disabled='#8d9686', border='#d5ddcd', hover='#edf4d7',
    accent='#badc43', accent_hover='#c9e762', accent_pressed='#a8cc2e',
    accent_text='#25300e', accent_ink='#516c18', selection='#dfedb6',
    selected_text='#293b13', modified='#486313', nav='#1a2016', nav_text='#ccd4c2',
    nav_muted='#8e9d7f', nav_hover='#303c23', nav_selected='#c1df58',
    graph='#edf2e5', graph_grid='#d0dabb', graph_line='#658b16', graph_eg='#927237',
    danger='#a22b35', danger_bg='#fff3f3', danger_border='#d9a9ad',
    lcd='#edf5cf', lcd_text='#405719', lcd_border='#c7d997',
    key_light='#ffffff', key_light_text='#293226', key_dark='#30372b', key_dark_text='#ecf1e5',
)
DARK = dict(
    window='#171b15', surface='#21271d', input='#191e16', raised='#2b3325',
    alternate='#252c20', text='#e2e9d8', title='#eff5e6', muted='#a8b59a',
    unknown='#879779', disabled='#718064', border='#3d4933', hover='#344128',
    accent='#c1e64c', accent_hover='#d1ef78', accent_pressed='#accf34',
    accent_text='#202a0d', accent_ink='#c6e86b', selection='#3f532b',
    selected_text='#eff8df', modified='#c4e76b', nav='#10150d', nav_text='#becbb0',
    nav_muted='#839573', nav_hover='#2b3820', nav_selected='#c1e64c',
    graph='#1c2416', graph_grid='#3a4a2d', graph_line='#c1e64c', graph_eg='#e0bc72',
    danger='#ffb0ac', danger_bg='#382324', danger_border='#885251',
    lcd='#28351a', lcd_text='#d3ee85', lcd_border='#536b30',
    key_light='#d3dbc9', key_light_text='#283120', key_dark='#11180c', key_dark_text='#b7c7a8',
)
PALETTES = {'light': LIGHT, 'dark': DARK}
CELL_THEME_ROLE = Qt.ItemDataRole.UserRole + 21


def colors():
    app = QApplication.instance()
    return PALETTES.get(app.property('mu_theme') if app else 'light', LIGHT)


def resolve(template, palette=None):
    for key, value in (palette or colors()).items():
        template = template.replace('@'+key+'@', value)
    return template


def style_widget(widget, template):
    widget.setProperty('mu_style_template', template)
    style = resolve(template)
    if widget.styleSheet() != style:
        widget.setStyleSheet(style)


QSS = '''
QMainWindow,QDialog { background:@window@; }
QWidget { font-family:"Yu Gothic UI","Segoe UI";font-size:13px;color:@text@; }
QMenuBar,QMenu { background:@surface@; }
QMenu::item:selected,QMenuBar::item:selected { background:@selection@;color:@selected_text@; }
QToolTip { background:@raised@;color:@text@;border:1px solid @border@;padding:5px; }
QPushButton { background:@surface@;border:1px solid @border@;border-radius:6px;padding:8px 12px;min-height:17px; }
QPushButton:hover { background:@hover@;border-color:@accent_ink@; }
QPushButton:pressed,QPushButton:checked { background:@selection@; }
QPushButton[primary="true"] { background:@accent@;color:@accent_text@;border-color:@accent@;font-weight:700; }
QPushButton[primary="true"]:hover { background:@accent_hover@; }
QPushButton[primary="true"]:pressed { background:@accent_pressed@; }
QPushButton:disabled { color:@disabled@;background:@raised@;border-color:@border@; }
QLineEdit,QComboBox,QSpinBox,QTextEdit,QPlainTextEdit { background:@input@;border:1px solid @border@;border-radius:5px;padding:6px;selection-background-color:@selection@;selection-color:@selected_text@; }
QLineEdit:focus,QComboBox:focus,QSpinBox:focus { border-color:@accent_ink@; }
QLineEdit:disabled,QComboBox:disabled,QSpinBox:disabled { color:@disabled@;background:@raised@; }
QComboBox { min-height:20px;padding-right:22px; }
QComboBox QAbstractItemView { background:@surface@;color:@text@;selection-background-color:@selection@;selection-color:@selected_text@;outline:0; }
QSpinBox { min-height:19px; }
QComboBox[compact="true"],QSpinBox[compact="true"] { min-height:16px;padding:2px 18px 2px 5px; }
QTableWidget { background:@surface@;alternate-background-color:@alternate@;border:1px solid @border@;border-radius:8px;selection-background-color:@selection@;selection-color:@selected_text@; }
QTableWidget QTableCornerButton::section { background:@raised@;border:0; }
QHeaderView::section { background:@raised@;border:0;border-bottom:1px solid @border@;padding:9px 7px;color:@muted@;font-weight:600; }
QTableWidget::item { padding:5px; }
QTabWidget::pane { background:@surface@;border:1px solid @border@;border-radius:7px; }
QTabBar::tab { background:@raised@;padding:10px 15px;margin-right:3px;border-top-left-radius:6px;border-top-right-radius:6px; }
QTabBar::tab:selected { background:@surface@;color:@accent_ink@;font-weight:700; }
QTabBar::tab:hover:!selected { background:@hover@; }
QScrollArea { border:0;background:@surface@; }
QScrollArea>QWidget>QWidget { background:@surface@; }
QGroupBox { background:@surface@;border:1px solid @border@;border-radius:8px;margin-top:12px;padding-top:15px; }
QGroupBox::title { subcontrol-origin:margin;left:12px;padding:0 5px; }
QCheckBox { spacing:7px; }
QLabel:disabled,QCheckBox:disabled { color:@disabled@; }
QStatusBar { background:@raised@; }
QProgressBar { border:0;background:@border@;border-radius:4px;height:9px; }
QProgressBar::chunk { background:@accent@;border-radius:4px; }
QWidget#header { background:@surface@;border-bottom:1px solid @border@; }
QWidget#navigationPanel,QListWidget#navigation { background:@nav@; }
QListWidget#navigation { color:@nav_text@;border:0;outline:0;padding-top:12px;font-size:14px; }
QListWidget#navigation::item { margin:3px 10px;padding:13px 12px;border-radius:7px; }
QListWidget#navigation::item:selected { color:@accent_text@;background:@nav_selected@;font-weight:700; }
QListWidget#navigation::item:hover:!selected { background:@nav_hover@; }
QWidget#footer { background:@raised@; }
QWidget#sysexPanel { background:@lcd@;border:1px solid @lcd_border@;border-radius:7px; }
QWidget#sysexPanel QLabel { color:@accent_ink@;background:transparent;border:0; }
QLineEdit#lastSysex { background:transparent;color:@lcd_text@;border:0;padding:2px 0;font-family:Consolas,"Cascadia Mono",monospace;font-size:12px; }
QScrollBar:vertical { background:@raised@;width:12px;margin:0; }
QScrollBar:horizontal { background:@raised@;height:12px;margin:0; }
QScrollBar::handle:vertical,QScrollBar::handle:horizontal { background:@border@;border-radius:5px;min-height:24px;min-width:24px; }
QScrollBar::add-line,QScrollBar::sub-line { width:0;height:0; }
QScrollBar::add-page,QScrollBar::sub-page { background:transparent; }
QSplitter::handle { background:@window@; }
QSpinBox::up-button { subcontrol-origin:border;subcontrol-position:top right;width:21px;border-left:1px solid @border@;border-bottom:1px solid @border@;border-top-right-radius:5px;background:@raised@; }
QSpinBox::down-button { subcontrol-origin:border;subcontrol-position:bottom right;width:21px;border-left:1px solid @border@;border-bottom-right-radius:5px;background:@raised@; }
QSpinBox::up-arrow { image:url(ASSETS/upARROW.svg);width:10px;height:8px; }
QSpinBox::down-arrow { image:url(ASSETS/downARROW.svg);width:10px;height:8px; }
/* Qt 6.12 clips the edit field when hidden spin buttons are right-aligned. */
DragSpinBox::up-button,DragSpinBox::down-button { subcontrol-position:center; }
QComboBox::drop-down { subcontrol-origin:padding;subcontrol-position:top right;width:22px;border:0; }
QComboBox::down-arrow { image:url(ASSETS/downARROW.svg);width:10px;height:8px; }
QCheckBox::indicator,QAbstractItemView::indicator { width:14px;height:14px;background:@input@;border:1px solid @muted@;border-radius:3px; }
QCheckBox::indicator:checked,QAbstractItemView::indicator:checked { background:@accent@;border-color:@accent@;image:url(ASSETS/check_lcd.svg); }
'''


def stylesheet(theme='light'):
    palette = PALETTES.get(theme, LIGHT)
    assets = (Path(__file__).parent/'data').as_posix()
    return resolve(QSS, palette).replace('ASSETS', assets).replace('ARROW', '_dark' if theme=='dark' else '')


STYLE = stylesheet()


def configure_application(app, theme='light'):
    theme = theme if theme in PALETTES else 'light'
    if app.property('mu_theme')==theme and app.property('mu_theme_ready'):
        return
    p = PALETTES[theme]
    if app.style().objectName().lower()!='fusion':app.setStyle('Fusion')
    app.setProperty('mu_theme', theme)
    palette = QPalette()
    roles = {'Window':'window','WindowText':'text','Base':'input','AlternateBase':'alternate',
             'Text':'text','Button':'surface','ButtonText':'text','Highlight':'selection',
             'HighlightedText':'selected_text','ToolTipBase':'raised','ToolTipText':'text',
             'Light':'surface','Midlight':'raised','Dark':'border','Mid':'border','Shadow':'nav',
             'PlaceholderText':'unknown','Link':'accent_ink','LinkVisited':'accent_ink'}
    for role,key in roles.items():
        palette.setColor(getattr(QPalette.ColorRole,role),QColor(p[key]))
    for role in ('WindowText','Text','ButtonText'):
        palette.setColor(QPalette.ColorGroup.Disabled,getattr(QPalette.ColorRole,role),QColor(p['disabled']))
    app.setPalette(palette)
    app.setStyleSheet(stylesheet(theme))
    for widget in app.allWidgets():
        template = widget.property('mu_style_template')
        if template:style_widget(widget,template)
        if isinstance(widget,QTableWidget):
            # Recoloring items emits cellChanged unless signals are blocked.
            # A theme switch must never transmit parameter changes.
            blocked=widget.blockSignals(True)
            try:
                for row in range(widget.rowCount()):
                    for col in range(widget.columnCount()):
                        cell=widget.item(row,col)
                        state=cell.data(CELL_THEME_ROLE) if cell else None
                        if state is not None:
                            modified,unknown=state
                            cell.setForeground(QColor(p['modified' if modified else 'unknown' if unknown else 'text']))
            finally:widget.blockSignals(blocked)
        widget.update()
    app.setProperty('mu_theme_ready',True)
