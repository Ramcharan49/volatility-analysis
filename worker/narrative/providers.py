"""Single extension point for LLM providers.

Adding a new provider requires:
  1. One branch in `build_model()` below.
  2. One pip dep (e.g., `pydantic-ai-slim[anthropic]`).
  3. One api-key field on Settings (already wired via phase0/config.py).

Callers never import provider-specific classes directly.
"""
from __future__ import annotations

from phase0.config import Settings


class NarrativeConfigError(RuntimeError):
    """Raised when the settings are incomplete for the selected provider."""


def build_model(settings: Settings):
    """Return a pydantic-ai Model for the configured provider/model_id.

    Imports provider SDKs lazily so we don't pay for pydantic-ai sub-packages
    we haven't installed. `pydantic-ai-slim[google]` is the only hard dep today.
    """
    provider = (settings.narrative_provider or "").strip().lower()
    model_id = settings.narrative_model

    if not model_id:
        raise NarrativeConfigError("NARRATIVE_MODEL is empty")

    if provider == "google-gla":
        if not settings.gemini_api_key:
            raise NarrativeConfigError("GEMINI_API_KEY is required for google-gla provider")
        # Use GoogleProvider (the non-deprecated path in pydantic-ai 0.8.x).
        # GoogleGLAProvider exists but is marked deprecated and returns an
        # httpx.AsyncClient that GoogleModel no longer drives correctly.
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider
        return GoogleModel(
            model_id,
            provider=GoogleProvider(api_key=settings.gemini_api_key),
        )

    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise NarrativeConfigError("ANTHROPIC_API_KEY is required for anthropic provider")
        from pydantic_ai.models.anthropic import AnthropicModel
        return AnthropicModel(model_id, api_key=settings.anthropic_api_key)

    if provider == "openai":
        if not settings.openai_api_key:
            raise NarrativeConfigError("OPENAI_API_KEY is required for openai provider")
        from pydantic_ai.models.openai import OpenAIModel
        return OpenAIModel(model_id, api_key=settings.openai_api_key)

    if provider == "groq":
        if not settings.groq_api_key:
            raise NarrativeConfigError("GROQ_API_KEY is required for groq provider")
        from pydantic_ai.models.groq import GroqModel
        return GroqModel(model_id, api_key=settings.groq_api_key)

    raise NarrativeConfigError(f"Unknown NARRATIVE_PROVIDER: {settings.narrative_provider!r}")
