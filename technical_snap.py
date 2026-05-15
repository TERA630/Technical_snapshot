#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import math
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError as exc:
    raise SystemExit("tkinter が必要です。GUI対応の Python を使ってください。") from exc

try:
    import yfinance as yf
except ImportError as exc:
    raise SystemExit("yfinance が必要です。先に `pip install yfinance pandas` を実行してください。") from exc

RSI_PERIOD = 14
ATR_PERIOD = 14
MARKET_SYMBOLS = {
    "WTI": "CL=F",
    "銅": "HG=F",
    "NASDAQ": "^IXIC",
}


def safe_float(value):
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except Exception:
        return None



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


def compute_atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    prev_close = df["Close"].shift(1)
    true_range = pd.concat([
        df["High"] - df["Low"],
        (df["High"] - prev_close).abs(),
        (df["Low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def classify_range_by_atr(ratio):
    if ratio is None or (isinstance(ratio, float) and (math.isnan(ratio) or math.isinf(ratio))):
        return "N/A"
    if ratio < 0.5:
        return "浅い値幅"
    if ratio < 1.0:
        return "通常値幅"
    if ratio < 1.5:
        return "大きめ"
    return "急拡大"


def classify_close_position(position):
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


def classify_prev_session(prev_range_atr, close_position, prev_vol_ratio):
    """
    前日が押し・中立・崩れのどれに近いかを粗く判定する。
    目的はエントリー前の見落とし防止であり、単独で売買判断には使わない。
    """
    if prev_range_atr is None or close_position is None:
        return "判定不可"

    vol_ratio = 0.0 if prev_vol_ratio is None else prev_vol_ratio

    # 大きく動いて安値圏で終わり、出来高も増えているなら崩れ。
    if prev_range_atr >= 1.30 and close_position <= 0.30 and vol_ratio >= 20:
        return "崩れ"
    if prev_range_atr >= 1.50 and close_position <= 0.40:
        return "崩れ"

    # 適度な値幅で、安値から戻して終わり、出来高が過度に増えていなければ押し。
    if 0.50 <= prev_range_atr <= 1.20 and close_position >= 0.45 and vol_ratio <= 20:
        return "押し"

    return "中立"


def classify_prev_evaluation(prev_candle, prev_wick_shape, prev_range_atr, close_position, prev_vol_ratio):
    """
    前日の値動きを、相談時に読みやすい1行評価へ落とす。
    classify_prev_session は「押し/中立/崩れ」の安全判定、
    こちらは陽線・陰線・ヒゲを含めた補助的な解釈ラベル。
    """
    if prev_range_atr is None or close_position is None:
        return "判定不可"

    vol_ratio = 0.0 if prev_vol_ratio is None else prev_vol_ratio

    # 明確な崩れ：大きく動いて安値圏で終わる。出来高増ならさらに危険。
    if (prev_range_atr >= 1.30 and close_position <= 0.30 and vol_ratio >= 20) or (prev_range_atr >= 1.50 and close_position <= 0.40):
        return "崩れ"

    # 強い上昇：終値が高値寄り。上ヒゲ長めは除外して、上で売られた陽線を強いとは扱わない。
    if prev_candle == "陽線" and close_position >= 0.60 and prev_range_atr <= 1.20 and prev_wick_shape != "上ヒゲ長め":
        if vol_ratio >= -30:
            return "強い上昇"

    # 弱い上昇：陽線でも高値から失速、または終値が中段以下。
    if prev_candle == "陽線" and (close_position < 0.50 or prev_wick_shape == "上ヒゲ長め"):
        return "弱い上昇"

    # 押し：陰線または小動きでも、安値圏で終わらず、値幅が通常範囲。
    if prev_candle in ("陰線", "十字線") and 0.50 <= prev_range_atr <= 1.20 and close_position >= 0.45 and vol_ratio <= 20:
        return "押し"

    # 下ヒゲで戻している場合は、ローソク色にかかわらず押し候補。
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

def fetch_intraday_vwap(code: str, interval: str = "5m"):
    """
    当日足からVWAPと最新足の時刻を取る。
    yfinanceは環境により20分遅延・終値反映待ちがあるため、
    取得時刻と最新足時刻は分けて表示する。
    """
    symbol = f"{code}.T"
    df = yf.download(symbol, period="1d", interval=interval, progress=False, auto_adjust=False)

    if df is None or df.empty:
        return None, pd.DataFrame()

    df = df.dropna().copy()

    # MultiIndex対策
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required_cols = {"Open", "High", "Low", "Close", "Volume"}
    if not required_cols.issubset(set(df.columns)):
        return None, df

    # 出来高0の足はVWAP計算を壊しやすいので除外。ただし全除外なら失敗扱い。
    df = df[df["Volume"].fillna(0) > 0].copy()
    if df.empty:
        return None, pd.DataFrame()

    # 典型価格と累積VWAP
    df["TypicalPrice"] = (df["High"] + df["Low"] + df["Close"]) / 3
    df["PV"] = df["TypicalPrice"] * df["Volume"]
    df["CumPV"] = df["PV"].cumsum()
    df["CumVol"] = df["Volume"].cumsum()
    df["VWAP"] = df["CumPV"] / df["CumVol"]

    latest_idx = df.index[-1]
    latest_price = safe_float(df["Close"].iloc[-1])
    latest_vwap = safe_float(df["VWAP"].iloc[-1])
    if latest_price is None or latest_vwap in (None, 0):
        return None, df

    return {
        "latest_price": latest_price,
        "latest_bar_time": fmt_time(latest_idx),
        "open": safe_float(df["Open"].iloc[0]),
        "high": safe_float(df["High"].max()),
        "low": safe_float(df["Low"].min()),
        "vwap": latest_vwap,
        "vwap_diff_pct": (latest_price / latest_vwap - 1) * 100,
        "volume": safe_float(df["Volume"].sum()),
    }, df

def get_realtime_snapshot_yf(code: str):
    result, _ = fetch_intraday_vwap(code, interval="5m")
    return result


def ema_rsi(series: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))



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



def fetch_history(symbol: str, period: str = "4mo", interval: str = "1d") -> pd.DataFrame:
    df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df



def infer_candle(open_price, close_price):
    if open_price is None or close_price is None:
        return "N/A"
    if close_price > open_price:
        return "陽線"
    if close_price < open_price:
        return "陰線"
    return "十字線"


def infer_wick_shape(open_price, high_price, low_price, close_price):
    """
    前日の足を、エントリー相談で使いやすい粗い形に分類する。
    しきい値は厳密な酒田五法ではなく、押し目判断用の実務分類。
    """
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



def infer_trend(latest, ma5, ma25, ma25_prev5):
    if latest is None or ma5 is None or ma25 is None:
        return "N/A"
    ma25_slope_up = ma25_prev5 is not None and ma25 > ma25_prev5
    if latest > ma5 > ma25 and ma25_slope_up:
        return "上昇トレンド"
    if latest < ma5 < ma25:
        return "下落トレンド"
    return "もみ合い / 戻り局面"



def fetch_market_snapshot():
    out = {}
    for name, symbol in MARKET_SYMBOLS.items():
        df = fetch_history(symbol, period="10d")
        if len(df) < 2:
            out[name] = {"latest": None, "change_pct": None, "trend": "N/A"}
            continue
        latest = safe_float(df["Close"].iloc[-1])
        prev = safe_float(df["Close"].iloc[-2])
        ma5 = safe_float(df["Close"].rolling(5).mean().iloc[-1]) if len(df) >= 5 else None
        ma25 = safe_float(df["Close"].rolling(25).mean().iloc[-1]) if len(df) >= 25 else None
        trend = infer_trend(latest, ma5, ma25, None) if ma5 is not None else "N/A"
        change_pct = None if latest in (None, 0) or prev in (None, 0) else (latest / prev - 1.0) * 100
        out[name] = {"latest": latest, "change_pct": change_pct, "trend": trend}
    return out



def analyze_stock(name: str, code: str):
    symbol = f"{code}.T"
    hist = fetch_history(symbol, period="4mo")
    if hist.empty or len(hist) < 30:
        return {"name": name, "code": code, "error": "価格データ不足"}

    hist = hist[["Open", "High", "Low", "Close", "Volume"]].dropna().copy()
    hist["MA5"] = hist["Close"].rolling(5).mean()
    hist["MA25"] = hist["Close"].rolling(25).mean()
    hist["RSI14"] = ema_rsi(hist["Close"], RSI_PERIOD)
    hist["ATR14"] = compute_atr(hist, ATR_PERIOD)
    hist["VolAvg20"] = hist["Volume"].rolling(20).mean()

    last = hist.iloc[-1]
    prev = hist.iloc[-2]
    ma25_prev5 = safe_float(hist["MA25"].iloc[-6]) if len(hist) >= 30 else None

    latest = safe_float(last["Close"])
    ma5 = safe_float(last["MA5"])
    ma25 = safe_float(last["MA25"])
    vol = safe_float(last["Volume"])
    atr14 = safe_float(last["ATR14"])

    intraday = get_realtime_snapshot_yf(code)

    latest_bar_time = "終値"
    open_price = safe_float(last["Open"])
    high_price = safe_float(last["High"])
    low_price = safe_float(last["Low"])
    volume_now = vol

    if intraday is not None:
        # 場中・引け後の最終5分足を現在値として優先する。
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
    
    prev_open = safe_float(prev["Open"])
    prev_high = safe_float(prev["High"])
    prev_low = safe_float(prev["Low"])
    prev_close = safe_float(prev["Close"])
    prev_change_pct = None
    if len(hist) >= 3:
        prev_prev_close = safe_float(hist["Close"].iloc[-3])
        if prev_close not in (None, 0) and prev_prev_close not in (None, 0):
            prev_change_pct = (prev_close / prev_prev_close - 1.0) * 100

    dev5 = None if latest in (None, 0) or ma5 in (None, 0) else (latest / ma5 - 1.0) * 100
    dev25 = None if latest in (None, 0) or ma25 in (None, 0) else (latest / ma25 - 1.0) * 100
    vwap_diff = None if latest in (None, 0) or vwap in (None, 0) else (latest / vwap - 1.0) * 100
    day_change_pct = None if latest in (None, 0) or prev_close in (None, 0) else (latest / prev_close - 1.0) * 100
    vol_avg20 = safe_float(last["VolAvg20"])
    vol_ratio = None if volume_now in (None, 0) or vol_avg20 in (None, 0) else (volume_now / vol_avg20 - 1.0) * 100

    prev_volume = safe_float(prev["Volume"])
    prev_vol_avg20 = safe_float(prev["VolAvg20"])
    prev_vol_ratio = None if prev_volume in (None, 0) or prev_vol_avg20 in (None, 0) else (prev_volume / prev_vol_avg20 - 1.0) * 100

    day_range = None
    if high_price is not None and low_price is not None:
        day_range = high_price - low_price

    prev_range = None
    if prev_high is not None and prev_low is not None:
        prev_range = prev_high - prev_low

    day_range_atr = None if atr14 in (None, 0) or day_range is None else day_range / atr14
    day_close_position = calc_close_position(high_price, low_price, latest)
    prev_range_atr = None if atr14 in (None, 0) or prev_range is None else prev_range / atr14
    prev_close_position = calc_close_position(prev_high, prev_low, prev_close)
    prev_session_judgement = classify_prev_session(prev_range_atr, prev_close_position, prev_vol_ratio)
    prev_evaluation = classify_prev_evaluation(
        infer_candle(prev_open, prev_close),
        infer_wick_shape(prev_open, prev_high, prev_low, prev_close),
        prev_range_atr,
        prev_close_position,
        prev_vol_ratio,
    )
    ma25_distance = None if latest is None or ma25 is None else latest - ma25
    ma25_distance_atr = None if atr14 in (None, 0) or ma25_distance is None else ma25_distance / atr14

    # ブレイクラインとして使うため、当日を除いた直近高値を採用する。
    recent5_high = safe_float(hist["High"].shift(1).rolling(5).max().iloc[-1]) if len(hist) >= 6 else None
    recent20_high = safe_float(hist["High"].shift(1).rolling(20).max().iloc[-1]) if len(hist) >= 21 else None
    recent5_high_distance = calc_distance(latest, recent5_high)
    recent5_high_distance_pct = calc_distance_pct(latest, recent5_high)
    recent20_high_distance = calc_distance(latest, recent20_high)
    recent20_high_distance_pct = calc_distance_pct(latest, recent20_high)

    return {
        "name": name,
        "code": code,
        "date": hist.index[-1].strftime("%Y-%m-%d"),
        "acquired_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "latest_bar_time": latest_bar_time,
        "prev_open": prev_open,
        "prev_high": prev_high,
        "prev_low": prev_low,
        "prev_close": prev_close,
        "prev_change_pct": prev_change_pct,
        "prev_wick_shape": infer_wick_shape(prev_open, prev_high, prev_low, prev_close),
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "latest": latest,
        "day_change_pct": day_change_pct,
        "vwap": vwap,
        "vwap_diff": vwap_diff,
        "ma5": ma5,
        "dev5": dev5,
        "ma25": ma25,
        "dev25": dev25,
        "rsi": safe_float(last["RSI14"]),
        "atr14": atr14,
        "day_range": day_range,
        "day_range_atr": day_range_atr,
        "day_range_label": classify_range_by_atr(day_range_atr),
        "day_close_position": day_close_position,
        "day_close_position_label": classify_close_position(day_close_position),
        "prev_range": prev_range,
        "prev_range_atr": prev_range_atr,
        "prev_range_label": classify_range_by_atr(prev_range_atr),
        "prev_close_position": prev_close_position,
        "prev_close_position_label": classify_close_position(prev_close_position),
        "prev_volume": prev_volume,
        "prev_vol_ratio": prev_vol_ratio,
        "prev_session_judgement": prev_session_judgement,
        "prev_evaluation": prev_evaluation,
        "ma25_distance": ma25_distance,
        "ma25_distance_atr": ma25_distance_atr,
        "recent5_high": recent5_high,
        "recent5_high_distance": recent5_high_distance,
        "recent5_high_distance_pct": recent5_high_distance_pct,
        "recent20_high": recent20_high,
        "recent20_high_distance": recent20_high_distance,
        "recent20_high_distance_pct": recent20_high_distance_pct,
        "volume": volume_now,
        "vol_ratio": vol_ratio,
        "prev_candle": infer_candle(prev_open, prev_close),
        "today_candle": infer_candle(open_price, latest),
        "trend": infer_trend(latest, ma5, ma25, ma25_prev5),
        "error": None,
    }



def render_market_block(market):
    lines = ["■市況"]
    for key in ["WTI", "銅", "NASDAQ"]:
        item = market.get(key, {})
        lines.append(f"{key}：{fmt_price(item.get('latest'))}（{fmt_pct(item.get('change_pct'))} / {item.get('trend', 'N/A')}）")
    return "\n".join(lines)



def render_stock_block(stock, include_market: bool, market_block: str) -> str:
    if stock.get("error"):
        return f"【銘柄】{stock['name']} ({stock['code']})\n\n取得失敗：{stock['error']}"

    lines = [
        f"【銘柄】{stock['name']} ({stock['code']})",
        f"データ日：{stock['date']} / 取得時刻：{stock.get('acquired_at', 'N/A')}",
        "",
        "■現在位置",
        f"現在値({stock.get('latest_bar_time', 'N/A')})：{fmt_price(stock['latest'])}（前日比 {fmt_pct(stock['day_change_pct'])}）",
        f"前日終値：{fmt_price(stock['prev_close'])}",
        "",
        "■当日レンジ・位置",
        f"O/H/L/C：{fmt_ohlc(stock['open'], stock['high'], stock['low'], stock['latest'])}",
        f"当日値幅：{fmt_price(stock['day_range'])}（ATR比 {fmt_multiple(stock['day_range_atr'])} / {stock['day_range_label']}）",
        f"終端位置：{fmt_close_position(stock.get('day_close_position'), stock.get('day_close_position_label', 'N/A'))}",
        "",
        "■当日テクニカル",
        f"VWAP：{fmt_vwap_position(stock['latest'], stock['vwap'])}",
        f"5日線：{fmt_price(stock['ma5'])}（乖離 {fmt_pct(stock['dev5'])}）",
        f"25日線：{fmt_price(stock['ma25'])}（乖離 {fmt_pct(stock['dev25'])} / 距離 {fmt_price_diff(stock['ma25_distance'])} / ATR比 {fmt_multiple(stock['ma25_distance_atr'])}）",
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
        "■節目・ブレイクライン",
        f"前日高値：{fmt_price(stock['prev_high'])}",
        f"直近5日高値：{fmt_price(stock['recent5_high'])}（現在値との差 {fmt_price_diff(stock['recent5_high_distance'])} / {fmt_pct(stock['recent5_high_distance_pct'])}）",
        f"直近20日高値：{fmt_price(stock['recent20_high'])}（現在値との差 {fmt_price_diff(stock['recent20_high_distance'])} / {fmt_pct(stock['recent20_high_distance_pct'])}）",
        "",
        "■流れ",
        f"直近トレンド：{stock['trend']}",
    ]
    if include_market:
        lines.extend(["", market_block])
    return "\n".join(lines)


class StockEntryPromptApp:
    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.title("株式エントリー相談テキスト生成")
        self.master.geometry("980x760")

        self.watchlist_path: Path | None = None
        self.watchlist: list[tuple[str, str]] = []
        self.market_cache: str = ""

        self.path_var = tk.StringVar(value="監視銘柄ファイル未選択")
        self.stock_var = tk.StringVar()
        self.include_market_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="監視銘柄ファイルを読み込んでください。")

        self.display_to_code: dict[str, tuple[str, str]] = {}

        self._build_ui()

    def _build_ui(self):
        root = ttk.Frame(self.master, padding=10)
        root.pack(fill="both", expand=True)

        top = ttk.Frame(root)
        top.pack(fill="x", pady=(0, 8))

        ttk.Button(top, text="監視銘柄ファイルを開く", command=self.open_watchlist).pack(side="left")
        ttk.Label(top, textvariable=self.path_var).pack(side="left", padx=10, fill="x", expand=True)

        control = ttk.Frame(root)
        control.pack(fill="x", pady=(0, 8))

        ttk.Label(control, text="銘柄選択").pack(side="left")
        self.stock_combo = ttk.Combobox(control, textvariable=self.stock_var, state="readonly", width=40)
        self.stock_combo.pack(side="left", padx=(8, 12))
        self.stock_combo.bind("<<ComboboxSelected>>", self.on_stock_selected)

        ttk.Checkbutton(control, text="WTI・銅・NASDAQを付ける", variable=self.include_market_var).pack(side="left", padx=(0, 12))
        ttk.Button(control, text="生成", command=self.generate_text).pack(side="left", padx=(0, 6))
        ttk.Button(control, text="コピー", command=self.copy_text).pack(side="left", padx=(0, 6))
        ttk.Button(control, text="保存", command=self.save_text).pack(side="left")

        ttk.Label(root, textvariable=self.status_var).pack(fill="x", pady=(0, 6))

        text_frame = ttk.Frame(root)
        text_frame.pack(fill="both", expand=True)

        self.text = tk.Text(text_frame, wrap="word", font=("Yu Gothic UI", 11))
        self.text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.text.yview)
        scroll.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scroll.set)

    def open_watchlist(self):
        path = filedialog.askopenfilename(
            title="監視銘柄ファイルを選択",
            filetypes=[("Markdown/Text", "*.md *.txt"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            watchlist = load_watchlist(Path(path))
        except Exception as exc:
            messagebox.showerror("読込失敗", str(exc))
            return

        self.watchlist_path = Path(path)
        self.watchlist = watchlist
        self.path_var.set(str(self.watchlist_path))

        values = []
        self.display_to_code.clear()
        for name, code in self.watchlist:
            label = f"{name} ({code})"
            values.append(label)
            self.display_to_code[label] = (name, code)

        self.stock_combo["values"] = values
        if values:
            self.stock_var.set(values[0])
            self.status_var.set(f"{len(values)}銘柄を読み込みました。銘柄を選んで生成してください。")
            self.generate_text()
        else:
            self.stock_var.set("")
            self.text.delete("1.0", tk.END)
            self.status_var.set("銘柄が見つかりませんでした。")

    def on_stock_selected(self, _event=None):
        self.generate_text()

    def selected_stock(self) -> tuple[str, str] | None:
        label = self.stock_var.get().strip()
        if not label:
            return None
        return self.display_to_code.get(label)

    def generate_text(self):
        selected = self.selected_stock()
        if selected is None:
            self.status_var.set("先に監視銘柄ファイルと銘柄を選んでください。")
            return

        name, code = selected
        self.status_var.set(f"取得中: {name} ({code})")
        self.master.update_idletasks()

        try:
            market_block = ""
            if self.include_market_var.get():
                market_block = render_market_block(fetch_market_snapshot())

            stock = analyze_stock(name, code)
            output = render_stock_block(stock, self.include_market_var.get(), market_block)
        except Exception as exc:
            messagebox.showerror("生成失敗", str(exc))
            self.status_var.set("生成に失敗しました。")
            return

        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", output)
        self.status_var.set(f"生成完了: {name} ({code})")

    def copy_text(self):
        content = self.text.get("1.0", tk.END).strip()
        if not content:
            self.status_var.set("コピーするテキストがありません。")
            return
        self.master.clipboard_clear()
        self.master.clipboard_append(content)
        self.status_var.set("クリップボードにコピーしました。")

    def save_text(self):
        content = self.text.get("1.0", tk.END).strip()
        if not content:
            self.status_var.set("保存するテキストがありません。")
            return

        selected = self.selected_stock()
        default_name = "stock_entry_prompt.txt"
        if selected is not None:
            _, code = selected
            default_name = f"stock_entry_prompt_{code}.txt"

        initial_dir = str(self.watchlist_path.parent) if self.watchlist_path else str(Path.cwd())
        path = filedialog.asksaveasfilename(
            title="保存先を選択",
            defaultextension=".txt",
            initialdir=initial_dir,
            initialfile=default_name,
            filetypes=[("Text files", "*.txt"), ("Markdown files", "*.md"), ("All files", "*.*")],
        )
        if not path:
            return

        Path(path).write_text(content + "\n", encoding="utf-8")
        self.status_var.set(f"保存完了: {path}")



def main():
    root = tk.Tk()
    app = StockEntryPromptApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
