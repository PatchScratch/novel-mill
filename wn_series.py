#!/usr/bin/env python3
"""
Shared book-folder layout for every Novel Mill tab.

A "book folder" is one web-novel series or one light-novel volume.
Tabs must not invent their own directory names.
"""

from __future__ import annotations

import re
from pathlib import Path

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


def _nat_key(path: Path):
    parts = re.split(r"(\d+)", path.name.lower())
    return [int(p) if p.isdigit() else p for p in parts]


def stitch_ocr_texts(ocr_dir: Path, dest_raw: Path) -> tuple[int, Path]:
    files = [p for p in ocr_dir.iterdir() if p.is_file() and p.suffix.lower() == ".txt"]
    files.sort(key=_nat_key)
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
    files.sort(key=_nat_key)
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
