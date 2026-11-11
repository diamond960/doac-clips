#!/usr/bin/env python3
"""Turn YouTube captions (json3) + info json into transcripts/<id>.json and transcripts/<id>.txt.

Usage: transcript.py <video_id> <work_dir> <out_dir>
"""
import json
import re
import sys
from pathlib import Path

NOISE = re.compile(r"^\[.*\]$")  # [Music], [Applause], ...


def pick_sub_file(work: Path, vid: str):
    for lang in ("en-orig", "en", "en-US", "en-GB"):
        p = work / f"{vid}.{lang}.json3"
        if p.exists():
            return p
    found = sorted(work.glob(f"{glob_escape(vid)}.*.json3"))
    return found[0] if found else None


def glob_escape(s: str) -> str:
    return re.sub(r"([\[\]*?])", r"[\1]", s)


def load_words(path: Path):
    data = json.loads(path.read_text(encoding="utf-8"))
    segs_all = []  # (start, end_limit, text)
    for ev in data.get("events", []):
        segs = ev.get("segs")
        if not segs:
            continue
        t0 = ev.get("tStartMs", 0)
        t_end = t0 + ev.get("dDurationMs", 0)
        starts = [t0 + s.get("tOffsetMs", 0) for s in segs]
        for i, seg in enumerate(segs):
            txt = seg.get("utf8", "").replace("\n", " ").strip()
            if not txt:
                continue
            nxt = starts[i + 1] if i + 1 < len(segs) else t_end
            segs_all.append((starts[i], max(nxt, starts[i] + 1), txt))

    words = []
    for st, en, txt in segs_all:
        toks = [t for t in txt.split() if t and not NOISE.match(t)]
        if not toks:
            continue
        step = (en - st) / len(toks)
        for k, tok in enumerate(toks):
            words.append([(st + k * step) / 1000.0, tok])
    words.sort(key=lambda w: w[0])

    out = []
    for i, (st, tok) in enumerate(words):
        nxt = words[i + 1][0] if i + 1 < len(words) else st + 0.6
        en = min(nxt, st + 1.2)
        out.append([round(st, 2), round(max(en, st + 0.12), 2), tok])
    return out


def fmt(t: float) -> str:
    t = int(t)
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}"


def readable(words, every=12.0):
    lines, cur, cur_start = [], [], None
    for st, _en, tok in words:
        if cur_start is None:
            cur_start = st
        cur.append(tok)
        ends_sentence = tok.endswith((".", "?", "!"))
        if st - cur_start >= every or (ends_sentence and st - cur_start >= 4):
            lines.append(f"[{fmt(cur_start)}] {' '.join(cur)}")
            cur, cur_start = [], None
    if cur:
        lines.append(f"[{fmt(cur_start)}] {' '.join(cur)}")
    return "\n".join(lines) + "\n"


def main():
    vid, work, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    out.mkdir(parents=True, exist_ok=True)
    info = {}
    info_path = work / f"{vid}.info.json"
    if info_path.exists():
        info = json.loads(info_path.read_text(encoding="utf-8"))
    sub = pick_sub_file(work, vid)
    if not sub:
        raise SystemExit(f"No English captions found for {vid}")
    words = load_words(sub)
    if not words:
        raise SystemExit(f"Captions for {vid} were empty")
    meta = {
        "video_id": vid,
        "title": info.get("title"),
        "channel": info.get("channel"),
        "duration": info.get("duration"),
        "upload_date": info.get("upload_date"),
        "caption_track": sub.name,
        "words": words,
    }
    (out / f"{vid}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    header = f"# {meta['title']} ({vid}) duration={meta['duration']}s\n"
    (out / f"{vid}.txt").write_text(header + readable(words), encoding="utf-8")
    print(f"{vid}: {len(words)} words from {sub.name}")


if __name__ == "__main__":
    main()
