# Novel Mill

Novel Mill translates a Japanese web novel or light novel into English, one scene at a time. You bring the book. The app extracts it, splits it, and sends each scene to a model. English comes back as `out\*.en.txt`.

It is a desktop app for Windows and Linux. The window title is Novel Mill. Script names stay `wn-*.py`.

## Requirements

Mill needs a running model server. OCR needs Tesseract. Neither is bundled.

- **LM Studio** (required to translate). Load a model with context **8192** and parallel slots **1**. Turn on the local server at `http://127.0.0.1:1234`. 4096 is too small once lock files are included.
- **Tesseract OCR** (required for scanned pages). Install `jpn` and `jpn_vert` traineddata. Text EPUBs do not need it.
- **Python 3** on the PATH, if you run from source (`py -3` on Windows).
- **Calibre**, only for store EPUBs. Convert EPUB to EPUB so Adobe DRM is gone before Extract.

## Install

Grab the Windows exe or the Linux AppImage from the [releases](https://github.com/PatchScratch/novel-mill/releases) page. Tesseract and LM Studio are still separate installs; see Requirements.

To run from source instead, unzip, then double-click `wn-local-mill.bat` (Windows) or run `python3 wn-local-mill.py` (Linux). Python 3 must be on the PATH.

Book folders are not part of the install. Theme, language, the scene tick list, and the Mill connection settings (API base, model, key, temp, pause, timeout, context) are saved under `%APPDATA%\NovelMill` (Windows) or `~/.config/novel_mill` (Linux).

## Tabs

| Tab | What it does |
| --- | --- |
| **EPUB** | DRM-free EPUB to `in\` text and `images\`. Refuses Adobe AES. |
| **OCR** | Tesseract on page pictures. Combine writes `raw_full.txt`. |
| **Split** | One Japanese dump into scene files in `in\`. |
| **Mill** | One HTTP request per ticked scene. Writes `out\*.en.txt`. |
| **Settings** | Book folder, appearance (System / Dark / Light), language (日本語 / English). |

Text EPUB: Extract, Split only if a chapter is huge, then Mill. Scanned book: OCR, Combine, Split, Mill.

Tick scenes on the Mill tab for a partial run. **Missing only** resumes files that have no `.en.txt`. Keep existing skips finished scenes.

## Book folder

```
my-book\
  raw_full.txt
  in\
  out\
  images\
  ocr\
  lock\
    prompt.txt
    glossary.txt
    voices.txt
```

Lock files are optional. They set names, speech marks, and tone, and they use context tokens.

Files on disk must be UTF-8. A garbled `raw_full.txt` is a bad export, not a vertical-script problem. Rebuild it from a DRM-free EPUB or from OCR.

## Mill

- API base `http://127.0.0.1:1234/v1`
- Model id must match `/v1/models`
- Context box must match the LM Studio load
- Pause default 10 seconds
- Timeout default 1200 seconds
- Three LM Studio faults in a row stop the queue

A volume of about 30 chapters is often 3–5 hours on an RTX 3070 with a 12B Q4 model, if stubs and `_break` files are skipped.

## Future features

- Cloud models through the OpenAI chat-completions API: ChatGPT, Grok, OpenRouter, and any other host that speaks that format. This release talks only to LM Studio on `http://127.0.0.1:1234`.

## Not this project

Not a downloader. For web novel downloads, use [novel_downloader](https://github.com/ayati/novel_downloader). Export a text dump, then open that dump here.

Not Translation Aggregator. Not a reader, TTS, or DRM remover.

## Licence

MIT. See `LICENSE`.
