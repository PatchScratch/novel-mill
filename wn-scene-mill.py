#!/usr/bin/env python3
"""
Novel Mill — Mill tab.

One Japanese scene file = one HTTP POST to LM Studio
(/v1/chat/completions). No chat history. No RAG. No second server.

Lock files (prompt.txt, glossary.txt, voices.txt) are concatenated into
the system message. Missing lock → FALLBACK_SYSTEM.

Pause (default 10 s) sits between POSTs so a 3070-class GPU can flush.

Connection settings (API base, model, key, temp, timeout, pause,
context, overwrite) persist to mill.json next to queues.json.
"""
from __future__ import annotations

import json
import queue
import re
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from wn_series import (
    app_version,
    config_dir,
    nat_key,
    read_text,
    strip_page_numbers,
    stitch_en_texts,
    write_text,
)

__version__ = app_version()
APP_TITLE = "Mill"
DEFAULT_BASE = ""
DEFAULT_API = "http://127.0.0.1:1234/v1"
DEFAULT_MODEL = "google/gemma-4-12b-it"
DEFAULT_KEY = "sk-xxx"
USER_PREFIX = (
    "Output the English translation of the following Japanese. "
    "No synopsis, no bullet points, no advice, no Japanese.\n\n<<<\n"
)
USER_SUFFIX = "\n>>>"
SKIP_INPUT = {"raw_full.txt", "raw.txt", "raw_full.en.txt"}
MIN_SCENE_CHARS = 80
SKIP_NAME = re.compile(
    r"(?:_break|_front|p-caution|(?:^|_)\d*_p-\d+|\bp-\d+)",
    re.I,
)
FALLBACK_SYSTEM = (
    "Japanese-to-English web novel translator. English only. "
    "Keep 「」『』（）！？…〜ー. Convert only 。→. and 、→,. "
    "「」 spoken. （） inner voice of the person who just acted, first person. "
    "Onomatopoeia in romaji (Bassaa, Kyaa). No Slash/WHOOSH."
)


def build_system(lock_dir: Path | None) -> str:
    parts = []
    if lock_dir is not None:
        for name in ("prompt.txt", "glossary.txt", "voices.txt"):
            p = lock_dir / name
            if p.is_file():
                parts.append(f"## {name}\n{read_text(p).strip()}")
    return "\n\n".join(parts) if parts else FALLBACK_SYSTEM


def scene_files(in_dir: Path) -> list[Path]:
    files = []
    for p in in_dir.iterdir():
        if not p.is_file() or p.suffix.lower() != ".txt":
            continue
        if p.name.lower() in SKIP_INPUT:
            continue
        if SKIP_NAME.search(p.stem):
            continue
        files.append(p)
    return sorted(files, key=nat_key)


def out_path_for(src: Path, out_dir: Path) -> Path:
    return out_dir / f"{src.stem}.en.txt"


def queue_store_path() -> Path:
    """Local only. Not written into the repo or the book folder."""
    return config_dir() / "queues.json"


def mill_settings_path() -> Path:
    """Local only. Connection settings survive restarts."""
    return config_dir() / "mill.json"


def load_mill_settings() -> dict:
    """Validated values for the setting vars; junk drops out, not in."""
    try:
        raw = json.loads(mill_settings_path().read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict = {}
    for key in ("api", "key", "model"):
        v = raw.get(key)
        if isinstance(v, str) and v.strip():
            out[key] = v
    for key in ("temp", "pause"):
        try:
            float(raw.get(key))
            out[key] = str(raw[key])
        except (TypeError, ValueError):
            pass
    for key in ("timeout", "ctx"):
        try:
            out[key] = str(int(raw.get(key)))
        except (TypeError, ValueError):
            pass
    if isinstance(raw.get("overwrite"), bool):
        out["overwrite"] = raw["overwrite"]
    return out


def save_mill_settings(data: dict) -> None:
    path = mill_settings_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def post_chat(api_base, api_key, model, system, user, temperature, timeout, max_tokens=None) -> str:
    """One OpenAI-style chat completion. Caller owns retry and pause."""
    url = api_base.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if max_tokens and max_tokens > 0:
        body["max_tokens"] = int(max_tokens)
    req = Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:800]}") from e
    except URLError as e:
        raise RuntimeError(f"Cannot reach LM Studio at {url}. ({e})") from e
    if "error" in payload:
        raise RuntimeError(str(payload["error"]))
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("Empty choices from API")
    return ((choices[0].get("message") or {}).get("content")) or ""


class MillApp(ttk.Frame):
    def __init__(self, master: tk.Misc | None = None) -> None:
        own = master is None
        if own:
            master = tk.Tk()
            master.title(APP_TITLE)
            master.geometry("920x640")
            master.minsize(760, 520)
        super().__init__(master)
        if own:
            self.pack(fill="both", expand=True)
        self._own_root = master if own else None
        self.stop_event = threading.Event()
        self.worker = None
        self.log_q = queue.Queue()
        self.ui_q: queue.Queue = queue.Queue()
        self.series_var = tk.StringVar(value="")
        self.in_var = tk.StringVar(value="")
        self.out_var = tk.StringVar(value="")
        self.lock_var = tk.StringVar(value="")
        saved = load_mill_settings()
        self.api_var = tk.StringVar(value=saved.get("api") or DEFAULT_API)
        self.model_var = tk.StringVar(value=saved.get("model") or DEFAULT_MODEL)
        self.key_var = tk.StringVar(value=saved.get("key") or DEFAULT_KEY)
        self.temp_var = tk.StringVar(value=saved.get("temp") or "0.1")
        self.timeout_var = tk.StringVar(value=saved.get("timeout") or "1200")
        self.pause_var = tk.StringVar(value=saved.get("pause") or "10")
        self.ctx_var = tk.StringVar(value=saved.get("ctx") or "8192")
        self.overwrite_var = tk.BooleanVar(value=saved.get("overwrite", False))
        for var in (
            self.api_var, self.key_var, self.model_var, self.temp_var,
            self.timeout_var, self.pause_var, self.ctx_var, self.overwrite_var,
        ):
            var.trace_add("write", lambda *_: self._save_mill_settings())
        self.status_var = tk.StringVar(value="Idle. LM Studio server must be running.")
        self._build()
        self.after(120, self._drain_log)
        if self._own_root is not None:
            self._own_root.protocol("WM_DELETE_WINDOW", self._on_close)

    def apply_series(self, layout: dict) -> None:
        self.series_var.set(str(layout["series"]))
        self.in_var.set(str(layout["in_dir"]))
        self.out_var.set(str(layout["out_dir"]))
        if layout["lock"].is_dir():
            self.lock_var.set(str(layout["lock"]))
        self._refresh_scenes()

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True)
        paths = ttk.LabelFrame(frm, text="Folders")
        paths.pack(fill="x", **pad)
        self._row_dir(paths, 0, "Series", self.series_var, self._pick_series)
        self._row_dir(paths, 1, "Scenes (in)", self.in_var, lambda: self._pick_dir(self.in_var))
        self._row_dir(paths, 2, "English (out)", self.out_var, lambda: self._pick_dir(self.out_var))
        self._row_dir(paths, 3, "Lock files", self.lock_var, lambda: self._pick_dir(self.lock_var))
        api = ttk.LabelFrame(frm, text="LM Studio")
        api.pack(fill="x", **pad)
        ttk.Label(api, text="API base").grid(row=0, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(api, textvariable=self.api_var).grid(row=0, column=1, sticky="ew")
        ttk.Label(api, text="Model").grid(row=0, column=2, sticky="w", padx=6)
        ttk.Entry(api, textvariable=self.model_var).grid(row=0, column=3, sticky="ew")
        ttk.Label(api, text="Key").grid(row=1, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(api, textvariable=self.key_var, width=16).grid(row=1, column=1, sticky="w")
        ttk.Label(api, text="Temp").grid(row=1, column=2, sticky="w", padx=6)
        ttk.Entry(api, textvariable=self.temp_var, width=8).grid(row=1, column=3, sticky="ew")
        ttk.Label(api, text="Timeout s").grid(row=1, column=4, sticky="w", padx=6)
        ttk.Entry(api, textvariable=self.timeout_var, width=8).grid(row=1, column=5, sticky="w")
        ttk.Label(api, text="Context").grid(row=2, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(api, textvariable=self.ctx_var, width=8).grid(row=2, column=1, sticky="w")
        ttk.Label(api, text="Pause s").grid(row=2, column=2, sticky="w", padx=6)
        ttk.Entry(api, textvariable=self.pause_var, width=8).grid(row=2, column=3, sticky="w")
        self.overwrite_lbl = ttk.Label(api, text="Existing .en.txt")
        self.overwrite_lbl.grid(row=3, column=0, sticky="w", padx=6, pady=3)
        ow = ttk.Frame(api, style="Seg.TFrame")
        ow.grid(row=3, column=1, columnspan=2, sticky="w", padx=6, pady=3)
        self._ow_keep = ttk.Button(ow, text="Keep existing", style="SegOn.TButton", command=lambda: self._set_overwrite(False))
        self._ow_over = ttk.Button(ow, text="Overwrite", style="SegOff.TButton", command=lambda: self._set_overwrite(True))
        self._ow_keep.pack(side="left", padx=1, pady=1)
        self._ow_over.pack(side="left", padx=1, pady=1)
        self._ui_lang = "en"
        self._paint_overwrite()
        api.columnconfigure(1, weight=1)
        api.columnconfigure(3, weight=1)
        btns = ttk.Frame(frm)
        btns.pack(fill="x", **pad)
        self.start_btn = ttk.Button(btns, text="Start selected", command=self._start)
        self.start_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(btns, text="Stop after this file", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        ttk.Button(btns, text="Make folders", command=self._make_folders).pack(side="left", padx=4)
        ttk.Button(btns, text="Ping API", command=self._ping).pack(side="left", padx=4)
        ttk.Button(btns, text="Combine out → one file", command=self._combine_out).pack(side="left", padx=4)
        pick = ttk.LabelFrame(frm, text="Scenes to mill")
        pick.pack(fill="both", expand=True, **pad)
        self.pick_fr = pick
        prow = ttk.Frame(pick)
        prow.pack(fill="x", padx=4, pady=2)
        self.btn_refresh = ttk.Button(prow, text="Refresh", command=self._refresh_scenes)
        self.btn_refresh.pack(side="left", padx=2)
        self.btn_missing = ttk.Button(prow, text="Missing only", command=self._pick_missing)
        self.btn_missing.pack(side="left", padx=2)
        self.btn_all = ttk.Button(prow, text="All", command=self._pick_all)
        self.btn_all.pack(side="left", padx=2)
        self.btn_none = ttk.Button(prow, text="None", command=self._pick_none)
        self.btn_none.pack(side="left", padx=2)
        self.pick_count = tk.StringVar(value="0 selected")
        ttk.Label(prow, textvariable=self.pick_count).pack(side="left", padx=8)
        self.scene_list = tk.Listbox(pick, height=10, activestyle="none", selectmode="browse")
        self.scene_list.pack(side="left", fill="both", expand=True, padx=(4, 0), pady=4)
        self.scene_list.bind("<Button-1>", self._toggle_scene)
        sc = ttk.Scrollbar(pick, command=self.scene_list.yview)
        self.scene_list.configure(yscrollcommand=sc.set)
        sc.pack(side="right", fill="y", pady=4)
        self._scenes: list[Path] = []
        self._picked: set[str] = set()
        self.progress = ttk.Progressbar(frm, mode="determinate")
        self.progress.pack(fill="x", padx=8, pady=2)
        ttk.Label(frm, textvariable=self.status_var).pack(anchor="w", padx=10)
        logf = ttk.LabelFrame(frm, text="Log")
        logf.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(logf, height=8, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(logf, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

    def _set_overwrite(self, on: bool) -> None:
        self.overwrite_var.set(on)
        self._paint_overwrite()

    def _paint_overwrite(self) -> None:
        on = bool(self.overwrite_var.get())
        self._ow_keep.configure(style="SegOff.TButton" if on else "SegOn.TButton")
        self._ow_over.configure(style="SegOn.TButton" if on else "SegOff.TButton")

    def set_ui_lang(self, lang: str) -> None:
        self._ui_lang = "en" if lang == "en" else "ja"
        if self._ui_lang == "ja":
            self.overwrite_lbl.configure(text="既存の .en.txt")
            self._ow_keep.configure(text="既存を残す")
            self._ow_over.configure(text="上書きする")
        else:
            self.overwrite_lbl.configure(text="Existing .en.txt")
            self._ow_keep.configure(text="Keep existing")
            self._ow_over.configure(text="Overwrite")
        ja = self._ui_lang == "ja"
        self.pick_fr.configure(text="ミルするシーン" if ja else "Scenes to mill")
        self.btn_refresh.configure(text="再読込" if ja else "Refresh")
        self.btn_missing.configure(text="未完了のみ" if ja else "Missing only")
        self.btn_all.configure(text="全部" if ja else "All")
        self.btn_none.configure(text="解除" if ja else "None")
        self.start_btn.configure(text="選択を開始" if ja else "Start selected")

    def _load_saved_pick(self, in_dir: Path) -> set[str] | None:
        try:
            raw = json.loads(queue_store_path().read_text(encoding="utf-8"))
            names = raw.get(str(in_dir))
            if isinstance(names, list):
                return {str(n) for n in names}
        except Exception:
            return None
        return None

    def _save_pick(self) -> None:
        in_dir = self.in_var.get().strip()
        if not in_dir:
            return
        path = queue_store_path()
        data: dict = {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        except Exception:
            data = {}
        data[in_dir] = sorted(self._picked)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    def _save_mill_settings(self) -> None:
        save_mill_settings(
            {
                "api": self.api_var.get().strip(),
                "key": self.key_var.get().strip(),
                "model": self.model_var.get().strip(),
                "temp": self.temp_var.get().strip(),
                "timeout": self.timeout_var.get().strip(),
                "pause": self.pause_var.get().strip(),
                "ctx": self.ctx_var.get().strip(),
                "overwrite": bool(self.overwrite_var.get()),
            }
        )

    def _refresh_scenes(self, keep: bool = True) -> None:
        in_dir = Path(self.in_var.get().strip()) if self.in_var.get().strip() else None
        self.scene_list.delete(0, "end")
        self._scenes = scene_files(in_dir) if in_dir and in_dir.is_dir() else []
        saved = self._load_saved_pick(in_dir) if in_dir else None
        if keep and saved is not None:
            self._picked = {p.name for p in self._scenes if p.name in saved}
        elif not keep:
            pass
        else:
            out_dir = Path(self.out_var.get().strip()) if self.out_var.get().strip() else None
            self._picked = {
                p.name for p in self._scenes
                if out_dir is None or not out_path_for(p, out_dir).is_file()
            }
        self._paint_scenes()

    def _paint_scenes(self) -> None:
        self.scene_list.delete(0, "end")
        out_dir = Path(self.out_var.get().strip()) if self.out_var.get().strip() else None
        done_word = "完了" if getattr(self, "_ui_lang", "en") == "ja" else "done"
        pend_word = "未完了" if getattr(self, "_ui_lang", "en") == "ja" else "pending"
        for p in self._scenes:
            mark = "x" if p.name in self._picked else " "
            state = done_word if out_dir and out_path_for(p, out_dir).is_file() else pend_word
            self.scene_list.insert("end", f"[{mark}]  {p.name}    {state}")
        n = len(self._picked)
        self.pick_count.set(f"{n} selected" if getattr(self, "_ui_lang", "en") != "ja" else f"{n} 件選択")

    def _toggle_scene(self, event) -> str:
        idx = self.scene_list.nearest(event.y)
        if idx < 0 or idx >= len(self._scenes):
            return "break"
        bbox = self.scene_list.bbox(idx)
        if not bbox or not (bbox[1] <= event.y <= bbox[1] + bbox[3]):
            return "break"
        name = self._scenes[idx].name
        if name in self._picked:
            self._picked.discard(name)
        else:
            self._picked.add(name)
        self._save_pick()
        self._paint_scenes()
        self.scene_list.see(idx)
        return "break"

    def _pick_missing(self) -> None:
        out_dir = Path(self.out_var.get().strip()) if self.out_var.get().strip() else None
        self._picked = {
            p.name for p in self._scenes
            if out_dir is None or not out_path_for(p, out_dir).is_file()
        }
        self._save_pick()
        self._paint_scenes()

    def _pick_all(self) -> None:
        self._picked = {p.name for p in self._scenes}
        self._save_pick()
        self._paint_scenes()

    def _pick_none(self) -> None:
        self._picked = set()
        self._save_pick()
        self._paint_scenes()

    def _row_dir(self, parent, row, label, var, cmd) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(parent, textvariable=var).grid(row=row, column=1, sticky="ew", padx=4)
        ttk.Button(parent, text="Browse", command=cmd).grid(row=row, column=2, padx=6)
        parent.columnconfigure(1, weight=1)

    def _pick_series(self) -> None:
        d = filedialog.askdirectory(initialdir=self.series_var.get() or DEFAULT_BASE)
        if not d:
            return
        self.series_var.set(d)
        self.in_var.set(str(Path(d) / "in"))
        self.out_var.set(str(Path(d) / "out"))
        lock = Path(d) / "lock"
        if lock.is_dir():
            self.lock_var.set(str(lock))
        self._refresh_scenes()

    def _pick_dir(self, var: tk.StringVar) -> None:
        d = filedialog.askdirectory(initialdir=var.get() or DEFAULT_BASE)
        if d:
            var.set(d)

    def _make_folders(self) -> None:
        for var in (self.in_var, self.out_var, self.lock_var):
            Path(var.get()).mkdir(parents=True, exist_ok=True)
        self.status_var.set("Folders ready.")

    def _ping(self) -> None:
        url = self.api_var.get().rstrip("/") + "/models"
        try:
            req = Request(url, headers={"Authorization": f"Bearer {self.key_var.get() or DEFAULT_KEY}"})
            with urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            ids = [m.get("id") for m in (data.get("data") or []) if m.get("id")]
            self._log("Models: " + (", ".join(ids) or "(none)"))
            self.status_var.set("API ok.")
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))

    def _combine_out(self) -> None:
        out_dir = Path(self.out_var.get().strip())
        series = Path(self.series_var.get().strip() or out_dir.parent)
        dest = series / "english_full.txt"
        try:
            n, dest = stitch_en_texts(out_dir, dest)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))
            return
        self.status_var.set(f"Combined {n} EN files → {dest}")
        self._log(f"Combined {n} files → {dest}")
        messagebox.showinfo(APP_TITLE, f"Wrote {n} shards to:\n{dest}")

    def _on_close(self) -> None:
        self.stop_event.set()
        (self._own_root or self.winfo_toplevel()).destroy()

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        in_txt = self.in_var.get().strip()
        out_txt = self.out_var.get().strip()
        lock_txt = self.lock_var.get().strip()
        if not in_txt or not out_txt:
            messagebox.showerror(APP_TITLE, "Scenes (in) and English (out) folders are both required.")
            return
        in_dir = Path(in_txt)
        if not in_dir.is_dir():
            messagebox.showerror(APP_TITLE, f"Input folder missing:\n{in_dir}")
            return
        files = [p for p in scene_files(in_dir) if p.name in self._picked]
        if not files:
            messagebox.showerror(APP_TITLE, "No scenes checked. Refresh, then tick the files to mill.")
            return
        try:
            temp = float(self.temp_var.get())
            timeout = int(self.timeout_var.get())
            pause = float(self.pause_var.get())
            ctx = int(self.ctx_var.get())
        except ValueError:
            messagebox.showerror(APP_TITLE, "Temp, timeout, pause, and context must be numbers.")
            return
        self.stop_event.clear()
        self._set_running(True)
        self.progress["value"] = 0
        self.progress["maximum"] = len(files)
        self.worker = threading.Thread(
            target=self._run_queue,
            args=(
                files,
                Path(out_txt),
                Path(lock_txt) if lock_txt else None,
                self.api_var.get().strip(),
                self.key_var.get().strip() or DEFAULT_KEY,
                self.model_var.get().strip(),
                temp,
                timeout,
                self.overwrite_var.get(),
                pause,
                ctx,
            ),
            daemon=True,
        )
        self.worker.start()

    def _set_running(self, on: bool) -> None:
        self.start_btn.configure(state="disabled" if on else "normal")
        self.stop_btn.configure(state="normal" if on else "disabled")

    def _stop(self) -> None:
        self.stop_event.set()
        self.status_var.set("Stopping after current file…")
        self._log("Stop requested.")

    def _run_queue(self, files, out_dir, lock_dir, api, key, model, temp, timeout, overwrite, pause=4.0, ctx=8192):
        try:
            system = build_system(lock_dir)
            self._log(f"Mill {__version__}  timeout={timeout}s pause={pause}s ctx={ctx}")
            self._log(f"System prompt {len(system)} chars from {lock_dir or '(no lock folder)'}")
            done = skip = fail = 0
            streak = 0
            total = len(files)
            for i, src in enumerate(files, start=1):
                if self.stop_event.is_set():
                    self._log("Stopped.")
                    break
                dest = out_path_for(src, out_dir)
                self._ui(lambda m=f"{i}/{total}  {src.name}": self.status_var.set(m))
                if dest.exists() and not overwrite:
                    self._log(f"SKIP {src.name} (exists {dest.name})")
                    skip += 1
                    self._ui(lambda v=i: self.progress.configure(value=v))
                    continue
                try:
                    jp = strip_page_numbers(read_text(src)).strip()
                except Exception as e:
                    self._log(f"SKIP {src.name} (unreadable: {e})")
                    skip += 1
                    self._ui(lambda v=i: self.progress.configure(value=v))
                    continue
                if not jp:
                    self._log(f"SKIP {src.name} (empty)")
                    skip += 1
                    self._ui(lambda v=i: self.progress.configure(value=v))
                    continue
                if len(jp) < MIN_SCENE_CHARS:
                    self._log(f"SKIP {src.name} ({len(jp)} chars, stub)")
                    skip += 1
                    self._ui(lambda v=i: self.progress.configure(value=v))
                    continue
                user = USER_PREFIX + jp + USER_SUFFIX
                # Japanese ≈ 1 token/char, ASCII ≈ 4 chars/token. Underestimating
                # here makes max_tokens overshoot the loaded context.
                wide = sum(1 for ch in user if ord(ch) >= 0x2E80)
                prompt_est = max(1, round(wide * 1.1 + (len(user) - wide) * 0.3 + len(system) * 0.3))
                max_tok = max(128, ctx - prompt_est)
                self._log(f"SEND {src.name}  ({len(jp)} chars ~{prompt_est} tok, max_out={max_tok})")
                t0 = time.time()
                en = ""
                err = ""
                try:
                    en = post_chat(api, key, model, system, user, temp, timeout, max_tok)
                except Exception as e:
                    err = str(e)
                    low = err.lower()
                    if "exceeds" in low and "context" in low:
                        # Estimate was optimistic; one retry with a minimal output budget.
                        try:
                            en = post_chat(api, key, model, system, user, temp, timeout, 256)
                            err = ""
                        except Exception:
                            pass
                    elif any(k in low for k in ("timed out", "channel", "fetch failed", "cannot reach", "refused")):
                        self._log(f"{src.name}: {err.split(':')[0]}. Cool 45s then retry once")
                        self._pause(45)
                        if self.stop_event.is_set():
                            break
                        try:
                            en = post_chat(api, key, model, system, user, temp, timeout, max_tok)
                            err = ""
                        except Exception as e2:
                            err = str(e2)
                if not err and not (en or "").strip():
                    err = "empty completion"
                if err:
                    fail += 1
                    streak += 1
                    self._log(f"FAIL {src.name}: {err}")
                    if "exceeds" in err.lower() and "context" in err.lower():
                        self._log("Context overflow. Split this scene smaller.")
                    self._ui(lambda v=i: self.progress.configure(value=v))
                    if streak >= 3:
                        self._log("Three LMS faults in a row. Stopping so the GPU can recover.")
                        break
                    self._pause(max(pause, 20))
                    continue
                streak = 0
                en = en.replace("\r\n", "\n").strip()
                while en.endswith("⸻") or en.endswith("─") or en.endswith("—"):
                    en = en.rstrip(" \t\n─—–―⸻")
                write_text(dest, en + "\n")
                done += 1
                self._log(f"OK   {dest.name}  {len(en)} chars  {time.time() - t0:.1f}s")
                self._ui(lambda v=i: self.progress.configure(value=v))
                self._pause(pause)
            msg = f"Done. ok={done} skip={skip} fail={fail}"
            self._ui(lambda m=msg: self.status_var.set(m))
            self._log(msg)
            self._ui(self._refresh_scenes)
        finally:
            self._ui(lambda: self._set_running(False))

    def _pause(self, seconds: float) -> None:
        if seconds <= 0:
            return
        self._log(f"Wait {seconds:.0f}s")
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self.stop_event.is_set():
                return
            time.sleep(0.2)

    def _log(self, msg: str) -> None:
        self.log_q.put(time.strftime("%H:%M:%S ") + msg)

    def _ui(self, fn) -> None:
        """Marshal a UI update from the worker thread onto the Tk main loop."""
        self.ui_q.put(fn)

    def _drain_log(self) -> None:
        try:
            while True:
                fn = self.ui_q.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except queue.Empty:
            pass
        try:
            while True:
                line = self.log_q.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", line + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(120, self._drain_log)

    def mainloop(self, n: int = 0):
        (self._own_root or self.winfo_toplevel()).mainloop(n)


def main() -> None:
    MillApp().mainloop()


if __name__ == "__main__":
    main()
