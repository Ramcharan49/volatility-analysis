from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Protocol


@dataclass(frozen=True)
class DailyCloseSnapshot:
    source_name: str
    target_date: date
    close_ts: datetime
    option_rows: List[Dict]
    future_price: Optional[float]
    spot_price: Optional[float]
    meta: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DailyBuildResult:
    status: str
    snapshot: Optional[DailyCloseSnapshot]
    warnings: List[str] = field(default_factory=list)
    diagnostics: Dict[str, Any] = field(default_factory=dict)


class DailyHistorySource(Protocol):
    name: str

    def build_close_snapshot(self, target_date: date) -> DailyBuildResult: ...
