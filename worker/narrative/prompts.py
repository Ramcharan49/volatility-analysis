"""System + user prompts for the daily regime narrative.

Kept here (not inside generator.py) so prompt iteration is a single-file change
reviewable in isolation — important when we're A/B testing providers and want
to diff prompt tweaks cleanly.
"""
from __future__ import annotations

from typing import List, Optional

from .context import MetricEntry, NarrativeContext


SYSTEM_PROMPT = """\
You write the daily market-regime narrative for the NIFTY vol analytics
dashboard. The reader is curious and intelligent but NOT a professional
options trader. They understand everyday market concepts (volatility,
risk, protection, calm vs stressed markets) but not specialist jargon.
Your job: take today's numbers and translate them into language a smart
non-specialist grasps on first read.

TONE
Declarative, grounded, calm. Like a thoughtful analyst explaining the day
to a friend over coffee. Never hedge, predict, or advise.

LANGUAGE — the most important rule
Do NOT use any of these technical terms in the output paragraph:
  percentile, Nth percentile, P[number]
  ATM IV, implied volatility, IV, IVx
  risk reversal, RR, 25-delta, 25Δ
  butterfly, BF
  term spread, term structure, front-end dominance, FED
  basis points, bps, standard deviation, stress-aligned
  regime composite, state score, stress score

Translate every technical concept into plain language. Concrete mappings:
  "at the 93rd percentile"          -> "at multi-month highs" / "near the
                                       top of its range"
  "30D ATM IV elevated"             -> "options are pricing bigger-than-
                                       usual moves over the next month"
  "Risk Reversal at stress-aligned
   99th"                            -> "protection against a drop is priced
                                       at extreme levels"
  "butterfly near zero"             -> "traders expect a narrow range"
  "backwardation / compressed term
   structure"                       -> "short-term contracts cost more
                                       than longer ones, a tell that the
                                       near-term feels fragile"
  "1-day flow percentile low"       -> "today was quiet" / "today's move
                                       was modest"
  "1-day flow percentile high"      -> "today brought a sharp shift"

STRUCTURE (one paragraph, 45-70 words, 2-3 sentences)
 1. Name the current regime (Stress / Calm / Compression / Transition)
    and what it feels like for the market in plain terms.
 2. Surface the 1-2 strongest observations in experiential language.
 3. Close with the tension or asymmetry — what is unusual today.

PROHIBITIONS
 - No first-person ("I", "we"), no second-person ("you").
 - No trading advice, predictions, or recommendations.
 - Never invent a number; only reference values shown in the context.
 - If a metric is null in the context, ignore it.

INTERNAL NOTES — use these to reason, do NOT surface in the output:
 - The user prompt tags each metric with [grid] or [composite-only].
   [grid] metrics are shown on the dashboard; ground observations in
   those. [composite-only] metrics are not shown — use them only if
   needed to explain why the regime sits where it does, and still
   translate them into plain language.
 - For 25-delta Risk Reversal, read the "stress-aligned" percentile:
   higher = more downside fear. Describe in experiential terms
   ("fear is elevated", "hedging demand is heavy"), never name the
   metric or percentile.

EXAMPLES

Bad (too technical — do NOT write like this):
  "Stress regime with 30D ATM IV at P93 and 30D RR at P99 stress-aligned,
  suggesting expanded skew and elevated downside hedging demand."

Good (plain English — aim for this voice):
  "NIFTY sits in a Stress regime. Options markets are pricing larger-than-
  usual moves over the next month, and traders are paying unusually high
  premiums to protect against a drop. Despite a quiet day, the market is
  braced for turbulence."

Bad:
  "Transition regime. Compressing term structure and rising RR percentile
  with 1D flow at the 82nd percentile."

Good:
  "The market tilts into Transition — absolute volatility is still low,
  but positioning is shifting fast. Short-dated protection is creeping
  above longer-dated, a subtle signal that the near-term could get jumpy."

Respond with JSON matching this schema exactly: {"narrative": "<paragraph>"}
"""


# ── User prompt builder ────────────────────────────────────────────────────

def build_user_prompt(ctx: NarrativeContext) -> str:
    lines: List[str] = []

    # Header
    lines.append(f"SNAPSHOT - {ctx.brief_date.isoformat()} (EOD)")
    lines.append(f"  Quadrant:     {ctx.quadrant or 'Unknown'}")
    lines.append(f"  State score:  {_fmt_score(ctx.state_score)}")
    lines.append(f"  Stress score: {_fmt_signed(ctx.stress_score)}")
    lines.append("")

    # Level percentiles (grid + composite-only, in one table)
    lines.append("Level percentiles (raw / stress-aligned):")
    for m in ctx.grid_metrics + ctx.composite_metrics:
        lines.append("  " + _fmt_level_line(m))
    lines.append("")

    # Flow percentiles (grid-visible momentum row)
    if ctx.flow_metrics:
        lines.append("Surface Momentum (percentile of today's 1-day change vs history of 1-day changes):")
        for f in ctx.flow_metrics:
            pct = _fmt_pct(f.raw_percentile)
            lines.append(f"  {f.key:<22} {pct:>8}   [grid]")
        lines.append("")

    # Trail
    if ctx.trail:
        lines.append(f"{len(ctx.trail)}-day regime trail:")
        for i, t in enumerate(ctx.trail):
            marker = "    <- today" if i == len(ctx.trail) - 1 else ""
            lines.append(
                f"  {t.day.strftime('%b %d')}  "
                f"state {_fmt_score(t.state_score):>6}  "
                f"stress {_fmt_signed(t.stress_score):>7}  "
                f"{t.quadrant or '-'}"
                f"{marker}"
            )

    return "\n".join(lines)


def _fmt_level_line(m: MetricEntry) -> str:
    raw = _fmt_pct(m.raw_percentile)
    aligned = _fmt_pct(m.stress_aligned_percentile)
    tag = "[grid]" if m.surface == "grid" else "[composite-only]"
    suffix = ""
    if m.key == "rr25_30d":
        suffix = "  -- inverted; raw low = extreme fear"
    return f"{m.key:<22} {raw:>8} / {aligned:<8}  {tag}{suffix}"


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"P{int(round(value))}"


def _fmt_score(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"{value:.1f}"


def _fmt_signed(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"{value:+.1f}"
