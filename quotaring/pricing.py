"""API list prices, to put a rough dollar figure on locally recorded tokens.

Subscriptions are not billed per token; this is what the same tokens would cost on the
provider's pay-as-you-go API. Prices are USD per 1M tokens: (input, output, cache read,
cache write).

Sources, in order:
  1. LiteLLM's community price list (github.com/BerriAI/litellm): first-party model ids only
     (no "bedrock/...", "us.anthropic...").
  2. OpenRouter's public model list, only for models LiteLLM lacks (Antigravity's Gemini 4
     Argon, for one): OpenRouter sometimes charges above list price, so it never overrides.
     Its "anthropic/claude-opus-5.5" becomes "claude-opus-5-5".
  3. The built-in table below (checked October 2026), when neither has the model or nothing
     was downloaded yet.
Both lists are downloaded at most once a week when the setting allows it and kept, merged, in
the cache directory. Models in none of them get no price rather than a guess.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from . import paths
from .jsonstore import read_json, write_json
from .model import Tokens

log = logging.getLogger(__name__)
BUILTIN_AS_OF = "2026-10"
REMOTE_URL = "https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json"
OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
OPENROUTER_VENDORS = ("anthropic/", "google/", "openai/")
REFRESH_AFTER = 7 * 86400
MAX_PRICE = 1000.0  # USD per 1M tokens; anything above is a broken entry
# First match wins: specific ids before their family.
PRICES: tuple[tuple[str, tuple[float, float, float, float]], ...] = (
    (r"claude-fable-5-1", (10.0, 50.0, 0.25, 12.5)),
    (r"claude-fable-5", (10.0, 50.0, 1.0, 12.5)),
    (r"claude-opus-5-5", (4.0, 20.0, 0.2, 5.0)),
    (r"claude-opus-(5|4-[5-8])", (5.0, 25.0, 0.5, 6.25)),
    (r"claude-opus-4", (15.0, 75.0, 1.5, 18.75)),
    (r"claude-sonnet-5-5", (2.0, 10.0, 0.1, 2.5)),
    (r"claude-sonnet-5", (2.0, 10.0, 0.2, 2.5)),
    (r"claude-sonnet-4", (3.0, 15.0, 0.3, 3.75)),
    (r"claude-haiku-5-5", (0.1, 0.5, 0.01, 0.125)),
    (r"claude-haiku-4-5", (1.0, 5.0, 0.1, 1.25)),
    (r"gemini-4-argon", (2.0, 10.0, 0.1, 0.0)),
    (r"gemini-3\.8-flash", (0.75, 3.75, 0.075, 0.0)),
    (r"gemini-(3\.1-)?pro", (2.0, 12.0, 0.2, 0.0)),
    (r"gpt-5\.5", (5.0, 30.0, 0.5, 0.0)),
    (r"gpt-5\.3-codex", (1.75, 14.0, 0.175, 0.0)),
)
FAMILIES = ("claude-", "gemini-", "gpt-", "o1", "o3", "o4", "codex-")

_remote: dict[str, tuple[float, float, float, float]] | None = None
_fetched_at: float | None = None


def cache_path() -> Path:
    return paths.cache_dir() / "prices.json"


def parse_litellm(data) -> dict[str, tuple[float, float, float, float]]:
    """{model id: per-1M prices} for first-party chat models in LiteLLM's list."""
    out = {}
    for model, entry in (data.items() if isinstance(data, dict) else []):
        if not isinstance(entry, dict) or "/" in model or "." in model.split("-")[0] \
                or not model.startswith(FAMILIES):
            continue

        def per_m(key):
            v = entry.get(key)
            return round(float(v) * 1_000_000, 6) if isinstance(v, (int, float)) and v >= 0 else None

        inp, out_ = per_m("input_cost_per_token"), per_m("output_cost_per_token")
        if inp is None or out_ is None:
            continue
        p = (inp, out_, per_m("cache_read_input_token_cost") or 0.0, per_m("cache_creation_input_token_cost") or 0.0)
        if all(x <= MAX_PRICE for x in p):
            out[model.lower()] = p
    return out


def parse_openrouter(data) -> dict[str, tuple[float, float, float, float]]:
    """{model id in LiteLLM's spelling: per-1M prices} from OpenRouter's /models reply."""
    models = data.get("data") if isinstance(data, dict) else None
    out = {}
    for m in models if isinstance(models, list) else []:
        mid, pr = (m.get("id"), m.get("pricing")) if isinstance(m, dict) else (None, None)
        if not isinstance(mid, str) or not isinstance(pr, dict) or ":" in mid or not mid.startswith(OPENROUTER_VENDORS):
            continue
        model = mid.split("/", 1)[1].lower()
        if model.startswith("claude-"):
            model = model.replace(".", "-")  # Anthropic ids use dashes: claude-opus-5-5

        def per_m(key):
            try:
                v = float(pr.get(key) or 0)
            except (TypeError, ValueError):
                return None
            return round(v * 1_000_000, 6) if v >= 0 else None

        p = (per_m("prompt"), per_m("completion"), per_m("input_cache_read"), per_m("input_cache_write"))
        if None not in p and p[0] > 0 and p[1] > 0 and all(x <= MAX_PRICE for x in p):
            out[model] = p
    return out


def _download(url: str):
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())


def _load_cache() -> None:
    global _remote, _fetched_at
    if _remote is not None:
        return
    raw = read_json(cache_path(), {})
    prices = raw.get("prices") if isinstance(raw, dict) else None
    _remote = {k: tuple(v) for k, v in prices.items()
               if isinstance(v, list) and len(v) == 4} if isinstance(prices, dict) else {}
    _fetched_at = raw.get("fetched_at") if isinstance(raw, dict) else None


def refresh(now: float | None = None, force: bool = False, fetch=_download) -> bool:
    """Download the price lists when the cached copy is a week old. True when it changed.

    LiteLLM's list is required; OpenRouter only fills gaps, so a failure there is not one.
    """
    global _remote, _fetched_at
    now = time.time() if now is None else now
    _load_cache()
    if not force and _fetched_at and now - _fetched_at < REFRESH_AFTER:
        return False
    try:
        prices = parse_litellm(fetch(REMOTE_URL))
    except (OSError, ValueError) as e:
        log.info("prices: LiteLLM download failed (%s)", type(e).__name__)
        return False
    if not prices:
        return False
    try:
        extra = parse_openrouter(fetch(OPENROUTER_URL))
    except (OSError, ValueError) as e:
        log.info("prices: OpenRouter download failed (%s)", type(e).__name__)
        extra = {}
    prices = {**extra, **prices}  # LiteLLM wins wherever both have the model
    _remote, _fetched_at = prices, now
    write_json(cache_path(), {"fetched_at": now, "sources": [REMOTE_URL, OPENROUTER_URL],
                              "prices": {k: list(v) for k, v in prices.items()}})
    return True


def as_of() -> str:
    """Date of the prices in use: the download's, else the built-in table's."""
    _load_cache()
    return datetime.fromtimestamp(_fetched_at).strftime("%Y-%m-%d") if _remote and _fetched_at else BUILTIN_AS_OF


def price(model: str) -> tuple[float, float, float, float] | None:
    m = model.lower()
    _load_cache()
    if _remote:
        # Antigravity adds variant tags ("gemini-3.8-flash-n", "claude-opus-5-5-medium"):
        # the longest known prefix is the model. Two-part prefixes only as the whole id, so
        # "gemini-pro-default" does not land on the old "gemini-pro".
        hit = _remote.get(m)
        parts = m.split("-")
        for n in range(len(parts) - 1, 2, -1):
            hit = hit or _remote.get("-".join(parts[:n]))
        if hit:
            return hit
    for pattern, p in PRICES:
        if re.match(pattern, m):
            return p
    return None


def cost(model: str, t: Tokens) -> float | None:
    """USD for these tokens at list price, or None for a model without a known price."""
    p = price(model)
    if p is None:
        return None
    return (t.input * p[0] + t.output * p[1] + t.cache_read * p[2] + t.cache_write * p[3]) / 1_000_000
