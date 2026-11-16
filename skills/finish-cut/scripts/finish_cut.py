#!/usr/bin/env python3
"""finish_cut.py: turn finished Frameo clips plus an edit list (EDL) into two run_ffmpeg jobs.

Stdlib only. No network, no Frameo calls. It writes JSON you pass to the `run_ffmpeg` tool:

  picture_job.json   clean-window cuts at a chosen speed, a transition on every cut, comic speech
                     bubbles (name tag, tail that follows the speaker's head) and yellow narration
                     caption boxes. No audio.
  audio_job.json     voice lane (narration + dialogue) + music beds ducked under speech + sound
                     effects + a whoosh on every cut, loudnorm to -14 LUFS, `-c:v copy` over the
                     picture. Its first input is the picture: pass --picture-url once the picture
                     job has finished (or edit the placeholder PICTURE_URL).
  timeline.json      what landed where (chain starts, speeds, line times, cut times, total seconds).

Usage:
  python finish_cut.py edl.json OUT_DIR [--picture-url URL]

EDL (see ../references/edl.md for every field):
  {
    "canvas": {"w": 480, "h": 854, "fps": 24},
    "clips":  {"<clip key>": "<video link a Frameo tool returned>"},
    "chains": [{"id": "c1", "clip": "<clip key>", "windows": [[0.3, 8.2], [10.4, 18.2]], "target_s": 14.4,
                "narration": "n1",
                "dialogue": [{"key": "d1", "t": 0.7, "head_x": 260}],
                "sfx": [{"name": "boxes", "t": 1.0, "gain": 0.5, "max_s": 4}]}],
    "speakers":  {"B": {"tag": "BEN", "color": "&HE0A03C&"}, "A": {"tag": "ANNA", "color": "&H9A3CE0&"}},
    "narration": {"n1": {"url": "...", "seconds": 13.0, "text": "..."}},
    "dialogue":  {"d1": {"url": "...", "seconds": 2.9, "speaker": "A", "text": "..."}},
    "sfx":       {"boxes": {"url": "...", "seconds": 4.0}, "whoosh": {"url": "...", "seconds": 1.0}},
    "bgm":       [{"url": "...", "seconds": 120, "from_chain": "c1", "gain": 0.30, "fade_in": 1.0}],
    "transition": {"mode": "flash", "image_url": "...", "alpha": 0.88, "width_s": 0.24},
    "options":   {"narration_offset_s": 0.6, "duck": true, "loudness_lufs": -14}
  }
"""
from __future__ import annotations

import json
import os
import re
import sys
import textwrap

BS = "\\"


# ---------------------------------------------------------------- timeline
def build_timeline(edl):
    """Give every chain a start, a speed and its sub-clips. Speed never drops below 1.0."""
    t = 0.0
    chains, subs = [], []
    for ch in edl["chains"]:
        wins = [tuple(w) for w in ch["windows"]]
        tot = sum(b - a for a, b in wins)
        f = max(1.0, tot / float(ch["target_s"])) if ch.get("target_s") else 1.0
        start = t
        for (a, b) in wins:
            ol = (b - a) / f
            subs.append({"chain": ch["id"], "clip": ch["clip"], "a": a, "b": b, "f": f, "start": t, "out": ol})
            t += ol
        chains.append(dict(ch, start=start, dur=t - start, f=f))
    return chains, subs, t


# ---------------------------------------------------------------- captions and bubbles (ASS)
def ts(s):
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    return "%d:%02d:%05.2f" % (h, m, s % 60)


def ass_head(w, h, bubble_font=27, caption_font=24):
    return (
        "[Script Info]\nScriptType: v4.00+\nPlayResX: %d\nPlayResY: %d\nWrapStyle: 2\n\n"
        "[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\n"
        "Style: Bub,DejaVu Sans,1,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,4,0,7,0,0,0,1\n"
        "Style: Txt,DejaVu Sans,%d,&H00000000,&H00000000,&H00FFFFFF,&H00000000,1,0,0,0,100,100,0,0,1,0,0,5,10,10,10,1\n"
        "Style: Cap,DejaVu Sans,%d,&H00000000,&H00000000,&H00FFFFFF,&H00000000,1,0,0,0,100,100,0,0,1,0,0,5,10,10,10,1\n\n"
        "[Events]\nFormat: Layer,Start,End,Style,Name,MarginL,MarginR,MarginV,Effect,Text\n" % (w, h, bubble_font, caption_font)
    )


def _hit(ax0, ay0, ax1, ay1, bx0, by0, bx1, by1, m=14):
    return not (ax1 + m < bx0 or bx1 + m < ax0 or ay1 + m < by0 or by1 + m < ay0)


def _ellipse(rx, ry):
    """Closed ellipse path (4 cubic segments) centred on (0,0)."""
    k = 0.5523
    a, b = rx * k, ry * k
    return ("m %d 0 b %d %d %d %d 0 %d b %d %d %d %d %d 0 b %d %d %d %d 0 %d b %d %d %d %d %d 0"
            % (-rx, -rx, -b, -a, -ry, -ry, a, -ry, rx, -b, rx, rx, b, a, ry, ry, -a, ry, -rx, b, -rx))


def bubble_size(text, tag, fs=24, wrap=16):
    """Size an ellipse to its text so the words always stay inside the bubble."""
    lines = textwrap.wrap(text, wrap, break_long_words=False) or [text]
    cw = 0.66 * fs                                    # bold DejaVu Sans average glyph width
    tw = max(max(len(l) for l in lines) * cw, len(tag) * 0.66 * 17)
    th = len(lines) * fs * 1.22 + 17 * 1.3
    rx = int((tw / 2 + 18) * 1.42)
    ry = int((th / 2 + 10) * 1.42)
    return lines, rx, ry


def place_bubble(w, h, head_x, faces, speaker_face=0, half_w=165, half_h=75):
    """House rule: a bubble NEVER covers a face. `faces` = [[x0,y0,x1,y1], ...] for every face visible while the
    bubble is up (canvas px). Search a grid for the spot that overlaps no face box, closest to the speaker's face
    (above it preferred). Returns (cx, cy, tip_x, tip_y); raises SystemExit if no free spot exists."""
    if not faces:
        raise SystemExit("bubble placement: no `faces` given for this line. Look at a frame and list every visible "
                         "face as [x0,y0,x1,y1]; bubbles must never overlay a face.")
    sf = faces[min(speaker_face, len(faces) - 1)]
    best = None
    for cy in range(half_h + 16, h - half_h - 16 + 1, 20):
        for cx in range(half_w + 16, w - half_w - 16 + 1, 20):
            box = (cx - half_w, cy - half_h, cx + half_w, cy + half_h)
            if any(_hit(*box, *f) for f in faces):
                continue
            fx, fy = (sf[0] + sf[2]) / 2.0, sf[1]
            dist = ((cx - fx) ** 2 + (cy - fy) ** 2) ** 0.5 + (80 if cy > fy else 0)
            if best is None or dist < best[0]:
                best = (dist, cx, cy)
    if best is None:
        raise SystemExit("bubble placement: no free spot that avoids every face (%s). Re-frame the shot or shorten the "
                         "line; never overlay a face." % faces)
    _, cx, cy = best
    # tail tip: the point on the speaker's face box nearest the bubble, nudged 6 px outward, so the tail never
    # crosses the face (bubble below the face -> tip on the chin side, above -> forehead side, beside -> cheek side)
    px = min(max(cx, sf[0]), sf[2])
    py = min(max(cy, sf[1]), sf[3])
    dx, dy = cx - px, cy - py
    n = (dx * dx + dy * dy) ** 0.5 or 1.0
    tx, ty = px + dx / n * 6, py + dy / n * 6
    return cx, cy, tx, ty


def bubble(w, h, faces, speaker_face, tag, color, text, a, b, head_x=None):
    """White ellipse sized to its text, placed where it covers no face, tail on the speaker's face."""
    # try several wrap widths and keep the placement with the shortest tail (narrower bubbles fit beside faces)
    best = None
    base = 15 if w < 900 else 18
    for wrap in sorted({base, max(12, base - 2)}, reverse=True):
        lines_, rx_, ry_ = bubble_size(text, tag, wrap=wrap)
        try:
            cx_, cy_, tx_, ty_ = place_bubble(w, h, head_x if head_x is not None else w // 2, faces, speaker_face, rx_, ry_)
        except SystemExit:
            continue
        tail = ((tx_ - cx_) ** 2 + (ty_ - cy_) ** 2) ** 0.5
        if ry_ > 165 and best is not None:
            continue
        if best is None or tail < best[0] - 80:
            best = (tail, lines_, rx_, ry_, cx_, cy_, tx_, ty_)
    if best is None:
        raise SystemExit("bubble placement: no free spot that avoids every face (%s)." % faces)
    _, lines, rx, ry, cx, cy, tx, ty = best
    ux, uy = tx - cx, ty - cy
    n = (ux * ux + uy * uy) ** 0.5 or 1.0
    ux, uy = ux / n, uy / n
    t = 0.94 / (((ux / rx) ** 2 + (uy / ry) ** 2) ** 0.5)
    ex, ey = ux * t, uy * t
    px, py = -uy * 24, ux * 24
    tail = "m %d %d l %d %d l %d %d" % (ex - px, ey - py, tx - cx, ty - cy, ex + px, ey + py)
    shape = "{" + BS + "an7" + BS + "pos(%d,%d)" % (cx, cy) + BS + "bord4" + BS + "3c&H000000&" + BS + "1c&HFFFFFF&" + BS + "p1}"
    e1 = "Dialogue: 0,%s,%s,Bub,,0,0,0,,%s%s %s{%sp0}" % (ts(a), ts(b), shape, _ellipse(rx, ry), tail, BS)
    body = ("{" + BS + "fs17" + BS + "b1" + BS + "c" + color + "}" + tag + "{" + BS + "r}{" + BS + "fs24}" + BS + "N"
            + (BS + "N").join(lines))
    e2 = "Dialogue: 1,%s,%s,Txt,,0,0,0,,{%san5%spos(%d,%d)}%s" % (ts(a), ts(b), BS, BS, cx, cy, body)
    return e1 + "\n" + e2 + "\n"


def caption(w, h, text, a, b, margin=34):
    """Yellow comic caption box, bottom centre, sized to its wrapped lines."""
    lines = textwrap.wrap(text, 27)
    bh = len(lines) * 29 + 26
    cy = h - margin - bh // 2
    hw = w // 2 - 18
    box = "m -%d %d l %d %d l %d %d l -%d %d" % (hw, -bh // 2, hw, -bh // 2, hw, bh // 2, hw, bh // 2)
    shape = "{" + BS + "an7" + BS + "pos(%d,%d)" % (w // 2, cy) + BS + "bord4" + BS + "3c&H000000&" + BS + "1c&H4FD9F9&" + BS + "p1}"
    e1 = "Dialogue: 0,%s,%s,Bub,,0,0,0,,%s%s{%sp0}" % (ts(a), ts(b), shape, box, BS)
    e2 = "Dialogue: 1,%s,%s,Cap,,0,0,0,,{%san5%spos(%d,%d)}%s" % (ts(a), ts(b), BS, BS, w // 2, cy, (BS + "N").join(lines))
    return e1 + "\n" + e2 + "\n"


def chunk_text(text, max_chars=85):
    """Sentence chunks; any chunk over max_chars is split near its middle at a comma or conjunction."""
    def split(x):
        if len(x) <= max_chars:
            return [x]
        mid = len(x) // 2
        cands = [m.start() for m in re.finditer(r", | and | but | while ", x)]
        if cands:
            k = min(cands, key=lambda i: abs(i - mid))
            cut = x.index(" ", k + 1) if x[k] == "," else k
        else:
            cut = x.index(" ", mid)
        return split(x[:cut].strip()) + split(x[cut:].strip())

    out = []
    for s in re.split(r"(?<=[.;])\s+", text.strip()):
        out += split(s)
    return out


# ---------------------------------------------------------------- picture job
def transition_overlay(edl, cuts, total, inputs, fc, canvas):
    """Return the label of the video after transitions. Modes: none | flash | halftone."""
    tr = edl.get("transition") or {"mode": "none"}
    mode = tr.get("mode", "none")
    if mode == "none" or not cuts:
        return "[vc]"
    if mode == "flash":
        wd = float(tr.get("width_s", 0.24))
        inputs.append({"name": "board.png", "url": tr["image_url"], "loop": True})
        bi = len(inputs) - 1
        en = "+".join("between(t,%.2f,%.2f)" % (max(0, c - wd / 2), c + wd / 2) for c in cuts)
        fc.append("[%d:v]scale=%d:%d,format=rgba,colorchannelmixer=aa=%.2f[pat]" % (bi, canvas["w"], canvas["h"], float(tr.get("alpha", 0.88))))
        fc.append("[vc][pat]overlay=enable='%s'[vo]" % en)
        return "[vo]"
    if mode == "halftone":
        try:
            import halftone_transition as ht  # sits next to this file
        except ImportError as e:  # pragma: no cover
            raise SystemExit("transition.mode=halftone needs halftone_transition.py next to finish_cut.py: %s" % e)
        return ht.apply(edl, cuts, total, inputs, fc, canvas)
    raise SystemExit("unknown transition mode %r" % mode)


def build_picture(edl, chains, subs, total):
    canvas = edl.get("canvas", {"w": 480, "h": 854, "fps": 24})
    W, H, FPS = canvas["w"], canvas["h"], canvas.get("fps", 24)
    opt = edl.get("options", {})
    off = float(opt.get("narration_offset_s", 0.6))
    cuts = [s["start"] for s in subs[1:]]

    clip_order = []
    for s in subs:
        if s["clip"] not in clip_order:
            clip_order.append(s["clip"])
    inputs = [{"name": "c%d.mp4" % i, "url": edl["clips"][c]} for i, c in enumerate(clip_order)]

    fc, n = [], 0
    for i, c in enumerate(clip_order):
        ss = [s for s in subs if s["clip"] == c]
        if len(ss) > 1:
            fc.append("[%d:v]split=%d%s" % (i, len(ss), "".join("[s%d_%d]" % (i, j) for j in range(len(ss)))))
            srcs = ["[s%d_%d]" % (i, j) for j in range(len(ss))]
        else:
            srcs = ["[%d:v]" % i]
        for j, s in enumerate(ss):
            fc.append("%strim=%.2f:%.2f,setpts=(PTS-STARTPTS)/%.4f,fps=%d,scale=%d:%d,setsar=1[v%d]"
                      % (srcs[j], s["a"], s["b"], s["f"], FPS, W, H, n))
            s["order"] = n
            n += 1
    ordered = sorted(subs, key=lambda s: s["start"])
    fc.append("".join("[v%d]" % s["order"] for s in ordered) + "concat=n=%d:v=1:a=0[vc]" % len(ordered))
    last = transition_overlay(edl, cuts, total, inputs, fc, canvas)

    # ASS: narration captions timed by measured speech seconds, bubbles by measured line seconds
    ass = ass_head(W, H)
    speakers = edl.get("speakers", {})
    events = {"narration": [], "dialogue": [], "sfx": []}
    for ch in chains:
        nk = ch.get("narration")
        if nk:
            nar = edl["narration"][nk]
            s0 = ch["start"] + off
            events["narration"].append((nk, s0))
            parts = chunk_text(nar["text"])
            tot = float(sum(len(p) for p in parts))
            cur = s0
            for p in parts:
                ln = nar["seconds"] * len(p) / tot
                ass += caption(W, H, p, cur, cur + ln)
                cur += ln
        for d in ch.get("dialogue", []):
            line = edl["dialogue"][d["key"]]
            sp = speakers.get(line["speaker"], {"tag": str(line["speaker"]).upper(), "color": "&H000000&"})
            s0 = ch["start"] + d["t"]
            events["dialogue"].append((d["key"], s0))
            ass += bubble(W, H, d.get("faces"), d.get("speaker_face", 0), sp["tag"], sp["color"], line["text"], s0 - 0.1, s0 + line["seconds"] + 0.35, d.get("head_x"))
        for e in ch.get("sfx", []):
            events["sfx"].append((e["name"], ch["start"] + e["t"], e.get("gain", 0.4), e.get("max_s", 5)))

    argv = []
    for x in inputs:
        argv += (["-loop", "1", "-t", "%.1f" % (total + 2)] if x.get("loop") else []) + ["-i", x["name"]]
    fc.append("%sass=b.ass[v]" % last)
    argv += ["-filter_complex", ";".join(fc), "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "veryfast",
             "-pix_fmt", "yuv420p", "-crf", "23", "-t", "%.2f" % total, "picture.mp4"]
    job = {"reason": "finish-cut picture: clean windows, transitions, bubbles, caption boxes",
           "inputs": [{"name": x["name"], "url": x["url"]} for x in inputs],
           "sidecars": [{"name": "b.ass", "content": ass}], "argv": argv,
           "outputs": [{"name": "picture.mp4", "mime_type": "video/mp4"}], "timeout_seconds": 600}
    return job, events, cuts


# ---------------------------------------------------------------- audio job
def build_audio(edl, chains, total, events, cuts, picture_url):
    opt = edl.get("options", {})
    lufs = opt.get("loudness_lufs", -14)
    ain = [{"name": "film.mp4", "url": picture_url}]
    fa, lane = [], []

    def add(name, url):
        ain.append({"name": name, "url": url})
        return len(ain) - 1

    for key, s0 in events["narration"]:
        i = add("n_%s.mp3" % key, edl["narration"][key]["url"])
        fa.append("[%d:a]aresample=48000,aformat=channel_layouts=stereo,adelay=%d:all=1[a%d]" % (i, int(s0 * 1000), i))
        lane.append("[a%d]" % i)
    for key, s0 in events["dialogue"]:
        i = add("d_%s.mp3" % key, edl["dialogue"][key]["url"])
        fa.append("[%d:a]aresample=48000,aformat=channel_layouts=stereo,adelay=%d:all=1[a%d]" % (i, int(s0 * 1000), i))
        lane.append("[a%d]" % i)
    if not lane:
        raise SystemExit("no narration or dialogue in the EDL: use the `fill` policy by hand")
    fa.append("%samix=inputs=%d:normalize=0,asplit=2[dlg][key]" % ("".join(lane), len(lane)))

    # music beds: each starts at its chain (-1.5 s), ends where the next one starts (or the film ends)
    starts = {c["id"]: c["start"] for c in chains}
    beds = edl.get("bgm", [])
    bl = []
    for k, b in enumerate(beds):
        # bed k begins 1.5 s before its chain (crossfade) and runs 1.5 s into the next bed's chain
        s0 = max(0.0, starts[b["from_chain"]] - (1.5 if k else 0.0))
        e0 = (starts[beds[k + 1]["from_chain"]] + 1.5) if k + 1 < len(beds) else total
        length = e0 - s0
        i = add("bgm%d.mp3" % k, b["url"])
        fin = float(b.get("fade_in", 1.0 if k == 0 else 2.5))
        fout = 2.5 if k + 1 < len(beds) else 3.0
        fa.append("[%d:a]aresample=48000,aformat=channel_layouts=stereo,aloop=loop=-1:size=2147483647,atrim=0:%.2f,"
                  "asetpts=PTS-STARTPTS,afade=t=in:st=0:d=%.1f,afade=t=out:st=%.2f:d=%.1f,volume=%.2f,adelay=%d:all=1[bg%d]"
                  % (i, length, fin, max(0.0, length - fout), fout, b.get("gain", 0.3), int(s0 * 1000), k))
        bl.append("[bg%d]" % k)
    mix_in = ["[dlg]"]
    if bl:
        fa.append("%samix=inputs=%d:normalize=0,asetpts=PTS-STARTPTS[bgm]" % ("".join(bl), len(bl)))
        if opt.get("duck", True):
            fa.append("[bgm][key]sidechaincompress=threshold=0.04:ratio=6:attack=20:release=350[bed]")
            mix_in.append("[bed]")
        else:
            mix_in.append("[bgm]")
    else:
        fa.append("[key]anullsink")  # nothing else reads the sidechain copy

    for name, at, gain, mx in events["sfx"]:
        i = add("s%d_%s.mp3" % (len(ain), name), edl["sfx"][name]["url"])
        fa.append("[%d:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:%.2f,asetpts=PTS-STARTPTS,volume=%.2f,adelay=%d:all=1[x%d]"
                  % (i, mx, gain, int(at * 1000), i))
        mix_in.append("[x%d]" % i)

    wh = edl.get("sfx", {}).get("whoosh")
    if wh and cuts and (edl.get("transition") or {}).get("mode", "none") != "none":
        i = add("whoosh.mp3", wh["url"])
        wv = float((edl.get("transition") or {}).get("whoosh_gain", 0.35))
        fa.append("[%d:a]aresample=48000,aformat=channel_layouts=stereo,volume=%.2f,asplit=%d%s"
                  % (i, wv, len(cuts), "".join("[w%d]" % k for k in range(len(cuts)))))
        for k, c in enumerate(cuts):
            fa.append("[w%d]adelay=%d:all=1[wd%d]" % (k, int(max(0, c - 0.2) * 1000), k))
            mix_in.append("[wd%d]" % k)

    fa.append("%samix=inputs=%d:duration=first:dropout_transition=0:normalize=0,loudnorm=I=%d:TP=-1.5:LRA=11,aresample=48000[a]"
              % ("".join(mix_in), len(mix_in), lufs))
    argv = []
    for x in ain:
        argv += ["-i", x["name"]]
    argv += ["-filter_complex", ";".join(fa), "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", "-t", "%.2f" % total, "final-mix.mp4"]
    return {"reason": "finish-cut sound: voices, ducked music, effects, loudnorm; picture copied untouched",
            "inputs": ain, "argv": argv, "outputs": [{"name": "final-mix.mp4", "mime_type": "video/mp4"}],
            "timeout_seconds": 600}


# ---------------------------------------------------------------- main
def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    edl = json.load(open(argv[1], encoding="utf-8"))
    out = argv[2]
    purl = argv[argv.index("--picture-url") + 1] if "--picture-url" in argv else "PICTURE_URL"
    os.makedirs(out, exist_ok=True)
    chains, subs, total = build_timeline(edl)
    pic, events, cuts = build_picture(edl, chains, subs, total)
    aud = build_audio(edl, chains, total, events, cuts, purl)
    json.dump(pic, open(os.path.join(out, "picture_job.json"), "w", encoding="utf-8"))
    json.dump(aud, open(os.path.join(out, "audio_job.json"), "w", encoding="utf-8"))
    tl = {"total_s": round(total, 2), "cuts": [round(c, 2) for c in cuts],
          "chains": [{"id": c["id"], "start": round(c["start"], 2), "dur": round(c["dur"], 2), "speed": round(c["f"], 2)} for c in chains],
          "dialogue": [(k, round(t, 2)) for k, t in events["dialogue"]]}
    json.dump(tl, open(os.path.join(out, "timeline.json"), "w", encoding="utf-8"), indent=1)
    print("total %.1f s (%.1f min), %d chains, %d cuts" % (total, total / 60, len(chains), len(cuts)))
    over = edl.get("options", {}).get("max_total_s")
    if over and total > over:
        print("WARNING: over the %s s budget; shorten windows or raise speed" % over)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
