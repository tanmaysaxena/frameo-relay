#!/usr/bin/env python3
"""Halftone-dot edge-to-edge scene transitions, made with ffmpeg `geq` (no assets, no credits).

How it looks: a magenta halftone dot grid (with a cyan layer that lags and sits a few pixels off, like
misregistered print) grows from one edge until the frame is fully covered (the CUT happens at that peak),
then the dots shrink away in the SAME direction, so the motion keeps flowing through the cut. Eight
directions (LR, RL, TB, BT and the four diagonals) are shuffled across the cuts so no two neighbours repeat.

Two steps, both free `run_ffmpeg` work:

  1. python halftone_transition.py jobs [W H FPS DUR]   -> JSON list of 8 run_ffmpeg jobs (one per
     direction, black background, colour dots). Send them 5 at a time (a call holds at most 5 jobs) and
     keep the 8 output links: {"LR": "<link>", ...}.
  2. In the EDL set  "transition": {"mode": "halftone", "clips": {"LR": "<link>", ...}, "seed": 7}
     and run finish_cut.py. It calls apply() below: per cut, the right clip is keyed (black becomes
     transparent), delayed so its peak (DUR/2) lands exactly on the cut, and overlaid.

  python halftone_transition.py expr LR   -> the geq expression for one direction (for debugging)

Tuning: PITCH is the dot spacing in px (bigger = fewer, bolder dots); RMAX above 0.7072 guarantees the
frame is fully covered at the peak; DUR is the whole transition (0.9 s: grow 0.45, shrink 0.45). If the
overlay shows a dark fringe, raise the colorkey similarity in apply(). If geq is slow on a long film,
render the 8 clips once and reuse them (they are inputs, not recomputed per cut).
"""
from __future__ import annotations

import json
import random
import sys

FPS = 24
DUR = 0.9
PITCH = 30
RMAX = 0.76

# s = 0 at the start edge, 1 at the far edge
DIRS = {
    "LR": "X/W",
    "RL": "1-X/W",
    "TB": "Y/H",
    "BT": "1-Y/H",
    "TLBR": "(X/W+Y/H)/2",
    "BRTL": "1-(X/W+Y/H)/2",
    "TRBL": "((W-X)/W+Y/H)/2",
    "BLTR": "1-((W-X)/W+Y/H)/2",
}


def mask_expr(direction, dur=DUR, pitch=PITCH, rmax=RMAX, lag=0.0, dx=0, dy=0):
    s = DIRS[direction].replace("X", "(X-%d)" % dx).replace("Y", "(Y-%d)" % dy)
    p = "(max(T-%.3f,0)/%.3f)" % (lag, dur / 2)
    a = "if(lt(%s,1),clip((%s*1.7-(%s))*3,0,1),1-clip(((%s-1)*1.7-(%s))*3,0,1))" % (p, p, s, p, s)
    du = "mod(((X-%d)+(Y-%d))*0.70711+4000,%d)-%d" % (dx, dy, pitch, pitch // 2)
    dv = "mod(((X-%d)-(Y-%d))*0.70711+4000,%d)-%d" % (dx, dy, pitch, pitch // 2)
    return "lte(hypot(%s,%s),%.2f*%s)" % (du, dv, rmax * pitch, a)


def geq(direction, dur=DUR, pitch=PITCH, rmax=RMAX):
    m = mask_expr(direction, dur, pitch, rmax)
    c = mask_expr(direction, dur, pitch, rmax, lag=0.07, dx=5, dy=3)
    return "geq=r='if(%s,255,0)':g='if(%s,46,if(%s,222,0))':b='if(%s,147,if(%s,226,0))'" % (m, m, c, m, c)


def job(direction, w=480, h=854, fps=FPS, dur=DUR):
    name = "ht_%s.mp4" % direction
    return {
        "reason": "Halftone dot transition %s (edge to edge, flows in one direction)" % direction,
        "inputs": [],
        "argv": ["-f", "lavfi", "-i", "color=c=black:s=%dx%d:r=%d:d=%.2f" % (w, h, fps, dur),
                 "-vf", "format=rgb24," + geq(direction, dur) + ",format=yuv420p",
                 "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p", name],
        "outputs": [{"name": name, "mime_type": "video/mp4"}],
        "timeout_seconds": 300,
    }


def shuffled_directions(n, seed=7):
    """n directions, every direction used about equally, no two neighbours the same."""
    rng = random.Random(seed)
    out, deck = [], []
    while len(out) < n:
        if not deck:
            deck = list(DIRS)
            rng.shuffle(deck)
            if out and deck[0] == out[-1]:
                deck.append(deck.pop(0))
        out.append(deck.pop(0))
    return out


def apply(edl, cuts, total, inputs, fc, canvas):
    """Hook for finish_cut.py. Adds the transition clips as inputs and overlay filters; returns the label."""
    tr = edl["transition"]
    clips = tr["clips"]
    dur = float(tr.get("dur_s", DUR))
    dirs = shuffled_directions(len(cuts), int(tr.get("seed", 7)))
    used = {}
    for k, d in enumerate(dirs):
        used.setdefault(d, []).append(k)
    sim = float(tr.get("key_similarity", 0.25))
    last = "[vc]"
    n = 0
    for d, ks in used.items():
        inputs.append({"name": "ht_%s.mp4" % d, "url": clips[d]})
        idx = len(inputs) - 1
        labs = ["[h%s_%d]" % (d, j) for j in range(len(ks))]
        if len(ks) > 1:
            fc.append("[%d:v]format=rgba,colorkey=black:%.2f:0.15,split=%d%s" % (idx, sim, len(ks), "".join(labs)))
        else:
            fc.append("[%d:v]format=rgba,colorkey=black:%.2f:0.15%s" % (idx, sim, labs[0]))
        for j, k in enumerate(ks):
            start = max(0.0, cuts[k] - dur / 2)
            fc.append("%ssetpts=PTS-STARTPTS+%.3f/TB[hs%d]" % (labs[j], start, n))
            fc.append("%s[hs%d]overlay=eof_action=pass:format=auto[ho%d]" % (last, n, n))
            last = "[ho%d]" % n
            n += 1
    return last


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "jobs"
    if cmd == "jobs":
        w, h, fps, dur = (int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5])) if len(sys.argv) > 5 else (480, 854, FPS, DUR)
        print(json.dumps([job(d, w, h, fps, dur) for d in DIRS]))
    elif cmd == "expr":
        print(geq(sys.argv[2]))
    else:
        print(__doc__)
