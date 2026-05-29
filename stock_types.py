from __future__ import annotations

from typing import Any, NotRequired, TypedDict


class Diagnostic(TypedDict):
    category: str
    field: str
    message: str


class StockIdentity(TypedDict):
    name: str
    code: str
    date: NotRequired[str]
    acquired_at: NotRequired[str]
    error: NotRequired[str | None]


class PriceSnapshot(TypedDict, total=False):
    latest_bar_time: str
    latest_price_source: str
    latest_price_timestamp: str
    open: float | None
    high: float | None
    low: float | None
    latest: float | None
    day_change_pct: float | None
    volume: float | None


class VwapSnapshot(TypedDict, total=False):
    value: float | None
    diff_pct: float | None
    source: str
    timestamp: str


class TechnicalSnapshot(TypedDict, total=False):
    ma5: float | None
    dev5: float | None
    ma25: float | None
    dev25: float | None
    rsi: float | None
    atr14: float | None
    trend: str


class RangeSnapshot(TypedDict, total=False):
    day_range: float | None
    day_range_atr: float | None
    day_range_label: str
    day_close_position: float | None
    day_close_position_label: str
    ma25_distance: float | None
    ma25_distance_atr: float | None


class PreviousSessionSnapshot(TypedDict, total=False):
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    change_pct: float | None
    candle: str
    wick_shape: str
    range_atr: float | None
    range_label: str
    close_position: float | None
    close_position_label: str
    volume: float | None
    vol_ratio: float | None
    session_judgement: str
    evaluation: str


class BreaklineSnapshot(TypedDict, total=False):
    recent5_high: float | None
    recent5_high_distance: float | None
    recent5_high_distance_pct: float | None
    recent20_high: float | None
    recent20_high_distance: float | None
    recent20_high_distance_pct: float | None
    recent60_high: float | None
    recent60_low: float | None
    recent60_range_position: float | None
    recent60_range_zone: str


class ValuationSnapshot(TypedDict, total=False):
    per_actual: float | None
    per_fy0: float | None
    per_fy1: float | None
    eps_actual: float | None
    eps_fy0: float | None
    eps_fy1: float | None


class ProfitabilitySnapshot(TypedDict, total=False):
    roe_actual: float | None
    op_margin_actual: float | None
    op_growth_actual: float | None


class DividendSnapshot(TypedDict, total=False):
    annual_dividend: float | None
    latest_dividend: float | None
    latest_dividend_date: str | None
    dividend_yield: float | None


class StructuredStockSnapshot(TypedDict):
    identity: StockIdentity
    price: PriceSnapshot
    vwap: VwapSnapshot
    technical: TechnicalSnapshot
    range: RangeSnapshot
    previous_session: PreviousSessionSnapshot
    breakline: BreaklineSnapshot
    valuation: ValuationSnapshot
    profitability: ProfitabilitySnapshot
    dividend: DividendSnapshot
    diagnostics: list[Diagnostic]


FlatStockSnapshot = dict[str, Any]


def to_structured_snapshot(stock: FlatStockSnapshot) -> StructuredStockSnapshot:
    return {
        "identity": {
            "name": stock.get("name"),
            "code": stock.get("code"),
            "date": stock.get("date"),
            "acquired_at": stock.get("acquired_at"),
            "error": stock.get("error"),
        },
        "price": {
            "latest_bar_time": stock.get("latest_bar_time"),
            "latest_price_source": stock.get("latest_price_source"),
            "latest_price_timestamp": stock.get("latest_price_timestamp"),
            "open": stock.get("open"),
            "high": stock.get("high"),
            "low": stock.get("low"),
            "latest": stock.get("latest"),
            "day_change_pct": stock.get("day_change_pct"),
            "volume": stock.get("volume"),
        },
        "vwap": {
            "value": stock.get("vwap"),
            "diff_pct": stock.get("vwap_diff"),
            "source": stock.get("vwap_source"),
            "timestamp": stock.get("vwap_timestamp"),
        },
        "technical": {
            "ma5": stock.get("ma5"),
            "dev5": stock.get("dev5"),
            "ma25": stock.get("ma25"),
            "dev25": stock.get("dev25"),
            "rsi": stock.get("rsi"),
            "atr14": stock.get("atr14"),
            "trend": stock.get("trend"),
        },
        "range": {
            "day_range": stock.get("day_range"),
            "day_range_atr": stock.get("day_range_atr"),
            "day_range_label": stock.get("day_range_label"),
            "day_close_position": stock.get("day_close_position"),
            "day_close_position_label": stock.get("day_close_position_label"),
            "ma25_distance": stock.get("ma25_distance"),
            "ma25_distance_atr": stock.get("ma25_distance_atr"),
        },
        "previous_session": {
            "open": stock.get("prev_open"),
            "high": stock.get("prev_high"),
            "low": stock.get("prev_low"),
            "close": stock.get("prev_close"),
            "change_pct": stock.get("prev_change_pct"),
            "candle": stock.get("prev_candle"),
            "wick_shape": stock.get("prev_wick_shape"),
            "range_atr": stock.get("prev_range_atr"),
            "range_label": stock.get("prev_range_label"),
            "close_position": stock.get("prev_close_position"),
            "close_position_label": stock.get("prev_close_position_label"),
            "volume": stock.get("prev_volume"),
            "vol_ratio": stock.get("prev_vol_ratio"),
            "session_judgement": stock.get("prev_session_judgement"),
            "evaluation": stock.get("prev_evaluation"),
        },
        "breakline": {
            "recent5_high": stock.get("recent5_high"),
            "recent5_high_distance": stock.get("recent5_high_distance"),
            "recent5_high_distance_pct": stock.get("recent5_high_distance_pct"),
            "recent20_high": stock.get("recent20_high"),
            "recent20_high_distance": stock.get("recent20_high_distance"),
            "recent20_high_distance_pct": stock.get("recent20_high_distance_pct"),
            "recent60_high": stock.get("recent60_high"),
            "recent60_low": stock.get("recent60_low"),
            "recent60_range_position": stock.get("recent60_range_position"),
            "recent60_range_zone": stock.get("recent60_range_zone"),
        },
        "valuation": {
            "per_actual": stock.get("per_actual"),
            "per_fy0": stock.get("per_fy0"),
            "per_fy1": stock.get("per_fy1"),
            "eps_actual": stock.get("eps_actual"),
            "eps_fy0": stock.get("eps_fy0"),
            "eps_fy1": stock.get("eps_fy1"),
        },
        "profitability": {
            "roe_actual": stock.get("roe_actual"),
            "op_margin_actual": stock.get("op_margin_actual"),
            "op_growth_actual": stock.get("op_growth_actual"),
        },
        "dividend": {
            "annual_dividend": stock.get("annual_dividend"),
            "latest_dividend": stock.get("latest_dividend"),
            "latest_dividend_date": stock.get("latest_dividend_date"),
            "dividend_yield": stock.get("dividend_yield"),
        },
        "diagnostics": stock.get("diagnostics") or [],
    }
