# Novel Mill

A small Windows (and Linux) desktop app that turns a Japanese **web novel** or **light novel** into English scene files using a model you run yourself in LM Studio.

The GitHub folder is still called `wn-local-mill`. That is only the old project name. The window title is **Novel Mill**. Leave the `.py` file names alone so an existing install folder keeps working.

There is no cloud account and no second AI server in this app. The mill talks only to LM Studio on `http://127.0.0.1:1234`.

## What you need

- Python 3 on the PATH (`py -3` on Windows)
- LM Studio, model loaded, Developer server on port 1234
- For scanned pages: Tesseract-OCR with `jpn` and `jpn_vert` traineddata
- For store EPUBs: Calibre. Convert EPUB to EPUB (or TXT) so Adobe DRM is gone before you Extract

## How to run

1. Close Novel Mill if it is open.
2. Copy the files from this repo over your existing Novel Mill folder (same names).
3. Double-click `wn-local-mill.bat`.
4. In LM Studio, load the model with **context 8192** (4096 is too small once lock files are included).

Standalone bats still open one tab as its own window. Day to day, use the tabbed host.

## The five tabs

| Tab | What it does |
| --- | --- |
| **EPUB** | Opens a DRM-free EPUB, writes chapter text into `in/` and pictures into `images/`. Refuses Adobe AES / ADEPT files. |
| **OCR** | Runs Tesseract on a folder of page pictures. Writes `ocr/*.ocr.txt`. **Combine** stitches those into `raw_full.txt`. |
| **Split** | Cuts one big Japanese dump (`raw_full.txt`) into many small files in `in/`. |
| **Mill** | Sends each `in/*.txt` to LM Studio, one HTTP request per file. Writes `out/*.en.txt`. |
| **Settings** | The shared **book folder**. Apply to tabs so every tab points at the same tree. |

Usual path: EPUB (or OCR then Combine) then Split then Mill.

## Book folder layout

One folder per WN series or per LN volume:

    my-book/
      raw_full.txt
      in/
      out/
      images/
      ocr/
      lock/
        prompt.txt
        glossary.txt
        voices.txt

Default folder fields in the app are empty on purpose. Point Settings at your book folder. No sample novel path is shipped in the source.

## Words we use

**WN** — Web novel.

**LN** — Light novel.

**Book folder** — The one directory that holds `in`, `out`, `raw_full.txt`.

**Scene** — One file in `in/`. One HTTP request per file.

**Shard** — One scene file or one `*.en.txt`.

**Dump / raw_full.txt** — The whole Japanese book as one UTF-8 file.

**Split** — Cutting the dump on headings or page tags.

**_break.txt** — Rule-mode leftovers. Not extra chapters. Delete them.

**Stub** — Tiny illustration pages. The mill skips bodies under 80 characters.

**Mill** — The LM Studio loop. No memory of the previous scene.

**Lock** — prompt.txt + glossary.txt + voices.txt.

**Context** — Token window of the loaded model. Set it in LM Studio and in the Mill Context box.

**Pause** — Seconds between scenes. Default 10.

**DRM / ADEPT** — Adobe encryption. Convert in Calibre first.

**Combine** — OCR texts to raw_full.txt, or English shards to english_full.txt.

## Encoding

Everything on disk must be UTF-8.

## What this project is not

- Not Novel Downloader
- Not Translation Aggregator
- Not an in-app reader, TTS, or cloud queue
- Not a DRM remover

## Licence

See LICENSE.
