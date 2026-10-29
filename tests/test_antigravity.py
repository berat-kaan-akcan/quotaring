import os
import sqlite3
import time

from quotaring import protowire as pw
from quotaring.model import State
from quotaring.providers.antigravity import AntigravityProvider, parse_generation

NOW = time.time()


# --- tiny protobuf encoder for synthetic fixtures -----------------------------
def varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def f_int(field: int, v: int) -> bytes:
    return varint(field << 3) + varint(v)


def f_bytes(field: int, b: bytes) -> bytes:
    return varint(field << 3 | 2) + varint(len(b)) + b


def generation(inp, out, cr=0, cw=0, think=0, model=b"gemini-test", steps=(0,), packed=True):
    usage = f_int(1, 1318) + f_int(2, inp) + f_int(3, out) + f_int(4, cw) + f_int(5, cr) + f_int(9, think)
    usage += f_bytes(8, f_bytes(1, b"x-header") + f_bytes(2, b"v"))  # map entry, ignored
    chat = f_bytes(1, b"system prompt text") + f_bytes(4, usage) + f_bytes(19, model)
    retry = f_bytes(2, usage)  # retry_infos[].usage mirrors usage; must not be counted again
    chat += f_bytes(17, retry)
    if packed:
        idx = f_bytes(2, b"".join(varint(s) for s in steps))
    else:
        idx = b"".join(f_int(2, s) for s in steps)
    return f_bytes(1, chat) + idx + f_bytes(4, b"exec-id")


def step_meta(ts: int) -> bytes:
    return f_bytes(1, f_int(1, ts) + f_int(2, 5000))


def make_db(path, gens, steps=None, tables=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    if tables:
        con.execute("CREATE TABLE steps (idx integer PRIMARY KEY, step_type integer, metadata blob)")
        con.execute("CREATE TABLE gen_metadata (idx integer PRIMARY KEY, data blob, size integer)")
        for i, ts in (steps or {}).items():
            con.execute("INSERT INTO steps VALUES (?, 1, ?)", (i, step_meta(ts)))
        for i, g in enumerate(gens):
            con.execute("INSERT INTO gen_metadata VALUES (?, ?, ?)", (i, g, len(g) if g else 0))
    else:
        con.execute("CREATE TABLE other (x)")
    con.commit()
    con.close()


def test_protowire_roundtrip_and_errors():
    msg = pw.parse(f_int(2, 300) + f_bytes(3, b"abc"))
    assert pw.first(msg, 2) == 300 and pw.first(msg, 3) == b"abc"
    for bad in (b"\x10", b"\x1a\x05ab", b"\x00\x01", b"\x0f"):
        try:
            pw.parse(bad)
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad!r}")


def test_parse_generation_fields():
    model, comps, steps = parse_generation(generation(1000, 300, cr=5000, cw=7, think=200, steps=(3, 4)))
    assert model == "gemini-test"
    assert comps == [1000, 300, 5000, 7, 200]
    assert steps == [3, 4]


def test_parse_generation_unpacked_steps_and_garbage():
    assert parse_generation(generation(1, 1, steps=(7,), packed=False))[2] == [7]
    assert parse_generation(b"\xff\xff\xff") is None
    assert parse_generation(None) is None
    assert parse_generation(f_bytes(1, f_bytes(19, b"m"))) is None  # no usage
    assert parse_generation(generation(0, 0)) is None  # all-zero usage is not an event


def test_provider_reads_dbs_readonly(settings, tmp_path):
    root = tmp_path / "antigravity-ide"
    db = root / "conversations" / "c1.db"
    t = int(NOW) - 120
    make_db(db, [generation(100, 10, steps=(0,)), generation(200, 20, steps=(1, 2)), b"garbage"],
            steps={0: t, 1: t + 10, 2: t + 20})
    before = os.stat(db).st_mtime
    p = AntigravityProvider(settings, roots=[root])
    u = p.collect_local(NOW)
    assert u.state == State.OK
    per = u.period("5h")
    assert per.events == 2
    assert per.total.input == 300 and per.total.output == 30
    assert os.stat(db).st_mtime == before
    assert not (root / "conversations" / "c1.db-journal").exists()


def test_undated_generation_only_in_all(settings, tmp_path):
    root = tmp_path / "antigravity-cli"
    make_db(root / "conversations" / "c2.db", [generation(5, 5, steps=(9,))], steps={})
    u = AntigravityProvider(settings, roots=[root]).collect_local(NOW)
    assert u.period("all").events == 1
    assert u.period("today").events == 0


def test_same_conversation_in_two_roots_counted_once(settings, tmp_path):
    a, b = tmp_path / "antigravity-ide", tmp_path / "antigravity"
    for r in (a, b):
        make_db(r / "conversations" / "same.db", [generation(1, 1)], steps={0: int(NOW) - 5})
    u = AntigravityProvider(settings, roots=[a, b]).collect_local(NOW)
    assert u.period("all").events == 1


def test_unrelated_and_corrupt_db(settings, tmp_path):
    root = tmp_path / "antigravity"
    make_db(root / "conversations" / "x.db", [], tables=False)
    (root / "conversations" / "broken.db").write_bytes(b"not a database at all" * 10)
    u = AntigravityProvider(settings, roots=[root]).collect_local(NOW)
    assert u.state == State.OK
    assert u.period("all").events == 0
    assert "could not be read" in u.detail


def test_missing_roots(settings, tmp_path):
    u = AntigravityProvider(settings, roots=[tmp_path / "none"]).collect_local(NOW)
    assert u.state == State.NOT_INSTALLED


def test_quota_is_unavailable_never_invented(settings, tmp_path):
    q = AntigravityProvider(settings, roots=[tmp_path]).collect_quota(NOW)
    assert q.state == State.UNAVAILABLE and q.windows == []


def test_changed_db_is_rescanned(settings, tmp_path):
    root = tmp_path / "antigravity-ide"
    db = root / "conversations" / "c.db"
    make_db(db, [generation(1, 1)], steps={0: int(NOW) - 5})
    p = AntigravityProvider(settings, roots=[root])
    assert p.collect_local(NOW).period("all").events == 1
    con = sqlite3.connect(db)
    g = generation(2, 2)
    con.execute("INSERT INTO gen_metadata VALUES (5, ?, ?)", (g, len(g)))
    con.commit()
    con.close()
    os.utime(db, (NOW + 5, NOW + 5))
    assert p.collect_local(NOW).period("all").events == 2


def test_db_deleted_during_scan_is_skipped(settings, tmp_path, monkeypatch):
    root = tmp_path / "antigravity-ide"
    make_db(root / "conversations" / "keep.db", [generation(1, 1)], steps={0: int(NOW) - 5})
    make_db(root / "conversations" / "gone.db", [generation(2, 2)], steps={0: int(NOW) - 5})
    real = os.path.getmtime

    def flaky(path):
        if str(path).endswith("gone.db"):
            raise FileNotFoundError(path)
        return real(path)

    monkeypatch.setattr("quotaring.providers.antigravity.os.path.getmtime", flaky)
    u = AntigravityProvider(settings, roots=[root]).collect_local(NOW)
    assert u.state == State.OK and u.period("all").events == 1


# -- quota from the IDE's cached UserStatus ------------------------------------
def _pb_varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _pb(field, value):
    if isinstance(value, int):
        return _pb_varint(field << 3) + _pb_varint(value)
    return _pb_varint(field << 3 | 2) + _pb_varint(len(value)) + value


def _pb_float(field, value):
    import struct
    return _pb_varint(field << 3 | 5) + struct.pack("<f", value)


def _model(label, remaining, reset):
    quota = _pb_float(1, remaining) + _pb(2, _pb(1, reset))
    return _pb(1, label.encode()) + _pb(15, quota)


def _state_db(path, user_status: bytes):
    import base64
    import sqlite3
    record = _pb(1, _pb(1, b"userStatusSentinelKey") + _pb(2, _pb(1, base64.b64encode(user_status))))
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE ItemTable (key TEXT UNIQUE ON CONFLICT REPLACE, value BLOB)")
    con.execute("INSERT INTO ItemTable VALUES (?, ?)",
                ("antigravityUnifiedStateSync.userStatus", base64.b64encode(record).decode()))
    con.execute("INSERT INTO ItemTable VALUES ('antigravityUnifiedStateSync.oauthToken', 'SECRET')")
    con.commit()
    con.close()


def test_quota_from_ide_cache(tmp_path):
    import time
    from quotaring.model import State
    from quotaring.providers.antigravity import AntigravityProvider
    from quotaring.settings import Settings
    now = time.time()
    status = (_pb(3, b"Some Name") + _pb(7, b"someone@example.com")
              + _pb(33, _pb(1, _model("Gemini 3.8 Flash (High)", 1.0, int(now) + 3600))
                    + _pb(1, _model("Gemini 3.8 Flash (Low)", 0.4, int(now) + 1800))
                    + _pb(1, _model("Claude Opus 5.5 (High)", 0.75, int(now) + 7200)))
              + _pb(36, _pb(1, b"g1-pro-tier") + _pb(2, b"Google AI Pro")))
    db = tmp_path / "state.vscdb"
    _state_db(db, status)
    q = AntigravityProvider(Settings(), roots=[], state_dbs=[db])._collect_quota(now)
    assert q.state == State.OK and q.plan == "Google AI Pro"
    assert [(w.label, w.used_percent) for w in q.windows] == [("Gemini 3.8 Flash", 60.0), ("Claude Opus 5.5", 25.0)]
    assert q.windows[0].resets_at == int(now) + 1800  # earliest reset of the family
    assert "example.com" not in repr(q) and "SECRET" not in repr(q) and "Some Name" not in repr(q)


def test_quota_cache_old_or_missing(tmp_path):
    import os
    import time
    from quotaring.model import State
    from quotaring.providers.antigravity import QUOTA_STALE_AFTER, AntigravityProvider
    from quotaring.settings import Settings
    now = time.time()
    p = AntigravityProvider(Settings(), roots=[], state_dbs=[tmp_path / "missing.vscdb"])
    assert p._collect_quota(now).state == State.UNAVAILABLE
    db = tmp_path / "state.vscdb"
    _state_db(db, _pb(33, _pb(1, _model("Gemini 3.8 Flash (High)", 0.5, int(now) + 60))))
    old = now - QUOTA_STALE_AFTER - 60
    os.utime(db, (old, old))
    q = AntigravityProvider(Settings(), roots=[], state_dbs=[db])._collect_quota(now)
    assert q.state == State.STALE and q.updated_at == old and q.windows[0].used_percent == 50.0


SUMMARY = {"response": {"groups": [
    {"displayName": "Gemini Models", "buckets": [
        {"bucketId": "gemini-weekly", "window": "weekly", "remainingFraction": 0.99, "resetTime": "2026-11-04T09:25:36Z"},
        {"bucketId": "gemini-5h", "window": "5h", "remainingFraction": 0.75, "resetTime": "2026-10-29T16:50:21Z"}]},
    {"displayName": "Claude and GPT models", "buckets": [
        {"bucketId": "3p-5h", "window": "5h", "resetTime": "2026-10-29T19:21:04Z"},
        {"bucketId": "3p-daily", "window": "daily", "remainingFraction": 0.5}]},
    {"displayName": "Gemini 4 Argon", "buckets": [
        {"bucketId": "gemini-argon-wtu-weekly", "window": "weekly", "remainingFraction": 0.78}]},
]}}


def test_parse_quota_summary_groups_and_windows():
    from quotaring.providers.antigravity import parse_quota_summary
    ws = parse_quota_summary(SUMMARY)
    assert [(w.label, w.used_percent, w.window_minutes) for w in ws] == [
        ("5-hour session · Gemini", 25.0, 300), ("Weekly · Gemini", 1.0, 10080),
        ("5-hour session · Claude and GPT", 100.0, 300),  # proto3 JSON leaves out a zero fraction
        ("Weekly · Gemini 4 Argon", 22.0, 10080)]
    assert ws[0].key == "antigravity:gemini-5h" and ws[0].resets_at == 1793292621.0
    assert ws[3].resets_at is None
    assert parse_quota_summary({}) == [] and parse_quota_summary({"response": {"groups": "x"}}) == []


def test_server_args_from_command_line():
    from quotaring.providers.antigravity import _server_args
    assert _server_args(["/home/u/.gemini/bin/agy", "--hub", "--hub-port=46579", "--csrf_token=abc"]) == (46579, "abc")
    assert _server_args(["agy", "--mode", "auto"]) is None
    assert _server_args(["/usr/bin/python", "--hub-port=1", "--csrf_token=abc"]) is None
    assert _server_args([""]) is None


def test_quota_prefers_running_server(tmp_path, monkeypatch):
    from quotaring.providers import antigravity
    from quotaring.settings import Settings
    db = tmp_path / "state.vscdb"
    _state_db(db, _pb(33, _pb(1, _model("Gemini 3.8 Flash (High)", 0.5, int(NOW) + 60)))
              + _pb(36, _pb(2, b"Google AI Pro")))
    calls = []

    def fetch(port, token, path):
        calls.append((port, token))
        if port == 1:
            raise OSError("refused")
        return SUMMARY if path == antigravity.QUOTA_SUMMARY_PATH else STATUS

    monkeypatch.setattr(antigravity, "fetch", fetch)
    p = antigravity.AntigravityProvider(Settings(), roots=[], state_dbs=[db], servers=[(1, "a"), (2, "b")])
    q = p._collect_quota(NOW)
    assert calls == [(1, "a"), (2, "b"), (2, "b")]
    assert q.state == State.OK and q.plan == "Google AI Pro" and q.updated_at == NOW
    assert "Weekly · Gemini 4 Argon" in [w.label for w in q.windows]
    assert [m["name"] for m in q.extra["models"]] == ["Gemini 4 Argon"]  # no descriptions: by name only
    monkeypatch.setattr(antigravity, "fetch", lambda port, token, path: {})
    q = p._collect_quota(NOW)  # server says nothing useful: the IDE cache
    assert [w.label for w in q.windows] == ["Gemini 3.8 Flash"] and q.extra == {}


STATUS = {"userStatus": {"email": "someone@example.com", "cascadeModelConfigData": {"clientModelConfigs": [
    {"label": "Gemini 4 Argon (Medium)"}, {"label": "Gemini 4 Argon (High)"}, {"label": "Gemini 3.8 Flash (High)"},
    {"label": "Claude Opus 5.5 (Low)"}, {"label": "Mystery Model"}]}}}


def test_models_matched_to_their_group():
    from quotaring.providers.antigravity import group_models, model_families, parse_quota_summary
    summary = {"response": {"groups": [
        dict(SUMMARY["response"]["groups"][0], description="Models within this group: Gemini Flash, Gemini Pro"),
        dict(SUMMARY["response"]["groups"][1], description="Models within this group: Claude Opus, Claude Sonnet, GPT-OSS"),
        dict(SUMMARY["response"]["groups"][2], description="For paid Pro plans, Argon quota is separate.")]}}
    families = model_families(STATUS)
    assert families == ["Gemini 4 Argon", "Gemini 3.8 Flash", "Claude Opus 5.5", "Mystery Model"]
    models = group_models(families, summary, parse_quota_summary(summary))
    assert models == [
        {"name": "Gemini 4 Argon", "windows": ["antigravity:gemini-argon-wtu-weekly"]},  # its own group, not Gemini's
        {"name": "Gemini 3.8 Flash", "windows": ["antigravity:gemini-5h", "antigravity:gemini-weekly"]},
        {"name": "Claude Opus 5.5", "windows": ["antigravity:3p-5h"]}]
    assert model_families({}) == [] and model_families({"userStatus": {"cascadeModelConfigData": {"clientModelConfigs": 3}}}) == []


def test_server_names_carry_no_markup():
    from quotaring.providers.antigravity import model_families, parse_quota_summary
    summary = {"response": {"groups": [{"displayName": "<img src=x>Evil models", "buckets": [
        {"bucketId": "e", "window": "weekly", "remainingFraction": 0.5}]}]}}
    assert parse_quota_summary(summary)[0].label == "Weekly · img src=xEvil"
    status = {"userStatus": {"cascadeModelConfigData": {"clientModelConfigs": [{"label": "<b>Bold</b> (High)"}]}}}
    assert model_families(status) == ["bBold/b"]


def test_only_this_users_processes_are_trusted(monkeypatch, tmp_path):
    import sys
    from quotaring.providers import antigravity
    if not sys.platform.startswith("linux"):
        return
    real_glob = antigravity.Path.glob
    mine, theirs = tmp_path / "100", tmp_path / "200"
    for d in (mine, theirs):
        d.mkdir()
        (d / "cmdline").write_bytes(b"/x/agy\0--hub-port=1\0--csrf_token=t\0")
    real_stat = antigravity.Path.stat
    monkeypatch.setattr(antigravity.Path, "glob",
                        lambda self, pat: [mine, theirs] if str(self) == "/proc" else real_glob(self, pat))
    monkeypatch.setattr(antigravity.Path, "stat", lambda self, **kw: type("S", (), {
        "st_uid": os.getuid() if self == mine else os.getuid() + 1})() if self in (mine, theirs) else real_stat(self, **kw))
    assert antigravity.own_cmdlines() == [["/x/agy", "--hub-port=1", "--csrf_token=t", ""]]
