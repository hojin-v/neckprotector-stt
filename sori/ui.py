from __future__ import annotations

import math
import sys
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal, QTimer, QPointF, QRectF, QSize, QUrl, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QColor, QPainter, QPen, QLinearGradient, QRadialGradient, QIcon, QPixmap, QFont, QFontDatabase, QDesktopServices
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QGridLayout, QScrollArea, QLineEdit, QComboBox, QDialog, QFormLayout, QCheckBox,
    QFileDialog, QDialogButtonBox, QStackedWidget, QSizePolicy, QListView, QProgressBar)
from sori.keybindings import DEFAULT_HOTKEY, SPECIAL_KEYS, hotkey_label, valid_hotkey


STYLE = """
QWidget { color: #27243b; font-size: 13px; }
QWidget#dashboard { background: #f8f7fb; }
QFrame#sidebar { background: #eeedf5; border-right: 1px solid #e3e0ee; }
QLabel#muted { color: #8b879d; }
QLabel#eyebrow { color: #938baf; font-size: 11px; font-weight: 700; }
QLabel#title { font-size: 27px; font-weight: 700; color: #27243b; }
QLabel#subtitle { color: #8b879d; font-size: 13px; }
QPushButton { border: 1px solid #e4e1ee; border-radius: 9px; padding: 9px 14px; background: #fff; color: #686176; font-weight: 600; }
QPushButton:hover { background: #f0edf9; border-color: #cec5e7; }
QPushButton:pressed { background: #e5ddf7; }
QPushButton:disabled { color: #b6b0c4; background: #f0edf4; }
QPushButton#primary { background: #8061cf; color: white; border: none; }
QPushButton#primary:hover { background: #6e50bd; }
QPushButton#nav { text-align: left; border: none; background: transparent; padding: 12px 17px; color: #817a94; }
QPushButton#nav:checked { background: #e1daf1; color: #7152b6; }
QFrame#card { background: white; border: 1px solid #e8e5f0; border-radius: 14px; }
QFrame#entry { background: white; border: 1px solid #e8e5f0; border-radius: 12px; }
QFrame#tip { background: #e7e1f3; border: none; border-radius: 12px; }
QLineEdit { border: 1px solid #e7e3ee; background: white; border-radius: 9px; padding: 10px 13px; color: #575066; }
QLineEdit:focus { border-color: #a38acb; }
QComboBox { background: white; border: 1px solid #e4e1ee; border-radius: 10px; padding: 9px 32px 9px 13px; min-height: 20px; }
QComboBox:hover { border-color: #bca8dc; background: #fcfbff; }
QComboBox:focus, QComboBox:on { border-color: #a38acb; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox::down-arrow { image: none; }
QListView#comboPopup { background: #fcfbff; color: #4c435c; border: 1px solid #ded5eb; padding: 6px; outline: none; selection-background-color: #ece5f7; selection-color: #634398; }
QListView#comboPopup::item { min-height: 30px; padding: 5px 11px; border-radius: 6px; margin: 1px 0; }
QListView#comboPopup::item:hover { background: #f0eaf8; }
QListView#comboPopup::item:selected { background: #e8dff5; color: #604091; }
QMenu { background: #fcfbff; border: 1px solid #ded5eb; padding: 6px; }
QMenu::item { padding: 8px 20px; border-radius: 6px; }
QMenu::item:selected { background: #e8dff5; }
QProgressBar { border: none; border-radius: 3px; background: #e7e1ef; max-height: 6px; }
QProgressBar::chunk { background: #8d70ce; border-radius: 3px; }
QScrollArea { border: none; background: transparent; }
QScrollArea > QWidget > QWidget { background: transparent; }
QScrollBar:vertical { background: transparent; width: 6px; margin: 4px 0; }
QScrollBar::handle:vertical { background: #d6cfe4; border-radius: 3px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QDialog { background: #f8f7fb; }
QCheckBox { spacing: 10px; }
QCheckBox::indicator { width: 18px; height: 18px; }
"""


def configure_appearance(application):
    """Use an installed CJK font instead of relying on unsupported CSS fallback lists."""
    families = set(QFontDatabase.families())
    preferred = {"win32": ["Malgun Gothic", "맑은 고딕"], "darwin": ["Apple SD Gothic Neo"]}.get(sys.platform, [])
    preferred += ["Noto Sans CJK KR", "Noto Sans KR", "NanumGothic"]
    family = next((name for name in preferred if name in families), application.font().family())
    font = QFont(family, 10)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    application.setFont(font)
    application.setStyle("Fusion")
    application.setStyleSheet(STYLE)


class SoftComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        view = QListView()
        view.setObjectName("comboPopup")
        view.setSpacing(1)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setView(view)
        self.setMaxVisibleItems(8)
        self.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(8)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor("#9784b3"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        x, y = self.width() - 18, self.height() / 2
        painter.drawPolyline([QPointF(x - 4, y - 2), QPointF(x, y + 2), QPointF(x + 4, y - 2)])
        painter.end()


def label(text, name="", wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setObjectName(name)
    widget.setWordWrap(wrap)
    return widget


def icon(name: str, color="#8e82ac", size=22) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 24, size / 24)
    painter.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    if name == "mic":
        painter.drawRoundedRect(QRectF(8.5, 3, 7, 12), 3.5, 3.5)
        painter.drawArc(QRectF(5, 6, 14, 13), 180 * 16, 180 * 16)
        painter.drawLine(QPointF(12, 19), QPointF(12, 22))
    elif name == "history":
        painter.drawRoundedRect(QRectF(5, 3, 14, 18), 2, 2)
        for y in (8, 12, 16):
            painter.drawLine(QPointF(9, y), QPointF(15, y))
    elif name == "settings":
        painter.drawEllipse(QRectF(4, 4, 16, 16))
        painter.drawEllipse(QRectF(9, 9, 6, 6))
        for a in range(0, 360, 45):
            t = math.radians(a)
            painter.drawLine(QPointF(12 + 8 * math.cos(t), 12 + 8 * math.sin(t)), QPointF(12 + 10 * math.cos(t), 12 + 10 * math.sin(t)))
    elif name == "folder":
        painter.drawPolyline([QPointF(3, 7), QPointF(3, 20), QPointF(21, 20), QPointF(21, 7), QPointF(12, 7), QPointF(9, 4), QPointF(3, 4), QPointF(3, 7)])
    elif name == "copy":
        painter.drawRoundedRect(QRectF(8, 8, 12, 13), 2, 2)
        painter.drawPolyline([QPointF(15, 4), QPointF(4, 4), QPointF(4, 16)])
    elif name == "close":
        painter.drawLine(QPointF(7, 7), QPointF(17, 17))
        painter.drawLine(QPointF(17, 7), QPointF(7, 17))
    elif name == "arrow":
        painter.drawLine(QPointF(4, 12), QPointF(19, 12))
        painter.drawPolyline([QPointF(14, 7), QPointF(19, 12), QPointF(14, 17)])
    elif name == "logo":
        painter.setPen(QPen(QColor(color), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for x, height in [(4, 6), (9, 14), (14, 20), (19, 10)]:
            painter.drawLine(QPointF(x, 12 - height / 2), QPointF(x, 12 + height / 2))
    painter.end()
    return QIcon(pixmap)


def button(text, image=None, name="", callback=None):
    widget = QPushButton(text)
    widget.setObjectName(name)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if image:
        widget.setIcon(icon(image))
        widget.setIconSize(QSize(19, 19))
    if callback:
        widget.clicked.connect(callback)
    return widget


class VoiceCanvas(QWidget):
    clicked = Signal()

    def __init__(self, compact=False):
        super().__init__()
        self.compact = compact
        self.active = False
        self.phase = 0
        self.level = 0
        self.smoothed_level = 0
        self.setMinimumSize(160 if compact else 260, 90 if compact else 190)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("받아쓰기 시작 / 중단")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.animate)
        self.timer.start(50)

    def animate(self):
        if self.isVisible():
            self.phase += 0.1
            target = self.level if self.active else 0
            self.smoothed_level += (target - self.smoothed_level) * 0.35
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() / 2
        if self.compact:
            self.paint_compact(painter, cx, cy)
            painter.end()
            return
        glow = QRadialGradient(QPointF(cx, cy), 105)
        glow.setColorAt(0, QColor(136, 105, 215, 55 if self.active else 25))
        glow.setColorAt(1, QColor(136, 105, 215, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), 106, 90)
        for radius in (57, 72, 89):
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor(166, 145, 207, 45 if self.compact else 65), 1))
            painter.drawEllipse(QPointF(cx, cy), radius, radius)
        for side in (-1, 1):
            for i in range(13):
                x = cx + side * (104 + i * 7)
                envelope = math.sin((i + 1) / 14 * math.pi)
                activity = self.smoothed_level if self.active else 0
                height = 4 + envelope * 65 * activity * (0.35 + 0.65 * abs(math.sin(self.phase + i * 0.65)))
                painter.setPen(QPen(QColor(180, 159, 221, max(35, 155 - i * 6)), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(x, cy - height / 2), QPointF(x, cy + height / 2))
        gradient = QLinearGradient(cx - 45, cy - 45, cx + 45, cy + 45)
        gradient.setColorAt(0, QColor("#bc9ceb"))
        gradient.setColorAt(1, QColor("#8661cd"))
        painter.setPen(QPen(QColor("#d4b8fa"), 1))
        painter.setBrush(gradient)
        painter.drawEllipse(QPointF(cx, cy), 43, 43)
        if self.active:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor("#faf6ff"))
            painter.drawRoundedRect(QRectF(cx - 10, cy - 10, 20, 20), 5, 5)
        else:
            painter.drawPixmap(round(cx - 17), round(cy - 20), icon("mic", "#faf6ff", 34).pixmap(34, 34))
        painter.end()

    def paint_compact(self, painter, cx, cy):
        # The halo signals capture; waveform height is driven only by measured RMS.
        level = self.smoothed_level
        pulse = (1 + math.sin(self.phase * 1.8)) / 2 if self.active else 0
        glow = QRadialGradient(QPointF(cx, cy), 48)
        glow.setColorAt(0, QColor(91, 208, 249, round(48 + 55 * level + 15 * pulse)))
        glow.setColorAt(1, QColor(66, 188, 237, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QPointF(cx, cy), 48, 45)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(175, 231, 255, round(55 + 65 * pulse)), 1))
        radius = 36 + 2 * pulse + 3 * level
        painter.drawEllipse(QPointF(cx, cy), radius, radius)
        for side in (-1, 1):
            for i in range(7):
                x = cx + side * (51 + i * 6)
                envelope = math.sin((i + 1) / 8 * math.pi)
                height = 3 + envelope * 40 * level * (0.4 + 0.6 * abs(math.sin(self.phase * 2 + i * 0.7)))
                color = QColor(174, 229, 249, 160 if self.active else 50)
                painter.setPen(QPen(color, 2.2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                painter.drawLine(QPointF(x, cy - height / 2), QPointF(x, cy + height / 2))
        gradient = QLinearGradient(cx - 26, cy - 31, cx + 25, cy + 31)
        gradient.setColorAt(0, QColor("#b9efff"))
        gradient.setColorAt(0.4, QColor("#62d2f4"))
        gradient.setColorAt(1, QColor("#3aa9df"))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(218, 248, 255, 200), 1))
        painter.drawEllipse(QPointF(cx, cy), 31, 31)
        highlight = QRadialGradient(QPointF(cx - 12, cy - 18), 33)
        highlight.setColorAt(0, QColor(255, 255, 255, 100))
        highlight.setColorAt(1, QColor(255, 255, 255, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(highlight)
        painter.drawEllipse(QPointF(cx, cy), 30, 30)
        if self.active:
            painter.setBrush(QColor("#154b60"))
            painter.drawRoundedRect(QRectF(cx - 8, cy - 8, 16, 16), 4, 4)
        else:
            painter.drawPixmap(round(cx - 15), round(cy - 16), icon("mic", "#154b60", 30).pixmap(30, 30))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()


class FloatingPanel(QWidget):
    hidden_by_user = Signal()
    toggle = Signal()
    open_history = Signal()
    open_settings = Signal()

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint |
                            Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setFixedSize(310, 174)
        self.setWindowTitle("소리 · 음성 입력")
        self.setWindowIcon(icon("logo", "#a786df", 64))
        self.drag_position = None
        self.fade = QPropertyAnimation(self, b"windowOpacity", self)
        self.fade.setDuration(180)
        self.fade.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade.finished.connect(lambda: self.hide() if self.windowOpacity() < 0.1 else None)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 13, 20, 13)
        layout.setSpacing(0)
        header = QHBoxLayout()
        header.setSpacing(3)
        for image, tooltip, callback in [("settings", "설정 · 마이크 테스트", self.open_settings.emit), ("history", "기록 화면", self.open_history.emit)]:
            control = self.glass_control(image, tooltip, callback)
            header.addWidget(control)
        header.addStretch()
        handle = QFrame()
        handle.setFixedSize(34, 3)
        handle.setStyleSheet("background: rgba(222, 242, 249, 95); border-radius: 1px;")
        handle.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        header.addWidget(handle)
        header.addStretch()
        header.addSpacing(25)
        close = self.glass_control("close", "패널 숨기기", self.hide_by_user)
        header.addWidget(close)
        layout.addLayout(header)
        self.voice = VoiceCanvas(True)
        self.voice.setFixedHeight(88)
        self.voice.clicked.connect(self.toggle)
        layout.addWidget(self.voice)
        self.status = label("목소리를 들려주세요")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet("color: #f1f9fd; font-size: 12px; font-weight: 600;")
        layout.addWidget(self.status)
        layout.addSpacing(3)
        self.hint = label(f"{DEFAULT_HOTKEY}을 눌러 시작 · 다시 눌러 마치기")
        self.hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.hint.setStyleSheet("color: #aac4d0; font-size: 10px;")
        layout.addWidget(self.hint)
        self.engine_label = label("●  Qwen3 ASR · 0.6B")
        self.engine_label.hide()
        for child in self.findChildren(QPushButton):
            child.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def glass_control(self, image, tooltip, callback):
        control = button("", callback=callback)
        control.setIcon(icon(image, "#d7eaf2", 19))
        control.setFixedSize(25, 25)
        control.setToolTip(tooltip)
        control.setStyleSheet("QPushButton {border: none; border-radius: 7px; background: transparent; padding: 0;} QPushButton:hover {background: rgba(225, 245, 255, 25);}")
        return control

    def hide_by_user(self):
        self.hide()
        self.hidden_by_user.emit()

    def reveal(self):
        self.fade.stop()
        self.setWindowOpacity(1.0)
        self.show()
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            position = ctypes.windll.user32.SetWindowPos
            position.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT]
            position.restype = wintypes.BOOL
            position(int(self.winId()), -1, 0, 0, 0, 0, 0x0053)  # TOPMOST, NOACTIVATE, SHOWWINDOW
        else:
            self.raise_()
        self.setWindowOpacity(0.05)
        self.fade.setStartValue(0.05)
        self.fade.setEndValue(1.0)
        self.fade.start()

    def dismiss(self):
        self.fade.stop()
        self.fade.setStartValue(self.windowOpacity())
        self.fade.setEndValue(0.0)
        self.fade.start()

    def nativeEvent(self, event_type, message):
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes
            native = wintypes.MSG.from_address(int(message))
            if native.message == 0x0021:  # WM_MOUSEACTIVATE: don't steal the input application's focus.
                return True, 3
        return super().nativeEvent(event_type, message)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for spread in range(6, 0, -1):
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(16, 9, 31, 3))
            painter.drawRoundedRect(QRectF(6 - spread / 2, 6 - spread / 2, self.width() - 12 + spread, self.height() - 12 + spread), 24, 24)
        gradient = QLinearGradient(0, 0, self.width(), self.height())
        gradient.setColorAt(0, QColor(42, 73, 91, 232))
        gradient.setColorAt(0.45, QColor(23, 47, 64, 225))
        gradient.setColorAt(1, QColor(24, 43, 60, 242))
        painter.setBrush(gradient)
        painter.setPen(QPen(QColor(189, 225, 241, 75), 1))
        painter.drawRoundedRect(QRectF(6, 6, self.width() - 12, self.height() - 12), 22, 22)
        # A soft edge highlight and reflected light preserve contrast on any desktop.
        sheen = QLinearGradient(0, 7, 0, 85)
        sheen.setColorAt(0, QColor(232, 249, 255, 30))
        sheen.setColorAt(1, QColor(232, 249, 255, 0))
        painter.setBrush(sheen)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(QRectF(7, 7, self.width() - 14, 110), 21, 21)
        edge = QLinearGradient(15, 0, self.width() - 15, 0)
        edge.setColorAt(0, QColor(222, 246, 255, 0))
        edge.setColorAt(0.3, QColor(222, 246, 255, 110))
        edge.setColorAt(1, QColor(222, 246, 255, 0))
        painter.setPen(QPen(edge, 1))
        painter.drawLine(24, 7, self.width() - 24, 7)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self.drag_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_position)

    def mouseReleaseEvent(self, event):
        self.drag_position = None


class Dashboard(QWidget):
    close_requested = Signal()
    open_settings = Signal()
    open_panel = Signal()
    copy_text = Signal(str)
    export = Signal()
    prepare = Signal()
    exit_app = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("dashboard")
        self.setWindowTitle("소리 — 목소리가 기록이 되는 순간")
        self.setWindowIcon(icon("logo", "#8061cf", 64))
        self.resize(1110, 780)
        self.setMinimumSize(930, 680)
        self.store = None
        self.selected_day = datetime.now().astimezone().date().isoformat()
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(208)
        left = QVBoxLayout(sidebar)
        left.setContentsMargins(22, 34, 22, 24)
        left.setSpacing(12)
        brand = QHBoxLayout()
        mark = label("")
        mark.setPixmap(icon("logo", "#8161ce", 32).pixmap(32, 32))
        brand.addWidget(mark)
        brand.addWidget(label("소리", "title"))
        brand.addStretch()
        left.addLayout(brand)
        left.addWidget(label("YOUR VOICE, WRITTEN.", "eyebrow"))
        left.addSpacing(36)
        left.addWidget(label("WORKSPACE", "eyebrow"))
        history = button("  나의 기록", "history", "nav")
        history.setCheckable(True)
        history.setChecked(True)
        history.clicked.connect(lambda: history.setChecked(True))
        left.addWidget(history)
        left.addWidget(button("  음성 입력 패널", "mic", "nav", self.open_panel.emit))
        left.addWidget(button("  설정", "settings", "nav", self.open_settings.emit))
        left.addStretch()
        tip = QFrame()
        tip.setObjectName("tip")
        tips = QVBoxLayout(tip)
        tips.setContentsMargins(15, 18, 15, 18)
        tips.addWidget(label("작은 생각도 놓치지 않게", wrap=True))
        tips.addSpacing(4)
        self.sidebar_hint = label(f"{DEFAULT_HOTKEY}을 누르고\n떠오르는 대로 말해보세요.", "muted", True)
        self.sidebar_hint.setStyleSheet("font-size: 11px; color: #8f7daa; line-height: 1.6;")
        tips.addWidget(self.sidebar_hint)
        left.addWidget(tip)
        left.addSpacing(14)
        left.addWidget(label("●  내 기기에서만 음성 인식", "muted"))
        left.addWidget(button("앱 종료", name="nav", callback=self.exit_app.emit))
        root.addWidget(sidebar)
        content = QVBoxLayout()
        content.setContentsMargins(34, 30, 34, 20)
        content.setSpacing(18)
        header = QHBoxLayout()
        heading = QVBoxLayout()
        heading.addWidget(label("VOICE JOURNAL", "eyebrow"))
        heading.addSpacing(5)
        heading.addWidget(label("목소리가 기록이 되는 순간", "title"))
        heading.addWidget(label("말에만 집중하세요. 입력과 기록은 소리가 챙길게요.", "subtitle"))
        header.addLayout(heading)
        header.addStretch()
        header.addWidget(button("  입력 패널", "mic", callback=self.open_panel.emit))
        content.addLayout(header)
        hero = QFrame()
        hero.setObjectName("card")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(24, 12, 24, 12)
        self.voice = VoiceCanvas()
        self.voice.setFixedWidth(330)
        self.voice.clicked.connect(self.open_panel)
        hero_layout.addWidget(self.voice)
        copy = QVBoxLayout()
        copy.setSpacing(8)
        badge = label("LOCAL DICTATION")
        badge.setStyleSheet("color: #9578bb; font-size: 10px; font-weight: 700;")
        copy.addWidget(badge)
        self.hero_status = label("생각의 속도로, 말하세요.")
        self.hero_status.setStyleSheet("font-size: 21px; font-weight: 700; color: #393049;")
        copy.addWidget(self.hero_status)
        self.hero_hint = label(f"입력할 곳에 커서를 놓고 {DEFAULT_HOTKEY}을 눌러보세요.\n말을 마치면 문장이 그 자리에 입력됩니다.", "muted", True)
        self.hero_hint.setStyleSheet("color: #93899f; font-size: 12px;")
        copy.addWidget(self.hero_hint)
        copy.addSpacing(6)
        self.prepare_button = button("모델 준비하기", name="primary", callback=self.prepare.emit)
        copy.addWidget(self.prepare_button, alignment=Qt.AlignmentFlag.AlignLeft)
        hero_layout.addLayout(copy, 1)
        content.addWidget(hero)
        stats = QHBoxLayout()
        stats.setSpacing(12)
        self.stats = []
        for title, unit in [("오늘의 받아쓰기", "건"), ("목소리로 쓴 글", "자"), ("말한 시간", "분")]:
            card = QFrame()
            card.setObjectName("card")
            box = QVBoxLayout(card)
            box.setContentsMargins(19, 14, 19, 14)
            box.addWidget(label(title, "muted"))
            value = label("0")
            value.setStyleSheet("font-size: 25px; font-weight: 700; color: #554368;")
            number = QHBoxLayout()
            number.addWidget(value)
            number.addWidget(label(unit, "muted"), alignment=Qt.AlignmentFlag.AlignBottom)
            number.addStretch()
            box.addLayout(number)
            stats.addWidget(card)
            self.stats.append(value)
        content.addLayout(stats)
        toolbar = QHBoxLayout()
        self.day_picker = SoftComboBox()
        self.day_picker.setMinimumWidth(155)
        self.day_picker.currentIndexChanged.connect(self.change_day)
        toolbar.addWidget(self.day_picker)
        self.search = QLineEdit()
        self.search.setPlaceholderText("기록에서 검색…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.refresh_entries)
        toolbar.addWidget(self.search, 1)
        toolbar.addWidget(button("전체 복사", "copy", callback=self.copy_day))
        toolbar.addWidget(button("기록 폴더", "folder", callback=self.export.emit))
        content.addLayout(toolbar)
        self.live_text = label("", wrap=True)
        self.live_text.setStyleSheet("color: #7152b6; background: #eee7f8; border-radius: 9px; padding: 12px;")
        self.live_text.hide()
        content.addWidget(self.live_text)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.entries_container = QWidget()
        self.entries_layout = QVBoxLayout(self.entries_container)
        self.entries_layout.setContentsMargins(0, 0, 8, 0)
        self.entries_layout.setSpacing(10)
        self.entries_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.entries_container)
        content.addWidget(self.scroll, 1)
        self.footer = label("기록은 날짜별로 자동 저장됩니다. Markdown · JSONL", "muted")
        self.footer.setWordWrap(True)
        self.footer.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.footer.setStyleSheet("color: #9e96ad; font-size: 10px;")
        content.addWidget(self.footer)
        root.addLayout(content, 1)

    def refresh(self, store):
        self.store = store
        today = datetime.now().astimezone().date().isoformat()
        days = sorted(set([today] + store.days()), reverse=True)
        self.day_picker.blockSignals(True)
        self.day_picker.clear()
        for day in days:
            self.day_picker.addItem("오늘 · " + day[5:].replace("-", ".") if day == today else day.replace("-", "."), day)
        index = self.day_picker.findData(self.selected_day)
        self.day_picker.setCurrentIndex(max(0, index))
        self.day_picker.blockSignals(False)
        rows = store.entries(today)
        values = [str(len(rows)), f"{sum(len(r['text']) for r in rows):,}", f"{sum(r['duration'] for r in rows) / 60:.1f}"]
        for widget, value in zip(self.stats, values):
            widget.setText(value)
        self.refresh_entries()

    def change_day(self):
        self.selected_day = self.day_picker.currentData()
        self.refresh_entries()

    def refresh_entries(self):
        if not self.store:
            return
        while self.entries_layout.count():
            item = self.entries_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        rows = self.store.entries(self.selected_day, self.search.text())
        if not rows:
            empty = label("아직 조용한 페이지예요.\n첫 번째 목소리를 남겨보세요." if not self.search.text() else "검색 결과가 없습니다.", "muted", True)
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setMinimumHeight(130)
            self.entries_layout.addWidget(empty)
        for row in reversed(rows):
            card = QFrame()
            card.setObjectName("entry")
            box = QVBoxLayout(card)
            box.setContentsMargins(18, 13, 18, 15)
            box.setSpacing(8)
            top = QHBoxLayout()
            stamp = datetime.fromisoformat(row["timestamp"])
            top.addWidget(label(f"{stamp:%H:%M}   ·   {row['duration']:.0f}초", "muted"))
            target = row["target"] or "음성 메모"
            target_label = label(target[:35] + ("…" if len(target) > 35 else ""), "muted")
            target_label.setToolTip(target)
            top.addWidget(target_label)
            top.addStretch()
            control = button("", "copy", callback=lambda checked=False, text=row["text"]: self.copy_text.emit(text))
            control.setToolTip("이 문장 복사")
            control.setFixedSize(26, 25)
            control.setStyleSheet("QPushButton {border: none; padding: 2px; background: transparent;}")
            top.addWidget(control)
            box.addLayout(top)
            text = label(row["text"], wrap=True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            text.setStyleSheet("color: #5d556d; font-size: 13px;")
            box.addWidget(text)
            self.entries_layout.addWidget(card)

    def copy_day(self):
        if self.store:
            self.copy_text.emit("\n".join(row["text"] for row in self.store.entries(self.selected_day)))

    def closeEvent(self, event):
        event.ignore()
        self.close_requested.emit()


class SingleKeyPicker(QPushButton):
    changed = Signal(str)
    capture_error = Signal(str)

    def __init__(self, key):
        super().__init__()
        self.key_name = key
        self.capturing = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("클릭한 뒤 사용할 키 하나를 누르세요. Esc로 취소할 수 있습니다.")
        self.clicked.connect(self.begin_capture)
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(self.cancel_capture)
        self.refresh_text()

    def refresh_text(self):
        self.setText(hotkey_label(self.key_name) + "   ·   키 변경")

    def begin_capture(self):
        if self.capturing:
            self.cancel_capture()
            return
        self.capturing = True
        self.setText("사용할 키 하나를 누르세요 · Esc 취소")
        self.setFocus(Qt.FocusReason.OtherFocusReason)
        self.grabKeyboard()
        self.timeout.start(15000)

    def cancel_capture(self):
        if self.capturing:
            self.releaseKeyboard()
        self.capturing = False
        self.timeout.stop()
        self.refresh_text()

    @staticmethod
    def from_event(event):
        key = event.key()
        if sys.platform == "win32":
            sided = {0xA3: "Right Ctrl", 0xA5: "Right Alt", 0xA1: "Right Shift", 0x5C: "Right Meta"}
            if event.nativeVirtualKey() in sided:
                return sided[event.nativeVirtualKey()]
        if Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            return "F" + str(key - Qt.Key.Key_F1 + 1)
        if Qt.Key.Key_A <= key <= Qt.Key.Key_Z or Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            return chr(key)
        names = {
            Qt.Key.Key_CapsLock: "CapsLock", Qt.Key.Key_ScrollLock: "ScrollLock",
            Qt.Key.Key_Pause: "Pause", Qt.Key.Key_Insert: "Insert", Qt.Key.Key_Menu: "Menu",
            Qt.Key.Key_NumLock: "NumLock", Qt.Key.Key_Space: "Space", Qt.Key.Key_Tab: "Tab",
            Qt.Key.Key_Return: "Enter", Qt.Key.Key_Enter: "Enter", Qt.Key.Key_Backspace: "Backspace",
            Qt.Key.Key_Delete: "Delete", Qt.Key.Key_Home: "Home", Qt.Key.Key_End: "End",
            Qt.Key.Key_PageUp: "PageUp", Qt.Key.Key_PageDown: "PageDown", Qt.Key.Key_Up: "Up",
            Qt.Key.Key_Down: "Down", Qt.Key.Key_Left: "Left", Qt.Key.Key_Right: "Right",
            Qt.Key.Key_Control: "Ctrl", Qt.Key.Key_Alt: "Alt", Qt.Key.Key_Shift: "Shift",
            Qt.Key.Key_Meta: "Meta", Qt.Key.Key_AltGr: "Right Alt",
        }
        if key in names:
            return names[key]
        if sys.platform == "win32":
            candidate = f"VK:{event.nativeVirtualKey()}"
            if valid_hotkey(candidate):
                return candidate
        return None

    def keyPressEvent(self, event):
        if not self.capturing:
            return super().keyPressEvent(event)
        event.accept()
        if event.isAutoRepeat():
            return
        if event.key() == Qt.Key.Key_Escape:
            self.cancel_capture()
            return
        name = self.from_event(event)
        if not name:
            self.capture_error.emit("이 키는 인식하지 못했습니다. CapsLock·기능 키 등 다른 키를 눌러주세요.")
            return
        self.key_name = name
        self.cancel_capture()
        self.changed.emit(name)

    def hideEvent(self, event):
        self.cancel_capture()
        super().hideEvent(event)


class SettingsDialog(QDialog):
    def __init__(self, settings, devices, parent=None):
        super().__init__(parent)
        self.setWindowTitle("소리 · 설정")
        self.setMinimumWidth(490)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 16)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        scroll.setWidget(page)
        root.addWidget(scroll, 1)
        box = QVBoxLayout(page)
        box.setContentsMargins(28, 26, 28, 24)
        box.setSpacing(17)
        box.addWidget(label("내게 맞는 음성 입력", "title"))
        box.addWidget(label("단축키부터 기록까지, 편한 방식으로 설정하세요.", "muted"))
        form = QFormLayout()
        form.setVerticalSpacing(14)
        form.setHorizontalSpacing(20)
        def combo(options, value):
            widget = SoftComboBox()
            for title, data in options:
                widget.addItem(title, data)
            widget.setCurrentIndex(max(0, widget.findData(value)))
            return widget
        self.hotkey = SingleKeyPicker(settings.hotkey)
        self.hotkey_hint = label("", "muted", True)
        self.hotkey_hint.setStyleSheet("font-size: 11px; color: #93899f;")
        self.hotkey.changed.connect(self.update_hotkey_hint)
        self.hotkey.capture_error.connect(self.hotkey_hint.setText)
        self.mode = combo([("누르기 → 시작 · 다시 누르기 → 중단", "toggle"), ("누르고 말하기 → 떼면 중단", "hold")], settings.mode)
        self.language = combo([("한국어", "Korean"), ("자동 감지", "auto"), ("English", "English"), ("日本語", "Japanese"), ("中文", "Chinese")], settings.language)
        self.device = combo([("자동 · 사용 가능한 GPU 우선", "auto"), ("CPU", "cpu"), ("NVIDIA GPU (CUDA)", "cuda"), ("Intel GPU (XPU)", "xpu"), ("Apple GPU (MPS · 실험적)", "mps")], settings.device)
        self.microphone = combo([("기본 마이크", "")] + [(description, key) for key, description in devices], settings.microphone)
        self.clipboard = combo([("오늘 받아쓴 모든 문장", "today"), ("가장 최근 문장", "latest")], settings.clipboard)
        self.input_method = combo([("붙여넣기 · 대부분의 앱", "paste"), ("직접 키 입력 · 클립보드 유지", "unicode")], settings.input_method)
        for title, widget in [("지정 키", self.hotkey), ("입력 방식", self.mode), ("인식 언어", self.language), ("마이크", self.microphone), ("연산 장치", self.device), ("클립보드 내용", self.clipboard)]:
            form.addRow(title, widget)
        box.addLayout(form)
        form.addRow("입력 전달", self.input_method)
        box.addWidget(self.hotkey_hint)
        self.update_hotkey_hint(settings.hotkey)
        from sori.audio import Microphone
        self.test_microphone = Microphone(self)
        self.test_microphone.level.connect(self.update_microphone_level)
        self.test_microphone.error.connect(self.microphone_test_failed)
        self.test_timer = QTimer(self)
        self.test_timer.setSingleShot(True)
        self.test_timer.timeout.connect(self.finish_microphone_test)
        self.test_peak = 0
        self.test_button = button("마이크 테스트 · 5초", callback=self.toggle_microphone_test)
        self.test_meter = QProgressBar()
        self.test_meter.setRange(0, 100)
        self.test_meter.setTextVisible(False)
        self.test_meter.setValue(0)
        test_row = QHBoxLayout()
        test_row.addWidget(self.test_button)
        test_row.addWidget(self.test_meter, 1)
        if sys.platform == "win32":
            privacy = button("마이크 권한", callback=lambda: QDesktopServices.openUrl(QUrl("ms-settings:privacy-microphone")))
            test_row.addWidget(privacy)
        box.addLayout(test_row)
        self.test_status = label("테스트를 누르고 말해보세요. 음성은 저장하지 않습니다.", "muted", True)
        self.test_status.setStyleSheet("font-size: 11px; color: #85788f;")
        box.addWidget(self.test_status)
        self.finished.connect(self.stop_microphone_test)
        self.microphone.currentIndexChanged.connect(self.stop_microphone_test)
        self.auto_paste = QCheckBox("현재 입력창에 받아쓴 문장 자동 입력")
        self.auto_paste.setChecked(settings.auto_paste)
        box.addWidget(self.auto_paste)
        path_row = QHBoxLayout()
        self.archive = QLineEdit(settings.archive_directory)
        self.archive.setPlaceholderText("기본 기록 폴더")
        path_row.addWidget(self.archive)
        path_row.addWidget(button("폴더 선택", callback=self.choose_folder))
        box.addLayout(path_row)
        note = label("Qwen3-ASR-0.6B · 첫 준비 시 모델을 다운로드합니다.\n이후 음성 인식은 기기에서 실행됩니다. 길게 누르기는 0.25초 후 시작됩니다.", "muted", True)
        note.setStyleSheet("font-size: 11px; color: #93899f;")
        box.addWidget(note)
        actions = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        actions.button(QDialogButtonBox.StandardButton.Save).setText("저장")
        actions.button(QDialogButtonBox.StandardButton.Cancel).setText("취소")
        actions.accepted.connect(self.accept)
        actions.rejected.connect(self.reject)
        action_row = QHBoxLayout()
        action_row.setContentsMargins(28, 0, 28, 0)
        action_row.addWidget(actions)
        root.addLayout(action_row)
        self.resize(530, min(790, self.screen().availableGeometry().height() - 80))

    def toggle_microphone_test(self):
        if self.test_timer.isActive():
            self.finish_microphone_test()
            return
        self.test_peak = 0
        self.test_meter.setValue(0)
        try:
            self.test_microphone.start(self.microphone.currentData(), monitor_only=True)
        except Exception as exc:
            self.microphone_test_failed(str(exc))
            return
        self.test_button.setText("테스트 중단")
        self.test_status.setText("마이크를 듣고 있어요. 말하면 음량 막대가 움직입니다.")
        self.test_timer.start(5000)

    def update_microphone_level(self, level):
        self.test_peak = max(self.test_peak, level)
        self.test_meter.setValue(round(level * 100))

    def finish_microphone_test(self):
        received, peak = self.test_microphone.frames_received, self.test_peak
        self.stop_microphone_test()
        if not received:
            self.test_status.setText("입력 데이터가 없습니다. 마이크 연결과 데스크톱 앱 마이크 권한을 확인해 주세요.")
        elif peak < 0.021:
            self.test_status.setText("마이크는 열렸지만 음성이 작거나 무음입니다. 음소거와 입력 음량을 확인해 주세요.")
        else:
            self.test_status.setText("입력 신호를 확인했어요. 이 마이크로 받아쓸 수 있습니다.")

    def stop_microphone_test(self, *args):
        self.test_timer.stop()
        self.test_microphone.stop()
        self.test_button.setText("마이크 테스트 · 5초")
        self.test_meter.setValue(0)

    def microphone_test_failed(self, error):
        self.stop_microphone_test()
        self.test_status.setText(error)

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, "기록 저장 폴더", self.archive.text())
        if path:
            self.archive.setText(path)

    def update_settings(self, settings):
        settings.hotkey = self.hotkey.key_name
        for name in ("mode", "language", "device", "microphone", "clipboard", "input_method"):
            setattr(settings, name, getattr(self, name).currentData())
        settings.auto_paste = self.auto_paste.isChecked()
        settings.archive_directory = self.archive.text().strip()

    def update_hotkey_hint(self, name):
        if sys.platform == "win32" and name != "Ctrl+Alt+Space":
            self.hotkey_hint.setText(f"{hotkey_label(name)}은 앱 실행 중 음성 입력 전용 키로 사용합니다.\n앱을 종료하거나 다른 키로 바꾸면 원래 키 동작을 사용할 수 있습니다.")
        else:
            self.hotkey_hint.setText("키 변경을 누른 뒤 원하는 키 하나를 누르세요.\n이 환경에서는 지정 키의 원래 동작도 함께 실행될 수 있습니다.")
