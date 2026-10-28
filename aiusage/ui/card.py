"""One provider's card: account quota and local activity, kept visually separate."""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QSizePolicy,
                               QTableWidget, QTableWidgetItem, QToolTip, QVBoxLayout, QWidget)

from ..i18n import tr, tr_label
from ..model import ProviderSnapshot, State
from . import format as fmt
from .theme import PROVIDER_COLORS, Palette

PERIOD_LABELS = {"today": "Today", "5h": "5 h", "7d": "7 d", "30d": "30 d", "all": "All"}


class Bar(QWidget):
    def __init__(self, palette: Palette):
        super().__init__()
        self.palette_ = palette
        self.value = 0.0
        self.dim = False
        self.setFixedHeight(6)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def sizeHint(self):
        return QSize(120, 6)

    def set(self, value: float, dim: bool):
        self.value, self.dim = value, dim
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.palette_.track))
        p.drawRoundedRect(r, 3, 3)
        pal = self.palette_
        color = pal.bad if self.value >= 90 else pal.warn if self.value >= 70 else pal.accent
        c = QColor(color)
        if self.dim:
            c.setAlphaF(0.45)
        w = r.width() * max(0.0, min(100.0, self.value)) / 100
        if w > 0:
            p.setBrush(c)
            p.drawRoundedRect(QRectF(r.x(), r.y(), max(w, 6), r.height()), 3, 3)


class DailyChart(QWidget):
    """Bars of locally recorded tokens per day (oldest left). Hover shows the day's total."""

    def __init__(self, palette: Palette, color: str):
        super().__init__()
        self.palette_ = palette
        self.color = color
        self.days: list = []
        self.setFixedHeight(54)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_days(self, days: list):
        self.days = days or []
        peak = max((d[1] for d in self.days), default=0)
        self.setToolTip(tr("Daily recorded tokens (local), last {n} days · peak {peak}").format(
            n=len(self.days), peak=fmt.tokens(peak)))
        self.update()

    def _slot(self, x: float) -> int | None:
        if not self.days:
            return None
        i = int(x / (self.width() / len(self.days)))
        return i if 0 <= i < len(self.days) else None

    def mouseMoveEvent(self, e):
        i = self._slot(e.position().x())
        if i is not None:
            day, total = self.days[i]
            text = tr("{day}: {short} tokens ({full})").format(day=day, short=fmt.tokens(total), full=f"{total:,}")
            QToolTip.showText(e.globalPosition().toPoint(), text, self)

    def paintEvent(self, _e):
        if not self.days:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        n = len(self.days)
        peak = max(d[1] for d in self.days) or 1
        slot = self.width() / n
        bw = max(2.0, slot * 0.68)
        h = self.height() - 2
        p.setPen(Qt.NoPen)
        for i, (_day, total) in enumerate(self.days):
            x = i * slot + (slot - bw) / 2
            bh = max(2.0, h * total / peak) if total else 2.0
            c = QColor(self.color if total else self.palette_.track)
            if i < n - 1 and total:
                c.setAlphaF(0.7)
            p.setBrush(c)
            p.drawRoundedRect(QRectF(x, h - bh + 1, bw, bh), 2, 2)


class Pill(QLabel):
    def __init__(self, palette: Palette):
        super().__init__()
        self.palette_ = palette
        self.setAlignment(Qt.AlignCenter)

    def set_state(self, state: State, text: str | None = None):
        p = self.palette_
        color = {State.OK: p.ok, State.STALE: p.warn, State.RATE_LIMITED: p.warn,
                 State.NOT_AUTHENTICATED: p.bad, State.PENDING: p.info}.get(state, p.muted)
        self.setText(text or fmt.state_text(state))
        c = QColor(color)
        self.setStyleSheet(
            f"color: {color}; background: rgba({c.red()},{c.green()},{c.blue()},38);"
            "border-radius: 8px; padding: 1px 7px; font-size: 8pt; font-weight: 600;")


def _section(text: str) -> QLabel:
    lab = QLabel(tr(text).upper())
    lab.setObjectName("section")
    return lab


def _small(text: str = "") -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("small")
    lab.setWordWrap(True)
    return lab


class ProviderCard(QFrame):
    def __init__(self, provider_id: str, name: str, palette: Palette):
        super().__init__()
        self.setObjectName("card")
        self.pid = provider_id
        self.palette_ = palette
        self.expanded = False
        self.period = "today"
        self.snapshot: ProviderSnapshot | None = None
        self._quota_widgets: list[QWidget] = []

        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)

        head = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {PROVIDER_COLORS.get(provider_id, palette.accent)}; font-size: 11pt;")
        title = QLabel(name)
        title.setObjectName("title")
        self.plan = _small()
        self.pill = Pill(palette)
        head.addWidget(dot)
        head.addWidget(title)
        head.addWidget(self.plan)
        head.addStretch(1)
        head.addWidget(self.pill)
        lay.addLayout(head)

        # Account quota
        self.quota_title = _section("Account quota")
        lay.addWidget(self.quota_title)
        self.quota_box = QWidget()
        self.quota_grid = QGridLayout(self.quota_box)
        self.quota_grid.setContentsMargins(0, 0, 0, 0)
        self.quota_grid.setHorizontalSpacing(8)
        self.quota_grid.setVerticalSpacing(3)
        lay.addWidget(self.quota_box)
        self.quota_msg = _small()
        lay.addWidget(self.quota_msg)
        self.breakdown = _small()
        lay.addWidget(self.breakdown)

        # Local activity
        self.local_title = _section("Local activity · recorded tokens")
        lay.addWidget(self.local_title)
        row = QHBoxLayout()
        row.setSpacing(14)
        self.local_vals: dict[str, QLabel] = {}
        for key in ("today", "5h", "7d"):
            col = QVBoxLayout()
            col.setSpacing(0)
            v = QLabel("–")
            v.setObjectName("big")
            col.addWidget(v)
            col.addWidget(_small(tr(PERIOD_LABELS[key])))
            row.addLayout(col)
            self.local_vals[key] = v
        row.addStretch(1)
        self.local_row = QWidget()
        self.local_row.setLayout(row)
        lay.addWidget(self.local_row)
        self.local_msg = _small()
        lay.addWidget(self.local_msg)
        self.chart = DailyChart(palette, PROVIDER_COLORS.get(provider_id, palette.accent))
        self.chart_label = _small()
        lay.addWidget(self.chart)
        lay.addWidget(self.chart_label)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr(h) for h in ("Model", "Input", "Output", "Cache r/w", "Total")])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setTextElideMode(Qt.ElideRight)
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in range(1, 5):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        lay.addWidget(self.table)

        self.footer = _small()
        lay.addWidget(self.footer)
        self.table.hide()
        self.breakdown.hide()

    # ------------------------------------------------------------------
    def set_mode(self, expanded: bool, period: str):
        self.expanded, self.period = expanded, period
        if self.snapshot:
            self.update_snapshot(self.snapshot)

    def _clear_quota(self):
        # Rows are tracked in a list rather than drained with takeAt(), keeping ownership simple.
        for w in self._quota_widgets:
            self.quota_grid.removeWidget(w)
            w.hide()
            w.deleteLater()
        self._quota_widgets = []

    def update_snapshot(self, snap: ProviderSnapshot):
        self.snapshot = snap
        now = time.time()
        q, loc = snap.quota, snap.local
        self.plan.setText(q.plan or "")

        # Nothing installed, or provider switched off: one line instead of two empty sections.
        for st, text in ((State.NOT_INSTALLED, "Not installed — no CLI or local history found on this computer"),
                         (State.DISABLED, "Disabled in settings")):
            collapsed = loc.state == st and q.state in (st, State.DISABLED, State.UNAVAILABLE)
            if collapsed:
                break
        for w in (self.quota_title, self.quota_box, self.quota_msg, self.breakdown,
                  self.local_title, self.local_row, self.local_msg, self.table,
                  self.chart, self.chart_label):
            w.setVisible(not collapsed)
        if collapsed:
            self.pill.set_state(st)
            self.footer.setText(tr(text))
            return
        self.quota_title.show()
        self.local_title.show()

        # Overall pill: worst meaningful state, preferring local data availability.
        if q.state == State.OK and loc.state == State.OK:
            self.pill.set_state(State.OK)
        elif State.STALE in (q.state, loc.state):
            self.pill.set_state(State.STALE)
        elif loc.state == State.OK:
            self.pill.set_state(State.OK, tr("Local only"))
        else:
            self.pill.set_state(loc.state if loc.state != State.OK else q.state)

        # Quota
        self._clear_quota()
        has_windows = bool(q.windows) and q.state in (State.OK, State.STALE)
        self.quota_box.setVisible(has_windows)
        if has_windows:
            stale = q.state == State.STALE
            for row, w in enumerate(q.windows):
                label = QLabel(tr_label(w.label))
                bar = Bar(self.palette_)
                bar.set(w.used_percent, stale or (w.resets_at is not None and w.resets_at <= now))
                pct = QLabel(fmt.pct(w.used_percent))
                pct.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                pct.setMinimumWidth(36)
                reset = _small(fmt.resets(w.resets_at, now))
                reset.setWordWrap(False)
                self.quota_grid.addWidget(label, row * 2, 0)
                self.quota_grid.addWidget(bar, row * 2, 1)
                self.quota_grid.addWidget(pct, row * 2, 2)
                self.quota_grid.addWidget(reset, row * 2 + 1, 0, 1, 3)
                self._quota_widgets += [label, bar, pct, reset]
            self.quota_grid.setColumnStretch(1, 1)
        msg = []
        if q.state == State.STALE:
            msg.append(tr("Stale (last updated {age}): {detail}").format(age=fmt.age(q.updated_at, now),
                                                                          detail=tr(q.detail)))
        elif q.state != State.OK:
            msg.append(fmt.state_text(q.state) + (f" — {tr(q.detail)}" if q.detail else ""))
        elif self.expanded and q.source:
            msg.append(tr("Source: {source}").format(source=tr(q.source))
                       + ("" if q.documented else tr(" — may change without notice")))
        self.quota_msg.setText("  ".join(msg))
        self.quota_msg.setVisible(bool(msg))
        rows = q.extra.get("weekly_breakdown") if q.extra else None
        if self.expanded and rows and has_windows:
            self.breakdown.setText(tr("Weekly share: ") + " · ".join(
                f"{tr(r['label'])} {fmt.pct(r['percent'])}" for r in rows))
            self.breakdown.show()
        else:
            self.breakdown.hide()

        # Local activity
        has_local = loc.state in (State.OK, State.STALE) and bool(loc.periods)
        self.local_row.setVisible(has_local)
        if has_local:
            for key, lab in self.local_vals.items():
                per = loc.period(key)
                lab.setText(fmt.tokens(per.total.total) if per else "–")
                lab.setToolTip(self._tooltip(per) if per else "")
        lm = []
        if loc.state == State.STALE:
            lm.append(tr("Stale (last updated {age}): {detail}").format(age=fmt.age(loc.updated_at, now),
                                                                         detail=tr(loc.detail)))
        elif loc.state != State.OK:
            lm.append(fmt.state_text(loc.state) + (f" — {tr(loc.detail)}" if loc.detail else ""))
        elif loc.detail:
            lm.append(tr(loc.detail))
        self.local_msg.setText("  ".join(lm))
        self.local_msg.setVisible(bool(lm))

        show_chart = has_local and self.expanded and bool(loc.daily)
        self.chart.setVisible(show_chart)
        self.chart_label.setVisible(show_chart)
        if show_chart:
            self.chart.palette_ = self.palette_
            self.chart.set_days(loc.daily)
            self.chart_label.setText(tr("Daily recorded tokens, last {n} days ({start} → today) · hover for values")
                                     .format(n=len(loc.daily), start=loc.daily[0][0][5:]))
        self._fill_table(loc if has_local and self.expanded else None)
        foot = [fmt.updated(loc.updated_at, now)]
        if has_local and self.expanded:
            foot.append(tr("{n} files").format(n=loc.files) + " · "
                        + tr("exact counts from local records" if loc.exact else "estimated"))
        self.footer.setText(" · ".join(foot))

    @staticmethod
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

    def _fill_table(self, loc):
        if loc is None:
            self.table.hide()
            return
        per = loc.period(self.period)
        models = sorted(per.by_model.items(), key=lambda kv: kv[1].total, reverse=True) if per else []
        self.table.setRowCount(len(models) or 1)
        if not models:
            self.table.setItem(0, 0, QTableWidgetItem(
                tr("No recorded usage ({period})").format(period=tr(PERIOD_LABELS[self.period]))))
            for c in range(1, 5):
                self.table.setItem(0, c, QTableWidgetItem(""))
        for r, (model, t) in enumerate(models):
            vals = [model, fmt.tokens(t.input), fmt.tokens(t.output),
                    f"{fmt.tokens(t.cache_read)}/{fmt.tokens(t.cache_write)}", fmt.tokens(t.total)]
            for c, v in enumerate(vals):
                item = QTableWidgetItem(v)
                if c:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.table.setItem(r, c, item)
        self.table.resizeRowsToContents()
        h = self.table.horizontalHeader().height() + sum(
            self.table.rowHeight(i) for i in range(self.table.rowCount())) + 4
        self.table.setFixedHeight(h)
        self.table.show()
