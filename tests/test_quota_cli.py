"""Quota collection against fake provider CLIs speaking the real wire protocols."""

import time

import pytest

from quotaring.model import State
from quotaring.providers.claude import ClaudeProvider
from quotaring.providers.codex import CodexProvider
from conftest import fake_cli

NOW = time.time()

CLAUDE_TEMPLATE = """
import json, sys, time
MODE = {mode!r}
for line in sys.stdin:
    msg = json.loads(line)
    rid = msg["request_id"]; kind = msg["request"]["subtype"]
    def reply(body=None, error=None):
        r = {{"subtype": "error", "request_id": rid, "error": error}} if error else \\
            {{"subtype": "success", "request_id": rid, "response": body}}
        print(json.dumps({{"type": "control_response", "response": r}}), flush=True)
    print("not json noise", flush=True)
    print(json.dumps({{"type": "system", "subtype": "ui_invalidate"}}), flush=True)
    if kind == "initialize":
        if MODE == "hang":
            time.sleep(60)
        if MODE == "exit":
            sys.exit(1)
        reply({{"account": {{"tokenSource": "none" if MODE == "nologin" else "oauth"}}}})
    elif kind == "get_usage":
        if MODE == "unsupported":
            reply(error="Unsupported control request subtype: get_usage")
        elif MODE == "ratelimit":
            reply(error="API error 429: rate_limit_error")
        elif MODE == "auth":
            reply(error="401 OAuth token has expired")
        elif MODE == "apikey":
            reply({{"rate_limits_available": False, "subscription_type": None}})
        elif MODE == "malformed":
            reply("a string")
        elif MODE == "nolimits":
            reply({{"subscription_type": "pro", "rate_limits_available": True, "rate_limits": None}})
        elif MODE == "v312":
            reply({{"subscription_type": "pro", "rate_limits_available": True, "rate_limits": {{
                "five_hour": {{"utilization": 100, "resets_at": "2030-01-01T10:00:00Z"}},
                "seven_day": {{"utilization": 40, "resets_at": "2030-01-05T10:00:00Z"}},
                "seven_day_sonnet": {{"utilization": 9, "resets_at": "2030-01-05T10:00:00Z"}},
                "model_scoped": [{{"display_name": "Fable", "utilization": 55, "resets_at": "2030-01-05T10:00:00Z"}},
                                 {{"display_name": "Sonnet", "utilization": 9, "resets_at": None}},
                                 {{"display_name": "Bad", "utilization": None, "resets_at": None}}],
                "extra_usage": None}}}})
        else:
            reply({{"subscription_type": "max", "rate_limits_available": True, "rate_limits": {{
                "five_hour": {{"utilization": 31, "resets_at": "2030-01-01T10:00:00Z"}},
                "seven_day": {{"utilization": 77.5, "resets_at": "2030-01-05T10:00:00+00:00"}},
                "seven_day_opus": None,
                "limits": [{{"kind": "weekly_scoped", "percent": 12, "resets_at": "2030-01-05T10:00:00Z",
                            "scope": {{"model": {{"display_name": "Opus"}}}}}},
                           {{"kind": "session", "percent": 31}}],
                "seven_day_breakdown": {{"rows": [{{"key": "claude_code", "display_name": "Claude Code", "percent": 70}},
                                                 {{"key": "chat", "display_name": "Chats", "percent": 7.5}}]}}
            }}}})
"""


def claude(settings, tmp_path, mode):
    settings.claude_command = fake_cli(tmp_path, "claude", CLAUDE_TEMPLATE.format(mode=mode))
    return ClaudeProvider(settings, roots=[tmp_path]).collect_quota(NOW)


def test_claude_quota_ok(settings, tmp_path):
    q = claude(settings, tmp_path, "ok")
    assert q.state == State.OK
    assert q.plan == "Max"
    assert [(w.key, w.used_percent) for w in q.windows] == [
        ("five_hour", 31.0), ("seven_day", 77.5), ("weekly:Opus", 12.0)]
    assert q.windows[0].resets_at == pytest.approx(1893492000)
    assert q.extra["weekly_breakdown"][1] == {"key": "chat", "label": "Chats", "percent": 7.5}
    assert q.documented is False and q.updated_at == NOW


def test_claude_quota_cli_2_1_312_shape(settings, tmp_path):
    q = claude(settings, tmp_path, "v312")
    assert q.state == State.OK
    assert [(w.key, w.label, w.used_percent) for w in q.windows] == [
        ("five_hour", "5-hour session", 100.0), ("seven_day", "Weekly", 40.0),
        ("seven_day_sonnet", "Weekly · Sonnet", 9.0), ("weekly:Fable", "Weekly · Fable", 55.0)]


@pytest.mark.parametrize("mode,state", [
    ("nolimits", State.UNAVAILABLE),
    ("nologin", State.NOT_AUTHENTICATED),
    ("auth", State.NOT_AUTHENTICATED),
    ("ratelimit", State.RATE_LIMITED),
    ("unsupported", State.UNSUPPORTED),
    ("apikey", State.UNSUPPORTED),
    ("malformed", State.UNAVAILABLE),
    ("exit", State.UNAVAILABLE),
])
def test_claude_quota_failures(settings, tmp_path, mode, state, monkeypatch):
    monkeypatch.setattr("quotaring.providers.base.time.sleep", lambda s: None)
    q = claude(settings, tmp_path, mode)
    assert q.state == state
    assert q.windows == []
    assert "token" not in q.detail.lower() or state == State.NOT_AUTHENTICATED


def test_claude_quota_timeout(settings, tmp_path, monkeypatch):
    monkeypatch.setattr("quotaring.providers.base.time.sleep", lambda s: None)
    settings.timeout_seconds = 1
    start = time.monotonic()
    q = claude(settings, tmp_path, "hang")
    assert q.state == State.UNAVAILABLE
    assert "timed out" in q.detail
    assert time.monotonic() - start < 15  # 3 attempts x 1 s + process cleanup


def test_claude_not_installed(settings, tmp_path):
    settings.claude_command = str(tmp_path / "does-not-exist")
    q = ClaudeProvider(settings, roots=[tmp_path]).collect_quota(NOW)
    assert q.state == State.NOT_INSTALLED


CODEX_TEMPLATE = """
import json, sys, time
MODE = {mode!r}
for line in sys.stdin:
    msg = json.loads(line)
    if "id" not in msg:
        continue
    mid, method = msg["id"], msg["method"]
    out = lambda o: print(json.dumps(o), flush=True)
    out({{"method": "some/notification", "params": {{}}}})
    if method == "initialize":
        out({{"id": mid, "result": {{"userAgent": "fake"}}}})
    elif method == "account/read":
        if MODE == "nologin":
            out({{"id": mid, "result": {{"account": None, "requiresOpenaiAuth": True}}}})
        elif MODE == "apikey":
            out({{"id": mid, "result": {{"account": {{"type": "apiKey"}}}}}})
        else:
            out({{"id": mid, "result": {{"account": {{"type": "chatgpt", "planType": "pro"}}}}}})
    elif method == "account/rateLimits/read":
        if MODE == "ratelimit":
            out({{"id": mid, "error": {{"code": -32000, "message": "HTTP 429 Too Many Requests"}}}})
        elif MODE == "hang":
            time.sleep(60)
        elif MODE == "empty":
            out({{"id": mid, "result": {{"rateLimits": {{}}}}}})
        else:
            out({{"id": mid, "result": {{"rateLimits": {{
                "primary": {{"usedPercent": 12, "windowDurationMins": 300, "resetsAt": 1900000000}},
                "secondary": {{"usedPercent": 64, "windowDurationMins": 10080, "resetsAt": 1900400000}}}}}}}})
"""


def codex(settings, tmp_path, mode):
    settings.codex_command = fake_cli(tmp_path, "codex", CODEX_TEMPLATE.format(mode=mode))
    return CodexProvider(settings, roots=[tmp_path]).collect_quota(NOW)


def test_codex_quota_ok(settings, tmp_path):
    q = codex(settings, tmp_path, "ok")
    assert q.state == State.OK and q.documented
    assert q.plan == "Pro"
    assert [(w.label, w.used_percent) for w in q.windows] == [("5-hour session", 12.0), ("Weekly", 64.0)]


def test_claude_quota_cli_2_1_312_shape(settings, tmp_path):
    q = claude(settings, tmp_path, "v312")
    assert q.state == State.OK
    assert [(w.key, w.label, w.used_percent) for w in q.windows] == [
        ("five_hour", "5-hour session", 100.0), ("seven_day", "Weekly", 40.0),
        ("seven_day_sonnet", "Weekly · Sonnet", 9.0), ("weekly:Fable", "Weekly · Fable", 55.0)]


@pytest.mark.parametrize("mode,state", [
    ("nologin", State.NOT_AUTHENTICATED),
    ("apikey", State.UNSUPPORTED),
    ("ratelimit", State.RATE_LIMITED),
    ("empty", State.UNAVAILABLE),
])
def test_codex_quota_states(settings, tmp_path, mode, state):
    assert codex(settings, tmp_path, mode).state == state


def test_codex_quota_timeout(settings, tmp_path, monkeypatch):
    monkeypatch.setattr("quotaring.providers.base.time.sleep", lambda s: None)
    settings.timeout_seconds = 1
    q = codex(settings, tmp_path, "hang")
    assert q.state == State.UNAVAILABLE and "timed out" in q.detail


def test_claude_native_install_fallback(settings, tmp_path, isolated_dirs):
    import os
    from quotaring.providers import claude as cmod
    versions = isolated_dirs / "home" / ".local" / "share" / "claude" / "versions"
    versions.mkdir(parents=True)
    for v in ("2.1.9", "2.1.312", "2.1.40"):
        f = versions / v
        f.write_text("#!/bin/sh\n")
        os.chmod(f, 0o755)
    (versions / "notes.txt").write_text("x")
    assert cmod.native_install_binary().endswith("2.1.312")


def test_shutdown_kills_running_query_and_stops_retries(settings, tmp_path):
    import threading
    from quotaring.providers import base
    settings.timeout_seconds = 30
    settings.claude_command = fake_cli(tmp_path, "claude", CLAUDE_TEMPLATE.format(mode="hang"))
    out = {}
    t = threading.Thread(target=lambda: out.setdefault("q", ClaudeProvider(settings, roots=[tmp_path]).collect_quota(NOW)))
    start = time.monotonic()
    t.start()
    deadline = time.monotonic() + 10
    while not base._live and time.monotonic() < deadline:
        time.sleep(0.05)
    try:
        base.shutdown_children()
        t.join(10)
    finally:
        base._shutdown.clear()
    assert not t.is_alive()
    assert time.monotonic() - start < 8  # not 3 x 30 s
    assert out["q"].state == State.UNAVAILABLE
