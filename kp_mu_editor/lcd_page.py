# SPDX-License-Identifier: GPL-3.0-or-later
# Adapted from KP Roland SC Editor, 干瓢碁 2026.
"""LCD editing for Yamaha MU modules."""
from pathlib import Path

from PySide6.QtCore import QRegularExpression, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QRegularExpressionValidator
from PySide6.QtWidgets import QHBoxLayout, QScrollArea, QVBoxLayout, QWidget

from .i18n import QFileDialog, QGroupBox, QLineEdit
from .lcd import LCD_MESSAGE_INTERVAL, LCD_SIZE, LCD_TEXT_LIMIT, lcd_bitmap, lcd_text
from .smf import embed_lcd_midi
from .theme import colors
from .widgets import button, label


class DotGrid(QWidget):
    changed = Signal()
    CELL = 13

    def __init__(self):
        super().__init__()
        self.pixels = set()
        self.last_cell = None
        self.drawing = False
        edges = LCD_SIZE * self.CELL + 1
        self.setFixedSize(edges, edges)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setAccessibleName("16×16")

    def replace(self, pixels):
        self.pixels = set(pixels)
        self.update()
        self.changed.emit()

    def paintEvent(self, _event):
        painter = QPainter(self)
        palette = colors()
        painter.fillRect(self.rect(), QColor(palette["graph_grid"]))
        background = QColor(palette["graph"])
        foreground = QColor(palette["graph_line"])
        for y in range(LCD_SIZE):
            for x in range(LCD_SIZE):
                painter.fillRect(x * self.CELL + 1, y * self.CELL + 1, self.CELL - 1, self.CELL - 1,
                                 foreground if (x, y) in self.pixels else background)

    def cell_at(self, position):
        x = int(position.x() // self.CELL)
        y = int(position.y() // self.CELL)
        if 0 <= x < LCD_SIZE and 0 <= y < LCD_SIZE:
            return x, y
        return None

    def paint_to(self, cell):
        x, y = self.last_cell
        dx, dy = cell[0] - x, cell[1] - y
        steps = max(abs(dx), abs(dy), 1)
        apply = self.pixels.add if self.drawing else self.pixels.discard
        count = len(self.pixels)
        for step in range(1, steps + 1):
            apply((round(x + dx * step / steps), round(y + dy * step / steps)))
        self.last_cell = cell
        if len(self.pixels) != count:
            self.update()
            self.changed.emit()

    def mousePressEvent(self, event):
        cell = self.cell_at(event.position())
        if event.button() == Qt.MouseButton.LeftButton and cell is not None:
            self.drawing = cell not in self.pixels
            self.last_cell = cell
            self.paint_to(cell)

    def mouseMoveEvent(self, event):
        if self.last_cell is not None and event.buttons() & Qt.MouseButton.LeftButton:
            cell = self.cell_at(event.position())
            if cell is not None:
                self.paint_to(cell)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.last_cell = None


class LCDPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.window = window
        page = QVBoxLayout(self)
        page.setContentsMargins(22, 16, 22, 16)
        page.setSpacing(8)
        page.addWidget(label("LCD編集", "font-size:23px;font-weight:700;color:@title@;"))
        page.addWidget(label("LCD表示は仕様書ベース・実機未確認です。", "color:@muted@;"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page.addWidget(scroll, 1)
        body = QWidget()
        scroll.setWidget(body)
        layout = QHBoxLayout(body)
        layout.setContentsMargins(0, 0, 10, 0)
        layout.setSpacing(16)

        dot_group = QGroupBox("ドット絵（16×16）")
        layout.addWidget(dot_group, 0, Qt.AlignmentFlag.AlignTop)
        dot_layout = QVBoxLayout(dot_group)
        self.grid = DotGrid()
        dot_layout.addWidget(self.grid)

        controls = QVBoxLayout()
        layout.addLayout(controls, 1)
        text_group = QGroupBox("文字表示")
        controls.addWidget(text_group)
        text_layout = QVBoxLayout(text_group)
        text_row = QHBoxLayout()
        text_layout.addLayout(text_row)
        self.text = QLineEdit()
        self.text.setMaxLength(LCD_TEXT_LIMIT)
        char_pattern = QRegularExpression(r"[ -~]{0," + str(LCD_TEXT_LIMIT) + "}")
        self.text.setValidator(QRegularExpressionValidator(char_pattern, self.text))
        self.text.setPlaceholderText("半角英数字・記号を32文字まで")
        text_row.addWidget(self.text, 1)
        self.text_count = label("")
        self.text_count.setMinimumWidth(44)
        text_row.addWidget(self.text_count)
        self.clear_text = button("文字欄を消去", self.text.clear)
        self.send_text = button("文字を送信", lambda: self.send(True, False))
        text_actions = QHBoxLayout()
        text_actions.addStretch()
        text_actions.addWidget(self.clear_text)
        text_actions.addWidget(self.send_text)
        text_layout.addLayout(text_actions)

        controls.addWidget(label("クリックで反転。ドラッグで続けて描画できます。", "color:@muted@;"))
        self.clear_dots = button("ドット絵を消去", lambda: self.grid.replace(()))
        self.send_dots = button("ドット絵を送信", lambda: self.send(False, True))
        self.send_both = button("文字とドット絵を送信", lambda: self.send(True, True), primary=True)
        dot_actions = QHBoxLayout()
        dot_actions.addWidget(self.clear_dots)
        dot_actions.addWidget(self.send_dots)
        dot_actions.addStretch()
        controls.addLayout(dot_actions)
        controls.addWidget(self.send_both, 0, Qt.AlignmentFlag.AlignLeft)
        controls.addStretch()
        actions = QHBoxLayout()
        self.target = label("", "color:@muted@;")
        actions.addWidget(self.target, 1)
        self.embed_button = button("MIDIに組み込む", self.embed)
        actions.addWidget(self.embed_button)
        page.addLayout(actions)

        self.text.textChanged.connect(self.refresh)
        self.grid.changed.connect(self.refresh)
        self.refresh()

    def refresh(self):
        app = self.window
        has_text = bool(self.text.text()) and self.text.hasAcceptableInput()
        has_dots = bool(self.grid.pixels)
        supported = app.session.profile.lcd
        live = supported and app.can_send()
        self.text_count.setText(f"{len(self.text.text())} / {LCD_TEXT_LIMIT}")
        if not supported:
            self.target.setText("選択機種はLCD表示の送信対象外です。")
        elif not app.engine.connected:
            self.target.setText("本体へ表示するにはMIDI出力Aを接続してください。")
        elif not app.device_matches():
            self.target.setText("選択機種と検出した本体を確認してください。")
        else:
            self.target.setText("LCD表示の送信先はMIDI出力Aです。")
        self.clear_text.setEnabled(bool(self.text.text()))
        self.clear_dots.setEnabled(has_dots)
        self.send_text.setEnabled(live and has_text)
        self.send_dots.setEnabled(live)
        self.send_both.setEnabled(live and has_text)
        self.embed_button.setEnabled(has_text or has_dots)

    def packets(self, characters, dots):
        device = self.window.engine.device
        packets = []
        if characters:
            packets.append(lcd_text(self.text.text(), device))
        if dots:
            packets.append(lcd_bitmap(self.grid.pixels, device))
        return packets

    def send(self, characters, dots):
        app = self.window
        if not app.session.profile.lcd or not app.can_send():
            return
        try:
            messages = [(0, raw) for raw in self.packets(characters, dots)]
            app.send_messages(messages, "LCD表示の送信", interval=LCD_MESSAGE_INTERVAL)
            app.status("LCD表示データを送信中…")
        except ValueError as exc:
            app.error(str(exc))

    def embed(self):
        app = self.window
        filename, _ = QFileDialog.getOpenFileName(
            self, "LCD表示を組み込むMIDIを選択", str(app.midi_file or app.data_dir), "MIDI (*.mid *.midi)")
        if not filename:
            return
        source = Path(filename)
        suggested = source.with_name(f"{source.stem}-LCD.mid")
        filename, _ = QFileDialog.getSaveFileName(
            self, "LCD表示を組み込んだMIDIを保存", str(suggested), "MIDI (*.mid *.midi)")
        if not filename:
            return
        destination = Path(filename)
        if destination.suffix.lower() not in (".mid", ".midi"):
            destination = destination.with_suffix(".mid")
        try:
            raw = self.packets(bool(self.text.text()), bool(self.grid.pixels))
            embed_lcd_midi(source, destination, raw)
        except (OSError, ValueError, EOFError, RuntimeError) as exc:
            app.error(str(exc))
            return
        app.select_midi_file(destination)
        app.status("LCD表示を組み込んだMIDIを選択しました。")
