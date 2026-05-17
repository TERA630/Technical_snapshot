from __future__ import annotations

import pandas as pd
import yfinance as yf

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


def fetch_intraday_vwap(code: str, interval: str = "5m"):
    symbol = f"{code}.T"
    df = yf.download(symbol, period="1d", interval=interval, progress=False, auto_adjust=False)

    if df is None or df.empty:
        return None, pd.DataFrame()

    df = df.dropna().copy()

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    required_cols = {"Open", "High", "Low", "Close", "Volume"}
    if not required_cols.issubset(set(df.columns)):
        return None, df

    df = df[df["Volume"].fillna(0) > 0].copy()
    if df.empty:
        return None, pd.DataFrame()

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


def fetch_history(symbol: str, period: str = "4mo", interval: str = "1d") -> pd.DataFrame:
    df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df


def fetch_market_snapshot(infer_trend_func):
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
        trend = infer_trend_func(latest, ma5, ma25, None) if ma5 is not None else "N/A"
        change_pct = None if latest in (None, 0) or prev in (None, 0) else (latest / prev - 1.0) * 100
        out[name] = {"latest": latest, "change_pct": change_pct, "trend": trend}
    return out


def fetch_valuation_snapshot(code: str) -> dict:
    symbol = f"{code}.T"
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}

    trailing_eps = safe_float(info.get("trailingEps"))
    forward_eps = safe_float(info.get("forwardEps"))
    trailing_pe = safe_float(info.get("trailingPE"))
    forward_pe = safe_float(info.get("forwardPE"))

    eps_fy0 = None
    eps_fy1 = None
    try:
        estimates = ticker.get_earnings_estimate()
        if estimates is not None and not estimates.empty:
            if "avg" in estimates.columns:
                if "0y" in estimates.index:
                    eps_fy0 = safe_float(estimates.loc["0y", "avg"])
                if "+1y" in estimates.index:
                    eps_fy1 = safe_float(estimates.loc["+1y", "avg"])
    except Exception:
        pass

    return {
        "eps_actual": trailing_eps,
        "eps_fy0": eps_fy0 if eps_fy0 is not None else forward_eps,
        "eps_fy1": eps_fy1,
        "per_actual": trailing_pe,
        "per_forward": forward_pe,
    }


def calc_margin_ratio(operating_income, total_revenue):
    if operating_income is None or total_revenue in (None, 0):
        return None
    return (operating_income / total_revenue) * 100


def fetch_profitability_snapshot(code: str) -> dict:
    symbol = f"{code}.T"
    ticker = yf.Ticker(symbol)
    info = ticker.info or {}

    roe_actual = safe_float(info.get("returnOnEquity"))
    if roe_actual is not None and roe_actual <= 1:
        roe_actual *= 100

    # NOTE:
    # yfinance.get_earnings_estimate() is EPS-oriented (per-share estimate),
    # and must not be treated as operating income.
    # To avoid mixing units, operating income forecast is kept as None unless
    # a reliable operating-income source is introduced.
    op_income_fy0 = None
    op_income_fy1 = None
    revenue_fy0 = None
    revenue_fy1 = None

    try:
        rev_est = ticker.get_revenue_estimate()
        if rev_est is not None and not rev_est.empty and "avg" in rev_est.columns:
            if "0y" in rev_est.index:
                revenue_fy0 = safe_float(rev_est.loc["0y", "avg"])
            if "+1y" in rev_est.index:
                revenue_fy1 = safe_float(rev_est.loc["+1y", "avg"])
    except Exception:
        pass

    op_margin_fy0 = calc_margin_ratio(op_income_fy0, revenue_fy0)
    op_margin_fy1 = calc_margin_ratio(op_income_fy1, revenue_fy1)

    return {
        "roe_actual": roe_actual,
        "roe_fy0": None,
        "roe_fy1": None,
        "op_income_fy0": op_income_fy0,
        "op_income_fy1": op_income_fy1,
        "revenue_fy0": revenue_fy0,
        "revenue_fy1": revenue_fy1,
        "op_margin_fy0": op_margin_fy0,
        "op_margin_fy1": op_margin_fy1,
    }
