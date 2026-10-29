"""Limit-reached evidence from Claude Code's logged 429 responses, and how it is shown."""

import time

import pytest

from aiusage import i18n, viewmodel
from aiusage.engine import NEAR_LIMIT_INTERVAL, Engine
from aiusage.model import LocalUsage, ProviderSnapshot, Quota, QuotaWindow, State
from aiusage.providers.base import Provider, QuotaError
from aiusage.providers.claude import ClaudeProvider, apply_limit_hit, parse_limit_hit
from aiusage.ui import format as fmt
from conftest import iso, write_jsonl
from test_claude import assistant

NOW = time.time()


def hit_record(ts, reset, kind="five_hour", status="rejected"):
    """Shape of the synthetic message Claude Code logs when a limit blocks a request."""
    return {"type": "assistant", "timestamp": iso(ts), "isApiErrorMessage": True, "error": "rate_limit",
            "message": {"id": "x", "model": "<synthetic>", "role": "assistant",
                        "content": [{"type": "text", "text": "You've hit your limit"}],
                        "usage": {"input_tokens": 0, "output_tokens": 0}},
            "quotaLimits": {"status": status, "resetsAt": int(reset), "rateLimitType": kind,
                            "overageStatus": "rejected", "isUsingOverage": False}}


def test_parse_limit_hit():
    ts, kind, reset = parse_limit_hit(hit_record(NOW, NOW + 600))
    assert ts == pytest.approx(NOW, abs=1) and kind == "five_hour" and reset == float(int(NOW + 600))
    assert parse_limit_hit(hit_record(NOW, NOW + 600, status="allowed")) is None
    assert parse_limit_hit({"quotaLimits": {"status": "rejected", "resetsAt": True, "rateLimitType": "x"},
                            "timestamp": iso(NOW)}) is None
    assert parse_limit_hit({"quotaLimits": "rejected"}) is None


def test_scan_finds_latest_hit_and_not_counted_as_usage(settings, tmp_path):
    proj = tmp_path / "projects" / "p"
    write_jsonl(proj / "a.jsonl", [assistant("m1", NOW - 100), hit_record(NOW - 3000, NOW - 60),
                                   hit_record(NOW - 50, NOW + 900)])
    write_jsonl(proj / "b.jsonl", [hit_record(NOW - 4000, NOW + 100, kind="seven_day")])
    p = ClaudeProvider(settings, roots=[tmp_path / "projects"])
    loc = p.collect_local(NOW)
    assert loc.period("all").events == 1  # the synthetic message is not usage
    assert p.limit_hit[1:] == ["five_hour", float(int(NOW + 900))]


def test_apply_limit_hit_overrides_polled_and_failed_quota():
    hit = [NOW - 10, "five_hour", NOW + 900]
    polled = Quota(State.OK, [QuotaWindow("five_hour", "5-hour session", 64.0, NOW + 800, 300),
                              QuotaWindow("seven_day", "Weekly", 20.0, NOW + 9e5, 10080)], plan="Pro")
    q = apply_limit_hit(polled, hit, NOW)
    assert q.state == State.OK and q.plan == "Pro"
    assert [(w.key, w.used_percent, w.limited) for w in q.windows] == [
        ("five_hour", 100.0, True), ("seven_day", 20.0, False)]
    assert q.windows[0].resets_at == NOW + 900
    assert polled.windows[0].used_percent == 64.0  # input untouched

    failed = apply_limit_hit(Quota(State.UNAVAILABLE, detail="Usage endpoint returned no data"), hit, NOW)
    assert failed.state == State.OK and failed.windows[0].active_limit(NOW)
    assert "local log" in failed.source

    assert apply_limit_hit(polled, [NOW - 10, "five_hour", NOW - 1], NOW) is polled  # already reset
    assert apply_limit_hit(Quota(State.UNSUPPORTED), hit, NOW).state == State.UNSUPPORTED
    assert not failed.windows[0].active_limit(NOW + 901)


class Fake(Provider):
    id = "claude"
    name = "Claude Code"
    windows = [QuotaWindow("five_hour", "5-hour session", 50.0, NOW + 3600, 300)]
    hit = None

    def _collect_local(self, now):
        return LocalUsage(State.OK, updated_at=now)

    def _collect_quota(self, now):
        if self.windows is None:
            raise QuotaError(State.UNAVAILABLE, "Usage endpoint returned no data", transient=True)
        return Quota(State.OK, list(self.windows))

    def overlay_quota(self, quota, now):
        return apply_limit_hit(quota, self.hit, now)


def test_engine_shows_hit_from_local_scan_before_next_poll(settings, tmp_path):
    f = Fake(settings)
    e = Engine(settings, [f], cache_path=tmp_path / "s.json")
    e.apply_quota("claude", e.run_quota("claude", NOW), NOW)
    assert not e.snapshots["claude"].quota.windows[0].limited
    f.hit = [NOW, "five_hour", NOW + 3600]
    snap = e.apply_local("claude", e.run_local("claude", NOW))  # quota not due yet
    assert snap.quota.windows[0].active_limit(NOW)
    f.windows = None  # next poll fails: still shown as reached, not the old 50 %
    snap = e.apply_quota("claude", e.run_quota("claude", NOW + 400), NOW + 400)
    assert snap.quota.state == State.STALE and snap.quota.windows[0].active_limit(NOW + 400)


def test_engine_polls_faster_near_a_limit(settings, tmp_path):
    f = Fake(settings)
    f.windows = [QuotaWindow("five_hour", "5-hour session", 85.0, NOW + 3600, 300)]
    e = Engine(settings, [f], cache_path=tmp_path / "s.json")
    e.apply_quota("claude", e.run_quota("claude", NOW), NOW)
    assert e.next_quota_at["claude"] == NOW + min(settings.quota_refresh_seconds, NEAR_LIMIT_INTERVAL)


def test_views_say_limit_reached():
    i18n.set_language("en")
    w = QuotaWindow("five_hour", "5-hour session", 100.0, NOW + 600, 300, limited=True)
    snap = ProviderSnapshot("claude", "Claude Code", LocalUsage(State.OK),
                            Quota(State.STALE, [w, QuotaWindow("seven_day", "Weekly", 3.0, NOW + 9e5)],
                                  detail="Usage endpoint returned no data"))
    v = viewmodel.provider_view(snap, NOW)
    assert v["quota"][0]["percentText"] == "Limit reached" and v["quota"][0]["limited"]
    assert not v["quota"][0]["dim"] and v["quota"][1]["dim"]
    assert viewmodel.headline([snap], NOW) == "Limit reached"
    assert "Limit reached" in fmt.summary([snap], NOW)
    assert viewmodel.headline([snap], NOW + 601) == "3%"  # after the reset the hit no longer applies
    i18n.set_language("tr")
    try:
        assert fmt.window_pct(w, NOW) == "Limit doldu"
    finally:
        i18n.set_language("en")


def test_window_roundtrip_keeps_flag_and_old_caches_load():
    w = QuotaWindow("five_hour", "5-hour session", 100.0, NOW + 1, 300, limited=True)
    assert QuotaWindow.from_dict(w.to_dict()) == w
    assert QuotaWindow.from_dict({"key": "k", "label": "L", "used_percent": 1.0}).limited is False


def test_alerts_once_per_window_and_shared(tmp_path):
    from aiusage import alerts
    i18n.set_language("en")
    lim = QuotaWindow("five_hour", "5-hour session", 100.0, NOW + 600, 300, limited=True)
    hi = QuotaWindow("seven_day", "Weekly", 92.0, NOW + 9e5, 10080)
    snap = ProviderSnapshot("claude", "Claude Code", LocalUsage(State.OK), Quota(State.OK, [lim, hi]))
    found = alerts.pending([snap], 90, NOW)
    assert [a["title"] for a in found] == ["Claude Code: 5-hour session limit reached",
                                          "Claude Code: Weekly at 92%"]
    first, second = alerts.Seen(tmp_path / "n.json"), alerts.Seen(tmp_path / "n.json")  # app + widget
    assert len(first.take_new(found, NOW)) == 2
    assert second.take_new(alerts.pending([snap], 90, NOW), NOW) == []
    stale = ProviderSnapshot("claude", "Claude Code", LocalUsage(State.OK), Quota(State.STALE, [lim, hi]))
    assert [a["key"].endswith("|limit") for a in alerts.pending([stale], 90, NOW)] == [True]
    assert alerts.pending([snap], 0, NOW) == []  # notifications switched off
    # after the reset a new window can alert again; expired keys are pruned
    nxt = QuotaWindow("five_hour", "5-hour session", 100.0, NOW + 18600, 300, limited=True)
    snap2 = ProviderSnapshot("claude", "Claude Code", LocalUsage(State.OK), Quota(State.OK, [nxt]))
    assert len(first.take_new(alerts.pending([snap2], 90, NOW + 700), NOW + 700)) == 1
