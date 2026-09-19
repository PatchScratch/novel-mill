# v1.0.0 — 2026-09-19

First production release. Private repo: https://github.com/PatchScratch/wn-local-mill

Tip of `main` at publish: create the GitHub Release from this file.

## Ship list

- `wn-raw-split.py` / `wn-raw-split.bat` / `wn-raw-split.rules.json`
- `wn-scene-mill.py` / `wn-scene-mill.bat`
- `README.md`, `CHANGELOG.md`, `LICENSE` (MIT), `VERSION` (`1.0.0`)

## What it does

1. Split one novel dump into scene files (Auto / Generic / built-in families / user JSON rules).
2. Queue those files against LM Studio `/v1/chat/completions`. One scene per request. No history. No RAG.

## Runtime lock

- Context 4096
- Temperature 0.1
- Thinking off
- Uninstall RAG, remove mmproj
- Proven on RTX 3070 8 GB at 5–6 tok/s clean

## GitHub Release click path

Repo → **Releases** → **Draft a new release** → tag `v1.0.0` on `main` → title `v1.0.0` → paste this file → **Publish release**.
