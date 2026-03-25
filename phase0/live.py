from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Sequence, Tuple

from phase0.artifacts import json_default
from phase0.providers.upstox.quotes import normalise_snapshot_payload
from phase0.models import ProbeUniverseItem
from phase0.quant import compute_expiry_nodes
from phase0.time_utils import indian_timezone


IST = indian_timezone()


@dataclass
class SealedMinuteResult:
    minute_ts: datetime
    underlying_rows: List[Dict]
    option_rows: List[Dict]
    expiry_node_rows: List[Dict]


class MinuteAccumulator:
    def __init__(self, universe: Sequence[ProbeUniverseItem], rate: float, allow_ltp_fallback: bool = False):
        self.universe = list(universe)
        self.items_by_key = {
            item.instrument_key: item for item in self.universe if item.instrument_key is not None
        }
        self.rate = rate
        self.allow_ltp_fallback = allow_ltp_fallback
        self.minute_buckets: Dict[datetime, Dict[str, Dict]] = {}
        self.spot_key = next(
            (item.instrument_key for item in self.universe if item.role == "spot" and item.instrument_key is not None),
            None,
        )
        self.future_front_key = next(
            (
                item.instrument_key
                for item in self.universe
                if item.role == "future_front" and item.instrument_key is not None
            ),
            None,
        )

    def _prune_old_buckets(self, now: datetime, max_age_minutes: int = 5) -> None:
        """Drop minute buckets older than max_age_minutes to bound memory."""
        cutoff = ensure_ist(now) - timedelta(minutes=max_age_minutes)
        stale = [ts for ts in self.minute_buckets if ts < cutoff]
        for ts in stale:
            del self.minute_buckets[ts]

    def feed_ticks(self, ticks: Sequence[Dict], received_at: datetime) -> None:
        received_at_ist = ensure_ist(received_at)
        self._prune_old_buckets(received_at_ist)
        for tick in ticks:
            key = tick.get("instrument_key")
            if key is None:
                continue
            if key not in self.items_by_key:
                continue

            event_ts = choose_tick_timestamp(tick, received_at_ist)
            minute_ts = floor_minute(event_ts)
            bucket = self.minute_buckets.setdefault(minute_ts, {})
            current = bucket.get(key)
            if current and (event_ts, received_at_ist) < (current["event_ts"], current["received_at"]):
                continue
            bucket[key] = {
                "payload": dict(tick),
                "event_ts": event_ts,
                "received_at": received_at_ist,
            }

    def seal_ready(self, now: datetime, seal_lag_seconds: int) -> List[SealedMinuteResult]:
        ready_minutes = [
            minute_ts
            for minute_ts in self.minute_buckets
            if minute_ts + timedelta(minutes=1, seconds=seal_lag_seconds) <= ensure_ist(now)
        ]
        results = []
        for minute_ts in sorted(ready_minutes):
            bucket = self.minute_buckets.pop(minute_ts)
            results.append(self._seal_minute(minute_ts, bucket))
        return results

    def _seal_minute(self, minute_ts: datetime, bucket: Dict[str, Dict]) -> SealedMinuteResult:
        underlying_rows: List[Dict] = []
        option_rows: List[Dict] = []

        for key, record in bucket.items():
            item = self.items_by_key[key]
            row_type, row = normalise_snapshot_payload(item, record["payload"], minute_ts)
            if row_type == "underlying":
                underlying_rows.append(row)
            else:
                option_rows.append(row)

        future_price = _pick_underlying_price(underlying_rows, self.future_front_key)
        spot_price = _pick_underlying_price(underlying_rows, self.spot_key)
        expiry_nodes = compute_expiry_nodes(
            option_rows=option_rows,
            snapshot_ts=minute_ts,
            future_price=future_price,
            spot_price=spot_price,
            rate=self.rate,
            allow_ltp_fallback=self.allow_ltp_fallback,
        )

        return SealedMinuteResult(
            minute_ts=minute_ts,
            underlying_rows=underlying_rows,
            option_rows=option_rows,
            expiry_node_rows=[asdict(node) for node in expiry_nodes],
        )


def choose_tick_timestamp(tick: Dict, received_at: datetime) -> datetime:
    for key in ("exchange_timestamp", "last_trade_time"):
        value = tick.get(key)
        if value:
            return ensure_ist(value)
    return ensure_ist(received_at)


def floor_minute(value: datetime) -> datetime:
    return ensure_ist(value).replace(second=0, microsecond=0)


def ensure_ist(value) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        return value.replace(tzinfo=IST)
    return value.astimezone(IST)


def universe_items_from_rows(rows: Sequence[Dict]) -> List[ProbeUniverseItem]:
    items = []
    for row in rows:
        meta = row.get("meta_json") or {}
        items.append(
            ProbeUniverseItem(
                role=row["role"],
                exchange=row["exchange"],
                tradingsymbol=row["tradingsymbol"],
                instrument_key=row.get("provider_instrument_id") or meta.get("instrument_key"),
                instrument_token=row.get("instrument_token"),
                provider=row.get("provider", "upstox"),
                segment=meta.get("segment"),
                instrument_type=meta.get("instrument_type"),
                expiry=_parse_date_or_none(row.get("expiry")),
                strike=float(row["strike"]) if row.get("strike") is not None else None,
                option_type=row.get("option_type"),
                lot_size=int(meta["lot_size"]) if meta.get("lot_size") is not None else None,
            )
        )
    return items


def compare_row_sets(
    expected_rows: Sequence[Dict],
    actual_rows: Sequence[Dict],
    key_fields: Sequence[str],
    tolerance: float = 1e-9,
) -> Dict:
    expected_map = {tuple(_normalise_key(row.get(field)) for field in key_fields): serialise_for_compare(row) for row in expected_rows}
    actual_map = {tuple(_normalise_key(row.get(field)) for field in key_fields): serialise_for_compare(row) for row in actual_rows}

    missing_keys = sorted(key for key in expected_map if key not in actual_map)
    extra_keys = sorted(key for key in actual_map if key not in expected_map)
    mismatches = []
    for key in sorted(key for key in expected_map if key in actual_map):
        row_mismatches = []
        _compare_values(expected_map[key], actual_map[key], tolerance, "", row_mismatches)
        if row_mismatches:
            mismatches.append({"key": key, "differences": row_mismatches})

    return {
        "expected_count": len(expected_rows),
        "actual_count": len(actual_rows),
        "missing_keys": missing_keys,
        "extra_keys": extra_keys,
        "mismatches": mismatches,
        "ok": not missing_keys and not extra_keys and not mismatches,
    }


def serialise_for_compare(payload: Dict) -> Dict:
    return json.loads(json.dumps(payload, default=json_default))


def _compare_values(expected, actual, tolerance: float, path: str, mismatches: List[Dict]) -> None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        keys = sorted(set(expected) | set(actual))
        for key in keys:
            next_path = key if not path else "%s.%s" % (path, key)
            if key not in expected or key not in actual:
                mismatches.append({"path": next_path, "expected": expected.get(key), "actual": actual.get(key)})
                continue
            _compare_values(expected[key], actual[key], tolerance, next_path, mismatches)
        return

    if isinstance(expected, list) and isinstance(actual, list):
        if len(expected) != len(actual):
            mismatches.append({"path": path, "expected": expected, "actual": actual})
            return
        for index, (left, right) in enumerate(zip(expected, actual)):
            next_path = "%s[%s]" % (path, index)
            _compare_values(left, right, tolerance, next_path, mismatches)
        return

    if _both_numeric(expected, actual):
        if abs(float(expected) - float(actual)) > tolerance:
            mismatches.append({"path": path, "expected": expected, "actual": actual})
        return

    if expected != actual:
        mismatches.append({"path": path, "expected": expected, "actual": actual})


def _both_numeric(left, right) -> bool:
    return isinstance(left, (int, float)) and isinstance(right, (int, float)) and not isinstance(left, bool) and not isinstance(right, bool)


def _normalise_key(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _pick_underlying_price(rows: Sequence[Dict], preferred_key: Optional[str]) -> Optional[float]:
    for row in rows:
        if preferred_key is not None and row.get("instrument_key") == preferred_key:
            return float(row["last_price"])
    for row in rows:
        if row.get("last_price") is not None:
            return float(row["last_price"])
    return None


def _parse_date_or_none(value) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))
