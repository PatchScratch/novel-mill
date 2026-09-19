#!/usr/bin/env python3
# WN Scene Mill — dumb file loop to LM Studio (OpenAI-compatible).
# One scene per request. No chat history. No RAG.
# Windows: py -3 wn-scene-mill.py

from __future__ import annotations

import json
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

__version__ = "1.0.0"
APP_TITLE = "WN Scene Mill"
DEFAULT_BASE = r"D:\Translation Software\WN-Work\_series\n7183mn"
DEFAULT_API = "http://127.0.0.1:1234/v1"
DEFAULT_MODEL = "google/gemma-4-12b-it"
DEFAULT_KEY = "sk-xxx"
USER_PREFIX = (
    "Output the English translation of the following Japanese. "
    "No synopsis, no bullet points, no advice, no Japanese.\n\n<<<\n"
)
USER_SUFFIX = "\n>>>"


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_system(lock_dir: Path) -> str:
    parts: list[str] = []
    for name in ("prompt.txt", "glossary.txt", "voices.txt"):
        p = lock_dir / name
        if p.is_file():
            parts.append(f"## {name}\n{read_text(p).strip()}")
    if not parts:
        parts.append(
            "Japanese-to-English web novel translator. English only.\n"
            "Keep 「」『』（）！？…〜ー. Convert only 。 to . and 、 to ,.\n"
            "「」 spoken. （） inner voice of the person who just acted, FIRST PERSON.\n"
            "Onomatopoeia in romaji (Bassaa, Kyaa). No Slash/WHOOSH."
        )
    return "\n\n".join(parts)


def scene_files(in_dir: Path) -> list[Path]:
    files = [p for p in in_dir.iterdir() if p.is_file() and p.suffix.lower() == ".txt"]
    return sorted(files, key=lambda p: p.name.lower())


def out_path_for(src: Path, out_dir: Path) -> Path:
    return out_dir / f"{src.stem}.en.txt"


def post_chat(
    api_base: str,
    api_key: str,
    model: str,
    system: str,
    user: str,
    temperature: float,
    timeout: int,
) -> str:
    url = api_base.rstrip("/") + "/chat/completions"
    body = {
        "model": model,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    raw = json.dumps(body).encode("utf-8")
    req = Request(
        url,
        data=raw,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
    )
    try:
        with urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {detail[:800]}") from e
    except URLError as e:
        raise RuntimeError(
            f"Cannot reach LM Studio at {url}. Start Developer server on port 1234. ({e})"
        ) from e

    if "error" in payload:
        raise RuntimeError(str(payload["error"]))

    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("Empty choices from API")
    msg = choices[0].get("message") or {}
    text = (msg.get("content") or "").strip()
    if not text:
        reason = choices[0].get("finish_reason")
        raise RuntimeError(f"Empty content (finish_reason={reason})")
    return text


class MillApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("920x640")
        self.minsize(760, 520)

        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.log_q: queue.Queue[str] = queue.Queue()

        self.series_var = tk.StringVar(value=DEFAULT_BASE)
        self.in_var = tk.StringVar(value=str(Path(DEFAULT_BASE) / "in"))
        self.out_var = tk.StringVar(value=str(Path(DEFAULT_BASE) / "out"))
        self.lock_var = tk.StringVar(value=str(Path(DEFAULT_BASE) / "lock"))
        self.api_var = tk.StringVar(value=DEFAULT_API)
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.key_var = tk.StringVar(value=DEFAULT_KEY)
        self.temp_var = tk.StringVar(value="0.1")
        self.timeout_var = tk.StringVar(value="600")
        self.overwrite_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Idle. LM Studio server must be running.")

        self._build()
        self.after(120, self._drain_log)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self)
        frm.pack(fill="both", expand=True)

        paths = ttk.LabelFrame(frm, text="Folders")
        paths.pack(fill="x", **pad)
        self._row_dir(paths, 0, "Series", self.series_var, self._pick_series)
        self._row_dir(paths, 1, "Input scenes", self.in_var, lambda: self._pick_dir(self.in_var))
        self._row_dir(paths, 2, "Output EN", self.out_var, lambda: self._pick_dir(self.out_var))
        self._row_dir(paths, 3, "Lock files", self.lock_var, lambda: self._pick_dir(self.lock_var))

        api = ttk.LabelFrame(frm, text="LM Studio")
        api.pack(fill="x", **pad)
        ttk.Label(api, text="API base").grid(row=0, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(api, textvariable=self.api_var, width=36).grid(row=0, column=1, sticky="ew")
        ttk.Label(api, text="Model").grid(row=0, column=2, sticky="w", padx=6)
        ttk.Entry(api, textvariable=self.model_var, width=28).grid(row=0, column=3, sticky="ew")
        ttk.Label(api, text="Key").grid(row=1, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(api, textvariable=self.key_var, width=16).grid(row=1, column=1, sticky="w")
        ttk.Label(api, text="Temp").grid(row=1, column=2, sticky="w", padx=6)
        ttk.Entry(api, textvariable=self.temp_var, width=8).grid(row=1, column=3, sticky="w")
        ttk.Label(api, text="Timeout s").grid(row=1, column=3, sticky="e", padx=(120, 6))
        ttk.Entry(api, textvariable=self.timeout_var, width=8).grid(row=1, column=3, sticky="e")
        ttk.Checkbutton(
            api, text="Overwrite existing .en.txt", variable=self.overwrite_var
        ).grid(row=2, column=1, columnspan=2, sticky="w", padx=6, pady=3)
        api.columnconfigure(1, weight=1)
        api.columnconfigure(3, weight=1)

        btns = ttk.Frame(frm)
        btns.pack(fill="x", **pad)
        self.start_btn = ttk.Button(btns, text="Start queue", command=self._start)
        self.start_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(btns, text="Stop after this file", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        ttk.Button(btns, text="Make folders", command=self._make_folders).pack(side="left", padx=4)
        ttk.Button(btns, text="Ping API", command=self._ping).pack(side="left", padx=4)

        self.progress = ttk.Progressbar(frm, mode="determinate")
        self.progress.pack(fill="x", padx=8, pady=2)
        ttk.Label(frm, textvariable=self.status_var).pack(anchor="w", padx=10)

        logf = ttk.LabelFrame(frm, text="Log")
        logf.pack(fill="both", expand=True, **pad)
        self.log = tk.Text(logf, height=16, wrap="word", state="disabled")
        scroll = ttk.Scrollbar(logf, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)
        self.log.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        hint = (
            "One scene file = one API call. No history. RAG must be uninstalled. "
            "Context 4096: keep lock short and scenes split."
        )
        ttk.Label(frm, text=hint, foreground="#444").pack(anchor="w", padx=10, pady=(0, 8))

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
        self.lock_var.set(str(Path(d) / "lock"))

    def _pick_dir(self, var: tk.StringVar) -> None:
        d = filedialog.askdirectory(initialdir=var.get() or DEFAULT_BASE)
        if d:
            var.set(d)

    def _make_folders(self) -> None:
        for v in (self.in_var, self.out_var, self.lock_var):
            Path(v.get()).mkdir(parents=True, exist_ok=True)
        lock = Path(self.lock_var.get())
        samples = {
            "prompt.txt": (
                "Japanese-to-English web novel translator. English only. "
                "No refusal, synopsis, notes, or Japanese output.\n"
                "Keep 「」『』（）！？…〜ー. Convert only 。 to . and 、 to ,.\n"
                "「」 = spoken. （） = inner voice of the person who just acted or spoke, FIRST PERSON.\n"
                "Onomatopoeia: romaji only (Bassaa, Kyaa). No Slash/WHOOSH/BAM.\n"
                "Drop 青空 ［＃…］ markup rather than explaining it.\n"
            ),
            "glossary.txt": "小泉晴道 = Harumichi Koizumi\n如月千紗 = Chisa Kisaragi\n",
            "voices.txt": (
                "（） after Chisa acts/speaks: I is Chisa.\n"
                "あんなに元気 in that thought is Harumichi, not Chisa.\n"
            ),
        }
        created = []
        for name, text in samples.items():
            p = lock / name
            if not p.exists():
                write_text(p, text)
                created.append(name)
        self._log(f"Folders ready. Sample lock written: {', '.join(created) or 'already existed'}")
        messagebox.showinfo(APP_TITLE, "Created in / out / lock (sample lock files if missing).")

    def _ping(self) -> None:
        url = self.api_var.get().rstrip("/") + "/models"
        try:
            req = Request(url, headers={"Authorization": f"Bearer {self.key_var.get()}"})
            with urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
            self._log("API OK. Models: " + (", ".join(ids) if ids else "(none listed)"))
            if ids and self.model_var.get() not in ids:
                self._log("Warning: configured model name is not in the list. Copy one id into Model.")
        except Exception as e:
            self._log(f"Ping failed: {e}")
            messagebox.showerror(APP_TITLE, str(e))

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        in_dir = Path(self.in_var.get())
        out_dir = Path(self.out_var.get())
        lock_dir = Path(self.lock_var.get())
        if not in_dir.is_dir():
            messagebox.showerror(APP_TITLE, f"Input folder missing:\n{in_dir}")
            return
        files = scene_files(in_dir)
        if not files:
            messagebox.showerror(APP_TITLE, f"No .txt files in:\n{in_dir}")
            return
        try:
            temp = float(self.temp_var.get())
            timeout = int(self.timeout_var.get())
        except ValueError:
            messagebox.showerror(APP_TITLE, "Temp must be a float, timeout an integer.")
            return

        self.stop_event.clear()
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress["value"] = 0
        self.progress["maximum"] = len(files)
        self.worker = threading.Thread(
            target=self._run_queue,
            args=(
                files,
                out_dir,
                lock_dir,
                self.api_var.get().strip(),
                self.key_var.get().strip() or DEFAULT_KEY,
                self.model_var.get().strip(),
                temp,
                timeout,
                self.overwrite_var.get(),
            ),
            daemon=True,
        )
        self.worker.start()

    def _stop(self) -> None:
        self.stop_event.set()
        self.status_var.set("Stopping after current file…")
        self._log("Stop requested.")

    def _run_queue(
        self,
        files: list[Path],
        out_dir: Path,
        lock_dir: Path,
        api: str,
        key: str,
        model: str,
        temp: float,
        timeout: int,
        overwrite: bool,
    ) -> None:
        try:
            system = build_system(lock_dir)
            self._log(f"System prompt {len(system)} chars from {lock_dir}")
            done = skip = fail = 0
            total = len(files)
            for i, src in enumerate(files, start=1):
                if self.stop_event.is_set():
                    self._log("Stopped.")
                    break
                dest = out_path_for(src, out_dir)
                self.status_var.set(f"{i}/{total}  {src.name}")
                if dest.exists() and not overwrite:
                    self._log(f"SKIP {src.name} (exists {dest.name})")
                    skip += 1
                    self.progress["value"] = i
                    continue
                jp = read_text(src).strip()
                if not jp:
                    self._log(f"SKIP {src.name} (empty)")
                    skip += 1
                    self.progress["value"] = i
                    continue
                user = USER_PREFIX + jp + USER_SUFFIX
                self._log(f"SEND {src.name}  ({len(jp)} chars)")
                t0 = time.time()
                try:
                    en = post_chat(api, key, model, system, user, temp, timeout)
                except Exception as e:
                    fail += 1
                    self._log(f"FAIL {src.name}: {e}")
                    if "exceeds" in str(e).lower() and "context" in str(e).lower():
                        self._log("Context overflow. Split this scene smaller.")
                    break
                elapsed = time.time() - t0
                write_text(dest, en + "\n")
                done += 1
                self._log(f"OK   {dest.name}  {len(en)} chars  {elapsed:.1f}s")
                self.progress["value"] = i
            self.status_var.set(f"Done. ok={done} skip={skip} fail={fail}")
            self._log(self.status_var.get())
        finally:
            self.start_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")

    def _log(self, msg: str) -> None:
        self.log_q.put(time.strftime("%H:%M:%S ") + msg)

    def _drain_log(self) -> None:
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

    def _on_close(self) -> None:
        self.stop_event.set()
        self.destroy()


def main() -> None:
    MillApp().mainloop()


if __name__ == "__main__":
    main()
