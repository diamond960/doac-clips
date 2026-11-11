#!/usr/bin/env python3
"""Cut vertical, captioned clips for every job in jobs/ that has no output yet.

A job file jobs/<video_id>.json looks like:
{
  "video_id": "6VTSAs4Rsck",
  "clips": [
    {"slug": "c01", "start": 123.4, "end": 171.0, "hook": "Why the next crash is coming"}
  ]
}

For each job: download the episode once (720p), cut each clip to 1080x1920 with the full
frame centred over a blurred fill, burn word-timed captions + the hook + a credit line,
publish the clips as assets of release "clips-<video_id>" and write output/<video_id>.json
with their public links. Failures write output/<video_id>.error.txt instead.

Env (testing only): LOCAL_SOURCE=<file> uses a local video instead of downloading;
SKIP_RELEASE=1 skips publishing.
"""
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
JOBS, OUT, TRANS, WORK = ROOT / "jobs", ROOT / "output", ROOT / "transcripts", ROOT / "work"
W, H = 1080, 1920
CREDIT = "Full episode: The Diary Of A CEO"


def run(cmd):
    print("+", " ".join(str(c) for c in cmd), flush=True)
    subprocess.run(cmd, check=True)


def ass_time(t: float) -> str:
    t = max(t, 0)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def ass_escape(s: str) -> str:
    return s.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def chunks(words, start, end):
    """Group words inside [start, end] into short caption chunks (times relative to start)."""
    sel = [(s - start, e - start, w) for s, e, w in words if s >= start - 0.05 and s < end]
    out, cur = [], []
    for s, e, w in sel:
        if cur:
            gap = s - cur[-1][1]
            span = e - cur[0][0]
            if len(cur) >= 3 or gap > 0.6 or span > 1.6 or cur[-1][2].endswith((".", "?", "!", ",")):
                out.append(cur)
                cur = []
        cur.append((s, e, w))
    if cur:
        out.append(cur)
    dur = end - start
    res = []
    for i, c in enumerate(out):
        s0 = max(c[0][0], 0)
        e0 = out[i + 1][0][0] if i + 1 < len(out) else c[-1][1] + 0.3
        e0 = min(e0, c[-1][1] + 0.6, dur)
        if e0 - s0 < 0.08:
            continue
        res.append((s0, e0, " ".join(w for _, _, w in c).upper()))
    return res


def build_ass(path: Path, words, start, end, hook):
    dur = end - start
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,DejaVu Sans,86,&H00FFFFFF,&H00FFFFFF,&H00000000,&H78000000,-1,0,0,0,100,100,0,0,1,7,3,8,70,70,1320,1
Style: Hook,DejaVu Sans,62,&H0000E5FF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,6,2,2,80,80,1320,1
Style: Credit,DejaVu Sans,38,&H40FFFFFF,&H00FFFFFF,&H00000000,&H96000000,-1,0,0,0,100,100,0,0,1,3,1,2,60,60,150,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = []
    if hook:
        lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(dur)},Hook,,0,0,0,,{ass_escape(hook)}")
    lines.append(f"Dialogue: 1,{ass_time(0)},{ass_time(dur)},Credit,,0,0,0,,{CREDIT}")
    for s, e, txt in chunks(words, start, end):
        lines.append(f"Dialogue: 2,{ass_time(s)},{ass_time(e)},Cap,,0,0,0,,{ass_escape(txt)}")
    path.write_text(head + "\n".join(lines) + "\n", encoding="utf-8")


def render(src: Path, start, end, ass: Path, out: Path):
    vf = (
        f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
        f"boxblur=24:2,eq=brightness=-0.18[bg];"
        f"[0:v]scale={W}:-2[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,ass={ass.name},fps=30,format=yuv420p[v]"
    )
    run([
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.2f}", "-to", f"{end:.2f}", "-i", str(src),
        "-filter_complex", vf, "-map", "[v]", "-map", "0:a:0?",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-movflags", "+faststart", str(out),
    ])


def download(vid: str) -> Path:
    local = os.environ.get("LOCAL_SOURCE")
    if local:
        return Path(local)
    dest = WORK / f"{vid}.mp4"
    if dest.exists():
        return dest
    run([
        "yt-dlp", "--no-playlist", "--no-progress",
        "-f", "bv*[height<=720][ext=mp4]+ba[ext=m4a]/b[height<=720]/bv*+ba/b",
        "--merge-output-format", "mp4",
        "-o", str(dest), f"https://www.youtube.com/watch?v={vid}",
    ])
    return dest


def publish(vid: str, files):
    tag = f"clips-{vid}"
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if os.environ.get("SKIP_RELEASE"):
        return {f.name: f"file://{f}" for f in files}
    exists = subprocess.run(["gh", "release", "view", tag], capture_output=True).returncode == 0
    if not exists:
        run(["gh", "release", "create", tag, "--title", f"Clips {vid}", "--notes", "Auto-generated clips"])
    run(["gh", "release", "upload", tag, "--clobber", *[str(f) for f in files]])
    return {f.name: f"https://github.com/{repo}/releases/download/{tag}/{f.name}" for f in files}


def process(job_path: Path):
    job = json.loads(job_path.read_text(encoding="utf-8"))
    vid = job["video_id"]
    trans_path = TRANS / f"{vid}.json"
    words = json.loads(trans_path.read_text(encoding="utf-8"))["words"] if trans_path.exists() else []
    src = download(vid)
    clip_dir = WORK / f"clips-{vid}"
    clip_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for c in job["clips"]:
        start, end = float(c["start"]), float(c["end"])
        # Owner wants 2-3 minute clips; YouTube Shorts must stay at or under 3:00.
        if not (90 <= end - start <= 178):
            print(f"skip {c['slug']}: length {end - start:.1f}s", flush=True)
            continue
        slug = "".join(ch for ch in str(c["slug"]) if ch.isalnum() or ch in "-_")
        ass = clip_dir / f"{slug}.ass"
        build_ass(ass, words, start, end, c.get("hook", ""))
        out = clip_dir / f"{slug}.mp4"
        cwd = os.getcwd()
        os.chdir(clip_dir)  # ass filter path relative to clip_dir avoids escaping issues
        try:
            render(src.resolve(), start, end, ass, out.resolve())
        finally:
            os.chdir(cwd)
        made.append((c, slug, out))
    urls = publish(vid, [m[2] for m in made])
    result = {
        "video_id": vid,
        "status": "ok",
        "clips": [
            {"slug": slug, "start": c["start"], "end": c["end"], "hook": c.get("hook", ""),
             "url": urls[out.name], "size_bytes": out.stat().st_size}
            for c, slug, out in made
        ],
    }
    (OUT / f"{vid}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"{vid}: {len(made)} clips", flush=True)


def main():
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)
    failed = False
    for job_path in sorted(JOBS.glob("*.json")):
        vid = job_path.stem
        if (OUT / f"{vid}.json").exists():
            continue
        try:
            process(job_path)
            (OUT / f"{vid}.error.txt").unlink(missing_ok=True)
        except Exception:
            failed = True
            (OUT / f"{vid}.error.txt").write_text(traceback.format_exc()[-4000:], encoding="utf-8")
            traceback.print_exc()
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
