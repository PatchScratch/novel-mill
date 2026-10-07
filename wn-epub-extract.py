#!/usr/bin/env python3
# Novel Mill — EPUB tab. Spine/nav → in\ files + images. Refuses Adobe AES DRM.
# Writes in\NNN_title.txt and optionally raw_full.txt.
# Windows: py -3 wn-epub-extract.py
# Stdlib only (zipfile + html.parser). No ebooklib.

from __future__ import annotations

import html
import posixpath
import re
import tkinter as tk
import zipfile
from html.parser import HTMLParser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from xml.etree import ElementTree as ET

from wn_series import ILLEGAL, IMAGE_EXT, app_version, safe_stem, strip_page_numbers

__version__ = app_version()
APP_TITLE = "EPUB"
DEFAULT_SERIES = r""
DEFAULT_OUT = str(Path(DEFAULT_SERIES) / "in")
DEFAULT_IMG = str(Path(DEFAULT_SERIES) / "images")

NS = {
    "c": "urn:oasis:names:tc:opendocument:xmlns:container",
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
    "xhtml": "http://www.w3.org/1999/xhtml",
    "epub": "http://www.idpf.org/2007/ops",
}

SKIP_STEMS = re.compile(
    r"(nav|toc|ncx|cover|titlepage|copyright|colophon|dedication|contents)",
    re.I,
)


class TextExtractor(HTMLParser):
    SKIP = {"script", "style", "svg", "head", "title"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self.blocks: list[str] = []
        self._buf: list[str] = []
        self.headings: list[str] = []
        self.images: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t in self.SKIP:
            self._skip += 1
            return
        if self._skip:
            return
        if t == "img":
            src = ""
            alt = ""
            for k, v in attrs:
                if k.lower() == "src" and v:
                    src = v
                elif k.lower() == "alt" and v:
                    alt = v
            if src:
                self.images.append(src.split("#", 1)[0].split("?", 1)[0])
                mark = Path(src.split("?")[0]).name
                extra = f" {alt}" if alt else ""
                self._buf.append(f"[image: {mark}{extra}]")
        if t in ("br", "hr"):
            self._flush()
        elif t in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "blockquote", "section"):
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in self.SKIP and self._skip:
            self._skip -= 1
            return
        if self._skip:
            return
        if t in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "blockquote", "section", "br"):
            text = self._flush()
            if t in ("h1", "h2", "h3", "h4") and text:
                self.headings.append(text)

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        self._buf.append(data)

    def _flush(self) -> str:
        raw = "".join(self._buf)
        self._buf.clear()
        line = re.sub(r"[ \t\u00a0\u3000]+", " ", raw).strip()
        if line:
            self.blocks.append(line)
        return line

    def text(self) -> str:
        self._flush()
        out = "\n".join(self.blocks)
        out = re.sub(r"\n{3,}", "\n\n", out).strip()
        return out + ("\n" if out else "")


def q(tag: str, kind: str) -> str:
    return "{%s}%s" % (NS[kind], tag)


def local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def read_xml(data: bytes) -> ET.Element:
    # EPUB XML often has default namespaces; keep them.
    return ET.fromstring(data)


def opf_path(zf: zipfile.ZipFile) -> str:
    raw = zf.read("META-INF/container.xml")
    root = read_xml(raw)
    for el in root.iter():
        if local(el.tag) == "rootfile":
            href = el.attrib.get("full-path") or el.attrib.get("full-path".lower())
            if href:
                return href.replace("\\", "/")
    raise ValueError("container.xml has no rootfile")


def dirname_pos(path: str) -> str:
    path = path.replace("\\", "/")
    if "/" not in path:
        return ""
    return path.rsplit("/", 1)[0]


def join_pos(base_dir: str, href: str) -> str:
    href = href.split("#", 1)[0].split("?", 1)[0]
    href = href.replace("\\", "/")
    if not href:
        return ""
    if base_dir:
        return posixpath.normpath(posixpath.join(base_dir, href))
    return posixpath.normpath(href)


def parse_opf(zf: zipfile.ZipFile, opf: str) -> tuple[str, list[tuple[str, str]], list[str]]:
    root = read_xml(zf.read(opf))
    title = "untitled"
    for el in root.iter():
        if local(el.tag) == "title" and (el.text or "").strip():
            title = (el.text or "").strip()
            break

    manifest: dict[str, tuple[str, str]] = {}
    for el in root.iter():
        if local(el.tag) != "item":
            continue
        iid = el.attrib.get("id")
        href = el.attrib.get("href")
        media = (el.attrib.get("media-type") or "").lower()
        props = el.attrib.get("properties") or ""
        if iid and href:
            manifest[iid] = (href, media + " " + props)

    spine: list[tuple[str, str]] = []
    base = dirname_pos(opf)
    for el in root.iter():
        if local(el.tag) != "itemref":
            continue
        idref = el.attrib.get("idref")
        if not idref or idref not in manifest:
            continue
        href, meta = manifest[idref]
        path = join_pos(base, href)
        if not path:
            continue
        if "xhtml" not in meta and "html" not in meta and not path.lower().endswith((".xhtml", ".html", ".htm")):
            continue
        spine.append((path, idref))
    images: list[str] = []
    for href, meta in manifest.values():
        path = join_pos(base, href)
        low = meta.lower()
        ext = Path(path).suffix.lower()
        if path and ("image/" in low or ext in IMAGE_EXT):
            images.append(path)
    return title, spine, images


def nav_titles(zf: zipfile.ZipFile, opf: str) -> dict[str, str]:
    """Map spine href → nav label when a nav/ncx exists."""
    out: dict[str, str] = {}
    names = zf.namelist()
    base = dirname_pos(opf)
    for name in names:
        low = name.lower()
        is_ncx = low.endswith(".ncx")
        if not is_ncx and not (low.endswith((".xhtml", ".html")) and re.search(r"(nav|toc)", low)):
            continue
        try:
            raw = zf.read(name)
        except KeyError:
            continue
        try:
            root = read_xml(raw)
        except ET.ParseError:
            continue
        if is_ncx:
            # EPUB2: navMap > navPoint > navLabel > text + content src=…
            for np_el in root.iter():
                if local(np_el.tag).lower() != "navpoint":
                    continue
                label = ""
                src = ""
                for sub in np_el.iter():
                    t = local(sub.tag).lower()
                    if t == "text" and not label:
                        label = (sub.text or "").strip()
                    elif t == "content" and not src:
                        src = sub.attrib.get("src") or ""
                path = join_pos(base, src) if src else ""
                if path and label and len(label) < 120:
                    out.setdefault(path, label)
        else:
            nav_dir = dirname_pos(name)
            for el in root.iter():
                if local(el.tag).lower() != "a":
                    continue
                href = el.attrib.get("href")
                if not href:
                    continue
                path = join_pos(nav_dir, href)
                label = "".join(el.itertext()).strip()
                if path and label and len(label) < 120:
                    out.setdefault(path, label)
    return out


def html_to_text(data: bytes) -> tuple[str, list[str], list[str]]:
    # decode
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp932", "shift_jis", "gb18030"):
        try:
            text = data.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        text = data.decode("utf-8", errors="replace")
    parser = TextExtractor()
    try:
        parser.feed(text)
        parser.close()
    except Exception:
        stripped = re.sub(r"(?is)<(script|style|svg)[^>]*>.*?</\1>", " ", text)
        stripped = re.sub(r"(?is)<br\s*/?>", "\n", stripped)
        stripped = re.sub(r"(?is)</p>", "\n\n", stripped)
        stripped = re.sub(r"(?is)<[^>]+>", "", stripped)
        stripped = html.unescape(stripped)
        stripped = re.sub(r"[ \t]+\n", "\n", stripped)
        stripped = re.sub(r"\n{3,}", "\n\n", stripped).strip() + "\n"
        return stripped, [], []
    return parser.text(), parser.headings, parser.images


class Chapter:
    def __init__(self, index: int, href: str, title: str, body: str, skip: bool) -> None:
        self.index = index
        self.href = href
        self.title = title
        self.body = body
        self.skip = skip
        self.include = not skip

    @property
    def chars(self) -> int:
        return len(self.body)


def collect_zip_images(zf: zipfile.ZipFile, extra: list[str] | None = None) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    names = list(extra or [])
    names.extend(zf.namelist())
    for name in names:
        path = name.replace("\\", "/")
        if path in seen:
            continue
        ext = Path(path).suffix.lower()
        if ext in IMAGE_EXT:
            seen.add(path)
            found.append(path)
    return found


def write_images(epub: Path, dest: Path) -> list[Path]:
    dest.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    used: set[str] = set()
    with zipfile.ZipFile(epub) as zf:
        opf = opf_path(zf)
        _title, _spine, manifest_imgs = parse_opf(zf, opf)
        for src in collect_zip_images(zf, manifest_imgs):
            try:
                data = zf.read(src)
            except KeyError:
                continue
            if not data:
                continue
            name = Path(src).name
            name = ILLEGAL.sub("", name) or "image.bin"
            stem, ext = Path(name).stem, Path(name).suffix
            final = name
            n = 2
            while final.lower() in used or (dest / final).exists():
                final = f"{stem}_{n}{ext}"
                n += 1
            used.add(final.lower())
            out = dest / final
            out.write_bytes(data)
            written.append(out)
    return written


def encrypted_uris(zf: zipfile.ZipFile) -> list[str]:
    names = {n.replace("\\", "/") for n in zf.namelist()}
    hits = []
    for cand in ("META-INF/encryption.xml", "META-INF/Encryption.xml"):
        if cand not in names:
            continue
        raw = zf.read(cand).decode("utf-8", errors="replace")
        if "http://ns.adobe.com/adept" in raw or "xmlenc#aes" in raw.lower() or "EncryptedData" in raw:
            import re

            hits = re.findall(r'URI="([^"]+)"', raw)
            if not hits:
                hits = ["(encryption.xml present)"]
        break
    return hits


def extract_epub(path: Path) -> tuple[str, list[Chapter], list[str]]:
    if not zipfile.is_zipfile(path):
        raise ValueError(f"Not a zip/EPUB: {path}")
    with zipfile.ZipFile(path) as zf:
        locked = encrypted_uris(zf)
        if locked:
            n = len(locked)
            raise ValueError(
                f"{path.name} is DRM-encrypted ({n} files, Adobe AES).\n"
                "Calibre can display it with your Adobe ID; this tab only unzips.\n"
                "Convert to TXT in Calibre, or OCR page images. Do not Extract this file."
            )
        if "mimetype" in zf.namelist():
            mt = zf.read("mimetype").decode("ascii", errors="replace").strip()
            if mt != "application/epub+zip":
                pass
        opf = opf_path(zf)
        book_title, spine, manifest_imgs = parse_opf(zf, opf)
        titles = nav_titles(zf, opf)
        chapters: list[Chapter] = []
        n = 0
        for href, _idref in spine:
            try:
                data = zf.read(href)
            except KeyError:
                continue
            body, heads, _imgs = html_to_text(data)
            if not body.strip():
                continue
            n += 1
            stem = Path(href).stem
            title = titles.get(href) or (heads[0] if heads else stem)
            skip = bool(SKIP_STEMS.search(stem) or SKIP_STEMS.search(title))
            if skip and len(body) > 2500:
                skip = False
            chapters.append(Chapter(n, href, title, body, skip))
        images = collect_zip_images(zf, manifest_imgs)
    if not chapters:
        raise ValueError("No XHTML spine documents with text.")
    return book_title, chapters, images


def filename_for(ch: Chapter, pad: int) -> str:
    return f"{ch.index:0{pad}d}_{safe_stem(ch.title, f'ch_{ch.index}')}.txt"


class ExtractApp(ttk.Frame):
    def __init__(self, master: tk.Misc | None = None) -> None:
        own = master is None
        if own:
            master = tk.Tk()
            master.title(f"{APP_TITLE} {__version__}")
            master.geometry("980x680")
            master.minsize(820, 540)
        super().__init__(master)
        if own:
            self.pack(fill="both", expand=True)
        self._own_root = master if own else None

        self.epub_var = tk.StringVar(value="")
        self.out_var = tk.StringVar(value=DEFAULT_OUT)
        self.img_var = tk.StringVar(value=DEFAULT_IMG)
        self.raw_var = tk.BooleanVar(value=True)
        self.images_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Open an .epub, Scan, then Write into the mill in\\ folder.")
        self.book_title = ""
        self.chapters: list[Chapter] = []
        self.image_paths: list[str] = []

        self._build()

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True)

        self.files_fr = ttk.LabelFrame(root, text="Files")
        self.files_fr.pack(fill="x", **pad)
        self.lbl_epub = ttk.Label(self.files_fr, text="EPUB")
        self.lbl_epub.grid(row=0, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(self.files_fr, textvariable=self.epub_var).grid(row=0, column=1, sticky="ew", padx=4)
        self.btn_epub = ttk.Button(self.files_fr, text="Browse", command=self._pick_epub)
        self.btn_epub.grid(row=0, column=2, padx=6)
        self.lbl_scenes = ttk.Label(self.files_fr, text="Scenes (in\\)")
        self.lbl_scenes.grid(row=1, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(self.files_fr, textvariable=self.out_var).grid(row=1, column=1, sticky="ew", padx=4)
        self.btn_out = ttk.Button(self.files_fr, text="Browse", command=self._pick_out)
        self.btn_out.grid(row=1, column=2, padx=6)
        self.lbl_imgs = ttk.Label(self.files_fr, text="Images (images\\)")
        self.lbl_imgs.grid(row=2, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(self.files_fr, textvariable=self.img_var).grid(row=2, column=1, sticky="ew", padx=4)
        self.btn_img = ttk.Button(self.files_fr, text="Browse", command=self._pick_img)
        self.btn_img.grid(row=2, column=2, padx=6)
        self.files_fr.columnconfigure(1, weight=1)

        self.opts_fr = ttk.LabelFrame(root, text="Output")
        self.opts_fr.pack(fill="x", **pad)
        self.chk_raw = ttk.Checkbutton(
            self.opts_fr,
            text="Also write raw_full.txt in the parent of in\\ (splitter input)",
            variable=self.raw_var,
        )
        self.chk_raw.pack(anchor="w", padx=8, pady=2)
        self.chk_img = ttk.Checkbutton(
            self.opts_fr,
            text="Extract images into the Images folder (jpg/png/gif/webp/svg/bmp)",
            variable=self.images_var,
        )
        self.chk_img.pack(anchor="w", padx=8, pady=2)

        btns = ttk.Frame(root)
        btns.pack(fill="x", **pad)
        self.btn_scan = ttk.Button(btns, text="Scan", command=self._scan)
        self.btn_scan.pack(side="left", padx=4)
        self.btn_write = ttk.Button(btns, text="Write files", command=self._write)
        self.btn_write.pack(side="left", padx=4)
        self.btn_toggle = ttk.Button(btns, text="Toggle selected", command=self._toggle)
        self.btn_toggle.pack(side="left", padx=4)
        self.btn_hand = ttk.Button(btns, text="Handoff to Split", command=self._handoff_split)
        self.btn_hand.pack(side="left", padx=4)

        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", padx=10)

        mid = ttk.Panedwindow(root, orient="horizontal")
        mid.pack(fill="both", expand=True, padx=8, pady=6)
        left = ttk.Frame(mid)
        right = ttk.Frame(mid)
        mid.add(left, weight=1)
        mid.add(right, weight=1)
        self.lbl_spine = ttk.Label(left, text="Spine chapters  (x = skip)")
        self.lbl_spine.pack(anchor="w")
        self.listbox = tk.Listbox(left, height=18)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._show)
        self.lbl_prev = ttk.Label(right, text="Preview")
        self.lbl_prev.pack(anchor="w")
        self.preview = tk.Text(right, wrap="word")
        self.preview.pack(fill="both", expand=True)

        self.hint_lbl = ttk.Label(
            root,
            text="One spine document = one in\\NNN_title.txt for the mill.",
        )
        self.hint_lbl.pack(anchor="w", padx=10, pady=(0, 8))
        self._ui_lang = "en"

    def set_ui_lang(self, lang: str) -> None:
        ja = lang != "en"
        self._ui_lang = "ja" if ja else "en"
        self.files_fr.configure(text="ファイル" if ja else "Files")
        self.opts_fr.configure(text="出力" if ja else "Output")
        self.lbl_scenes.configure(text="シーン (in\\)" if ja else "Scenes (in\\)")
        self.lbl_imgs.configure(text="画像 (images\\)" if ja else "Images (images\\)")
        for b in (self.btn_epub, self.btn_out, self.btn_img):
            b.configure(text="参照" if ja else "Browse")
        self.chk_raw.configure(text="親フォルダに raw_full.txt も書く（分割の入力）" if ja else "Also write raw_full.txt in the parent of in\\ (splitter input)")
        self.chk_img.configure(text="画像フォルダへ画像を出す" if ja else "Extract images into the Images folder")
        self.btn_scan.configure(text="スキャン" if ja else "Scan")
        self.btn_write.configure(text="書き出し" if ja else "Write files")
        self.btn_toggle.configure(text="選択を切替" if ja else "Toggle selected")
        self.btn_hand.configure(text="分割へ渡す" if ja else "Handoff to Split")
        self.lbl_spine.configure(text="目次（x = スキップ）" if ja else "Spine chapters  (x = skip)")
        self.lbl_prev.configure(text="プレビュー" if ja else "Preview")
        self.hint_lbl.configure(
            text="目次1件 = in\\ の1ファイル。" if ja else "One spine document = one in\\NNN_title.txt for the mill."
        )

    def apply_series(self, layout: dict) -> None:
        self.out_var.set(str(layout["in_dir"]))
        self.img_var.set(str(layout["images"]))

    def _handoff_split(self) -> None:
        fn = getattr(self, "handoff_split", None)
        if callable(fn):
            fn()

    def _pick_epub(self) -> None:
        p = filedialog.askopenfilename(
            title="EPUB",
            filetypes=[("EPUB", "*.epub"), ("All", "*.*")],
        )
        if p:
            self.epub_var.set(p)

    def _pick_out(self) -> None:
        d = filedialog.askdirectory(initialdir=self.out_var.get() or DEFAULT_OUT)
        if d:
            self.out_var.set(d)
            parent = Path(d)
            if parent.name.lower() == "in":
                self.img_var.set(str(parent.parent / "images"))

    def _pick_img(self) -> None:
        d = filedialog.askdirectory(initialdir=self.img_var.get() or DEFAULT_IMG)
        if d:
            self.img_var.set(d)

    def _img_dest(self) -> Path:
        out = Path(self.out_var.get().strip() or DEFAULT_OUT)
        raw = self.img_var.get().strip()
        return Path(raw) if raw else (out.parent / "images")

    def _scan(self) -> None:
        path = Path(self.epub_var.get().strip())
        if not path.is_file():
            messagebox.showerror(APP_TITLE, f"EPUB not found:\n{path}")
            return
        try:
            self.book_title, self.chapters, self.image_paths = extract_epub(path)
        except Exception as e:
            messagebox.showerror(APP_TITLE, str(e))
            return
        self._refill()
        keep = sum(1 for c in self.chapters if c.include)
        self.status_var.set(
            f"{self.book_title}: {len(self.chapters)} spine docs, {keep} marked write, "
            f"{len(self.image_paths)} images."
        )

    def _refill(self) -> None:
        self.listbox.delete(0, "end")
        pad = max(2, len(str(len(self.chapters))))
        for ch in self.chapters:
            mark = "  " if ch.include else "x "
            self.listbox.insert(
                "end",
                f"{mark}{ch.index:0{pad}d}  {ch.title}  ({ch.chars} chars)",
            )

    def _selected(self) -> Chapter | None:
        sel = self.listbox.curselection()
        if not sel:
            return None
        i = int(sel[0])
        if 0 <= i < len(self.chapters):
            return self.chapters[i]
        return None

    def _show(self, _evt=None) -> None:
        ch = self._selected()
        self.preview.delete("1.0", "end")
        if not ch:
            return
        head = f"{ch.title}\n{ch.href}\n{ch.chars} chars\ninclude={ch.include}\n\n"
        self.preview.insert("1.0", head + ch.body[:8000])

    def _toggle(self) -> None:
        ch = self._selected()
        if not ch:
            return
        ch.include = not ch.include
        self._refill()

    def _write(self) -> None:
        if not self.chapters:
            messagebox.showerror(APP_TITLE, "Scan an EPUB first. Use the OCR tab for pictures only.")
            return
        out = Path(self.out_var.get().strip() or DEFAULT_OUT)
        chosen = [c for c in self.chapters if c.include]
        if not chosen:
            messagebox.showerror(APP_TITLE, "No chapters marked for write.")
            return
        img_dir = self._img_dest()
        img_written: list[Path] = []
        if self.images_var.get():
            epub = Path(self.epub_var.get().strip())
            if not epub.is_file():
                messagebox.showerror(APP_TITLE, f"EPUB not found:\n{epub}")
                return
            try:
                img_written = write_images(epub, img_dir)
            except Exception as e:
                messagebox.showerror(APP_TITLE, str(e))
                return
        out.mkdir(parents=True, exist_ok=True)
        pad = max(3, len(str(chosen[-1].index)))
        written = 0
        parts_for_raw: list[str] = []
        for ch in chosen:
            body = strip_page_numbers(ch.body)
            dest = out / filename_for(ch, pad)
            dest.write_text(body, encoding="utf-8")
            written += 1
            parts_for_raw.append(body.strip())
        raw_path = None
        if self.raw_var.get():
            raw_path = out.parent / "raw_full.txt"
            joined = ("\n\n⸻\n\n").join(parts_for_raw) + "\n"
            raw_path.write_text(joined, encoding="utf-8")
        msg = f"Wrote {written} files to:\n{out}"
        if raw_path:
            msg += f"\n{raw_path.name} ({raw_path.stat().st_size} bytes)"
        if img_written:
            msg += f"\nImages: {len(img_written)} files in {img_dir}"
        self.status_var.set(msg.replace("\n", " | "))
        messagebox.showinfo(APP_TITLE, msg)

    def mainloop(self, n: int = 0):  # type: ignore[override]
        root = self._own_root or self.winfo_toplevel()
        root.mainloop(n)


def main() -> None:
    ExtractApp().mainloop()


if __name__ == "__main__":
    main()
