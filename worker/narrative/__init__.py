"""AI-generated daily regime narrative for the NIFTY vol analytics dashboard.

Entry point: worker.narrative_job (invoked by the daily GitHub Actions step).
All public surface is re-exported here for convenience.
"""
from .context import NarrativeContext, MetricEntry, FlowEntry, TrailPoint, build_context
from .generator import GenerationResult, Narrative, generate_narrative
from .persistence import log_narrative_run, upsert_narrative

__all__ = [
    "NarrativeContext",
    "MetricEntry",
    "FlowEntry",
    "TrailPoint",
    "build_context",
    "GenerationResult",
    "Narrative",
    "generate_narrative",
    "log_narrative_run",
    "upsert_narrative",
]
