#!/usr/bin/env python3
# Novel Mill — OCR tab. Tesseract on a folder of page images → ocr\*.ocr.txt.
# Separate from EPUB extract. Windows: py -3 wn-ocr.py

from __future__ import annotations

import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

__version__ = "1.4.3"
APP_TITLE = "OCR"
DEFAULT_IMG = ""
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tif", ".tiff"}
OCR_EXT = {".jpg", ".jpeg", ".png", ".gif", ".tif", ".tiff", ".bmp", ".webp"}
TESS_CANDIDATES = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    "/usr/bin/tesseract",
    "tesseract",
)


def find_tesseract(explicit: str = "") -> str | None:
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return str(p)
        found = shutil.which(explicit)
        if found:
            return found
    for cand in TESS_CANDIDATES:
        path = Path(cand)
        if path.is_file():
            return str(path)
        found = shutil.which(cand)
        if found:
            return found
    return None


def _ascii_safe(path: Path) -> bool:
    try:
        str(path).encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


_LANG_CACHE: dict[str, set[str]] = {}


def tess_langs(tess: str) -> set[str]:
    if tess in _LANG_CACHE:
        return _LANG_CACHE[tess]
    try:
        proc = subprocess.run([tess, "--list-langs"], capture_output=True, timeout=15, check=False)
    except Exception:
        _LANG_CACHE[tess] = set()
        return set()
    text = (proc.stdout or proc.stderr).decode("utf-8", errors="replace")
    langs = {ln.strip() for ln in text.splitlines() if ln.strip() and " " not in ln.strip()}
    _LANG_CACHE[tess] = langs
    return langs


_JP = r"\u3040-\u30FF\u4E00-\u9FFF\uFF66-\uFF9D"
_JP_PUNCT = r"。、！？…ー〜「」『』（）・"


def tidy_ocr(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\u3000", " ")
    text = re.sub(rf"(?<=[{_JP}{_JP_PUNCT}])[ \t]+(?=[{_JP}{_JP_PUNCT}])", "", text)
    text = re.sub(rf"(?<=[{_JP}])[ \t]+(?=[A-Za-z0-9])", "", text)
    text = re.sub(rf"(?<=[A-Za-z0-9])[ \t]+(?=[{_JP}])", "", text)
    text = re.sub(r"[ \t]+([。、！？）」』])", r"\1", text)
    text = re.sub(r"([「『（])[ \t]+", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _cjk_score(text: str) -> int:
    n = 0
    for ch in text:
        o = ord(ch)
        if 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or 0xFF66 <= o <= 0xFF9D:
            n += 1
    return n


def _tess_once(tess: str, work: Path, lang: str, psm: str) -> str:
    cmd = [tess, str(work), "stdout", "-l", lang, "--psm", psm]
    proc = subprocess.run(cmd, capture_output=True, timeout=180, check=False)
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 and not out:
        err = proc.stderr.decode("utf-8", errors="replace")[:300]
        raise RuntimeError(err or "tesseract failed")
    return out


def ocr_image(tess: str, image: Path, lang: str, mode: str = "auto") -> str:
    if image.suffix.lower() not in OCR_EXT:
        return ""
    work = image
    tmp: Path | None = None
    if not _ascii_safe(image):
        ext = image.suffix.lower() or ".jpg"
        fd, raw = tempfile.mkstemp(prefix="wnocr_", suffix=ext)
        os.close(fd)
        tmp = Path(raw)
        shutil.copyfile(image, tmp)
        work = tmp
    installed = tess_langs(tess)
    attempts: list[tuple[str, str]] = []
    if mode in ("auto", "vertical"):
        if not installed or "jpn_vert" in installed:
            attempts.append(("jpn_vert+jpn", "5"))
            attempts.append(("jpn_vert", "5"))
        attempts.append((lang, "5"))
    if mode in ("auto", "horizontal"):
        attempts.append((lang, "6"))
        attempts.append((lang, "4"))
    seen: set[tuple[str, str]] = set()
    best = ""
    best_score = -1
    last_err = ""
    try:
        for use_lang, psm in attempts:
            key = (use_lang, psm)
            if key in seen:
                continue
            seen.add(key)
            parts = [p for p in use_lang.split("+") if p]
            if installed and parts and not all(p in installed or p == "osd" for p in parts):
                continue
            try:
                text = _tess_once(tess, work, use_lang, psm)
            except Exception as e:
                last_err = str(e)
                continue
            score = _cjk_score(text) * 4 + len(text)
            if score > best_score:
                best_score = score
                best = text
            if mode != "auto" and text:
                break
            if mode == "auto" and _cjk_score(text) >= 40:
                break
    finally:
        if tmp is not None:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
    if not best and last_err:
        raise RuntimeError(f"{image.name}: {last_err}")
    return tidy_ocr(best)


def folder_images(folder: Path) -> list[Path]:
    if not folder.is_dir():
        return []
    ocr_dir = (folder / "ocr").resolve()
    out: list[Path] = []
    for p in folder.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in IMAGE_EXT:
            continue
        try:
            p.resolve().relative_to(ocr_dir)
            continue
        except ValueError:
            out.append(p)
    return sorted(out, key=lambda x: x.name.lower())


def ocr_images(images: list[Path], tess: str, lang: str, dest_dir: Path) -> tuple[dict[str, Path], list[str]]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    errors: list[str] = []
    for img in images:
        try:
            text = ocr_image(tess, img, lang)
        except Exception as e:
            errors.append(f"{img.name}: {e}")
            continue
        if not text:
            continue
        out = dest_dir / f"{img.stem}.ocr.txt"
        out.write_text(text + "\n", encoding="utf-8")
        written[img.name] = out
    return written, errors


class OcrApp(ttk.Frame):
    def __init__(self, master: tk.Misc | None = None) -> None:
        own = master is None
        if own:
            master = tk.Tk()
            master.title(f"{APP_TITLE} {__version__}")
            master.geometry("920x640")
            master.minsize(760, 480)
        super().__init__(master)
        if own:
            self.pack(fill="both", expand=True)
        self._own_root = master if own else None

        self.img_var = tk.StringVar(value=DEFAULT_IMG)
        self.out_var = tk.StringVar(value=str(Path(DEFAULT_IMG) / "ocr"))
        self.tess_var = tk.StringVar(value=find_tesseract() or r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        self.lang_var = tk.StringVar(value="jpn+eng")
        self.mode_var = tk.StringVar(value="auto")
        self.status_var = tk.StringVar(value="Point at an image folder. No EPUB required.")
        self._files: list[Path] = []
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.log_q: queue.Queue[str] = queue.Queue()
        self._build()
        self.after(120, self._drain_log)

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True)

        self.files_fr = ttk.LabelFrame(root, text="Folders")
        self.files_fr.pack(fill="x", **pad)
        self.lbl_img = ttk.Label(self.files_fr, text="Images (images\\)")
        self.lbl_img.grid(row=0, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(self.files_fr, textvariable=self.img_var).grid(row=0, column=1, sticky="ew", padx=4)
        self.btn_img = ttk.Button(self.files_fr, text="Browse", command=self._pick_img)
        self.btn_img.grid(row=0, column=2, padx=6)
        self.lbl_ocr = ttk.Label(self.files_fr, text="OCR text (ocr\\)")
        self.lbl_ocr.grid(row=1, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(self.files_fr, textvariable=self.out_var).grid(row=1, column=1, sticky="ew", padx=4)
        self.btn_out = ttk.Button(self.files_fr, text="Browse", command=self._pick_out)
        self.btn_out.grid(row=1, column=2, padx=6)
        self.files_fr.columnconfigure(1, weight=1)

        self.engine_fr = ttk.LabelFrame(root, text="Tesseract")
        self.engine_fr.pack(fill="x", **pad)
        self.lbl_bin = ttk.Label(self.engine_fr, text="Binary")
        self.lbl_bin.grid(row=0, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(self.engine_fr, textvariable=self.tess_var).grid(row=0, column=1, sticky="ew", padx=4)
        self.btn_tess = ttk.Button(self.engine_fr, text="Browse", command=self._pick_tess)
        self.btn_tess.grid(row=0, column=2, padx=6)
        self.lbl_lang = ttk.Label(self.engine_fr, text="Lang")
        self.lbl_lang.grid(row=1, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(self.engine_fr, textvariable=self.lang_var, width=16).grid(row=1, column=1, sticky="w", padx=4)
        self.lbl_layout = ttk.Label(self.engine_fr, text="Layout")
        self.lbl_layout.grid(row=1, column=2, sticky="w", padx=6)
        self.mode_combo = ttk.Combobox(
            self.engine_fr,
            textvariable=self.mode_var,
            values=("auto", "vertical", "horizontal"),
            state="readonly",
            width=12,
        )
        self.mode_combo.grid(row=1, column=3, sticky="w", padx=4)
        self.engine_fr.columnconfigure(1, weight=1)

        btns = ttk.Frame(root)
        btns.pack(fill="x", **pad)
        self.btn_list = ttk.Button(btns, text="List folder", command=self._list)
        self.btn_list.pack(side="left", padx=4)
        self.btn_add = ttk.Button(btns, text="Add files…", command=self._add_files)
        self.btn_add.pack(side="left", padx=4)
        self.run_btn = ttk.Button(btns, text="Run OCR", command=self._run)
        self.run_btn.pack(side="left", padx=4)
        self.stop_btn = ttk.Button(btns, text="Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        self.btn_combine = ttk.Button(btns, text="Combine → raw_full.txt", command=self._combine)
        self.btn_combine.pack(side="left", padx=4)
        self.btn_hand = ttk.Button(btns, text="Handoff to Split", command=self._handoff_split)
        self.btn_hand.pack(side="left", padx=4)

        self.progress = ttk.Progressbar(root, mode="determinate")
        self.progress.pack(fill="x", padx=8, pady=2)
        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", padx=10)

        mid = ttk.Panedwindow(root, orient="horizontal")
        mid.pack(fill="both", expand=True, padx=8, pady=6)
        left = ttk.Frame(mid)
        right = ttk.Frame(mid)
        mid.add(left, weight=1)
        mid.add(right, weight=1)
        self.lbl_list = ttk.Label(left, text="Images")
        self.lbl_list.pack(anchor="w")
        self.listbox = tk.Listbox(left, height=18)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._show)
        self.lbl_log = ttk.Label(right, text="Log / preview")
        self.lbl_log.pack(anchor="w")
        self.preview = tk.Text(right, wrap="word")
        self.preview.pack(fill="both", expand=True)

        self.hint_lbl = ttk.Label(
            root,
            text="Japanese folder names are copied to a temp ASCII path before Tesseract runs.",
            foreground="#888",
        )
        self.hint_lbl.pack(anchor="w", padx=10, pady=(0, 8))
        self._ui_lang = "en"

    def set_ui_lang(self, lang: str) -> None:
        ja = lang != "en"
        self.files_fr.configure(text="フォルダ" if ja else "Folders")
        self.engine_fr.configure(text="Tesseract")
        self.lbl_img.configure(text="画像 (images\\)" if ja else "Images (images\\)")
        self.lbl_ocr.configure(text="OCR テキスト (ocr\\)" if ja else "OCR text (ocr\\)")
        self.lbl_bin.configure(text="実行ファイル" if ja else "Binary")
        self.lbl_lang.configure(text="言語" if ja else "Lang")
        self.lbl_layout.configure(text="レイアウト" if ja else "Layout")
        for b in (self.btn_img, self.btn_out, self.btn_tess):
            b.configure(text="参照" if ja else "Browse")
        self.btn_list.configure(text="フォルダ一覧" if ja else "List folder")
        self.btn_add.configure(text="ファイル追加…" if ja else "Add files…")
        self.run_btn.configure(text="OCR 実行" if ja else "Run OCR")
        self.stop_btn.configure(text="停止" if ja else "Stop")
        self.btn_combine.configure(text="結合 → raw_full.txt" if ja else "Combine → raw_full.txt")
        self.btn_hand.configure(text="分割へ渡す" if ja else "Handoff to Split")
        self.lbl_list.configure(text="画像" if ja else "Images")
        self.lbl_log.configure(text="ログ / プレビュー" if ja else "Log / preview")
        self.hint_lbl.configure(
            text="日本語パスは Tesseract の前に ASCII 一時ファイルへコピーします。" if ja
            else "Japanese folder names are copied to a temp ASCII path before Tesseract runs."
        )

    def apply_series(self, layout: dict) -> None:
        self.img_var.set(str(layout["images"]))
        self.out_var.set(str(layout["ocr"]))
        self._series = layout["series"]
        self._raw = layout["raw"]

    def _handoff_split(self) -> None:
        fn = getattr(self, "handoff_split", None)
        if callable(fn):
            fn()
        else:
            messagebox.showinfo(APP_TITLE, "Open the Split tab and set Raw dump to raw_full.txt")

    def _combine(self) -> None:
        ocr_dir = Path(self.out_var.get().strip())
        try:
            from wn_series import infer_series_root
        except ImportError:
            infer_series_root = None
        dest = None
        if infer_series_root:
            root = infer_series_root(ocr_dir, self.img_var.get())
            if root is not None:
                dest = root / "raw_full.txt"
                self._series = root
                self._raw = dest
        if dest is None:
            dest = ocr_dir.parent / "raw_full.txt"
        try:
            from wn_series import stitch_ocr_texts
        except ImportError:
            import importlib.util

            path = Path(__file__).resolve().parent / "wn_series.py"
            spec = importlib.util.spec_from_file_location("wn_series", path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            stitch_ocr_texts = mod.stitch_ocr_texts
        try:
            n, dest = stitch_ocr_texts(ocr_dir, Path(dest))
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))
            return
        self.status_var.set(f"Combined {n} OCR files → {dest}")
        self._log(f"Combined {n} files → {dest}")
        messagebox.showinfo(APP_TITLE, f"Wrote {n} pages to:\n{dest}\nUse Split on that file.")

    def _pick_img(self) -> None:
        d = filedialog.askdirectory(initialdir=self.img_var.get() or DEFAULT_IMG)
        if d:
            self.img_var.set(d)
            self.out_var.set(str(Path(d) / "ocr"))
            self._list()

    def _pick_out(self) -> None:
        d = filedialog.askdirectory(initialdir=self.out_var.get() or DEFAULT_IMG)
        if d:
            self.out_var.set(d)

    def _pick_tess(self) -> None:
        p = filedialog.askopenfilename(title="tesseract", filetypes=[("All", "*.*")])
        if p:
            self.tess_var.set(p)

    def _refill(self) -> None:
        self.listbox.delete(0, "end")
        for p in self._files:
            self.listbox.insert("end", f"{p.name}  ({p.stat().st_size} bytes)")

    def _list(self) -> None:
        folder = Path(self.img_var.get().strip())
        self._files = folder_images(folder)
        self._refill()
        self.status_var.set(f"{len(self._files)} images in {folder}")

    def _add_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="Images",
            filetypes=[("Images", "*.jpg *.jpeg *.png *.gif *.webp *.bmp *.tif *.tiff"), ("All", "*.*")],
        )
        if not paths:
            return
        extra = [Path(p) for p in paths]
        dest = Path(self.img_var.get().strip() or DEFAULT_IMG)
        dest.mkdir(parents=True, exist_ok=True)
        added = []
        for src in extra:
            if src.suffix.lower() not in IMAGE_EXT:
                continue
            target = dest / src.name
            n = 2
            while target.exists() and target.resolve() != src.resolve():
                target = dest / f"{src.stem}_{n}{src.suffix}"
                n += 1
            if target.resolve() != src.resolve():
                shutil.copy2(src, target)
            added.append(target)
        self.img_var.set(str(dest))
        if not self.out_var.get().strip():
            self.out_var.set(str(dest / "ocr"))
        self._list()
        self.status_var.set(f"Added {len(added)} files to {dest}")

    def _show(self, _evt=None) -> None:
        sel = self.listbox.curselection()
        self.preview.delete("1.0", "end")
        if not sel:
            return
        img = self._files[int(sel[0])]
        ocr = Path(self.out_var.get().strip() or (img.parent / "ocr")) / f"{img.stem}.ocr.txt"
        if ocr.is_file():
            self.preview.insert("1.0", ocr.read_text(encoding="utf-8"))
        else:
            self.preview.insert("1.0", f"{img}\nNo OCR file yet. Run OCR.")

    def _log(self, msg: str) -> None:
        self.log_q.put(time.strftime("%H:%M:%S ") + msg)

    def _drain_log(self) -> None:
        try:
            while True:
                line = self.log_q.get_nowait()
                self.preview.insert("end", line + "\n")
                self.preview.see("end")
        except queue.Empty:
            pass
        self.after(120, self._drain_log)

    def _stop(self) -> None:
        self.stop_event.set()
        self.status_var.set("Stopping after this file…")
        self._log("Stop requested.")

    def _run(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        if not self._files:
            self._list()
        if not self._files:
            messagebox.showerror(APP_TITLE, "No images in the Images folder.")
            return
        tess = find_tesseract(self.tess_var.get().strip())
        if not tess:
            messagebox.showerror(APP_TITLE, "Tesseract not found.")
            return
        dest = Path(self.out_var.get().strip() or (Path(self.img_var.get()) / "ocr"))
        lang = self.lang_var.get().strip() or "jpn+eng"
        mode = self.mode_var.get().strip() or "auto"
        self.stop_event.clear()
        self.run_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.progress["value"] = 0
        self.progress["maximum"] = len(self._files)
        self.preview.delete("1.0", "end")
        files = list(self._files)
        self.worker = threading.Thread(
            target=self._run_queue, args=(files, tess, lang, dest, mode), daemon=True
        )
        self.worker.start()

    def _run_queue(self, files: list[Path], tess: str, lang: str, dest: Path, mode: str = "auto") -> None:
        dest.mkdir(parents=True, exist_ok=True)
        ok = fail = skip = 0
        total = len(files)
        have = tess_langs(tess)
        self._log(f"Queue {total} files. lang={lang} layout={mode}")
        if "jpn_vert" not in have:
            self._log("Warning: jpn_vert missing. Vertical LN pages will be poor.")
            self._log("Mint: sudo apt install tesseract-ocr-jpn-vert")
            self._log("Windows: put jpn_vert.traineddata in Tesseract-OCR\\tessdata")
        try:
            for i, img in enumerate(files, start=1):
                if self.stop_event.is_set():
                    self._log("Stopped.")
                    break
                self.status_var.set(f"{i}/{total}  {img.name}")
                self.progress["value"] = i - 1
                out = dest / f"{img.stem}.ocr.txt"
                if out.exists() and out.stat().st_size > 0:
                    self._log(f"SKIP {img.name} (exists {out.name})")
                    skip += 1
                    self.progress["value"] = i
                    continue
                self._log(f"OCR  {img.name}")
                t0 = time.time()
                try:
                    text = ocr_image(tess, img, lang, mode)
                except Exception as e:
                    fail += 1
                    self._log(f"FAIL {img.name}: {e}")
                    self.progress["value"] = i
                    continue
                elapsed = time.time() - t0
                if not text:
                    skip += 1
                    self._log(f"EMPTY {img.name}  {elapsed:.1f}s")
                else:
                    out.write_text(text + "\n", encoding="utf-8")
                    ok += 1
                    self._log(f"OK   {out.name}  {len(text)} chars  {elapsed:.1f}s")
                self.progress["value"] = i
            msg = f"Done. ok={ok} skip={skip} fail={fail}"
            self.status_var.set(msg)
            self._log(msg)
        finally:
            self.run_btn.configure(state="normal")
            self.stop_btn.configure(state="disabled")

    def mainloop(self, n: int = 0):  # type: ignore[override]
        root = self._own_root or self.winfo_toplevel()
        root.mainloop(n)


def main() -> None:
    OcrApp().mainloop()


if __name__ == "__main__":
    main()
