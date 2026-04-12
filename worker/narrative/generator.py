"""LLM-based narrative generator.

Thin wrapper around pydantic-ai that:
  - Builds a provider-specific model via the `providers` factory.
  - Renders the user prompt from the `NarrativeContext`.
  - Calls the model with a strict Pydantic output schema.
  - Runs post-generation guardrails (forbidden phrases, quadrant anchoring).

Returns a `GenerationResult` dataclass the caller can persist directly into
the `narrative_runs` audit table whether the call succeeded or failed.
Never raises for API or guardrail errors during normal operation — those are
captured in the result so the daily pipeline never goes red on a narrative
issue.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Optional

from pydantic import BaseModel, Field, ValidationError

from phase0.config import Settings

from .context import NarrativeContext
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .providers import NarrativeConfigError, build_model


log = logging.getLogger("worker.narrative")


# ── Output schema enforced by pydantic-ai ────────────────────────────────

class Narrative(BaseModel):
    """Structured LLM output. pydantic-ai will coerce any provider's JSON
    response into this shape; if it can't, it raises before we see anything."""
    narrative: str = Field(min_length=25, max_length=400)


# ── Result surface ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class GenerationResult:
    """What the caller gets back. Only `narrative` is user-visible; all other
    fields land in the `narrative_runs` audit table."""
    narrative: Optional[str]
    provider: str
    model: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    latency_ms: Optional[int] = None
    api_error: Optional[str] = None
    guardrail_error: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        return self.narrative is not None


# ── Public entry point ───────────────────────────────────────────────────

def generate_narrative(ctx: NarrativeContext, settings: Settings) -> GenerationResult:
    """Call the configured LLM once and return a GenerationResult.

    This function does not raise on known failure modes (missing key, rate
    limit, malformed JSON, guardrail rejection). Those are captured in the
    result's `api_error` / `guardrail_error` fields and the caller should
    log them to `narrative_runs` without retrying.
    """
    provider = settings.narrative_provider
    model_id = settings.narrative_model

    # 1. Build the agent (may raise NarrativeConfigError on misconfiguration).
    try:
        model = build_model(settings)
    except NarrativeConfigError as e:
        log.warning("Narrative config error: %s", e)
        return GenerationResult(
            narrative=None, provider=provider, model=model_id,
            api_error=f"config: {e}",
        )

    # Import Agent lazily so test suites without pydantic-ai installed can
    # still import modules that merely reference `GenerationResult`.
    from pydantic_ai import Agent

    agent = Agent(model, output_type=Narrative, system_prompt=SYSTEM_PROMPT)
    user_prompt = build_user_prompt(ctx)

    # 2. Execute the LLM call with wall-clock timing.
    t0 = time.monotonic()
    try:
        result = agent.run_sync(user_prompt)
    except ValidationError as e:
        latency_ms = int((time.monotonic() - t0) * 1000)
        log.warning("Narrative validation failed: %s", e)
        return GenerationResult(
            narrative=None, provider=provider, model=model_id,
            latency_ms=latency_ms, api_error=f"validation: {e}",
        )
    except Exception as e:  # network, auth, rate limit, provider-side, ...
        latency_ms = int((time.monotonic() - t0) * 1000)
        log.warning("Narrative API call failed: %s", e)
        return GenerationResult(
            narrative=None, provider=provider, model=model_id,
            latency_ms=latency_ms, api_error=f"{type(e).__name__}: {e}",
        )
    latency_ms = int((time.monotonic() - t0) * 1000)

    narrative_text = result.output.narrative.strip()

    # 3. Guardrails — last line of defence before we write to the user-visible
    #    column. Any failure here returns None for the narrative.
    guardrail_err = validate_guardrails(narrative_text, ctx.quadrant)
    if guardrail_err:
        log.warning("Narrative rejected by guardrails: %s", guardrail_err)
        return GenerationResult(
            narrative=None, provider=provider, model=model_id,
            latency_ms=latency_ms, guardrail_error=guardrail_err,
        )

    usage = _extract_usage(result)
    log.info(
        "Narrative generated: provider=%s model=%s latency_ms=%d chars=%d "
        "prompt_tokens=%s completion_tokens=%s",
        provider, model_id, latency_ms, len(narrative_text),
        usage.get("prompt_tokens"), usage.get("completion_tokens"),
    )

    return GenerationResult(
        narrative=narrative_text,
        provider=provider,
        model=model_id,
        latency_ms=latency_ms,
        prompt_tokens=usage.get("prompt_tokens"),
        completion_tokens=usage.get("completion_tokens"),
    )


# ── Guardrails ────────────────────────────────────────────────────────────

# Words that turn the narrative into advice or break the third-person voice.
# Case-insensitive substring check with word-boundary care (leading space).
_FORBIDDEN_SUBSTRINGS = (
    " i ", " i'", " i’",           # first-person singular
    " we ", " we'", " we’",        # first-person plural
    " you ", " your ", " you'",    # second-person
    " should ", " must ",
    " recommend",
    " buy ", " sell ", " long ", " short ",
    " our view",
    " my ",
)


def validate_guardrails(narrative: str, quadrant: Optional[str]) -> Optional[str]:
    """Return None if narrative is clean; otherwise a short error string.

    We run these in addition to the Pydantic length bounds because some
    issues (voice drift, advice, missing quadrant anchor) are content
    policy, not schema."""
    if not narrative:
        return "empty"

    padded = f" {narrative.lower()} "
    for needle in _FORBIDDEN_SUBSTRINGS:
        if needle in padded:
            return f"forbidden_phrase: {needle.strip()!r}"

    if quadrant:
        if quadrant.lower() not in narrative.lower():
            return f"quadrant_not_mentioned: {quadrant}"

    return None


# ── Usage extraction (best-effort across pydantic-ai versions) ────────────

def _extract_usage(result) -> dict:
    """pydantic-ai Result.usage() surface varies slightly across versions.
    Fall back gracefully rather than crash on a minor API change."""
    try:
        usage = result.usage()
        prompt = getattr(usage, "request_tokens", None) or getattr(usage, "input_tokens", None)
        completion = getattr(usage, "response_tokens", None) or getattr(usage, "output_tokens", None)
        return {"prompt_tokens": prompt, "completion_tokens": completion}
    except Exception:
        return {}
