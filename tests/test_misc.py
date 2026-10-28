import json
import sys
import time
from datetime import datetime

import pytest

from aiusage import autostart, settings as settings_mod
from aiusage.aggregate import aggregate, period_starts
from aiusage.model import ProviderSnapshot, LocalUsage, Quota, QuotaWindow, State, Tokens, UsageEvent
from aiusage.ui import format as fmt

NOW = time.time()


def ev(ts, model="m", n=1):
    return UsageEvent(ts, model, Tokens(input=n))


def test_aggregate_periods():
    midnight = period_starts(NOW)["today"]
    events = [ev(NOW - 10), ev(midnight - 1), ev(NOW - 6 * 86400), ev(NOW - 29 * 86400),
              ev(NOW - 40 * 86400), ev(None), ev(NOW + 3600)]
    p = {x.key: x for x in aggregate(events, NOW)}
    assert p["today"].events == (1 if NOW - 10 >= midnight else 0)
    assert p["7d"].events == 3
    assert p["30d"].events == 4
    assert p["all"].events == 7  # includes undated and out-of-range events
    assert p["5h"].events == (2 if NOW - (midnight - 1) <= 5 * 3600 else 1)


def test_tokens_total_excludes_reasoning_double_count():
    t = Tokens(input=1, output=10, cache_read=100, cache_write=1000, reasoning=7)
    assert t.total == 1111


def test_snapshot_roundtrip():
    s = ProviderSnapshot("x", "X", LocalUsage(State.OK, aggregate([ev(NOW)], NOW)),
                         Quota(State.OK, [QuotaWindow("a", "A", 3.0, NOW, 300)], extra={"k": 1}))
    s2 = ProviderSnapshot.from_dict(json.loads(json.dumps(s.to_dict())))
    assert s2 == s


def test_settings_defaults_roundtrip_and_validation(tmp_path):
    path = tmp_path / "s.json"
    s = settings_mod.load(path)
    assert s.local_refresh_seconds == 60 and s.start_at_login is False
    s.theme = "dark"
    s.quota_enabled["codex"] = False
    settings_mod.save(s, path)
    s2 = settings_mod.load(path)
    assert s2.theme == "dark" and s2.quota_enabled["codex"] is False and s2.quota_enabled["claude"] is True
    path.write_text(json.dumps({"local_refresh_seconds": 1, "theme": "neon", "opacity": "x",
                                "always_on_top": "yes", "unknown": 5, "period": "1y"}))
    s3 = settings_mod.load(path)
    assert s3.local_refresh_seconds == 15 and s3.theme == "system" and s3.opacity == 0.96
    assert s3.always_on_top is True and s3.period == "today"
    path.write_text("[1,2,3]")
    assert settings_mod.load(path).theme == "system"
    path.write_text("{corrupt")
    assert settings_mod.load(path).theme == "system"


def test_settings_default_location_is_platform_config_dir(isolated_dirs):
    settings_mod.save(settings_mod.Settings())
    if sys.platform.startswith("linux"):
        assert (isolated_dirs / "config" / "ai-usage-widget" / "settings.json").exists()


def test_format_helpers():
    assert fmt.tokens(999) == "999"
    assert fmt.tokens(1500) == "1.5K"
    assert fmt.tokens(2_340_000) == "2.3M"
    assert fmt.tokens(123_000_000) == "123M"
    assert fmt.duration(3 * 3600 + 120) == "3h 2m"
    assert fmt.duration(2 * 86400 + 3600) == "2d 1h"
    assert fmt.resets(None, NOW) == "reset time unknown"
    assert "awaiting refresh" in fmt.resets(NOW - 1, NOW)
    assert fmt.resets(NOW + 600, NOW) == "resets in 10m"
    assert fmt.age(NOW - 5, NOW) == "just now"
    assert fmt.updated(None, NOW) == "not updated yet"


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="XDG autostart is Linux only")
def test_autostart_desktop_file(isolated_dirs):
    assert not autostart.is_enabled()
    autostart.set_enabled(True)
    f = isolated_dirs / "config" / "autostart" / "ai-usage-widget.desktop"
    text = f.read_text()
    assert "Exec=" in text and "-m aiusage" in text and "Type=Application" in text
    assert autostart.is_enabled()
    autostart.set_enabled(False)
    assert not f.exists()
    autostart.set_enabled(False)  # idempotent


def test_today_period_start_is_local_midnight():
    start = datetime.fromtimestamp(period_starts(NOW)["today"])
    assert (start.hour, start.minute, start.second) == (0, 0, 0)
