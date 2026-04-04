from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import requests

from phase0.config import Settings


def _make_settings(**overrides) -> Settings:
    tmpdir = Path(tempfile.mkdtemp())
    defaults = dict(
        provider="upstox",
        upstox_api_key="test",
        upstox_api_secret="test",
        upstox_redirect_url="http://localhost",
        session_state_path=tmpdir / "session.json",
        artifacts_dir=tmpdir / "artifacts",
        risk_free_rate=0.06,
        phase0_symbol="NIFTY",
        spot_instrument_key="NSE_INDEX|Nifty 50",
        derivative_segment="NSE_FO",
        store_raw_json_in_db=False,
        expired_history_months=6,
        supabase_db_url=None,
        strike_step=100.0,
        strikes_around_atm=3,
    )
    defaults.update(overrides)
    return Settings(**defaults)


class TestNseUdiffDailyHistorySource(unittest.TestCase):
    def test_overrides_default_requests_user_agent(self):
        from phase0.history_sources.nse_udiff import NseUdiffDailyHistorySource

        session = requests.Session()
        source = NseUdiffDailyHistorySource(_make_settings(), session=session)

        self.assertEqual(source.session.headers.get("User-Agent"), "Mozilla/5.0")

    def test_build_udiff_url_for_supported_date(self):
        from phase0.history_sources.nse_udiff import NseUdiffDailyHistorySource

        source = NseUdiffDailyHistorySource(_make_settings())
        url = source.build_udiff_url(date(2026, 4, 2))
        self.assertEqual(
            url,
            "https://nsearchives.nseindia.com/content/fo/"
            "BhavCopy_NSE_FO_0_0_0_20260402_F_0000.csv.zip",
        )

    def test_pre_udiff_date_returns_unsupported_status(self):
        from phase0.history_sources.nse_udiff import NseUdiffDailyHistorySource

        source = NseUdiffDailyHistorySource(_make_settings())
        result = source.build_close_snapshot(date(2024, 7, 5))
        self.assertEqual(result.status, "unsupported_legacy_format")
        self.assertIsNone(result.snapshot)

    def test_build_close_snapshot_uses_settlement_fallback(self):
        from phase0.history_sources.nse_udiff import NseUdiffDailyHistorySource

        rows = [
            {
                "TckrSymb": "NIFTY",
                "FinInstrmTp": "IDF",
                "FinInstrmNm": "NIFTY26APRFUT",
                "XpryDt": "2026-04-28",
                "ClsPric": "22766.60",
                "UndrlygPric": "22713.10",
                "OptnTp": "",
                "StrkPric": "",
                "SttlmPric": "22766.60",
                "OpnIntrst": "21429395",
                "TtlTradgVol": "134955",
                "NewBrdLotQty": "75",
            },
            {
                "TckrSymb": "NIFTY",
                "FinInstrmTp": "IDO",
                "FinInstrmNm": "NIFTY26APR22700CE",
                "XpryDt": "2026-04-28",
                "ClsPric": "0.00",
                "UndrlygPric": "22713.10",
                "OptnTp": "CE",
                "StrkPric": "22700.00",
                "SttlmPric": "120.25",
                "OpnIntrst": "100",
                "TtlTradgVol": "20",
                "NewBrdLotQty": "75",
            },
            {
                "TckrSymb": "NIFTY",
                "FinInstrmTp": "IDO",
                "FinInstrmNm": "NIFTY26APR22700PE",
                "XpryDt": "2026-04-28",
                "ClsPric": "115.50",
                "UndrlygPric": "22713.10",
                "OptnTp": "PE",
                "StrkPric": "22700.00",
                "SttlmPric": "115.50",
                "OpnIntrst": "120",
                "TtlTradgVol": "25",
                "NewBrdLotQty": "75",
            },
            {
                "TckrSymb": "NIFTY",
                "FinInstrmTp": "IDO",
                "FinInstrmNm": "NIFTY26APR23000CE",
                "XpryDt": "2026-04-28",
                "ClsPric": "80.00",
                "UndrlygPric": "22713.10",
                "OptnTp": "CE",
                "StrkPric": "23000.00",
                "SttlmPric": "80.00",
                "OpnIntrst": "90",
                "TtlTradgVol": "18",
                "NewBrdLotQty": "75",
            },
            {
                "TckrSymb": "NIFTY",
                "FinInstrmTp": "IDO",
                "FinInstrmNm": "NIFTY26APR23000PE",
                "XpryDt": "2026-04-28",
                "ClsPric": "175.00",
                "UndrlygPric": "22713.10",
                "OptnTp": "PE",
                "StrkPric": "23000.00",
                "SttlmPric": "175.00",
                "OpnIntrst": "95",
                "TtlTradgVol": "22",
                "NewBrdLotQty": "75",
            },
            {
                "TckrSymb": "NIFTY",
                "FinInstrmTp": "IDO",
                "FinInstrmNm": "NIFTY26APR24000CE",
                "XpryDt": "2026-04-28",
                "ClsPric": "10.00",
                "UndrlygPric": "22713.10",
                "OptnTp": "CE",
                "StrkPric": "24000.00",
                "SttlmPric": "10.00",
                "OpnIntrst": "10",
                "TtlTradgVol": "1",
                "NewBrdLotQty": "75",
            },
        ]

        source = NseUdiffDailyHistorySource(_make_settings())
        with patch.object(source, "download_udiff_zip", return_value=b"zip"), patch.object(
            source, "parse_udiff_zip", return_value=rows
        ):
            result = source.build_close_snapshot(date(2026, 4, 2))

        self.assertEqual(result.status, "completed")
        self.assertIsNotNone(result.snapshot)
        self.assertEqual(len(result.snapshot.option_rows), 4)
        self.assertEqual(result.snapshot.option_rows[0]["ltp"], 120.25)
        self.assertEqual(result.snapshot.future_price, 22766.60)
        self.assertEqual(result.snapshot.spot_price, 22713.10)
        self.assertEqual(result.diagnostics["used_settlement_fallback_count"], 1)

    def test_returns_no_data_when_all_option_prices_are_zero(self):
        from phase0.history_sources.nse_udiff import NseUdiffDailyHistorySource

        rows = [
            {
                "TckrSymb": "NIFTY",
                "FinInstrmTp": "IDO",
                "FinInstrmNm": "NIFTY26APR22700CE",
                "XpryDt": "2026-04-28",
                "ClsPric": "0.00",
                "UndrlygPric": "22713.10",
                "OptnTp": "CE",
                "StrkPric": "22700.00",
                "SttlmPric": "0.00",
                "OpnIntrst": "100",
                "TtlTradgVol": "20",
                "NewBrdLotQty": "75",
            }
        ]

        source = NseUdiffDailyHistorySource(_make_settings())
        with patch.object(source, "download_udiff_zip", return_value=b"zip"), patch.object(
            source, "parse_udiff_zip", return_value=rows
        ):
            result = source.build_close_snapshot(date(2026, 4, 2))

        self.assertEqual(result.status, "no_data")
        self.assertIsNone(result.snapshot)

    def test_404_archive_is_treated_as_no_data(self):
        from phase0.history_sources.nse_udiff import NseUdiffDailyHistorySource

        response = SimpleNamespace(status_code=404)
        error = requests.HTTPError("404 not found")
        error.response = response

        source = NseUdiffDailyHistorySource(_make_settings())
        with patch.object(source, "download_udiff_zip", side_effect=error):
            result = source.build_close_snapshot(date(2026, 4, 2))

        self.assertEqual(result.status, "no_data")
        self.assertIsNone(result.snapshot)


if __name__ == "__main__":
    unittest.main()
