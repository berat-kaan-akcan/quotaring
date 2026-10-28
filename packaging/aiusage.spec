# PyInstaller spec (one-folder build) for Linux and Windows.
# Build from the repository root:  pyinstaller --noconfirm packaging/aiusage.spec
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
ICON = str(ROOT / "packaging" / "icons" / "ai-usage-widget.ico")

# Qt modules the widget never uses; keeps the bundle small.
EXCLUDES = [
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtXml", "PySide6.QtConcurrent",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtPrintSupport",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools",
    "PySide6.QtSvgWidgets", "PySide6.QtNetworkAuth", "PySide6.QtStateMachine",
    "tkinter", "unittest", "pydoc", "pytest",
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ai-usage-widget",
    console=False,
    icon=ICON if sys.platform == "win32" else None,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="ai-usage-widget", upx=False)
