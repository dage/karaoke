# /Users/dag/projects/karaoke/run.py
from __future__ import annotations

import subprocess
import json
import sys
from pathlib import Path


DEFAULT_URL = "https://www.youtube.com/watch?v=1gfdp6V1Epc"
PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = PROJECT_ROOT / "output"


def resolve_url() -> str:
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        return sys.argv[1].strip()
    try:
        entered = input("YouTube URL (empty to use default): ").strip()
    except EOFError:
        entered = ""
    return entered if entered else DEFAULT_URL


def run(cmd: list[str]) -> None:
    completed = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if completed.returncode != 0:
        raise SystemExit(completed.returncode)


def main() -> None:
    url = resolve_url()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("Downloading audio (MP3)...")
    run([sys.executable, str(PROJECT_ROOT / "scripts" / "fetch_audio.py"), url])

    print("Fetching srv3 and generating words...")
    run([sys.executable, str(PROJECT_ROOT / "scripts" / "fetch_srv3_words.py"), url])

    print("Generating sentences...")
    run([sys.executable, str(PROJECT_ROOT / "scripts" / "fetch_srv3_sentences.py"), url])

    print("All outputs generated.")

    # Write manifest.json in output directory
    manifest = {
        "original_url": url,
        "words": "youtube_autosubs.words.txt",
        "sentences": "youtube_autosubs.sentences.txt",
        "audio_file": "song.mp3",
    }
    manifest_path = OUTPUT_DIR / "manifest.json"
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"Wrote manifest to {manifest_path}")


if __name__ == "__main__":
    main()


