#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path

from data_layer import fetch_market_snapshot
from domain_layer import StockInput, get_stock_snapshot, grade_trend
from presentation_layer import load_watchlist, render_market_block, render_stock_block
from stock_logging import setup_stock_logging

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError as exc:
    raise SystemExit("tkinter が必要です。GUI対応の Python を使ってください。") from exc


class StockEntryPromptApp:
    def __init__(self, master: tk.Tk):
        self.master = master
        self.master.title("株式エントリー相談テキスト生成")
        self.master.geometry("980x760")

        self.watchlist_path: Path | None = None
        self.watchlist: list[tuple[str, str]] = []

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
                market_block = render_market_block(fetch_market_snapshot(grade_trend))

            stock = get_stock_snapshot(StockInput(name=name, code=code))
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
    setup_stock_logging()
    root = tk.Tk()
    app = StockEntryPromptApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
