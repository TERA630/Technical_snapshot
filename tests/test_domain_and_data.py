from __future__ import annotations

import math
import logging
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data_layer import fetch_intraday_vwap
from domain_layer import (
    StockInput,
    calc_atr,
    calc_close_position,
    calc_rsi,
    get_stock_snapshot,
    get_structured_stock_snapshot,
    grade_prev_session,
    grade_range_by_atr,
    grade_trend,
    summarize_trend,
)
from presentation_layer import render_stock_block
from stock_logging import setup_stock_logging
from stock_types import to_structured_snapshot


def build_history(rows: int = 65) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="B")
    data = []
    for i in range(rows):
        close = 100 + i
        data.append({
            "Open": close - 1,
            "High": close + 2,
            "Low": close - 2,
            "Close": close,
            "Volume": 1000 + i * 10,
        })
    return pd.DataFrame(data, index=index)


class FakeRepository:
    def __init__(self, history=None, intraday=None, valuation=None, profitability=None):
        self.history = build_history() if history is None else history
        self.intraday = intraday
        self.valuation = valuation or {
            "eps_actual": 10,
            "eps_fy0": None,
            "eps_fy1": 12,
            "per_actual": 15,
            "per_forward": 14,
        }
        self.profitability = profitability or {
            "roe_actual": 8,
            "roe_fy0": None,
            "roe_fy1": None,
            "op_margin_actual": 7,
            "op_growth_actual": 5,
            "op_income_actual": 100,
            "op_income_prev": 95,
            "op_income_fy0": None,
            "op_income_fy1": None,
            "revenue_fy0": 1000,
            "revenue_fy1": 1100,
        }
    def fetch_daily_history(self, code: str, period: str = "4mo") -> pd.DataFrame:
        return self.history

    def fetch_intraday_snapshot(self, code: str, interval: str = "5m") -> dict | None:
        return self.intraday

    def fetch_valuation_snapshot(self, code: str) -> dict:
        return self.valuation

    def fetch_profitability_snapshot(self, code: str) -> dict:
        return self.profitability


class FailingValuationRepository(FakeRepository):
    def fetch_valuation_snapshot(self, code: str) -> dict:
        raise RuntimeError("valuation unavailable")


class DomainAndDataTests(unittest.TestCase):
    def test_intraday_vwap_uses_volume_weighted_typical_price(self):
        df = pd.DataFrame(
            [
                {"Open": 100, "High": 110, "Low": 90, "Close": 105, "Volume": 10},
                {"Open": 106, "High": 120, "Low": 100, "Close": 115, "Volume": 20},
            ],
            index=pd.to_datetime(["2026-05-29 09:00", "2026-05-29 09:05"]),
        )

        with patch("data_layer.yf.download", return_value=df):
            snapshot, _ = fetch_intraday_vwap("7203")

        expected_vwap = (((110 + 90 + 105) / 3) * 10 + ((120 + 100 + 115) / 3) * 20) / 30
        self.assertAlmostEqual(snapshot["vwap"], expected_vwap)
        self.assertEqual(snapshot["latest_price"], 115)
        self.assertEqual(snapshot["volume"], 30)

    def test_atr_and_rsi_are_calculated_from_fixed_history(self):
        hist = build_history()
        atr = calc_atr(hist)
        close = pd.Series([100, 102, 101, 103, 102, 104, 103, 105, 104, 106, 105, 107, 106, 108, 107, 109])
        rsi = calc_rsi(close)

        self.assertFalse(math.isnan(atr.iloc[-1]))
        self.assertGreater(atr.iloc[-1], 0)
        self.assertFalse(pd.isna(rsi.iloc[-1]))
        self.assertGreaterEqual(rsi.iloc[-1], 0)
        self.assertLessEqual(rsi.iloc[-1], 100)

    def test_labels_and_close_position_thresholds(self):
        self.assertEqual(calc_close_position(110, 90, 102), 0.6)
        self.assertEqual(grade_range_by_atr(0.4), "浅い値幅")
        self.assertEqual(grade_range_by_atr(1.2), "大きめ")
        self.assertEqual(grade_prev_session(1.0, 0.5, 0), "押し")
        self.assertEqual(grade_trend(120, 110, 100, 95), "上昇トレンド")
        self.assertEqual(summarize_trend("上昇トレンド"), ("↑", "上昇"))
        self.assertEqual(summarize_trend("下落トレンド"), ("↓", "下落"))
        self.assertEqual(summarize_trend("もみ合い / 戻り局面"), ("→", "もみ合い"))

    def test_stock_snapshot_uses_fallbacks_and_records_missing_intraday(self):
        snapshot = get_stock_snapshot(StockInput("テスト", "0000"), FakeRepository())

        self.assertIsNone(snapshot["error"])
        self.assertEqual(snapshot["latest_bar_time"], "終値")
        self.assertEqual(snapshot["latest_price_source"], "daily_close")
        self.assertTrue(snapshot["latest_price_timestamp"].endswith("終値"))
        self.assertEqual(snapshot["day_change_price"], 1)
        self.assertEqual(snapshot["vwap_source"], "日足参考値")
        self.assertTrue(snapshot["vwap_timestamp"].endswith("終値"))
        self.assertEqual(snapshot["per_fy0"], 14)
        self.assertEqual(snapshot["summary_trend_symbol"], "↑")
        self.assertEqual(snapshot["summary_trend_label"], "上昇")
        self.assertEqual(snapshot["diagnostics"][0]["field"], "intraday")
        self.assertIn("データ欠損", snapshot["diagnostics"][0]["category"])

    def test_optional_fetch_failure_becomes_diagnostic_not_crash(self):
        with self.assertLogs("domain_layer", level="WARNING") as captured:
            snapshot = get_stock_snapshot(StockInput("テスト", "0000"), FailingValuationRepository())

        self.assertIsNone(snapshot["error"])
        self.assertIsNone(snapshot["per_actual"])
        self.assertTrue(any(item["field"] == "valuation" for item in snapshot["diagnostics"]))
        self.assertTrue(any("valuation" in message for message in captured.output))

    def test_render_uses_na_for_missing_values(self):
        snapshot = get_stock_snapshot(StockInput("テスト", "0000"), FailingValuationRepository())
        rendered = render_stock_block(snapshot, include_market=False, market_block="")

        self.assertIn("PER  N/A(実績)", rendered)
        self.assertIn("■当日テクニカル", rendered)
        self.assertIn("日足参考値", rendered)

    def test_intraday_snapshot_marks_vwap_as_intraday_source(self):
        intraday = {
            "latest_price": 150,
            "latest_bar_time": "10:05",
            "open": 140,
            "high": 155,
            "low": 139,
            "vwap": 148,
            "volume": 12345,
        }
        snapshot = get_stock_snapshot(StockInput("テスト", "0000"), FakeRepository(intraday=intraday))
        rendered = render_stock_block(snapshot, include_market=False, market_block="")

        self.assertEqual(snapshot["latest_price_source"], "intraday_5m")
        self.assertEqual(snapshot["vwap_source"], "本日5分足")
        self.assertTrue(snapshot["vwap_timestamp"].endswith("10:05"))
        self.assertIn("本日5分足", rendered)

    def test_flat_snapshot_can_be_converted_to_structured_snapshot(self):
        snapshot = get_stock_snapshot(StockInput("テスト", "0000"), FakeRepository())
        structured = to_structured_snapshot(snapshot)

        self.assertEqual(structured["identity"]["code"], "0000")
        self.assertIn("latest", structured["price"])
        self.assertIn("latest_price_timestamp", structured["price"])
        self.assertEqual(structured["price"]["day_change_price"], 1)
        self.assertEqual(structured["summary"]["trend_symbol"], "↑")
        self.assertEqual(structured["summary"]["trend_label"], "上昇")
        self.assertEqual(structured["vwap"]["source"], "日足参考値")
        self.assertIn("per_fy0", structured["valuation"])
        self.assertNotIn("dividend", structured)

    def test_structured_snapshot_api_returns_grouped_snapshot(self):
        structured = get_structured_stock_snapshot(StockInput("テスト", "0000"), FakeRepository())

        self.assertEqual(structured["identity"]["name"], "テスト")
        self.assertIn("previous_session", structured)
        self.assertIn("diagnostics", structured)

    def test_snapshot_logging_can_write_to_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_path = setup_stock_logging(tmpdir)
            try:
                snapshot = get_stock_snapshot(StockInput("テスト", "0000"), FakeRepository())

                for handler in logging.getLogger("domain_layer").handlers:
                    handler.flush()

                log_text = log_path.read_text(encoding="utf-8")
                self.assertIn("stock snapshot acquired", log_text)
                self.assertIn(snapshot["latest_price_timestamp"], log_text)
            finally:
                logger = logging.getLogger("domain_layer")
                for handler in list(logger.handlers):
                    if isinstance(handler, logging.FileHandler):
                        try:
                            same_dir = Path(handler.baseFilename).parent.samefile(tmpdir)
                        except OSError:
                            same_dir = False
                        if same_dir:
                            logger.removeHandler(handler)
                            handler.close()


if __name__ == "__main__":
    unittest.main()
