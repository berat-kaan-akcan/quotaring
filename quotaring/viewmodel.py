"""Display-ready, localized view of the snapshots: the tray popup's data.

Quota only when provider-reported, local tokens labeled as local, explicit state texts
otherwise. No Qt imports, so it can be unit tested directly.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from . import __version__
from .i18n import language, tr, tr_label
from .model import ProviderSnapshot, State
from .ui import format as fmt

COLORS = {"claude": "#d97757", "codex": "#10a37f", "antigravity": "#4285f4"}
SHORT_WINDOW = {"5-hour session": "5 hours"}
RING_TAG = {"5-hour session": "5h", "Weekly": "W"}  # label written on the ring itself
SHORT_PERIODS = (("today", "Today"), ("5h", "5 hours"), ("7d", "7 days"), ("30d", "30 days"), ("all", "All"))
MONTHS_TR = ("Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara")
MONTHS_EN = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
CHART_DAYS = 7


def model_name(model: str) -> str:
    """'claude-opus-5-5' -> 'Opus 5.5'; other ids unchanged."""
    if not model.startswith("claude-"):
        return model
    parts = [p for p in model[7:].split("-") if not re.fullmatch(r"\d{8}", p)]
    words = [p.capitalize() for p in parts if not p.isdigit()]
    nums = [p for p in parts if p.isdigit()]
    return " ".join(words + ([".".join(nums)] if nums else [])) or model


def _limit_message(snap: ProviderSnapshot) -> str:
    q = snap.quota
    if q.state == State.NOT_AUTHENTICATED:
        return tr("Not signed in · run {cmd} login").format(cmd=snap.provider_id)
    if q.state == State.UNSUPPORTED:
        return tr("No plan limits for this account")
    if q.state == State.RATE_LIMITED:
        return tr("Limit check paused, retrying soon")
    if q.state == State.PENDING:
        return tr("Loading…")
    return tr("No limit data")


def _initials(label: str) -> str:
    """Ring tag for a per-model limit: 'Claude Opus 5.5' -> 'CO', 'GPT-OSS 120B' -> 'GO'."""
    words = [w for w in re.split(r"[\s\-·]+", label) if w[:1].isalpha()]
    return "".join(w[0].upper() for w in words[:2]) or label[:2]


def limits_view(snaps, now: float) -> list[dict]:
    out = []
    for s in snaps:
        q, loc = s.quota, s.local
        if q.state in (State.NOT_INSTALLED, State.DISABLED) and loc.state in (State.NOT_INSTALLED, State.DISABLED):
            continue
        item = {"id": s.provider_id, "name": s.name.replace(" Code", ""), "plan": q.plan or "",
                "color": COLORS.get(s.provider_id, "#888888"),
                "windows": [], "message": "", "level": "info", "note": ""}
        if q.windows and q.state in (State.OK, State.STALE):
            for w in q.windows:
                label = tr_label(w.label)
                label = tr(SHORT_WINDOW[w.label]) if w.label in SHORT_WINDOW else label
                passed = w.resets_at is not None and w.resets_at <= now
                limited = w.active_limit(now)
                used = 100.0 if limited else w.used_percent
                base = w.label.split(" · ")[0]
                item["windows"].append({
                    "label": label, "tag": tr(RING_TAG[base]) if base in RING_TAG else _initials(label),
                    "used": round(used), "remaining": round(max(0.0, 100 - used)),
                    "limited": limited, "dim": not limited and (passed or q.state == State.STALE),
                    "reset": fmt.resets(w.resets_at, now)})
            if q.state == State.STALE:
                item["note"] = tr("updated {age}").format(age=fmt.age(q.updated_at, now))
        else:
            item["message"] = _limit_message(s)
            item["level"] = "bad" if q.state == State.NOT_AUTHENTICATED else "muted"
        out.append(item)
    return out


def limits_tooltip(limits: list[dict], remaining: bool = True) -> str:
    """Tray tooltip: each provider's limits as what is left (or used), else why there are none."""
    lines = []
    for p in limits:
        if not p["windows"]:
            lines.append(f"{p['name']}: {p['message']}")
            continue
        parts = []
        for w in p["windows"]:
            value = tr("Limit reached") if w["limited"] else (
                f"{fmt.pct(w['remaining'])} {tr('left')}" if remaining else f"{fmt.pct(w['used'])} {tr('used')}")
            parts.append(f"{w['label']} {value}")
        lines.append(f"{p['name']}: " + " · ".join(parts))
    return "\n".join(lines)


def ring(snaps, now: float) -> dict:
    """The tightest current limit across providers: what the panel ring shows."""
    worst = None
    for s in snaps:
        if s.quota.state not in (State.OK, State.STALE):
            continue
        for w in s.quota.windows:
            if w.resets_at is not None and w.resets_at <= now:
                continue
            used = 100.0 if w.active_limit(now) else w.used_percent
            if worst is None or used > worst[0]:
                worst = (used, w.active_limit(now), s.name, tr_label(w.label))
    if worst is None:
        return {"available": False, "used": 0, "remaining": 0, "level": "muted", "limited": False, "label": ""}
    used, limited, name, label = worst
    remaining = max(0.0, 100 - used)
    level = "bad" if limited or remaining <= 10 else "warn" if remaining <= 30 else "ok"
    return {"available": True, "used": round(used), "remaining": round(remaining), "level": level,
            "limited": limited, "label": f"{name} · {label}"}


def _day_label(day: str) -> str:
    d = date.fromisoformat(day)
    # Fixed names, not strftime: the process locale (set by Qt) is not the UI language.
    return f"{d.day} {MONTHS_TR[d.month - 1]}" if language() == "tr" else f"{MONTHS_EN[d.month - 1]} {d.day}"


def tokens_view(snaps, now: float) -> dict:
    """Local token totals per provider and for all of them, per period, plus a 7-day chart."""
    usable = [s for s in snaps if s.local.state in (State.OK, State.STALE) and s.local.periods]
    groups = [("all", tr("All"), "", usable)] + [
        (s.provider_id, s.name.replace(" Code", ""), COLORS.get(s.provider_id, "#888888"), [s]) for s in usable]
    data = {}
    for key, _label, _color, members in groups:
        periods = {}
        for pkey, _plabel in SHORT_PERIODS:
            total, models = 0, {}
            for s in members:
                per = s.local.period(pkey)
                if not per:
                    continue
                total += per.total.total
                for m, t in per.by_model.items():
                    name = model_name(m)
                    prev = models.get(name, (0, s.provider_id))
                    models[name] = (prev[0] + t.total, s.provider_id)
            rows = sorted(models.items(), key=lambda kv: kv[1][0], reverse=True)
            top = rows[0][1][0] if rows else 0
            periods[pkey] = {"total": total, "totalText": fmt.tokens(total), "models": [
                {"name": n, "text": fmt.tokens(v), "ratio": v / top if top else 0,
                 "color": COLORS.get(pid, "#888888")} for n, (v, pid) in rows if v > 0]}
        days: dict[str, int] = {}
        for s in members:
            for d, v in (s.local.daily or [])[-CHART_DAYS:]:
                days[d] = days.get(d, 0) + v
        peak = max(days.values(), default=0)
        data[key] = {"periods": periods, "daily": [
            {"label": _day_label(d), "value": v, "text": fmt.tokens(v), "ratio": v / peak if peak else 0}
            for d, v in sorted(days.items())], "peakText": fmt.tokens(peak)}
    return {"groups": [{"key": k, "label": label, "color": c} for k, label, c, _m in groups],
            "periods": [{"key": k, "label": tr(label)} for k, label in SHORT_PERIODS], "data": data}


def widget_view(snapshots, now: float) -> dict:
    snaps = list(snapshots)
    return {
        "ring": ring(snaps, now),
        "limits": limits_view(snaps, now),
        "tokens": tokens_view(snaps, now),
        "text": {"limits": tr("Limits"), "tokens": tr("Tokens"), "left": tr("left"), "used": tr("used"),
                 "limitReached": tr("Limit reached"), "updated": tr("Updated {time}").format(
                     time=datetime.fromtimestamp(now).strftime("%H:%M")),
                 "localOnly": tr("From local Claude Code, Codex and Antigravity logs; not account quota."),
                 "total": tr("Total tokens · {period}"), "daily": tr("Daily"), "byModel": tr("By model"),
                 "noData": tr("No usage recorded in this period"), "noLimits": tr("No limit data yet")},
        "version": __version__,
        "language": language(),
        "generatedAt": datetime.fromtimestamp(now).isoformat(timespec="seconds"),
        "tooltip": fmt.summary(snaps, now),
        "labels": {"title": tr("QuotaRing"), "refresh": tr("Refresh now"), "settings": tr("Settings")},
    }
