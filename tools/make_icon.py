"""Generate a multi-resolution Windows icon from the app's vector drawing."""
import os
import struct
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QIODevice, QRectF, QPointF, Qt
from PySide6.QtGui import QPixmap, QPainter, QLinearGradient, QColor, QPen
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication([])
images = []
for size in (16, 32, 48, 64, 128, 256):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / 64, size / 64)
    gradient = QLinearGradient(4, 4, 58, 60)
    gradient.setColorAt(0, QColor("#63d5f4"))
    gradient.setColorAt(1, QColor("#4c62bb"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(2, 2, 60, 60), 17, 17)
    painter.setPen(QPen(QColor("#e8faff"), 4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    for x, height in [(18, 12), (27, 26), (36, 36), (45, 19)]:
        painter.drawLine(QPointF(x, 32 - height / 2), QPointF(x, 32 + height / 2))
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buffer, "PNG")
    images.append((size, bytes(buffer.data())))
output = Path(__file__).resolve().parents[1] / "sori" / "assets" / "sori.ico"
output.parent.mkdir(parents=True, exist_ok=True)
offset = 6 + 16 * len(images)
entries = []
for size, data in images:
    entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
    offset += len(data)
output.write_bytes(struct.pack("<HHH", 0, 1, len(images)) + b"".join(entries) + b"".join(data for _, data in images))
print(output)
