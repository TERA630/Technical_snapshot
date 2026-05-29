from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd

from stock_constants import (
    DISPLAY_LABELS,
    ENCODING,
    ERROR_MESSAGES,
    MARKET_DISPLAY_ORDER,
    NA_TEXT,
    SECTION_TITLES,
    TIMEZONE,
    UNIT_LABELS,
)


def fmt_price(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return NA_TEXT
    return f"{value:,.2f}"


def fmt_time(value):
    if value is None:
        return NA_TEXT
    if isinstance(value, str):
        return value or NA_TEXT
    try:
        ts = pd.Timestamp(value)
        if ts.tzinfo is not None:
            ts = ts.tz_convert(TIMEZONE)
        return ts.strftime("%H:%M")
    except Exception:
        return NA_TEXT


def fmt_pct(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return NA_TEXT
    return f"{value:+.2f}%"


def fmt_pct_plain(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return NA_TEXT
    return f"{value:.1f}%"


def fmt_price_diff(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return NA_TEXT
    return f"{value:+,.2f}"


def fmt_ohlc(open_price, high_price, low_price, close_price):
    return f"{fmt_price(open_price)} / {fmt_price(high_price)} / {fmt_price(low_price)} / {fmt_price(close_price)}"


def fmt_vwap_position(latest, vwap):
    if latest is None or vwap in (None, 0):
        return NA_TEXT
    diff = latest - vwap
    diff_pct = (latest / vwap - 1.0) * 100
    return f"{fmt_price(vwap)}（{fmt_price_diff(diff)} / {fmt_pct(diff_pct)}）"


def fmt_close_position(position, label):
    if position is None or (isinstance(position, float) and (math.isnan(position) or math.isinf(position))):
        return f"{NA_TEXT}（{label}）"
    return f"{fmt_pct_plain(position * 100)}（{label}）"


def fmt_volume(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return NA_TEXT
    return f"{value:,.0f}{UNIT_LABELS['shares']}"


def fmt_multiple(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return NA_TEXT
    return f"{value:.2f}{UNIT_LABELS['multiple']}"


def fmt_price_plain(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return NA_TEXT
    return f"{value:.0f}"




def fmt_price_current(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return NA_TEXT
    if abs(value) >= 1000:
        return f"{value:.0f}"
    return f"{value:.1f}"


def fmt_pct_no_sign_jp(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return NA_TEXT
    return f"{value:.2f}{UNIT_LABELS['percent_jp']}"

def fmt_pct_jp(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return NA_TEXT
    return f"{value:+.2f}{UNIT_LABELS['percent_jp']}"


def fmt_per(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return NA_TEXT
    return f"{value:.1f}{UNIT_LABELS['multiple']}"


def fmt_eps(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return NA_TEXT
    return f"{value:.0f}{UNIT_LABELS['yen']}"


def parse_watchlist_text(text: str):
    pattern = re.compile(r"[-*]?\s*([^\n()]+?)\s*[\(（]\s*(\d{4})\s*[\)）]")
    out = []
    seen = set()
    for line in text.splitlines():
        m = pattern.search(line)
        if not m:
            continue
        name = m.group(1).strip()
        code = m.group(2).strip()
        if code in seen:
            continue
        seen.add(code)
        out.append((name, code))
    return out


def load_watchlist(path: Path):
    try:
        text = path.read_text(encoding=ENCODING)
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8-sig")
    parsed = parse_watchlist_text(text)
    if not parsed:
        raise ValueError(ERROR_MESSAGES["watchlist_parse_failed"])
    return parsed


def render_market_block(market):
    lines = [SECTION_TITLES["market"]]
    for key in MARKET_DISPLAY_ORDER:
        item = market.get(key, {})
        lines.append(f"{key}：{fmt_price(item.get('latest'))}（{fmt_pct(item.get('change_pct'))} / {item.get('trend', NA_TEXT)}）")
    return "\n".join(lines)


def render_stock_block(stock, include_market: bool, market_block: str) -> str:
    if stock.get("error"):
        return f"【{DISPLAY_LABELS['stock']}】{stock['name']} ({stock['code']})\n\n{DISPLAY_LABELS['fetch_failed']}：{stock['error']}"

    acquired_at = stock.get("acquired_at", "")
    base_year = None
    if isinstance(acquired_at, str) and len(acquired_at) >= 4 and acquired_at[:4].isdigit():
        base_year = int(acquired_at[:4])
    else:
        base_year = pd.Timestamp.now().year
    actual_year = base_year - 1
    forecast_year = base_year

    lines = [
        f"【{DISPLAY_LABELS['stock']}】{stock['name']} ({stock['code']})",
        "",
        SECTION_TITLES["today_range"],
        f"{DISPLAY_LABELS['current_price']}({stock['date'].replace('-', '/')}　{stock.get('latest_bar_time', NA_TEXT)})：{fmt_price_current(stock['latest'])}({DISPLAY_LABELS['prev_day_change']}{fmt_pct_jp(stock['day_change_pct'])})",
        "",
        f"{DISPLAY_LABELS['ohlc']}：{fmt_ohlc(stock['open'], stock['high'], stock['low'], stock['latest'])}",
        f"{DISPLAY_LABELS['day_range']}：{fmt_price(stock['day_range'])}（{DISPLAY_LABELS['atr_ratio']} {fmt_multiple(stock['day_range_atr'])} / {stock['day_range_label']}）",
        f"{DISPLAY_LABELS['close_position']}：{fmt_close_position(stock.get('day_close_position'), stock.get('day_close_position_label', NA_TEXT))}",
        "",
        f"PER  {fmt_per(stock.get('per_actual'))}({DISPLAY_LABELS['actual']}) {fmt_per(stock.get('per_fy0'))}({DISPLAY_LABELS['fy0_forecast']}) {fmt_per(stock.get('per_fy1'))}({DISPLAY_LABELS['fy1_forecast']})",
        f"EPS  {fmt_eps(stock.get('eps_actual'))}({DISPLAY_LABELS['actual']}) {fmt_eps(stock.get('eps_fy0'))}({DISPLAY_LABELS['fy0_forecast']}) {fmt_eps(stock.get('eps_fy1'))}({DISPLAY_LABELS['fy1_forecast']})",
        "",
        SECTION_TITLES["technical"],
        f"{DISPLAY_LABELS['vwap']}：{fmt_vwap_position(stock['latest'], stock['vwap'])}",
        f"{DISPLAY_LABELS['ma5']}：{fmt_price(stock['ma5'])}（{DISPLAY_LABELS['deviation']} {fmt_pct(stock['dev5'])}）",
        f"{DISPLAY_LABELS['ma25']}：{fmt_price(stock['ma25'])}（{DISPLAY_LABELS['deviation']} {fmt_pct(stock['dev25'])} / {DISPLAY_LABELS['distance']} {fmt_price_diff(stock['ma25_distance'])} / {DISPLAY_LABELS['atr_ratio']} {fmt_multiple(stock['ma25_distance_atr'])}）",
        f"{DISPLAY_LABELS['atr14']}：{fmt_price(stock['atr14'])}",
        f"{DISPLAY_LABELS['rsi']}：{fmt_price(stock['rsi'])}",
        f"{DISPLAY_LABELS['volume']}：{fmt_volume(stock['volume'])}（{DISPLAY_LABELS['vol_avg20_ratio']} {fmt_pct(stock['vol_ratio'])}）",
        "",
        SECTION_TITLES["prev_evaluation"],
        f"{DISPLAY_LABELS['prev_close']}：{fmt_price(stock['prev_close'])}（{DISPLAY_LABELS['prev_day_change']} {fmt_pct(stock['prev_change_pct'])}）",
        f"{DISPLAY_LABELS['prev_hlc']}：{fmt_price(stock['prev_high'])} / {fmt_price(stock['prev_low'])} / {fmt_price(stock['prev_close'])}",
        f"{DISPLAY_LABELS['candle']}：{stock['prev_candle']} / {stock['prev_wick_shape']}",
        f"{DISPLAY_LABELS['close_position']}：{fmt_close_position(stock['prev_close_position'], stock['prev_close_position_label'])}",
        f"{DISPLAY_LABELS['atr_ratio']}：{fmt_multiple(stock['prev_range_atr'])}（{stock['prev_range_label']}）",
        f"{DISPLAY_LABELS['volume']}：{fmt_volume(stock['prev_volume'])}（{DISPLAY_LABELS['vol_avg20_ratio']} {fmt_pct(stock['prev_vol_ratio'])}）",
        f"{DISPLAY_LABELS['prev_session_judgement']}：{stock['prev_session_judgement']}",
        f"{DISPLAY_LABELS['overall_evaluation']}：{stock['prev_evaluation']}",
        "",
        SECTION_TITLES["fundamentals"],
        f"{DISPLAY_LABELS['dividend_yield']} {fmt_pct_no_sign_jp(stock.get('dividend_yield'))}",
        "",
        f"{actual_year}{DISPLAY_LABELS['actual_roe']} {fmt_pct_no_sign_jp(stock.get('roe_actual'))}",
        f"{actual_year}{DISPLAY_LABELS['actual_op_margin']} {fmt_pct_no_sign_jp(stock.get('op_margin_actual'))}",
        f"{actual_year}{DISPLAY_LABELS['actual_op_growth']} {fmt_pct_no_sign_jp(stock.get('op_growth_actual'))}",
        f"{forecast_year}{DISPLAY_LABELS['forecast_op_margin']} {fmt_pct_no_sign_jp(stock.get('op_margin_fy0'))}",
        "",
        SECTION_TITLES["breakline"],
        f"{DISPLAY_LABELS['prev_high']}：{fmt_price(stock['prev_high'])}",
        f"{DISPLAY_LABELS['recent5_high']}：{fmt_price(stock['recent5_high'])}（{DISPLAY_LABELS['current_diff']} {fmt_price_diff(stock['recent5_high_distance'])} / {fmt_pct(stock['recent5_high_distance_pct'])}）",
        f"{DISPLAY_LABELS['recent20_high']}：{fmt_price(stock['recent20_high'])}（{DISPLAY_LABELS['current_diff']} {fmt_price_diff(stock['recent20_high_distance'])} / {fmt_pct(stock['recent20_high_distance_pct'])}）",
        f"{DISPLAY_LABELS['recent60_high']}：{fmt_price(stock.get('recent60_high'))}",
        f"{DISPLAY_LABELS['recent60_low']}：{fmt_price(stock.get('recent60_low'))}",
        f"{DISPLAY_LABELS['current_range']}：{fmt_pct_plain((stock.get('recent60_range_position') or 0) * 100) if stock.get('recent60_range_position') is not None else NA_TEXT}（{stock.get('recent60_range_zone', NA_TEXT)}）",
        "",
        SECTION_TITLES["trend"],
        f"{DISPLAY_LABELS['recent_trend']}：{stock['trend']}",
    ]
    if include_market:
        lines.extend(["", market_block])
    return "\n".join(lines)
