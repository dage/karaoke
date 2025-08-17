# /Users/dag/projects/karaoke/scripts/convert_srv3_to_word_srt.py
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def ms_to_srt_timestamp(ms: int) -> str:
    total_seconds = ms // 1000
    milliseconds = ms % 1000
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def write_srt(cues: list[tuple[int, int, str]], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as f:
        for idx, (start_ms, end_ms, text) in enumerate(cues, start=1):
            if end_ms <= start_ms:
                continue
            f.write(f"{idx}\n")
            f.write(f"{ms_to_srt_timestamp(start_ms)} --> {ms_to_srt_timestamp(end_ms)}\n\n")
            f.write(f"{text}\n\n")


def parse_srv3_to_word_cues(xml_path: Path) -> list[tuple[int, int, str]]:
    tree = ET.parse(xml_path)
    root = tree.getroot()

    cues: list[tuple[int, int, str]] = []

    # Iterate through paragraph <p> nodes; each contains optional duration and <s> word fragments
    for p in root.findall(".//p"):
        t_attr = p.get("t")
        d_attr = p.get("d")

        if t_attr is None:
            # Without a start time, we cannot align; skip
            continue

        para_start = int(t_attr)
        para_dur = int(d_attr) if d_attr is not None else None

        word_nodes = list(p.findall("s"))

        # Handle paragraphs that are plain text (e.g., [เพลง]) without <s> children
        if not word_nodes:
            text = (p.text or "").strip()
            if not text:
                continue
            if para_dur is None:
                # If there's no duration, we cannot construct a cue reliably; skip
                continue
            cues.append((para_start, para_start + para_dur, text))
            continue

        # Collect (offset, text) pairs; missing t implies 0 offset
        offsets: list[int] = []
        texts: list[str] = []
        for s in word_nodes:
            word_text = (s.text or "").strip()
            if not word_text:
                continue
            offset_attr = s.get("t")
            offset = int(offset_attr) if offset_attr is not None else 0
            offsets.append(offset)
            texts.append(word_text)

        if not texts:
            continue

        # Build per-word cues by using next word start as end; last word ends at paragraph end
        for i, word_text in enumerate(texts):
            word_start_ms = para_start + offsets[i]
            if i + 1 < len(offsets):
                word_end_ms = para_start + offsets[i + 1]
            else:
                # Fallback to paragraph end if available; otherwise give minimal 250ms span
                if para_dur is not None:
                    word_end_ms = para_start + para_dur
                else:
                    word_end_ms = word_start_ms + 250

            # Skip overly long music tags as words; keep them as-is if present as solo paragraphs
            if word_text == "[เพลง]":
                # Treat as short cue
                word_end_ms = max(word_end_ms, word_start_ms + 500)

            cues.append((word_start_ms, word_end_ms, word_text))

    # Ensure cues are sorted chronologically
    cues.sort(key=lambda c: (c[0], c[1]))
    return cues


def main() -> None:
    if len(sys.argv) not in (1, 3):
        print("Usage: convert_srv3_to_word_srt.py [input_srv3 output_srt]")
        sys.exit(1)

    cwd = Path.cwd()
    default_in = cwd / "youtube_autosubs.th.srv3"
    default_out = cwd / "youtube_autosubs.srt"

    if len(sys.argv) == 3:
        in_path = Path(sys.argv[1])
        out_path = Path(sys.argv[2])
    else:
        in_path = default_in
        out_path = default_out

    if not in_path.exists():
        print(f"Input not found: {in_path}")
        sys.exit(2)

    cues = parse_srv3_to_word_cues(in_path)
    write_srt(cues, out_path)
    print(f"Wrote {len(cues)} cues to {out_path}")


if __name__ == "__main__":
    main()


