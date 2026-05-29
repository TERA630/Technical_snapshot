# 株価取得・指標作成・表示エンジン移植仕様書

## 1. 目的

本書は、現行プログラムの株価取得、指標作成、表示テキスト生成ロジックを他プログラムへ移植するための仕様をまとめる。

対象範囲は以下の4領域とする。

- データ取得仕様: `data_layer.py`
- ドメイン/指標算出仕様: `domain_layer.py`
- 表示整形仕様: `presentation_layer.py`
- GUIからの利用仕様: `technical_snap.py`

移植時は、GUI部分を切り離し、データ取得・ドメイン・表示を独立したエンジンとして扱える構成にすることを推奨する。

## 2. 現行アーキテクチャ

### 2.1 レイヤ構成

| レイヤ | 現行ファイル | 役割 |
|---|---|---|
| 共通定数 | `stock_constants.py` | 表示文言、評価ラベル、しきい値、市況シンボル、文字コード方針を集約する |
| データ層 | `data_layer.py` | yfinanceから価格、日中足、市況、PER/EPS、収益性、配当を取得し、Python値へ正規化する |
| ドメイン層 | `domain_layer.py` | 移動平均、ATR、RSI、VWAP差、値幅、終端位置、前日評価、トレンド、PER、配当利回りを算出する |
| 表示層 | `presentation_layer.py` | ドメイン層の辞書を固定フォーマットの日本語テキストに変換する |
| UI層 | `technical_snap.py` | 監視銘柄ファイルを読み、銘柄選択、生成、コピー、保存を行うTkinter GUI |

### 2.2 主要な実行フロー

1. 監視銘柄ファイルから `(銘柄名, 4桁コード)` を読み込む。
2. ユーザーが銘柄を選択する。
3. `get_stock_snapshot(StockInput(name, code))` を呼ぶ。
4. データ層が日足、日中足、バリュエーション、収益性、配当を取得する。
5. ドメイン層がテクニカル指標・評価ラベルを作成する。
6. `render_stock_block(stock, include_market, market_block)` が表示テキストを生成する。
7. 必要に応じて `fetch_market_snapshot()` と `render_market_block()` で市況ブロックを追加する。

## 3. 入力仕様

### 3.1 銘柄入力

ドメイン層の入力は `StockInput` とする。

| 項目 | 型 | 内容 |
|---|---|---|
| `name` | string | 表示用銘柄名 |
| `code` | string | 東証4桁コード。例: `7203` |

yfinanceの株価取得シンボルは `{code}.T` とする。

### 3.2 監視銘柄ファイル

表示層の `load_watchlist()` はMarkdownまたはテキストから銘柄を抽出する。

- 想定形式: `銘柄名 (1234)` または箇条書き内の同等表記
- コードは4桁数字のみ対象
- 同一コードが複数回出た場合は初出のみ採用
- 抽出できない場合はエラー

## 4. データ取得仕様

### 4.1 共通ルール

- 外部取得元は現状 `yfinance`
- 数値変換は `safe_float()` で行う
- `None`、NaN、変換不能値は `None`
- 取得・計算不可は例外で止めず、原則 `None` としてドメイン/表示層へ渡す
- 表示層では `None`、NaN、inf を `N/A` と表示する

### 4.2 日足価格

| 項目 | 仕様 |
|---|---|
| 関数 | `fetch_history(symbol, period="4mo", interval="1d")` |
| yfinance API | `yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)` |
| 現行利用 | `get_stock_snapshot()` から `{code}.T`, `period="4mo"` で取得 |
| 必須列 | `Open`, `High`, `Low`, `Close`, `Volume` |
| 最低件数 | 30件未満の場合は `価格データ不足` エラー |
| index | timezoneを除去したdatetime |

### 4.3 日中足/VWAP

| 項目 | 仕様 |
|---|---|
| 関数 | `fetch_intraday_vwap(code, interval="5m")` |
| yfinance API | `yf.download("{code}.T", period="1d", interval="5m", auto_adjust=False)` |
| 必須列 | `Open`, `High`, `Low`, `Close`, `Volume` |
| 除外条件 | Volumeが0または欠損の足は除外 |
| VWAP | `TypicalPrice = (High + Low + Close) / 3`、`VWAP = cumsum(TypicalPrice * Volume) / cumsum(Volume)` |

返却項目は以下。

| key | 内容 |
|---|---|
| `latest_price` | 最新5分足のClose |
| `latest_bar_time` | 最新足の時刻。timezoneありならAsia/Tokyoへ変換し `HH:MM` |
| `open` | 当日最初の有効足Open |
| `high` | 当日有効足Highの最大 |
| `low` | 当日有効足Lowの最小 |
| `vwap` | 当日累積VWAP |
| `vwap_diff_pct` | `latest_price / vwap - 1` の百分率 |
| `volume` | 当日有効足Volume合計 |

日中足が取得できない場合、現在値・O/H/L・出来高は日足終値ベースを使い、VWAPは日足の `(High + Low + Close) / 3` で代替する。

### 4.4 市況データ

| 表示名 | yfinance symbol |
|---|---|
| WTI | `CL=F` |
| 銅 | `HG=F` |
| NASDAQ | `^IXIC` |

取得仕様:

- `fetch_history(symbol, period="10d")`
- 終値2本未満なら `latest=None`, `change_pct=None`, `trend="N/A"`
- 騰落率: `latest / prev_close - 1`
- 5日移動平均が取得できる場合のみ `grade_trend()` でトレンド判定
- 10日取得のため、25日移動平均は通常不足し、市況トレンドは `N/A` になりやすい

### 4.5 PER/EPS

関数: `fetch_valuation_snapshot(code)`

| key | 取得元/算出 |
|---|---|
| `eps_actual` | `ticker.info["trailingEps"]` |
| `eps_fy0` | `ticker.get_earnings_estimate()` の index `0y`, column `avg`。なければ `ticker.info["forwardEps"]` |
| `eps_fy1` | `ticker.get_earnings_estimate()` の index `+1y`, column `avg` |
| `per_actual` | `ticker.info["trailingPE"]` |
| `per_forward` | `ticker.info["forwardPE"]` |

ドメイン層で以下を作る。

- `per_fy0`: `latest / eps_fy0`。`eps_fy0` がなければ `per_forward`
- `per_fy1`: `latest / eps_fy1`
- EPSが `None` または0以下の場合、PERは `None`

### 4.6 収益性

関数: `fetch_profitability_snapshot(code)`

| key | 取得元/算出 |
|---|---|
| `roe_actual` | `ticker.info["returnOnEquity"]`。1以下なら百分率へ変換 |
| `op_margin_actual` | 年次損益計算書の `Operating Income / Total Revenue * 100` |
| `op_growth_actual` | `最新Operating Income / 前期Operating Income - 1` の百分率 |
| `revenue_fy0` | `ticker.get_revenue_estimate()` の `0y / avg` |
| `revenue_fy1` | `ticker.get_revenue_estimate()` の `+1y / avg` |
| `op_income_fy0` | 現状 `None` |
| `op_income_fy1` | 現状 `None` |
| `op_margin_fy0` | 現状 `None`。営業利益予想が取得できないため |
| `op_margin_fy1` | 現状 `None` |

年次損益計算書は `ticker.income_stmt` を優先し、空なら `ticker.financials` をfallbackとする。

行名は以下を探索する。

- 営業利益: `Operating Income`, `OperatingIncome`
- 売上高: `Total Revenue`, `TotalRevenue`, `Revenue`

### 4.7 配当

関数: `fetch_dividend_snapshot(code)`

| key | 取得元/算出 |
|---|---|
| `annual_dividend` | `ticker.info["trailingAnnualDividendRate"]`。なければ `ticker.info["dividendRate"]` |
| `latest_dividend` | `ticker.dividends` の末尾 |
| `latest_dividend_date` | 最新配当日の `YYYY-MM-DD` |
| `dividend_yield` | ドメイン層で `annual_dividend / latest_price * 100` |

## 5. 指標作成仕様

### 5.1 移動平均

日足終値から以下を算出する。

| key | 式 |
|---|---|
| `ma5` | `Close.rolling(5).mean()` |
| `ma25` | `Close.rolling(25).mean()` |
| `ma25_prev5` | 5営業日前の25日移動平均。`len(hist) >= 30` の場合のみ |

乖離率:

- `dev5 = latest / ma5 - 1`
- `dev25 = latest / ma25 - 1`
- 表示値は百分率

### 5.2 RSI

期間は14。

```text
delta = Close.diff()
gain = max(delta, 0)
loss = -min(delta, 0)
avg_gain = gain.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
avg_loss = loss.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
RS = avg_gain / avg_loss
RSI = 100 - 100 / (1 + RS)
```

### 5.3 ATR

期間は14。True Rangeは以下の最大値。

- `High - Low`
- `abs(High - prev Close)`
- `abs(Low - prev Close)`

ATR:

```text
ATR14 = TrueRange.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
```

### 5.4 当日位置・レンジ

| key | 式 |
|---|---|
| `day_change_pct` | `latest / prev_close - 1` の百分率 |
| `day_range` | `high - low` |
| `day_range_atr` | `day_range / atr14` |
| `day_close_position` | `(latest - low) / (high - low)` |
| `ma25_distance` | `latest - ma25` |
| `ma25_distance_atr` | `(latest - ma25) / atr14` |

ゼロ除算、欠損、価格範囲が0以下の場合は `None`。

### 5.5 前日評価

前日足は日足履歴の末尾から2本目を使う。

| key | 式 |
|---|---|
| `prev_change_pct` | `prev_close / prev_prev_close - 1` の百分率 |
| `prev_range` | `prev_high - prev_low` |
| `prev_range_atr` | `prev_range / atr14` |
| `prev_close_position` | `(prev_close - prev_low) / (prev_high - prev_low)` |
| `prev_vol_ratio` | `prev_volume / prev_vol_avg20 - 1` の百分率 |

ローソク判定:

| 条件 | ラベル |
|---|---|
| `close > open` | 陽線 |
| `close < open` | 陰線 |
| その他 | 十字線 |

ヒゲ/形状判定:

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
| `prev_range_atr` または `prev_close_position` が欠損 | 判定不可 |
| `prev_range_atr >= 1.30` かつ `close_position <= 0.30` かつ `prev_vol_ratio >= 20` | 崩れ |
| `prev_range_atr >= 1.50` かつ `close_position <= 0.40` | 崩れ |
| `0.50 <= prev_range_atr <= 1.20` かつ `close_position >= 0.45` かつ `prev_vol_ratio <= 20` | 押し |
| その他 | 中立 |

総合評価:

- 欠損時は `判定不可`
- 大きな値幅、安値圏引け、出来高増の条件を満たす場合は `崩れ`
- 陽線、高値圏引け、ATR比が大きすぎず、上ヒゲ長めでない場合は `強い上昇`
- 陽線でも終端位置が弱い、または上ヒゲ長めの場合は `弱い上昇`
- 陰線または十字線で、通常範囲の値幅、終端位置が中段以上、出来高過熱なしの場合は `押し`
- 下ヒゲ長めで、終端位置が中段以上、ATR比が大きすぎない場合は `押し`
- その他は `中立`

### 5.6 節目・ブレイクライン

過去高値/安値は、当日を含めず `shift(1)` した日足から算出する。

| key | 式 |
|---|---|
| `recent5_high` | 直近5営業日のHigh最大 |
| `recent20_high` | 直近20営業日のHigh最大 |
| `recent60_high` | 直近60営業日のHigh最大 |
| `recent60_low` | 直近60営業日のLow最小 |
| `recent*_high_distance` | `latest - recent*_high` |
| `recent*_high_distance_pct` | `latest / recent*_high - 1` の百分率 |
| `recent60_range_position` | `(latest - recent60_low) / (recent60_high - recent60_low)` |

### 5.7 ラベルしきい値

値幅ATR比:

| 条件 | ラベル |
|---|---|
| 欠損/NaN/inf | N/A |
| `< 0.5` | 狭い値幅 |
| `< 1.0` | 通常値幅 |
| `< 1.5` | 大きめ |
| `>= 1.5` | 急拡大 |

終端位置:

| 条件 | ラベル |
|---|---|
| 欠損/NaN/inf | N/A |
| `>= 0.60` | 高値圏で終了 |
| `>= 0.30` | 中段で終了 |
| `< 0.30` | 安値圏で終了 |

60日レンジ位置:

| 条件 | ラベル |
|---|---|
| 欠損/NaN/inf | N/A |
| `>= 0.60` | 高値圏 |
| `>= 0.30` | 中段 |
| `< 0.30` | 安値圏 |

トレンド:

| 条件 | ラベル |
|---|---|
| `latest`, `ma5`, `ma25` のいずれか欠損 | N/A |
| `latest > ma5 > ma25` かつ `ma25 > ma25_prev5` | 上昇トレンド |
| `latest < ma5 < ma25` | 下降トレンド |
| その他 | もみ合い / 戻り局面 |

## 6. スナップショット出力仕様

`get_stock_snapshot()` は表示層へ渡す1銘柄分の辞書を返す。

主要keyは以下。

| 分類 | key |
|---|---|
| 銘柄 | `name`, `code`, `date`, `acquired_at`, `error`, `diagnostics` |
| 当日価格 | `latest_bar_time`, `open`, `high`, `low`, `latest`, `day_change_pct`, `volume` |
| VWAP | `vwap`, `vwap_diff` |
| テクニカル | `ma5`, `dev5`, `ma25`, `dev25`, `rsi`, `atr14`, `trend` |
| 当日レンジ | `day_range`, `day_range_atr`, `day_range_label`, `day_close_position`, `day_close_position_label` |
| 前日 | `prev_open`, `prev_high`, `prev_low`, `prev_close`, `prev_change_pct`, `prev_candle`, `prev_wick_shape`, `prev_range_atr`, `prev_range_label`, `prev_close_position`, `prev_close_position_label`, `prev_volume`, `prev_vol_ratio`, `prev_session_judgement`, `prev_evaluation` |
| 移動平均距離 | `ma25_distance`, `ma25_distance_atr` |
| 節目 | `recent5_high`, `recent5_high_distance`, `recent5_high_distance_pct`, `recent20_high`, `recent20_high_distance`, `recent20_high_distance_pct`, `recent60_high`, `recent60_low`, `recent60_range_position`, `recent60_range_zone` |
| PER/EPS | `per_actual`, `per_fy0`, `per_fy1`, `eps_actual`, `eps_fy0`, `eps_fy1` |
| 収益性 | `roe_actual`, `op_margin_actual`, `op_growth_actual`, `op_margin_fy0`, `op_margin_fy1` |
| 配当 | `annual_dividend`, `latest_dividend`, `latest_dividend_date`, `dividend_yield` |

エラー時は以下を返す。

```python
{"name": name, "code": code, "error": "価格データ不足"}
```

## 7. 表示仕様

### 7.1 基本整形

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

### 7.2 銘柄ブロックの表示順

表示順と見出しは固定。

1. `【銘柄】{name} ({code})`
2. 空行
3. `■当日位置・レンジ`
4. PER/EPS
5. `■当日テクニカル`
6. `■前日評価`
7. `■ファンダメンタル`
8. `■節目・ブレイクライン`
9. `■流れ`
10. 任意で `■市況`

### 7.3 当日位置・レンジ

表示項目:

- 現在値: `現在値({YYYY/MM/DD}　{HH:MMまたは終値})：{現在値}(前日比{+x.xx％})`
- `O/H/L/C`
- 当日値幅、ATR比、値幅ラベル
- 終端位置、終端位置ラベル

### 7.4 PER/EPS

表示項目:

- `PER  {実績PER}(実績) {今期末予想PER}(今期末予想) {来期予想PER}(来期予想)`
- `EPS  {実績EPS}(実績) {今期末予想EPS}(今期末予想) {来期予想EPS}(来期予想)`

### 7.5 当日テクニカル

表示項目:

- VWAP、現在値との差、VWAP比
- 5日線、5日線乖離
- 25日線、25日線乖離、価格差、ATR比
- 14日ATR
- RSI
- 出来高、20日平均比

### 7.6 前日評価

表示項目:

- 前日終値、前日比
- 前日H/L/C
- ローソク、ヒゲ/形状
- 終端位置
- ATR比、値幅ラベル
- 出来高、20日平均比
- 押し判定
- 総合評価

### 7.7 ファンダメンタル

表示項目:

- 配当利回り
- `{取得日時の前年}年実績ROE`
- `{取得日時の前年}年実績営業利益率`
- `{取得日時の前年}年実績営業成長率`
- `{取得日時の年}年予想営業利益率`

年は `acquired_at` の年を基準とする。`acquired_at` が不正な場合は現在年を使う。

### 7.8 節目・ブレイクライン

表示項目:

- 前日高値
- 直近5日高値、現在値との差、差分率
- 直近20日高値、現在値との差、差分率
- 60日高値
- 60日安値
- 現在レンジ、レンジラベル

### 7.9 市況ブロック

チェックボックス有効時のみ末尾に追加する。

表示順:

1. WTI
2. 銅
3. NASDAQ

各行の形式:

```text
{name}：{latest}（{change_pct} / {trend}）
```

## 8. 移植時の推奨インターフェース

他プログラムへ移植する場合、以下の3つを公開APIにすると扱いやすい。

```python
get_stock_snapshot(name: str, code: str, repository: StockDataRepository | None = None) -> dict
render_stock_snapshot(snapshot: dict, include_market: bool = False) -> str
parse_watchlist(text: str) -> list[tuple[str, str]]
```

外部データ取得は `StockDataRepository` 相当のインターフェースに閉じ込める。

```python
class StockDataRepository:
    def fetch_daily_history(code: str, period: str = "4mo") -> DataFrame: ...
    def fetch_intraday_snapshot(code: str, interval: str = "5m") -> dict | None: ...
    def fetch_valuation_snapshot(code: str) -> dict: ...
    def fetch_profitability_snapshot(code: str) -> dict: ...
    def fetch_dividend_snapshot(code: str) -> dict: ...
```

これにより、将来yfinanceから別APIへ切り替える場合もドメイン層と表示層を維持できる。

Python移植時は `stock_types.py` の `StructuredStockSnapshot` と `to_structured_snapshot()` を使い、現行のflat snapshotから保守性重視の階層構造へ変換できる。

## 9. 移植前にしておいたほうがいいこと

### 9.1 仕様固定用のサンプル出力を作る

代表銘柄を数件選び、`get_stock_snapshot()` の辞書JSONと `render_stock_block()` の表示テキストを保存する。

あなたにしてほしいこと:

1. サンプルに使う銘柄を3〜5件決める。
   - 例: 大型株、値がさ株、高配当株、出来高が少ない銘柄、指標が欠損しやすい銘柄を混ぜる。
2. 市況ブロックを含めるか決める。
   - 本移植検証では市況ブロックを含める。
3. サンプル取得日をメモする。
   - yfinanceの値は日々変わるため、比較時に「同じ日付の期待値」なのか「最新値で再取得した値」なのかを区別する。
4. 保存先フォルダ名を決める。
   - 保存先: `Samples/`

こちらで作業する場合に作るもの:

- `Samples/{code}_snapshot.json`: `get_stock_snapshot()` の辞書をJSON化したもの
- `Samples/{code}_render.txt`: `render_stock_block()` の表示結果。市況ブロックを含める
- `Samples/README.md`: 取得日、銘柄、比較時の注意点

目的:

- 移植後の差分比較に使う
- 表示崩れ、丸め、`N/A` 表示の退行を検出する
- yfinanceの取得値変動とロジック差分を切り分ける

### 9.2 データ取得と算出のテストを分ける

対応済み。

`tests/test_domain_and_data.py` を追加し、外部APIに依存しない固定データテストを用意した。

yfinanceは外部要因で値・列・欠損が変わるため、ドメイン層テストでは固定DataFrameを使う。日中VWAPだけは `yfinance.download` をモックし、取得結果の形を固定して検証する。

最低限テストしたい項目:

- 日中VWAP: 対応済み
- ATR14: 対応済み
- RSI14: 対応済み
- 終端位置: 対応済み
- 値幅ATR比ラベル: 対応済み
- 前日押し判定: 対応済み
- トレンド判定: 対応済み
- PER/EPS fallback: 対応済み
- 欠損時の `N/A`: 対応済み
- 任意データ取得失敗時の診断情報: 対応済み

実行コマンド:

```powershell
python -m unittest discover -s tests -v
```

### 9.3 表示文言を定数化する

対応済み。

`stock_constants.py` に以下を集約した。

- 見出し
- 評価ラベル
- しきい値
- 市況表示名
- yfinance symbol
- 欠損表示
- エラーメッセージ
- 単位ラベル

移植時は `stock_constants.py` を仕様の基準として扱い、表示文言やしきい値を変更する場合はこのファイルを先に変更する。

### 9.4 文字コードをUTF-8で統一する

対応済み。

日本語ラベルが多いため、移植先でも以下を固定する。

- ソースファイル: UTF-8
- 出力ファイル: UTF-8
- 改行: LFまたは移植先標準に統一
- Windowsコンソール表示時は文字化け確認を行う

現行コードでは `stock_constants.py` の `ENCODING = "utf-8"` を読み込み、監視銘柄ファイルの通常読み込みに使う。BOM付きUTF-8は `utf-8-sig` fallbackで読む。

Windows PowerShellで内容確認する場合は、以下のように出力エンコーディングをUTF-8にしてから読む。

```powershell
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
Get-Content -Raw -Encoding UTF8 porting_spec.md
```

### 9.5 取得失敗の扱いを明確化する

対応済み。

現行は多くの取得失敗を `None` として握り、表示で `N/A` にする。これに加えて、`get_stock_snapshot()` の返却辞書に `diagnostics` を追加し、内部的な原因を残す。

診断カテゴリは `stock_constants.py` の `DIAGNOSTIC_CATEGORIES` に集約した。

- 外部API失敗
- データ欠損
- 列名変更
- ゼロ除算
- 取得対象外

`diagnostics` の形式:

```python
{
    "category": "外部API失敗",
    "field": "valuation",
    "message": "valuation unavailable",
}
```

表示は従来どおり `N/A` のままとする。日足価格が不足する場合は従来どおり `error = "価格データ不足"` とし、日中足・PER/EPS・収益性・配当など任意データの取得失敗は全体を落とさず `diagnostics` に記録する。

### 9.6 yfinance依存リスクを隔離する

yfinanceは非公式APIに近く、列名・取得可否・推定値の有無が変わる可能性がある。

移植先では以下を用意するとよい。

- repository差し替え機構
- キャッシュ
- リトライ
- レート制限
- 取得元と取得時刻の記録
- APIレスポンスの簡易ログ

### 9.7 ドメイン辞書の型定義を作る

対応済み。

移植先はPythonとする。`stock_types.py` に `TypedDict` ベースの型定義を追加した。

採用方針:

- 型定義: `TypedDict`
- diagnostics: 表示には出さず、Python loggingへwarning出力する
- snapshot key: 現行flat keyは維持しつつ、移植用には保守性重視の階層構造を使う

追加した主要型:

- `Diagnostic`
- `StockIdentity`
- `PriceSnapshot`
- `VwapSnapshot`
- `TechnicalSnapshot`
- `RangeSnapshot`
- `PreviousSessionSnapshot`
- `BreaklineSnapshot`
- `ValuationSnapshot`
- `ProfitabilitySnapshot`
- `DividendSnapshot`
- `StructuredStockSnapshot`

変換関数:

```python
from stock_types import to_structured_snapshot

flat = get_stock_snapshot(StockInput(name, code))
structured = to_structured_snapshot(flat)
```

階層構造:

| key | 内容 |
|---|---|
| `identity` | 銘柄名、コード、取得日、エラー |
| `price` | 当日価格、現在値、出来高 |
| `vwap` | VWAP、VWAP差分率 |
| `technical` | MA、RSI、ATR、トレンド |
| `range` | 当日レンジ、終端位置、25日線距離 |
| `previous_session` | 前日価格、ローソク、押し判定、総合評価 |
| `breakline` | 直近高値、60日レンジ |
| `valuation` | PER/EPS |
| `profitability` | ROE、営業利益率、営業成長率 |
| `dividend` | 配当、配当利回り |
| `diagnostics` | 内部診断情報 |

## 10. 移植時の注意点

- `latest` は日中足が取れた場合は日中足終値、取れない場合は日足終値
- `date` は日足最終日の年月日であり、日中足の営業日とは完全一致しない可能性がある
- `latest_bar_time` は日中足取得時は `HH:MM`、未取得時は `終値`
- 直近高値は当日を除外している
- 市況は10日分しか取得していないため、25日移動平均を使うトレンド判定とは相性が悪い
- 表示上の「今期末予想営業利益率」は現状 `N/A` になりやすい
- `vwap_diff` はドメイン辞書にあるが、表示では `fmt_vwap_position(latest, vwap)` が再計算している
