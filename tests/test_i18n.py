import os
import re
import time
from pathlib import Path

import pytest

from quotaring import i18n
from quotaring.i18n import tr, tr_label
from quotaring.model import State
from quotaring.ui import format as fmt

ROOT = Path(__file__).resolve().parent.parent
NOW = time.time()


@pytest.fixture
def turkish():
    i18n.set_language("tr")
    yield
    i18n.set_language("en")


def test_english_is_identity():
    i18n.set_language("en")
    assert tr("Weekly") == "Weekly"
    assert tr_label("Weekly · Opus") == "Weekly · Opus"
    assert fmt.pct(24) == "24%"


def test_turkish_basics(turkish):
    assert tr("Weekly") == "Haftalık"
    assert tr("Something unknown") == "Something unknown"
    assert tr("3 database(s) could not be read") == "3 veritabanı okunamadı"
    assert tr("Local collection failed (KeyError)") == "Yerel toplama başarısız (KeyError)"
    assert tr_label("Weekly · Opus") == "Haftalık · Opus"
    assert tr_label("3-hour session · Spark") == "3 saatlik oturum · Spark"
    assert fmt.pct(24) == "%24"
    assert fmt.duration(3 * 3600 + 120) == "3sa 2dk"
    assert fmt.resets(NOW + 600, NOW) == "10dk sonra sıfırlanır"
    assert fmt.state_text(State.UNAVAILABLE) == "Kullanılamıyor"


def test_unknown_language_falls_back_to_english():
    assert i18n.set_language("xx") == "en"
    assert i18n.set_language("en") == "en"


def test_templates_keep_their_fields(turkish):
    for key, value in i18n.TR.items():
        fields_en = set(re.findall(r"{(\w*)}", key))
        fields_tr = set(re.findall(r"{(\w*)}", value))
        assert fields_en == fields_tr, key


def test_every_provider_message_is_translated(turkish):
    """Messages shown in the UI come from providers/engine as English literals."""
    sources = list((ROOT / "quotaring" / "providers").glob("*.py")) + [ROOT / "quotaring" / "engine.py"]
    found = set()
    for path in sources:
        text = path.read_text(encoding="utf-8")
        found |= set(re.findall(r'detail="([^"{]+)"', text))
        found |= set(re.findall(r'QuotaError\(State\.\w+, "([^"{]+)"', text))
        found |= set(re.findall(r'source="([^"{]+)"', text))
    found.discard("none")
    assert found, "regex found nothing — test is broken"
    # Membership, not "text changed": technical identifiers translate to themselves.
    missing = sorted(m for m in found
                     if m not in i18n.TR and not any(rx.match(m) for rx, _ in i18n.PATTERNS))
    assert not missing, missing


def test_settings_language_validation(tmp_path):
    import json
    from quotaring import settings as settings_mod
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"language": "tr"}))
    assert settings_mod.load(p).language == "tr"
    p.write_text(json.dumps({"language": "klingon"}))
    assert settings_mod.load(p).language == "system"


def test_ui_renders_in_turkish(turkish):
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    pytest.importorskip("PySide6.QtQuick")
    from quotaring import viewmodel
    from quotaring.settings import Settings
    from quotaring.ui import theme
    from quotaring.ui.popup import Backend, Popup
    from test_ui import NOW, snap

    QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    backend = Backend(Settings(), theme.LIGHT)
    popup = Popup(backend, docked=False)
    view = viewmodel.widget_view([snap(State.OK, State.OK)], NOW)
    backend.set_view(view)
    assert view["text"]["limits"] == "Limitler" and view["labels"]["settings"] == "Ayarlar"
    assert popup.window.title() == "QuotaRing"


def test_dates_follow_ui_language_not_process_locale(monkeypatch):
    import locale
    import time
    from quotaring import i18n, viewmodel
    from quotaring.ui import format as fmt
    try:
        locale.setlocale(locale.LC_TIME, "tr_TR.UTF-8")
    except locale.Error:
        pytest.skip("Turkish locale not installed")
    try:
        i18n.set_language("en")
        far = time.time() + 3 * 86400
        assert not any(t in fmt.resets(far, time.time()) for t in ("Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz", "Prş"))
        assert viewmodel._day_label("2026-10-29") == "Oct 29"
    finally:
        locale.setlocale(locale.LC_TIME, "C")
        i18n.set_language("en")
