"""What to tell a GNOME user whose tray icon cannot show."""

from __future__ import annotations

import os
import shutil

INSTALLER = "https://raw.githubusercontent.com/berat-kaan-akcan/quotaring/main/install.sh"


def extension_missing(tray_available: bool) -> bool:
    """GNOME has no tray of its own, so there no tray means its extension is missing or turned off."""
    return not tray_available and "GNOME" in os.environ.get("XDG_CURRENT_DESKTOP", "")


def command() -> str:
    """The install script knows each distribution's package and the extension's two names."""
    fetch = "wget -qO-" if shutil.which("wget") and not shutil.which("curl") else "curl -fsSL"
    return f"{fetch} {INSTALLER} | QUOTARING_TRAY_ONLY=1 sh"
