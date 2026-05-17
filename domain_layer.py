from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import math
from typing import Protocol

import pandas as pd

from data_layer import fetch_dividend_snapshot, fetch_history, fetch_intraday_vwap, fetch_profitability_snapshot, fetch_valuation_snapshot, safe_float

RSI_PERIOD = 14
ATR_PERIOD = 14


@dataclass(frozen=True)
class StockInput:
    name: str
    code: str


class StockDataRepository(Protocol):
    def fetch_daily_history(self, code: str, period: str = "4mo") -> pd.DataFrame: ...
    def fetch_intraday_snapshot(self, code: str, interval: str = "5m") -> dict | None: ...
    def fetch_valuation_snapshot(self, code: str) -> dict: ...
    def fetch_profitability_snapshot(self, code: str) -> dict: ...
    def fetch_dividend_snapshot(self, code: str) -> dict: ...


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

    def fetch_dividend_snapshot(self, code: str) -> dict:
        return fetch_dividend_snapshot(code)


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
        return "N/A"
    if ratio < 0.5:
        return "浅い値幅"
    if ratio < 1.0:
        return "通常値幅"
    if ratio < 1.5:
        return "大きめ"
    return "急拡大"


def grade_close_position(position):
    if position is None or (isinstance(position, float) and (math.isnan(position) or math.isinf(position))):
        return "N/A"
    if position >= 0.60:
        return "高値圏で終了"
    if position >= 0.30:
        return "中段で終了"
    return "安値圏で終了"


def calc_close_position(high_price, low_price, close_price):
    if high_price is None or low_price is None or close_price is None:
        return None
    price_range = high_price - low_price
    if price_range <= 0:
        return None
    return (close_price - low_price) / price_range


def grade_prev_session(prev_range_atr, close_position, prev_vol_ratio):
    if prev_range_atr is None or close_position is None:
        return "判定不可"
    vol_ratio = 0.0 if prev_vol_ratio is None else prev_vol_ratio
    if prev_range_atr >= 1.30 and close_position <= 0.30 and vol_ratio >= 20:
        return "崩れ"
    if prev_range_atr >= 1.50 and close_position <= 0.40:
        return "崩れ"
    if 0.50 <= prev_range_atr <= 1.20 and close_position >= 0.45 and vol_ratio <= 20:
        return "押し"
    return "中立"


def grade_prev_evaluation(prev_candle, prev_wick_shape, prev_range_atr, close_position, prev_vol_ratio):
    if prev_range_atr is None or close_position is None:
        return "判定不可"
    vol_ratio = 0.0 if prev_vol_ratio is None else prev_vol_ratio
    if (prev_range_atr >= 1.30 and close_position <= 0.30 and vol_ratio >= 20) or (prev_range_atr >= 1.50 and close_position <= 0.40):
        return "崩れ"
    if prev_candle == "陽線" and close_position >= 0.60 and prev_range_atr <= 1.20 and prev_wick_shape != "上ヒゲ長め":
        if vol_ratio >= -30:
            return "強い上昇"
    if prev_candle == "陽線" and (close_position < 0.50 or prev_wick_shape == "上ヒゲ長め"):
        return "弱い上昇"
    if prev_candle in ("陰線", "十字線") and 0.50 <= prev_range_atr <= 1.20 and close_position >= 0.45 and vol_ratio <= 20:
        return "押し"
    if prev_wick_shape == "下ヒゲ長め" and close_position >= 0.45 and prev_range_atr <= 1.30:
        return "押し"
    return "中立"


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
        return "N/A"
    if close_price > open_price:
        return "陽線"
    if close_price < open_price:
        return "陰線"
    return "十字線"


def grade_wick_shape(open_price, high_price, low_price, close_price):
    values = [open_price, high_price, low_price, close_price]
    if any(v is None for v in values):
        return "N/A"
    day_range = high_price - low_price
    if day_range <= 0:
        return "小動き"
    body = abs(close_price - open_price)
    upper_wick = high_price - max(open_price, close_price)
    lower_wick = min(open_price, close_price) - low_price
    body_ratio = body / day_range
    upper_ratio = upper_wick / day_range
    lower_ratio = lower_wick / day_range
    if body_ratio >= 0.65:
        return "実体大きめ"
    if lower_ratio >= 0.40 and lower_wick >= body * 1.5:
        return "下ヒゲ長め"
    if upper_ratio >= 0.40 and upper_wick >= body * 1.5:
        return "上ヒゲ長め"
    if body_ratio <= 0.20:
        return "小動き・十字線気味"
    return "通常足"


def grade_trend(latest, ma5, ma25, ma25_prev5):
    if latest is None or ma5 is None or ma25 is None:
        return "N/A"
    ma25_slope_up = ma25_prev5 is not None and ma25 > ma25_prev5
    if latest > ma5 > ma25 and ma25_slope_up:
        return "上昇トレンド"
    if latest < ma5 < ma25:
        return "下落トレンド"
    return "もみ合い / 戻り局面"




def calc_per(price, eps):
    if price in (None, 0) or eps is None or eps <= 0:
        return None
    return price / eps



def calc_dividend_yield(latest_price, annual_dividend):
    if latest_price in (None, 0) or annual_dividend is None:
        return None
    return (annual_dividend / latest_price) * 100

def get_stock_snapshot(stock_input: StockInput, repository: StockDataRepository | None = None):
    repo = repository or YFinanceStockDataRepository()
    hist = repo.fetch_daily_history(stock_input.code, period="4mo")
    if hist.empty or len(hist) < 30:
        return {"name": stock_input.name, "code": stock_input.code, "error": "価格データ不足"}

    hist = hist[["Open", "High", "Low", "Close", "Volume"]].dropna().copy()
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

    intraday = repo.fetch_intraday_snapshot(stock_input.code, interval="5m")
    valuation = repo.fetch_valuation_snapshot(stock_input.code)
    profitability = repo.fetch_profitability_snapshot(stock_input.code)
    dividend = repo.fetch_dividend_snapshot(stock_input.code)
    latest_bar_time = "終値"
    open_price = safe_float(last["Open"])
    high_price = safe_float(last["High"])
    low_price = safe_float(last["Low"])
    volume_now = vol

    if intraday is not None:
        latest = intraday.get("latest_price") if intraday.get("latest_price") is not None else latest
        latest_bar_time = intraday.get("latest_bar_time") or latest_bar_time
        open_price = intraday.get("open") if intraday.get("open") is not None else open_price
        high_price = intraday.get("high") if intraday.get("high") is not None else high_price
        low_price = intraday.get("low") if intraday.get("low") is not None else low_price
        volume_now = intraday.get("volume") if intraday.get("volume") is not None else volume_now
        vwap = intraday.get("vwap")
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

    return {
        "name": stock_input.name,
        "code": stock_input.code,
        "date": hist.index[-1].strftime("%Y-%m-%d"),
        "acquired_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "latest_bar_time": latest_bar_time,
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
        "op_margin_q_latest": profitability.get("op_margin_q_latest"),
        "op_growth_q_yoy": profitability.get("op_growth_q_yoy"),
        "op_income_q_latest": profitability.get("op_income_q_latest"),
        "op_income_q_prev_year": profitability.get("op_income_q_prev_year"),
        "op_income_q_ttm": profitability.get("op_income_q_ttm"),
        "revenue_q_ttm": profitability.get("revenue_q_ttm"),
        "op_margin_q_ttm": profitability.get("op_margin_q_ttm"),
        "op_income_q_ttm_prev": profitability.get("op_income_q_ttm_prev"),
        "op_growth_q_ttm_yoy": profitability.get("op_growth_q_ttm_yoy"),
        "quarterly_data_status": profitability.get("quarterly_data_status"),
        "quarterly_periods_count": profitability.get("quarterly_periods_count"),
        "quarterly_latest_period": profitability.get("quarterly_latest_period"),
        "op_margin_fy0": profitability.get("op_margin_fy0"),
        "op_margin_fy1": profitability.get("op_margin_fy1"),
        "annual_dividend": dividend.get("annual_dividend"),
        "latest_dividend": dividend.get("latest_dividend"),
        "latest_dividend_date": dividend.get("latest_dividend_date"),
        "dividend_yield": calc_dividend_yield(latest, dividend.get("annual_dividend")),
        "error": None,
    }
