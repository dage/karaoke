# Project Guide for Agents

This repository extracts audio and Thai auto captions from YouTube into aligned sentence/word timelines and an MP3. It is intentionally minimal and script‑driven.

## Overview
- Language: Thai only (captions and selection logic target Thai).
- Captions source: youtubei player API (prefers json3, falls back to srv3).
- Outputs (under `output/`):
  - `song.mp3`
  - `youtube_autosubs.sentences.txt` (start_seconds<TAB>sentence)
  - `youtube_autosubs.words.txt` (start_seconds<TAB>word)
  - `manifest.json` (summary with file names and original URL)

## Key Scripts
- `run.py`: Orchestrates end‑to‑end flow (audio + lyrics + manifest).
- `scripts/fetch_audio.py`: Downloads best audio via `yt_dlp` and converts to MP3 using ffmpeg.
- `scripts/fetch_lyrics.py`: Fetches Thai caption tracks via youtubei and writes words/sentences.
- Tools (optional):
  - `tools/upload_to_s3.py`: Uploads `output/` files to S3 and rewrites manifest with absolute URLs.
  - `tools/ping_openai.py` + `scripts/query_llm.py`: Simple LLM connectivity test via OpenRouter.

## Environment
- Preferred setup: Conda
  - `conda create -y -n karaoke-yt -c conda-forge python=3.11 ffmpeg`
  - `conda activate karaoke-yt`
  - `pip install -r requirements.txt` (includes `yt-dlp`, `requests`, `boto3`, `python-dotenv`, `openai`)
- Secrets: Use `.env` for local development. Do not commit real secrets.
  - Template: `.env_template` (copy to `.env`).

## Constraints and Expectations
- Thai‑only pipeline. Do not add language switches or config unless requested.
- Preserve file names and relative paths for outputs and `manifest.json` keys:
  - `words`: `youtube_autosubs.words.txt`
  - `sentences`: `youtube_autosubs.sentences.txt`
  - `audio_file`: `song.mp3`
  - `original_url`: source YouTube URL
- Keep changes minimal and focused; avoid unrelated refactors.
- Avoid introducing new external services or heavy dependencies.

## Validation Steps (Manual)
1) `python run.py` (optionally pass a YouTube URL) 
2) Confirm files in `output/` and a valid `manifest.json`.
3) Optional: `python tools/upload_to_s3.py` to verify S3 creds and upload flow.

## Common Issues
- ffmpeg missing: ensure the Conda env includes `ffmpeg`.
- Captions not found: some videos lack Thai auto captions; try another URL.
- Network/API: youtubei endpoints can rate limit; retry or change IP.

## Coding Style and Practices
- Python 3.11. Keep code concise; prefer standard libs plus existing deps.
- Error handling: fail with clear messages; avoid noisy stack traces for expected network errors.
- Don’t rename or move public entry points or output filenames without explicit direction.

## Commit & Pull Request Guidelines
- Format: `type: imperative summary ≤50 chars` (no scope in parentheses).
- Commit message body is PLAIN TEXT (not Markdown). Start at line 3 (line 2 blank) and write each bullet as a literal line beginning with `- ` at column 1. Example: `- add X`
- Types: feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert.
- Example: `fix: prevent single model failures from crashing parallel execution`
- PRs: concise description, linked issue, UI screenshots when relevant, and validation steps (commands + expected outputs).
- Keep messages short and focused; for small changes, a single‑line commit without a body is fine.

## When in Doubt
- Ask before broad refactors.
- Preserve Thai‑only behavior and output compatibility.
- Keep README and .env template consistent with the current flow.

