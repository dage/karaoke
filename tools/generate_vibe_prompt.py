#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import textwrap
from pathlib import Path
from typing import List, Tuple
import contextlib

from dotenv import load_dotenv, find_dotenv

# Make project root importable so we can import sibling modules under tools/ and scripts/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Local imports
from tools.upload_to_s3 import upload_output_and_get_manifest


ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "output"
WORDS_PATH = OUTPUT_DIR / "youtube_autosubs.words.txt"
SENTENCES_PATH = OUTPUT_DIR / "youtube_autosubs.sentences.txt"


def _safe_read_lines(path: Path, max_lines: int = 2000) -> List[str]:
    try:
        with path.open("r", encoding="utf-8") as f:
            lines: List[str] = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    break
                lines.append(line.rstrip("\n"))
            return lines
    except FileNotFoundError:
        return []


def _parse_tsv_pairs(lines: List[str]) -> List[Tuple[float, str]]:
    out: List[Tuple[float, str]] = []
    for ln in lines:
        if not ln.strip():
            continue
        # Expect: start_seconds<TAB>text
        if "\t" not in ln:
            continue
        ts_str, text = ln.split("\t", 1)
        try:
            ts = float(ts_str.strip())
        except ValueError:
            continue
        out.append((ts, text))
    return out


def _duration_from_sentences(pairs: List[Tuple[float, str]]) -> float:
    if not pairs:
        return 0.0
    # Use last timestamp + a small tail buffer
    last_ts = max(p[0] for p in pairs)
    return last_ts + 5.0


def _mmss(seconds: float) -> str:
    if seconds <= 0:
        return "0:00"
    m = int(seconds // 60)
    s = int(round(seconds - m * 60))
    return f"{m}:{s:02d}"


def _llm_song_brief(sample_sentences: List[Tuple[float, str]], duration_s: float) -> str:
    """Query the local LLM helper to synthesize a song-specific style brief.

    Falls back to a generic brief if env/API unavailable.
    """
    # Import lazily to allow running even when requests/openai env is absent
    try:
        from scripts import query_llm  # type: ignore
    except Exception:
        return _fallback_brief(sample_sentences, duration_s)

    # Monkey-patch token budget for a useful response without editing the helper.
    try:
        query_llm.DEFAULT_MAX_TOKENS = 600  # type: ignore
        query_llm.DEFAULT_TEMPERATURE = 0.7  # type: ignore
    except Exception:
        pass

    # Prepare a compact excerpt of the first ~12 lines to prime the model
    excerpt_lines = []
    for ts, txt in sample_sentences[:12]:
        excerpt_lines.append(f"{_mmss(ts)}\t{txt}")
    excerpt = "\n".join(excerpt_lines)

    # Suggest a few cue anchors across the track
    anchors: List[str] = []
    if duration_s > 0:
        for frac in (0.25, 0.50, 0.75):
            anchors.append(_mmss(duration_s * frac))
    anchors_text = ", ".join(anchors) if anchors else "0:45, 1:30, 2:15"

    prompt = textwrap.dedent(
        f"""
        You are a senior music visual designer. Given Thai lyrics excerpts with timestamps,
        produce a SONG-SPECIFIC STYLE BRIEF for a web karaoke player. Do NOT translate lyrics;
        infer mood, themes, and arc from the Thai as-is. Keep it concise but evocative.

        Provide:
        - Title: short title for the visual concept
        - Mood & Themes: 2-3 lines
        - Color Palette: 4-6 colors with roles (bg, accents)
        - Typography: primary + accent style guidance
        - FX Motifs: particles, glows, shaders, transitions
        - Timeline Cues: 6–10 cue points with mm:ss and effect notes
          - Use anchor times like {anchors_text} and add others you deem right
          - Include at least one mid-song shift (e.g., happy → melancholic)

        Constraints:
        - Output in plain text, compact bullets.
        - Do not ask questions or add closing remarks.
        - Do not use code fences or markdown tables.
        - Keep technical details implementable in a web canvas/WebGL/CSS environment.
        - Avoid copyrighted brand names.

        Thai lyric excerpt (time\ttext):
        {excerpt}
        Total approximate duration: {_mmss(duration_s)}
        """
    ).strip()

    try:
        return query_llm.query(prompt)
    except Exception:
        return _fallback_brief(sample_sentences, duration_s)


def _fallback_brief(sample_sentences: List[Tuple[float, str]], duration_s: float) -> str:
    # Minimal, generic brief if LLM is unavailable
    cues: List[str] = []
    anchors = [0.25, 0.5, 0.75]
    for frac in anchors:
        cues.append(f"- {_mmss(duration_s*frac)}: subtle color shift and particle density change")
    return textwrap.dedent(
        f"""
        Title: Neon Silk Pulse
        Mood & Themes: Dreamy, emotive, intimate performance with gradual introspection.
        Color Palette: Deep indigo (bg), electric magenta (primary), cyan glow (accent), warm amber (highlight).
        Typography: Rounded sans for lyrics; high-contrast italic for emphasized words.
        FX Motifs: Soft bloom, chromatic aberration on peaks, floating bokeh particles synced to beat.
        Timeline Cues:\n""".strip()
        + "\n" + "\n".join(cues)
    )


def build_and_print_prompt() -> int:
    # Ensure env is loaded for S3 + LLM
    load_dotenv(find_dotenv())

    # 1) Upload output/ to S3 (and rewrite manifest URLs)
    try:
        # Silence all output from the upload helper so only the prompt is printed
        with open(os.devnull, "w") as _null:
            with contextlib.redirect_stdout(_null), contextlib.redirect_stderr(_null):
                manifest_url, manifest = upload_output_and_get_manifest()
    except Exception as e:
        sys.stderr.write(f"Error uploading output to S3: {e}\n")
        sys.stderr.flush()
        return 1

    # 2) Gather inputs for the prompt
    words_lines = _safe_read_lines(WORDS_PATH, max_lines=5000)
    sent_lines = _safe_read_lines(SENTENCES_PATH, max_lines=5000)
    sentences = _parse_tsv_pairs(sent_lines)
    duration_s = _duration_from_sentences(sentences)
    brief = _llm_song_brief(sentences, duration_s)

    audio_url = str(manifest.get("audio_file", "")).strip()
    words_url = str(manifest.get("words", "")).strip()
    sentences_url = str(manifest.get("sentences", "")).strip()

    # 3) Compose the final vibe-coding prompt for a modern AI model
    tsv_desc = textwrap.dedent(
        """
        TSV format (UTF-8, LF, tab-separated)

        Sentences TSV: start_seconds\tfull_sentence_text
        Example: 4.220 [เพลง]

        Words TSV: start_seconds\tword_text
        Example: 18.680 หน้า
        """
    ).strip()

    features = [
        "Highlight the currently sung word, smooth crossfade to next word",
        "Show the current sentence prominently and preview the next sentence",
        "Accurate MP3 timeline with seek-on-click, play/pause, and scrub",
        "Time-synchronized visuals and transitions tied to lyric timestamps",
    ]
    # Build a consistently formatted bullet list with no odd indentation
    features_text = "\n".join([f"- {item}" for item in features])

    # Build the full prompt explicitly line-by-line to avoid indentation anomalies
    lines: list[str] = []
    lines.append("Build a visually stunning, modern web karaoke player for THAI lyrics.")
    lines.append("")
    lines.append("Core features:")
    lines.extend(features_text.splitlines())
    lines.append("")
    lines.append("Assets (public URLs from S3):")
    lines.append(f"- Audio (MP3): {audio_url}")
    lines.append(f"- Word lyrics (TSV): {words_url}")
    lines.append(f"- Sentence lyrics (TSV): {sentences_url}")
    lines.append("")
    lines.append(tsv_desc)
    lines.append("")
    lines.append("Implementation notes:")
    lines.append("- Parse TSVs client-side; each row is start_seconds (float) and text.")
    lines.append("- Use the audio element currentTime to find the active word/sentence via binary search.")
    lines.append("- Render lyrics with the active word highlighted and next sentence visible.")
    lines.append("- Animate visuals using Canvas/WebGL/CSS variables; target 60fps with requestAnimationFrame.")
    lines.append("- Ensure mobile responsiveness; large, legible Thai typography.")
    lines.append("")
    lines.append("Song-specific style brief (use this to tailor visuals):")
    lines.append(brief)
    lines.append("")
    lines.append(
        "Deliver a single-page app (HTML/CSS/JS or a small React/Vite setup). "
        "Prioritize jaw-dropping visuals with tasteful effects that enhance readability and timing precision."
    )
    final_prompt = "\n".join(lines).strip()

    # Print to stdout for easy copy/paste
    print(final_prompt)
    return 0


def main() -> int:
    # Pre-flight checks
    if not OUTPUT_DIR.exists():
        sys.stderr.write(f"Error: output directory not found at {OUTPUT_DIR}\n")
        sys.stderr.flush()
        return 2
    if not (OUTPUT_DIR / "manifest.json").exists():
        sys.stderr.write(f"Error: manifest.json not found under {OUTPUT_DIR}\n")
        sys.stderr.flush()
        return 3
    return build_and_print_prompt()


if __name__ == "__main__":
    raise SystemExit(main())
