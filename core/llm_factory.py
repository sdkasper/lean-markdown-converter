"""MarkItDown factory with optional LLM (OCR/vision) support.

A single code path handles every provider through the openai SDK, since
Gemini exposes an official OpenAI-compatible endpoint — there is no need
for (and this deliberately avoids) a bespoke google-generativeai adapter.
The old GUI/CLI GeminiOpenAIAdapter shim is broken (its .chat is a method,
not an attribute, so MarkItDown's `client.chat.completions.create()` never
resolves) and is not ported here.

openai is imported lazily inside build_markitdown() so importing this
module has no startup-time cost when image OCR is never used.
"""

from typing import Optional

from markitdown import MarkItDown

PROVIDER_PRESETS = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-2.0-flash",
        "needs_key": True,
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "llava",
        "needs_key": False,
    },
    "custom": {
        "base_url": "",
        "model": "",
        "needs_key": True,
    },
}


class LLMConfigError(Exception):
    """Raised when image_conversion config can't be turned into a working
    MarkItDown+LLM client. Never contains API key material.
    """


def build_markitdown(image_conversion: Optional[dict]) -> "MarkItDown":
    """Build a MarkItDown instance, wiring up an LLM client for OCR mode.

    - image_conversion is None/empty, disabled, or mode == "exif" -> a plain
      MarkItDown() with no LLM client (EXIF-only / no-LLM behavior).
    - mode == "ocr" -> resolve the provider preset, build an openai.OpenAI
      client, and return MarkItDown(llm_client=client, llm_model=model).

    No network call happens at construction time - the client is lazy and
    MarkItDown only calls out to the LLM when an image is actually converted.
    """
    config = image_conversion or {}
    enabled = config.get("enabled", False)
    mode = config.get("mode", "exif")

    if not enabled or mode != "ocr":
        return MarkItDown()

    provider = config.get("provider", "")
    preset = PROVIDER_PRESETS.get(provider)
    if preset is None:
        raise LLMConfigError(f"Unknown image conversion provider: '{provider}'")

    base_url = str(config.get("base_url") or preset["base_url"]).strip()
    model = str(config.get("model") or preset["model"]).strip()
    api_key = str(config.get("api_key") or "").strip()

    if provider == "ollama" and not api_key:
        api_key = "ollama"

    if preset["needs_key"] and not api_key:
        raise LLMConfigError(f"{provider} requires an API key")

    if not model:
        raise LLMConfigError(f"{provider} requires a model name")

    try:
        import openai

        client_kwargs = {"api_key": api_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        client = openai.OpenAI(**client_kwargs)

        return MarkItDown(llm_client=client, llm_model=model)
    except LLMConfigError:
        raise
    except Exception as e:
        error_type = type(e).__name__
        raise LLMConfigError(f"Failed to initialize LLM client ({error_type}): {e}") from e
