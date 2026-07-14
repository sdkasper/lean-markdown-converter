"""Tests for core/llm_factory.py — provider selection and MarkItDown wiring.

All LLM/client construction is mocked — zero network calls, no real API
keys anywhere. openai is stubbed via sys.modules injection so build_markitdown's
lazy `import openai` picks up the fake module instead of the real SDK.
"""

import sys
import types

import pytest

from core.llm_factory import PROVIDER_PRESETS, LLMConfigError, build_markitdown


class _FakeOpenAIClient:
    """Records the kwargs it was constructed with, for assertions."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _install_fake_openai(monkeypatch, raise_on_construct=None):
    """Inject a fake openai module. Returns the list that captures each
    OpenAI(...) call's kwargs, in construction order.
    """
    calls = []
    fake_module = types.ModuleType("openai")

    class OpenAI:
        def __init__(self, **kwargs):
            if raise_on_construct is not None:
                raise raise_on_construct
            calls.append(kwargs)
            self.kwargs = kwargs

    fake_module.OpenAI = OpenAI
    monkeypatch.setitem(sys.modules, "openai", fake_module)
    return calls


# ─── disabled / exif mode -> plain MarkItDown, no LLM ──────────────────────

def test_none_config_returns_plain_markitdown():
    md = build_markitdown(None)
    assert md._llm_client is None
    assert md._llm_model is None


def test_empty_dict_returns_plain_markitdown():
    md = build_markitdown({})
    assert md._llm_client is None


def test_disabled_returns_plain_markitdown(monkeypatch):
    _install_fake_openai(monkeypatch)
    md = build_markitdown({"enabled": False, "mode": "ocr", "provider": "gemini", "api_key": "secret"})
    assert md._llm_client is None


def test_exif_mode_returns_plain_markitdown_even_if_enabled(monkeypatch):
    _install_fake_openai(monkeypatch)
    md = build_markitdown({"enabled": True, "mode": "exif", "provider": "gemini", "api_key": "secret"})
    assert md._llm_client is None


# ─── gemini preset ──────────────────────────────────────────────────────────

def test_gemini_preset_uses_default_base_url_and_model(monkeypatch):
    calls = _install_fake_openai(monkeypatch)
    md = build_markitdown({
        "enabled": True,
        "mode": "ocr",
        "provider": "gemini",
        "api_key": "my-secret-key",
    })
    assert len(calls) == 1
    assert calls[0]["api_key"] == "my-secret-key"
    assert calls[0]["base_url"] == PROVIDER_PRESETS["gemini"]["base_url"]
    assert md._llm_model == "gemini-flash-latest"
    assert md._llm_client is not None


def test_gemini_without_key_raises_and_omits_key_material(monkeypatch):
    _install_fake_openai(monkeypatch)
    with pytest.raises(LLMConfigError) as exc_info:
        build_markitdown({"enabled": True, "mode": "ocr", "provider": "gemini", "api_key": ""})
    message = str(exc_info.value)
    assert "gemini" in message
    assert "my-secret-key" not in message


def test_user_edited_model_and_base_url_override_preset(monkeypatch):
    calls = _install_fake_openai(monkeypatch)
    md = build_markitdown({
        "enabled": True,
        "mode": "ocr",
        "provider": "gemini",
        "api_key": "key123",
        "model": "gemini-1.5-pro",
        "base_url": "https://custom.example.com/v1beta/openai/",
    })
    assert calls[0]["base_url"] == "https://custom.example.com/v1beta/openai/"
    assert md._llm_model == "gemini-1.5-pro"


# ─── ollama preset ──────────────────────────────────────────────────────────

def test_ollama_no_key_injects_placeholder(monkeypatch):
    calls = _install_fake_openai(monkeypatch)
    md = build_markitdown({"enabled": True, "mode": "ocr", "provider": "ollama", "api_key": ""})
    assert calls[0]["api_key"] == "ollama"
    assert calls[0]["base_url"] == PROVIDER_PRESETS["ollama"]["base_url"]
    assert md._llm_model == "llava"


def test_ollama_no_key_does_not_raise(monkeypatch):
    _install_fake_openai(monkeypatch)
    # Should not raise LLMConfigError since ollama doesn't need a key.
    build_markitdown({"enabled": True, "mode": "ocr", "provider": "ollama", "api_key": ""})


# ─── custom preset ──────────────────────────────────────────────────────────

def test_custom_with_base_url_model_key_passed_through(monkeypatch):
    calls = _install_fake_openai(monkeypatch)
    md = build_markitdown({
        "enabled": True,
        "mode": "ocr",
        "provider": "custom",
        "api_key": "custom-key",
        "model": "gpt-4o",
        "base_url": "https://api.example.com/v1",
    })
    assert calls[0]["api_key"] == "custom-key"
    assert calls[0]["base_url"] == "https://api.example.com/v1"
    assert md._llm_model == "gpt-4o"


def test_custom_without_model_raises(monkeypatch):
    _install_fake_openai(monkeypatch)
    with pytest.raises(LLMConfigError):
        build_markitdown({
            "enabled": True,
            "mode": "ocr",
            "provider": "custom",
            "api_key": "custom-key",
            "model": "",
            "base_url": "https://api.example.com/v1",
        })


def test_custom_without_base_url_falls_through_but_needs_model(monkeypatch):
    calls = _install_fake_openai(monkeypatch)
    md = build_markitdown({
        "enabled": True,
        "mode": "ocr",
        "provider": "custom",
        "api_key": "custom-key",
        "model": "gpt-4o",
        "base_url": "",
    })
    # No base_url passed through to OpenAI() -> falls through to official endpoint.
    assert "base_url" not in calls[0]
    assert calls[0]["api_key"] == "custom-key"
    assert md._llm_model == "gpt-4o"


# ─── unknown provider ───────────────────────────────────────────────────────

def test_unknown_provider_raises(monkeypatch):
    _install_fake_openai(monkeypatch)
    with pytest.raises(LLMConfigError):
        build_markitdown({"enabled": True, "mode": "ocr", "provider": "not-a-real-provider", "api_key": "key"})


# ─── openai.OpenAI construction failure ────────────────────────────────────

def test_openai_construction_failure_wrapped_in_llmconfigerror(monkeypatch):
    _install_fake_openai(monkeypatch, raise_on_construct=RuntimeError("boom"))
    with pytest.raises(LLMConfigError) as exc_info:
        build_markitdown({"enabled": True, "mode": "ocr", "provider": "gemini", "api_key": "key123"})
    message = str(exc_info.value)
    assert "RuntimeError" in message
    assert "key123" not in message


def test_openai_construction_failure_leaves_no_partial_state(monkeypatch):
    """After a failed build, a subsequent successful call must work cleanly -
    no partial/global state left behind by the failed attempt."""
    _install_fake_openai(monkeypatch, raise_on_construct=RuntimeError("boom"))
    with pytest.raises(LLMConfigError):
        build_markitdown({"enabled": True, "mode": "ocr", "provider": "gemini", "api_key": "key123"})

    calls = _install_fake_openai(monkeypatch)
    md = build_markitdown({"enabled": True, "mode": "ocr", "provider": "gemini", "api_key": "key123"})
    assert md._llm_client is not None
    assert len(calls) == 1
