# 株価取得・指標作成・表示エンジン移植仕様書

## 1. 位置づけ

本書を、現行プログラムの株価取得・指標作成・表示エンジンに関する正本仕様とする。


## 2. 対象ファイル

| ファイル | 役割 |
|---|---|
| `stock_constants.py` | 表示文言、評価ラベル、しきい値、市況シンボル、文字コード、診断カテゴリ |
| `stock_types.py` | Python向け `TypedDict`、階層snapshot型、flatからstructuredへの変換 |
| `stock_logging.py` | 取得ログを `Logs/stock_snapshot.log` に残す設定 |
| `data_layer.py` | yfinanceから外部データを取得し、Python値へ正規化 |
| `domain_layer.py` | 指標算出、評価ラベル作成、flat/structured snapshot API |
| `presentation_layer.py` | flat snapshotを固定フォーマットの日本語テキストへ変換 |
| `technical_snap.py` | Tkinter GUI |
| `tests/test_domain_and_data.py` | 外部APIに依存しない固定データテスト |
| `Samples/` | 移植比較用サンプル |

## 3. 公開API

### 3.1 現行互換API

```python
from domain_layer import StockInput, get_stock_snapshot

flat = get_stock_snapshot(StockInput(name="トヨタ自動車", code="7203"))
```

`get_stock_snapshot()` は現行表示層と互換性があるflat辞書を返す。

### 3.2 移植推奨API

```python
from domain_layer import StockInput, get_structured_stock_snapshot

snapshot = get_structured_stock_snapshot(StockInput(name="トヨタ自動車", code="7203"))
```

`get_structured_stock_snapshot()` は保守性重視の階層snapshotを返す。Python移植先ではこのAPIを優先して使う。

### 3.3 表示API

```python
from presentation_layer import render_stock_block

text = render_stock_block(flat, include_market=True, market_block=market_block)
```

現行表示層はflat snapshotを入力とする。structured snapshotを直接表示する場合は、移植先で専用rendererを作る。

## 4. 入力仕様

### 4.1 銘柄入力

| 項目 | 型 | 内容 |
|---|---|---|
| `name` | string | 表示用銘柄名 |
| `code` | string | 東証4桁コード。例: `7203` |

yfinanceの株価取得シンボルは `{code}.T` とする。

### 4.2 監視銘柄ファイル

`presentation_layer.load_watchlist()` はMarkdownまたはテキストから銘柄を抽出する。

- 想定形式: `銘柄名 (1234)` または箇条書き内の同等表記
- コードは4桁数字のみ対象
- 同一コードが複数回出た場合は初出のみ採用
- 抽出できない場合は `ERROR_MESSAGES["watchlist_parse_failed"]`
- 通常読み込みはUTF-8、BOM付きUTF-8は `utf-8-sig` fallback

## 5. データ取得仕様

### 5.1 共通

- 外部取得元は `yfinance`
- 数値正規化は `safe_float()`
- `None`、NaN、変換不能値は `None`
- 表示層では `None`、NaN、inf を `N/A`
- 任意データの取得失敗は全体を落とさず `diagnostics` に記録
- 日足価格が不足する場合のみ `error = "価格データ不足"`
- 取得処理の実行時刻は `acquired_at`
- 取得した現在値が何時点の価格かは `latest_price_timestamp`
- 価格の由来は `latest_price_source`

### 5.2 日足価格

| 項目 | 仕様 |
|---|---|
| 関数 | `fetch_history(symbol, period="4mo", interval="1d")` |
| API | `yf.Ticker(symbol).history(auto_adjust=False)` |
| 現行利用 | `{code}.T`, `period="4mo"` |
| 必須列 | `Open`, `High`, `Low`, `Close`, `Volume` |
| 最低件数 | 欠損除去後30件以上 |
| index | timezone除去済みdatetime |

### 5.3 日中足/VWAP

| 項目 | 仕様 |
|---|---|
| 関数 | `fetch_intraday_vwap(code, interval="5m")` |
| API | `yf.download("{code}.T", period="1d", interval="5m", auto_adjust=False)` |
| 必須列 | `Open`, `High`, `Low`, `Close`, `Volume` |
| 除外条件 | Volumeが0または欠損の足を除外 |

VWAP:

```text
TypicalPrice = (High + Low + Close) / 3
VWAP = cumsum(TypicalPrice * Volume) / cumsum(Volume)
```

日中足が取れない場合:

- 現在値、O/H/L、出来高は日足ベース
- `latest_bar_time` は `終値`
- `latest_price_source` は `daily_close`
- `latest_price_timestamp` は `{日足日付} 終値`
- VWAPは日足の `(High + Low + Close) / 3`
- `vwap_source` は `日足参考値`
- `vwap_timestamp` は `{日足日付} 終値`
- `diagnostics` に `field="intraday"` を記録

日中足が取れた場合:

- VWAPは本日5分足の価格と出来高から計算
- `vwap_source` は `本日5分足`
- `vwap_timestamp` は `{日足日付} {latest_bar_time}`

### 5.4 市況

| 表示名 | yfinance symbol |
|---|---|
| WTI | `CL=F` |
| 銅 | `HG=F` |
| NASDAQ | `^IXIC` |

取得仕様:

- `fetch_history(symbol, period="10d")`
- 終値2本未満なら `latest=None`, `change_pct=None`, `trend="N/A"`
- 騰落率は `latest / prev_close - 1`
- 5日移動平均が取れる場合のみ `grade_trend()`

### 5.5 PER/EPS

関数: `fetch_valuation_snapshot(code)`

| key | 取得元/算出 |
|---|---|
| `eps_actual` | `ticker.info["trailingEps"]` |
| `eps_fy0` | `get_earnings_estimate()` の `0y / avg`。なければ `forwardEps` |
| `eps_fy1` | `get_earnings_estimate()` の `+1y / avg` |
| `per_actual` | `ticker.info["trailingPE"]` |
| `per_forward` | `ticker.info["forwardPE"]` |

ドメイン層:

- `per_fy0 = latest / eps_fy0`
- `eps_fy0` がない場合は `per_forward`
- `per_fy1 = latest / eps_fy1`
- EPSが `None` または0以下の場合、算出PERは `None`

### 5.6 収益性

関数: `fetch_profitability_snapshot(code)`

| key | 取得元/算出 |
|---|---|
| `roe_actual` | `ticker.info["returnOnEquity"]`。1以下なら百分率へ変換 |
| `op_margin_actual` | 年次損益計算書の `Operating Income / Total Revenue * 100` |
| `op_growth_actual` | `最新Operating Income / 前期Operating Income - 1` の百分率 |

今期末予想営業利益率は、現状のyfinance標準取得では営業利益予想値を安定取得できないため、表示・ドメインsnapshotの対象外とする。

年次損益計算書は `ticker.income_stmt` を優先し、空なら `ticker.financials` をfallbackとする。

行名:

- 営業利益: `Operating Income`, `OperatingIncome`
- 売上高: `Total Revenue`, `TotalRevenue`, `Revenue`

## 6. 指標作成仕様

### 6.1 移動平均

| key | 式 |
|---|---|
| `ma5` | `Close.rolling(5).mean()` |
| `ma25` | `Close.rolling(25).mean()` |
| `ma25_prev5` | 5営業日前の25日移動平均。30件以上の場合のみ |
| `dev5` | `latest / ma5 - 1` の百分率 |
| `dev25` | `latest / ma25 - 1` の百分率 |

### 6.2 RSI

期間は14。

```text
delta = Close.diff()
gain = delta.clip(lower=0)
loss = -delta.clip(upper=0)
avg_gain = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
avg_loss = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
RSI = 100 - 100 / (1 + avg_gain / avg_loss)
```

### 6.3 ATR

期間は14。True Rangeは以下の最大値。

- `High - Low`
- `abs(High - prev Close)`
- `abs(Low - prev Close)`

```text
ATR14 = TrueRange.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
```

### 6.4 当日レンジ

| key | 式 |
|---|---|
| `day_change_price` | `latest - prev_close` |
| `day_change_pct` | `latest / prev_close - 1` の百分率 |
| `day_range` | `high - low` |
| `day_range_atr` | `day_range / atr14` |
| `day_close_position` | `(latest - low) / (high - low)` |
| `ma25_distance` | `latest - ma25` |
| `ma25_distance_atr` | `(latest - ma25) / atr14` |

### 6.5 前日評価

前日足は日足履歴の末尾から2本目を使う。

| key | 式 |
|---|---|
| `prev_change_pct` | `prev_close / prev_prev_close - 1` の百分率 |
| `prev_range` | `prev_high - prev_low` |
| `prev_range_atr` | `prev_range / atr14` |
| `prev_close_position` | `(prev_close - prev_low) / (prev_high - prev_low)` |
| `prev_vol_ratio` | `prev_volume / prev_vol_avg20 - 1` の百分率 |

ローソク:

| 条件 | ラベル |
|---|---|
| `close > open` | 陽線 |
| `close < open` | 陰線 |
| その他 | 十字線 |

形状:

| 条件 | ラベル |
|---|---|
| 日中値幅が0以下 | 小動き |
| 実体 / 値幅 >= 0.65 | 実体大きめ |
| 下ヒゲ / 値幅 >= 0.40 かつ 下ヒゲ >= 実体 * 1.5 | 下ヒゲ長め |
| 上ヒゲ / 値幅 >= 0.40 かつ 上ヒゲ >= 実体 * 1.5 | 上ヒゲ長め |
| 実体 / 値幅 <= 0.20 | 小動き・十字線気味 |
| その他 | 通常足 |

押し判定:

| 条件 | ラベル |
|---|---|
| `prev_range_atr` または `prev_close_position` 欠損 | 判定不可 |
| `prev_range_atr >= 1.30` かつ `close_position <= 0.30` かつ `prev_vol_ratio >= 20` | 崩れ |
| `prev_range_atr >= 1.50` かつ `close_position <= 0.40` | 崩れ |
| `0.50 <= prev_range_atr <= 1.20` かつ `close_position >= 0.45` かつ `prev_vol_ratio <= 20` | 押し |
| その他 | 中立 |

### 6.6 節目

当日を含めず `shift(1)` した日足から算出する。

| key | 式 |
|---|---|
| `recent5_high` | 直近5営業日のHigh最大 |
| `recent20_high` | 直近20営業日のHigh最大 |
| `recent60_high` | 直近60営業日のHigh最大 |
| `recent60_low` | 直近60営業日のLow最小 |
| `recent*_high_distance` | `latest - recent*_high` |
| `recent*_high_distance_pct` | `latest / recent*_high - 1` の百分率 |
| `recent60_range_position` | `(latest - recent60_low) / (recent60_high - recent60_low)` |

## 7. ラベル仕様

| 種別 | 条件 | ラベル |
|---|---|---|
| 値幅ATR比 | `< 0.5` | 浅い値幅 |
| 値幅ATR比 | `< 1.0` | 通常値幅 |
| 値幅ATR比 | `< 1.5` | 大きめ |
| 値幅ATR比 | `>= 1.5` | 急拡大 |
| 終端位置 | `>= 0.60` | 高値圏で終了 |
| 終端位置 | `>= 0.30` | 中段で終了 |
| 終端位置 | `< 0.30` | 安値圏で終了 |
| 60日レンジ | `>= 0.60` | 高値圏 |
| 60日レンジ | `>= 0.30` | 中段 |
| 60日レンジ | `< 0.30` | 安値圏 |
| トレンド | `latest > ma5 > ma25` かつ `ma25 > ma25_prev5` | 上昇トレンド |
| トレンド | `latest < ma5 < ma25` | 下落トレンド |
| トレンド | その他 | もみ合い / 戻り局面 |

欠損、NaN、infの場合は `N/A`。

## 8. Snapshot仕様

### 8.1 flat snapshot

`get_stock_snapshot()` は現行表示互換のflat辞書を返す。主な分類は以下。

| 分類 | key例 |
|---|---|
| 銘柄 | `name`, `code`, `date`, `acquired_at`, `error`, `diagnostics` |
| 先頭サマリ | `summary_trend_symbol`, `summary_trend_label` |
| 当日価格 | `latest_bar_time`, `latest_price_source`, `latest_price_timestamp`, `open`, `high`, `low`, `latest`, `day_change_price`, `day_change_pct`, `volume` |
| VWAP | `vwap`, `vwap_diff`, `vwap_source`, `vwap_timestamp` |
| テクニカル | `ma5`, `dev5`, `ma25`, `dev25`, `rsi`, `atr14`, `trend` |
| 前日 | `prev_close`, `prev_candle`, `prev_wick_shape`, `prev_evaluation` |
| 節目 | `recent5_high`, `recent20_high`, `recent60_high`, `recent60_low` |
| PER/EPS | `per_actual`, `per_fy0`, `per_fy1`, `eps_actual`, `eps_fy0`, `eps_fy1` |
| 収益性 | `roe_actual`, `op_margin_actual`, `op_growth_actual` |

### 8.2 structured snapshot

`get_structured_stock_snapshot()` は `stock_types.StructuredStockSnapshot` を返す。

| key | 内容 |
|---|---|
| `identity` | 銘柄名、コード、取得日、エラー |
| `summary` | 先頭サマリ用のトレンド記号、短縮ラベル |
| `price` | 当日価格、現在値、出来高、価格時点、価格ソース |
| `vwap` | VWAP、VWAP差分率、VWAP由来、VWAP時点 |
| `technical` | MA、RSI、ATR、トレンド |
| `range` | 当日レンジ、終端位置、25日線距離 |
| `previous_session` | 前日価格、ローソク、押し判定、総合評価 |
| `breakline` | 直近高値、60日レンジ |
| `valuation` | PER/EPS |
| `profitability` | ROE、営業利益率、営業成長率 |
| `diagnostics` | 内部診断情報 |

flatからstructuredへの変換は `stock_types.to_structured_snapshot()`。

## 9. Diagnostics/ログ仕様

`get_stock_snapshot()` と `get_structured_stock_snapshot()` は診断情報を `diagnostics` に持つ。

形式:

```python
{
    "category": "外部API失敗",
    "field": "valuation",
    "message": "valuation unavailable",
}
```

カテゴリ:

- 外部API失敗
- データ欠損
- 列名変更/列不足
- ゼロ除算
- 取得対象外

診断情報は表示テキストには出さず、`domain_layer` loggerへwarning出力する。

通常の取得成功/失敗ログも `domain_layer` loggerへinfo出力する。GUI起動時は `technical_snap.py` が `setup_stock_logging()` を呼び、`Logs/stock_snapshot.log` に以下を残す。

- 銘柄名
- コード
- 取得処理時刻 `acquired_at`
- 現在値 `latest`
- 価格ソース `latest_price_source`
- 価格時点 `latest_price_timestamp`
- VWAP由来 `vwap_source`
- VWAP時点 `vwap_timestamp`
- エラー有無
- diagnostics件数

## 10. 表示仕様

### 10.1 基本整形

| 関数 | 仕様 |
|---|---|
| `fmt_price` | `1,234.56`。欠損は `N/A` |
| `fmt_price_current` | 1000以上は小数なし、1000未満は小数1桁 |
| `fmt_price_diff` | 符号付き、カンマ、小数2桁 |
| `fmt_pct` | 符号付き、小数2桁、`%` |
| `fmt_pct_plain` | 符号なし、小数1桁、`%` |
| `fmt_pct_jp` | 符号付き、小数2桁、`％` |
| `fmt_pct_no_sign_jp` | 符号なし、小数2桁、`％` |
| `fmt_volume` | カンマ区切り整数 + `株` |
| `fmt_multiple` | 小数2桁 + `倍` |
| `fmt_per` | 小数1桁 + `倍` |
| `fmt_eps` | 小数なし + `円` |

### 10.2 先頭サマリ

目的は、銘柄ごとの現在位置、短期方向、VWAP・25日線からの距離、RSI、60日レンジ位置を冒頭で一目確認できるようにすること。

表示位置は銘柄見出しの直後、既存の `■当日位置・レンジ` より前とする。既存の詳細ブロックは削除せず、先頭サマリは詳細ブロックの要約として追加する。

ドメイン層は先頭サマリ用に、前日比の円差 `day_change_price` とトレンド短縮表示 `summary_trend_symbol` / `summary_trend_label` をsnapshotに追加する。数値の小数桁、括弧、円・%などの表示整形はpresentation層で行う。

表示テンプレート:

```text
【銘柄】{name} ({code})
株価：{latest}円（前日比{day_change_price}円：{day_change_pct}） ({latest_price_timestamp} 時点)   終端位置({day_close_position}:{day_close_position_label})
トレンド　{trend_symbol} {trend_short}
VWAP　　{vwap_diff_pct} ({vwap_diff_price}円)
位置　　　25日線 {dev25}（ATR比：{ma25_distance_atr}）
RSI　　　{rsi}

60日レンジ位置 {recent60_range_position}（{recent60_range_zone}）
```

項目仕様:

| 表示項目 | snapshot key / 算出 | 表示仕様 |
|---|---|---|
| 銘柄 | `name`, `code` | 既存見出し `【銘柄】{name} ({code})` を使う |
| 株価 | `latest`, `latest_price_timestamp` | `株価：{latest}円`。価格は `fmt_price_current()` + `円`。時点は `latest_price_timestamp` をそのまま表示 |
| 前日比 | `day_change_price`, `day_change_pct` | `（前日比{day_change_price}円：{day_change_pct}）`。価格差は符号付き円、率は符号付き・小数1桁の `%` |
| 終端位置 | `day_close_position`, `day_close_position_label` | 比率は `day_close_position * 100` を小数1桁の `%`。ラベルは既存ラベルをそのまま使う |
| トレンド | `summary_trend_symbol`, `summary_trend_label` | 記号 + 短縮ラベルで表示 |
| VWAP | `vwap_diff`, `latest - vwap` | 左にVWAP乖離率、括弧内に価格差。価格差は符号付き、`円`付き |
| 位置 | `dev25`, `ma25_distance_atr` | `25日線 {dev25}（ATR比：{ma25_distance_atr}）`。ATR比は小数1桁を基本とする |
| RSI | `rsi` | 小数1桁 |
| 60日レンジ位置 | `recent60_range_position`, `recent60_range_zone` | `recent60_range_position * 100` を小数1桁の `%`。ゾーンラベルを括弧で併記 |

トレンド短縮ラベル:

| 元ラベル | 先頭サマリ表示 |
|---|---|
| 上昇トレンド | ↑ 上昇 |
| 下落トレンド | ↓ 下落 |
| もみ合い / 戻り局面 | → もみ合い |

終端位置ラベルは既存ラベルを維持する。

| 元ラベル | 先頭サマリ表示 |
|---|---|
| 高値圏で終了 | 高値圏で終了 |
| 中段で終了 | 中段で終了 |
| 安値圏で終了 | 安値圏で終了 |

欠損時:

- 数値が欠損、NaN、infの場合は該当箇所を `N/A` とする。
- VWAPが欠損する場合は `VWAP　　N/A` とし、価格差も表示しない。
- 25日線またはATRが欠損する場合は、取得できる値だけ表示し、不足部分を `N/A` とする。
- 60日レンジの高値・安値が同値、または算出不能の場合は `60日レンジ位置 N/A` とする。

例:

```text
【ダイセキ (9793)】
株価：3904円（前日比+120円：+x.x%） (20xx/xx/xx xx:xx 時点)   終端位置(0.0%:安値圏で終了)
トレンド　↓ 下落
VWAP　　-1.13% (-xxx円)
位置　　　25日線 -4.24%（ATR比：x.x）
RSI　　　xx.x

60日レンジ位置 xx.x%（安値圏）
```

VWAPの括弧内の価格差は、既存の `latest - vwap` と同じ符号にする。つまり現在値がVWAPより下ならマイナス。

### 10.3 当日テクニカルブロック

先頭サマリへの移動に伴い、既存の `■当日テクニカル` から `VWAP` と `RSI` の行は削除する。

`■当日テクニカル` に残す項目:

- 5日線
- 25日線
- 14日ATR
- 出来高

`VWAP`、`RSI` は先頭サマリのみで表示する。算出自体はsnapshotに残し、表示責務だけを先頭サマリへ移す。

### 10.4 ファンダメンタルブロック

`■ファンダメンタル` に表示する項目:

- ROE
- 営業利益率
- 営業成長率

配当利回りは表示しない。ドメイン・structured snapshotにも配当利回り項目は持たせない。

### 10.5 表示順

1. `【銘柄】{name} ({code})`
2. 先頭サマリ
3. `■当日位置・レンジ`
4. PER/EPS
5. `■当日テクニカル`
6. `■前日評価`
7. `■ファンダメンタル`
8. `■節目・ブレイクライン`
9. `■流れ`
10. 任意で `■市況`

### 10.6 市況ブロック

市況ブロックはチェック有効時のみ末尾に追加する。表示順は WTI、銅、NASDAQ。

```text
{name}：{latest}（{change_pct} / {trend}）
```

## 11. テスト仕様

テストは `tests/test_domain_and_data.py` に集約する。外部APIに依存しない固定データを使う。

実行:

```powershell
python -m unittest discover -s tests -v
```

検証対象:

- 日中VWAP
- ATR14
- RSI14
- 終端位置
- 値幅ATR比ラベル
- 前日押し判定
- トレンド判定
- PER/EPS fallback
- 欠損時の `N/A`
- 任意データ取得失敗時のdiagnostics
- flatからstructuredへの変換
- `get_structured_stock_snapshot()`
- 先頭サマリの表示順、トレンド短縮ラベル、終端位置の既存ラベル維持、欠損時の `N/A`
- `■当日テクニカル` から `VWAP`、`RSI` が削除されていること
- `■ファンダメンタル` に配当利回りが表示されず、structured snapshotにも配当項目がないこと

## 12. Samples仕様

保存先は `Samples/`。

各銘柄について以下を保存する。

- `{code}_snapshot.json`: flat snapshot
- `{code}_structured.json`: structured snapshot
- `{code}_render.txt`: 市況ブロック込み表示テキスト
- `README.md`: 取得日時、銘柄、注意事項

現在のサンプル銘柄:

- トヨタ自動車 (7203)
- 北川電機 (6327)
- 東京エレクトロン (8035)
- オムロン (6645)
- 三菱商事 (8058)

## 13. 移植時の注意点

- `latest` は日中足が取れた場合は日中足終値、取れない場合は日足終値。
- `date` は日足最終日の年月日であり、日中足の営業日とは完全一致しない可能性がある。
- `latest_bar_time` は日中足取得時は `HH:MM`、未取得時は `終値`。
- `latest_price_timestamp` は日中足取得時は `{日足日付} {HH:MM}`、未取得時は `{日足日付} 終値`。
- `latest_price_source` は日中足なら `intraday_5m`、日足終値代替なら `daily_close`。
- 直近高値は当日を除外している。
- 今期末予想営業利益率は現行仕様の対象外。取得できない値を `N/A` として表示し続けるより、表示・ドメインから削除する。
- `vwap_source` は日中足由来なら `本日5分足`、日足代替なら `日足参考値`。
- `vwap_timestamp` は日中足由来なら `{日足日付} {HH:MM}`、日足代替なら `{日足日付} 終値`。
- `vwap_diff` はflat snapshotにあるが、表示では `fmt_vwap_position(latest, vwap, vwap_source)` が再計算している。
- structured snapshotは移植用の推奨形式。現行表示層はflat snapshotを使う。
