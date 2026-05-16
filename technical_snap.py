#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import math
import re
from pathlib import Path
from datetime import datetime

import pandas as pd

from data_layer import fetch_market_snapshot
from domain_layer import analyze_stock, infer_trend

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError as exc:
    raise SystemExit("tkinter が必要です。GUI対応の Python を使ってください。") from exc

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
                market_block = render_market_block(fetch_market_snapshot(infer_trend))

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
