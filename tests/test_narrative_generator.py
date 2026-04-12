"""Tests for the LLM call + guardrail layer.

Mocks `pydantic_ai.Agent.run_sync` so no network is needed. Covers:
  - Clean path → narrative returned + usage fields populated
  - Forbidden phrase → guardrail error, narrative=None
  - Missing quadrant anchor → guardrail error
  - Agent raises → api_error captured, no crash
  - Missing API key → config error, no call
"""
from __future__ import annotations

import sys
import types
import unittest
from datetime import date
from unittest.mock import MagicMock, patch


# ── Stub pydantic-ai if it isn't installed in the test env ──────────────
# The generator imports `Agent` lazily inside generate_narrative(); we patch
# the module path so the test never needs the real pydantic-ai dep.

def _install_pydantic_ai_stub():
    if "pydantic_ai" in sys.modules:
        return
    mod = types.ModuleType("pydantic_ai")

    class _Agent:
        def __init__(self, model, output_type=None, system_prompt=None, **kwargs):
            self.model = model
            self.output_type = output_type
            self.system_prompt = system_prompt

        def run_sync(self, user_prompt):
            raise RuntimeError("stub agent; tests should patch this")

    mod.Agent = _Agent
    sys.modules["pydantic_ai"] = mod


_install_pydantic_ai_stub()


# Provide a stub for the google model path as well, so providers.build_model
# doesn't blow up if tests accidentally invoke it. We avoid calling build_model
# directly — our tests patch it — but the stubs defuse import-time hazards.
def _install_google_stubs():
    for name, attr in [
        ("pydantic_ai.models.google", "GoogleModel"),
        ("pydantic_ai.providers.google_gla", "GoogleGLAProvider"),
    ]:
        if name in sys.modules:
            continue
        mod = types.ModuleType(name)
        setattr(mod, attr, lambda *a, **kw: object())
        sys.modules[name] = mod


_install_google_stubs()


from phase0.config import Settings
from worker.narrative.context import NarrativeContext, MetricEntry
from worker.narrative.generator import (
    Narrative,
    generate_narrative,
    validate_guardrails,
)
from worker.narrative.providers import NarrativeConfigError


def _settings(**overrides) -> Settings:
    defaults = dict(
        provider="nse_udiff",
        upstox_api_key="",
        upstox_api_secret="",
        upstox_redirect_url="",
        session_state_path="./state/session.json",
        artifacts_dir="./artifacts",
        risk_free_rate=0.06,
        phase0_symbol="NIFTY",
        spot_instrument_key="NSE_INDEX|Nifty 50",
        derivative_segment="NSE_FO",
        store_raw_json_in_db=False,
        expired_history_months=6,
        supabase_db_url=None,
        gemini_api_key="test-key",
        narrative_enabled=True,
        narrative_provider="google-gla",
        narrative_model="gemma-4-31b-it",
    )
    from pathlib import Path
    defaults["session_state_path"] = Path(defaults["session_state_path"])
    defaults["artifacts_dir"] = Path(defaults["artifacts_dir"])
    defaults.update(overrides)
    return Settings(**defaults)


def _ctx(quadrant: str = "Stress") -> NarrativeContext:
    return NarrativeContext(
        brief_date=date(2026, 4, 12),
        quadrant=quadrant,
        state_score=57.3,
        stress_score=28.1,
        grid_metrics=[
            MetricEntry("atm_iv_30d", "ATM IV 30D", 0.20, 93.0, 93.0, "grid"),
        ],
    )


def _mock_result(narrative_text: str) -> MagicMock:
    """Build a fake pydantic-ai result object that looks like what the
    generator expects: `.data.narrative` + `.usage().request_tokens` etc."""
    result = MagicMock()
    result.output = Narrative(narrative=narrative_text)
    usage = MagicMock()
    usage.request_tokens = 500
    usage.response_tokens = 80
    result.usage.return_value = usage
    return result


class TestGuardrails(unittest.TestCase):
    def test_clean_narrative_passes(self):
        text = "Stress regime persists as 30D vol holds near extremes and downside skew widens."
        self.assertIsNone(validate_guardrails(text, "Stress"))

    def test_forbidden_first_person(self):
        err = validate_guardrails("I see stress regime is elevated.", "Stress")
        self.assertIsNotNone(err)
        self.assertIn("forbidden", err)

    def test_forbidden_advice_verb(self):
        err = validate_guardrails("Stress regime. Traders should buy downside.", "Stress")
        self.assertIsNotNone(err)

    def test_missing_quadrant_rejected(self):
        text = "Volatility holds near extremes; skew widens across tenors."
        err = validate_guardrails(text, "Stress")
        self.assertIsNotNone(err)
        self.assertIn("quadrant_not_mentioned", err)

    def test_empty_rejected(self):
        self.assertEqual(validate_guardrails("", "Stress"), "empty")


class TestGenerateNarrative(unittest.TestCase):
    def test_happy_path(self):
        settings = _settings()
        ctx = _ctx("Stress")
        text = "Stress regime persists as 30D ATM vol sits at multi-month highs while downside skew trades at extremes."

        with patch("worker.narrative.generator.build_model", return_value=MagicMock()), \
             patch.object(sys.modules["pydantic_ai"].Agent, "run_sync",
                          return_value=_mock_result(text), create=True):
            result = generate_narrative(ctx, settings)

        self.assertTrue(result.succeeded)
        self.assertEqual(result.narrative, text)
        self.assertEqual(result.provider, "google-gla")
        self.assertEqual(result.model, "gemma-4-31b-it")
        self.assertIsNone(result.guardrail_error)
        self.assertIsNone(result.api_error)
        self.assertIsNotNone(result.latency_ms)

    def test_missing_api_key_returns_config_error(self):
        settings = _settings(gemini_api_key=None)
        ctx = _ctx("Stress")

        result = generate_narrative(ctx, settings)

        self.assertFalse(result.succeeded)
        self.assertIsNone(result.narrative)
        self.assertIn("config", result.api_error or "")

    def test_guardrail_rejection(self):
        settings = _settings()
        ctx = _ctx("Stress")
        # Contains "I " which is a forbidden first-person substring.
        bad_text = "I observe Stress regime with elevated vol and wider skew across the surface."

        with patch("worker.narrative.generator.build_model", return_value=MagicMock()), \
             patch.object(sys.modules["pydantic_ai"].Agent, "run_sync",
                          return_value=_mock_result(bad_text), create=True):
            result = generate_narrative(ctx, settings)

        self.assertFalse(result.succeeded)
        self.assertIsNone(result.narrative)
        self.assertIsNotNone(result.guardrail_error)
        self.assertIn("forbidden", result.guardrail_error)

    def test_agent_exception_captured_as_api_error(self):
        settings = _settings()
        ctx = _ctx("Stress")

        def _raise(*a, **kw):
            raise RuntimeError("rate_limit_exceeded")

        with patch("worker.narrative.generator.build_model", return_value=MagicMock()), \
             patch.object(sys.modules["pydantic_ai"].Agent, "run_sync",
                          side_effect=_raise, create=True):
            result = generate_narrative(ctx, settings)

        self.assertFalse(result.succeeded)
        self.assertIsNone(result.narrative)
        self.assertIn("rate_limit_exceeded", result.api_error)


if __name__ == "__main__":
    unittest.main()
