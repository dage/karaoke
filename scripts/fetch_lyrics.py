#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = REPO_ROOT / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def extract_video_id(s: str) -> str:
    m = re.search(r"(?:v=|youtu\.be/|youtube\.com/watch\?v=)([A-Za-z0-9_-]{6,})", s)
    return m.group(1) if m else s.strip()


def _fetch_watch_html(video_id: str) -> Optional[str]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept-Language": "th,en-US;q=0.9,en;q=0.8",
    }
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        return r.text
    except Exception:
        return None


def _extract_innertube_keys(html: str) -> Optional[Tuple[str, str, str]]:
    key_m = re.search(r'"INNERTUBE_API_KEY"\s*:\s*"([^"]+)"', html)
    if not key_m:
        return None
    key = key_m.group(1)
    client_m = re.search(r'"INNERTUBE_CLIENT_NAME"\s*:\s*"([^"]+)"', html)
    ver_m = re.search(r'"INNERTUBE_CLIENT_VERSION"\s*:\s*"([^"]+)"', html)
    client = client_m.group(1) if client_m else "WEB"
    version = ver_m.group(1) if ver_m else "2.20240901.00.00"
    return key, client, version


def fetch_captiontracks_via_youtubei(video_id: str, hl: str = 'th', gl: str = 'TH') -> List[Dict]:
    html = _fetch_watch_html(video_id)
    if not html:
        return []
    kc = _extract_innertube_keys(html)
    if not kc:
        return []
    api_key, client_name, client_version = kc
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        "Accept-Language": f"{hl},en-US;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
    }
    body = {
        "videoId": video_id,
        "context": {
            "client": {
                "clientName": client_name,
                "clientVersion": client_version,
                "hl": hl,
                "gl": gl,
            }
        }
    }
    api_url = f"https://www.youtube.com/youtubei/v1/player?key={api_key}"
    try:
        pr = requests.post(api_url, headers=headers, json=body, timeout=30)
        pr.raise_for_status()
        data = pr.json()
    except Exception:
        return []
    return (
        data.get('captions', {})
            .get('playerCaptionsTracklistRenderer', {})
            .get('captionTracks', [])
        or []
    )


def pick_track(tracks: List[Dict], lang: str = 'th') -> Optional[Dict]:
    def score(t: Dict) -> Tuple[int, int, int]:
        code = t.get("languageCode") or t.get("vssId") or ""
        exact = 1 if code == lang else 0
        prefix = 1 if (lang and str(code).startswith(lang)) else 0
        asr = 1 if t.get("kind") == "asr" or (t.get("vssId") or "").startswith("a.") else 0
        return (exact, prefix, asr)
    if not tracks:
        return None
    return sorted(tracks, key=score, reverse=True)[0]


def download_caption(base_url: str, prefer: Tuple[str, ...] = ("json3", "srv3")) -> Tuple[str, bytes]:
    headers = {"User-Agent": "Mozilla/5.0"}
    for fmt in prefer:
        url = base_url
        if "fmt=" not in url:
            sep = "&" if "?" in url else "?"
            url = f"{url}{sep}fmt={fmt}"
        if fmt == "json3" and "xorb=" not in url:
            url += "&xorb=2&xobt=3&xovt=3"
        r = requests.get(url, headers=headers, timeout=30)
        if r.status_code != 200 or not r.content:
            continue
        body = r.content.lstrip()
        if fmt == "json3":
            if body.startswith(b")]}\'\n"):
                body = body.split(b"\n", 1)[1]
            if b"\"events\"" in body or b"events" in body:
                return fmt, r.content
        else:
            if b"<p " in body:
                return fmt, r.content
    raise RuntimeError("No usable caption data")


def parse_json3_sentences(data: bytes) -> List[Tuple[float, str]]:
    obj = json.loads(data.decode("utf-8"))
    events = obj.get("events") or []
    out: List[Tuple[float, str]] = []
    for ev in events:
        t0 = ev.get("tStartMs")
        segs = ev.get("segs") or []
        if t0 is None or not segs:
            continue
        text = "".join([(s.get("utf8") or "") for s in segs]).replace("\n", " ").strip()
        if text:
            out.append((float(t0) / 1000.0, text))
    return out


def parse_json3_words(data: bytes) -> List[Tuple[float, str]]:
    obj = json.loads(data.decode("utf-8"))
    events = obj.get("events") or []
    out: List[Tuple[float, str]] = []
    for ev in events:
        t0 = ev.get("tStartMs")
        segs = ev.get("segs") or []
        if t0 is None or not segs:
            continue
        for s in segs:
            token = (s.get("utf8") or "").strip()
            if not token or (token.startswith("[") and token.endswith("]")):
                continue
            ts = (int(t0) + int(s.get("tOffsetMs", 0))) / 1000.0
            out.append((ts, token))
    return out


def parse_srv3_sentences(data: bytes) -> List[Tuple[float, str]]:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(data)
    out: List[Tuple[float, str]] = []
    for p in root.findall(".//p"):
        t = p.get("t")
        if t is None:
            continue
        start_ms = int(t)
        text = "".join([(s.text or "").strip() for s in p.findall("s")]).strip()
        if text:
            out.append((start_ms / 1000.0, text))
    return out


def parse_srv3_words(data: bytes) -> List[Tuple[float, str]]:
    import xml.etree.ElementTree as ET
    root = ET.fromstring(data)
    out: List[Tuple[float, str]] = []
    for p in root.findall(".//p"):
        pt = p.get("t")
        if pt is None:
            continue
        base = int(pt)
        for s in p.findall("s"):
            txt = (s.text or "").strip()
            if not txt or (txt.startswith("[") and txt.endswith("]")):
                continue
            off = int(s.get("t") or 0)
            out.append(((base + off) / 1000.0, txt))
    return out


def write_pairs(pairs: List[Tuple[float, str]], path: Path) -> None:
    pairs.sort(key=lambda t: t[0])
    with path.open('w', encoding='utf-8') as f:
        for t, s in pairs:
            f.write(f"{t:.3f}\t{s}\n")


def main() -> int:
    url_or_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get('TEST_YT_URL', 'https://www.youtube.com/watch?v=1gfdp6V1Epc')
    vid = extract_video_id(url_or_id)

    # Thai-only pipeline
    tracks = fetch_captiontracks_via_youtubei(vid, hl='th', gl='TH')
    if not tracks:
        print('ERROR: No captionTracks available from youtubei.')
        return 2
    track = pick_track(tracks, lang='th')
    if not track or not track.get('baseUrl'):
        print('ERROR: Could not select a caption track.')
        return 3

    fmt, data = download_caption(track['baseUrl'], prefer=("json3", "srv3"))

    if fmt == 'json3':
        sentences = parse_json3_sentences(data)
        words = parse_json3_words(data)
    else:
        sentences = parse_srv3_sentences(data)
        words = parse_srv3_words(data)

    out_sent = OUTPUT_DIR / 'youtube_autosubs.sentences.txt'
    out_words = OUTPUT_DIR / 'youtube_autosubs.words.txt'
    write_pairs(sentences, out_sent)
    write_pairs(words, out_words)

    print(f'OK: wrote {len(sentences)} sentences and {len(words)} words')
    try:
        with out_sent.open('r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= 6:
                    break
                print(line.rstrip())
    except Exception:
        pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
