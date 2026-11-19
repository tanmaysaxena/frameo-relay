#!/usr/bin/env python3
"""cut_builder.py: builds a long film's picture, voice, music and final-join `run_ffmpeg` jobs from a per-shot cut spec.
It is the book-length sibling of finish_cut.py (which does EDL cuts with bubbles and halftone transitions): one clip per
shot, no bubbles, dialogue carried by lipsync or voice-over, every length decided by measured speech. No network, no credits.

JOB is the job folder (relay.json, state.json, speech_urls.json, cut_spec.json, ... made by conductor/scripts/chapter_driver.py).

Usage:
  cut_builder.py build JOB [--part-size 16] [--size WxH] [--fps 24] [--crf 21] [--call-size 5]
                           [--music-gain 0.20] [--fade-in 1.5] [--fade-out 2.0]
      writes jobs/cut_picture.json (one job per picture part), jobs/cut_voice.json, jobs/cut_music.json (when
      music_urls.json has sections), jobs/starts.json (film start of every shot + total), lip_plan.json, and
      jobs/picture_call<N>.json (up to 5 jobs each: the argument of one run_ffmpeg call)
  cut_builder.py outputs JOB part1=URL part2=URL voice=URL music=URL     # remember the links run_ffmpeg returned
  cut_builder.py final JOB [--actual SECONDS | --factor F] [--out final.mp4] [--loudness -16] [--crf 24]
      writes jobs/final.json: concat the parts, stretch the picture by planned/actual, mix voice + music, loudnorm, -t planned

Files read from JOB:
  cut_spec.json     {"use": {"5": "rclip"},                  which recorded result (state.json key) a shot's picture comes from
                     "trim": {"4": [[0, 4.8], [6.0, null]]}, windows of the clip kept, in order (null = to the planned end);
                                                              a third item "orig" takes that window from the original clip
                     "nolip": [7, 12],                       shots whose speakers never get lipsync (silhouettes, off-screen)
                     "keep_len": [9],                        pad the shot back to its planned length
                     "offscreen_speakers": ["narrator"]}     speakers never lipsynced (voice-only locks are added automatically)
  speech_urls.json  {"<line id>": {"url", "dur"}}           measured speech (chapter_driver.py speech-urls)
  music_urls.json   {"tracks": {"<id>": {"url", "dur"}},
                     "sections": [{"from": 1, "to": 12, "tracks": ["<id>", ...]}]}   beds placed by shot range, looped to fit
  lip_results.json  {"<shot>.<piece>": {"url", "L"}}        written by lipsync_plan.py save when every piece is back
  final_clips.json  optional {"<shot>": url}                replaces the recorded clip for a shot (for example an upscaled one)

Rules it keeps (measured on the first full book): a shot lasts at least 0.4 s + every line's length + 0.35 s; lines start 0.3 s
into the shot and follow each other 0.35 s apart; a shorter picture is held on its last frame (tpad clone), never stretched; every
shot start comes from real clip lengths plus pads, never from a joined file; picture parts hold at most 16 segments.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

PAD_EPS = 0.05


class CutError(Exception):
    pass


def read_json(path, default=None):
    if not os.path.isfile(path):
        if default is not None:
            return default
        raise CutError("missing file: " + path)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise CutError("%s is not valid JSON: %s" % (path, exc))


def write_json(path, data, **kw):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, **kw)


def shots_of(relay):
    return [s for c in relay.get("chains", []) for s in c.get("segments", [])]


def frame_size(relay, override=None):
    if override:
        w, h = override.lower().split("x")
        return int(w), int(h)
    job = relay.get("job", {})
    short = int("".join(ch for ch in str(job.get("resolution", "720p")) if ch.isdigit()) or 720)
    aw, ah = [float(x) for x in str(job.get("aspect_ratio", "9:16")).split(":")]
    if aw < ah:
        w, h = short, round(short * ah / aw)
    else:
        w, h = round(short * aw / ah), short
    return w + w % 2, h + h % 2


# ---------------------------------------------------------------- layout
def pick_source(st, fin, spec, n):
    key = str(n)
    w = (spec.get("use") or {}).get(key)
    if w:
        if key not in st.get(w, {}):
            raise CutError("cut_spec says shot %d uses %r but state.json has no %r result for it" % (n, w, w))
        return st[w][key]
    if key in st.get("rclip", {}):
        return st["rclip"][key]
    if fin.get(key):
        return fin[key]
    if key not in st.get("clip", {}):
        raise CutError("shot %d has no recorded clip" % n)
    return st["clip"][key]


def original_clip(st, fin, n):
    return fin.get(str(n)) or st["clip"][str(n)]


def layout(job):
    """Everything the jobs are built from: the picture segments, shot starts, the voice events and the lipsync plan."""
    relay = read_json(os.path.join(job, "relay.json"))
    st = read_json(os.path.join(job, "state.json"))
    fin = read_json(os.path.join(job, "final_clips.json"), default={})
    spec = read_json(os.path.join(job, "cut_spec.json"), default={})
    U = read_json(os.path.join(job, "speech_urls.json"), default={})
    lip = read_json(os.path.join(job, "lip_results.json"), default={})
    S = shots_of(relay)
    idx = {s["id"]: i + 1 for i, s in enumerate(S)}
    lines = (relay.get("dialogue") or {}).get("lines", [])
    by = {}
    for ln in lines:
        by.setdefault(idx[ln["segment"]], []).append(ln["id"])
    missing = [i for ids in by.values() for i in ids if i not in U]
    if missing:
        raise CutError("no measured speech for lines: %s (chapter_driver.py speech-urls)" % ", ".join(missing[:8]))
    speaker = {ln["id"]: ln["speaker"] for ln in lines}
    phone = {ln["id"] for ln in lines if ln.get("bubble") == "phone"}
    offscreen = set(spec.get("offscreen_speakers") or []) | {"narrator"}
    for lk in (relay.get("locks") or {}).get("items", []):
        if lk.get("voice_only") or lk.get("kind") == "voice":
            offscreen.add(lk["id"])
    nolip = {int(x) for x in spec.get("nolip", [])}
    keep_len = {int(x) for x in spec.get("keep_len", [])}

    segs, starts, lipplan = [], {}, {}
    t = 0.0
    for n in range(1, len(S) + 1):
        d = S[n - 1]["duration_s"]
        ranges = (spec.get("trim") or {}).get(str(n)) or [[0, None]]
        u = pick_source(st, fin, spec, n)
        dur = sum((rg[1] if rg[1] else d) - rg[0] for rg in ranges)
        ids = by.get(n, [])
        need = 0.4 + sum(U[i]["dur"] + 0.35 for i in ids)
        pad = round(max(0.0, need - dur), 2)
        if n in keep_len:
            pad = round(max(pad, max(need, d) - dur), 2)
        if pad < PAD_EPS:
            pad = 0
        lt, tt = [], 0.3
        for i in ids:
            lt.append((i, tt, U[i]["dur"]))
            tt += U[i]["dur"] + 0.35
        ps = 0.0
        for k, rg in enumerate(ranges):
            a_, b_ = rg[0], rg[1]
            uu = original_clip(st, fin, n) if len(rg) > 2 and rg[2] == "orig" else u
            plen = (b_ if b_ else d) - a_
            last = k == len(ranges) - 1
            key = "%d.%d" % (n, k)
            inl = [(i, t0, du) for i, t0, du in lt
                   if speaker[i] not in offscreen and i not in phone and n not in nolip
                   and t0 >= ps - 0.05 and t0 < ps + plen - 0.4]
            if inl:
                ev = [(i, a_ + (t0 - ps), du) for i, t0, du in inl]
                lx = max(c + du for i, c, du in ev) + 0.15
                lx = round(min(lx, b_ if b_ else d + 0.04), 2)
                lipplan[key] = {"shot": n, "k": k, "url": uu, "a": a_, "b": b_, "L": lx,
                                "lines": [(i, round(c, 3)) for i, c, du in ev]}
            lr = lip.get(key)
            if lr:
                segs.append((n, lr["url"], a_, lr["L"], 0))
                segs.append((n, uu, lr["L"], b_, pad if last else 0))
            else:
                segs.append((n, uu, a_, b_, pad if last else 0))
            ps += plen
        starts[n] = t
        t += dur + pad
    events = []
    for n in range(1, len(S) + 1):
        t0 = starts[n] + 0.3
        for i in by.get(n, []):
            events.append((i, round(t0, 3)))
            t0 += U[i]["dur"] + 0.35
    return {"relay": relay, "shots": S, "segs": segs, "starts": starts, "total": t, "lipplan": lipplan,
            "events": events, "speech": U, "by": by}


# ---------------------------------------------------------------- jobs
def ffmpeg_job(reason, inputs, argv, outputs, timeout):
    return {"reason": reason, "inputs": inputs, "argv": list(argv), "outputs": outputs, "timeout_seconds": timeout}


def picture_jobs(lay, part_size=16, size=None, fps=24, crf=21):
    w, h = frame_size(lay["relay"], size)
    segs = lay["segs"]
    parts = [segs[i:i + part_size] for i in range(0, len(segs), part_size)]
    jobs = []
    for pi, part in enumerate(parts, 1):
        ins, fc, lab = [], [], []
        for k, (n, u, a, b, pad) in enumerate(part):
            ins.append({"name": "c%d.mp4" % k, "url": u})
            f = "[%d:v]trim=start=%s%s,setpts=PTS-STARTPTS" % (k, a, (":end=%s" % b) if b else "")
            if pad:
                f += ",tpad=stop_mode=clone:stop_duration=%s" % pad
            f += ",scale=%d:%d,setsar=1,fps=%d[v%d]" % (w, h, fps, k)
            fc.append(f)
            lab.append("[v%d]" % k)
        graph = ";".join(fc) + ";" + "".join(lab) + "concat=n=%d:v=1:a=0[v]" % len(part)
        argv = ["-y"]
        for x in ins:
            argv += ["-i", x["name"]]
        argv += ["-filter_complex", graph, "-map", "[v]", "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf),
                 "-movflags", "+faststart", "part%d.mp4" % pi]
        jobs.append(ffmpeg_job("picture part %d of %d (cut from the shot spec)" % (pi, len(parts)), ins, argv,
                               [{"name": "part%d.mp4" % pi, "mime_type": "video/mp4"}], 600))
    return jobs


def voice_job(lay):
    ev, U = lay["events"], lay["speech"]
    if not ev:
        return None
    ins = [{"name": "v%d.mp3" % k, "url": U[i]["url"]} for k, (i, _) in enumerate(ev)]
    fc = ";".join("[%d:a]adelay=%d|%d,volume=1.0[a%d]" % (k, int(round(t * 1000)), int(round(t * 1000)), k) for k, (i, t) in enumerate(ev))
    fc += ";" + "".join("[a%d]" % k for k in range(len(ev)))
    fc += "amix=inputs=%d:normalize=0:dropout_transition=0,apad=whole_dur=%s[voice]" % (len(ev), round(lay["total"], 2))
    argv = ["-y"]
    for x in ins:
        argv += ["-i", x["name"]]
    argv += ["-filter_complex", fc, "-map", "[voice]", "-ac", "1", "-c:a", "libmp3lame", "-b:a", "160k", "voice.mp3"]
    return ffmpeg_job("voice track from measured line starts", ins, argv, [{"name": "voice.mp3", "mime_type": "audio/mpeg"}], 600)


def place_beds(lay, music):
    """[(url, start_s, length_s)] from sections of shots with ordered tracks; a short section loops its tracks."""
    starts, total = lay["starts"], lay["total"]
    tracks = music.get("tracks") or {}
    beds = []
    for sec in music.get("sections") or []:
        a, b = int(sec["from"]), int(sec["to"])
        if a not in starts or b not in starts:
            raise CutError("music section %s..%s is outside the shots" % (a, b))
        s0 = starts[a]
        s1 = starts[b + 1] if b + 1 in starts else total
        ids = sec.get("tracks") or []
        for tid in ids:
            if tid not in tracks:
                raise CutError("music track %r is not in music_urls.json tracks" % tid)
        if not ids or any(tracks[t]["dur"] <= 0 for t in ids):
            raise CutError("music section %s..%s needs tracks with a positive dur" % (a, b))
        pos, k = s0, 0
        while s1 - pos > 1:
            tr = tracks[ids[k % len(ids)]]
            ln = min(tr["dur"], s1 - pos)
            beds.append((tr["url"], pos, ln))
            pos += ln
            k += 1
    return beds


def music_job(lay, music, gain=0.20, fade_in=1.5, fade_out=2.0):
    beds = place_beds(lay, music)
    if not beds:
        return None
    ins = [{"name": "m%d.mp3" % k, "url": b[0]} for k, b in enumerate(beds)]
    parts = []
    for k, (u, pos, ln) in enumerate(beds):
        ms = int(round(pos * 1000))
        parts.append("[%d:a]atrim=duration=%s,afade=t=in:d=%s,afade=t=out:st=%s:d=%s,adelay=%d|%d,volume=%s[m%d]"
                     % (k, round(ln, 2), fade_in, max(0, round(ln - fade_out, 2)), fade_out, ms, ms, gain, k))
    fc = ";".join(parts) + ";" + "".join("[m%d]" % k for k in range(len(beds)))
    fc += "amix=inputs=%d:normalize=0:dropout_transition=0,apad=whole_dur=%s[music]" % (len(beds), round(lay["total"], 2))
    argv = ["-y"]
    for x in ins:
        argv += ["-i", x["name"]]
    argv += ["-filter_complex", fc, "-map", "[music]", "-ac", "2", "-c:a", "libmp3lame", "-b:a", "160k", "music.mp3"]
    return ffmpeg_job("music beds placed by scene", ins, argv, [{"name": "music.mp3", "mime_type": "audio/mpeg"}], 600)


def final_job(outputs, total, factor=1.0, loudness=-16, crf=24, out="final.mp4"):
    parts = sorted((k for k in outputs if k.startswith("part")), key=lambda k: int(k[4:]))
    if not parts:
        raise CutError("jobs/outputs.json has no part1.. links (cut_builder.py outputs JOB part1=URL ...)")
    if "voice" not in outputs:
        raise CutError("jobs/outputs.json has no voice link")
    ins = [{"name": "%s.mp4" % p, "url": outputs[p]} for p in parts]
    ins.append({"name": "voice.mp3", "url": outputs["voice"]})
    audio = ["[%d:a]" % (len(parts))]
    if outputs.get("music"):
        ins.append({"name": "music.mp3", "url": outputs["music"]})
        audio.append("[%d:a]" % (len(parts) + 1))
    v = "".join("[%d:v]" % i for i in range(len(parts))) + "concat=n=%d:v=1:a=0" % len(parts)
    if abs(factor - 1.0) > 1e-6:
        v += ",setpts=PTS*%.6f" % factor
    v += ",format=yuv420p[v]"
    a = "".join(audio)
    if len(audio) > 1:
        a += "amix=inputs=%d:normalize=0:dropout_transition=0," % len(audio)
    else:
        a += "anull,"
    a += "loudnorm=I=%s:TP=-1.5:LRA=11[a]" % loudness
    argv = ["-y"]
    for x in ins:
        argv += ["-i", x["name"]]
    argv += ["-filter_complex", v + ";" + a, "-map", "[v]", "-map", "[a]", "-t", "%.2f" % total,
             "-c:v", "libx264", "-preset", "veryfast", "-crf", str(crf), "-c:a", "aac", "-b:a", "192k",
             "-movflags", "+faststart", out]
    return ffmpeg_job("final join: parts, setpts x%.4f, voice + music, loudnorm" % factor, ins, argv,
                      [{"name": out, "mime_type": "video/mp4"}], 600)


def write_calls(job_dir, prefix, jobs, size=5):
    """A run_ffmpeg call holds 1 to 5 jobs: write each group as its own minified file."""
    names = []
    for c in range(0, len(jobs), size):
        name = "%s%d.json" % (prefix, c // size + 1)
        with open(os.path.join(job_dir, "jobs", name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(jobs[c:c + size], separators=(",", ":")))
        names.append(name)
    return names


# ---------------------------------------------------------------- commands
def cmd_build(a):
    job = a.job
    lay = layout(job)
    os.makedirs(os.path.join(job, "jobs"), exist_ok=True)
    pj = picture_jobs(lay, a.part_size, a.size, a.fps, a.crf)
    write_json(os.path.join(job, "jobs", "cut_picture.json"), pj)
    calls = write_calls(job, "picture_call", pj, a.call_size)
    vj = voice_job(lay)
    if vj:
        write_json(os.path.join(job, "jobs", "cut_voice.json"), vj)
    music = read_json(os.path.join(job, "music_urls.json"), default={})
    mj = music_job(lay, music, a.music_gain, a.fade_in, a.fade_out) if music.get("sections") else None
    if mj:
        write_json(os.path.join(job, "jobs", "cut_music.json"), mj)
    write_json(os.path.join(job, "lip_plan.json"), lay["lipplan"])
    write_json(os.path.join(job, "jobs", "starts.json"),
               {"starts": {str(k): round(v, 3) for k, v in lay["starts"].items()}, "total": round(lay["total"], 2), "parts": len(pj)})
    print("total picture %.1f s, picture parts %d (%s), voice lines %d, music beds %s, lipsync pieces %d (%.0f audio s)"
          % (lay["total"], len(pj), ", ".join(calls), len(lay["events"]),
             len(mj["inputs"]) if mj else "none", len(lay["lipplan"]), sum(v["L"] for v in lay["lipplan"].values())))
    return 0


def cmd_outputs(a):
    path = os.path.join(a.job, "jobs", "outputs.json")
    d = read_json(path, default={})
    for p in a.pairs:
        if "=" not in p:
            raise CutError("expected name=url, got %r" % p)
        k, v = p.split("=", 1)
        d[k] = v
    write_json(path, d, indent=1)
    print("outputs known:", ", ".join(sorted(d)))
    return 0


def cmd_final(a):
    meta = read_json(os.path.join(a.job, "jobs", "starts.json"))
    outputs = read_json(os.path.join(a.job, "jobs", "outputs.json"))
    total = meta["total"]
    if a.actual and a.factor:
        raise CutError("give --actual or --factor, not both")
    factor = a.factor if a.factor else (total / a.actual if a.actual else 1.0)
    if not 0.9 <= factor <= 1.1:
        raise CutError("stretch factor %.4f is outside 0.9..1.1: a drift that large is a cut problem, not rounding" % factor)
    job = final_job(outputs, total, factor, a.loudness, a.crf, a.out)
    write_json(os.path.join(a.job, "jobs", "final.json"), job)
    print("final job: %d inputs, planned %.2f s, setpts factor %.4f -> jobs/final.json" % (len(job["inputs"]), total, factor))
    return 0


def build_parser():
    ap = argparse.ArgumentParser(description="Per-shot cut builder: picture parts, voice, music, final join.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build")
    p.add_argument("job")
    p.add_argument("--part-size", type=int, default=16)
    p.add_argument("--size", help="WxH (default: job.resolution and job.aspect_ratio)")
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--crf", type=int, default=21)
    p.add_argument("--call-size", type=int, default=5, help="jobs per run_ffmpeg call (at most 5)")
    p.add_argument("--music-gain", type=float, default=0.20)
    p.add_argument("--fade-in", type=float, default=1.5)
    p.add_argument("--fade-out", type=float, default=2.0)
    p.set_defaults(fn=cmd_build)
    p = sub.add_parser("outputs")
    p.add_argument("job")
    p.add_argument("pairs", nargs="+", help="part1=URL ... voice=URL music=URL")
    p.set_defaults(fn=cmd_outputs)
    p = sub.add_parser("final")
    p.add_argument("job")
    p.add_argument("--actual", type=float, help="measured length in seconds of the joined parts; factor = planned/actual")
    p.add_argument("--factor", type=float, help="setpts factor directly (1.0 = none)")
    p.add_argument("--out", default="final.mp4")
    p.add_argument("--loudness", default="-16")
    p.add_argument("--crf", type=int, default=24)
    p.set_defaults(fn=cmd_final)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    if getattr(a, "call_size", 5) > 5:
        a.call_size = 5
    try:
        return a.fn(a)
    except CutError as exc:
        print("FAIL: %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
