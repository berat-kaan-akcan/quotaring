"""Offscreen smoke tests for the QML popup: every state renders without QML errors."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("PySide6.QtQuick")

from PySide6.QtCore import QtMsgType, qInstallMessageHandler  # noqa: E402

from quotaring import viewmodel  # noqa: E402
from quotaring.aggregate import aggregate  # noqa: E402
from quotaring.model import LocalUsage, ProviderSnapshot, Quota, QuotaWindow, State, Tokens, UsageEvent  # noqa: E402
from quotaring.ui import theme  # noqa: E402
from quotaring.ui.popup import Backend, Popup  # noqa: E402

NOW = time.time()


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def qml_errors():
    """QML warnings (binding errors, type errors) collected while the test runs."""
    errors = []

    def handler(kind, _ctx, msg):
        if kind != QtMsgType.QtDebugMsg and ("qml" in msg.lower() or "file:" in msg):
            errors.append(msg)
    previous = qInstallMessageHandler(handler)
    yield errors
    qInstallMessageHandler(previous)


def snap(local_state, quota_state, windows=True):
    periods = aggregate([UsageEvent(NOW - 60, "model-a", Tokens(input=1234, output=56))], NOW)
    loc = LocalUsage(local_state, periods if local_state in (State.OK, State.STALE) else [],
                     detail="why", updated_at=NOW - 30, files=3,
                     daily=[["2026-10-%02d" % d, d * 1000] for d in range(15, 29)])
    q = Quota(quota_state,
              [QuotaWindow("five_hour", "5-hour session", 42.0, NOW + 3600, 300),
               QuotaWindow("seven_day", "Weekly", 95.0, NOW - 5, 10080)] if windows else [],
              plan="Pro", detail="because", extra={"weekly_breakdown": [{"key": "chat", "label": "Chats", "percent": 3}]},
              updated_at=NOW - 30)
    return ProviderSnapshot("claude", "Claude Code", loc, q)


def settle(app, n=20):
    for _ in range(n):
        app.processEvents()


def popup_for(settings, palette=theme.DARK, docked=False):
    backend = Backend(settings, palette)
    return backend, Popup(backend, docked=docked)


@pytest.mark.parametrize("remaining", [True, False])
@pytest.mark.parametrize("palette", [theme.LIGHT, theme.DARK])
def test_all_states_render(app, settings, qml_errors, remaining, palette):
    settings.show_remaining = remaining
    backend, popup = popup_for(settings, palette)
    popup.show()
    for ls in State:
        for qs in State:
            backend.set_view(viewmodel.widget_view([snap(ls, qs, windows=qs in (State.OK, State.STALE))], NOW))
            settle(app, 2)
    assert not popup.window.grabWindow().isNull()
    assert qml_errors == []


def test_token_strip_per_provider(app, settings, qml_errors):
    from PySide6.QtCore import QObject
    codex = snap(State.OK, State.OK)
    codex.provider_id, codex.name = "codex", "Codex"
    view = viewmodel.widget_view([snap(State.OK, State.OK), codex], NOW)
    assert [g["key"] for g in view["tokens"]["groups"]] == ["all", "claude", "codex"]
    backend, popup = popup_for(settings)
    popup.show()
    backend.set_view(view)
    content = popup.window.findChild(QObject, "popupContent")
    for group in ("codex", "gone", "all"):  # an unknown group falls back to all providers
        content.setProperty("tokGroup", group)
        settle(app, 2)
    assert qml_errors == []


def test_no_data_yet_renders(app, settings, qml_errors):
    _backend, popup = popup_for(settings)
    popup.show()
    settle(app)
    assert qml_errors == []


def test_prefs_round_trip(app, settings):
    backend, _popup = popup_for(settings)
    saved = []
    backend.prefsSaved.connect(lambda: saved.append(True))
    backend.setPref("showRemaining", False)
    backend.setPref("window", {"x": 1})  # unknown keys are ignored
    assert settings.show_remaining is False
    assert backend.prefs == {"showRemaining": False, "pinned": {}}
    assert len(saved) == 1


def test_toggle_and_reopen_guard(app, settings):
    _backend, popup = popup_for(settings, docked=True)
    popup.toggle()
    assert popup.is_visible()
    popup.toggle()
    assert not popup.is_visible()
    popup.toggle()  # the click that took focus away from the popup: must not reopen it
    assert not popup.is_visible()
    popup._hidden_at -= 1
    popup.toggle()
    assert popup.is_visible()


def test_focus_loss_right_after_show_keeps_popup(app, settings):
    _backend, popup = popup_for(settings, docked=True)
    popup.show()
    popup.focus_lost()
    assert popup.is_visible()
    popup._shown_at -= 1
    popup.focus_lost()
    assert not popup.is_visible()


def test_ring_icon_draws(app):
    from quotaring.app import make_ring_icon
    for ring in (viewmodel.ring([snap(State.OK, State.OK)], NOW),
                 {"available": True, "used": 100, "remaining": 0, "level": "bad", "limited": True}):
        icon = make_ring_icon(ring, True, theme.DARK)
        assert not icon.pixmap(22, 22).isNull()


def test_popup_centres_on_click_inside_screen():
    from quotaring.ui.popup import MARGIN, centered_left
    assert centered_left(800, 400, 0, 1536) == 600
    assert centered_left(1500, 400, 0, 1536) == 1536 - 400 - MARGIN  # near the right edge
    assert centered_left(10, 400, 0, 1536) == MARGIN
    assert centered_left(2000, 400, 1536, 1920) == 1800  # second screen


def test_tray_tooltip_shows_what_is_left():
    limits = viewmodel.limits_view([snap(State.OK, State.OK)], NOW)
    tip = viewmodel.limits_tooltip(limits)
    assert tip.startswith("Claude: 5 hours 58% left")
    assert "used" in viewmodel.limits_tooltip(limits, remaining=False)
    none = viewmodel.limits_view([snap(State.OK, State.NOT_AUTHENTICATED, windows=False)], NOW)
    assert viewmodel.limits_tooltip(none) == "Claude: Not signed in · run claude login"


def test_settings_window_renders_and_saves(app, settings, qml_errors):
    from quotaring.ui import settings_form
    backend, popup = popup_for(settings)
    backend.set_settings_form(settings_form.form(settings, True))
    saved = []
    backend.settingsSaved.connect(lambda values: saved.append(values))
    popup.open_settings()
    settle(app)
    win = popup.settings_window
    assert win.isVisible() and not win.grabWindow().isNull()
    draft = win.property("draft").toVariant()
    assert draft["theme"] == settings.theme  # the draft starts from the current settings
    backend.saveSettings(dict(draft, theme="dark", enabled_codex=False))
    assert saved and saved[0]["theme"] == "dark" and saved[0]["enabled_codex"] is False
    assert qml_errors == []


def test_settings_form_round_trip(settings):
    from quotaring.ui import settings_form
    f = settings_form.form(settings, autostart_supported=False)
    assert f["values"]["quota_antigravity"] is True and f["autostartSupported"] is False
    assert f["text"]["locale"] == "en"  # section titles upper-case as English even on a Turkish system
    values = dict(f["values"], local_refresh_seconds="5", theme="dark", quota_codex=False,
                  quota_antigravity=False, claude_command="  ", unknown=1)
    settings_form.apply(settings, values)
    assert settings.local_refresh_seconds == 15  # clamped
    assert settings.theme == "dark" and settings.quota_enabled["codex"] is False
    assert settings.quota_enabled["antigravity"] is False
    assert settings.claude_command == "claude"


def test_pin_keeps_a_limit_on_the_ring(app, settings, qml_errors):
    backend, popup = popup_for(settings)
    saved = []
    backend.prefsSaved.connect(lambda: saved.append(True))
    backend.pin("antigravity", "Claude Sonnet 5.5")
    assert settings.pinned == {"antigravity": "Claude Sonnet 5.5"}
    assert backend.prefs["pinned"] == {"antigravity": "Claude Sonnet 5.5"}
    backend.pin("antigravity", "Claude Sonnet 5.5")  # same row again: released
    assert settings.pinned == {} and len(saved) == 2
    # A card with more limits than rings renders with and without a pin.
    windows = [QuotaWindow(f"a:{i}", name, used, NOW + 3600)
               for i, (name, used) in enumerate((("Gemini 3.8 Flash", 20.0), ("Claude Opus 5.5", 85.0),
                                                 ("Claude Sonnet 5.5", 40.0), ("GPT-OSS 120B", 0.0)))]
    ag = ProviderSnapshot("antigravity", "Antigravity", LocalUsage(State.NOT_INSTALLED),
                          Quota(State.OK, windows, plan="Google AI Pro", updated_at=NOW))
    popup.show()
    backend.set_view(viewmodel.widget_view([ag], NOW))
    settle(app)
    backend.pin("antigravity", "GPT-OSS 120B")
    settle(app)
    assert qml_errors == []


def test_pinned_setting_is_cleaned(tmp_path):
    import json
    from quotaring import settings as settings_mod
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"pinned": {"antigravity": "GPT-OSS 120B", "bard": "x", "codex": 3}}))
    assert settings_mod.load(p).pinned == {"antigravity": "GPT-OSS 120B"}


def test_accent_colours():
    from quotaring.settings import Settings
    for name, (light, dark) in theme.ACCENTS.items():
        assert theme.with_accent(theme.LIGHT, name).accent == light
        assert theme.with_accent(theme.DARK, name).accent == dark
    amber = theme.with_accent(theme.DARK, "amber")
    assert amber.warn not in (theme.DARK.warn, amber.accent)  # "limit near" stays distinguishable
    assert theme.with_accent(theme.LIGHT, "bogus").accent == theme.ACCENTS["slate"][0]
    assert Settings(accent="bogus").clamp().accent == "slate"


def test_accent_setting_round_trip(app, settings):
    from quotaring.app import make_icon
    from quotaring.ui import settings_form
    settings_form.apply(settings, {"accent": "amber"})
    assert settings.accent == "amber"
    assert settings_form.form(settings, False)["values"]["accent"] == "amber"
    assert not make_icon(settings.accent).pixmap(32, 32).isNull()


def test_settings_apply_without_save(app, settings, qml_errors):
    from PySide6.QtCore import Q_ARG, QMetaObject
    from quotaring.ui import settings_form
    backend, popup = popup_for(settings)
    backend.set_settings_form(settings_form.form(settings, True))
    saved = []
    backend.settingsSaved.connect(lambda values: saved.append(values))
    popup.open_settings()
    settle(app)
    win = popup.settings_window

    def change(key, value, typed=False):
        QMetaObject.invokeMethod(win, "set", Q_ARG("QVariant", key), Q_ARG("QVariant", value),
                                 Q_ARG("QVariant", typed))

    change("theme", "dark")
    deadline = time.time() + 2
    while not saved and time.time() < deadline:
        settle(app, 1)
        time.sleep(0.02)
    assert saved and saved[-1]["theme"] == "dark"  # applied without a Save button
    change("claude_command", "/opt/claude", typed=True)
    win.close()  # closing applies a typed value that was still waiting for a pause
    settle(app)
    assert saved[-1]["claude_command"] == "/opt/claude"
    assert qml_errors == []
