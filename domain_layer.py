from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import math
from typing import Protocol

import pandas as pd

from data_layer import fetch_history, fetch_intraday_vwap, fetch_profitability_snapshot, fetch_valuation_snapshot, safe_float
from stock_constants import (
    ATR_PERIOD,
    CANDLE_LABELS,
    CLOSE_POSITION_LABELS,
    CLOSE_POSITION_THRESHOLDS,
    DIAGNOSTIC_CATEGORIES,
    ERROR_MESSAGES,
    NA_TEXT,
    PREV_SESSION_THRESHOLDS,
    PRICE_SOURCE_LABELS,
    RANGE_ATR_LABELS,
    RANGE_ATR_THRESHOLDS,
    RANGE_ZONE_LABELS,
    RANGE_ZONE_THRESHOLDS,
    RSI_PERIOD,
    SESSION_LABELS,
    TREND_LABELS,
    UNIT_LABELS,
    VWAP_SOURCE_LABELS,
    WICK_SHAPE_LABELS,
    WICK_SHAPE_THRESHOLDS,
)
from stock_types import StructuredStockSnapshot, to_structured_snapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StockInput:
    name: str
    code: str


class StockDataRepository(Protocol):
    def fetch_daily_history(self, code: str, period: str = "4mo") -> pd.DataFrame: ...
    def fetch_intraday_snapshot(self, code: str, interval: str = "5m") -> dict | None: ...
    def fetch_valuation_snapshot(self, code: str) -> dict: ...
    def fetch_profitability_snapshot(self, code: str) -> dict: ...


class YFinanceStockDataRepository:
    def fetch_daily_history(self, code: str, period: str = "4mo") -> pd.DataFrame:
        return fetch_history(f"{code}.T", period=period)

    def fetch_intraday_snapshot(self, code: str, interval: str = "5m") -> dict | None:
        snapshot, _ = fetch_intraday_vwap(code, interval=interval)
        return snapshot

    def fetch_valuation_snapshot(self, code: str) -> dict:
        return fetch_valuation_snapshot(code)

    def fetch_profitability_snapshot(self, code: str) -> dict:
        return fetch_profitability_snapshot(code)


def add_diagnostic(diagnostics: list[dict], category_key: str, field: str, message: str):
    diagnostic = {
        "category": DIAGNOSTIC_CATEGORIES[category_key],
        "field": field,
        "message": message,
    }
    diagnostics.append(diagnostic)
    logger.warning(
        "stock snapshot diagnostic: category=%s field=%s message=%s",
        diagnostic["category"],
        diagnostic["field"],
        diagnostic["message"],
    )


def fetch_optional_snapshot(diagnostics: list[dict], field: str, fetch_func, default_value):
    try:
        value = fetch_func()
    except Exception as exc:
        add_diagnostic(diagnostics, "external_api_failure", field, str(exc))
        return default_value
    if value is None:
        add_diagnostic(diagnostics, "data_missing", field, "取得結果がありません")
        return default_value
    return value


def build_latest_price_timestamp(date_text: str, latest_bar_time: str) -> str:
    return f"{date_text} {latest_bar_time}"


def log_snapshot_result(snapshot: dict):
    logger.info(
        "stock snapshot acquired: name=%s code=%s acquired_at=%s latest=%s latest_price_source=%s latest_price_timestamp=%s vwap_source=%s vwap_timestamp=%s error=%s diagnostics_count=%s",
        snapshot.get("name"),
        snapshot.get("code"),
        snapshot.get("acquired_at"),
        snapshot.get("latest"),
        snapshot.get("latest_price_source"),
        snapshot.get("latest_price_timestamp"),
        snapshot.get("vwap_source"),
        snapshot.get("vwap_timestamp"),
        snapshot.get("error"),
        len(snapshot.get("diagnostics") or []),
    )


def calc_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    prev_close = df["Close"].shift(1)
    true_range = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def grade_range_by_atr(ratio):
    if ratio is None or (isinstance(ratio, float) and (math.isnan(ratio) or math.isinf(ratio))):
        return NA_TEXT
    if ratio < RANGE_ATR_THRESHOLDS["narrow"]:
        return RANGE_ATR_LABELS["narrow"]
    if ratio < RANGE_ATR_THRESHOLDS["normal"]:
        return RANGE_ATR_LABELS["normal"]
    if ratio < RANGE_ATR_THRESHOLDS["wide"]:
        return RANGE_ATR_LABELS["wide"]
    return RANGE_ATR_LABELS["expanded"]


def grade_close_position(position):
    if position is None or (isinstance(position, float) and (math.isnan(position) or math.isinf(position))):
        return NA_TEXT
    if position >= CLOSE_POSITION_THRESHOLDS["high"]:
        return CLOSE_POSITION_LABELS["high"]
    if position >= CLOSE_POSITION_THRESHOLDS["middle"]:
        return CLOSE_POSITION_LABELS["middle"]
    return CLOSE_POSITION_LABELS["low"]


def grade_range_zone(position):
    if position is None or (isinstance(position, float) and (math.isnan(position) or math.isinf(position))):
        return NA_TEXT
    if position >= RANGE_ZONE_THRESHOLDS["high"]:
        return RANGE_ZONE_LABELS["high"]
    if position >= RANGE_ZONE_THRESHOLDS["middle"]:
        return RANGE_ZONE_LABELS["middle"]
    return RANGE_ZONE_LABELS["low"]


def calc_close_position(high_price, low_price, close_price):
    if high_price is None or low_price is None or close_price is None:
        return None
    price_range = high_price - low_price
    if price_range <= 0:
        return None
    return (close_price - low_price) / price_range


def grade_prev_session(prev_range_atr, close_position, prev_vol_ratio):
    if prev_range_atr is None or close_position is None:
        return SESSION_LABELS["unavailable"]
    vol_ratio = 0.0 if prev_vol_ratio is None else prev_vol_ratio
    if (
        prev_range_atr >= PREV_SESSION_THRESHOLDS["collapse_range_atr"]
        and close_position <= PREV_SESSION_THRESHOLDS["collapse_close_position"]
        and vol_ratio >= PREV_SESSION_THRESHOLDS["collapse_volume_ratio"]
    ):
        return SESSION_LABELS["collapse"]
    if (
        prev_range_atr >= PREV_SESSION_THRESHOLDS["large_collapse_range_atr"]
        and close_position <= PREV_SESSION_THRESHOLDS["large_collapse_close_position"]
    ):
        return SESSION_LABELS["collapse"]
    if (
        PREV_SESSION_THRESHOLDS["pullback_range_atr_min"]
        <= prev_range_atr
        <= PREV_SESSION_THRESHOLDS["pullback_range_atr_max"]
        and close_position >= PREV_SESSION_THRESHOLDS["pullback_close_position"]
        and vol_ratio <= PREV_SESSION_THRESHOLDS["pullback_volume_ratio"]
    ):
        return SESSION_LABELS["pullback"]
    return SESSION_LABELS["neutral"]


def grade_prev_evaluation(prev_candle, prev_wick_shape, prev_range_atr, close_position, prev_vol_ratio):
    if prev_range_atr is None or close_position is None:
        return SESSION_LABELS["unavailable"]
    vol_ratio = 0.0 if prev_vol_ratio is None else prev_vol_ratio
    if (
        prev_range_atr >= PREV_SESSION_THRESHOLDS["collapse_range_atr"]
        and close_position <= PREV_SESSION_THRESHOLDS["collapse_close_position"]
        and vol_ratio >= PREV_SESSION_THRESHOLDS["collapse_volume_ratio"]
    ) or (
        prev_range_atr >= PREV_SESSION_THRESHOLDS["large_collapse_range_atr"]
        and close_position <= PREV_SESSION_THRESHOLDS["large_collapse_close_position"]
    ):
        return SESSION_LABELS["collapse"]
    if (
        prev_candle == CANDLE_LABELS["bullish"]
        and close_position >= PREV_SESSION_THRESHOLDS["strong_rise_close_position"]
        and prev_range_atr <= PREV_SESSION_THRESHOLDS["strong_rise_range_atr"]
        and prev_wick_shape != WICK_SHAPE_LABELS["long_upper_wick"]
    ):
        if vol_ratio >= PREV_SESSION_THRESHOLDS["strong_rise_volume_ratio"]:
            return SESSION_LABELS["strong_rise"]
    if (
        prev_candle == CANDLE_LABELS["bullish"]
        and (
            close_position < PREV_SESSION_THRESHOLDS["weak_rise_close_position"]
            or prev_wick_shape == WICK_SHAPE_LABELS["long_upper_wick"]
        )
    ):
        return SESSION_LABELS["weak_rise"]
    if (
        prev_candle in (CANDLE_LABELS["bearish"], CANDLE_LABELS["doji"])
        and PREV_SESSION_THRESHOLDS["pullback_range_atr_min"]
        <= prev_range_atr
        <= PREV_SESSION_THRESHOLDS["pullback_range_atr_max"]
        and close_position >= PREV_SESSION_THRESHOLDS["pullback_close_position"]
        and vol_ratio <= PREV_SESSION_THRESHOLDS["pullback_volume_ratio"]
    ):
        return SESSION_LABELS["pullback"]
    if (
        prev_wick_shape == WICK_SHAPE_LABELS["long_lower_wick"]
        and close_position >= PREV_SESSION_THRESHOLDS["pullback_close_position"]
        and prev_range_atr <= PREV_SESSION_THRESHOLDS["long_lower_wick_range_atr"]
    ):
        return SESSION_LABELS["pullback"]
    return SESSION_LABELS["neutral"]


def calc_distance(value, base):
    if value is None or base in (None, 0):
        return None
    return value - base


def calc_distance_pct(value, base):
    if value is None or base in (None, 0):
        return None
    return (value / base - 1.0) * 100


def calc_rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def grade_candle(open_price, close_price):
    if open_price is None or close_price is None:
        return NA_TEXT
    if close_price > open_price:
        return CANDLE_LABELS["bullish"]
    if close_price < open_price:
        return CANDLE_LABELS["bearish"]
    return CANDLE_LABELS["doji"]


def grade_wick_shape(open_price, high_price, low_price, close_price):
    values = [open_price, high_price, low_price, close_price]
    if any(v is None for v in values):
        return NA_TEXT
    day_range = high_price - low_price
    if day_range <= 0:
        return WICK_SHAPE_LABELS["small_move"]
    body = abs(close_price - open_price)
    upper_wick = high_price - max(open_price, close_price)
    lower_wick = min(open_price, close_price) - low_price
    body_ratio = body / day_range
    upper_ratio = upper_wick / day_range
    lower_ratio = lower_wick / day_range
    if body_ratio >= WICK_SHAPE_THRESHOLDS["large_body_ratio"]:
        return WICK_SHAPE_LABELS["large_body"]
    if (
        lower_ratio >= WICK_SHAPE_THRESHOLDS["long_wick_ratio"]
        and lower_wick >= body * WICK_SHAPE_THRESHOLDS["long_wick_body_multiple"]
    ):
        return WICK_SHAPE_LABELS["long_lower_wick"]
    if (
        upper_ratio >= WICK_SHAPE_THRESHOLDS["long_wick_ratio"]
        and upper_wick >= body * WICK_SHAPE_THRESHOLDS["long_wick_body_multiple"]
    ):
        return WICK_SHAPE_LABELS["long_upper_wick"]
    if body_ratio <= WICK_SHAPE_THRESHOLDS["small_body_ratio"]:
        return WICK_SHAPE_LABELS["small_doji_like"]
    return WICK_SHAPE_LABELS["normal"]


def grade_trend(latest, ma5, ma25, ma25_prev5):
    if latest is None or ma5 is None or ma25 is None:
        return NA_TEXT
    ma25_slope_up = ma25_prev5 is not None and ma25 > ma25_prev5
    if latest > ma5 > ma25 and ma25_slope_up:
        return TREND_LABELS["up"]
    if latest < ma5 < ma25:
        return TREND_LABELS["down"]
    return TREND_LABELS["mixed"]




def calc_per(price, eps):
    if price in (None, 0) or eps is None or eps <= 0:
        return None
    return price / eps



def get_stock_snapshot(stock_input: StockInput, repository: StockDataRepository | None = None):
    repo = repository or YFinanceStockDataRepository()
    diagnostics: list[dict] = []
    try:
        hist = repo.fetch_daily_history(stock_input.code, period="4mo")
    except Exception as exc:
        add_diagnostic(diagnostics, "external_api_failure", "daily_history", str(exc))
        snapshot = {
            "name": stock_input.name,
            "code": stock_input.code,
            "acquired_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": ERROR_MESSAGES["insufficient_price_data"],
            "diagnostics": diagnostics,
        }
        log_snapshot_result(snapshot)
        return snapshot
    if hist.empty or len(hist) < 30:
        add_diagnostic(diagnostics, "data_missing", "daily_history", "日足が30件未満です")
        snapshot = {
            "name": stock_input.name,
            "code": stock_input.code,
            "acquired_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": ERROR_MESSAGES["insufficient_price_data"],
            "diagnostics": diagnostics,
        }
        log_snapshot_result(snapshot)
        return snapshot

    required_cols = {"Open", "High", "Low", "Close", "Volume"}
    missing_cols = sorted(required_cols - set(hist.columns))
    if missing_cols:
        add_diagnostic(diagnostics, "column_missing", "daily_history", f"不足列: {', '.join(missing_cols)}")
        snapshot = {
            "name": stock_input.name,
            "code": stock_input.code,
            "acquired_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": ERROR_MESSAGES["insufficient_price_data"],
            "diagnostics": diagnostics,
        }
        log_snapshot_result(snapshot)
        return snapshot

    hist = hist[["Open", "High", "Low", "Close", "Volume"]].dropna().copy()
    if len(hist) < 30:
        add_diagnostic(diagnostics, "data_missing", "daily_history", "欠損除去後の日足が30件未満です")
        snapshot = {
            "name": stock_input.name,
            "code": stock_input.code,
            "acquired_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "error": ERROR_MESSAGES["insufficient_price_data"],
            "diagnostics": diagnostics,
        }
        log_snapshot_result(snapshot)
        return snapshot
    hist["MA5"] = hist["Close"].rolling(5).mean()
    hist["MA25"] = hist["Close"].rolling(25).mean()
    hist["RSI14"] = calc_rsi(hist["Close"], RSI_PERIOD)
    hist["ATR14"] = calc_atr(hist, ATR_PERIOD)
    hist["VolAvg20"] = hist["Volume"].rolling(20).mean()

    last = hist.iloc[-1]
    prev = hist.iloc[-2]
    ma25_prev5 = safe_float(hist["MA25"].iloc[-6]) if len(hist) >= 30 else None

    latest = safe_float(last["Close"])
    ma5 = safe_float(last["MA5"])
    ma25 = safe_float(last["MA25"])
    vol = safe_float(last["Volume"])
    atr14 = safe_float(last["ATR14"])

    intraday = fetch_optional_snapshot(
        diagnostics,
        "intraday",
        lambda: repo.fetch_intraday_snapshot(stock_input.code, interval="5m"),
        None,
    )
    valuation = fetch_optional_snapshot(
        diagnostics,
        "valuation",
        lambda: repo.fetch_valuation_snapshot(stock_input.code),
        {},
    )
    profitability = fetch_optional_snapshot(
        diagnostics,
        "profitability",
        lambda: repo.fetch_profitability_snapshot(stock_input.code),
        {},
    )
    latest_bar_time = UNIT_LABELS["closing_price"]
    latest_price_source = PRICE_SOURCE_LABELS["daily_close"]
    vwap_source = VWAP_SOURCE_LABELS["daily_typical"]
    open_price = safe_float(last["Open"])
    high_price = safe_float(last["High"])
    low_price = safe_float(last["Low"])
    volume_now = vol

    if intraday is not None:
        latest = intraday.get("latest_price") if intraday.get("latest_price") is not None else latest
        latest_bar_time = intraday.get("latest_bar_time") or latest_bar_time
        latest_price_source = PRICE_SOURCE_LABELS["intraday"]
        open_price = intraday.get("open") if intraday.get("open") is not None else open_price
        high_price = intraday.get("high") if intraday.get("high") is not None else high_price
        low_price = intraday.get("low") if intraday.get("low") is not None else low_price
        volume_now = intraday.get("volume") if intraday.get("volume") is not None else volume_now
        vwap = intraday.get("vwap")
        vwap_source = VWAP_SOURCE_LABELS["intraday"]
    else:
        typical = (last["High"] + last["Low"] + last["Close"]) / 3.0
        vwap = safe_float(typical)

    prev_open, prev_high, prev_low, prev_close = map(safe_float, [prev["Open"], prev["High"], prev["Low"], prev["Close"]])
    prev_change_pct = None
    if len(hist) >= 3:
        prev_prev_close = safe_float(hist["Close"].iloc[-3])
        if prev_close not in (None, 0) and prev_prev_close not in (None, 0):
            prev_change_pct = (prev_close / prev_prev_close - 1.0) * 100

    dev5 = None if latest in (None, 0) or ma5 in (None, 0) else (latest / ma5 - 1.0) * 100
    dev25 = None if latest in (None, 0) or ma25 in (None, 0) else (latest / ma25 - 1.0) * 100
    day_change_pct = None if latest in (None, 0) or prev_close in (None, 0) else (latest / prev_close - 1.0) * 100
    vol_avg20 = safe_float(last["VolAvg20"])
    vol_ratio = None if volume_now in (None, 0) or vol_avg20 in (None, 0) else (volume_now / vol_avg20 - 1.0) * 100

    prev_volume = safe_float(prev["Volume"])
    prev_vol_avg20 = safe_float(prev["VolAvg20"])
    prev_vol_ratio = None if prev_volume in (None, 0) or prev_vol_avg20 in (None, 0) else (prev_volume / prev_vol_avg20 - 1.0) * 100
    day_range = None if high_price is None or low_price is None else high_price - low_price
    prev_range = None if prev_high is None or prev_low is None else prev_high - prev_low

    day_range_atr = None if atr14 in (None, 0) or day_range is None else day_range / atr14
    day_close_position = calc_close_position(high_price, low_price, latest)
    prev_range_atr = None if atr14 in (None, 0) or prev_range is None else prev_range / atr14
    prev_close_position = calc_close_position(prev_high, prev_low, prev_close)

    prev_candle = grade_candle(prev_open, prev_close)
    prev_wick_shape = grade_wick_shape(prev_open, prev_high, prev_low, prev_close)

    recent5_high = safe_float(hist["High"].shift(1).rolling(5).max().iloc[-1]) if len(hist) >= 6 else None
    recent20_high = safe_float(hist["High"].shift(1).rolling(20).max().iloc[-1]) if len(hist) >= 21 else None
    recent60_high = safe_float(hist["High"].shift(1).rolling(60).max().iloc[-1]) if len(hist) >= 61 else None
    recent60_low = safe_float(hist["Low"].shift(1).rolling(60).min().iloc[-1]) if len(hist) >= 61 else None
    recent60_range_position = calc_close_position(recent60_high, recent60_low, latest)

    date_text = hist.index[-1].strftime("%Y-%m-%d")
    acquired_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    snapshot = {
        "name": stock_input.name,
        "code": stock_input.code,
        "date": date_text,
        "acquired_at": acquired_at,
        "latest_bar_time": latest_bar_time,
        "latest_price_source": latest_price_source,
        "latest_price_timestamp": build_latest_price_timestamp(date_text, latest_bar_time),
        "prev_open": prev_open,
        "prev_high": prev_high,
        "prev_low": prev_low,
        "prev_close": prev_close,
        "prev_change_pct": prev_change_pct,
        "prev_wick_shape": prev_wick_shape,
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "latest": latest,
        "day_change_pct": day_change_pct,
        "vwap": vwap,
        "vwap_diff": None if latest in (None, 0) or vwap in (None, 0) else (latest / vwap - 1.0) * 100,
        "vwap_source": vwap_source,
        "vwap_timestamp": build_latest_price_timestamp(date_text, latest_bar_time),
        "ma5": ma5,
        "dev5": dev5,
        "ma25": ma25,
        "dev25": dev25,
        "rsi": safe_float(last["RSI14"]),
        "atr14": atr14,
        "day_range": day_range,
        "day_range_atr": day_range_atr,
        "day_range_label": grade_range_by_atr(day_range_atr),
        "day_close_position": day_close_position,
        "day_close_position_label": grade_close_position(day_close_position),
        "prev_range": prev_range,
        "prev_range_atr": prev_range_atr,
        "prev_range_label": grade_range_by_atr(prev_range_atr),
        "prev_close_position": prev_close_position,
        "prev_close_position_label": grade_close_position(prev_close_position),
        "prev_volume": prev_volume,
        "prev_vol_ratio": prev_vol_ratio,
        "prev_session_judgement": grade_prev_session(prev_range_atr, prev_close_position, prev_vol_ratio),
        "prev_evaluation": grade_prev_evaluation(prev_candle, prev_wick_shape, prev_range_atr, prev_close_position, prev_vol_ratio),
        "ma25_distance": None if latest is None or ma25 is None else latest - ma25,
        "ma25_distance_atr": None if atr14 in (None, 0) or latest is None or ma25 is None else (latest - ma25) / atr14,
        "recent5_high": recent5_high,
        "recent5_high_distance": calc_distance(latest, recent5_high),
        "recent5_high_distance_pct": calc_distance_pct(latest, recent5_high),
        "recent20_high": recent20_high,
        "recent20_high_distance": calc_distance(latest, recent20_high),
        "recent20_high_distance_pct": calc_distance_pct(latest, recent20_high),
        "recent60_high": recent60_high,
        "recent60_low": recent60_low,
        "recent60_range_position": recent60_range_position,
        "recent60_range_zone": grade_range_zone(recent60_range_position),
        "volume": volume_now,
        "vol_ratio": vol_ratio,
        "prev_candle": prev_candle,
        "today_candle": grade_candle(open_price, latest),
        "trend": grade_trend(latest, ma5, ma25, ma25_prev5),
        "per_actual": valuation.get("per_actual"),
        "per_fy0": calc_per(latest, valuation.get("eps_fy0")) if valuation.get("eps_fy0") is not None else valuation.get("per_forward"),
        "per_fy1": calc_per(latest, valuation.get("eps_fy1")),
        "eps_actual": valuation.get("eps_actual"),
        "eps_fy0": valuation.get("eps_fy0"),
        "eps_fy1": valuation.get("eps_fy1"),
        "roe_actual": profitability.get("roe_actual"),
        "roe_fy0": profitability.get("roe_fy0"),
        "roe_fy1": profitability.get("roe_fy1"),
        "op_income_fy0": profitability.get("op_income_fy0"),
        "op_income_fy1": profitability.get("op_income_fy1"),
        "revenue_fy0": profitability.get("revenue_fy0"),
        "revenue_fy1": profitability.get("revenue_fy1"),
        "op_margin_actual": profitability.get("op_margin_actual"),
        "op_growth_actual": profitability.get("op_growth_actual"),
        "op_income_actual": profitability.get("op_income_actual"),
        "op_income_prev": profitability.get("op_income_prev"),
        "error": None,
        "diagnostics": diagnostics,
    }
    log_snapshot_result(snapshot)
    return snapshot


def get_structured_stock_snapshot(
    stock_input: StockInput,
    repository: StockDataRepository | None = None,
) -> StructuredStockSnapshot:
    return to_structured_snapshot(get_stock_snapshot(stock_input, repository))
