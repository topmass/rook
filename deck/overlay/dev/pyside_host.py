"""A stand-in for qmlscene --transparent, for testing overlay.qml off the Deck (SteamOS has no PySide6):

    ROOK_OVERLAY_QML_HOST="uv run --no-project --with PySide6 python overlay/dev/pyside_host.py" \\
        python3 overlay/rook_overlay.py --mode webengine ...
"""
import sys

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickWindow
from PySide6.QtWebEngineQuick import QtWebEngineQuick

QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
QtWebEngineQuick.initialize()
QQuickWindow.setDefaultAlphaBuffer(True)  # What qmlscene --transparent does.
app = QGuiApplication(sys.argv)
engine = QQmlApplicationEngine(sys.argv[-1])
if not engine.rootObjects():
    sys.exit(1)
sys.exit(app.exec())
