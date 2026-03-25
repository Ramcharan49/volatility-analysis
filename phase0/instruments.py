from __future__ import annotations

from datetime import date, datetime
from typing import Dict, List, Optional, Sequence
from phase0.models import ProbeUniverseItem
from phase0.time_utils import indian_timezone


IST = indian_timezone()


def filter_nifty_derivatives(
    rows: Sequence[Dict],
    symbol_name: str = "NIFTY",
    derivative_segment: str = "NSE_FO",
) -> List[Dict]:
    filtered = []
    for row in rows:
        segment = row.get("segment") or row.get("exchange") or ""
        if segment != derivative_segment:
            continue
        if row.get("name") != symbol_name:
            continue
        if row.get("instrument_type") not in {"FUT", "CE", "PE"}:
            continue
        filtered.append(row)
    return filtered


def build_probe_universe(
    rows: Sequence[Dict],
    spot_ltp: float,
    strike_span: int = 5,
    spot_instrument_key: str = "NSE_INDEX|Nifty 50",
    spot_exchange: str = "NSE",
    spot_tradingsymbol: str = "Nifty 50",
    provider: str = "upstox",
) -> List[ProbeUniverseItem]:
    today = datetime.now(IST).date()
    futures = sorted(
        [row for row in rows if row.get("instrument_type") == "FUT" and _expiry_or_none(row) and _expiry_or_none(row) >= today],
        key=lambda row: _expiry_or_none(row),
    )
    options = sorted(
        [row for row in rows if row.get("instrument_type") in {"CE", "PE"} and _expiry_or_none(row) and _expiry_or_none(row) >= today],
        key=lambda row: (_expiry_or_none(row), float(row.get("strike") or row.get("strike_price") or 0), row.get("instrument_type")),
    )

    selected: List[ProbeUniverseItem] = [
        ProbeUniverseItem(
            role="spot",
            exchange=spot_exchange,
            tradingsymbol=spot_tradingsymbol,
            instrument_key=spot_instrument_key,
            provider=provider,
        )
    ]

    for index, row in enumerate(futures[:2]):
        selected.append(
            ProbeUniverseItem(
                role="future_front" if index == 0 else "future_next",
                exchange=_exchange_short(row),
                tradingsymbol=row.get("tradingsymbol") or row.get("trading_symbol") or "",
                instrument_key=row.get("instrument_key"),
                instrument_token=_int_or_none(row.get("instrument_token") or row.get("exchange_token")),
                provider=provider,
                segment=row.get("segment"),
                instrument_type=row.get("instrument_type"),
                expiry=_expiry_or_none(row),
                lot_size=_int_or_none(row.get("lot_size")),
            )
        )

    option_expiries = _select_option_expiries(options, today)
    if not option_expiries:
        return selected

    strike_step = infer_strike_step([row for row in options if _expiry_or_none(row) == option_expiries[0]]) or 50.0
    atm_strike = round(spot_ltp / strike_step) * strike_step
    min_strike = atm_strike - (strike_step * strike_span)
    max_strike = atm_strike + (strike_step * strike_span)

    for expiry in option_expiries:
        scoped = [
            row
            for row in options
            if _expiry_or_none(row) == expiry and min_strike <= float(row.get("strike") or row.get("strike_price") or 0) <= max_strike
        ]
        for row in scoped:
            selected.append(
                ProbeUniverseItem(
                    role="option",
                    exchange=_exchange_short(row),
                    tradingsymbol=row.get("tradingsymbol") or row.get("trading_symbol") or "",
                    instrument_key=row.get("instrument_key"),
                    instrument_token=_int_or_none(row.get("instrument_token") or row.get("exchange_token")),
                    provider=provider,
                    segment=row.get("segment"),
                    instrument_type=row.get("instrument_type"),
                    expiry=expiry,
                    strike=float(row.get("strike") or row.get("strike_price") or 0),
                    option_type=row.get("instrument_type"),
                    lot_size=_int_or_none(row.get("lot_size")),
                )
            )

    return selected


def build_full_universe(
    rows: Sequence[Dict],
    spot_ltp: float,
    max_dte_days: int = 120,
    ws_token_limit: int = 1800,
    moneyness_bands: Sequence[tuple] = ((0.80, 1.20), (0.85, 1.15), (0.90, 1.10)),
    spot_instrument_key: str = "NSE_INDEX|Nifty 50",
    spot_exchange: str = "NSE",
    spot_tradingsymbol: str = "Nifty 50",
    provider: str = "upstox",
) -> List[ProbeUniverseItem]:
    """Build full NIFTY universe: all options with DTE <= max_dte_days.

    If the total instrument count exceeds ws_token_limit, progressively
    tighten the moneyness band around spot_ltp until it fits.
    """
    today = datetime.now(IST).date()

    futures = sorted(
        [row for row in rows if row.get("instrument_type") == "FUT"
         and _expiry_or_none(row) and _expiry_or_none(row) >= today
         and (_expiry_or_none(row) - today).days <= max_dte_days],
        key=lambda row: _expiry_or_none(row),
    )

    options = sorted(
        [row for row in rows if row.get("instrument_type") in {"CE", "PE"}
         and _expiry_or_none(row) and _expiry_or_none(row) >= today
         and (_expiry_or_none(row) - today).days <= max_dte_days],
        key=lambda row: (_expiry_or_none(row), float(row.get("strike") or row.get("strike_price") or 0), row.get("instrument_type")),
    )

    # Start: spot + futures + all options within DTE
    selected_options = options
    # 1 spot + len(futures) futures + len(selected_options)
    total = 1 + len(futures) + len(selected_options)

    if total > ws_token_limit:
        # Tighten moneyness band progressively
        for low_mult, high_mult in moneyness_bands:
            min_strike = spot_ltp * low_mult
            max_strike = spot_ltp * high_mult
            selected_options = [
                row for row in options
                if min_strike <= float(row.get("strike") or row.get("strike_price") or 0) <= max_strike
            ]
            total = 1 + len(futures) + len(selected_options)
            if total <= ws_token_limit:
                break

    # Build universe items
    selected: List[ProbeUniverseItem] = [
        ProbeUniverseItem(
            role="spot",
            exchange=spot_exchange,
            tradingsymbol=spot_tradingsymbol,
            instrument_key=spot_instrument_key,
            provider=provider,
        )
    ]

    for index, row in enumerate(futures):
        role = "future_front" if index == 0 else ("future_next" if index == 1 else "future_far")
        selected.append(
            ProbeUniverseItem(
                role=role,
                exchange=_exchange_short(row),
                tradingsymbol=row.get("tradingsymbol") or row.get("trading_symbol") or "",
                instrument_key=row.get("instrument_key"),
                instrument_token=_int_or_none(row.get("instrument_token") or row.get("exchange_token")),
                provider=provider,
                segment=row.get("segment"),
                instrument_type=row.get("instrument_type"),
                expiry=_expiry_or_none(row),
                lot_size=_int_or_none(row.get("lot_size")),
            )
        )

    for row in selected_options:
        selected.append(
            ProbeUniverseItem(
                role="option",
                exchange=_exchange_short(row),
                tradingsymbol=row.get("tradingsymbol") or row.get("trading_symbol") or "",
                instrument_key=row.get("instrument_key"),
                instrument_token=_int_or_none(row.get("instrument_token") or row.get("exchange_token")),
                provider=provider,
                segment=row.get("segment"),
                instrument_type=row.get("instrument_type"),
                expiry=_expiry_or_none(row),
                strike=float(row.get("strike") or row.get("strike_price") or 0),
                option_type=row.get("instrument_type"),
                lot_size=_int_or_none(row.get("lot_size")),
            )
        )

    return selected


def infer_strike_step(option_rows: Sequence[Dict]) -> Optional[float]:
    strikes = sorted({float(row.get("strike") or row.get("strike_price") or 0) for row in option_rows if float(row.get("strike") or row.get("strike_price") or 0) > 0})
    if len(strikes) < 2:
        return None

    diffs = [round(strikes[index + 1] - strikes[index], 4) for index in range(len(strikes) - 1)]
    positive_diffs = [diff for diff in diffs if diff > 0]
    if not positive_diffs:
        return None
    return min(positive_diffs)


def instrument_catalog_rows(rows: Sequence[Dict], as_of_date: date, provider: str = "upstox") -> List[Dict]:
    records = []
    for row in rows:
        records.append(
            {
                "as_of_date": as_of_date,
                "provider": provider,
                "provider_instrument_id": row.get("instrument_key") or "",
                "exchange": _exchange_short(row),
                "segment": row.get("segment") or "",
                "tradingsymbol": row.get("tradingsymbol") or row.get("trading_symbol") or "",
                "instrument_token": _int_or_none(row.get("instrument_token") or row.get("exchange_token")),
                "name": row.get("name"),
                "instrument_type": row.get("instrument_type"),
                "expiry": _expiry_or_none(row),
                "strike": float(row.get("strike") or row.get("strike_price") or 0) if (row.get("strike") or row.get("strike_price")) is not None else None,
                "tick_size": float(row.get("tick_size") or 0) if row.get("tick_size") is not None else None,
                "lot_size": _int_or_none(row.get("lot_size")),
                "raw_json": row.get("raw") or dict(row),
            }
        )
    return records


def phase0_universe_rows(run_id: str, items: Sequence[ProbeUniverseItem], as_of_date: date) -> List[Dict]:
    rows = []
    for item in items:
        rows.append(
            {
                "run_id": run_id,
                "as_of_date": as_of_date,
                "provider": item.provider,
                "provider_instrument_id": item.instrument_key,
                "role": item.role,
                "exchange": item.exchange,
                "tradingsymbol": item.tradingsymbol,
                "instrument_token": item.instrument_token,
                "expiry": item.expiry,
                "strike": item.strike,
                "option_type": item.option_type,
                "meta_json": {
                    "segment": item.segment,
                    "instrument_type": item.instrument_type,
                    "lot_size": item.lot_size,
                    "instrument_key": item.instrument_key,
                },
            }
        )
    return rows


def pick_historical_targets(universe: Sequence[ProbeUniverseItem], spot_reference: float) -> List[ProbeUniverseItem]:
    futures = [item for item in universe if item.role == "future_front"]
    options = [item for item in universe if item.role == "option" and item.expiry is not None and item.strike is not None]
    if not options:
        return futures

    earliest_expiry = min(item.expiry for item in options if item.expiry is not None)
    scoped = [item for item in options if item.expiry == earliest_expiry]
    ce = [item for item in scoped if item.option_type == "CE"]
    pe = [item for item in scoped if item.option_type == "PE"]

    nearest_ce = min(ce, key=lambda item: abs(float(item.strike or 0) - spot_reference)) if ce else None
    nearest_pe = min(pe, key=lambda item: abs(float(item.strike or 0) - spot_reference)) if pe else None

    targets = list(futures)
    if nearest_ce:
        targets.append(nearest_ce)
    if nearest_pe:
        targets.append(nearest_pe)
    return targets


def _select_option_expiries(options: Sequence[Dict], today: date) -> List[date]:
    expiries = sorted({_expiry_or_none(row) for row in options if _expiry_or_none(row) and _expiry_or_none(row) >= today})
    expiries = [expiry for expiry in expiries if expiry is not None]
    if not expiries:
        return []

    selected = [expiries[0]]
    later = [expiry for expiry in expiries[1:] if (expiry - today).days >= 20]
    if later:
        selected.append(later[0])
    elif len(expiries) > 1:
        selected.append(expiries[1])
    return selected


def _expiry_or_none(row: Dict) -> Optional[date]:
    value = row.get("expiry")
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        try:
            ts = value / 1000 if value > 1e10 else value
            return datetime.fromtimestamp(ts).date()
        except (ValueError, OSError):
            return None
    return None


def _exchange_short(row: Dict) -> str:
    seg = row.get("segment") or row.get("exchange") or ""
    if seg == "NSE_FO":
        return "NFO"
    if seg == "NSE_EQ":
        return "NSE"
    return seg


def _int_or_none(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
