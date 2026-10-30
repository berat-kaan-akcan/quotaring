"""Windows 11: show the tray icon next to the clock instead of under the overflow arrow.

Explorer keeps one key per tray icon under HKCU\\Control Panel\\NotifyIconSettings, created the
first time the icon appears, and hides it until IsPromoted is 1. There is no API for this, so the
value is set once on our own entry; when the user later hides the icon Explorer writes 0, which
is left alone.
"""

from __future__ import annotations

import logging
import os
import sys

log = logging.getLogger("quotaring")

KEY = r"Control Panel\NotifyIconSettings"


def same_exe(recorded: str, exe: str) -> bool:
    """Whether Explorer's ExecutablePath is `exe`; it may start with a known-folder GUID
    ("{6D809377-…}\\QuotaRing\\quotaring.exe") instead of the folder itself."""
    a = os.path.normcase(os.path.normpath(recorded))
    b = os.path.normcase(os.path.normpath(exe))
    if a.startswith("{") and "}" in a:
        return b.endswith(a[a.index("}") + 1:])
    return a == b


def promote(exe: str) -> bool:
    """Set IsPromoted on `exe`'s entries that have none yet; False while Explorer has none."""
    if sys.platform != "win32":
        return False
    import winreg
    found = False
    try:
        root = winreg.OpenKey(winreg.HKEY_CURRENT_USER, KEY)
    except OSError:
        return False
    with root:
        i = 0
        while True:
            try:
                name = winreg.EnumKey(root, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(root, name, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
                    path, _ = winreg.QueryValueEx(k, "ExecutablePath")
                    if not same_exe(str(path), exe):
                        continue
                    found = True
                    try:
                        winreg.QueryValueEx(k, "IsPromoted")  # the user's own choice: keep it
                    except FileNotFoundError:
                        winreg.SetValueEx(k, "IsPromoted", 0, winreg.REG_DWORD, 1)
            except OSError as e:
                log.debug("tray entry %s: %s", name, e)
    return found
