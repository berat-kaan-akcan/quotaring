# PyInstaller spec (one-folder build) for Linux and Windows.
# Build from the repository root:  pyinstaller --noconfirm packaging/quotaring.spec
import sys
from pathlib import Path

ROOT = Path(SPECPATH).parent
ICON = str(ROOT / "packaging" / "icons" / "quotaring.ico")

# Qt modules the widget never uses; keeps the bundle small. QtQml/QtQuick draw the popup, and
# PySide6.QtQml imports PySide6.QtNetwork, so that one must stay.
EXCLUDES = [
    "PySide6.QtQuickWidgets",
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
    datas=[(str(ROOT / "quotaring" / "ui" / "qml"), "quotaring/ui/qml")],
    noarchive=False,
)
if sys.platform.startswith("linux"):
    # The build machine's libstdc++ (Ubuntu 22.04) is older than the one newer Mesa drivers are
    # linked against, so bundling it makes GLX fail to load on e.g. Arch/CachyOS and the app
    # aborts with "Could not initialize GLX". Every distribution ships a libstdc++ at least as new.
    a.binaries = [b for b in a.binaries if not Path(b[0]).name.startswith("libstdc++.so")]
VERSION = None
if sys.platform == "win32":
    # Windows shows FileDescription as the notification sender and in Task Manager; without it, "quotaring.exe".
    import re
    from PyInstaller.utils.win32.versioninfo import (FixedFileInfo, StringFileInfo, StringStruct, StringTable,
                                                     VarFileInfo, VarStruct, VSVersionInfo)
    ver = re.search(r'__version__ = "([^"]+)"', (ROOT / "quotaring" / "__init__.py").read_text()).group(1)
    nums = tuple((list(map(int, re.findall(r"\d+", ver)[:4])) + [0, 0, 0, 0])[:4])
    VERSION = VSVersionInfo(
        ffi=FixedFileInfo(filevers=nums, prodvers=nums),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", "Berat Kaan Akcan"),
                StringStruct("FileDescription", "QuotaRing"),
                StringStruct("FileVersion", ver),
                StringStruct("InternalName", "quotaring"),
                StringStruct("LegalCopyright", "MIT License"),
                StringStruct("OriginalFilename", "quotaring.exe"),
                StringStruct("ProductName", "QuotaRing"),
                StringStruct("ProductVersion", ver),
            ])]),
            VarFileInfo([VarStruct("Translation", [0x0409, 1200])]),
        ],
    )

pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="quotaring",
    console=False,
    icon=ICON if sys.platform == "win32" else None,
    version=VERSION,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="quotaring", upx=False)
