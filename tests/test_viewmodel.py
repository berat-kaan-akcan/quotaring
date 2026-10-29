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
    assert viewmodel.model_name("claude-opus-5-5-medium") == "Opus 5.5"
    assert viewmodel.model_name("gemini-3.8-flash-n") == "Gemini 3.8 Flash"
    assert viewmodel.model_name("gemini-4-argon-trial") == "Gemini 4 Argon"
    assert viewmodel.model_name("gemini-pro-default") == "Gemini Pro"


def test_cost_at_api_prices():
    from quotaring import pricing
    t = Tokens(input=1_000_000, output=1_000_000, cache_read=10_000_000, cache_write=1_000_000)
    assert pricing.cost("claude-opus-5-5", t) == 4 + 20 + 2 + 5
    assert pricing.cost("claude-opus-4-7", t) == 5 + 25 + 5 + 6.25
    assert pricing.cost("gemini-3.8-flash-n", Tokens(input=1_000_000)) == 0.75
    assert pricing.cost("mystery", t) is None
    snap_ = ProviderSnapshot("claude", "Claude Code", LocalUsage(State.OK, aggregate(
        [UsageEvent(NOW - 60, "claude-opus-5-5", Tokens(input=500_000, output=100_000))], NOW)), Quota(State.OK))
    today = viewmodel.tokens_view([snap_], NOW)["data"]["claude"]["periods"]["today"]
    assert today["costText"] == "$4.00" and not today["unpriced"]
    assert today["models"][0]["cost"] == "$4.00" and today["models"][0]["parts"]["output"] == "100K"
    assert today["providers"] == [{"name": "Claude", "color": viewmodel.COLORS["claude"], "text": "600K",
                                   "cost": "$4.00"}]


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
    # The same model under two providers stays two rows: their prices can differ.
    assert [(m["name"], m["provider"]) for m in all7["models"]] == [
        ("model-a", "Claude"), ("model-a", "Claude"), ("model-b", "Claude"), ("model-b", "Claude")]
    assert all7["unpriced"] and all7["costText"] == "$0.00" and all7["models"][0]["cost"] == "—"
    assert len(t["data"]["claude"]["daily"]) == 7
    assert json.loads(json.dumps(viewmodel.widget_view([snap()], NOW)))["ring"]["available"]


def test_antigravity_models_one_row_each_with_ring_pair():
    i18n.set_language("en")
    windows = [QuotaWindow("g5", "5-hour session · Gemini", 10.0, NOW + 3600, 300),
               QuotaWindow("gw", "Weekly · Gemini", 1.0, NOW + 5 * 86400, 10080),
               QuotaWindow("p5", "5-hour session · Claude and GPT", 0.0, NOW + 3600, 300),
               QuotaWindow("pw", "Weekly · Claude and GPT", 12.0, NOW + 5 * 86400, 10080),
               QuotaWindow("aw", "Weekly · Gemini 4 Argon", 22.0, NOW + 5 * 86400, 10080)]
    q = Quota(State.OK, windows, extra={"models": [
        {"name": "Gemini 4 Argon", "windows": ["aw"]}, {"name": "Gemini 3.8 Flash", "windows": ["g5", "gw"]},
        {"name": "Claude Opus 5.5", "windows": ["p5", "pw"]}, {"name": "Claude Sonnet 5.5", "windows": ["p5", "pw"]}]})
    item = viewmodel.limits_view([ProviderSnapshot("antigravity", "Antigravity", LocalUsage(State.OK), q)], NOW)[0]
    rows = item["windows"]
    assert [(r["label"], r["tag"], r["remaining"]) for r in rows] == [
        ("Gemini 4 Argon", "GA", 78), ("Gemini 3.8 Flash", "GF", 90), ("Claude Opus 5.5", "CO", 88),
        ("Claude Sonnet 5.5", "CS", 88)]
    assert [w["tag"] for w in rows[1]["pair"]] == ["5h", "W"] and len(rows[0]["pair"]) == 1
    assert rows[2]["reset"].startswith("W · ")
    json.dumps(item)
