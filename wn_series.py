#!/usr/bin/env python3
"""
Shared helpers for every Novel Mill tab: book-folder layout, text codecs,
Tesseract OCR.

A "book folder" is one web-novel series or one light-novel volume.
Tabs must not invent their own directory names — or their own copies
of these helpers.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def app_version() -> str:
    """Single version source: the VERSION file beside this module."""
    try:
        v = (Path(__file__).resolve().parent / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0"
    return v or "0.0.0"


def config_dir() -> Path:
    """Per-user config dir (ui.json, queues, mill settings, user rules)."""
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA") or Path.home()) / "NovelMill"
    return Path(os.environ.get("XDG_CONFIG_HOME") or (Path.home() / ".config")) / "novel_mill"

DEFAULT_SERIES = r""
RAW_NAME = "raw_full.txt"
SEP = "\n\n⸻\n\n"


LEAF_NAMES = {"in", "out", "ocr", "images", "lock"}

RE_PAGE_BRACKET = re.compile(r"^[\s　]*[\[［【][0-9０-９]{1,6}[\]］】][\s　]*$")
RE_PAGE_DECORATED = re.compile(
    r"^[\s　]*[-–—―─～~・]{1,3}[\s　]*[0-9０-９]{1,4}[\s　]*[-–—―─～~・]{1,3}[\s　]*$"
)
RE_PAGE_BARE = re.compile(r"^[\s　]*[0-9０-９]{1,4}[\s　]*$")
RE_STITCH = re.compile(r"^[\s　]*[⸻─—–―]{1,}[\s　]*$")


def strip_page_numbers(text: str) -> str:
    """Remove [0017], ［12］, - 17 -, lone page digits. Keep [image: …]."""
    kept: list[str] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        s = line.strip().replace("\u3000", " ")
        if RE_PAGE_BRACKET.match(s):
            continue
        if RE_PAGE_DECORATED.match(s):
            continue
        if RE_PAGE_BARE.match(s):
            continue
        if RE_STITCH.match(s):
            continue
        line = re.sub(r"［＃改ページ］", "", line)
        kept.append(line)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip() + "\n"


def infer_series_root(*paths: str | Path | None) -> Path | None:
    """Parent of in/out/ocr/images/lock, or the directory itself."""
    for raw in paths:
        if raw is None or str(raw).strip() == "":
            continue
        p = Path(str(raw).strip())
        if p.suffix.lower() in {".txt", ".epub"}:
            p = p.parent
        name = p.name.lower()
        if name == "ocr" and p.parent.name.lower() == "images":
            return p.parent.parent
        if name in LEAF_NAMES:
            return p.parent
        if p.is_dir() or p.parent.is_dir():
            return p if p.is_dir() else p.parent
    return None


def series_layout(series: str | Path) -> dict[str, Path]:
    root = Path(str(series).strip() or DEFAULT_SERIES)
    return {
        "series": root,
        "raw": root / RAW_NAME,
        "in_dir": root / "in",
        "out_dir": root / "out",
        "images": root / "images",
        "ocr": root / "ocr",
        "lock": root / "lock",
    }


def ensure_dirs(layout: dict[str, Path]) -> None:
    for key in ("in_dir", "out_dir", "images", "ocr"):
        layout[key].mkdir(parents=True, exist_ok=True)


def nat_key(path: Path):
    parts = re.split(r"(\d+)", path.name.lower())
    return [int(p) if p.isdigit() else p for p in parts]


def stitch_ocr_texts(ocr_dir: Path, dest_raw: Path) -> tuple[int, Path]:
    files = [p for p in ocr_dir.iterdir() if p.is_file() and p.suffix.lower() == ".txt"]
    files.sort(key=nat_key)
    if not files:
        raise FileNotFoundError(f"No .txt OCR files in {ocr_dir}")
    chunks: list[str] = []
    for f in files:
        body = f.read_text(encoding="utf-8", errors="replace").strip()
        if not body:
            continue
        stem = f.name
        if stem.endswith(".ocr.txt"):
            stem = stem[: -len(".ocr.txt")]
        else:
            stem = f.stem
        chunks.append(f"[{stem}]\n{body}")
    dest_raw.parent.mkdir(parents=True, exist_ok=True)
    dest_raw.write_text(SEP.join(chunks) + "\n", encoding="utf-8")
    return len(chunks), dest_raw


SKIP_COMBINE = {
    "raw_full.txt",
    "raw.txt",
    "english_full.txt",
    "out_full.en.txt",
    "full.en.txt",
}


def stitch_en_texts(out_dir: Path, dest: Path) -> tuple[int, Path]:
    files = [
        p
        for p in out_dir.iterdir()
        if p.is_file()
        and p.name.lower().endswith(".en.txt")
        and p.name.lower() not in SKIP_COMBINE
        and p.resolve() != dest.resolve()
    ]
    files.sort(key=nat_key)
    if not files:
        raise FileNotFoundError(f"No .en.txt shards in {out_dir}")
    chunks: list[str] = []
    for f in files:
        body = f.read_text(encoding="utf-8", errors="replace").strip()
        if body:
            chunks.append(body)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n\n".join(chunks) + "\n", encoding="utf-8")
    return len(chunks), dest


# ---- shared text helpers (split / mill / epub) ----

ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def cjk_count(text: str) -> int:
    n = 0
    for ch in text:
        o = ord(ch)
        if 0x3040 <= o <= 0x30FF or 0x4E00 <= o <= 0x9FFF or 0xFF66 <= o <= 0xFF9D:
            n += 1
    return n


def read_text(path: Path) -> str:
    """UTF-8 (BOM ok) with CP932/UTF-16 fallback for user-supplied dumps."""
    data = path.read_bytes()
    if not data:
        raise ValueError(f"{path.name} is empty.")
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        text = data.decode("utf-16")
    elif len(data) >= 4 and data[1:4:2] == b"\x00\x00" and data[0] != 0:
        text = data.decode("utf-16-le")
    else:
        text = None
        for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "gb18030"):
            try:
                cand = data.decode(enc)
            except UnicodeDecodeError:
                continue
            if cand.count("\ufffd") > 8:
                continue
            text = cand
            break
        if text is None:
            raise ValueError(
                f"{path.name} is not UTF-8 / UTF-16 / CP932 text.\n"
                "In Notepad: Save As → Encoding UTF-8. Do not feed it a binary file."
            )
    if text.count("\ufffd") > 20 or (len(text) > 200 and cjk_count(text) < 8 and "\x00" in text):
        raise ValueError(
            f"{path.name} looks like broken encoding or binary.\n"
            "Re-save it as UTF-8 and rebuild the pieces from it."
        )
    return text


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.replace("\r\n", "\n").replace("\r", "\n"), encoding="utf-8")


def safe_stem(text: str, fallback: str) -> str:
    t = text.strip()
    t = re.sub(r"［＃.*?］", "", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("《", "").replace("》", "")
    t = re.sub(r"\s+", "_", t)
    t = ILLEGAL.sub("", t)
    t = t.strip("._ ")
    if len(t) > 42:
        t = t[:42].rstrip("._ ")
    return t or fallback


# ---- shared Tesseract OCR ----

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".tif", ".tiff"}
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


def _tess_once(tess: str, work: Path, lang: str, psm: str) -> str:
    cmd = [tess, str(work), "stdout", "-l", lang, "--psm", psm]
    proc = subprocess.run(cmd, capture_output=True, timeout=180, check=False)
    out = proc.stdout.decode("utf-8", errors="replace").strip()
    if proc.returncode != 0 and not out:
        err = proc.stderr.decode("utf-8", errors="replace")[:300]
        raise RuntimeError(err or "tesseract failed")
    return out


def ocr_image(tess: str, image: Path, lang: str, mode: str = "auto") -> str:
    """Vertical-aware Tesseract pass with CJK-scored fallbacks."""
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
            score = cjk_count(text) * 4 + len(text)
            if score > best_score:
                best_score = score
                best = text
            if mode != "auto" and text:
                break
            if mode == "auto" and cjk_count(text) >= 40:
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
    return sorted(out, key=nat_key)


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
