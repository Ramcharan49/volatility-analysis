from __future__ import annotations

import csv
import io
import zipfile
from datetime import date, datetime, time
from typing import Dict, List, Optional

import requests

from phase0.history_sources.base import DailyBuildResult, DailyCloseSnapshot
from phase0.time_utils import indian_timezone


IST = indian_timezone()
UDIFF_START_DATE = date(2024, 7, 8)
ARCHIVE_BASE_URL = "https://nsearchives.nseindia.com/content/fo"
REQUIRED_COLUMNS = {
    "TckrSymb",
    "FinInstrmTp",
    "FinInstrmNm",
    "XpryDt",
    "ClsPric",
    "UndrlygPric",
    "OptnTp",
    "StrkPric",
    "SttlmPric",
    "OpnIntrst",
    "TtlTradgVol",
    "NewBrdLotQty",
}


class NseUdiffDailyHistorySource:
    name = "nse_udiff"

    def __init__(self, settings, session: Optional[requests.Session] = None):
        self.settings = settings
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": "Mozilla/5.0"})

    def build_udiff_url(self, target_date: date) -> str:
        stamp = target_date.strftime("%Y%m%d")
        return "%s/BhavCopy_NSE_FO_0_0_0_%s_F_0000.csv.zip" % (ARCHIVE_BASE_URL, stamp)

    def build_close_snapshot(self, target_date: date) -> DailyBuildResult:
        if target_date < UDIFF_START_DATE:
            return DailyBuildResult(
                status="unsupported_legacy_format",
                snapshot=None,
                diagnostics={"target_date": target_date.isoformat()},
            )

        try:
            zip_bytes = self.download_udiff_zip(target_date)
        except requests.HTTPError as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            status = "no_data" if status_code == 404 else "download_error"
            return DailyBuildResult(
                status=status,
                snapshot=None,
                warnings=[str(exc)],
                diagnostics={"target_date": target_date.isoformat(), "status_code": status_code},
            )
        except Exception as exc:
            return DailyBuildResult(
                status="source_error",
                snapshot=None,
                warnings=[str(exc)],
                diagnostics={"target_date": target_date.isoformat()},
            )

        try:
            rows = self.parse_udiff_zip(zip_bytes)
        except Exception as exc:
            return DailyBuildResult(
                status="parse_error",
                snapshot=None,
                warnings=[str(exc)],
                diagnostics={"target_date": target_date.isoformat()},
            )

        return self._normalize_rows(target_date, rows)

    def download_udiff_zip(self, target_date: date) -> bytes:
        response = self.session.get(self.build_udiff_url(target_date), timeout=30)
        response.raise_for_status()
        return response.content

    def parse_udiff_zip(self, zip_bytes: bytes) -> List[Dict[str, str]]:
        archive = zipfile.ZipFile(io.BytesIO(zip_bytes))
        names = archive.namelist()
        if not names:
            raise ValueError("UDiFF zip is empty")
        with archive.open(names[0]) as handle:
            reader = csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8"))
            if not reader.fieldnames:
                raise ValueError("UDiFF CSV has no header")
            missing = REQUIRED_COLUMNS - set(reader.fieldnames)
            if missing:
                raise ValueError("UDiFF CSV missing required columns: %s" % ", ".join(sorted(missing)))
            return list(reader)

    def _normalize_rows(self, target_date: date, rows: List[Dict[str, str]]) -> DailyBuildResult:
        symbol = self.settings.phase0_symbol
        scoped = [row for row in rows if (row.get("TckrSymb") or "").strip() == symbol]
        option_rows = [row for row in scoped if (row.get("OptnTp") or "").strip() in {"CE", "PE"}]
        future_rows = [row for row in scoped if (row.get("FinInstrmTp") or "").strip() == "IDF"]

        diagnostics = {
            "raw_row_count": len(rows),
            "nifty_row_count": len(scoped),
            "option_row_count": len(option_rows),
            "future_row_count": len(future_rows),
            "used_settlement_fallback_count": 0,
            "dropped_zero_price_rows": 0,
        }

        spot_price = next((self._float_or_none(row.get("UndrlygPric")) for row in scoped if self._float_or_none(row.get("UndrlygPric"))), None)

        eligible_expiries = sorted({
            expiry for expiry in (self._parse_date(row.get("XpryDt")) for row in option_rows)
            if expiry is not None and expiry >= target_date
        })
        if not eligible_expiries:
            return DailyBuildResult(status="no_data", snapshot=None, diagnostics=diagnostics)

        selected_expiries = [
            expiry for expiry in eligible_expiries
            if (expiry - target_date).days <= self.settings.max_dte_days
        ]
        beyond = [
            expiry for expiry in eligible_expiries
            if (expiry - target_date).days > self.settings.max_dte_days
        ]
        if beyond:
            selected_expiries.append(beyond[0])

        future_price = None
        nearest_future = sorted(
            (
                row for row in future_rows
                if (expiry := self._parse_date(row.get("XpryDt"))) is not None and expiry >= target_date
            ),
            key=lambda row: self._parse_date(row.get("XpryDt")),
        )
        if nearest_future:
            future_price = self._float_or_none(nearest_future[0].get("ClsPric"))

        anchor_price = spot_price or future_price
        strike_filter = None
        if anchor_price and self.settings.strike_step and self.settings.strikes_around_atm > 0:
            step = self.settings.strike_step
            atm_strike = round(anchor_price / step) * step
            n = self.settings.strikes_around_atm
            strike_filter = {atm_strike + i * step for i in range(-n, n + 1)}

        normalized = []
        for row in option_rows:
            expiry = self._parse_date(row.get("XpryDt"))
            strike = self._float_or_none(row.get("StrkPric"))
            option_type = (row.get("OptnTp") or "").strip()
            if expiry is None or strike is None or option_type not in {"CE", "PE"}:
                continue
            if expiry not in selected_expiries:
                continue
            if strike_filter is not None and strike not in strike_filter:
                continue

            close_price = self._float_or_none(row.get("ClsPric")) or 0.0
            settle_price = self._float_or_none(row.get("SttlmPric")) or 0.0
            ltp = None
            if close_price > 0:
                ltp = close_price
            elif settle_price > 0:
                ltp = settle_price
                diagnostics["used_settlement_fallback_count"] += 1
            else:
                diagnostics["dropped_zero_price_rows"] += 1
                continue

            normalized.append({
                "expiry": expiry,
                "strike": strike,
                "option_type": option_type,
                "bid": None,
                "ask": None,
                "ltp": ltp,
                "volume": int(float(row.get("TtlTradgVol") or 0)),
                "oi": int(float(row.get("OpnIntrst") or 0)),
                "quote_quality": "ltp_fallback",
            })

        diagnostics["usable_option_row_count"] = len(normalized)
        diagnostics["selected_expiries"] = [expiry.isoformat() for expiry in selected_expiries]
        diagnostics["selected_strike_count"] = len({row["strike"] for row in normalized})

        if not normalized:
            return DailyBuildResult(status="no_data", snapshot=None, diagnostics=diagnostics)

        snapshot = DailyCloseSnapshot(
            source_name=self.name,
            target_date=target_date,
            close_ts=datetime.combine(target_date, time(15, 29), tzinfo=IST),
            option_rows=normalized,
            future_price=future_price,
            spot_price=spot_price,
            meta=diagnostics,
        )
        return DailyBuildResult(status="completed", snapshot=snapshot, diagnostics=diagnostics)

    @staticmethod
    def _parse_date(value: Optional[str]) -> Optional[date]:
        if not value:
            return None
        return date.fromisoformat(value)

    @staticmethod
    def _float_or_none(value) -> Optional[float]:
        if value in (None, ""):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
