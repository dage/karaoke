# /Users/dag/projects/karaoke/scripts/fetch_srv3_sentences.py
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
    """Download Thai auto-generated subtitles in srv3 format, return file path."""
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


def parse_srv3_sentences(srv3_file: Path) -> List[Tuple[int, str]]:
    """Return list of (start_ms, sentence_text) for each <p> block.

    If a <p> has <s> children, join their texts without spaces (Thai). If not, use the <p> text.
    Skip empty entries.
    """
    tree = ET.parse(srv3_file)
    root = tree.getroot()

    sentences: List[Tuple[int, str]] = []
    for p in root.findall(".//p"):
        t_attr = p.get("t")
        if t_attr is None:
            continue
        start_ms = int(t_attr)

        s_nodes = list(p.findall("s"))
        if s_nodes:
            parts: List[str] = []
            for s in s_nodes:
                txt = (s.text or "").strip()
                if txt:
                    parts.append(txt)
            text = "".join(parts).strip()
        else:
            text = (p.text or "").strip()

        if not text:
            continue

        sentences.append((start_ms, text))

    sentences.sort(key=lambda x: x[0])
    return sentences


def write_sentences_seconds(sentences: List[Tuple[int, str]], output_path: Path) -> None:
    """Write as '<start_seconds>\t<text>' with start time in seconds (3 decimals)."""
    with output_path.open("w", encoding="utf-8") as f:
        for start_ms, text in sentences:
            seconds = start_ms / 1000.0
            f.write(f"{seconds:.3f}\t{text}\n")


def main() -> None:
    # Resolve URL from argv or prompt or default
    if len(sys.argv) >= 2 and sys.argv[1].strip():
        url = sys.argv[1].strip()
    else:
        entered = input("YouTube URL (empty to use default): ").strip()
        url = entered if entered else DEFAULT_URL

    # Use a temp directory for intermediate srv3 file
    with tempfile.TemporaryDirectory() as tmpdir:
        out_base = os.path.join(tmpdir, DEFAULT_OUT_BASENAME)
        srv3_path = download_srv3_subtitles(url, out_base)

        sentences = parse_srv3_sentences(srv3_path)

    # Write outputs to project root
    out_txt = PROJECT_ROOT / "youtube_autosubs.sentences.txt"
    write_sentences_seconds(sentences, out_txt)

    print(f"Wrote {len(sentences)} sentences to {out_txt}")


if __name__ == "__main__":
    main()


