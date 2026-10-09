"""Render real Qt widgets offscreen; no model, microphone, or real input."""
import os
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import QApplication
from sori.app import Controller
from sori.ui import SettingsDialog, configure_appearance

app = QApplication([])
for font in ["/mnt/c/Windows/Fonts/malgun.ttf", "/mnt/c/Windows/Fonts/malgunbd.ttf"]:
    if Path(font).exists():
        QFontDatabase.addApplicationFont(font)
configure_appearance(app)
output = Path("docs")
output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory(prefix="sori-preview-") as directory:
    controller = Controller(app, Path(directory), demo=True)
    controller.dashboard.resize(1110, 820)
    controller.panel.show()
    app.processEvents()
    controller.dashboard.grab().save(str(output / "dashboard.png"))
    controller.panel.grab().save(str(output / "floating-panel.png"))
    controller.panel.voice.active = True
    controller.panel.voice.level = controller.panel.voice.smoothed_level = 0.65
    controller.panel.status.setText("듣고 있어요   00:12")
    app.processEvents()
    controller.panel.grab().save(str(output / "floating-panel-listening.png"))
    dialog = SettingsDialog(controller.settings, [])
    dialog.show()
    app.processEvents()
    dialog.grab().save(str(output / "settings.png"))
    dialog.language.showPopup()
    app.processEvents()
    dialog.language.view().window().grab().save(str(output / "dropdown.png"))
    dialog.language.hidePopup()
    controller.cleanup()
print("Rendered docs/dashboard.png, docs/floating-panel.png, docs/settings.png")
