"""Offscreen smoke tests: every state renders without errors and with honest labels."""

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from aiusage.aggregate import aggregate  # noqa: E402
from aiusage.model import LocalUsage, ProviderSnapshot, Quota, QuotaWindow, State, Tokens, UsageEvent  # noqa: E402
from aiusage.ui import theme  # noqa: E402
from aiusage.ui.window import MainWindow  # noqa: E402

NOW = time.time()


@pytest.fixture(scope="module")
def app():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


def snap(local_state, quota_state, windows=True):
    periods = aggregate([UsageEvent(NOW - 60, "model-a", Tokens(input=1234, output=56))], NOW)
    loc = LocalUsage(local_state, periods if local_state in (State.OK, State.STALE) else [],
                     detail="why", updated_at=NOW - 30, files=3)
    q = Quota(quota_state,
              [QuotaWindow("five_hour", "5-hour session", 42.0, NOW + 3600, 300),
               QuotaWindow("seven_day", "Weekly", 95.0, NOW - 5, 10080)] if windows else [],
              plan="Pro", detail="because", extra={"weekly_breakdown": [{"key": "chat", "label": "Chats", "percent": 3}]},
              updated_at=NOW - 30)
    return ProviderSnapshot("claude", "Claude Code", loc, q)


@pytest.mark.parametrize("expanded", [False, True])
@pytest.mark.parametrize("palette", [theme.LIGHT, theme.DARK])
def test_all_states_render(app, settings, expanded, palette):
    settings.expanded = expanded
    w = MainWindow([("claude", "Claude Code")], palette, settings)
    card = w.cards["claude"]
    for ls in State:
        for qs in State:
            card.update_snapshot(snap(ls, qs, windows=qs in (State.OK, State.STALE)))
    w.resize(360, 600)
    assert not w.grab().isNull()


def test_stale_and_unavailable_texts(app, settings):
    w = MainWindow([("claude", "Claude Code")], theme.LIGHT, settings)
    card = w.cards["claude"]
    card.update_snapshot(snap(State.OK, State.STALE))
    assert card.quota_msg.text().startswith("Stale (last updated")
    card.update_snapshot(snap(State.OK, State.UNAVAILABLE, windows=False))
    assert "Unavailable" in card.quota_msg.text()
    assert card.pill.text() == "Local only"
    card.update_snapshot(snap(State.NOT_INSTALLED, State.NOT_INSTALLED, windows=False))
    assert card.pill.text() == "Not installed"


def test_window_flags_and_expand_toggle(app, settings):
    from PySide6.QtCore import Qt
    w = MainWindow([("claude", "Claude Code")], theme.DARK, settings)
    assert w.windowFlags() & Qt.WindowStaysOnTopHint
    settings.always_on_top = False
    w.apply_flags()
    assert not (w.windowFlags() & Qt.WindowStaysOnTopHint)
    before = settings.expanded
    w.btn_expand.click()
    assert settings.expanded != before
