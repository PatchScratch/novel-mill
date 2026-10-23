# Novel Mill

Novel Mill translates a Japanese web novel or light novel into English, one scene at a time. You bring the book. The app extracts it, splits it, and sends each scene to a model. English comes back as `out\*.en.txt`.

It is a desktop app for Windows and Linux. The window title is Novel Mill. Script names stay `wn-*.py`.

## Requirements

Mill needs an OpenAI-compatible chat API. OCR needs Tesseract. Neither is bundled.

- **A chat model** (required to translate). Use **LM Studio** locally, or any host that speaks `/v1/chat/completions` (OpenAI, OpenRouter, xAI Grok, and others). For LM Studio: load a model with context **8192** and parallel slots **1**, server at `http://127.0.0.1:1234`. 4096 is too small once lock files are included. Cloud hosts need a real API key in the Mill Key field.
- **Tesseract OCR** (required for scanned pages). Install `jpn` and `jpn_vert` traineddata. Text EPUBs do not need it.
- **Python 3** on the PATH, if you run from source (`py -3` on Windows).
- **Calibre**, only for store EPUBs. Convert EPUB to EPUB so Adobe DRM is gone before Extract.

## Install

Grab the Windows exe or the Linux AppImage from the [releases](https://github.com/PatchScratch/novel-mill/releases) page. Tesseract (and LM Studio, if you run models locally) are still separate installs; see Requirements.

To run from source instead, unzip, then double-click `wn-local-mill.bat` (Windows) or run `python3 wn-local-mill.py` (Linux). Python 3 must be on the PATH.

Book folders are not part of the install. Theme, language, the scene tick list, and the Mill connection settings (provider, API base, model, key, temp, pause, timeout, context) are saved under `%APPDATA%\NovelMill` (Windows) or `~/.config/novel_mill` (Linux).

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

Provider presets fill the API base (and a sample model id if Model is empty or still a preset sample):

| Provider | API base |
| --- | --- |
| LM Studio | `http://127.0.0.1:1234/v1` |
| OpenAI | `https://api.openai.com/v1` |
| OpenRouter | `https://openrouter.ai/api/v1` |
| xAI Grok | `https://api.x.ai/v1` |
| Custom | whatever you type |

- Model id must match what the host lists on `/v1/models` (Ping API)
- Context box must match the loaded model’s context window
- Pause default 10 seconds (local GPU flush or cloud spacing)
- Timeout default 1200 seconds
- Three API faults in a row stop the queue; HTTP 429 gets one cool-down retry
- Non-localhost bases reject the placeholder key `sk-xxx`

A volume of about 30 chapters is often 3–5 hours on an RTX 3070 with a 12B Q4 model, if stubs and `_break` files are skipped.

## Not this project

Not a downloader. For web novel downloads, use [novel_downloader](https://github.com/ayati/novel_downloader). Export a text dump, then open that dump here.

Not Translation Aggregator. Not a reader, TTS, or DRM remover.

## Licence

MIT. See `LICENSE`.
