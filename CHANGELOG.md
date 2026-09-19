# Changelog

## 1.0.0 — 2026-09-19

First production release.

### WN Raw Split
- Auto / Generic chapter detection for JP, EN, CN, KR dumps
- 青空 大・中・小見出し, 話/章/Chapter/화, ep001, Scene001, named extras, volumes
- User-defined splitters in `wn-raw-split.rules.json`
- GUI: Scan, preview, write numbered files, strip 青空/HTML/ruby

### WN Scene Mill
- Queue `in\*.txt` against LM Studio `/v1/chat/completions`
- Fresh messages every file (no history)
- Skip or overwrite existing English
- Ping API, make lock folders, stop after current file
