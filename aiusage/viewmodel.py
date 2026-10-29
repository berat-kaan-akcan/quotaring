"""Display-ready, localized view of the snapshots, for the Plasma widget (JSON over stdout).

Same rules as the Qt cards: quota only when provider-reported, local tokens labeled as local,
explicit state texts otherwise. No Qt imports, so it can be unit tested directly.
"""

from __future__ import annotations

import re
from datetime import date, datetime

from . import __version__
from .i18n import language, tr, tr_label
from .model import ProviderSnapshot, State, Tokens
from .ui import format as fmt

COLORS = {"claude": "#d97757", "codex": "#10a37f", "antigravity": "#4285f4"}
PERIODS = (("today", "Today"), ("5h", "Last 5 hours"), ("7d", "Last 7 days"),
           ("30d", "Last 30 days"), ("all", "All scanned"))
SHORT = {"today": "Today", "5h": "5 h", "7d": "7 d"}
LEVEL = {State.OK: "ok", State.STALE: "warn", State.RATE_LIMITED: "warn",
         State.NOT_AUTHENTICATED: "bad", State.PENDING: "info"}


def _pill(state: State, text: str | None = None) -> dict:
    return {"text": text or fmt.state_text(state), "level": LEVEL.get(state, "muted")}


def _tooltip(per) -> str:
    t = per.total
    return "\n".join([
        tr("{label}: {n} responses").format(label=tr(per.label), n=per.events),
        tr("input {v}").format(v=f"{t.input:,}"),
        tr("output {v} (reasoning {r})").format(v=f"{t.output:,}", r=f"{t.reasoning:,}"),
        tr("cache read {v}").format(v=f"{t.cache_read:,}"),
        tr("cache write {v}").format(v=f"{t.cache_write:,}"),
        tr("Recorded in local logs; not account quota."),
    ])


def provider_view(snap: ProviderSnapshot, now: float) -> dict:
    q, loc = snap.quota, snap.local
    view = {"id": snap.provider_id, "name": snap.name, "color": COLORS.get(snap.provider_id, "#888888"),
            "plan": q.plan or "", "collapsed": False, "message": "", "quota": [], "quotaMessage": "",
            "quotaSource": "", "breakdown": "", "local": [], "localMessage": "", "daily": [],
            "chartLabel": "", "models": {}, "footer": fmt.updated(loc.updated_at, now)}

    for st, text in ((State.NOT_INSTALLED, "Not installed — no CLI or local history found on this computer"),
                     (State.DISABLED, "Disabled in settings")):
        if loc.state == st and q.state in (st, State.DISABLED, State.UNAVAILABLE):
            view.update(collapsed=True, message=tr(text), pill=_pill(st))
            return view

    if q.state == State.OK and loc.state == State.OK:
        view["pill"] = _pill(State.OK)
    elif State.STALE in (q.state, loc.state):
        view["pill"] = _pill(State.STALE)
    elif loc.state == State.OK:
        view["pill"] = _pill(State.OK, tr("Local only"))
    else:
        view["pill"] = _pill(loc.state if loc.state != State.OK else q.state)

    if q.windows and q.state in (State.OK, State.STALE):
        for w in q.windows:
            view["quota"].append({
                "label": tr_label(w.label), "percent": round(w.used_percent, 1),
                "percentText": fmt.window_pct(w, now), "reset": fmt.resets(w.resets_at, now),
                "limited": w.active_limit(now),
                "dim": not w.active_limit(now) and (
                    q.state == State.STALE or (w.resets_at is not None and w.resets_at <= now)),
            })
    if q.state == State.STALE:
        view["quotaMessage"] = tr("Stale (last updated {age}): {detail}").format(
            age=fmt.age(q.updated_at, now), detail=tr(q.detail))
    elif q.state != State.OK:
        view["quotaMessage"] = fmt.state_text(q.state) + (f" — {tr(q.detail)}" if q.detail else "")
    if q.source and q.state in (State.OK, State.STALE):
        view["quotaSource"] = tr("Source: {source}").format(source=tr(q.source)) + (
            "" if q.documented else tr(" — may change without notice"))
    rows = (q.extra or {}).get("weekly_breakdown")
    if rows and view["quota"]:
        view["breakdown"] = tr("Weekly share: ") + " · ".join(
            f"{tr(r['label'])} {fmt.pct(r['percent'])}" for r in rows)

    if loc.state in (State.OK, State.STALE) and loc.periods:
        for key in ("today", "5h", "7d"):
            per = loc.period(key)
            if per:
                view["local"].append({"label": tr(SHORT[key]), "value": fmt.tokens(per.total.total),
                                      "tooltip": _tooltip(per)})
        for key, _label in PERIODS:
            per = loc.period(key)
            models = sorted(per.by_model.items(), key=lambda kv: kv[1].total, reverse=True) if per else []
            view["models"][key] = [
                [m, fmt.tokens(t.input), fmt.tokens(t.output),
                 f"{fmt.tokens(t.cache_read)}/{fmt.tokens(t.cache_write)}", fmt.tokens(t.total)]
                for m, t in models]
        if loc.daily:
            peak = max(v for _d, v in loc.daily) or 1
            view["daily"] = [{"day": d, "value": v, "ratio": v / peak,
                              "tooltip": tr("{day}: {short} tokens ({full})").format(
                                  day=d, short=fmt.tokens(v), full=f"{v:,}")} for d, v in loc.daily]
            view["chartLabel"] = tr("Daily recorded tokens, last {n} days ({start} → today) · hover for values").format(
                n=len(loc.daily), start=loc.daily[0][0][5:])
        view["footer"] += " · " + tr("{n} files").format(n=loc.files) + " · " + tr(
            "exact counts from local records" if loc.exact else "estimated")
    if loc.state == State.STALE:
        view["localMessage"] = tr("Stale (last updated {age}): {detail}").format(
            age=fmt.age(loc.updated_at, now), detail=tr(loc.detail))
    elif loc.state != State.OK:
        view["localMessage"] = fmt.state_text(loc.state) + (f" — {tr(loc.detail)}" if loc.detail else "")
    elif loc.detail:
        view["localMessage"] = tr(loc.detail)
    return view


def headline(snapshots, now: float) -> str:
    """Short text for a panel: highest provider-reported quota use, else empty."""
    best = None
    for s in snapshots:
        if any(w.active_limit(now) for w in s.quota.windows):
            return tr("Limit reached")
        if s.quota.state not in (State.OK, State.STALE):
            continue
        for w in s.quota.windows:
            if w.resets_at is not None and w.resets_at <= now:
                continue  # window already reset: the old percentage no longer applies
            if best is None or w.used_percent > best:
                best = w.used_percent
    return fmt.pct(best) if best is not None else ""


# -- compact popup (Limits / Tokens tabs) and panel ring ---------------------
SHORT_WINDOW = {"5-hour session": "5 hours"}
SHORT_PERIODS = (("today", "Today"), ("5h", "5 hours"), ("7d", "7 days"), ("30d", "30 days"), ("all", "All"))
MONTHS_TR = ("Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara")
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


def limits_view(snaps, now: float) -> list[dict]:
    out = []
    for s in snaps:
        q, loc = s.quota, s.local
        if q.state in (State.NOT_INSTALLED, State.DISABLED) and loc.state in (State.NOT_INSTALLED, State.DISABLED):
            continue
        item = {"id": s.provider_id, "name": s.name.replace(" Code", ""), "plan": q.plan or "",
                "windows": [], "message": "", "level": "info", "note": ""}
        if q.windows and q.state in (State.OK, State.STALE):
            for w in q.windows:
                label = tr_label(w.label)
                label = tr(SHORT_WINDOW[w.label]) if w.label in SHORT_WINDOW else label
                passed = w.resets_at is not None and w.resets_at <= now
                limited = w.active_limit(now)
                used = 100.0 if limited else w.used_percent
                item["windows"].append({
                    "label": label, "used": round(used), "remaining": round(max(0.0, 100 - used)),
                    "limited": limited, "dim": not limited and (passed or q.state == State.STALE),
                    "reset": fmt.resets(w.resets_at, now)})
            if q.state == State.STALE:
                item["note"] = tr("updated {age}").format(age=fmt.age(q.updated_at, now))
        else:
            item["message"] = _limit_message(s)
            item["level"] = "bad" if q.state == State.NOT_AUTHENTICATED else "muted"
        out.append(item)
    return out


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
    return f"{d.day} {MONTHS_TR[d.month - 1]}" if language() == "tr" else d.strftime("%b %-d")


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
        "headline": headline(snaps, now),
        "tooltip": fmt.summary(snaps, now),
        "labels": {
            "title": tr("AI Usage"), "quota": tr("Account quota").upper(),
            "local": tr("Local activity · recorded tokens").upper(), "refresh": tr("Refresh now"),
            "breakdown": tr("Breakdown:"),
            "columns": [tr(h) for h in ("Model", "Input", "Output", "Cache r/w", "Total")],
            "periods": [{"key": k, "label": tr(label)} for k, label in PERIODS],
            "noUsage": tr("No recorded usage ({period})"),
        },
        "providers": [provider_view(s, now) for s in snaps],
    }
