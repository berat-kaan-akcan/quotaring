import time

from quotaring import pricing
from quotaring.model import Tokens

NOW = time.time()
LIST = {
    "sample_spec": {"input_cost_per_token": 0},
    "claude-opus-5-5": {"input_cost_per_token": 4e-06, "output_cost_per_token": 2e-05,
                        "cache_read_input_token_cost": 2e-07, "cache_creation_input_token_cost": 5e-06},
    "gemini-3.8-flash": {"input_cost_per_token": 7.5e-07, "output_cost_per_token": 3.75e-06,
                         "cache_read_input_token_cost": 7.5e-08},
    "gemini-pro": {"input_cost_per_token": 5e-07, "output_cost_per_token": 1.5e-06},
    "gpt-5.5": {"input_cost_per_token": 6e-06, "output_cost_per_token": 3e-05},
    "us.anthropic.claude-opus-5-5": {"input_cost_per_token": 4.4e-06, "output_cost_per_token": 2.2e-05},
    "bedrock/claude-x": {"input_cost_per_token": 1e-06, "output_cost_per_token": 1e-06},
    "claude-broken": {"input_cost_per_token": "free", "output_cost_per_token": 1e-06},
    "claude-absurd": {"input_cost_per_token": 1.0, "output_cost_per_token": 1.0},
}
ROUTER = {"data": [
    {"id": "google/gemini-4-argon", "pricing": {"prompt": "0.000002", "completion": "0.00001",
                                                 "input_cache_read": "0.0000001"}},
    {"id": "google/gemini-4-argon:batch", "pricing": {"prompt": "0.000001", "completion": "0.000005"}},
    {"id": "google/gemini-3.8-flash", "pricing": {"prompt": "0.000000825", "completion": "0.000004125"}},
    {"id": "anthropic/claude-haiku-9.5", "pricing": {"prompt": "0.000001", "completion": "0.000005",
                                                     "input_cache_read": "0.0000001", "input_cache_write": "0.00000125"}},
    {"id": "meta/llama-9", "pricing": {"prompt": "0.000001", "completion": "0.000001"}},
    {"id": "openai/gpt-free", "pricing": {"prompt": "0", "completion": "0"}},
    {"id": "openai/gpt-odd", "pricing": {"prompt": "n/a", "completion": "0.000001"}},
]}


def lists(url):
    return ROUTER if url == pricing.OPENROUTER_URL else LIST


def test_parse_keeps_first_party_models_only():
    p = pricing.parse_litellm(LIST)
    assert set(p) == {"claude-opus-5-5", "gemini-3.8-flash", "gemini-pro", "gpt-5.5"}
    assert p["claude-opus-5-5"] == (4.0, 20.0, 0.2, 5.0)
    assert p["gemini-3.8-flash"][3] == 0.0  # no cache write price listed
    assert pricing.parse_litellm([]) == {}


def test_parse_openrouter():
    p = pricing.parse_openrouter(ROUTER)
    assert set(p) == {"gemini-4-argon", "gemini-3.8-flash", "claude-haiku-9-5"}  # Anthropic ids get dashes
    assert p["gemini-4-argon"] == (2.0, 10.0, 0.1, 0.0)
    assert pricing.parse_openrouter({"data": "x"}) == {} and pricing.parse_openrouter(None) == {}


def test_openrouter_only_fills_gaps():
    assert pricing.refresh(NOW, fetch=lists) is True
    assert pricing.price("gemini-4-argon-trial") == (2.0, 10.0, 0.1, 0.0)  # OpenRouter: LiteLLM lacks it
    assert pricing.price("gemini-3.8-flash-n")[0] == 0.75  # LiteLLM's list price, not OpenRouter's 0.825
    assert pricing.price("claude-haiku-9-5") == (1.0, 5.0, 0.1, 1.25)


def test_openrouter_failure_is_not_fatal_but_litellm_is():
    def no_router(url):
        if url == pricing.OPENROUTER_URL:
            raise OSError("down")
        return LIST

    assert pricing.refresh(NOW, fetch=no_router) is True and pricing.price("gpt-5.5")[0] == 6.0

    def no_litellm(url):
        if url == pricing.REMOTE_URL:
            raise OSError("down")
        return ROUTER

    assert pricing.refresh(NOW, force=True, fetch=no_litellm) is False
    assert pricing.price("gemini-3.8-flash")[0] == 0.75  # kept the earlier list


def test_refresh_downloads_weekly_and_caches(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        return lists(url)

    assert pricing.as_of() == pricing.BUILTIN_AS_OF
    assert pricing.refresh(NOW, fetch=fetch) is True
    assert pricing.refresh(NOW + 3600, fetch=fetch) is False  # fresh: no second download
    assert calls == [pricing.REMOTE_URL, pricing.OPENROUTER_URL] and pricing.cache_path().is_file()
    assert pricing.price("gpt-5.5") == (6.0, 30.0, 0.0, 0.0)  # the list wins over the table
    # Another start reads the cached copy.
    pricing._remote = pricing._fetched_at = None
    assert pricing.price("gpt-5.5")[0] == 6.0 and pricing.as_of() != pricing.BUILTIN_AS_OF
    assert pricing.refresh(NOW + pricing.REFRESH_AFTER + 1, fetch=fetch) is True and len(calls) == 4


def test_failed_download_keeps_what_there_is():
    def broken(url):
        raise OSError("offline")

    assert pricing.refresh(NOW, fetch=broken) is False
    assert pricing.refresh(NOW, fetch=lambda url: {"nothing": {}}) is False
    assert pricing.price("claude-opus-5-5") == (4.0, 20.0, 0.2, 5.0)  # built-in table


def test_variant_ids_and_fallback():
    pricing.refresh(NOW, fetch=lambda url: LIST)
    assert pricing.price("claude-opus-5-5-medium") == (4.0, 20.0, 0.2, 5.0)
    assert pricing.price("gemini-3.8-flash-n")[0] == 0.75
    assert pricing.price("gemini-pro-default") == (2.0, 12.0, 0.2, 0.0)  # not the old gemini-pro
    assert pricing.price("gemini-4-argon-trial") == (2.0, 10.0, 0.1, 0.0)  # missing from the list
    assert pricing.price("mystery-model") is None
    assert pricing.cost("claude-opus-5-5", Tokens(output=1_000_000)) == 20.0
