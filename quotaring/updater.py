"""New releases on GitHub, and installing them over the running copy.

The latest release is asked for at most twice a day when the setting allows it. How an update is
installed depends on how this copy was installed:
  win-setup  Inno Setup install: the new setup runs silently and starts the app again.
  win-zip    portable folder: swapped for the new one by a helper once the app has quit.
  appimage   the AppImage file is replaced (Linux keeps the running one open).
  deb        the new .deb goes through apt (or dpkg) under pkexec, which asks for the password.
  tarball    portable folder, swapped while running (Linux allows it).
  manual     the Arch package, a source checkout, other CPUs: only the release page is offered.
Every download is checked against the release's SHA256SUMS.txt before it is used.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import paths
from .jsonstore import read_json, write_json

log = logging.getLogger(__name__)
API_URL = "https://api.github.com/repos/berat-kaan-akcan/quotaring/releases/latest"
RELEASES_URL = "https://github.com/berat-kaan-akcan/quotaring/releases/latest"
CHECK_AFTER = 12 * 3600
SUMS = "SHA256SUMS.txt"
AUTO_KINDS = ("win-setup", "win-zip", "appimage", "deb", "tarball")


class UpdateError(Exception):
    """An update could not be downloaded, verified or installed; the message says which step."""


@dataclass
class Release:
    version: str
    page: str = RELEASES_URL
    assets: dict = field(default_factory=dict)  # file name -> download URL


def parse_version(text) -> tuple[int, ...] | None:
    """(0, 2, 1) from "v0.2.1"; None for anything else, pre-releases included."""
    m = re.fullmatch(r"v?(\d+(?:\.\d+)*)", text.strip()) if isinstance(text, str) else None
    return tuple(int(p) for p in m[1].split(".")) if m else None


def is_newer(version: str, current: str) -> bool:
    new, cur = parse_version(version), parse_version(current)
    if not new or not cur:
        return False
    width = max(len(new), len(cur))  # 0.2 == 0.2.0
    return new + (0,) * (width - len(new)) > cur + (0,) * (width - len(cur))


def parse_release(data) -> Release | None:
    """The fields we use from GitHub's /releases/latest reply; None for drafts and pre-releases."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name")
    if not parse_version(tag):
        return None
    assets = {}
    for a in data.get("assets") if isinstance(data.get("assets"), list) else []:
        if isinstance(a, dict) and isinstance(a.get("name"), str) \
                and str(a.get("browser_download_url", "")).startswith("https://"):
            assets[a["name"]] = a["browser_download_url"]
    page = data.get("html_url")
    return Release(tag.lstrip("v"), page if isinstance(page, str) and page.startswith("https://") else RELEASES_URL,
                   assets)


def _get(url: str, timeout: float = 30):
    req = urllib.request.Request(url, headers={"User-Agent": "QuotaRing", "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def _fetch_json(url: str):
    with _get(url) as r:
        return json.loads(r.read())


def cache_path() -> Path:
    return paths.cache_dir() / "update.json"


def check(current: str, now: float | None = None, force: bool = False, fetch=_fetch_json) -> Release | None:
    """The latest release when it is newer than `current`, else None.

    GitHub is asked at most every CHECK_AFTER seconds; in between the last answer is reused.
    """
    now = time.time() if now is None else now
    cached = read_json(cache_path(), {})
    cached = cached if isinstance(cached, dict) else {}
    checked = cached.get("checked_at")
    if force or not isinstance(checked, (int, float)) or not 0 <= now - checked < CHECK_AFTER:
        try:
            data = fetch(API_URL)
        except Exception as e:  # noqa: BLE001 - offline, rate limited, bad JSON: try again later
            log.info("update check failed: %s", type(e).__name__)
            data = cached.get("release")
        else:
            try:
                write_json(cache_path(), {"checked_at": now, "release": data})
            except OSError:
                pass
    else:
        data = cached.get("release")
    rel = parse_release(data)
    return rel if rel and is_newer(rel.version, current) else None


# -- how this copy was installed ---------------------------------------------

def install_kind(frozen: bool | None = None, plat: str | None = None, exe: str | None = None,
                 environ=None, machine: str | None = None) -> str:
    frozen = getattr(sys, "frozen", False) if frozen is None else frozen
    plat = sys.platform if plat is None else plat
    exe = sys.executable if exe is None else exe
    environ = os.environ if environ is None else environ
    machine = (platform.machine() if machine is None else machine).lower()
    if not frozen or machine not in ("x86_64", "amd64"):
        return "manual"
    if plat == "win32":
        return "win-setup" if Path(exe).with_name("unins000.exe").exists() else "win-zip"
    if plat.startswith("linux"):
        if environ.get("APPIMAGE"):
            return "appimage"
        return "deb" if Path(exe).resolve().parent == Path("/opt/quotaring").resolve() else "tarball"
    return "manual"


def pick_asset(release: Release, kind: str) -> str | None:
    """The release file this kind of install updates from."""
    tests = {
        "win-setup": lambda n: n.endswith("-setup.exe"),
        "win-zip": lambda n: n.endswith("-windows-x64.zip"),
        "appimage": lambda n: n.endswith("-x86_64.AppImage"),
        "deb": lambda n: n.endswith("_amd64.deb"),
        "tarball": lambda n: "-linux-x86_64" in n and n.endswith(".tar.gz"),
    }
    test = tests.get(kind)
    names = sorted(n for n in release.assets if test and test(n))
    # The Ubuntu 22.04 build runs on the most distributions: prefer it when there are several.
    names.sort(key=lambda n: "ubuntu22.04" not in n)
    return names[0] if names else None


def can_install(release: Release, kind: str) -> bool:
    return kind in AUTO_KINDS and pick_asset(release, kind) is not None and SUMS in release.assets


# -- download and verify ------------------------------------------------------

def parse_sums(text: str) -> dict[str, str]:
    """{file name: sha256} from `sha256sum` output."""
    out = {}
    for line in text.splitlines():
        m = re.fullmatch(r"([0-9a-fA-F]{64}) [ *]?(.+)", line.strip())
        if m:
            out[m[2].strip()] = m[1].lower()
    return out


def _download_to(url: str, dest: Path, opener=_get) -> str:
    """Write the file and return its sha256."""
    h = hashlib.sha256()
    with opener(url, timeout=120) as r, open(dest, "wb") as f:
        while chunk := r.read(1 << 16):
            h.update(chunk)
            f.write(chunk)
    return h.hexdigest()


def download(release: Release, kind: str, workdir: Path | None = None, opener=_get) -> Path:
    """The verified installer/archive for this kind of install, in `workdir`."""
    name = pick_asset(release, kind)
    if not name or SUMS not in release.assets:
        raise UpdateError("no matching download in the release")
    workdir = workdir or paths.cache_dir() / "update"
    shutil.rmtree(workdir, ignore_errors=True)
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        with opener(release.assets[SUMS], timeout=30) as r:
            sums = parse_sums(r.read().decode("utf-8", "replace"))
        if name not in sums:
            raise UpdateError("the download has no checksum")
        dest = workdir / name
        if _download_to(release.assets[name], dest, opener) != sums[name]:
            dest.unlink(missing_ok=True)
            raise UpdateError("checksum mismatch")
    except UpdateError:
        raise
    except Exception as e:  # noqa: BLE001 - network and disk errors alike
        raise UpdateError(f"download failed ({type(e).__name__})") from e
    return dest


def clean_downloads(workdir: Path | None = None) -> None:
    """Remove what `download` left behind once that update is installed."""
    shutil.rmtree(workdir or paths.cache_dir() / "update", ignore_errors=True)


def _safe_members(names, root: Path):
    """Raise when an archive entry would land outside `root`."""
    root = root.resolve()
    for n in names:
        target = (root / n).resolve()
        if target != root and root not in target.parents:
            raise UpdateError("archive entry outside the target folder")


def extract_bundle(archive: Path, into: Path) -> Path:
    """Unpack a release archive and return its `quotaring` folder."""
    shutil.rmtree(into, ignore_errors=True)
    into.mkdir(parents=True)
    try:
        if archive.suffix == ".zip":
            with zipfile.ZipFile(archive) as z:
                _safe_members(z.namelist(), into)
                z.extractall(into)
        else:
            with tarfile.open(archive) as t:
                _safe_members(t.getnames(), into)
                if hasattr(tarfile, "data_filter"):
                    t.extractall(into, filter="data")
                else:  # pragma: no cover - Python without the 2023 tarfile filters
                    t.extractall(into)
    except (OSError, zipfile.BadZipFile, tarfile.TarError) as e:
        raise UpdateError(f"could not unpack ({type(e).__name__})") from e
    bundle = into / "quotaring"
    if not (bundle / ("quotaring.exe" if archive.suffix == ".zip" else "quotaring")).is_file():
        raise UpdateError("unexpected archive layout")
    return bundle


# -- install ------------------------------------------------------------------

def _ps_quote(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def swap_script_windows(pid: int, app_dir: Path, new_dir: Path) -> str:
    """PowerShell that waits for `pid` to exit, puts `new_dir` in place of `app_dir` and starts it.

    The old folder is kept until the new one is in place, and put back if the move fails."""
    app, new, old = _ps_quote(str(app_dir)), _ps_quote(str(new_dir)), _ps_quote(str(app_dir) + ".old")
    return "\n".join([
        "$ErrorActionPreference = 'Stop'",
        f"try {{ Wait-Process -Id {int(pid)} -Timeout 60 }} catch {{}}",
        f"Remove-Item -LiteralPath {old} -Recurse -Force -ErrorAction SilentlyContinue",
        f"try {{ Move-Item -LiteralPath {app} -Destination {old} }} catch {{ Start-Process (Join-Path {app} 'quotaring.exe'); exit 1 }}",
        f"try {{ Move-Item -LiteralPath {new} -Destination {app} }} catch {{ Move-Item -LiteralPath {old} -Destination {app} }}",
        f"Start-Process (Join-Path {app} 'quotaring.exe')",
        f"Remove-Item -LiteralPath {old} -Recurse -Force -ErrorAction SilentlyContinue",
        f"Remove-Item -LiteralPath {_ps_quote(str(new_dir.parent))} -Recurse -Force -ErrorAction SilentlyContinue",
    ])


def _detached(cmd: list[str]) -> None:
    if sys.platform == "win32":
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(cmd, creationflags=flags, close_fds=True)
    else:
        subprocess.Popen(cmd, start_new_session=True, close_fds=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _relaunch_after_exit(exe: str) -> None:
    """Start `exe` once this process has gone, so the single-instance lock is free."""
    _detached(["/bin/sh", "-c", 'while kill -0 "$1" 2>/dev/null; do sleep 0.2; done; exec "$2"',
               "quotaring-relaunch", str(os.getpid()), exe])


def install(release: Release, kind: str, workdir: Path | None = None) -> None:
    """Download, verify and install; afterwards the caller quits and the new version starts.

    Runs off the UI thread. On Linux the files are replaced here; on Windows, where running files
    are locked, the replacement is left to a process that waits for this one to exit."""
    if kind not in AUTO_KINDS:
        raise UpdateError("this installation cannot update itself")
    file = download(release, kind, workdir)
    exe = Path(sys.executable)
    if kind == "win-setup":
        _detached([str(file), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/RELAUNCH=1"])
    elif kind == "win-zip":
        new = extract_bundle(file, exe.parent.with_name(exe.parent.name + ".new"))
        script = swap_script_windows(os.getpid(), exe.parent, new)
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")  # no quoting to get wrong
        _detached(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                   "-WindowStyle", "Hidden", "-EncodedCommand", encoded])
    elif kind == "appimage":
        target = Path(os.environ["APPIMAGE"])
        tmp = target.with_name(target.name + ".new")
        try:
            shutil.copyfile(file, tmp)
            tmp.chmod(0o755)
            os.replace(tmp, target)
        except OSError as e:
            tmp.unlink(missing_ok=True)
            raise UpdateError(f"could not replace the AppImage ({type(e).__name__})") from e
        _relaunch_after_exit(str(target))
    elif kind == "deb":
        if not shutil.which("pkexec"):
            raise UpdateError("pkexec is missing")
        cmd = ["apt-get", "install", "-y", str(file)] if shutil.which("apt-get") else ["dpkg", "-i", str(file)]
        if subprocess.run(["pkexec", *cmd], stdin=subprocess.DEVNULL).returncode != 0:
            raise UpdateError("the package was not installed")
        _relaunch_after_exit("/usr/bin/quotaring")
    else:  # tarball
        app = exe.parent
        new = extract_bundle(file, app.with_name(app.name + ".new"))
        old = app.with_name(app.name + ".old")
        shutil.rmtree(old, ignore_errors=True)
        try:
            os.rename(app, old)
            try:
                os.rename(new, app)
            except OSError:
                os.rename(old, app)
                raise
        except OSError as e:
            raise UpdateError(f"could not replace the folder ({type(e).__name__})") from e
        finally:
            shutil.rmtree(new.parent, ignore_errors=True)
        shutil.rmtree(old, ignore_errors=True)
        _relaunch_after_exit(str(app / "quotaring"))
