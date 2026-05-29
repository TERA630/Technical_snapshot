# ファンダメンタル取得仕様について

ファンダメンタル取得仕様は `porting_spec.md` に集約済み。

現行仕様の正本は以下を参照する。

- `porting_spec.md` の「4.5 PER/EPS」
- `porting_spec.md` の「4.6 収益性」
- `porting_spec.md` の「4.7 配当」
- `data_layer.py` の `fetch_valuation_snapshot()`, `fetch_profitability_snapshot()`, `fetch_dividend_snapshot()`
- `domain_layer.py` の `calc_per()`, `calc_dividend_yield()`

四半期ファンダメンタルは現行実装・移植仕様の対象外。
本ファイルは旧仕様との混在を避けるため、詳細仕様を保持しない。
