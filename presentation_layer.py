from __future__ import annotations

import math
import re
from pathlib import Path

import pandas as pd


def fmt_price(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    return f"{value:,.2f}"


def fmt_time(value):
    if value is None:
        return "N/A"
    if isinstance(value, str):
        return value or "N/A"
    try:
        ts = pd.Timestamp(value)
        if ts.tzinfo is not None:
            ts = ts.tz_convert("Asia/Tokyo")
        return ts.strftime("%H:%M")
    except Exception:
        return "N/A"


def fmt_pct(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    return f"{value:+.2f}%"


def fmt_pct_plain(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    return f"{value:.1f}%"


def fmt_price_diff(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    return f"{value:+,.2f}"


def fmt_ohlc(open_price, high_price, low_price, close_price):
    return f"{fmt_price(open_price)} / {fmt_price(high_price)} / {fmt_price(low_price)} / {fmt_price(close_price)}"


def fmt_vwap_position(latest, vwap):
    if latest is None or vwap in (None, 0):
        return "N/A"
    diff = latest - vwap
    diff_pct = (latest / vwap - 1.0) * 100
    return f"{fmt_price(vwap)}（{fmt_price_diff(diff)} / {fmt_pct(diff_pct)}）"


def fmt_close_position(position, label):
    if position is None or (isinstance(position, float) and (math.isnan(position) or math.isinf(position))):
        return f"N/A（{label}）"
    return f"{fmt_pct_plain(position * 100)}（{label}）"


def fmt_volume(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    return f"{value:,.0f}株"


def fmt_multiple(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    return f"{value:.2f}倍"


def fmt_price_plain(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    return f"{value:.0f}"




def fmt_price_current(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    if abs(value) >= 1000:
        return f"{value:.0f}"
    return f"{value:.1f}"


def fmt_pct_no_sign_jp(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    return f"{value:.2f}％"

def fmt_pct_jp(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    return f"{value:+.2f}％"


def fmt_per(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    return f"{value:.1f}倍"


def fmt_eps(value):
    if value is None or (isinstance(value, float) and (math.isnan(value) or math.isinf(value))):
        return "N/A"
    return f"{value:.0f}円"


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
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        text = path.read_text(encoding="utf-8-sig")
    parsed = parse_watchlist_text(text)
    if not parsed:
        raise ValueError("監視銘柄ファイルから '銘柄名 (4桁コード)' を抽出できませんでした。")
    return parsed


def render_market_block(market):
    lines = ["■市況"]
    for key in ["WTI", "銅", "NASDAQ"]:
        item = market.get(key, {})
        lines.append(f"{key}：{fmt_price(item.get('latest'))}（{fmt_pct(item.get('change_pct'))} / {item.get('trend', 'N/A')}）")
    return "\n".join(lines)


def render_stock_block(stock, include_market: bool, market_block: str) -> str:
    if stock.get("error"):
        return f"【銘柄】{stock['name']} ({stock['code']})\n\n取得失敗：{stock['error']}"

    acquired_at = stock.get("acquired_at", "")
    base_year = None
    if isinstance(acquired_at, str) and len(acquired_at) >= 4 and acquired_at[:4].isdigit():
        base_year = int(acquired_at[:4])
    else:
        base_year = pd.Timestamp.now().year
    actual_year = base_year - 1
    forecast_year = base_year

    lines = [
        f"【銘柄】{stock['name']} ({stock['code']})",
        "",
        "■当日位置・レンジ",
        f"現在値({stock['date'].replace('-', '/')}　{stock.get('latest_bar_time', 'N/A')})：{fmt_price_current(stock['latest'])}(前日比{fmt_pct_jp(stock['day_change_pct'])})",
        "",
        f"O/H/L/C：{fmt_ohlc(stock['open'], stock['high'], stock['low'], stock['latest'])}",
        f"当日値幅：{fmt_price(stock['day_range'])}（ATR比 {fmt_multiple(stock['day_range_atr'])} / {stock['day_range_label']}）",
        f"終端位置：{fmt_close_position(stock.get('day_close_position'), stock.get('day_close_position_label', 'N/A'))}",
        "",
        f"PER  {fmt_per(stock.get('per_actual'))}(実績) {fmt_per(stock.get('per_fy0'))}(今期末予想) {fmt_per(stock.get('per_fy1'))}(来期予想)",
        f"EPS  {fmt_eps(stock.get('eps_actual'))}(実績) {fmt_eps(stock.get('eps_fy0'))}(今期末予想) {fmt_eps(stock.get('eps_fy1'))}(来期予想)",
        "",
        "■当日テクニカル",
        f"VWAP：{fmt_vwap_position(stock['latest'], stock['vwap'])}",
        f"5日線：{fmt_price(stock['ma5'])}（乖離 {fmt_pct(stock['dev5'])}）",
        f"25日線：{fmt_price(stock['ma25'])}（乖離 {fmt_pct(stock['dev25'])} / 距離 {fmt_price_diff(stock['ma25_distance'])} / ATR比 {fmt_multiple(stock['ma25_distance_atr'])}）",
        f"14日ATR：{fmt_price(stock['atr14'])}",
        f"RSI：{fmt_price(stock['rsi'])}",
        f"出来高：{fmt_volume(stock['volume'])}（20日平均比 {fmt_pct(stock['vol_ratio'])}）",
        "",
        "■前日評価",
        f"前日終値：{fmt_price(stock['prev_close'])}（前日比 {fmt_pct(stock['prev_change_pct'])}）",
        f"前日H/L/C：{fmt_price(stock['prev_high'])} / {fmt_price(stock['prev_low'])} / {fmt_price(stock['prev_close'])}",
        f"ローソク：{stock['prev_candle']} / {stock['prev_wick_shape']}",
        f"終端位置：{fmt_close_position(stock['prev_close_position'], stock['prev_close_position_label'])}",
        f"ATR比：{fmt_multiple(stock['prev_range_atr'])}（{stock['prev_range_label']}）",
        f"出来高：{fmt_volume(stock['prev_volume'])}（20日平均比 {fmt_pct(stock['prev_vol_ratio'])}）",
        f"押し判定：{stock['prev_session_judgement']}",
        f"総合評価：{stock['prev_evaluation']}",
        "",
        "■ファンダメンタル",
        f"配当利回り {fmt_pct_no_sign_jp(stock.get('dividend_yield'))}",
        "",
        f"{actual_year}年実績ROE {fmt_pct_no_sign_jp(stock.get('roe_actual'))}",
        f"{actual_year}年実績営業利益率 {fmt_pct_no_sign_jp(stock.get('op_margin_actual'))}",
        f"{actual_year}年実績営業成長率 {fmt_pct_no_sign_jp(stock.get('op_growth_actual'))}",
        f"{forecast_year}年予想営業利益率 {fmt_pct_no_sign_jp(stock.get('op_margin_fy0'))}",
        "",
        "■節目・ブレイクライン",
        f"前日高値：{fmt_price(stock['prev_high'])}",
        f"直近5日高値：{fmt_price(stock['recent5_high'])}（現在値との差 {fmt_price_diff(stock['recent5_high_distance'])} / {fmt_pct(stock['recent5_high_distance_pct'])}）",
        f"直近20日高値：{fmt_price(stock['recent20_high'])}（現在値との差 {fmt_price_diff(stock['recent20_high_distance'])} / {fmt_pct(stock['recent20_high_distance_pct'])}）",
        f"直近60日高値：{fmt_price(stock['recent60_high'])}（現在値との差 {fmt_price_diff(stock['recent60_high_distance'])} / {fmt_pct(stock['recent60_high_distance_pct'])}）",
        f"直近60日安値：{fmt_price(stock['recent60_low'])}（現在値との差 {fmt_price_diff(stock['recent60_low_distance'])} / {fmt_pct(stock['recent60_low_distance_pct'])}）",
        f"60日レンジ位置：{fmt_close_position(stock['recent60_range_position'], stock['recent60_range_position_label'])}",
        "",
        "■流れ",
        f"直近トレンド：{stock['trend']}",
    ]
    if include_market:
        lines.extend(["", market_block])
    return "\n".join(lines)
