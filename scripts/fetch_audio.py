# /Users/dag/projects/karaoke/scripts/fetch_audio.py
from __future__ import annotations

import sys
from pathlib import Path

import yt_dlp


DEFAULT_URL = "https://www.youtube.com/watch?v=1gfdp6V1Epc"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "audio"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def download_audio_mp3(url: str, target_path: Path) -> Path:
    """Download best audio and save as MP3 to target_path (overwrites)."""
    # Use yt-dlp to fetch bestaudio and convert to mp3 via ffmpeg
    # We set outtmpl to the target base name; postprocessor will output mp3
    outtmpl = str(target_path.with_suffix(".%(ext)s"))
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": outtmpl,
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "overwrites": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    final_mp3 = target_path.with_suffix(".mp3")
    if not final_mp3.exists():
        raise FileNotFoundError(f"Expected MP3 not found at {final_mp3}")
    return final_mp3


def resolve_url() -> str:
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        return sys.argv[1].strip()
    entered = input("YouTube URL (empty to use default): ").strip()
    return entered if entered else DEFAULT_URL


def main() -> None:
    url = resolve_url()
    target = OUTPUT_DIR / "song"
    mp3_path = download_audio_mp3(url, target)
    print(f"Saved MP3: {mp3_path}")


if __name__ == "__main__":
    main()


