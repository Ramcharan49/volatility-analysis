from __future__ import annotations

from phase0.providers.base import MarketDataProvider


def get_provider(settings) -> MarketDataProvider:
    if settings.provider == "upstox":
        from phase0.providers.upstox import UpstoxProvider
        return UpstoxProvider(settings)
    raise ValueError("Unknown provider: %s" % settings.provider)
