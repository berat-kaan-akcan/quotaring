import hashlib
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from quotaring import updater
from quotaring.updater import Release, UpdateError

NOW = 1_800_000_000.0
ASSETS = ["quotaring-0.2.0-setup.exe", "quotaring-0.2.0-windows-x64.zip", "quotaring-0.2.0-x86_64.AppImage",
          "quotaring_0.2.0_amd64.deb", "quotaring-0.2.0-linux-x86_64.tar.gz",
          "quotaring-0.2.0-linux-x86_64-ubuntu22.04.tar.gz", "SHA256SUMS.txt"]


def gh(tag="v0.2.0", **extra):
    return {"tag_name": tag, "html_url": "https://github.com/x/quotaring/releases/tag/" + tag,
            "assets": [{"name": n, "browser_download_url": "https://dl/" + n} for n in ASSETS], **extra}


def test_versions():
    assert updater.parse_version("v0.2.1") == (0, 2, 1)
    assert updater.parse_version("0.2.0-rc1") is None and updater.parse_version(None) is None
    assert updater.is_newer("0.2.0", "0.1.0") and updater.is_newer("0.10.0", "0.9.9")
    assert not updater.is_newer("0.2", "0.2.0") and not updater.is_newer("0.1.0", "0.1.0")
    assert not updater.is_newer("junk", "0.1.0")


def test_parse_release():
    r = updater.parse_release(gh())
    assert r.version == "0.2.0" and r.page.endswith("/v0.2.0") and set(r.assets) == set(ASSETS)
    assert updater.parse_release(gh(prerelease=True)) is None
    assert updater.parse_release(gh(draft=True)) is None
    assert updater.parse_release(gh(tag="nightly")) is None
    assert updater.parse_release("x") is None
    bad = gh()
    bad["assets"].append({"name": "evil.exe", "browser_download_url": "http://dl/evil.exe"})
    assert "evil.exe" not in updater.parse_release(bad).assets  # https only


def test_check_reuses_the_last_answer():
    calls = []

    def fetch(url):
        calls.append(url)
        return gh()

    assert updater.check("0.1.0", NOW, fetch=fetch).version == "0.2.0"
    assert updater.check("0.1.0", NOW + 3600, fetch=fetch).version == "0.2.0"
    assert len(calls) == 1
    assert updater.check("0.2.0", NOW + 3600, fetch=fetch) is None  # already current
    updater.check("0.1.0", NOW + updater.CHECK_AFTER + 1, fetch=fetch)
    assert len(calls) == 2


def test_check_offline_keeps_the_cached_release():
    updater.check("0.1.0", NOW, fetch=lambda url: gh())

    def offline(url):
        raise OSError("down")

    assert updater.check("0.1.0", NOW + updater.CHECK_AFTER + 1, fetch=offline).version == "0.2.0"
    assert updater.check("0.1.0", NOW, force=True, fetch=offline).version == "0.2.0"


def test_check_without_cache_or_network():
    def offline(url):
        raise OSError("down")

    assert updater.check("0.1.0", NOW, fetch=offline) is None


def test_install_kind(tmp_path):
    exe = tmp_path / "QuotaRing" / "quotaring.exe"
    exe.parent.mkdir()
    kind = lambda **kw: updater.install_kind(**{"frozen": True, "plat": "linux", "exe": str(exe), "environ": {},
                                                "machine": "x86_64", **kw})
    assert kind(plat="win32") == "win-zip"
    (exe.parent / "unins000.exe").write_bytes(b"")
    assert kind(plat="win32", machine="AMD64") == "win-setup"
    assert kind(environ={"APPIMAGE": "/home/u/q.AppImage"}) == "appimage"
    assert kind(exe="/opt/quotaring/quotaring") == "deb"
    assert kind() == "tarball"
    assert kind(frozen=False) == "manual"  # source checkout or the Arch package
    assert kind(machine="aarch64") == "manual"
    assert kind(plat="darwin") == "manual"


def test_pick_asset():
    r = updater.parse_release(gh())
    assert updater.pick_asset(r, "win-setup") == "quotaring-0.2.0-setup.exe"
    assert updater.pick_asset(r, "win-zip") == "quotaring-0.2.0-windows-x64.zip"
    assert updater.pick_asset(r, "appimage") == "quotaring-0.2.0-x86_64.AppImage"
    assert updater.pick_asset(r, "deb") == "quotaring_0.2.0_amd64.deb"
    assert updater.pick_asset(r, "tarball") == "quotaring-0.2.0-linux-x86_64-ubuntu22.04.tar.gz"
    assert updater.pick_asset(r, "manual") is None
    assert updater.can_install(r, "deb") and not updater.can_install(r, "manual")
    r.assets.pop("SHA256SUMS.txt")
    assert not updater.can_install(r, "deb")  # nothing to verify against


def test_parse_sums():
    h = "a" * 64
    assert updater.parse_sums(f"{h}  one.zip\n{h.upper()} *two.exe\nnot a line\n") == {"one.zip": h, "two.exe": h}


class FakeWeb:
    def __init__(self, files: dict[str, bytes]):
        self.files = files

    def __call__(self, url, timeout=0):
        return io.BytesIO(self.files[url.rsplit("/", 1)[1]])


def release_with(name: str, data: bytes, digest: str | None = None) -> tuple[Release, FakeWeb]:
    digest = digest or hashlib.sha256(data).hexdigest()
    files = {name: data, "SHA256SUMS.txt": f"{digest}  {name}\n".encode()}
    return Release("0.2.0", assets={n: "https://dl/" + n for n in files}), FakeWeb(files)


def test_download_verifies_the_checksum(tmp_path):
    r, web = release_with("quotaring_0.2.0_amd64.deb", b"package")
    f = updater.download(r, "deb", tmp_path / "w", opener=web)
    assert f.read_bytes() == b"package"

    r, web = release_with("quotaring_0.2.0_amd64.deb", b"tampered", digest="0" * 64)
    with pytest.raises(UpdateError, match="checksum"):
        updater.download(r, "deb", tmp_path / "w", opener=web)
    assert not (tmp_path / "w" / "quotaring_0.2.0_amd64.deb").exists()


def test_download_needs_a_listed_checksum(tmp_path):
    r, web = release_with("quotaring_0.2.0_amd64.deb", b"package")
    web.files["SHA256SUMS.txt"] = b""
    with pytest.raises(UpdateError, match="no checksum"):
        updater.download(r, "deb", tmp_path / "w", opener=web)


def test_download_network_error(tmp_path):
    r, _ = release_with("quotaring_0.2.0_amd64.deb", b"package")

    def broken(url, timeout=0):
        raise OSError("reset")

    with pytest.raises(UpdateError, match="download failed"):
        updater.download(r, "deb", tmp_path / "w", opener=broken)


def test_extract_zip_bundle(tmp_path):
    archive = tmp_path / "q.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("quotaring/quotaring.exe", b"exe")
        z.writestr("quotaring/_internal/lib.dll", b"dll")
    bundle = updater.extract_bundle(archive, tmp_path / "out")
    assert (bundle / "_internal" / "lib.dll").read_bytes() == b"dll"


def test_extract_tar_bundle_and_bad_layouts(tmp_path):
    def tar(name, members):
        path = tmp_path / name
        with tarfile.open(path, "w:gz") as t:
            for m, data in members.items():
                info = tarfile.TarInfo(m)
                info.size = len(data)
                t.addfile(info, io.BytesIO(data))
        return path

    bundle = updater.extract_bundle(tar("ok.tar.gz", {"quotaring/quotaring": b"elf"}), tmp_path / "a")
    assert (bundle / "quotaring").read_bytes() == b"elf"
    with pytest.raises(UpdateError, match="layout"):
        updater.extract_bundle(tar("odd.tar.gz", {"other/quotaring": b"elf"}), tmp_path / "b")
    with pytest.raises(UpdateError, match="outside"):
        updater.extract_bundle(tar("evil.tar.gz", {"../escape": b"x", "quotaring/quotaring": b"elf"}), tmp_path / "c")
    assert not (tmp_path / "escape").exists()


def test_windows_swap_script_quotes_paths():
    script = updater.swap_script_windows(1234, Path(r"C:\Users\O'Neil\QuotaRing"), Path(r"C:\Users\O'Neil\QuotaRing.new\quotaring"))
    assert "Wait-Process -Id 1234" in script
    assert r"'C:\Users\O''Neil\QuotaRing'" in script and r"'C:\Users\O''Neil\QuotaRing.old'" in script
    # the old folder is moved back when the new one cannot take its place
    assert r"catch { Move-Item -LiteralPath 'C:\Users\O''Neil\QuotaRing.old' -Destination 'C:\Users\O''Neil\QuotaRing' }" in script


def test_manual_install_is_refused():
    with pytest.raises(UpdateError):
        updater.install(Release("0.2.0"), "manual")
