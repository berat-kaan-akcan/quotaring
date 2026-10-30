"""Offscreen smoke tests for the QML popup: every state renders without QML errors."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("QT_QUICK_BACKEND", "software")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")
pytest.importorskip("PySide6.QtQuick")

from PySide6.QtCore import QObject, QtMsgType, qInstallMessageHandler  # noqa: E402

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
    assert backend.prefs == {"showRemaining": False, "pinned": {}, "order": []}
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


def test_popup_stays_put_when_its_page_changes_size(app, settings, monkeypatch):
    """Clicks inside the popup (a chip, Details) resize it; it must not follow the pointer there."""
    from PySide6.QtCore import QPoint
    from quotaring.ui import popup as popup_mod
    screen = app.primaryScreen().availableGeometry()
    pointer = {"pos": QPoint(screen.right() - 150, screen.bottom() - 4)}  # the tray icon
    monkeypatch.setattr(popup_mod.QCursor, "pos", staticmethod(lambda: pointer["pos"]))
    _backend, popup = popup_for(settings, docked=True)
    popup.show()
    settle(app)
    where = (popup.window.x(), popup.window.y() + popup.window.height())
    for x, height in ((screen.right() - 330, 500), (screen.right() - 30, 620)):
        pointer["pos"] = QPoint(x, screen.bottom() - 300)  # inside the popup
        popup.window.setHeight(height)
        settle(app)
        assert (popup.window.x(), popup.window.y() + popup.window.height()) == where
    popup.hide()
    pointer["pos"] = QPoint(screen.left() + 300, screen.bottom() - 4)  # opened again elsewhere
    popup._hidden_at -= 1
    popup.show()
    settle(app)
    assert popup.window.x() == popup_mod.centered_left(screen.left() + 300, popup.window.width(),
                                                       screen.x(), screen.width())


@pytest.mark.parametrize("panel", ["bottom", "top"])
def test_popup_keeps_its_place_on_every_screen(app, settings, qml_errors, monkeypatch, panel):
    """Every page, chip, period, settings state, the update banner and new data: the popup keeps
    its side and its edge by the panel, and never leaves the screen."""
    from PySide6.QtCore import QPoint
    from quotaring.ui import popup as popup_mod
    from quotaring.ui import settings_form
    monkeypatch.setattr(popup_mod, "panel_at_top", lambda _screen: panel == "top")
    screen = app.primaryScreen().availableGeometry()
    pointer = {"pos": QPoint(screen.right() - 120, screen.bottom() - 4 if panel == "bottom" else screen.top() + 4)}
    monkeypatch.setattr(popup_mod.QCursor, "pos", staticmethod(lambda: pointer["pos"]))
    codex = snap(State.OK, State.OK)
    codex.provider_id, codex.name = "codex", "Codex"
    snaps = [snap(State.OK, State.OK), codex]
    backend, popup = popup_for(settings, docked=True)
    backend.set_view(viewmodel.widget_view(snaps, NOW))
    backend.set_settings_form(settings_form.form(settings, True))
    popup.show()
    settle(app)
    content, win = popup.content(), popup.window

    def edge():  # the side by the panel stays put
        return win.y() + win.height() if panel == "bottom" else win.y()

    where, heights = (win.x(), edge()), set()

    def check(step):
        settle(app, 6)
        pointer["pos"] = QPoint(win.x() + 30 + len(heights) * 37 % 340, win.y() + 40)  # clicks land inside
        settle(app, 2)
        heights.add(win.height())
        assert (win.x(), edge()) == where, step
        assert screen.top() <= win.y() and win.y() + win.height() <= screen.bottom() + 1, step

    check("limits")
    backend.set_update({"text": "QuotaRing 9.9 is available", "action": "Update", "busy": False})
    check("update banner")
    backend.set_update({})
    check("banner gone")
    content.setProperty("page", "tokens")
    check("tokens")
    for group in ("claude", "codex", "all"):
        for period in ("today", "5h", "7d", "30d", "all"):
            content.setProperty("tokGroup", group)
            content.setProperty("tokPeriod", period)
            check(f"tokens {group} {period}")
    content.setProperty("page", "settings")
    check("settings")
    for enabled in (False, True):  # the notification section folds away when it is off
        settings.notify_enabled = enabled
        backend.set_settings_form(settings_form.form(settings, True))
        check(f"notifications {enabled}")
    content.setProperty("page", "limits")
    check("back to limits")
    backend.set_view(viewmodel.widget_view(snaps[:1], NOW))  # a provider went away: fewer cards
    check("one card")
    backend.set_view(viewmodel.widget_view([], NOW))
    check("no data")
    assert len(heights) > 2  # the pages really had different heights
    assert qml_errors == []


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


def test_settings_page_renders_and_saves(app, settings, qml_errors):
    from quotaring.ui import settings_form
    backend, popup = popup_for(settings)
    backend.set_settings_form(settings_form.form(settings, True))
    saved = []
    backend.settingsSaved.connect(lambda values: saved.append(values))
    popup.open_settings()
    settle(app)
    win = popup.window.findChild(QObject, "settingsPage")
    assert win.isVisible() and not popup.window.grabWindow().isNull()
    draft = win.property("draft").toVariant()
    assert draft["theme"] == settings.theme  # the draft starts from the current settings
    # Toggling notifications from the tray menu while Settings is open updates the open draft too.
    settings.notify_enabled = False
    backend.set_settings_form(settings_form.form(settings, True))
    settle(app)
    draft = win.property("draft").toVariant()
    assert draft["notify_enabled"] is False
    backend.saveSettings(dict(draft, theme="dark", enabled_codex=False))
    assert saved and saved[0]["theme"] == "dark" and saved[0]["enabled_codex"] is False
    assert saved[0]["notify_enabled"] is False
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
    assert f["values"]["notify_levels"] == [90] and f["values"]["notify_codex"] is True
    settings_form.apply(settings, {"notify_levels": [95, 50, 50, 300], "notify_codex": False,
                                   "notify_enabled": False, "notify_reset": True})
    assert settings.notify_levels == [50, 95] and settings.notify_providers["codex"] is False
    assert settings.notify_enabled is False and settings.notify_reset is True


def test_old_notify_threshold_is_migrated(tmp_path):
    import json
    from quotaring import settings as settings_mod
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"notify_threshold": 0}))
    assert settings_mod.load(p).notify_enabled is False
    p.write_text(json.dumps({"notify_threshold": 80, "card_order": ["codex"]}))
    s = settings_mod.load(p)
    assert s.notify_enabled and s.notify_levels == [80] and s.card_order == ["codex"]
    settings_mod.save(s, p)
    assert settings_mod.load(p).notify_levels == [80]


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
    win = popup.window.findChild(QObject, "settingsPage")

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
    popup.content().setProperty("page", "limits")  # leaving applies a typed value still waiting for a pause
    settle(app)
    assert saved[-1]["claude_command"] == "/opt/claude"
    assert qml_errors == []


def test_card_order_is_saved_and_cleaned(app, settings, tmp_path):
    import json
    from quotaring import settings as settings_mod
    backend, _popup = popup_for(settings)
    saved = []
    backend.prefsSaved.connect(lambda: saved.append(1))
    backend.setCardOrder(["antigravity", "claude", "bard", "claude"])
    assert settings.card_order == ["antigravity", "claude"] and backend.prefs["order"] == ["antigravity", "claude"]
    assert saved == [1]
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"card_order": "codex"}))
    assert settings_mod.load(p).card_order == []


def test_cards_reorder_by_dragging(app, settings, qml_errors):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest
    backend, popup = popup_for(settings)
    popup.show()
    snaps = []
    for pid, name in (("claude", "Claude Code"), ("codex", "Codex"), ("antigravity", "Antigravity")):
        s = snap(State.OK, State.OK)
        snaps.append(ProviderSnapshot(pid, name, s.local, s.quota))
    backend.set_view(viewmodel.widget_view(snaps, NOW))
    settle(app)
    w = popup.window

    def walk(item):
        yield item
        for c in item.childItems():
            yield from walk(c)

    def cards():  # slot -> card
        return {c.property("slot"): c for c in walk(w.contentItem()) if c.objectName() == "providerCard"}

    def at(item, fx, fy):
        p = item.mapToScene(item.boundingRect().topLeft())
        return QPoint(int(p.x() + item.width() * fx), int(p.y() + item.height() * fy))

    def wait(ms):
        end = time.time() + ms / 1000
        while time.time() < end:
            app.processEvents()
            time.sleep(0.01)

    def drag(card, onto, hold_ms=0, click_first=False):
        start, target = at(card, 0.3, 0.9), at(onto, 0.5, 0.5)  # from a row: rows have handlers too
        if click_first:  # touchpad-style double tap and drag
            QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, start)
            wait(30)
        QTest.mousePress(w, Qt.LeftButton, Qt.NoModifier, start)
        wait(hold_ms or 10)
        assert card.property("dragging") is False  # nothing moves before the pointer does
        for i in range(1, 9):
            QTest.mouseMove(w, target * i / 8 + start * (8 - i) / 8)
            wait(15)
        assert card.property("dragging") is True
        QTest.mouseRelease(w, Qt.LeftButton, Qt.NoModifier, target)
        wait(50)
        assert card.property("dragging") is False

    # A plain click moves nothing.
    QTest.mouseClick(w, Qt.LeftButton, Qt.NoModifier, at(cards()[0], 0.03, 0.02))
    wait(50)
    assert settings.card_order == []
    drag(cards()[0], cards()[2], hold_ms=700)  # press, hold, drag
    assert settings.card_order == ["codex", "antigravity", "claude"]
    assert settings.pinned == {}  # dragging from a row is not a click on it
    drag(cards()[2], cards()[0])  # press and drag right away
    assert settings.card_order == ["claude", "codex", "antigravity"]
    drag(cards()[1], cards()[0], click_first=True)
    assert settings.card_order[0] == "codex"
    assert {s: c.property("slot") for s, c in cards().items()} == {0: 0, 1: 1, 2: 2}
    assert qml_errors == []
