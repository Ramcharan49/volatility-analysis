from __future__ import annotations

from phase0.history_sources.base import DailyBuildResult, DailyCloseSnapshot, DailyHistorySource


def get_daily_history_source(settings, source_name=None) -> DailyHistorySource:
    resolved = source_name or settings.daily_history_source
    if resolved == "nse_udiff":
        from phase0.history_sources.nse_udiff import NseUdiffDailyHistorySource

        return NseUdiffDailyHistorySource(settings)
    if resolved == "upstox":
        from phase0.history_sources.upstox_daily import UpstoxDailyHistorySource

        return UpstoxDailyHistorySource(settings)
    raise ValueError("Unknown daily history source: %s" % resolved)


__all__ = [
    "DailyBuildResult",
    "DailyCloseSnapshot",
    "DailyHistorySource",
    "get_daily_history_source",
]
