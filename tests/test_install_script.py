"""install.sh's GNOME tray step, run with stand-ins for the system commands."""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="a POSIX shell script")

ROOT = Path(__file__).resolve().parent.parent
UBUNTU = "ubuntu-appindicators@ubuntu.com"
UPSTREAM = "appindicatorsupport@rgcjonas.gmail.com"


def tray_step() -> str:
    text = (ROOT / "install.sh").read_text()
    return text[text.index("TRAY_EXTENSIONS="):text.index("# A running copy:")]


def run(tmp_path: Path, enabled=(), known=(), packaged=(), settings="@as []", no_package=False):
    """`known`: what the running shell lists; `packaged`: what installing the package would add;
    `no_package`: the distribution has no package of the extension."""
    tmp_path = tmp_path / "install"
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(parents=True)
    log = tmp_path / "calls"
    (tmp_path / "settings").write_text(settings)
    for name, body in (("gnome-shell", 'echo "GNOME Shell 50.1"'),
                       ("curl", f'echo "curl $*" >> {log}\necho \'{{"download_url": "/download/x.zip"}}\'')):
        stub = bin_dir / name
        stub.write_text(f"#!/bin/sh\n{body}\n")
        stub.chmod(0o755)
    ext = bin_dir / "gnome-extensions"
    ext.write_text(f"""#!/bin/sh
echo "gnome-extensions $*" >> {log}
case "$1 $2" in
  "list --enabled") printf '%s\\n' {' '.join(enabled) or '""'} ;;
  "list "*) printf '%s\\n' {' '.join((*enabled, *known)) or '""'} ;;
  enable*) case " {' '.join((*enabled, *known))} " in *" $2 "*) ;; *) exit 2 ;; esac ;;
esac
""")
    gs = bin_dir / "gsettings"
    gs.write_text(f"""#!/bin/sh
echo "gsettings $*" >> {log}
[ "$1" = get ] && cat {tmp_path}/settings
[ "$1" = set ] && printf '%s' "$4" > {tmp_path}/settings
exit 0
""")
    for f in (ext, gs):
        f.chmod(f.stat().st_mode | stat.S_IEXEC)
    home = tmp_path / "home"
    home.mkdir()
    adds = "".join(f'mkdir -p "$HOME/.local/share/gnome-shell/extensions/{u}"; ' for u in packaged)
    script = (
        "set -eu\nsay() { echo \"quotaring: $*\"; }\n"
        f'pkg_install() {{ echo "pkg_install $*" >> {log}; {adds}return {int(no_package)}; }}\n'
        f'TMP={tmp_path}\n'
        + tray_step() + "\nensure_gnome_tray\n"
    )
    env = {"PATH": f"{bin_dir}:{os.environ['PATH']}", "HOME": str(home), "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
           "XDG_DATA_DIRS": str(tmp_path / "system")}  # not this machine's own extensions
    r = subprocess.run(["sh", "-c", script], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    calls = log.read_text() if log.exists() else ""
    return r.stdout, calls, (tmp_path / "settings").read_text()


def test_ubuntu_extension_already_on_needs_nothing(tmp_path):
    out, calls, _ = run(tmp_path, enabled=[UBUNTU])
    assert "pkg_install" not in calls  # no sudo prompt
    assert "enable" not in calls.replace("--enabled", "")
    assert out == ""  # no "log out" advice either


def test_ubuntu_extension_turned_off_is_turned_on_without_a_package(tmp_path):
    out, calls, _ = run(tmp_path, known=[UBUNTU])
    assert "pkg_install" not in calls
    assert f"gnome-extensions enable {UBUNTU}" in calls
    assert "log out" not in out  # a known extension starts at once


def test_new_package_is_enabled_for_the_next_login(tmp_path):
    # The running shell does not know a just-installed extension: `gnome-extensions enable` fails.
    out, calls, settings = run(tmp_path, packaged=[UPSTREAM], settings="['other@example.com']")
    assert "pkg_install" in calls
    assert settings == f"['other@example.com', '{UPSTREAM}']"
    assert "log out" in out


def test_new_package_with_no_extensions_on_yet(tmp_path):
    _, _, settings = run(tmp_path, packaged=[UPSTREAM])
    assert settings == f"['{UPSTREAM}']"


def test_no_package_falls_back_to_extensions_gnome_org(tmp_path):
    _, calls, _ = run(tmp_path, no_package=True)
    assert "shell_version=50" in calls
    assert "https://extensions.gnome.org/download/x.zip" in calls
    assert "gnome-extensions install --force" in calls


def test_other_desktops_are_left_alone(tmp_path):
    script = "set -eu\nsay() { :; }\n" + tray_step() + "\nensure_gnome_tray\necho done\n"
    r = subprocess.run(["sh", "-c", script], capture_output=True, text=True,
                       env={"PATH": os.environ["PATH"], "HOME": str(tmp_path), "XDG_CURRENT_DESKTOP": "KDE"})
    assert r.stdout.strip() == "done"
