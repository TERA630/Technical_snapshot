# ファンダメンタル取得仕様（現状）

本書は、現在の実装におけるファンダメンタル系データの**取得元**と**算出可否**を整理したもの。
対象は `data_layer.py` / `domain_layer.py` の現実装。

## 1. 検証結果サマリ（ご提示6点）

1. **実績EPS**：✅ 概ね正しい  
   - 現在は `info["trailingEps"]` を参照している。
2. **今期末予想EPS**：⚠️ 一部誤り（綴り＋優先順位）  
   - `info['formardEps']` ではなく `info["forwardEps"]`。  
   - ただし実装の第一優先は `get_earnings_estimate()["avg"].loc["0y"]`。
3. **来季末EPS**：✅ `get_earnings_estimate()` から取得  
   - `+1y` の `avg` を `eps_fy1` として使用。
4. **実績営業利益率**：✅ 方向性は正しい  
   - `ticker.financials`（年次損益）から `Operating Income / Total Revenue` を計算。
5. **実績営業成長率**：❌ 未実装  
   - ただし `ticker.financials` の複数期が取得できれば算出可能。
6. **今期営業利益率（予想）**：⚠️ 現実装は不可  
   - 今期の**予想営業利益**が yfinance 標準で安定取得できず、現実装は `None`。
   - 代替として「直近四半期ベースの実績ランレート」なら算出ロジックは設計可能（別実装）。

---

## 2. 現状の取得仕様（実装準拠）

## 2.1 EPS / PER（valuation）

取得関数: `fetch_valuation_snapshot(code)`

- 実績EPS: `ticker.info["trailingEps"]`
- 今期寄りEPS（fallback）: `ticker.info["forwardEps"]`
- 今期末予想EPS（優先）: `ticker.get_earnings_estimate()` の `0y / avg`
- 来期予想EPS: `ticker.get_earnings_estimate()` の `+1y / avg`
- 実装上の優先順位:
  - `eps_fy0 = earnings_estimate(0y)` が取れれば採用
  - 取れなければ `forwardEps` を採用

## 2.2 営業利益率 / ROE（profitability）

取得関数: `fetch_profitability_snapshot(code)`

- 実績ROE: `ticker.info["returnOnEquity"]`（0〜1値は `%` 換算）
- 実績営業利益率:
  - `ticker.financials` から
  - `Operating Income` と `Total Revenue` を探索して
  - `calc_margin_ratio(営業利益, 売上高)` で算出
- 今期/来期営業利益率:
  - `revenue_fy0`, `revenue_fy1` は `get_revenue_estimate()` から取得を試行
  - ただし `op_income_fy0`, `op_income_fy1` は現状 `None` 固定（EPS流用禁止方針）
  - よって `op_margin_fy0`, `op_margin_fy1` は現状 `None`

## 2.3 配当

取得関数: `fetch_dividend_snapshot(code)`

- 年間配当: `trailingAnnualDividendRate`（なければ `dividendRate`）
- 直近配当: `ticker.dividends` の末尾
- 配当利回り（ドメインで算出）: `annual_dividend / latest_price * 100`

---

## 3. 論点別の可否と設計メモ

## 3.1 ③ 来季末EPSはどこから？
- 取得元は `ticker.get_earnings_estimate()` の `+1y / avg`。
- 取れない銘柄は `None`。

## 3.2 ⑤ 実績営業成長率（未実装）
- 可能。
- 定義例:
  - `growth = (営業利益_t / 営業利益_t-1 - 1) * 100`
- 必要条件:
  - `ticker.financials` に複数期の営業利益が存在
  - 欠損・符号反転（赤字↔黒字）の扱いを仕様化

## 3.3 ⑥ 今期営業利益率の代替案
- 厳密な「今期予想営業利益率」は現ソースでは不安定。
- 代替（参考値）としては以下が現実的:
  1. 直近4四半期累計の営業利益率（TTM）
  2. 直近四半期の営業利益率
  3. 直近四半期の前年同期比成長率（営業利益）
- ただしこれらは**予想値ではなく実績ベース近似**であることを表示で明示する必要がある。

---

## 4. 今後の実装方針（提案）

- データ層: `fetch_*` のみで外部取得・正規化
- ドメイン層: `calc_*` で率/成長率を算出
- 表示層: `render_*` で「予想/実績/参考値」のラベルを厳密表示

以上。


## 5. 新規実装仕様（ドメイン反映済み）

### 5.1 実績営業成長率
- 取得ソース: `ticker.income_stmt`（年次、fallback: `ticker.financials`）の `Operating Income`
- 使用データ:
  - 当期実績営業利益: 最新列 `iloc[0]`
  - 前期実績営業利益: 次列 `iloc[1]`
- 計算式:
  - `calc_growth_rate(current, base) = (current / base - 1) * 100`
- 出力キー:
  - `op_growth_actual`

### 5.2 直近四半期営業利益率
- 取得ソース: `ticker.quarterly_income_stmt`（fallback: `ticker.quarterly_financials`）
  - 営業利益: `Operating Income`
  - 売上高: `Total Revenue`
- 計算式:
  - `calc_margin_ratio(営業利益, 売上高) = 営業利益 / 売上高 * 100`
- 出力キー:
  - `op_margin_q_latest`

### 5.3 直近四半期の昨年同期比営業成長率
- 取得ソース: `ticker.quarterly_income_stmt`（fallback: `ticker.quarterly_financials`） の `Operating Income`
- 使用データ:
  - 直近四半期: `iloc[0]`
  - 昨年同期（4四半期前）: `iloc[4]`
- 計算式:
  - `calc_growth_rate(直近四半期営業利益, 昨年同期営業利益)`
- 出力キー:
  - `op_growth_q_yoy`

※ 欠損/ゼロ除算時は `None`（表示層で `N/A` 想定）。
