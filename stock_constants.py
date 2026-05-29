from __future__ import annotations

ENCODING = "utf-8"
TIMEZONE = "Asia/Tokyo"
NA_TEXT = "N/A"
LOG_DIR = "Logs"
LOG_FILE = "stock_snapshot.log"

RSI_PERIOD = 14
ATR_PERIOD = 14

MARKET_SYMBOLS = {
    "WTI": "CL=F",
    "銅": "HG=F",
    "NASDAQ": "^IXIC",
}
MARKET_DISPLAY_ORDER = ("WTI", "銅", "NASDAQ")

SECTION_TITLES = {
    "market": "■市況",
    "today_range": "■当日位置・レンジ",
    "technical": "■移動平均・出来高",
    "prev_evaluation": "■前日評価",
    "fundamentals": "■ファンダメンタル",
    "breakline": "■節目・ブレイクライン",
    "trend": "■流れ",
}

DISPLAY_LABELS = {
    "stock": "銘柄",
    "fetch_failed": "取得失敗",
    "current_price": "現在値",
    "prev_day_change": "前日比",
    "ohlc": "O/H/L/C",
    "day_range": "当日値幅",
    "atr_ratio": "ATR比",
    "close_position": "終端位置",
    "actual": "実績",
    "fy0_forecast": "今期末予想",
    "fy1_forecast": "来期予想",
    "vwap": "VWAP",
    "ma5": "5日線",
    "ma25": "25日線",
    "deviation": "乖離",
    "distance": "距離",
    "atr14": "14日ATR",
    "rsi": "RSI",
    "volume": "出来高",
    "vol_avg20_ratio": "20日平均比",
    "prev_close": "前日終値",
    "prev_hlc": "前日H/L/C",
    "candle": "ローソク",
    "prev_session_judgement": "押し判定",
    "overall_evaluation": "総合評価",
    "actual_roe": "年実績ROE",
    "actual_op_margin": "年実績営業利益率",
    "actual_op_growth": "年実績営業成長率",
    "prev_high": "前日高値",
    "recent5_high": "直近5日高値",
    "recent20_high": "直近20日高値",
    "recent60_high": "60日高値",
    "recent60_low": "60日安値",
    "current_range": "現在レンジ",
    "current_diff": "現在値との差",
    "recent_trend": "直近トレンド",
}

ERROR_MESSAGES = {
    "insufficient_price_data": "価格データ不足",
    "watchlist_parse_failed": "監視銘柄ファイルから '銘柄名 (4桁コード)' を抽出できませんでした。",
}

DIAGNOSTIC_CATEGORIES = {
    "external_api_failure": "外部API失敗",
    "data_missing": "データ欠損",
    "column_missing": "列名変更/列不足",
    "division_by_zero": "ゼロ除算",
    "out_of_scope": "取得対象外",
}

UNIT_LABELS = {
    "shares": "株",
    "multiple": "倍",
    "yen": "円",
    "percent_jp": "％",
    "closing_price": "終値",
}

PRICE_SOURCE_LABELS = {
    "intraday": "intraday_5m",
    "daily_close": "daily_close",
}

VWAP_SOURCE_LABELS = {
    "intraday": "本日5分足",
    "daily_typical": "日足参考値",
}

RANGE_ATR_LABELS = {
    "narrow": "浅い値幅",
    "normal": "通常値幅",
    "wide": "大きめ",
    "expanded": "急拡大",
}

CLOSE_POSITION_LABELS = {
    "high": "高値圏で終了",
    "middle": "中段で終了",
    "low": "安値圏で終了",
}

RANGE_ZONE_LABELS = {
    "high": "高値圏",
    "middle": "中段",
    "low": "安値圏",
}

SESSION_LABELS = {
    "unavailable": "判定不可",
    "collapse": "崩れ",
    "pullback": "押し",
    "neutral": "中立",
    "strong_rise": "強い上昇",
    "weak_rise": "弱い上昇",
}

CANDLE_LABELS = {
    "bullish": "陽線",
    "bearish": "陰線",
    "doji": "十字線",
}

WICK_SHAPE_LABELS = {
    "small_move": "小動き",
    "large_body": "実体大きめ",
    "long_lower_wick": "下ヒゲ長め",
    "long_upper_wick": "上ヒゲ長め",
    "small_doji_like": "小動き・十字線気味",
    "normal": "通常足",
}

TREND_LABELS = {
    "up": "上昇トレンド",
    "down": "下落トレンド",
    "mixed": "もみ合い / 戻り局面",
}

RANGE_ATR_THRESHOLDS = {
    "narrow": 0.5,
    "normal": 1.0,
    "wide": 1.5,
}

CLOSE_POSITION_THRESHOLDS = {
    "high": 0.60,
    "middle": 0.30,
}

RANGE_ZONE_THRESHOLDS = {
    "high": 0.60,
    "middle": 0.30,
}

PREV_SESSION_THRESHOLDS = {
    "collapse_range_atr": 1.30,
    "collapse_close_position": 0.30,
    "collapse_volume_ratio": 20,
    "large_collapse_range_atr": 1.50,
    "large_collapse_close_position": 0.40,
    "pullback_range_atr_min": 0.50,
    "pullback_range_atr_max": 1.20,
    "pullback_close_position": 0.45,
    "pullback_volume_ratio": 20,
    "strong_rise_close_position": 0.60,
    "strong_rise_range_atr": 1.20,
    "strong_rise_volume_ratio": -30,
    "weak_rise_close_position": 0.50,
    "long_lower_wick_range_atr": 1.30,
}

WICK_SHAPE_THRESHOLDS = {
    "large_body_ratio": 0.65,
    "long_wick_ratio": 0.40,
    "long_wick_body_multiple": 1.5,
    "small_body_ratio": 0.20,
}

STATEMENT_ROW_KEYS = {
    "operating_income": ("Operating Income", "OperatingIncome"),
    "total_revenue": ("Total Revenue", "TotalRevenue", "Revenue"),
}
