# Novel Mill

A small Windows (and Linux) desktop app that turns a Japanese **web novel** or **light novel** into English scene files using a model you run yourself in LM Studio.

The GitHub folder is still called `wn-local-mill`. That is only the old project name. The window title is **Novel Mill**. Leave the `.py` file names alone so the copy on `D:\\Translation Software\\wn-local-mill\\` keeps working.

There is no cloud account and no second AI server in this app. The mill talks only to LM Studio on `http://127.0.0.1:1234`.

## What you need

- Python 3 on the PATH (`py -3` on Windows)
- LM Studio, model loaded, Developer server on port 1234
- For scanned pages: Tesseract-OCR with `jpn` and `jpn_vert` traineddata
- For store EPUBs: Calibre. Convert EPUB to EPUB (or TXT) so Adobe DRM is gone before you Extract

## How to run

1. Close Novel Mill if it is open.
2. Copy the files from this repo over `D:\\Translation Software\\wn-local-mill\\` (same names).
3. Double-click `wn-local-mill.bat`.
4. In LM Studio, load the model with **context 8192** (4096 is too small once lock files are included).

Standalone bats still open one tab as its own window. Day to day, use the tabbed host.

## The five tabs

| Tab | What it does |
| --- | --- |
| **EPUB** | Opens a DRM-free EPUB, writes chapter text into `in\\` and pictures into `images\\`. Refuses Adobe AES / ADEPT files. |
| **OCR** | Runs Tesseract on a folder of page pictures. Writes `ocr\\*.ocr.txt`. **Combine** stitches those into `raw_full.txt`. |
| **Split** | Cuts one big Japanese dump (`raw_full.txt`) into many small files in `in\\`. |
| **Mill** | Sends each `in\\*.txt` to LM Studio, one HTTP request per file. Writes `out\\*.en.txt`. |
| **Settings** | The shared **book folder**. Apply to tabs so every tab points at the same tree. |

Usual path: EPUB (or OCR then Combine) then Split then Mill.

## Book folder layout

One folder per WN series or per LN volume:

    my-book\\
      raw_full.txt     whole Japanese text (Split input)
      in\\              one scene or chapter per file (Mill input)
      out\\             English files from the mill (*.en.txt)
      images\\          page pictures
      ocr\\             Tesseract output
      lock\\            mill instructions (optional)
        prompt.txt
        glossary.txt
        voices.txt

## Words we use

**WN** — Web novel. Usually a long running serial (Syosetu and the like), plain text.

**LN** — Light novel. A published volume, often an EPUB, sometimes vertical (tategaki) pages or pictures of pages.

**Book folder** — The one directory that holds `in`, `out`, `raw_full.txt`, and so on.

**Scene** — One file in `in\\`. The mill sends exactly one scene per request.

**Shard** — One scene file, or one English `*.en.txt`. Combine glues shards back into one file.

**Dump / raw_full.txt** — The whole Japanese book in one UTF-8 text file.

**Split** — Cutting the dump on headings, `[0017]` OCR page tags, or rule lines such as a long dash.

**_break.txt** — Files Split creates when the cut mode is rule (dash lines). They are not extra chapters. Delete them. The mill skips `*_break` names.

**Stub / p-017.txt** — Tiny files from illustration pages. The mill skips bodies under 80 characters.

**Mill** — The loop that calls LM Studio. No memory of the previous scene.

**Lock** — prompt.txt + glossary.txt + voices.txt. Names, speech marks, tone. They eat context tokens.

**Context** — How many tokens the loaded model can see. Set it in LM Studio when you load the GGUF and in the Mill Context box. The box does not reload the model. 4096 + a lock file = HTTP 400.

**Pause** — Seconds to wait after each scene so the GPU can catch up. Default is **10**.

**LMS / LM Studio** — The local app that serves `/v1/chat/completions`. Novel Mill does not start it.

**DRM / ADEPT** — Adobe encryption on a store EPUB. Convert in Calibre, then Extract the new EPUB.

**Combine** — OCR: merge ocr text into raw_full.txt. Mill: merge out\\*.en.txt into english_full.txt.

## Mill settings that matter

- API base: `http://127.0.0.1:1234/v1`
- Context: match the engine load (8192 on a 3070-class card)
- Timeout: use 900 if 8-minute chapters die
- Pause: default 10
- Overwrite off means skip files that already have an .en.txt

A typical LN volume of about 30 real chapters is about 3 to 5 hours on an RTX 3070 with Gemma 12B Q4, if you skip stubs and _break files.

## Encoding

Everything on disk must be UTF-8. Notepad Unicode is UTF-16 and will look like garbage after a split.

## What this project is not

- Not Novel Downloader
- Not Translation Aggregator
- Not an in-app reader, TTS, or cloud queue
- Not a DRM remover

## Files

- wn-local-mill.py + .bat — tabbed host
- wn-epub-extract.py — EPUB tab
- wn-ocr.py — OCR tab
- wn-raw-split.py — Split tab
- wn-scene-mill.py — Mill tab
- wn_series.py — shared folder names
- wn-raw-split.rules.json — extra Split regexes

## Licence

See LICENSE.
