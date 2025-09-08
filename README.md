# Karaoke Creator for YouTube Songs

Extract audio and Thai auto captions from a YouTube video into sentence/word timelines and an MP3 audio track.

## Quick Start (Conda)

1) Clone and create environment
```bash
git clone https://github.com/dage/karaoke karaoke
cd karaoke
conda create -y -n karaoke-yt -c conda-forge python=3.11 ffmpeg
conda activate karaoke-yt
pip install -r requirements.txt
```

2) Configure (optional)
- Copy `.env_template` to `.env` and set as needed:
  - LLM test: `OPENAI_API_KEY`, optional `OPENAI_API_ENDPOINT`, `OPENAI_DEFAULT_MODEL`
  - S3 upload: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_REGION`, `S3_BUCKET_NAME`

3) Run
```bash
python run.py [optional-YouTube-URL]
```
- Downloads audio as `song.mp3`
- Fetches Thai auto captions and writes:
  - `youtube_autosubs.sentences.txt`  (start_seconds<TAB>sentence)
  - `youtube_autosubs.words.txt`      (start_seconds<TAB>word)
- Writes `manifest.json` summarizing outputs

Outputs are written to `output/`.

## Notes
- Thai only. The pipeline selects Thai auto captions from YouTube.
- If no URL arg is provided, a sample Thai video is used.

## Tools
- LLM ping test: `python tools/ping_openai.py`
- Upload to S3: `python tools/upload_to_s3.py`

## License
MIT — see LICENSE
