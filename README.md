# wn-local-mill

Version **1.0.0**. Private production release.

Two Windows GUIs that turn one web-novel / light-novel dump into English scene files via a local LM Studio server. No pip packages. Standard library plus Tk only.

| Tool | File | Job |
| --- | --- | --- |
| WN Raw Split | `wn-raw-split.py` | Split `raw_full.txt` into `in/*.txt` |
| WN Scene Mill | `wn-scene-mill.py` | One POST per scene to LM Studio; write `out/*.en.txt` |

Launchers: `wn-raw-split.bat`, `wn-scene-mill.bat`.

## Requirements

- Windows with Python 3.10+ (`py -3` on PATH). Tkinter is included with the official Windows installer.
- [LM Studio](https://lmstudio.ai/) Developer server on `http://127.0.0.1:1234/v1`.
- Proven local load (RTX 3070 8 GB): Gemma 4 12B-it Q4 Unsloth, context **4096**, Thinking **off**, **no mmproj**, **RAG uninstalled**. Clean decode is about 5–6 tok/s. RAG drops that to ~0.2 tok/s and overflows the window.

## Install

```
git clone https://github.com/PatchScratch/wn-local-mill.git
cd wn-local-mill
```

Or copy the six runtime files into a folder:

```
wn-raw-split.py
wn-raw-split.bat
wn-raw-split.rules.json
wn-scene-mill.py
wn-scene-mill.bat
```

Double-click a `.bat`, or:

```
py -3 wn-raw-split.py
py -3 wn-scene-mill.py
```

## Series folder layout

```
D:\Translation Software\WN-Work\_series\<id>\
  raw_full.txt          # one dump
  in\                   # splitter output
  out\                  # mill English
  lock\
    prompt.txt          # system lock (required style)
    glossary.txt        # names
    voices.txt          # who owns （） inner voice
```

Mill → **Make folders** creates `in`, `out`, `lock` and writes sample lock files if they are missing.

Skip `000_front.txt` in the mill (title pages, TOC). Leave it in `in\` or delete it.

## 1. Split the dump

1. Open WN Raw Split.
2. Point **Raw dump** at `raw_full.txt`. **Write to** defaults to a sibling `in\` folder.
3. Mode **Auto (best heading family)** is the usual choice. **Generic** unions 話 / 章 / Chapter / 화 / ep / named extras / volumes plus enabled user rules.
4. **Scan**. Check the part list and preview.
5. **Write files**. Names look like `01_第1話_出会い.txt`.

Built-in families: 青空 大・中・小見出し, 第N話 / N話 / 第N话, 第N章 / Chapter N / 제N장, ep001 / Episode, Scene001, Prologue / プロローグ / 閑話 / Afterword, Volume / 第N巻 / 第N部, page-break marks, rule lines (`───`, `***`).

Use **Scene** only to cut a fat episode that overflows 4096 context. Do not run Scene on a whole novel.

Encodings tried in order: UTF-8 BOM, UTF-8, cp932, Shift_JIS, GB18030, EUC-KR.

## 2. Add your own splitters

Edit `wn-raw-split.rules.json` (same folder as the script) or use **Add rule** in the GUI, then **Reload rules**.

```json
{
  "heading_max_len": 80,
  "rules": [
    {
      "id": "part_en",
      "label": "Part I / Part 2",
      "pattern": "^\\s*Part\\s+[0-9IVXLCivxlc]+\\b.*",
      "flags": "i",
      "enabled": true,
      "in_auto": true,
      "in_generic": true,
      "whole_line": true,
      "weight": 1.0
    }
  ]
}
```

| Field | Meaning |
| --- | --- |
| `id` | Mode key. No spaces. |
| `pattern` | Python regex. Anchor with `^` for a heading line. |
| `flags` | `i` / `m` / `s` |
| `whole_line` | Only test lines shorter than `heading_max_len` that are not dialogue |
| `in_auto` / `in_generic` | Include in those modes |
| `weight` | Auto-mode score multiplier |
| `enabled` | Off = ignored |

Shipped examples: Part I/II, Day N / N日目, disabled HTML `<h1>`–`<h3>` chapter tags.

## 3. Mill overnight

LM Studio first:

1. Load Gemma 4 12B-it Q4. Context 4096.
2. Uninstall RAG. Remove any mmproj / vision adapter from the model folder.
3. Thinking off. No attachments. No chat history.
4. Start the local server on port 1234.

Then WN Scene Mill:

1. **Series** = the novel folder. `in`, `out`, `lock` fill in.
2. Model id must match LM Studio (`google/gemma-4-12b-it` or whatever `/v1/models` lists). **Ping API** to check.
3. Temperature `0.1`. Timeout `600` seconds per file.
4. **Start queue**. Existing `*.en.txt` are skipped unless **Overwrite** is on.
5. **Stop after this file** finishes the current POST, then exits.

Each file is a new request:

- `system` = concatenation of `lock/prompt.txt`, `glossary.txt`, `voices.txt`
- `user` = `Translate to English only` wrapper around the Japanese scene

No conversation history. Keep the lock short. If the API returns a context overflow, split that one scene smaller and re-queue.

## Lock file rules that matter

- English only. No synopsis, notes, or Japanese echo.
- Keep `「」『』（）！？…〜ー`. Convert only `。` → `.` and `、` → `,`.
- `「」` = spoken. `（）` = inner voice of the person who just acted or spoke, first person.
- Onomatopoeia in romaji (`Bassaa`, `Kyaa`). No Slash / WHOOSH / BAM.
- Drop 青空 `［＃…］` markup; do not explain it.

## Dual stream (how this tool is used)

- **Stream A** — simple chapters: Sugoi Toolkit Offline Japan, not this mill.
- **Stream C** — voice / glossary novels: this mill + LM Studio.

Do not attach RAG, Nomic embeddings, or previous chapters. Consistency comes from the lock files, not from memory.

## License

MIT. See `LICENSE`.
