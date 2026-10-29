"""API list prices, to put a rough dollar figure on locally recorded tokens.

Subscriptions are not billed per token; this is what the same tokens would cost on the
provider's pay-as-you-go API. Prices are USD per 1M tokens: (input, output, cache read,
cache write). Checked October 2026 (Anthropic model table; Google and OpenAI pricing pages as
reported by price trackers). Models not listed get no price rather than a guess.
"""

from __future__ import annotations

import re

from .model import Tokens

AS_OF = "2026-10"
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


def price(model: str) -> tuple[float, float, float, float] | None:
    m = model.lower()
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
