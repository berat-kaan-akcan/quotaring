"""Display-ready, localized view of the snapshots, for the Plasma widget (JSON over stdout).

Same rules as the Qt cards: quota only when provider-reported, local tokens labeled as local,
explicit state texts otherwise. No Qt imports, so it can be unit tested directly.
"""

from __future__ import annotations

from datetime import datetime

from . import __version__
from .i18n import language, tr, tr_label
from .model import ProviderSnapshot, State
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


def widget_view(snapshots, now: float) -> dict:
    snaps = list(snapshots)
    return {
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
