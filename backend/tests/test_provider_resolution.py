"""A row's remembered "provider" is not always a provider.

Reported as issue #5: a card made by hand is stored with provider "manual", which matched none of the
real backends and fell through to "some OpenAI-compatible server on localhost:1234". A user with only
a NanoGPT key got "[Errno 61] Connection refused" from a local server they had never run.
"""
import os

import pytest

import generator as G

NOT_PROVIDERS = ["manual", "import", "helper", "text-module", "", "   ", None, "default", "wat"]


@pytest.fixture
def keys(monkeypatch):
    def set_keys(nano="", openr=""):
        monkeypatch.setenv("NANOGPT_API_KEY", nano)
        monkeypatch.setenv("OPENROUTER_API_KEY", openr)
    return set_keys


@pytest.mark.parametrize("stored", NOT_PROVIDERS)
def test_a_word_that_is_not_a_provider_uses_the_configured_one(stored, keys):
    keys(nano="sk-test")
    assert G._resolve_provider(stored) == "nanogpt"


@pytest.mark.parametrize("stored", NOT_PROVIDERS)
def test_it_falls_to_openrouter_when_that_is_the_one_set(stored, keys):
    keys(openr="sk-or-test")
    assert G._resolve_provider(stored) == "openrouter"


@pytest.mark.parametrize("stored", NOT_PROVIDERS)
def test_with_nothing_configured_it_still_means_local(stored, keys):
    keys()
    assert G._resolve_provider(stored) == "local"


@pytest.mark.parametrize("real", ["nanogpt", "openrouter", "local"])
def test_a_real_provider_is_left_alone(real, keys):
    keys(nano="sk-test", openr="sk-or-test")
    assert G._resolve_provider(real) == real
    assert G._resolve_provider(real.upper()) == real       # and case does not matter


def test_the_reported_bug_the_request_no_longer_goes_to_localhost(keys, monkeypatch):
    """Issue #5 exactly: a manual card, a NanoGPT key set, no local server."""
    keys(nano="sk-test")
    monkeypatch.delenv("LOCAL_OPENAI_BASE_URL", raising=False)
    url, headers, payload = G._build_request("manual", "", "sys", "user")
    assert "localhost" not in url and "127.0.0.1" not in url
    assert "nano-gpt.com" in url
    assert headers.get("Authorization", "").endswith("sk-test")


def test_a_local_card_still_goes_local(keys, monkeypatch):
    keys(nano="sk-test")                                   # a key is set, but the card says local
    monkeypatch.setenv("LOCAL_OPENAI_BASE_URL", "http://localhost:4321/v1")
    url, _, _ = G._build_request("local", "", "sys", "user")
    assert url.startswith("http://localhost:4321/v1")


def test_with_no_keys_a_manual_card_goes_where_the_local_server_is(keys, monkeypatch):
    keys()
    monkeypatch.setenv("LOCAL_OPENAI_BASE_URL", "http://localhost:1234/v1")
    url, _, _ = G._build_request("manual", "", "sys", "user")
    assert url == "http://localhost:1234/v1/chat/completions"
