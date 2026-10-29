"""Start at login: XDG autostart on Linux, the HKCU Run key on Windows."""

from __future__ import annotations

import os
import shlex
import sys
from pathlib import Path

APP_ID = "quotaring"
RUN_VALUE = "QuotaRing"


def launch_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable]
    exe = sys.executable
    if sys.platform == "win32":
        pyw = Path(exe).with_name("pythonw.exe")
        if pyw.exists():
            exe = str(pyw)
    return [exe, "-m", "quotaring"]


def supported() -> bool:
    return sys.platform == "win32" or sys.platform.startswith("linux")


def desktop_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(os.path.expanduser("~"), ".config")
    return Path(base) / "autostart" / f"{APP_ID}.desktop"


def desktop_entry(cmd: list[str], cwd: str | None) -> str:
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        "Name=QuotaRing",
        "Comment=Claude Code, Codex and Antigravity usage",
        "Exec=" + " ".join(shlex.quote(c) for c in cmd),
        "Icon=utilities-system-monitor",
        "Terminal=false",
        "X-GNOME-Autostart-enabled=true",
    ]
    if cwd:
        lines.append("Path=" + cwd)
    return "\n".join(lines) + "\n"


def _source_root() -> str | None:
    if getattr(sys, "frozen", False):
        return None
    return str(Path(__file__).resolve().parent.parent)


def is_enabled() -> bool:
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run") as k:
                winreg.QueryValueEx(k, RUN_VALUE)
                return True
        except OSError:
            return False
    return desktop_file().exists()


def set_enabled(enabled: bool) -> None:
    cmd = launch_command()
    if sys.platform == "win32":
        import subprocess
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                            winreg.KEY_SET_VALUE) as k:
            if enabled:
                value = subprocess.list2cmdline(cmd)
                root = _source_root()
                if root:  # running from source: start in the checkout so `-m quotaring` resolves
                    value = f'cmd /c "cd /d {root} && {value}"'
                winreg.SetValueEx(k, RUN_VALUE, 0, winreg.REG_SZ, value)
            else:
                try:
                    winreg.DeleteValue(k, RUN_VALUE)
                except FileNotFoundError:
                    pass
        return
    path = desktop_file()
    if enabled:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(desktop_entry(cmd, _source_root()), encoding="utf-8")
    else:
        try:
            path.unlink()
        except FileNotFoundError:
            pass
