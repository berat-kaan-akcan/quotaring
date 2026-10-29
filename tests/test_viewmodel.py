import json
import time

from quotaring import i18n, viewmodel
from quotaring.aggregate import aggregate, daily_totals
from quotaring.model import LocalUsage, ProviderSnapshot, Quota, QuotaWindow, State, Tokens, UsageEvent

NOW = time.time()


def snap(pid="claude", local=State.OK, quota=State.OK, windows=None):
    events = [UsageEvent(NOW - 60, "model-a", Tokens(input=1500, output=20)),
              UsageEvent(NOW - 3 * 86400, "model-b", Tokens(input=10))]
    loc = LocalUsage(local, aggregate(events, NOW) if local in (State.OK, State.STALE) else [],
                     daily=daily_totals(events, NOW), files=2, updated_at=NOW - 5)
    if windows is None:
        windows = [QuotaWindow("five_hour", "5-hour session", 41.0, NOW + 3600, 300),
                   QuotaWindow("seven_day", "Weekly", 4.0, NOW + 6 * 86400, 10080)]
    q = Quota(quota, windows if quota in (State.OK, State.STALE) else [], plan="Pro",
              source="claude CLI get_usage (experimental, undocumented)",
              extra={"weekly_breakdown": [{"key": "chat", "label": "Chats", "percent": 2.0}]},
              detail="" if quota == State.OK else "Provider timed out", updated_at=NOW - 5)
    return ProviderSnapshot(pid, "Claude Code", loc, q)


def test_widget_view_is_json_and_complete():
    i18n.set_language("en")
    v = json.loads(json.dumps(viewmodel.widget_view([snap()], NOW)))
    assert v["ring"] == {"available": True, "used": 41, "remaining": 59, "level": "ok", "limited": False,
                         "label": "Claude Code · 5-hour session"}
    claude = v["limits"][0]
    assert [(w["label"], w["tag"], w["remaining"]) for w in claude["windows"]] == [("5 hours", "5h", 59), ("Weekly", "W", 96)]
    assert claude["plan"] == "Pro" and claude["color"] == viewmodel.COLORS["claude"]
    assert v["tokens"]["data"]["all"]["periods"]["today"]["models"][0]["name"] == "model-a"
    assert set(v["labels"]) == {"title", "refresh", "settings"}


def test_ring_ignores_windows_past_reset_and_unverified_quota():
    i18n.set_language("en")
    passed = snap(windows=[QuotaWindow("w", "Weekly", 99.0, NOW - 10, 10080),
                           QuotaWindow("s", "5-hour session", 12.0, NOW + 60, 300)])
    assert viewmodel.ring([passed], NOW)["used"] == 12
    assert not viewmodel.ring([snap(quota=State.UNAVAILABLE)], NOW)["available"]


def test_states_hidden_stale_and_unavailable():
    i18n.set_language("en")
    assert viewmodel.limits_view([snap("codex", State.NOT_INSTALLED, State.NOT_INSTALLED)], NOW) == []
    stale = viewmodel.limits_view([snap(quota=State.STALE)], NOW)[0]
    assert all(w["dim"] for w in stale["windows"]) and stale["note"].startswith("updated")
    unavailable = viewmodel.limits_view([snap(quota=State.UNAVAILABLE)], NOW)[0]
    assert unavailable["windows"] == [] and unavailable["message"] == "No limit data"


def test_model_name():
    assert viewmodel.model_name("claude-opus-5-5") == "Opus 5.5"
    assert viewmodel.model_name("claude-sonnet-4-5-20250929") == "Sonnet 4.5"
    assert viewmodel.model_name("gpt-5.1-codex") == "gpt-5.1-codex"


def test_ring_is_tightest_current_limit():
    i18n.set_language("en")
    r = viewmodel.ring([snap()], NOW)
    assert r == {"available": True, "used": 41, "remaining": 59, "level": "ok", "limited": False,
                 "label": "Claude Code · 5-hour session"}
    low = snap(windows=[QuotaWindow("w", "Weekly", 93.0, NOW + 60, 10080)])
    assert viewmodel.ring([low], NOW)["level"] == "bad"
    lim = snap(windows=[QuotaWindow("five_hour", "5-hour session", 20.0, NOW + 60, 300, limited=True)])
    assert viewmodel.ring([lim], NOW)["remaining"] == 0 and viewmodel.ring([lim], NOW)["limited"]
    assert not viewmodel.ring([snap(quota=State.UNAVAILABLE)], NOW)["available"]


def test_limits_view_is_short():
    i18n.set_language("en")
    v = viewmodel.limits_view([snap(), snap("codex", State.NOT_INSTALLED, State.NOT_INSTALLED),
                               snap("antigravity", quota=State.NOT_AUTHENTICATED)], NOW)
    assert [p["id"] for p in v] == ["claude", "antigravity"]  # not installed: hidden
    assert v[0]["name"] == "Claude" and v[0]["windows"][0]["label"] == "5 hours"
    assert v[0]["windows"][0]["remaining"] == 59
    assert v[1]["message"] == "Not signed in · run antigravity login" and v[1]["level"] == "bad"


def test_tokens_view_groups_and_periods():
    i18n.set_language("en")
    t = viewmodel.tokens_view([snap(), snap("codex")], NOW)
    assert [g["key"] for g in t["groups"]] == ["all", "claude", "codex"]
    all7 = t["data"]["all"]["periods"]["7d"]
    assert all7["total"] == 2 * (1520 + 10)
    assert [m["name"] for m in all7["models"]] == ["model-a", "model-b"]
    assert len(t["data"]["claude"]["daily"]) == 7
    assert json.loads(json.dumps(viewmodel.widget_view([snap()], NOW)))["ring"]["available"]
