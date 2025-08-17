# /Users/dag/projects/karaoke/scripts/fetch_srv3_words.py
from __future__ import annotations

import sys
from pathlib import Path
import xml.etree.ElementTree as ET
from typing import List, Tuple
import tempfile
import os

import yt_dlp


DEFAULT_URL = "https://www.youtube.com/watch?v=1gfdp6V1Epc"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT_BASENAME = "youtube_autosubs"


def download_srv3_subtitles(url: str, out_base: str) -> Path:
    """Download Thai auto-generated subtitles in srv3 format, return file path.

    The file will be saved as f"{out_base}.th.srv3" in the current working directory.
    """
    ydl_opts = {
        "writeautomaticsub": True,
        "writesubtitles": True,
        "skip_download": True,
        "subtitleslangs": ["th"],
        "subtitlesformat": "srv3",
        "outtmpl": out_base,
        "quiet": True,
        "no_warnings": True,
    }

    srv3_path = Path(f"{out_base}.th.srv3")

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if not srv3_path.exists():
        raise FileNotFoundError(f"Expected subtitles not found: {srv3_path}")

    return srv3_path


def parse_srv3_words(srv3_file: Path) -> List[Tuple[int, str]]:
    """Parse srv3 and return list of (start_ms, word_text) for each <s> token."""
    tree = ET.parse(srv3_file)
    root = tree.getroot()

    result: List[Tuple[int, str]] = []
    for p in root.findall(".//p"):
        p_start_str = p.get("t")
        if p_start_str is None:
            continue
        para_start = int(p_start_str)

        for s in p.findall("s"):
            text = (s.text or "").strip()
            if not text:
                continue
            offset_str = s.get("t")
            offset = int(offset_str) if offset_str is not None else 0
            start_ms = para_start + offset
            result.append((start_ms, text))

    # Sort by time to be safe
    result.sort(key=lambda t: t[0])
    return result


def write_wordlist(words: List[Tuple[int, str]], output_path: Path) -> None:
    """Write as plain text file: one line per word: '<start_seconds>\t<word>'"""
    with output_path.open("w", encoding="utf-8") as f:
        for start_ms, word in words:
            seconds = start_ms / 1000.0
            f.write(f"{seconds:.3f}\t{word}\n")


def main() -> None:
    # Resolve URL
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        url = sys.argv[1].strip()
    else:
        entered = input("YouTube URL (empty to use default): ").strip()
        url = entered if entered else DEFAULT_URL

    # Use a temp directory for intermediate srv3 file
    with tempfile.TemporaryDirectory() as tmpdir:
        out_base = os.path.join(tmpdir, DEFAULT_OUT_BASENAME)
        srv3_path = download_srv3_subtitles(url, out_base)

        words = parse_srv3_words(srv3_path)

    # Write outputs to project root
    out_txt = PROJECT_ROOT / "youtube_autosubs.words.txt"
    write_wordlist(words, out_txt)

    print(f"Wrote {len(words)} words to {out_txt}")


if __name__ == "__main__":
    main()


