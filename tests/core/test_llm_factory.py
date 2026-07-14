"""Tests for core/llm_factory.py — provider selection and MarkItDown wiring.

All LLM/client construction is mocked — zero network calls, no real API
keys anywhere. openai is stubbed via sys.modules injection so build_markitdown's
lazy `import openai` picks up the fake module instead of the real SDK.
"""

import sys
import types

import pytest

from core.llm_factory import (
    DEFAULT_LLM_PROMPT,
    PROVIDER_PRESETS,
    LLMConfigError,
    build_markitdown,
    resolve_llm_prompt,
)


class _FakeOpenAIClient:
    """Records the kwargs it was constructed with, for assertions."""

    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _install_fake_openai(monkeypatch, raise_on_construct=None):
    """Inject a fake openai module. Returns the list that captures each
    OpenAI(...) call's kwargs, in construction order.

    The fake client exposes the real SDK's chat.completions.create attribute
    chain (which MarkItDown calls and _apply_generation_caps wraps); each
    create() call's kwargs are recorded on client.create_calls.
    """
    calls = []
    fake_module = types.ModuleType("openai")

    class OpenAI:
        def __init__(self, **kwargs):
            if raise_on_construct is not None:
                raise raise_on_construct
            calls.append(kwargs)
            self.kwargs = kwargs
            self.create_calls = []

            client = self

            class _Completions:
                @staticmethod
                def create(*args, **create_kwargs):
                    client.create_calls.append(create_kwargs)
                    return types.SimpleNamespace(
                        choices=[types.SimpleNamespace(
                            message=types.SimpleNamespace(content="fake"))]
                    )

            self.chat = types.SimpleNamespace(completions=_Completions())

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
    assert md._llm_model == "glm-ocr"


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


# ─── generation caps (anti repetition-loop / runaway-cost guard) ────────────

def test_ollama_requests_get_full_generation_caps(monkeypatch):
    """Small local models can degenerate into repetition loops on dense
    pages; ollama OCR create() calls must carry max_tokens,
    frequency_penalty AND the reasoning kill-switch (thinking models like
    qwen3.5 otherwise burn the whole token budget in their hidden reasoning
    channel and return empty content - observed live 2026-07-14)."""
    from core.llm_factory import (
        OCR_FREQUENCY_PENALTY,
        OCR_MAX_TOKENS,
        OCR_REASONING_EFFORT,
    )

    _install_fake_openai(monkeypatch)
    md = build_markitdown({"enabled": True, "mode": "ocr", "provider": "ollama", "api_key": ""})
    client = md._llm_client

    client.chat.completions.create(model="glm-ocr", messages=[])

    assert len(client.create_calls) == 1
    assert client.create_calls[0]["max_tokens"] == OCR_MAX_TOKENS
    assert client.create_calls[0]["frequency_penalty"] == OCR_FREQUENCY_PENALTY
    assert client.create_calls[0]["extra_body"] == {"reasoning_effort": OCR_REASONING_EFFORT}


def test_gemini_never_gets_frequency_penalty(monkeypatch):
    """Gemini's OpenAI-compatible endpoint rejects frequency_penalty with
    400 INVALID_ARGUMENT (observed live 2026-07-14, failed every image);
    it must receive max_tokens only."""
    from core.llm_factory import OCR_MAX_TOKENS

    _install_fake_openai(monkeypatch)
    md = build_markitdown({"enabled": True, "mode": "ocr", "provider": "gemini", "api_key": "k"})
    client = md._llm_client

    client.chat.completions.create(model="gemini-flash-latest", messages=[])

    assert client.create_calls[0]["max_tokens"] == OCR_MAX_TOKENS
    assert "frequency_penalty" not in client.create_calls[0]
    assert "extra_body" not in client.create_calls[0]


def test_custom_gets_openai_standard_caps_only(monkeypatch):
    """Custom endpoints get the OpenAI-standard caps but not the
    ollama-specific reasoning kill-switch (unknown endpoint tolerance)."""
    from core.llm_factory import OCR_FREQUENCY_PENALTY, OCR_MAX_TOKENS

    _install_fake_openai(monkeypatch)
    md = build_markitdown({
        "enabled": True, "mode": "ocr", "provider": "custom",
        "base_url": "https://example.invalid/v1", "model": "m", "api_key": "k",
    })
    client = md._llm_client

    client.chat.completions.create(model="m", messages=[])

    assert client.create_calls[0]["max_tokens"] == OCR_MAX_TOKENS
    assert client.create_calls[0]["frequency_penalty"] == OCR_FREQUENCY_PENALTY
    assert "extra_body" not in client.create_calls[0]


def test_explicit_caller_values_override_caps(monkeypatch):
    _install_fake_openai(monkeypatch)
    md = build_markitdown({"enabled": True, "mode": "ocr", "provider": "ollama", "api_key": ""})
    client = md._llm_client

    client.chat.completions.create(
        model="m", messages=[], max_tokens=99, frequency_penalty=0.0,
        extra_body={"reasoning_effort": "high"},
    )

    assert client.create_calls[0]["max_tokens"] == 99
    assert client.create_calls[0]["frequency_penalty"] == 0.0
    assert client.create_calls[0]["extra_body"] == {"reasoning_effort": "high"}


def test_capped_create_still_returns_response(monkeypatch):
    _install_fake_openai(monkeypatch)
    md = build_markitdown({"enabled": True, "mode": "ocr", "provider": "ollama", "api_key": ""})

    response = md._llm_client.chat.completions.create(model="glm-ocr", messages=[])

    assert response.choices[0].message.content == "fake"


# ─── llm_prompt resolution (verbatim transcription override) ────────────────

class TestResolveLlmPrompt:
    def test_none_config_returns_none(self):
        assert resolve_llm_prompt(None) is None
        assert resolve_llm_prompt({}) is None

    def test_disabled_returns_none(self):
        assert resolve_llm_prompt({"enabled": False, "mode": "ocr"}) is None

    def test_exif_mode_returns_none(self):
        assert resolve_llm_prompt({"enabled": True, "mode": "exif"}) is None

    def test_ocr_without_key_uses_default_transcription_prompt(self):
        """Legacy configs have no llm_prompt key at all - default applies."""
        prompt = resolve_llm_prompt({"enabled": True, "mode": "ocr", "provider": "ollama"})
        assert prompt == DEFAULT_LLM_PROMPT

    def test_ocr_with_custom_prompt_wins(self):
        prompt = resolve_llm_prompt({
            "enabled": True, "mode": "ocr", "llm_prompt": "Describe colors only.",
        })
        assert prompt == "Describe colors only."

    def test_blank_or_whitespace_prompt_falls_back_to_default(self):
        assert resolve_llm_prompt({"enabled": True, "mode": "ocr", "llm_prompt": ""}) == DEFAULT_LLM_PROMPT
        assert resolve_llm_prompt({"enabled": True, "mode": "ocr", "llm_prompt": "   "}) == DEFAULT_LLM_PROMPT

    def test_default_prompt_wording_keeps_transcription_intent(self):
        lowered = DEFAULT_LLM_PROMPT.lower()
        assert "transcribe" in lowered
        assert "verbatim" in lowered
        assert "markdown" in lowered
        # Project writing convention: no em dashes / double hyphens anywhere.
        assert "—" not in DEFAULT_LLM_PROMPT
        assert "--" not in DEFAULT_LLM_PROMPT


# ─── end-to-end: prompt reaches the LLM request through MarkItDown ─────────

# Minimal valid 1x1 transparent PNG (magika/MarkItDown detect it as png).
_PNG_1X1 = __import__("base64").b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg=="
)


def _convert_png_through_engine(monkeypatch, tmp_path, config):
    """Drive core.engine.convert_one over a real PNG with a real MarkItDown
    wired to the fake openai client; returns (status, create_calls)."""
    from core.engine import convert_one
    from core.logging_util import RunLogger
    from core.scanner import ConversionTask

    _install_fake_openai(monkeypatch)
    md = build_markitdown(config)

    src = tmp_path / "sample.png"
    src.write_bytes(_PNG_1X1)
    task = ConversionTask(src=src, dst=tmp_path / "sample.md", existed=False)
    logger = RunLogger(tmp_path / "logs", "2.0.1", enabled=False)

    status = convert_one(task, md, logger, llm_prompt=resolve_llm_prompt(config))
    return status, md._llm_client.create_calls


def test_default_prompt_reaches_llm_request_for_image(monkeypatch, tmp_path):
    config = {"enabled": True, "mode": "ocr", "provider": "ollama", "api_key": ""}
    status, create_calls = _convert_png_through_engine(monkeypatch, tmp_path, config)

    assert status == "converted"
    assert len(create_calls) == 1
    assert DEFAULT_LLM_PROMPT in str(create_calls[0]["messages"])


def test_config_prompt_override_reaches_llm_request(monkeypatch, tmp_path):
    config = {
        "enabled": True, "mode": "ocr", "provider": "ollama", "api_key": "",
        "llm_prompt": "Only list the hyperlinks in this image.",
    }
    status, create_calls = _convert_png_through_engine(monkeypatch, tmp_path, config)

    assert status == "converted"
    messages_repr = str(create_calls[0]["messages"])
    assert "Only list the hyperlinks in this image." in messages_repr
    assert DEFAULT_LLM_PROMPT not in messages_repr
