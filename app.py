import os
import json
import subprocess
import tempfile
import shutil
import urllib.request
import urllib.parse
from pathlib import Path

import whisper
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

UPLOAD_DIR = Path("uploads")
OUTPUT_DIR = Path("outputs")
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

_model_cache = {}


def get_model(model_name: str):
    if model_name not in _model_cache:
        _model_cache[model_name] = whisper.load_model(model_name)
    return _model_cache[model_name]


@app.get("/", response_class=HTMLResponse)
async def index():
    return open("index.html").read()


@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form("base"),
    language: str = Form("auto"),
):
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=UPLOAD_DIR) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        m = get_model(model)
        opts = {"word_timestamps": True}
        if language != "auto":
            opts["language"] = language

        result = m.transcribe(tmp_path, **opts)

        segments = []
        for seg in result["segments"]:
            words = []
            for w in seg.get("words", []):
                words.append({
                    "word": w["word"],
                    "start": round(w["start"], 3),
                    "end": round(w["end"], 3),
                })
            segments.append({
                "id": seg["id"],
                "start": round(seg["start"], 3),
                "end": round(seg["end"], 3),
                "text": seg["text"].strip(),
                "words": words,
            })

        return {"segments": segments, "language": result.get("language", "unknown")}
    finally:
        os.unlink(tmp_path)


@app.post("/export/srt")
async def export_srt(data: dict):
    segments = data.get("segments", [])
    words_per_chunk = int(data.get("words_per_chunk", 3))

    lines = []
    idx = 1
    for seg in segments:
        words = seg.get("words", [])
        if not words:
            start = seg["start"]
            end = seg["end"]
            text = seg["text"]
            lines.append(f"{idx}\n{_srt_time(start)} --> {_srt_time(end)}\n{text}\n")
            idx += 1
            continue

        chunks = [words[i:i+words_per_chunk] for i in range(0, len(words), words_per_chunk)]
        for chunk in chunks:
            start = chunk[0]["start"]
            end = chunk[-1]["end"]
            text = "".join(w["word"] for w in chunk).strip()
            lines.append(f"{idx}\n{_srt_time(start)} --> {_srt_time(end)}\n{text}\n")
            idx += 1

    srt_path = OUTPUT_DIR / "subtitles.srt"
    srt_path.write_text("\n".join(lines))
    return FileResponse(srt_path, filename="subtitles.srt", media_type="text/plain")


@app.post("/export/ass")
async def export_ass(data: dict):
    segments = data.get("segments", [])
    style = data.get("style", {})
    words_per_chunk = int(data.get("words_per_chunk", 3))

    font = style.get("font", "Arial Black")
    fontsize = style.get("fontsize", 22)
    primary = style.get("primary_color", "&H00FFFFFF")
    outline_color = style.get("outline_color", "&H00000000")
    highlight_color = style.get("highlight_color", "&H0000F0FF")
    bold = style.get("bold", True)
    outline = style.get("outline", 3)
    shadow = style.get("shadow", 0)
    margin_v = style.get("margin_v", 80)
    alignment = style.get("alignment", 2)  # bottom center

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{fontsize},{primary},&H00FFFFFF,{outline_color},&H00000000,{int(bold)},0,0,0,100,100,0,0,1,{outline},{shadow},{alignment},10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events = []
    for seg in segments:
        words = seg.get("words", [])
        if not words:
            start = _ass_time(seg["start"])
            end = _ass_time(seg["end"])
            events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{seg['text']}")
            continue

        chunks = [words[i:i+words_per_chunk] for i in range(0, len(words), words_per_chunk)]
        for chunk in chunks:
            chunk_start = chunk[0]["start"]
            chunk_end = chunk[-1]["end"]
            line_parts = []
            for w in chunk:
                word_dur = int((w["end"] - w["start"]) * 100)
                line_parts.append(f"{{\\k{word_dur}\\1c{highlight_color}}}{w['word'].strip()}{{\\1c{primary}}}")
            text = " ".join(line_parts)
            events.append(f"Dialogue: 0,{_ass_time(chunk_start)},{_ass_time(chunk_end)},Default,,0,0,0,,{text}")

    ass_path = OUTPUT_DIR / "subtitles.ass"
    ass_path.write_text(header + "\n".join(events))
    return FileResponse(ass_path, filename="subtitles.ass", media_type="text/plain")


@app.post("/export/video")
async def export_video(
    file: UploadFile = File(...),
    segments_json: str = Form(...),
    style_json: str = Form(...),
    words_per_chunk: int = Form(3),
):
    segments = json.loads(segments_json)
    style = json.loads(style_json)

    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=UPLOAD_DIR) as tmp:
        shutil.copyfileobj(file.file, tmp)
        video_path = tmp.name

    ass_path = OUTPUT_DIR / "burn_subs.ass"
    out_path = OUTPUT_DIR / "output_with_subs.mp4"

    ass_data = {"segments": segments, "style": style, "words_per_chunk": words_per_chunk}

    font = style.get("font", "Arial Black")
    fontsize = style.get("fontsize", 22)
    primary = style.get("primary_color", "&H00FFFFFF")
    outline_color = style.get("outline_color", "&H00000000")
    highlight_color = style.get("highlight_color", "&H0000F0FF")
    bold = int(style.get("bold", True))
    outline = style.get("outline", 3)
    shadow = style.get("shadow", 0)
    margin_v = style.get("margin_v", 80)

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{fontsize},{primary},&H00FFFFFF,{outline_color},&H00000000,{bold},0,0,0,100,100,0,0,1,{outline},{shadow},2,10,10,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for seg in segments:
        words = seg.get("words", [])
        if not words:
            events.append(f"Dialogue: 0,{_ass_time(seg['start'])},{_ass_time(seg['end'])},Default,,0,0,0,,{seg['text']}")
            continue
        chunks = [words[i:i+words_per_chunk] for i in range(0, len(words), words_per_chunk)]
        for chunk in chunks:
            chunk_start = chunk[0]["start"]
            chunk_end = chunk[-1]["end"]
            line_parts = []
            for w in chunk:
                word_dur = int((w["end"] - w["start"]) * 100)
                line_parts.append(f"{{\\k{word_dur}\\1c{highlight_color}}}{w['word'].strip()}{{\\1c{primary}}}")
            text = " ".join(line_parts)
            events.append(f"Dialogue: 0,{_ass_time(chunk_start)},{_ass_time(chunk_end)},Default,,0,0,0,,{text}")

    ass_path.write_text(header + "\n".join(events))

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"ass={ass_path}",
        "-c:a", "copy",
        str(out_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(video_path)

    if result.returncode != 0:
        raise HTTPException(500, f"ffmpeg error: {result.stderr[-500:]}")

    return FileResponse(out_path, filename="output_with_subs.mp4", media_type="video/mp4")


@app.get("/search_gifs")
async def search_gifs(q: str, api_key: str = "", limit: int = 16):
    key = api_key.strip() or "dc6zaTOxFJmzC"
    params = urllib.parse.urlencode({"api_key": key, "q": q, "limit": limit, "rating": "g"})
    try:
        with urllib.request.urlopen(f"https://api.giphy.com/v1/gifs/search?{params}", timeout=8) as r:
            data = json.loads(r.read())
    except Exception as e:
        raise HTTPException(502, f"Giphy error: {e}")
    results = []
    for g in data.get("data", []):
        images = g["images"]
        results.append({
            "id": g["id"],
            "preview": images["fixed_height_small"]["url"],
            "mp4": images.get("original_mp4", {}).get("mp4") or images["original"].get("mp4", ""),
            "title": g.get("title", ""),
        })
    return {"results": results}


@app.post("/crop")
async def crop_video(
    file: UploadFile = File(...),
    aspect: str = Form("9:16"),
    offset_x: float = Form(0.5),
    offset_y: float = Form(0.5),
):
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=UPLOAD_DIR) as tmp:
        shutil.copyfileobj(file.file, tmp)
        video_path = tmp.name

    probe = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_streams", video_path],
        capture_output=True, text=True,
    )
    info = json.loads(probe.stdout)
    vstream = next(s for s in info["streams"] if s["codec_type"] == "video")
    src_w, src_h = int(vstream["width"]), int(vstream["height"])

    if aspect == "original":
        os.unlink(video_path)
        raise HTTPException(400, "Already original aspect")

    a_num, a_den = map(int, aspect.split(":"))
    target_ratio = a_num / a_den
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        crop_h = src_h
        crop_w = int(src_h * target_ratio) & ~1
        crop_x = int((src_w - crop_w) * max(0.0, min(1.0, offset_x)))
        crop_y = 0
    else:
        crop_w = src_w
        crop_h = int(src_w / target_ratio) & ~1
        crop_x = 0
        crop_y = int((src_h - crop_h) * max(0.0, min(1.0, offset_y)))

    TARGETS = {"9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350), "16:9": (1920, 1080)}
    out_w, out_h = TARGETS.get(aspect, (crop_w, crop_h))

    out_path = OUTPUT_DIR / f"cropped_{aspect.replace(':','x')}.mp4"
    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale={out_w}:{out_h}",
        "-c:v", "libx264", "-crf", "18", "-preset", "fast",
        "-c:a", "aac", str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(video_path)

    if result.returncode != 0:
        raise HTTPException(500, f"ffmpeg error: {result.stderr[-500:]}")

    return FileResponse(out_path, filename=out_path.name, media_type="video/mp4")


@app.post("/analyze_highlights")
async def analyze_highlights(data: dict):
    segments = data.get("segments", [])
    target_pct = float(data.get("target_pct", 0.5))
    api_key = data.get("api_key", "").strip()

    if not segments:
        raise HTTPException(400, "No segments provided")

    if api_key:
        try:
            return _analyze_with_claude(segments, target_pct, api_key)
        except Exception as e:
            # Fallback to local on any Claude error
            result = _local_scoring(segments, target_pct)
            result["warning"] = f"Claude failed ({e}), used local scoring"
            return result
    return _local_scoring(segments, target_pct)


_ENERGY_WORDS = {
    "wow","amazing","incredible","crazy","insane","unbelievable","shocking","never",
    "always","everyone","nobody","secret","reveal","key","important","critical",
    "best","worst","perfect","terrible","huge","massive","biggest","smallest",
    "fantastisk","otrolig","galen","otroligt","aldrig","alltid","alla","ingen",
    "viktig","hemlig","avslöja","bäst","sämst","perfekt","enorm","störst",
}

_IMPORTANCE_STARTERS = [
    "the key","most important","remember","here's why","the reason","this is why",
    "you need to","the secret","what you","the problem","the solution","the truth",
    "det viktigaste","kom ihåg","anledningen","hemligheten","problemet","lösningen",
    "sanningen","du måste","vad du",
]


def _score_segment(seg: dict) -> float:
    text = seg.get("text", "").lower()
    dur = seg.get("end", 0) - seg.get("start", 0)
    score = 1.0

    words_in_seg = text.split()
    score += sum(2.0 for w in words_in_seg if w.strip(".,!?") in _ENERGY_WORDS)
    score += text.count("!") * 1.5
    score += text.count("?") * 1.0

    if dur > 0:
        wps = len(seg.get("words") or words_in_seg) / dur
        if wps > 2.5:
            score += 1.0

    if dur < 1.0:
        score *= 0.5

    for starter in _IMPORTANCE_STARTERS:
        if text.startswith(starter):
            score += 2.0
            break

    return score


def _local_scoring(segments: list, target_pct: float) -> dict:
    raw_scores = [_score_segment(s) for s in segments]
    max_s = max(raw_scores) if raw_scores else 1.0
    scores = [round(s / max_s, 3) for s in raw_scores]

    total_dur = sum(s.get("end", 0) - s.get("start", 0) for s in segments)
    target_dur = total_dur * target_pct

    # Sort by score desc, greedily fill target duration
    ranked = sorted(range(len(segments)), key=lambda i: -scores[i])
    selected_set = set()
    selected_dur = 0.0
    for i in ranked:
        seg_dur = segments[i].get("end", 0) - segments[i].get("start", 0)
        if selected_dur + seg_dur <= target_dur * 1.15 or not selected_set:
            selected_set.add(i)
            selected_dur += seg_dur
        if selected_dur >= target_dur:
            break

    return {"scores": scores, "selected": sorted(selected_set)}


def _analyze_with_claude(segments: list, target_pct: float, api_key: str) -> dict:
    import anthropic

    total_dur = sum(s.get("end", 0) - s.get("start", 0) for s in segments)
    lines = "\n".join(
        f"[{i}] {s['start']:.1f}s-{s['end']:.1f}s: {s['text'].strip()}"
        for i, s in enumerate(segments)
    )

    client = anthropic.Anthropic(api_key=api_key)
    msg = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": (
                f"Analyze this video transcript and select the most important/engaging segments "
                f"for a highlight reel.\n\nTranscript:\n{lines}\n\n"
                f"Select segments totaling ~{int(target_pct*100)}% of the full {total_dur:.0f}s duration "
                f"(target ~{total_dur*target_pct:.0f}s).\n"
                f"Prioritize: key insights, surprising moments, emotional peaks, memorable quotes.\n"
                f"Avoid: filler, repetition, greetings, transitions.\n\n"
                f"Reply ONLY with valid JSON: "
                f'{{ "selected": [list of segment indices], "scores": [0.0-1.0 score per segment in order] }}'
            ),
        }],
    )

    import re
    match = re.search(r"\{.*\}", msg.content[0].text, re.DOTALL)
    if not match:
        raise ValueError("No JSON in response")
    parsed = json.loads(match.group())
    scores = [round(float(x), 3) for x in parsed.get("scores", [0.5] * len(segments))]
    selected = sorted(int(x) for x in parsed.get("selected", []))
    return {"scores": scores, "selected": selected}


@app.post("/export/highlights")
async def export_highlights(
    file: UploadFile = File(...),
    ranges_json: str = Form(...),
    padding: float = Form(0.15),
):
    ranges = json.loads(ranges_json)
    if not ranges:
        raise HTTPException(400, "No ranges provided")

    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, dir=UPLOAD_DIR) as tmp:
        shutil.copyfileobj(file.file, tmp)
        video_path = tmp.name

    out_path = OUTPUT_DIR / "highlights.mp4"

    # Pad each range and clamp to 0
    padded = [[max(0.0, s - padding), e + padding] for s, e in ranges]

    if len(padded) == 1:
        s, e = padded[0]
        cmd = [
            "ffmpeg", "-y", "-ss", str(s), "-to", str(e), "-i", video_path,
            "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-c:a", "aac",
            str(out_path),
        ]
    else:
        v_parts, a_parts = [], []
        for i, (s, e) in enumerate(padded):
            v_parts.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]")
            a_parts.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}]")
        n = len(padded)
        concat_in = "".join(f"[v{i}][a{i}]" for i in range(n))
        filter_complex = (
            ";".join(v_parts + a_parts)
            + f";{concat_in}concat=n={n}:v=1:a=1[vout][aout]"
        )
        cmd = [
            "ffmpeg", "-y", "-i", video_path,
            "-filter_complex", filter_complex,
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-crf", "18", "-preset", "fast", "-c:a", "aac",
            str(out_path),
        ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    os.unlink(video_path)

    if result.returncode != 0:
        raise HTTPException(500, f"ffmpeg error: {result.stderr[-500:]}")

    return FileResponse(out_path, filename="highlights.mp4", media_type="video/mp4")


def _srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _ass_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h}:{m:02}:{s:05.2f}"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
