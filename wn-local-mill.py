#!/usr/bin/env python3
"""
Novel Mill — host window for the local Japanese novel pipeline.

Works on web novels (WN) and light novels (LN). The GitHub / folder name
is still wn-local-mill so existing Windows copies keep working.

Tabs: EPUB → OCR → Split → Mill. Settings holds the shared book folder.

Windows: close the app, copy these .py files next to
wn-local-mill.bat, then run the bat.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

__version__ = "1.8.0"
APP_TITLE = "Novel Mill"
APP_USER_MODEL_ID = "NovelMill.Desktop"

# CustomTkinter / novel_downloader dark + light tokens (no white chrome).
THEMES = {
    "dark": {
        "BG": "#242424",
        "BG2": "#2b2b2b",
        "BG3": "#333333",
        "FG": "#e5e5e5",
        "FG_DIM": "#a0a0a0",
        "ACCENT": "#1f6aa5",
        "ACCENT_HOVER": "#144870",
        "BTN": "#3d3d3d",
        "DANGER": "#c23b3b",
        "ENTRY_BG": "#2e2e2e",
        "SELECT_FG": "#ffffff",
    },
    "light": {
        "BG": "#f2f2f2",
        "BG2": "#e8e8e8",
        "BG3": "#dedede",
        "FG": "#1a1a1a",
        "FG_DIM": "#5a5a5a",
        "ACCENT": "#1f6aa5",
        "ACCENT_HOVER": "#144870",
        "BTN": "#dcdcdc",
        "DANGER": "#c23b3b",
        "ENTRY_BG": "#ffffff",
        "SELECT_FG": "#ffffff",
    },
}

UI = {
    "tabs": (("EPUB", "OCR", "分割", "ミル", "設定"), ("EPUB", "OCR", "Split", "Mill", "Settings")),
    "book_folder": ("作品フォルダ（WNシリーズまたはLN一冊）", "Book folder (one WN series or one LN volume)"),
    "browse": ("参照", "Browse"),
    "apply_tabs": ("各タブに適用", "Apply to tabs"),
    "appearance": ("外観", "Appearance"),
    "language": ("表示言語", "Language"),
    "hint": (
        "作品ごとにフォルダを一つ。Novel Mill が使う名前:\n"
        "  raw_full.txt   日本語の全文（分割が読む）\n"
        "  in\\            シーン／章ファイル（ミルが読む）\n"
        "  out\\           英語 .en.txt\n"
        "  images\\        EPUB またはスキャンの画像\n"
        "  ocr\\           Tesseract テキスト\n"
        "  lock\\          prompt.txt / glossary.txt / voices.txt\n\n"
        "手順: EPUB（または OCR → 結合）→ 分割 → ミル。\n"
        "Adobe DRM の EPUB は拒否します。先に Calibre で変換してください。",
        "Each book gets its own folder. Novel Mill uses these names:\n"
        "  raw_full.txt   whole Japanese dump (Split reads this)\n"
        "  in\\            one scene/chapter file each (Mill reads this)\n"
        "  out\\           English .en.txt from the mill\n"
        "  images\\        page pictures from EPUB or your scans\n"
        "  ocr\\           Tesseract text files\n"
        "  lock\\          prompt.txt / glossary.txt / voices.txt for the mill\n\n"
        "Usual path: EPUB (or OCR → Combine) → Split → Mill.\n"
        "Adobe-DRM store EPUBs are refused. Convert in Calibre first.",
    ),
    "keep_en": ("既存を残す", "Keep existing"),
    "overwrite_en": ("上書きする", "Overwrite"),
    "overwrite_label": ("既存の .en.txt", "Existing .en.txt"),
}


def _ui(key: str, lang: str) -> str:
    pair = UI[key]
    return pair[1] if lang == "en" else pair[0]


def system_is_dark() -> bool:
    if sys.platform == "win32":
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
            )
            val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(val) == 0
        except Exception:
            return True
    return True


def resolve_theme(mode: str) -> str:
    if mode == "light":
        return "light"
    if mode == "system":
        return "dark" if system_is_dark() else "light"
    return "dark"


def ui_settings_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home()) / "NovelMill"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "novel_mill"
    return base / "ui.json"


def load_ui_settings() -> dict:
    data = {"appearance": "system", "ui_lang": "en", "book_folder": ""}
    try:
        raw = json.loads(ui_settings_path().read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data.update(raw)
    except Exception:
        pass
    if data.get("appearance") not in ("system", "dark", "light"):
        data["appearance"] = "system"
    if data.get("ui_lang") not in ("ja", "en"):
        data["ui_lang"] = "en"
    return data


def save_ui_settings(data: dict) -> None:
    path = ui_settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def apply_theme(root: tk.Tk, mode: str) -> ttk.Style:
    pal = THEMES[resolve_theme(mode)]
    bg, bg2, bg3 = pal["BG"], pal["BG2"], pal["BG3"]
    fg, dim = pal["FG"], pal["FG_DIM"]
    accent, hover = pal["ACCENT"], pal["ACCENT_HOVER"]
    btn, danger = pal["BTN"], pal["DANGER"]
    entry_bg = pal["ENTRY_BG"]
    root.configure(bg=bg)
    root.option_add("*Background", bg)
    root.option_add("*Foreground", fg)
    root.option_add("*selectBackground", accent)
    root.option_add("*selectForeground", pal["SELECT_FG"])
    root.option_add("*Text.background", entry_bg)
    root.option_add("*Text.foreground", fg)
    root.option_add("*Text.insertBackground", fg)
    root.option_add("*Text.highlightBackground", bg)
    root.option_add("*Listbox.background", entry_bg)
    root.option_add("*Listbox.foreground", fg)
    root.option_add("*Entry.background", entry_bg)
    root.option_add("*Entry.foreground", fg)
    root.option_add("*Entry.insertBackground", fg)
    root.option_add("*Entry.highlightBackground", bg)
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    flat = {"bordercolor": bg3, "lightcolor": bg, "darkcolor": bg, "relief": "flat"}
    style.configure(".", background=bg, foreground=fg, fieldbackground=entry_bg, **flat)
    style.configure("TFrame", background=bg, **flat)
    style.configure("TLabel", background=bg, foreground=fg)
    style.configure("TLabelframe", background=bg, foreground=fg, borderwidth=1, **flat)
    style.configure("TLabelframe.Label", background=bg, foreground=dim)
    style.configure("TButton", background=btn, foreground=fg, padding=6, **flat)
    style.map("TButton", background=[("active", hover), ("disabled", bg3)], foreground=[("active", "#fff")])
    style.configure("TCheckbutton", background=bg, foreground=fg)
    style.configure("TRadiobutton", background=bg, foreground=fg)
    style.configure("TEntry", fieldbackground=entry_bg, foreground=fg, insertcolor=fg, **flat)
    style.configure("TCombobox", fieldbackground=entry_bg, foreground=fg, background=entry_bg, **flat)
    style.map("TCombobox", fieldbackground=[("readonly", entry_bg)], foreground=[("readonly", fg)])
    style.configure("TNotebook", background=bg, borderwidth=0)
    style.configure("TNotebook.Tab", background=bg, foreground=fg, padding=0)
    style.layout("Hidden.TNotebook.Tab", [])
    style.configure("Hidden.TNotebook", background=bg, borderwidth=0)
    style.configure("TProgressbar", background=accent, troughcolor=bg3)
    style.configure("TScrollbar", background=bg2, troughcolor=bg, bordercolor=bg, arrowcolor=fg)
    style.configure("Chrome.TFrame", background=bg2)
    style.configure("Tab.TButton", background=bg2, foreground=dim, padding=(14, 8))
    style.map("Tab.TButton", background=[("active", bg3)], foreground=[("active", fg)])
    style.configure("TabOn.TButton", background=bg3, foreground=fg, padding=(14, 8))
    style.configure("Win.TButton", background=bg2, foreground=fg, width=3, padding=4)
    style.map("Win.TButton", background=[("active", bg3)])
    style.configure("Close.TButton", background=bg2, foreground=fg, width=3, padding=4)
    style.map("Close.TButton", background=[("active", danger)], foreground=[("active", "#fff")])
    style.configure("Status.TLabel", background=bg2, foreground=dim)
    style.configure("Seg.TFrame", background=bg3)
    style.configure("SegOff.TButton", background=bg3, foreground=dim, padding=(10, 4))
    style.configure("SegOn.TButton", background=accent, foreground="#ffffff", padding=(10, 4))
    style.map("SegOff.TButton", background=[("active", btn)], foreground=[("active", fg)])
    style.map("SegOn.TButton", background=[("active", hover)])
    _recolor_text_widgets(root, entry_bg, fg, bg)
    return style


def _recolor_text_widgets(widget: tk.Misc, bg: str, fg: str, chrome: str) -> None:
    if isinstance(widget, tk.Text):
        widget.configure(
            bg=bg,
            fg=fg,
            insertbackground=fg,
            highlightthickness=0,
            highlightbackground=chrome,
            relief="flat",
            borderwidth=0,
        )
    for child in widget.winfo_children():
        _recolor_text_widgets(child, bg, fg, chrome)


class SegmentedToggle(ttk.Frame):
    """Binary (or small-set) toggle matching novel_downloader's CTkSegmentedButton."""

    def __init__(self, master, values: tuple[str, ...], command=None, **kw):
        super().__init__(master, style="Seg.TFrame", **kw)
        self.values = values
        self.command = command
        self.var = tk.StringVar(value=values[0])
        self.buttons: dict[str, ttk.Button] = {}
        for i, val in enumerate(values):
            btn = ttk.Button(self, text=val, style="SegOff.TButton", command=lambda v=val: self.set(v, user=True))
            btn.pack(side="left", padx=1, pady=1)
            self.buttons[val] = btn
        self._paint()

    def get(self) -> str:
        return self.var.get()

    def set(self, value: str, user: bool = False) -> None:
        if value not in self.values:
            return
        self.var.set(value)
        self._paint()
        if user and self.command:
            self.command(value)

    def set_values(self, values: tuple[str, ...], current: str | None = None) -> None:
        for btn in self.buttons.values():
            btn.destroy()
        self.values = values
        self.buttons = {}
        if current not in values:
            current = values[0]
        self.var.set(current)
        for val in values:
            btn = ttk.Button(self, text=val, style="SegOff.TButton", command=lambda v=val: self.set(v, user=True))
            btn.pack(side="left", padx=1, pady=1)
            self.buttons[val] = btn
        self._paint()

    def _paint(self) -> None:
        cur = self.var.get()
        for val, btn in self.buttons.items():
            btn.configure(style="SegOn.TButton" if val == cur else "SegOff.TButton")


def _pin_windows_taskbar(root: tk.Tk, borderless: bool = True) -> None:
    if sys.platform != "win32":
        return
    try:
        root.overrideredirect(borderless)
    except tk.TclError:
        pass
    try:
        root.wm_attributes("-toolwindow", False)
    except tk.TclError:
        pass
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
        root.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        if not hwnd:
            hwnd = int(root.wm_frame(), 16) if root.wm_frame() else root.winfo_id()
        GWL_EXSTYLE = -20
        WS_EX_APPWINDOW = 0x00040000
        WS_EX_TOOLWINDOW = 0x00000080
        style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style = (style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
        ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
        root.withdraw()
        root.after(40, root.deiconify)
    except Exception:
        pass


REQUIRED = (
    ("wn_series.py", "def series_layout"),
    ("wn-epub-extract.py", "class ExtractApp(ttk.Frame)"),
    ("wn-ocr.py", "class OcrApp(ttk.Frame)"),
    ("wn-raw-split.py", "class SplitApp(ttk.Frame)"),
    ("wn-scene-mill.py", "class MillApp(ttk.Frame)"),
)


def _require_frame_siblings() -> None:
    here = Path(__file__).resolve().parent
    stale = []
    for name, needle in REQUIRED:
        path = here / name
        if not path.is_file():
            stale.append(f"{name} missing")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if needle not in text:
            stale.append(f"{name} is the old standalone window — replace it")
    if stale:
        raise SystemExit("Missing siblings:\n  " + "\n  ".join(stale))


def _load_sibling(mod_name: str, filename: str, need: str | None = None):
    path = Path(__file__).resolve().parent / filename
    if not path.is_file():
        raise SystemExit(f"Missing {path}")
    spec = importlib.util.spec_from_file_location(mod_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {filename}")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    if need and not hasattr(mod, need):
        names = [n for n in dir(mod) if n[:1].isupper() or n.endswith("App")]
        raise SystemExit(
            f"{path}\nhas no {need}. Found: {names}\n"
            "Replace this file with artifacts/wn-local-mill/wn-scene-mill.py "
            "(must contain class MillApp(ttk.Frame))."
        )
    return mod


def main() -> None:
    _require_frame_siblings()
    series_mod = _load_sibling("wn_series", "wn_series.py")
    extract_mod = _load_sibling("wn_epub_extract_mod", "wn-epub-extract.py")
    ocr_mod = _load_sibling("wn_ocr_mod", "wn-ocr.py")
    split_mod = _load_sibling("wn_raw_split_mod", "wn-raw-split.py")
    mill_mod = _load_sibling("wn_scene_mill_mod", "wn-scene-mill.py", "MillApp")

    ui = load_ui_settings()
    root = tk.Tk()
    root.title(f"{APP_TITLE} {__version__}")
    root.geometry("1100x780")
    root.minsize(900, 620)
    apply_theme(root, ui["appearance"])
    root.overrideredirect(True)

    chrome = ttk.Frame(root, style="Chrome.TFrame")
    chrome.pack(fill="x")

    drag_x = drag_y = 0

    def start_move(evt) -> None:
        nonlocal drag_x, drag_y
        drag_x, drag_y = evt.x_root, evt.y_root

    def on_move(evt) -> None:
        nonlocal drag_x, drag_y
        dx = evt.x_root - drag_x
        dy = evt.y_root - drag_y
        drag_x, drag_y = evt.x_root, evt.y_root
        root.geometry(f"+{root.winfo_x() + dx}+{root.winfo_y() + dy}")

    chrome.bind("<Button-1>", start_move)
    chrome.bind("<B1-Motion>", on_move)

    # Custom tab strip — ttk.Notebook tabs are hidden (style Hidden.TNotebook).
    tab_keys = ("EPUB", "OCR", "Split", "Mill", "Settings")
    tab_names = UI["tabs"][1 if ui["ui_lang"] == "en" else 0]
    brand = ttk.Label(chrome, text=APP_TITLE, style="Status.TLabel")
    brand.pack(side="left", padx=(12, 16), pady=6)
    brand.bind("<Button-1>", start_move)
    brand.bind("<B1-Motion>", on_move)
    tab_btns: dict[str, ttk.Button] = {}

    def paint_tabs(active: str) -> None:
        for name, btn in tab_btns.items():
            btn.configure(style="TabOn.TButton" if name == active else "Tab.TButton")

    nb = ttk.Notebook(root, style="Hidden.TNotebook")
    nb.pack(fill="both", expand=True)

    extract = extract_mod.ExtractApp(nb)
    ocr = ocr_mod.OcrApp(nb)
    split = split_mod.SplitApp(nb)
    mill = mill_mod.MillApp(nb)
    settings = ttk.Frame(nb)

    nb.add(extract, text="EPUB")
    nb.add(ocr, text="OCR")
    nb.add(split, text="Split")
    nb.add(mill, text="Mill")
    nb.add(settings, text="Settings")

    frames = {"EPUB": extract, "OCR": ocr, "Split": split, "Mill": mill, "Settings": settings}

    def show(name: str) -> None:
        nb.select(frames[name])
        paint_tabs(name)

    for key, label in zip(tab_keys, tab_names):
        btn = ttk.Button(chrome, text=label, style="Tab.TButton", command=lambda n=key: show(n))
        btn.pack(side="left")
        tab_btns[key] = btn

    def minimize() -> None:
        if sys.platform == "win32":
            root.overrideredirect(False)
            root.iconify()

            def _rebar(_evt=None) -> None:
                if root.state() == "normal":
                    root.overrideredirect(True)
                    _pin_windows_taskbar(root, borderless=True)

            root.bind("<Map>", _rebar)
        else:
            root.iconify()

    maximized = {"on": False, "geom": "1100x780"}

    def maximize() -> None:
        if maximized["on"]:
            root.geometry(maximized["geom"])
            maximized["on"] = False
            return
        maximized["geom"] = root.geometry()
        if sys.platform == "win32":
            root.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight() - 40}+0+0")
        else:
            root.geometry(f"{root.winfo_screenwidth()}x{root.winfo_screenheight()}+0+0")
        maximized["on"] = True

    def _on_close() -> None:
        if hasattr(mill, "stop_event"):
            mill.stop_event.set()
        if hasattr(ocr, "stop_event"):
            ocr.stop_event.set()
        root.destroy()

    ttk.Button(chrome, text="✕", style="Close.TButton", command=_on_close).pack(side="right")
    ttk.Button(chrome, text="□", style="Win.TButton", command=maximize).pack(side="right")
    ttk.Button(chrome, text="–", style="Win.TButton", command=minimize).pack(side="right")

    status = ttk.Frame(root, style="Chrome.TFrame")
    status.pack(fill="x", side="bottom")
    ttk.Label(
        status,
        text=f"{APP_TITLE}  {__version__}   ·   web novel + light novel",
        style="Status.TLabel",
    ).pack(side="left", padx=10, pady=4)

    series_var = tk.StringVar(value=str(ui.get("book_folder") or ""))
    pad = {"padx": 10, "pady": 6}
    look = ttk.LabelFrame(settings, text=_ui("appearance", ui["ui_lang"]))
    look.pack(fill="x", padx=10, pady=(12, 4))
    look_row = ttk.Frame(look)
    look_row.pack(anchor="w", padx=8, pady=6)
    ttk.Label(look_row, text=_ui("appearance", ui["ui_lang"])).pack(side="left", padx=(0, 8))
    appear_seg = SegmentedToggle(look_row, values=("System", "Dark", "Light"))
    appear_seg.pack(side="left")
    appear_seg.set({"system": "System", "dark": "Dark", "light": "Light"}.get(ui["appearance"], "System"))
    lang_row = ttk.Frame(look)
    lang_row.pack(anchor="w", padx=8, pady=(0, 8))
    ttk.Label(lang_row, text=_ui("language", ui["ui_lang"])).pack(side="left", padx=(0, 8))
    lang_seg = SegmentedToggle(lang_row, values=("日本語", "English"))
    lang_seg.pack(side="left")
    lang_seg.set("English" if ui["ui_lang"] == "en" else "日本語")

    folder_lbl = ttk.Label(settings, text=_ui("book_folder", ui["ui_lang"]))
    folder_lbl.pack(anchor="w", **pad)
    row = ttk.Frame(settings)
    row.pack(fill="x", padx=10)
    ttk.Entry(row, textvariable=series_var).pack(side="left", fill="x", expand=True)

    def apply_series(switch: str | None = None, source: str | None = None) -> None:
        if source == "ocr":
            guessed = series_mod.infer_series_root(ocr.out_var.get(), ocr.img_var.get())
            if guessed is not None:
                series_var.set(str(guessed))
        elif source == "epub":
            guessed = series_mod.infer_series_root(extract.out_var.get(), extract.img_var.get())
            if guessed is not None:
                series_var.set(str(guessed))
        elif source == "split":
            guessed = series_mod.infer_series_root(split.raw_var.get(), split.out_var.get())
            if guessed is not None:
                series_var.set(str(guessed))
        folder = series_var.get().strip()
        if not folder:
            return
        ui["book_folder"] = folder
        persist_ui()
        layout = series_mod.series_layout(folder)
        series_mod.ensure_dirs(layout)
        for app in (extract, ocr, split, mill):
            fn = getattr(app, "apply_series", None)
            if fn:
                fn(layout)
        if switch == "split":
            show("Split")
        elif switch == "mill":
            show("Mill")
        elif switch == "ocr":
            show("OCR")

    def pick_series() -> None:
        d = filedialog.askdirectory(initialdir=series_var.get())
        if d:
            series_var.set(d)
            apply_series()

    browse_btn = ttk.Button(row, text=_ui("browse", ui["ui_lang"]), command=pick_series)
    browse_btn.pack(side="left", padx=6)
    apply_btn = ttk.Button(row, text=_ui("apply_tabs", ui["ui_lang"]), command=lambda: apply_series())
    apply_btn.pack(side="left")
    hint_lbl = ttk.Label(settings, text=_ui("hint", ui["ui_lang"]), justify="left")
    hint_lbl.pack(anchor="w", padx=10, pady=16)

    def persist_ui() -> None:
        save_ui_settings(ui)

    def on_appearance(value: str) -> None:
        ui["appearance"] = {"System": "system", "Dark": "dark", "Light": "light"}[value]
        persist_ui()
        apply_theme(root, ui["appearance"])

    def on_lang(value: str) -> None:
        ui["ui_lang"] = "en" if value == "English" else "ja"
        persist_ui()
        labels = UI["tabs"][1 if ui["ui_lang"] == "en" else 0]
        for key, label in zip(tab_keys, labels):
            tab_btns[key].configure(text=label)
        look.configure(text=_ui("appearance", ui["ui_lang"]))
        folder_lbl.configure(text=_ui("book_folder", ui["ui_lang"]))
        browse_btn.configure(text=_ui("browse", ui["ui_lang"]))
        apply_btn.configure(text=_ui("apply_tabs", ui["ui_lang"]))
        hint_lbl.configure(text=_ui("hint", ui["ui_lang"]))
        for app in (extract, ocr, split, mill):
            fn = getattr(app, "set_ui_lang", None)
            if fn:
                fn(ui["ui_lang"])

    appear_seg.command = on_appearance
    lang_seg.command = on_lang
    for app in (extract, ocr, split, mill):
        fn = getattr(app, "set_ui_lang", None)
        if fn:
            fn(ui["ui_lang"])

    ocr.handoff_split = lambda: apply_series("split", "ocr")
    extract.handoff_split = lambda: apply_series("split", "epub")
    split.handoff_mill = lambda: apply_series("mill", "split")
    apply_series()
    show("EPUB")

    root.protocol("WM_DELETE_WINDOW", _on_close)
    _pin_windows_taskbar(root, borderless=True)
    root.mainloop()


if __name__ == "__main__":
    main()
