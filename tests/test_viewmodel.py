import json
import time

from aiusage import i18n, viewmodel
from aiusage.aggregate import aggregate, daily_totals
from aiusage.model import LocalUsage, ProviderSnapshot, Quota, QuotaWindow, State, Tokens, UsageEvent

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
    v = viewmodel.widget_view([snap()], NOW)
    v = json.loads(json.dumps(v))
    p = v["providers"][0]
    assert v["headline"] == "41%"
    assert [q["percentText"] for q in p["quota"]] == ["41%", "4%"]
    assert [x["label"] for x in p["local"]] == ["Today", "5 h", "7 d"]
    assert p["models"]["today"][0][0] == "model-a"
    assert {r[0] for r in p["models"]["7d"]} == {"model-a", "model-b"}
    assert len(p["daily"]) == 14 and max(d["ratio"] for d in p["daily"]) == 1
    assert "Chats 2%" in p["breakdown"]
    assert "may change without notice" in p["quotaSource"]
    assert len(v["labels"]["columns"]) == 5


def test_headline_ignores_windows_past_reset_and_unverified_quota():
    i18n.set_language("en")
    passed = snap(windows=[QuotaWindow("w", "Weekly", 99.0, NOW - 10, 10080),
                           QuotaWindow("s", "5-hour session", 12.0, NOW + 60, 300)])
    assert viewmodel.headline([passed], NOW) == "12%"
    assert viewmodel.headline([snap(quota=State.UNAVAILABLE)], NOW) == ""


def test_states_collapsed_and_stale():
    i18n.set_language("en")
    ni = viewmodel.provider_view(snap("codex", State.NOT_INSTALLED, State.NOT_INSTALLED), NOW)
    assert ni["collapsed"] and ni["pill"]["text"] == "Not installed" and ni["quota"] == []
    stale = viewmodel.provider_view(snap(quota=State.STALE), NOW)
    assert stale["pill"]["level"] == "warn"
    assert all(q["dim"] for q in stale["quota"])
    assert stale["quotaMessage"].startswith("Stale (last updated")
    local_only = viewmodel.provider_view(snap(quota=State.UNAVAILABLE), NOW)
    assert local_only["pill"]["text"] == "Local only" and local_only["quota"] == []


def test_turkish_view():
    i18n.set_language("tr")
    try:
        v = viewmodel.widget_view([snap()], NOW)
        assert v["headline"] == "%41"
        assert v["labels"]["quota"] == "HESAP KOTASI"
        assert v["providers"][0]["quota"][1]["label"] == "Haftalık"
    finally:
        i18n.set_language("en")


def test_widget_json_command_runs_isolated(capsys):
    """End to end on an empty (isolated) home: valid JSON, nothing installed, nothing invented."""
    from aiusage.app import widget_json
    assert widget_json() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["headline"] == ""
    assert {p["id"] for p in out["providers"]} == {"claude", "codex", "antigravity"}
    assert all(p["quota"] == [] for p in out["providers"])


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
