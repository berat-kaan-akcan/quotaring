import os
import sqlite3
import time

from aiusage import protowire as pw
from aiusage.model import State
from aiusage.providers.antigravity import AntigravityProvider, parse_generation

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

    monkeypatch.setattr("aiusage.providers.antigravity.os.path.getmtime", flaky)
    u = AntigravityProvider(settings, roots=[root]).collect_local(NOW)
    assert u.state == State.OK and u.period("all").events == 1
