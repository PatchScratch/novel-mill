#!/usr/bin/env python3
# Novel Mill — Split tab. One UTF-8 dump → in\*.txt by heading / page tag / rule.
# Windows: py -3 wn-raw-split.py

from __future__ import annotations

import json
import os
import re
import sys
import tkinter as tk
from dataclasses import asdict, dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from wn_series import app_version, config_dir, read_text, safe_stem, strip_page_numbers, write_text

APP_TITLE = "Split"
DEFAULT_RAW = ""
DEFAULT_OUT = ""

MAX_HEADING_LEN = 80
__version__ = app_version()
SCRIPT_DIR = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):
    # Inside a PyInstaller bundle the shipped rules file is read-only;
    # edits go to a seeded copy in the user config dir.
    DEFAULT_RULES_PATH = config_dir() / "wn-raw-split.rules.json"
    _bundled_rules = SCRIPT_DIR / "wn-raw-split.rules.json"
    if not DEFAULT_RULES_PATH.is_file() and _bundled_rules.is_file():
        try:
            DEFAULT_RULES_PATH.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_RULES_PATH.write_bytes(_bundled_rules.read_bytes())
        except OSError:
            pass
else:
    DEFAULT_RULES_PATH = SCRIPT_DIR / "wn-raw-split.rules.json"


@dataclass
class UserRule:
    id: str
    label: str
    pattern: str
    flags: str = ""
    enabled: bool = True
    in_auto: bool = True
    in_generic: bool = True
    whole_line: bool = True
    weight: float = 1.0

    def compile(self) -> re.Pattern[str]:
        f = 0
        if "i" in self.flags.lower():
            f |= re.IGNORECASE
        if "m" in self.flags.lower():
            f |= re.MULTILINE
        if "s" in self.flags.lower():
            f |= re.DOTALL
        return re.compile(self.pattern, f)


USER_RULES: list[UserRule] = []
RULES_PATH = DEFAULT_RULES_PATH

MODES: list[tuple[str, str]] = [
    ("auto", "Auto (best heading family)"),
    ("generic", "Generic chapter headings (JP/EN/CN/KR)"),
    ("aozora_dai", "Aozora large heading  大見出し"),
    ("aozora_chu", "Aozora medium heading 中見出し"),
    ("aozora_sho", "Aozora small heading  小見出し"),
    ("wa", "第N話 / N話 / 第N话"),
    ("sho", "第N章 / Chapter N / 제N장"),
    ("ep", "ep001 / Episode 1"),
    ("scene", "Scene001"),
    ("named", "Prologue / プロローグ / 閑話 / Afterword"),
    ("volume", "Volume / 第N巻 / 第N部"),
    ("ocr_page", "[0017] OCR page tags (stitched raw_full)"),
    ("pagebreak", "［＃改ページ］ / page break"),
    ("rule", "⸻ ─── * * * rules only"),
    ("custom", "Custom regex (Python)"),
]

HEADING_END = re.compile(
    r"［＃「(?P<title>[^」]+)」は(?P<kind>大見出し|中見出し|小見出し)終わり］"
)
HEADING_START = re.compile(
    r"［＃「(?P<title>[^」]+)」は(?P<kind>大見出し|中見出し|小見出し)］"
)
RE_PAGE = re.compile(r"［＃改ページ］|\[pagebreak\]|<!--\s*pagebreak\s*-->", re.I)
RE_RULE = re.compile(
    r"^[\s　]*(?:⸻+|──+|━━+|[─－—_*＊※~～]{3,}|(?:\*\s*){3,}|(?:＊\s*){3,})[\s　]*$"
)
RE_OCR_PAGE = re.compile(r"^[\s　]*\[([0-9A-Za-z._\-]+)\][\s　]*$")

# Short-line chapter headings. Keep anchored; dialogue rarely matches the whole line.
RE_WA = re.compile(
    r"^[\s　\[【]*(?:第)?\s*([0-9０-９一二三四五六七八九十百千]+)\s*(?:話|话|화)\b.*$"
)
RE_SHO = re.compile(
    r"^[\s　\[【]*"
    r"(?:"
    r"第\s*([0-9０-９一二三四五六七八九十百千]+)\s*(?:章|節|节|편)"
    r"|[Cc]hapter\s*([0-9IVXLCivxlc]+)"
    r"|[Cc]h\.?\s*([0-9]+)"
    r"|제\s*([0-9]+)\s*(?:장|화)"
    r")"
    r"\b.*$"
)
RE_EP = re.compile(
    r"^[\s　]*(?:ep|EP|Ep|Episode|episode|エピソード)[\s._-]*0*(\d+)\b.*$"
)
RE_SCENE = re.compile(
    r"^[\s　]*(?:Scene|scene|SCENE|シーン)[\s._-]*0*(\d+)\b.*$"
)
RE_VOLUME = re.compile(
    r"^[\s　\[【]*"
    r"(?:"
    r"第\s*([0-9０-９一二三四五六七八九十百千]+)\s*(?:巻|卷|部|編|编)"
    r"|[Vv]ol(?:ume)?\.?\s*([0-9]+)"
    r"|[Bb]ook\s*([0-9]+)"
    r"|[Aa]rc\s*([0-9]+)"
    r")"
    r"\b.*$"
)
RE_NAMED = re.compile(
    r"^[\s　\[【〈《(（]*"
    r"(?:"
    r"プロローグ|プロローグ篇|序章|序幕|はじまり"
    r"|エピローグ|終章|終幕|結末"
    r"|インタールード|インターミッション"
    r"|あとがき|後書き|まえがき|前書き|あとがきにかえて"
    r"|閑話|余話|番外(?:編|篇)?|特別篇|書き下ろし"
    r"|Prologue|Epilogue|Interlude|Afterword|Foreword|Preface"
    r"|Introduction|Prelude|Postscript"
    r"|서장|프롤로그|에필로그"
    r"|序章|尾声|后记|後記|番外"
    r")"
    r"(?:\s*[:：\-–—].*)?"
    r"[\s　\]】〉》)）]*$",
    re.I,
)

# Auto prefers real chapter families over decorative breaks.
AUTO_PRIORITY = [
    "ocr_page",
    "aozora_dai",
    "generic",
    "wa",
    "sho",
    "ep",
    "named",
    "aozora_chu",
    "volume",
    "scene",
    "aozora_sho",
    "pagebreak",
    "rule",
]


def load_user_rules(path: Path | None = None) -> str:
    """Load extra splitters from JSON. Returns a status line."""
    global USER_RULES, RULES_PATH, MAX_HEADING_LEN
    RULES_PATH = path or RULES_PATH
    if not RULES_PATH.is_file():
        USER_RULES = []
        return f"No rules file at {RULES_PATH} (built-in modes only)."
    data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
    if isinstance(data.get("heading_max_len"), int) and data["heading_max_len"] > 10:
        MAX_HEADING_LEN = data["heading_max_len"]
    rules: list[UserRule] = []
    for raw in data.get("rules") or []:
        rid = str(raw.get("id") or "").strip()
        pat = str(raw.get("pattern") or "")
        if not rid or not pat:
            continue
        rules.append(
            UserRule(
                id=rid,
                label=str(raw.get("label") or rid),
                pattern=pat,
                flags=str(raw.get("flags") or ""),
                enabled=bool(raw.get("enabled", True)),
                in_auto=bool(raw.get("in_auto", True)),
                in_generic=bool(raw.get("in_generic", True)),
                whole_line=bool(raw.get("whole_line", True)),
                weight=float(raw.get("weight") or 1.0),
            )
        )
        try:
            rules[-1].compile()
        except re.error as e:
            raise ValueError(f"Rule {rid}: {e}") from e
    USER_RULES = rules
    on = [r.id for r in USER_RULES if r.enabled]
    return f"Loaded {len(USER_RULES)} user rules from {RULES_PATH.name} ({len(on)} enabled)."


def save_user_rules(path: Path | None = None) -> None:
    dest = path or RULES_PATH
    payload = {
        "heading_max_len": MAX_HEADING_LEN,
        "rules": [asdict(r) for r in USER_RULES],
    }
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def user_rule(mode: str) -> UserRule | None:
    for r in USER_RULES:
        if r.id == mode:
            return r
    return None


def all_modes() -> list[tuple[str, str]]:
    extra = [(r.id, f"User: {r.label}") for r in USER_RULES if r.enabled]
    return MODES + extra


def collect_user_rule(lines: list[str], rule: UserRule) -> list[tuple[int, str]]:
    cre = rule.compile()
    out: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if rule.whole_line and not heading_ok(line):
            continue
        target = line.strip() if rule.whole_line else line
        if cre.search(target):
            out.append((i, line.strip() or f"part_{len(out)+1}"))
    return out


def lines_of(raw: str) -> list[str]:
    return raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")


def heading_ok(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > MAX_HEADING_LEN:
        return False
    if s.startswith(("「", "『", "“", '"', "(", "（")):
        return False
    return True


class Split:
    def __init__(self, index: int, start_line: int, title: str, body: str) -> None:
        self.index = index
        self.start_line = start_line
        self.title = title
        self.body = body.rstrip() + "\n"

    @property
    def chars(self) -> int:
        return len(self.body)


def collect_aozora(lines: list[str], want: str) -> list[tuple[int, str]]:
    starts: list[tuple[int, str]] = []
    seen: set[int] = set()

    def add(i: int, title: str) -> None:
        if i in seen:
            return
        seen.add(i)
        starts.append((i, title.strip() or f"part_{len(starts)+1}"))

    for i, line in enumerate(lines):
        m = HEADING_START.search(line)
        if m and m.group("kind") == want:
            add(i, m.group("title"))
            continue
        m = HEADING_END.search(line)
        if m and m.group("kind") == want:
            title = m.group("title")
            if i > 0 and title in lines[i - 1]:
                add(i - 1, title)
            else:
                add(i, title)
    return starts


def collect_regex(lines: list[str], cre: re.Pattern[str]) -> list[tuple[int, str]]:
    starts: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        if not heading_ok(line):
            continue
        if cre.match(line.strip()):
            starts.append((i, line.strip()))
    return starts


def collect_generic(lines: list[str]) -> list[tuple[int, str]]:
    """Union of chapter-like headings. Deduped by line number."""
    bag: dict[int, str] = {}
    for fn in (
        lambda ls: collect_aozora(ls, "大見出し"),
        lambda ls: collect_regex(ls, RE_WA),
        lambda ls: collect_regex(ls, RE_SHO),
        lambda ls: collect_regex(ls, RE_EP),
        lambda ls: collect_regex(ls, RE_NAMED),
        lambda ls: collect_regex(ls, RE_VOLUME),
    ):
        for i, title in fn(lines):
            bag.setdefault(i, title)
    for rule in USER_RULES:
        if rule.enabled and rule.in_generic:
            for i, title in collect_user_rule(lines, rule):
                bag.setdefault(i, title)
    return sorted(bag.items())


def collect_starts(lines: list[str], mode: str, custom: str) -> list[tuple[int, str]]:
    if mode == "custom":
        try:
            cre = re.compile(custom)
        except re.error as e:
            raise ValueError(f"Bad regex: {e}") from e
        out = []
        for i, line in enumerate(lines):
            if cre.search(line):
                out.append((i, line.strip() or f"part_{len(out)+1}"))
        return out
    if mode == "generic":
        return collect_generic(lines)
    if mode == "aozora_dai":
        return collect_aozora(lines, "大見出し")
    if mode == "aozora_chu":
        return collect_aozora(lines, "中見出し")
    if mode == "aozora_sho":
        return collect_aozora(lines, "小見出し")
    if mode == "wa":
        return collect_regex(lines, RE_WA)
    if mode == "sho":
        return collect_regex(lines, RE_SHO)
    if mode == "ep":
        return collect_regex(lines, RE_EP)
    if mode == "scene":
        return collect_regex(lines, RE_SCENE)
    if mode == "named":
        return collect_regex(lines, RE_NAMED)
    if mode == "volume":
        return collect_regex(lines, RE_VOLUME)
    if mode == "ocr_page":
        out = []
        for i, line in enumerate(lines):
            m = RE_OCR_PAGE.match(line)
            if m:
                out.append((i, m.group(1)))
        return out
    if mode == "pagebreak":
        out: list[tuple[int, str]] = []
        for i, line in enumerate(lines):
            if RE_PAGE.search(line):
                out.append((i, f"page_{len(out)+1}"))
        return out
    if mode == "rule":
        return [(i, "break") for i, line in enumerate(lines) if RE_RULE.match(line)]
    rule = user_rule(mode)
    if rule:
        if not rule.enabled:
            return []
        return collect_user_rule(lines, rule)
    raise ValueError(f"Unknown mode {mode}")


def apply_splits(lines: list[str], starts: list[tuple[int, str]]) -> list[Split]:
    if not starts:
        return []
    cleaned: list[tuple[int, str]] = []
    seen: set[int] = set()
    for i, title in starts:
        if i in seen:
            continue
        seen.add(i)
        cleaned.append((i, title))
    cleaned.sort(key=lambda x: x[0])

    parts: list[Split] = []
    preamble = "\n".join(lines[: cleaned[0][0]]).strip()
    if preamble:
        parts.append(Split(0, 1, "front_matter", preamble + "\n"))
    n = 1
    for k, (start, title) in enumerate(cleaned):
        end = cleaned[k + 1][0] if k + 1 < len(cleaned) else len(lines)
        body = "\n".join(lines[start:end])
        if not body.strip():
            continue
        parts.append(Split(n, start + 1, title, body))
        n += 1
    return parts


def score_mode(lines: list[str], mode: str) -> int:
    if mode in ("auto", "custom"):
        return 0
    try:
        hits = collect_starts(lines, mode, "")
    except ValueError:
        return 0
    n = len(hits)
    if n < 2 and mode in ("rule", "pagebreak"):
        return 0
    return n


def pick_auto(lines: list[str]) -> str:
    best_key = "generic"
    best_score = -1.0
    keys = list(AUTO_PRIORITY) + [r.id for r in USER_RULES if r.enabled and r.in_auto]
    for key in keys:
        n = score_mode(lines, key)
        weight = float(n)
        if key == "ocr_page":
            weight = n * 3.0
        elif key in ("rule", "pagebreak"):
            weight = n * 0.2
        elif key == "generic":
            weight = n * 1.05
        else:
            ur = user_rule(key)
            if ur:
                weight = n * ur.weight
        if weight > best_score:
            best_score = weight
            best_key = key
    if best_score <= 0:
        return "generic"
    return best_key


def filename_for(part: Split, pad: int) -> str:
    if part.index == 0:
        return "000_front.txt"
    return f"{part.index:0{pad}d}_{safe_stem(part.title, f'part_{part.index}')}.txt"


def strip_markup(text: str) -> str:
    text = strip_page_numbers(text)
    text = HEADING_START.sub("", text)
    text = HEADING_END.sub("", text)
    text = RE_PAGE.sub("", text)
    text = re.sub(r"［＃.*?］", "", text)
    text = re.sub(r"《[^》]*》", "", text)
    text = re.sub(r"<[^>]+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


class SplitApp(ttk.Frame):
    def __init__(self, master: tk.Misc | None = None) -> None:
        own = master is None
        if own:
            master = tk.Tk()
            master.title(APP_TITLE)
            master.geometry("1000x720")
            master.minsize(840, 560)
        super().__init__(master)
        if own:
            self.pack(fill="both", expand=True)
        self._own_root = master if own else None

        self.raw_var = tk.StringVar(value=DEFAULT_RAW)
        self.out_var = tk.StringVar(value=DEFAULT_OUT)
        self.custom_var = tk.StringVar(value=r"^(Chapter|第.+話|第.+章)\b")
        self.rules_var = tk.StringVar(value=str(DEFAULT_RULES_PATH))
        self.strip_var = tk.BooleanVar(value=True)
        self.keep_front_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Load a raw .txt, Scan, then Write.")

        self.lines: list[str] = []
        self.parts: list[Split] = []
        self._build()
        self._reload_rules(silent=True)

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        root = ttk.Frame(self)
        root.pack(fill="both", expand=True)

        self.files_fr = ttk.LabelFrame(root, text="Files")
        self.files_fr.pack(fill="x", **pad)
        ttk.Label(self.files_fr, text="raw_full.txt").grid(row=0, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(self.files_fr, textvariable=self.raw_var).grid(row=0, column=1, sticky="ew", padx=4)
        self.btn_raw = ttk.Button(self.files_fr, text="Browse", command=self._pick_raw)
        self.btn_raw.grid(row=0, column=2, padx=6)
        self.lbl_scenes = ttk.Label(self.files_fr, text="Scenes (in\\)")
        self.lbl_scenes.grid(row=1, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(self.files_fr, textvariable=self.out_var).grid(row=1, column=1, sticky="ew", padx=4)
        self.btn_out = ttk.Button(self.files_fr, text="Browse", command=self._pick_out)
        self.btn_out.grid(row=1, column=2, padx=6)
        self.lbl_rules = ttk.Label(self.files_fr, text="Rules JSON")
        self.lbl_rules.grid(row=2, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(self.files_fr, textvariable=self.rules_var).grid(row=2, column=1, sticky="ew", padx=4)
        self.btn_rules = ttk.Button(self.files_fr, text="Browse", command=self._pick_rules)
        self.btn_rules.grid(row=2, column=2, padx=6)
        self.files_fr.columnconfigure(1, weight=1)

        self.opts_fr = ttk.LabelFrame(root, text="Split on")
        self.opts_fr.pack(fill="x", **pad)
        self.lbl_mode = ttk.Label(self.opts_fr, text="Mode")
        self.lbl_mode.grid(row=0, column=0, sticky="w", padx=6, pady=3)
        self.mode_combo = ttk.Combobox(
            self.opts_fr, values=[lab for _k, lab in MODES], state="readonly", width=46
        )
        self.mode_combo.current(0)
        self.mode_combo.grid(row=0, column=1, sticky="w", padx=4)
        self.lbl_regex = ttk.Label(self.opts_fr, text="Custom regex")
        self.lbl_regex.grid(row=1, column=0, sticky="w", padx=6, pady=3)
        ttk.Entry(self.opts_fr, textvariable=self.custom_var).grid(row=1, column=1, sticky="ew", padx=4)
        self.chk_strip = ttk.Checkbutton(
            self.opts_fr,
            text="Strip 青空 / HTML / 《ruby》 from output",
            variable=self.strip_var,
        )
        self.chk_strip.grid(row=2, column=1, sticky="w", padx=4, pady=2)
        self.chk_front = ttk.Checkbutton(
            self.opts_fr,
            text="Keep preamble as 000_front.txt (skip in the mill)",
            variable=self.keep_front_var,
        )
        self.chk_front.grid(row=3, column=1, sticky="w", padx=4, pady=2)
        self.opts_fr.columnconfigure(1, weight=1)

        btns = ttk.Frame(root)
        btns.pack(fill="x", **pad)
        self.btn_scan = ttk.Button(btns, text="Scan", command=self._scan)
        self.btn_scan.pack(side="left", padx=4)
        self.btn_hand = ttk.Button(btns, text="Handoff to Mill", command=self._handoff_mill)
        self.btn_hand.pack(side="left", padx=4)
        self.btn_write = ttk.Button(btns, text="Write files", command=self._write)
        self.btn_write.pack(side="left", padx=4)
        self.btn_reload = ttk.Button(btns, text="Reload rules", command=self._reload_rules)
        self.btn_reload.pack(side="left", padx=4)
        self.btn_add = ttk.Button(btns, text="Add rule", command=self._add_rule)
        self.btn_add.pack(side="left", padx=4)
        self.btn_json = ttk.Button(btns, text="Edit JSON", command=self._edit_json)
        self.btn_json.pack(side="left", padx=4)

        ttk.Label(root, textvariable=self.status_var).pack(anchor="w", padx=10)

        mid = ttk.Panedwindow(root, orient="horizontal")
        mid.pack(fill="both", expand=True, padx=8, pady=6)
        left = ttk.Frame(mid)
        right = ttk.Frame(mid)
        mid.add(left, weight=1)
        mid.add(right, weight=1)
        self.lbl_parts = ttk.Label(left, text="Parts")
        self.lbl_parts.pack(anchor="w")
        self.listbox = tk.Listbox(left, height=18)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._show_part)
        self.lbl_prev = ttk.Label(right, text="Preview")
        self.lbl_prev.pack(anchor="w")
        self.preview = tk.Text(right, wrap="word", height=18)
        self.preview.pack(fill="both", expand=True)

        self.hint_lbl = ttk.Label(
            root,
            text="Add splitters in wn-raw-split.rules.json (id, label, pattern).",
        )
        self.hint_lbl.pack(anchor="w", padx=10, pady=(0, 8))
        self._ui_lang = "en"

    def set_ui_lang(self, lang: str) -> None:
        ja = lang != "en"
        self.files_fr.configure(text="ファイル" if ja else "Files")
        self.opts_fr.configure(text="分割条件" if ja else "Split on")
        self.lbl_scenes.configure(text="シーン (in\\)" if ja else "Scenes (in\\)")
        self.lbl_rules.configure(text="ルール JSON" if ja else "Rules JSON")
        self.lbl_mode.configure(text="モード" if ja else "Mode")
        self.lbl_regex.configure(text="カスタム正規表現" if ja else "Custom regex")
        for b in (self.btn_raw, self.btn_out, self.btn_rules):
            b.configure(text="参照" if ja else "Browse")
        self.chk_strip.configure(text="青空 / HTML / 《ルビ》を除去" if ja else "Strip 青空 / HTML / 《ruby》 from output")
        self.chk_front.configure(text="前書きを 000_front.txt に残す" if ja else "Keep preamble as 000_front.txt (skip in the mill)")
        self.btn_scan.configure(text="スキャン" if ja else "Scan")
        self.btn_hand.configure(text="ミルへ渡す" if ja else "Handoff to Mill")
        self.btn_write.configure(text="書き出し" if ja else "Write files")
        self.btn_reload.configure(text="ルール再読込" if ja else "Reload rules")
        self.btn_add.configure(text="ルール追加" if ja else "Add rule")
        self.btn_json.configure(text="JSON 編集" if ja else "Edit JSON")
        self.lbl_parts.configure(text="分割結果" if ja else "Parts")
        self.lbl_prev.configure(text="プレビュー" if ja else "Preview")
        self.hint_lbl.configure(
            text="wn-raw-split.rules.json に分割ルールを追加できます。" if ja
            else "Add splitters in wn-raw-split.rules.json (id, label, pattern)."
        )

    def _mode_key(self) -> str:
        label = self.mode_combo.get()
        for key, lab in all_modes():
            if lab == label:
                return key
        return "auto"

    def _refresh_modes(self, keep: str | None = None) -> None:
        labels = [lab for _k, lab in all_modes()]
        current = keep or self.mode_combo.get()
        self.mode_combo["values"] = labels
        if current in labels:
            self.mode_combo.set(current)
        else:
            self.mode_combo.current(0)

    def _reload_rules(self, silent: bool = False) -> None:
        path = Path(self.rules_var.get() or DEFAULT_RULES_PATH)
        try:
            msg = load_user_rules(path)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            messagebox.showerror(APP_TITLE, f"Rules file error:\n{e}")
            return
        self._refresh_modes()
        self.status_var.set(msg)
        if not silent:
            messagebox.showinfo(APP_TITLE, msg)

    def _pick_rules(self) -> None:
        p = filedialog.askopenfilename(
            initialdir=str(Path(self.rules_var.get()).parent),
            filetypes=[("JSON", "*.json"), ("All", "*.*")],
        )
        if p:
            self.rules_var.set(p)
            self._reload_rules()

    def _add_rule(self) -> None:
        rid = simpledialog.askstring(APP_TITLE, "Rule id (no spaces):", parent=self)
        if not rid:
            return
        rid = re.sub(r"\W+", "_", rid.strip())
        if user_rule(rid) or rid in {k for k, _ in MODES}:
            messagebox.showerror(APP_TITLE, f"Id already used: {rid}")
            return
        label = simpledialog.askstring(APP_TITLE, "Label:", parent=self, initialvalue=rid) or rid
        pattern = simpledialog.askstring(
            APP_TITLE,
            "Python regex (usually start with ^ for a whole heading line):",
            parent=self,
        )
        if not pattern:
            return
        try:
            re.compile(pattern)
        except re.error as e:
            messagebox.showerror(APP_TITLE, f"Bad regex:\n{e}")
            return
        USER_RULES.append(
            UserRule(id=rid, label=label, pattern=pattern, flags="i", enabled=True)
        )
        dest = Path(self.rules_var.get() or DEFAULT_RULES_PATH)
        try:
            save_user_rules(dest)
        except OSError as e:
            messagebox.showerror(APP_TITLE, str(e))
            return
        self._refresh_modes(keep=f"User: {label}")
        self.status_var.set(f"Saved rule {rid} to {dest.name}")

    def _edit_json(self) -> None:
        path = Path(self.rules_var.get() or DEFAULT_RULES_PATH)
        if not path.is_file():
            save_user_rules(path)
        try:
            os.startfile(path)  # type: ignore[attr-defined]
        except AttributeError:
            os.system(f'xdg-open "{path}"')

    def apply_series(self, layout: dict) -> None:
        self.raw_var.set(str(layout["raw"]))
        self.out_var.set(str(layout["in_dir"]))

    def _handoff_mill(self) -> None:
        fn = getattr(self, "handoff_mill", None)
        if callable(fn):
            fn()

    def _pick_raw(self) -> None:
        p = filedialog.askopenfilename(
            initialdir=str(Path(self.raw_var.get()).parent),
            filetypes=[("Text", "*.txt"), ("All", "*.*")],
        )
        if p:
            self.raw_var.set(p)
            parent = Path(p).parent
            self.out_var.set(str(parent / "in"))

    def _pick_out(self) -> None:
        d = filedialog.askdirectory(initialdir=self.out_var.get())
        if d:
            self.out_var.set(d)

    def _scan(self) -> None:
        path = Path(self.raw_var.get())
        if not path.is_file():
            messagebox.showerror(APP_TITLE, f"Raw file not found:\n{path}")
            return
        try:
            raw = read_text(path)
        except ValueError as e:
            messagebox.showerror(APP_TITLE, str(e))
            return
        self.lines = lines_of(raw)
        mode = self._mode_key()
        used = mode
        try:
            if mode == "auto":
                used = pick_auto(self.lines)
            starts = collect_starts(self.lines, used, self.custom_var.get())
        except ValueError as e:
            messagebox.showerror(APP_TITLE, str(e))
            return
        self.parts = apply_splits(self.lines, starts)
        if not self.keep_front_var.get():
            self.parts = [p for p in self.parts if p.index != 0]
        counts = {
            k: score_mode(self.lines, k)
            for k, _ in all_modes()
            if k not in ("auto", "custom")
        }
        summary = "  ".join(f"{k}:{n}" for k, n in counts.items() if n)
        self.listbox.delete(0, "end")
        pad = max(2, len(str(max((p.index for p in self.parts), default=1))))
        for p in self.parts:
            name = filename_for(p, pad)
            self.listbox.insert(
                "end", f"{name}   {p.chars}c   L{p.start_line}   {p.title[:48]}"
            )
        self.status_var.set(
            f"{path.name}: {len(self.lines)} lines, {len(raw)} chars. "
            f"Mode={used} → {len(self.parts)} files.  Hits: {summary or 'none'}"
        )
        if self.parts:
            self.listbox.selection_set(0)
            self._show_part()
        else:
            self.preview.delete("1.0", "end")
            self.preview.insert(
                "1.0",
                "No splits. Try Generic, 第N話, Chapter N, or a custom regex.",
            )

    def _show_part(self, _evt=None) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        part = self.parts[sel[0]]
        body = strip_markup(part.body) if self.strip_var.get() else _strip_pages(part.body)
        self.preview.delete("1.0", "end")
        extra = "\n\n… [truncated preview]" if len(body) > 8000 else ""
        self.preview.insert("1.0", body[:8000] + extra)

    def _write(self) -> None:
        if not self.parts:
            messagebox.showerror(APP_TITLE, "Scan first.")
            return
        out = Path(self.out_var.get())
        out.mkdir(parents=True, exist_ok=True)
        pad = max(2, len(str(max(p.index for p in self.parts))))
        written = 0
        for part in self.parts:
            body = strip_markup(part.body) if self.strip_var.get() else _strip_pages(part.body)
            write_text(out / filename_for(part, pad), body)
            written += 1
        self.status_var.set(f"Wrote {written} files to {out}")
        messagebox.showinfo(APP_TITLE, f"Wrote {written} files to:\n{out}")


    def mainloop(self, n: int = 0):  # type: ignore[override]
        root = self._own_root or self.winfo_toplevel()
        root.mainloop(n)


def main() -> None:
    SplitApp().mainloop()


if __name__ == "__main__":
    main()
