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
        "model": "gemini-flash-latest",
        "needs_key": True,
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "model": "glm-ocr",
        "needs_key": False,
    },
    "custom": {
        "base_url": "",
        "model": "",
        "needs_key": True,
    },
}

# Generation caps injected into every OCR request (MarkItDown itself passes
# neither). Small local models (e.g. glm-ocr) can fall into repetition loops
# on dense document pages; without a token cap one image can degenerate into
# thousands of lines of garbage (observed live 2026-07-14 on an academic
# paper page). The caps also bound worst-case cost on paid cloud providers.
# - max_tokens: a clean dense-page extraction measures ~1,300 tokens; 4096
#   leaves generous headroom while cutting runaway loops.
# - frequency_penalty: 0.4 is mild enough not to corrupt legitimately
#   repetitive document text (tables), strong enough to break loop attractors.
OCR_MAX_TOKENS = 4096
OCR_FREQUENCY_PENALTY = 0.4

# Default prompt sent with every OCR image request. MarkItDown's built-in
# ImageConverter prompt is "Write a detailed caption for this image.", which
# makes vision models (qwen3.5:9b especially) paraphrase or summarize instead
# of transcribing. This override keeps the intent verbatim-transcription.
# Users can replace it via the optional image_conversion.llm_prompt config key.
DEFAULT_LLM_PROMPT = (
    "Transcribe all text in this image exactly as written, formatted as "
    "Markdown. Preserve the original wording verbatim - do not summarize, "
    "paraphrase, or translate. Preserve structure such as headings, lists, "
    "and tables. If the image contains no text, write a concise description "
    "of it instead."
)


def resolve_llm_prompt(image_conversion: Optional[dict]) -> Optional[str]:
    """Return the effective OCR prompt for image files, or None.

    None means "OCR mode is not active - do not pass an llm_prompt kwarg",
    which keeps MarkItDown's default behavior for EXIF mode and for embedded
    images in non-image documents. When OCR is active, a non-empty
    image_conversion["llm_prompt"] wins; otherwise DEFAULT_LLM_PROMPT.
    """
    config = image_conversion or {}
    if not config.get("enabled", False) or config.get("mode", "exif") != "ocr":
        return None

    custom = str(config.get("llm_prompt") or "").strip()
    return custom or DEFAULT_LLM_PROMPT


def _apply_generation_caps(client) -> None:
    """Wrap client.chat.completions.create so OCR calls get default caps.

    This shadows the bound method with a plain function attribute - callers
    (MarkItDown) simply invoke it, nothing subclasses it, so this is safe
    (unlike the v1.1.0 hide_console.py Popen-as-function bug, which broke
    because asyncio SUBCLASSES what it patched). Explicitly passed values
    always win via setdefault.
    """
    original_create = client.chat.completions.create

    def create_with_caps(*args, **kwargs):
        kwargs.setdefault("max_tokens", OCR_MAX_TOKENS)
        kwargs.setdefault("frequency_penalty", OCR_FREQUENCY_PENALTY)
        return original_create(*args, **kwargs)

    client.chat.completions.create = create_with_caps


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
        _apply_generation_caps(client)

        return MarkItDown(llm_client=client, llm_model=model)
    except LLMConfigError:
        raise
    except Exception as e:
        error_type = type(e).__name__
        raise LLMConfigError(f"Failed to initialize LLM client ({error_type}): {e}") from e
