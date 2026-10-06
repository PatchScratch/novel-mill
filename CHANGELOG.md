# Changelog

## 1.8.0 — 2026-10-06

- README rewritten for a public release: translation up front, LM Studio and Tesseract called out as requirements. Future work is its own section.
- Mill can tick scenes for a partial run. Selection is saved locally, not in the book folder.
- Appearance: System / Dark / Light. Language: 日本語 / English.
- Existing `.en.txt` is Keep existing | Overwrite.

## 1.7.0 — 2026-09-22

- Display name is **Novel Mill** (WN and LN). Repo folder name unchanged.
- Mill pause default is 10 seconds.
- Mill skips `_break`, `p-00x` stubs, and bodies under 80 characters.
- Mill retries a timeout once; queue continues after Channel Error.
- EPUB tab refuses Adobe ADEPT / AES-encrypted EPUBs.
- Combine English shards → `english_full.txt`.
- README rewritten in plain English with a terminology list.

## 1.6.x

- Tabbed dark host, EPUB + OCR + Split + Mill.
- OCR vertical Japanese (`jpn_vert`), Combine to `raw_full.txt`.
- Page-number and `⸻` strip before mill POST.
