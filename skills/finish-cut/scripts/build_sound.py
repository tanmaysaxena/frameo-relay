#!/usr/bin/env python3
"""build_sound.py: build the sound `run_ffmpeg` job for a hard-cut film from a small JSON spec. No network, no credits.

Why per clip: every dialogue clip is its own input, gated to its measured line windows and delayed to its start in the
film, so a retake that changes a clip length never shifts later dialogue (one long joined audio file does).

Usage:  python build_sound.py spec.json > audio_job.json      (then send the job with run_ffmpeg)

Spec (all times in seconds, clip-local unless noted):
{
  "clips":     [{"id": "s01", "url": "...", "seconds": 17.06}, ...]          film order; seconds = length used in the picture
  "lines":     [{"clip": "s05", "t": 6.95, "end": 8.23}, ...]               measured native speech windows (analyze_media)
  "keep_whole": ["s11"],                                                      clips whose native audio stays open (ambience)
  "dub":       [{"id": "l09", "url": "...", "clip": "s11", "at": 0.8}],       speech files laid in at a clip-local time
  "narration": [{"id": "n01", "url": "...", "clip": "s01", "at": 0.8, "gain": 1.15}],
  "beds":      [{"id": "mA", "url": "...", "start_clip": null, "lead": 0, "fade_in": 1.5,
                 "fade_out_clip": "s05", "fade_out_lead": 5.0, "fade_out_d": 8.0}, ...],   beds follow the shots they cover
  "title_s": 5.0, "bed_gain": 0.30, "pad": 0.15, "tail": 0.30, "loudness": -14
}
A native window is opened from t - pad to end + tail. `fade_out_clip: null` fades out `fade_out_lead` before the end of the picture.
"""
from __future__ import annotations

import json
import sys


def film_starts(clips: list) -> tuple:
    starts, t = {}, 0.0
    for c in clips:
        starts[c["id"]] = t
        t += float(c["seconds"])
    return starts, t


def build(spec: dict) -> dict:
    clips = spec["clips"]
    starts, picture_s = film_starts(clips)
    total = round(picture_s + float(spec.get("title_s", 5.0)), 2)
    pad, tail = float(spec.get("pad", 0.15)), float(spec.get("tail", 0.30))
    bed_gain = float(spec.get("bed_gain", 0.30))
    by_id = {c["id"]: c for c in clips}
    windows: dict = {}
    for ln in spec.get("lines", []):
        windows.setdefault(ln["clip"], []).append((max(0.0, ln["t"] - pad), ln["end"] + tail))
    for cid in spec.get("keep_whole", []):
        windows[cid] = [(0.0, float(by_id[cid]["seconds"]))]

    inputs, fc, voices = [], [], []

    def add(name: str, url: str) -> int:
        inputs.append({"name": name, "url": url})
        return len(inputs) - 1

    for cid in [c["id"] for c in clips if c["id"] in windows]:
        i = add(cid + ".mp4", by_id[cid]["url"])
        gate = "+".join("between(t,%.2f,%.2f)" % w for w in windows[cid])
        ms = int(round(starts[cid] * 1000))
        fc.append("[%d:a]aresample=44100,aformat=channel_layouts=mono,volume=0:enable='not(%s)',adelay=%d|%d[d%s]" % (i, gate, ms, ms, cid))
        voices.append("[d%s]" % cid)
    for item in spec.get("dub", []) + spec.get("narration", []):
        i = add(item["id"] + ".mp3", item["url"])
        ms = int(round((starts[item["clip"]] + float(item["at"])) * 1000))
        gain = float(item.get("gain", 1.15 if item["id"].startswith("n") else 1.0))
        fc.append("[%d:a]aresample=44100,aformat=channel_layouts=mono,volume=%.2f,adelay=%d|%d[%s]" % (i, gain, ms, ms, item["id"]))
        voices.append("[%s]" % item["id"])
    fc.append("".join(voices) + "amix=inputs=%d:duration=longest:dropout_transition=0:normalize=0[voice0]" % len(voices))
    fc.append("[voice0]asplit=2[voice][key]")

    bed_labels = []
    for b in spec.get("beds", []):
        i = add("bed%s.mp3" % b["id"], b["url"])
        start = max(0.0, (starts[b["start_clip"]] if b.get("start_clip") else 0.0) - float(b.get("lead", 0.0)))
        out_at = (starts[b["fade_out_clip"]] if b.get("fade_out_clip") else picture_s) - float(b.get("fade_out_lead", 5.0))
        fade_out_st = max(0.0, out_at - start)          # afade runs before adelay, so it is relative to the bed's own start
        ms = int(round(start * 1000))
        fc.append("[%d:a]aresample=44100,aformat=channel_layouts=stereo,volume=%.2f,afade=t=in:d=%.1f,afade=t=out:st=%.1f:d=%.1f,adelay=%d|%d[%s]"
                  % (i, bed_gain, float(b.get("fade_in", 3.0)), fade_out_st, float(b.get("fade_out_d", 7.0)), ms, ms, b["id"]))
        bed_labels.append("[%s]" % b["id"])
    fc.append("".join(bed_labels) + "amix=inputs=%d:duration=longest:dropout_transition=0:normalize=0[bgm]" % len(bed_labels))
    fc.append("[bgm][key]sidechaincompress=threshold=0.04:ratio=6:attack=20:release=350[duck]")
    fc.append("[voice]aformat=channel_layouts=stereo[vs]")
    fc.append("[vs][duck]amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,atrim=0:%.2f,loudnorm=I=%d:TP=-1.5:LRA=11,aresample=48000[a]"
              % (total, int(spec.get("loudness", -14))))
    argv: list = []
    for it in inputs:
        argv += ["-i", it["name"]]
    argv += ["-filter_complex", ";".join(fc), "-map", "[a]", "-vn", "-c:a", "aac", "-b:a", "192k", "-t", "%.2f" % total, "mix.m4a"]
    return {"reason": "film sound: per-clip gated dialogue, dubbed lines, narration, beds that follow the shots, ducked, loudnorm",
            "inputs": inputs, "argv": argv, "outputs": [{"name": "mix.m4a", "mime_type": "audio/mp4"}], "timeout_seconds": 900,
            "film_seconds": round(picture_s, 2), "total_seconds": total}


def main(argv: list) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as fh:
            spec = json.load(fh)
        job = build(spec)
    except (OSError, KeyError, ValueError) as exc:
        print("cannot build the sound job:", exc, file=sys.stderr)
        return 2
    print(json.dumps({k: v for k, v in job.items() if k not in ("film_seconds", "total_seconds")}, separators=(",", ":")))
    print("film %.2f s, with title %.2f s" % (job["film_seconds"], job["total_seconds"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
