"""Data model shared by providers, cache and UI.

Local activity (tokens recorded in local logs) and account quota (limits reported by the
provider) are deliberately separate types: nothing here converts one into the other.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum

TOKEN_FIELDS = ("input", "output", "cache_read", "cache_write", "reasoning")


class State(str, Enum):
    OK = "ok"
    STALE = "stale"  # showing the last good value; the latest refresh failed
    NOT_INSTALLED = "not_installed"  # no data directory / executable found
    NOT_AUTHENTICATED = "not_authenticated"
    RATE_LIMITED = "rate_limited"
    UNAVAILABLE = "unavailable"  # no verified source, or the source failed
    UNSUPPORTED = "unsupported"  # e.g. API-key account, or this platform
    DISABLED = "disabled"  # turned off in settings
    PENDING = "pending"  # not collected yet


@dataclass
class Tokens:
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    reasoning: int = 0  # subset of output where the source reports it separately

    @property
    def total(self) -> int:
        # reasoning is already included in output for every source used here
        return self.input + self.output + self.cache_read + self.cache_write

    def add(self, other: "Tokens") -> None:
        for f in TOKEN_FIELDS:
            setattr(self, f, getattr(self, f) + getattr(other, f))

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Tokens":
        return cls(**{f: int(d.get(f) or 0) for f in TOKEN_FIELDS})


@dataclass
class UsageEvent:
    """One model response with recorded token counts."""

    ts: float | None  # epoch seconds; None when the source has no usable timestamp
    model: str
    tokens: Tokens


@dataclass
class PeriodUsage:
    key: str  # "today", "5h", "7d", "30d", "all"
    label: str
    total: Tokens = field(default_factory=Tokens)
    by_model: dict[str, Tokens] = field(default_factory=dict)
    events: int = 0

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "total": self.total.to_dict(),
            "by_model": {m: t.to_dict() for m, t in self.by_model.items()},
            "events": self.events,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PeriodUsage":
        return cls(
            key=d["key"],
            label=d.get("label", d["key"]),
            total=Tokens.from_dict(d.get("total") or {}),
            by_model={m: Tokens.from_dict(t) for m, t in (d.get("by_model") or {}).items()},
            events=int(d.get("events") or 0),
        )


@dataclass
class LocalUsage:
    state: State
    periods: list[PeriodUsage] = field(default_factory=list)
    source: str = ""  # human-readable description of where the numbers come from
    exact: bool = True  # False when counts are estimates
    detail: str = ""  # message for non-OK states
    files: int = 0
    updated_at: float | None = None

    def period(self, key: str) -> PeriodUsage | None:
        return next((p for p in self.periods if p.key == key), None)

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "periods": [p.to_dict() for p in self.periods],
            "source": self.source,
            "exact": self.exact,
            "detail": self.detail,
            "files": self.files,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LocalUsage":
        return cls(
            state=State(d["state"]),
            periods=[PeriodUsage.from_dict(p) for p in d.get("periods") or []],
            source=d.get("source", ""),
            exact=bool(d.get("exact", True)),
            detail=d.get("detail", ""),
            files=int(d.get("files") or 0),
            updated_at=d.get("updated_at"),
        )


@dataclass
class QuotaWindow:
    key: str  # stable id, e.g. "five_hour", "seven_day", "codex:primary"
    label: str  # e.g. "5-hour", "Weekly", "Weekly · Opus"
    used_percent: float
    resets_at: float | None = None  # epoch seconds
    window_minutes: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "QuotaWindow":
        return cls(**d)


@dataclass
class Quota:
    state: State
    windows: list[QuotaWindow] = field(default_factory=list)
    plan: str | None = None
    source: str = ""
    documented: bool = False
    detail: str = ""
    extra: dict = field(default_factory=dict)  # e.g. Claude per-surface weekly breakdown
    updated_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "windows": [w.to_dict() for w in self.windows],
            "plan": self.plan,
            "source": self.source,
            "documented": self.documented,
            "detail": self.detail,
            "extra": self.extra,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Quota":
        return cls(
            state=State(d["state"]),
            windows=[QuotaWindow.from_dict(w) for w in d.get("windows") or []],
            plan=d.get("plan"),
            source=d.get("source", ""),
            documented=bool(d.get("documented")),
            detail=d.get("detail", ""),
            extra=d.get("extra") or {},
            updated_at=d.get("updated_at"),
        )


@dataclass
class ProviderSnapshot:
    provider_id: str
    name: str
    local: LocalUsage
    quota: Quota

    def to_dict(self) -> dict:
        return {
            "provider_id": self.provider_id,
            "name": self.name,
            "local": self.local.to_dict(),
            "quota": self.quota.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProviderSnapshot":
        return cls(
            provider_id=d["provider_id"],
            name=d["name"],
            local=LocalUsage.from_dict(d["local"]),
            quota=Quota.from_dict(d["quota"]),
        )
