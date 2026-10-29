import json
import time

from quotaring.engine import RATE_LIMIT_BACKOFF, Engine, merge_local, merge_quota
from quotaring.model import LocalUsage, PeriodUsage, Quota, QuotaWindow, State, Tokens
from quotaring.providers.base import Provider, QuotaError, classify_error_text, with_retries

NOW = time.time()


class Boom(Provider):
    id = "boom"
    name = "Boom"

    def _collect_local(self, now):
        raise RuntimeError("secret payload should not leak")

    def _collect_quota(self, now):
        raise KeyError("x")


class Good(Provider):
    id = "good"
    name = "Good"
    quota_state = State.OK

    def _collect_local(self, now):
        return LocalUsage(State.OK, [PeriodUsage("all", "All", Tokens(input=5))])

    def _collect_quota(self, now):
        if self.quota_state != State.OK:
            raise QuotaError(self.quota_state, "failed")
        return Quota(State.OK, [QuotaWindow("w", "W", 10.0, NOW + 100)])


def ok_local():
    return LocalUsage(State.OK, [PeriodUsage("all", "All", Tokens(input=1))], updated_at=1.0)


def ok_quota():
    return Quota(State.OK, [QuotaWindow("w", "W", 50.0)], plan="Pro", updated_at=1.0)


def test_provider_exceptions_are_isolated(settings):
    p = Boom(settings)
    loc = p.collect_local(NOW)
    assert loc.state == State.UNAVAILABLE and "secret" not in loc.detail
    q = p.collect_quota(NOW)
    assert q.state == State.UNAVAILABLE and q.updated_at == NOW


def test_merge_local_keeps_last_good_as_stale():
    m = merge_local(ok_local(), LocalUsage(State.UNAVAILABLE, detail="disk error"))
    assert m.state == State.STALE and m.periods and m.updated_at == 1.0 and m.detail == "disk error"
    assert merge_local(ok_local(), LocalUsage(State.NOT_INSTALLED)).state == State.NOT_INSTALLED
    assert merge_local(None, LocalUsage(State.UNAVAILABLE)).state == State.UNAVAILABLE


def test_merge_quota_stale_only_for_transient_failures():
    assert merge_quota(ok_quota(), Quota(State.UNAVAILABLE)).state == State.STALE
    assert merge_quota(ok_quota(), Quota(State.RATE_LIMITED)).state == State.STALE
    # auth expiry must be visible, not hidden behind old numbers
    assert merge_quota(ok_quota(), Quota(State.NOT_AUTHENTICATED)).state == State.NOT_AUTHENTICATED
    assert merge_quota(ok_quota(), Quota(State.OK, [])).state == State.OK


def test_engine_cache_roundtrip_marks_stale(settings, tmp_path):
    path = tmp_path / "snap.json"
    e = Engine(settings, [Good(settings)], cache_path=path)
    e.apply_local("good", e.run_local("good", NOW))
    e.apply_quota("good", e.run_quota("good", NOW), NOW)
    e.save_cache()
    e2 = Engine(settings, [Good(settings)], cache_path=path)
    snap = e2.snapshots["good"]
    assert snap.local.state == State.STALE and snap.local.period("all").total.input == 5
    assert snap.quota.state == State.STALE and snap.quota.windows[0].used_percent == 10.0


def test_engine_corrupt_cache_ignored(settings, tmp_path):
    path = tmp_path / "snap.json"
    path.write_text("{broken")
    assert Engine(settings, [Good(settings)], cache_path=path).snapshots["good"].local.state == State.PENDING
    path.write_text(json.dumps({"version": 1, "snapshots": {"good": {"bad": 1}}}))
    assert Engine(settings, [Good(settings)], cache_path=path).snapshots["good"].local.state == State.PENDING


def test_quota_scheduling_and_rate_limit_backoff(settings, tmp_path):
    g = Good(settings)
    e = Engine(settings, [g], cache_path=tmp_path / "s.json")
    assert e.quota_due("good", NOW)
    e.apply_quota("good", e.run_quota("good", NOW), NOW)
    assert not e.quota_due("good", NOW + 10)
    assert e.quota_due("good", NOW + settings.quota_refresh_seconds)
    assert e.quota_due("good", NOW + 10, force=True)
    g.quota_state = State.RATE_LIMITED
    snap = e.apply_quota("good", e.run_quota("good", NOW), NOW)
    assert snap.quota.state == State.STALE  # last good numbers kept, marked stale
    assert not e.quota_due("good", NOW + RATE_LIMIT_BACKOFF - 1)


def test_disabled_provider(settings, tmp_path):
    settings.providers_enabled["good"] = False
    e = Engine(settings, [Good(settings)], cache_path=tmp_path / "s.json")
    assert e.run_local("good", NOW).state == State.DISABLED
    assert e.run_quota("good", NOW).state == State.DISABLED


def test_busy_guard(settings, tmp_path):
    e = Engine(settings, [Good(settings)], cache_path=tmp_path / "s.json")
    assert e.try_begin("good", "local")
    assert not e.try_begin("good", "local")
    e.end("good", "local")
    assert e.try_begin("good", "local")


def test_classify_error_text():
    assert classify_error_text("HTTP 429 Too Many Requests").state == State.RATE_LIMITED
    assert classify_error_text("401 Unauthorized").state == State.NOT_AUTHENTICATED
    assert classify_error_text("403 Forbidden").state == State.NOT_AUTHENTICATED
    e = classify_error_text("request timed out")
    assert e.state == State.UNAVAILABLE and e.transient
    other = classify_error_text("Bearer sk-ant-abc123 something odd")
    assert "sk-ant" not in other.detail


def test_with_retries_backoff():
    calls, sleeps = [], []

    def flaky():
        calls.append(1)
        if len(calls) < 3:
            raise QuotaError(State.UNAVAILABLE, "x", transient=True)
        return "ok"

    assert with_retries(flaky, attempts=3, sleep=sleeps.append) == "ok"
    assert sleeps == [1.0, 2.0]

    def auth():
        calls.append(1)
        raise QuotaError(State.NOT_AUTHENTICATED, "no")

    calls.clear()
    try:
        with_retries(auth, attempts=3, sleep=sleeps.append)
    except QuotaError as e:
        assert e.state == State.NOT_AUTHENTICATED
    assert len(calls) == 1  # non-transient: no retry
