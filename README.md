# SubTok

A local web app for transcribing video/audio and generating styled subtitles — optimized for short-form content (TikTok, Reels, Shorts).

## Features

- **Transcription** via [OpenAI Whisper](https://github.com/openai/whisper) — runs locally, no API key needed
- **Subtitle export** — SRT and ASS formats with word-level timing
- **Karaoke-style word highlight** — animated word-by-word highlighting in ASS format
- **Burn subtitles into video** — powered by ffmpeg
- **Highlight detection** — pick the best segments automatically, optionally using Claude AI
- **Video cropping** — crop to 9:16, 1:1, 4:5, or 16:9 with adjustable framing
- **GIF overlay search** — search and embed GIFs via Giphy

## Requirements

- Python 3.9+
- [ffmpeg](https://ffmpeg.org/) installed and available in PATH

## Quick start

```bash
./start.sh
```

The script creates a virtual environment on first run, installs dependencies, and opens the app at `http://localhost:8000`.

## Whisper models

| Model  | Speed  | Accuracy |
|--------|--------|----------|
| tiny   | Fastest | Lower   |
| base   | Fast    | Good    |
| small  | Medium  | Better  |
| medium | Slow    | High    |
| large  | Slowest | Best    |

The model is downloaded automatically on first use.

## Optional: Claude AI for highlight detection

Add your [Anthropic API key](https://console.anthropic.com/) in the app UI to use Claude for smarter highlight selection. Falls back to local scoring if no key is provided.

## Project structure

```
app.py          — FastAPI backend
index.html      — Frontend (single-page app)
requirements.txt
start.sh        — Setup and launch script
```
