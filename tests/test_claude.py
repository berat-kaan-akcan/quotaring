import json
import time

from aiusage.model import State
from aiusage.providers.claude import ClaudeProvider, parse_claude_line
from conftest import iso, write_jsonl

NOW = time.time()


def assistant(mid, ts, inp=10, out=5, cr=100, cw=20, model="claude-test-1", req="req_1", **extra):
    d = {
        "type": "assistant",
        "timestamp": iso(ts),
        "requestId": req,
        "sessionId": "s1",
        "message": {
            "id": mid,
            "model": model,
            "role": "assistant",
            "usage": {
                "input_tokens": inp,
                "output_tokens": out,
                "cache_read_input_tokens": cr,
                "cache_creation_input_tokens": cw,
                "some_future_field": {"x": 1},
            },
        },
    }
    d.update(extra)
    return d


def provider(settings, tmp_path):
    return ClaudeProvider(settings, roots=[tmp_path / "projects"])


def today(p):
    return p.collect_local(NOW).period("all")


def test_parse_line_basic_and_unknown_fields():
    key, rec = parse_claude_line(assistant("m1", NOW))
    assert key == "m1:req_1"
    assert rec[1:] == ["claude-test-1", 10, 5, 100, 20, 0]


def test_parse_line_rejects_non_usage_and_synthetic():
    assert parse_claude_line({"type": "user", "message": {"content": "x"}}) is None
    assert parse_claude_line(assistant("m1", NOW, model="<synthetic>")) is None
    bad = assistant("m1", NOW)
    bad["message"]["usage"] = "oops"
    assert parse_claude_line(bad) is None
    no_ts = assistant("m1", NOW)
    no_ts["timestamp"] = "not a date"
    assert parse_claude_line(no_ts) is None
    err = assistant("m1", NOW, isApiErrorMessage=True)
    assert parse_claude_line(err) is None


def test_parse_line_tolerates_bad_numbers():
    d = assistant("m1", NOW)
    d["message"]["usage"].update(input_tokens=None, output_tokens="7", cache_read_input_tokens=-5,
                                 cache_creation_input_tokens=True)
    _, rec = parse_claude_line(d)
    assert rec[2:6] == [0, 7, 0, 0]


def test_missing_folder_is_not_installed(settings, tmp_path):
    u = provider(settings, tmp_path).collect_local(NOW)
    assert u.state == State.NOT_INSTALLED


def test_empty_folder_is_ok_with_zero(settings, tmp_path):
    (tmp_path / "projects").mkdir()
    u = provider(settings, tmp_path).collect_local(NOW)
    assert u.state == State.OK
    assert u.period("all").total.total == 0


def test_streaming_duplicates_take_max(settings, tmp_path):
    write_jsonl(tmp_path / "projects" / "p" / "a.jsonl", [
        assistant("m1", NOW - 60, out=1),
        assistant("m1", NOW - 60, out=50),  # same response, later partial with more output
        assistant("m1", NOW - 60, out=50),
        assistant("m1", NOW - 60, out=20, cr=300),  # component-wise max, not last-wins
    ])
    per = today(provider(settings, tmp_path))
    assert per.events == 1
    assert per.total.output == 50
    assert per.total.cache_read == 300
    assert per.total.total == 10 + 50 + 300 + 20


def test_duplicates_across_files_counted_once(settings, tmp_path):
    rows = [assistant("m1", NOW - 60), assistant("m2", NOW - 30, req="req_2")]
    write_jsonl(tmp_path / "projects" / "p" / "a.jsonl", rows)
    write_jsonl(tmp_path / "projects" / "p" / "resumed.jsonl", rows + [assistant("m3", NOW - 10, req="r3")])
    per = today(provider(settings, tmp_path))
    assert per.events == 3


def test_malformed_lines_and_partial_tail(settings, tmp_path):
    write_jsonl(tmp_path / "projects" / "a.jsonl",
                ["{not json", json.dumps([1, 2]), "", assistant("m1", NOW - 5)],
                trailing_partial='{"type":"assistant","message":{"usage"')
    per = today(provider(settings, tmp_path))
    assert per.events == 1


def test_incremental_append_and_truncate(settings, tmp_path):
    f = tmp_path / "projects" / "a.jsonl"
    write_jsonl(f, [assistant("m1", NOW - 50)])
    p = provider(settings, tmp_path)
    assert today(p).events == 1
    offset = p._states.files[str(f)]["offset"]
    with open(f, "a") as fh:
        fh.write(json.dumps(assistant("m2", NOW - 40, req="r2")) + "\n")
    assert today(p).events == 2
    assert p._states.files[str(f)]["offset"] > offset
    # Rewritten (shorter) file: re-read from scratch
    write_jsonl(f, [assistant("m9", NOW - 30, req="r9")])
    assert today(p).events == 1


def test_scan_cache_persists_between_instances(settings, tmp_path):
    write_jsonl(tmp_path / "projects" / "a.jsonl", [assistant("m1", NOW - 50)])
    assert today(provider(settings, tmp_path)).events == 1
    p2 = provider(settings, tmp_path)
    assert today(p2).events == 1  # loaded from cache, file unchanged


def test_periods_and_models(settings, tmp_path):
    write_jsonl(tmp_path / "projects" / "a.jsonl", [
        assistant("m1", NOW - 60, model="claude-a"),
        assistant("m2", NOW - 6 * 3600, model="claude-b", req="r2"),
        assistant("m3", NOW - 3 * 86400, model="claude-b", req="r3"),
        assistant("m4", NOW - 20 * 86400, model="claude-a", req="r4"),
    ])
    u = provider(settings, tmp_path).collect_local(NOW)
    assert u.period("5h").events == 1
    assert u.period("7d").events == 3
    assert u.period("30d").events == 4
    assert set(u.period("30d").by_model) == {"claude-a", "claude-b"}
