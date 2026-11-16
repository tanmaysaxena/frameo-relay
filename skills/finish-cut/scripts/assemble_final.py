#!/usr/bin/env python3
"""assemble_final.py: turn finish_cut's picture_job.json into the final one-job render (picture + title card + sound mix),
at the picture's own size or at another size with upscaled clips. No network, no credits.

Usage:
  python assemble_final.py picture_job.json --mix MIX_URL --title TITLE_URL --out final.mp4 [--size 1080x1920]
         [--crf 21] [--clip-map clips.json] [--ht-map ht.json] [--title-s 5] > final_job.json

  --clip-map  JSON list of clip URLs in chain order (c0, c1, ...) that replaces the picture job's clip inputs (upscaled clips)
  --ht-map    JSON object {old transition clip URL: new URL} for transition clips rendered at the new size
Rules it keeps: the bubble file (.ass) is untouched (its PlayRes scales), the title card is scaled to the film size, the
mix is faded out over its last 2.6 s of picture and padded to the full length, and the audio is the approved mix, never rebuilt.
"""
from __future__ import annotations

import json
import re
import sys


def assemble(job: dict, mix_url: str, title_url: str, out: str, size: tuple = None, crf: int = None,
             clip_urls: list = None, ht_map: dict = None, title_s: float = 5.0, fade_s: float = 2.6) -> dict:
    job = json.loads(json.dumps(job))
    argv = job["argv"]
    fi = argv.index("-filter_complex")
    t_idx = len(argv) - 1 - argv[::-1].index("-t")
    picture_s = float(argv[t_idx + 1])
    fc = argv[fi + 1]
    if "ass=b.ass[v]" not in fc:
        raise ValueError("the picture job's filter graph does not end with ass=b.ass[v]")
    if size:
        w, h = size
        fc = re.sub(r"scale=\d+:\d+", "scale=%d:%d" % (w, h), fc)
    else:
        m = re.search(r"scale=(\d+):(\d+)", fc)
        if not m:
            raise ValueError("the picture job has no scale= step; pass --size")
        w, h = int(m.group(1)), int(m.group(2))
    for it in job["inputs"]:
        n = it["name"][:-4]
        if n.startswith("c") and n[1:].isdigit() and clip_urls:
            it["url"] = clip_urls[int(n[1:])]
        elif n.startswith("ht_") and ht_map and it["url"] in ht_map:
            it["url"] = ht_map[it["url"]]
    n_in = len([x for x in argv if x == "-i"])
    total = round(picture_s + title_s, 2)
    tail = "ass=b.ass[v]"
    if tail not in fc:
        raise ValueError("the picture job's filter graph does not end with ass=b.ass[v]")
    fc = fc.replace(tail, "ass=b.ass[pv];[pv]fps=24,scale=%d:%d,setsar=1[pa];[%d:v]fps=24,scale=%d:%d,setsar=1[pb];"
                    "[pa][pb]concat=n=2:v=1:a=0[v];[%d:a]afade=t=out:st=%.1f:d=%.1f,apad=whole_dur=%.2f[au]"
                    % (w, h, n_in, w, h, n_in + 1, picture_s - fade_s, fade_s, total))
    job["inputs"] += [{"name": "title.mp4", "url": title_url}, {"name": "mix.m4a", "url": mix_url}]
    new = argv[:fi + 1] + [fc] + argv[fi + 2:]
    new[fi:fi] = ["-i", "title.mp4", "-i", "mix.m4a"]
    mi = new.index("-map")
    crf_val = str(crf if crf else (21 if h <= 1280 else 20))
    new[mi:] = ["-map", "[v]", "-map", "[au]", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-crf", crf_val,
                "-c:a", "aac", "-b:a", "192k", "-t", "%.2f" % total, out]
    job["argv"] = new
    job["outputs"] = [{"name": out, "mime_type": "video/mp4"}]
    job["reason"] = "final render: picture, title card and sound mix (%dx%d)" % (w, h)
    job["timeout_seconds"] = 900
    return job


def main(argv: list) -> int:
    args = argv[1:]
    if not args or args[0].startswith("-"):
        print(__doc__)
        return 2

    def opt(name: str, default=None):
        if name in args:
            i = args.index(name)
            return args[i + 1]
        return default
    try:
        with open(args[0], encoding="utf-8") as fh:
            job = json.load(fh)
        size = None
        if opt("--size"):
            a, b = opt("--size").lower().split("x")
            size = (int(a), int(b))
        clips = json.load(open(opt("--clip-map"), encoding="utf-8")) if opt("--clip-map") else None
        ht = json.load(open(opt("--ht-map"), encoding="utf-8")) if opt("--ht-map") else None
        final = assemble(job, opt("--mix"), opt("--title"), opt("--out"), size, int(opt("--crf")) if opt("--crf") else None,
                         clips, ht, float(opt("--title-s", 5.0)))
    except (OSError, ValueError, KeyError, TypeError, IndexError) as exc:
        print("cannot assemble the final job:", exc, file=sys.stderr)
        return 2
    print(json.dumps(final, ensure_ascii=False, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
