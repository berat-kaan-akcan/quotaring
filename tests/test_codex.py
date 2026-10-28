import time

from aiusage.model import State
from aiusage.providers.codex import CodexProvider, parse_codex_lines, windows_from_rate_limits
from conftest import iso, write_jsonl

NOW = time.time()


def tc(ts, total, last=None):
    info = {"total_token_usage": total}
    if last is not None:
        info["last_token_usage"] = last
    return {"timestamp": iso(ts), "type": "event_msg", "payload": {"type": "token_count", "info": info}}


def u(inp, cached, out, reasoning=0):
    return {"input_tokens": inp, "cached_input_tokens": cached, "output_tokens": out,
            "reasoning_output_tokens": reasoning, "total_tokens": inp + out}


def ctx(ts, model):
    return {"timestamp": iso(ts), "type": "turn_context", "payload": {"model": model, "cwd": "/x"}}


def run(lines, state=None):
    state = {} if state is None else state
    return parse_codex_lines(list(enumerate(lines)), state), state


def test_first_event_counts_last_usage_only():
    recs, _ = run([ctx(NOW, "gpt-x"), tc(NOW, u(1000, 400, 50), last=u(100, 40, 5))])
    (r,) = recs.values()
    assert r[1] == "gpt-x"
    assert r[2:5] == [60, 5, 40]  # input excl. cached, output, cache_read


def test_cumulative_deltas_and_repeats():
    recs, _ = run([
        tc(NOW, u(100, 0, 10), last=u(100, 0, 10)),
        tc(NOW, u(100, 0, 10), last=u(100, 0, 10)),  # repeated: ignored
        tc(NOW, u(250, 50, 30, 5)),
    ])
    vals = sorted(recs.values(), key=lambda r: r[3])
    assert [v[2:5] for v in vals] == [[100, 10, 0], [100, 20, 50]]
    assert vals[1][6] == 5


def test_counter_reset_uses_last_usage():
    recs, _ = run([
        tc(NOW, u(500, 0, 50), last=u(500, 0, 50)),
        tc(NOW, u(20, 0, 2), last=u(20, 0, 2)),  # went backwards (new context)
    ])
    assert sorted(r[2] for r in recs.values()) == [20, 500]


def test_modern_records_win_over_token_count():
    recs, state = run([
        ctx(NOW, "gpt-y"),
        {"timestamp": iso(NOW), "type": "event_msg",
         "payload": {"type": "token_usage_record", "response_id": "resp_1", "usage": u(10, 0, 3)}},
        tc(NOW, u(999, 0, 999), last=u(999, 0, 999)),
    ])
    assert list(recs) == ["r:resp_1"]
    assert state["modern"] is True


def test_malformed_events_ignored():
    recs, _ = run([
        {"type": "event_msg", "payload": {"type": "token_count"}},  # no timestamp
        {"timestamp": iso(NOW), "type": "event_msg", "payload": {"type": "token_count", "info": None}},
        {"timestamp": iso(NOW), "type": "event_msg", "payload": "nope"},
        {"timestamp": "garbage", "type": "event_msg", "payload": {"type": "token_count"}},
    ])
    assert recs == {}


def test_state_carries_across_scans(settings, tmp_path):
    f = tmp_path / "sessions" / "2026" / "10" / "28" / "rollout-1.jsonl"
    write_jsonl(f, [ctx(NOW - 100, "gpt-z"), tc(NOW - 100, u(100, 0, 10), last=u(100, 0, 10))])
    p = CodexProvider(settings, roots=[tmp_path / "sessions"])
    assert p.collect_local(NOW).period("all").total.input == 100
    with open(f, "a") as fh:
        import json
        fh.write(json.dumps(tc(NOW - 50, u(160, 0, 15))) + "\n")
    per = p.collect_local(NOW).period("all")
    assert per.total.input == 160 and per.events == 2
    assert set(per.by_model) == {"gpt-z"}


def test_missing_folder(settings, tmp_path):
    p = CodexProvider(settings, roots=[tmp_path / "nope"])
    assert p.collect_local(NOW).state == State.NOT_INSTALLED


def test_rate_limit_windows_parsing():
    payload = {"rateLimits": {
        "primary": {"usedPercent": 42.5, "windowDurationMins": 300, "resetsAt": 1900000000},
        "secondary": {"usedPercent": 7, "windowDurationMins": 10080, "resetsAt": 1900500000},
        "planType": "plus",
    }}
    w, plan = windows_from_rate_limits(payload)
    assert [x.label for x in w] == ["5-hour session", "Weekly"]
    assert w[0].used_percent == 42.5 and w[0].resets_at == 1900000000
    assert plan == "plus"


def test_rate_limit_windows_by_limit_id_and_bad_values():
    payload = {"rateLimitsByLimitId": {
        "codex": {"primary": {"usedPercent": 150, "windowDurationMins": 300, "resetsAt": None}},
        "other": {"limitName": "Spark", "primary": {"usedPercent": "x"},
                  "secondary": {"usedPercent": True}},
        "bad": "nope",
    }}
    w, _ = windows_from_rate_limits(payload)
    assert len(w) == 1
    assert w[0].used_percent == 100.0 and w[0].resets_at is None
