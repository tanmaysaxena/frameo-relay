#!/usr/bin/env python3
"""lipsync_plan.py: the lipsync recipe (sync-3, cut_off mode) as bookkeeping. Plans which shot pieces get a lipsynced face, builds
their dialogue-only audio jobs, composes the generate_lipsync calls and records the results so cut_builder.py can splice them.
No network by default, no credits: the paid calls are yours.

The recipe, measured on the first full book:
  - A piece is one trim window of one shot with at least one on-screen, non-narrator, non-phone speaker. Shots listed in
    cut_spec.json "nolip" (silhouettes, nobody visibly speaking, off-screen voices) are skipped: lipsync would make the wrong
    face talk. Lipsync is weak on wide shots; it works on close and medium shots with one clearly visible speaker.
  - Each piece gets one dialogue-only mp3: every line delayed to its clip time (0.3 s into the shot, then each line's measured
    length + 0.35 s), mixed with amix normalize=0.
  - generate_lipsync(video_url = the clip used, audio_url = that mp3, model sync-3). The output covers the audio length from
    the clip start (about 17-19 credits per audio second, one item per call, quote first).
  - The cut then plays lipsync [a, L] followed by the original [L, b], where L = planned L - 0.15 (written by `save`).

JOB is the job folder (relay.json, state.json, speech_urls.json, cut_spec.json, ... see chapter_driver.py and cut_builder.py).

Usage:
  lipsync_plan.py plan JOB                      # write lip_plan.json from the cut spec (needs finish-cut/scripts/cut_builder.py)
  lipsync_plan.py audio JOB [--group 5]         # jobs/lip_audio_grouped.json + jobs/lipcall<N>.json (up to 5 jobs per run_ffmpeg call)
  lipsync_plan.py audio-urls JOB key=URL ...    # remember the mp3 links run_ffmpeg returned (key like 12.0 = shot 12, piece 0)
  lipsync_plan.py next JOB A B                  # EST and the calls for pieces A..B (0-based slice of lip_plan.json), saved to calls/
  lipsync_plan.py record JOB A B gen1,gen2 [--credits 18]   # generation ids (+ ledger rows when --credits is given)
  lipsync_plan.py save JOB A [--verify] < rows  # result links for pieces A.. ("<link or id>" or "<key>=<link or id>" per line);
                                                # writes lip_results.json once every piece is back

Run it as `python "$RELAY_HOME/skills/conductor/scripts/lipsync_plan.py" ...`. Python 3.10+, stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import chapter_driver as cd  # noqa: E402

MODEL = "sync-3"
TAIL_TRIM = 0.15  # seconds taken off L when the lipsync result is spliced
MP3_ARGS = ["-ac", "1", "-c:a", "libmp3lame", "-b:a", "160k"]


class LipError(Exception):
    pass


def jp(job, *p):
    return os.path.join(job, *p)


def load_plan(job):
    return cd.read_json(jp(job, "lip_plan.json"))


def key_file(key):
    return key.replace(".", "_")


def cmd_plan(a):
    cut_dir = os.path.join(HERE, "..", "..", "finish-cut", "scripts")
    sys.path.insert(0, cut_dir)
    try:
        import cut_builder  # noqa: E402
    except ImportError:
        raise LipError("cut_builder.py not found next to the conductor skill (looked in %s); run `cut_builder.py build JOB` instead"
                       % os.path.normpath(cut_dir))
    try:
        lay = cut_builder.layout(a.job)
    except cut_builder.CutError as exc:
        raise LipError(str(exc))
    cd.write_json(jp(a.job, "lip_plan.json"), lay["lipplan"])
    plan = lay["lipplan"]
    print("lipsync pieces %d, audio seconds %.0f" % (len(plan), sum(v["L"] for v in plan.values())))
    return 0


def audio_jobs(plan, speech, group=5, label="lipsync audio"):
    keys = list(plan.keys())
    jobs = []
    for g in range(0, len(keys), group):
        ks = keys[g:g + group]
        ins, fc, maps, outs = [], [], [], []
        j = 0
        for key in ks:
            labs = []
            for lid, c in plan[key]["lines"]:
                if lid not in speech:
                    raise LipError("no measured speech for line %s" % lid)
                ins.append({"name": "i%d.mp3" % j, "url": speech[lid]["url"]})
                ms = int(round(c * 1000))
                fc.append("[%d:a]adelay=%d|%d[x%d]" % (j, ms, ms, j))
                labs.append("[x%d]" % j)
                j += 1
            out, lab = "lip_%s.mp3" % key_file(key), "o%s" % key_file(key)
            fc.append("".join(labs) + ("amix=inputs=%d:normalize=0:dropout_transition=0[%s]" % (len(labs), lab) if len(labs) > 1
                                       else "anull[%s]" % lab))
            maps += ["-map", "[%s]" % lab] + MP3_ARGS + [out]
            outs.append({"name": out, "mime_type": "audio/mpeg"})
        argv = ["-y"]
        for x in ins:
            argv += ["-i", x["name"]]
        argv += ["-filter_complex", ";".join(fc)] + maps
        jobs.append({"reason": "%s %s" % (label, ",".join(ks[:1] + ks[-1:])), "inputs": ins, "argv": argv,
                     "outputs": outs, "timeout_seconds": 300})
    return jobs


def cmd_audio(a):
    plan = load_plan(a.job)
    speech = cd.read_json(jp(a.job, "speech_urls.json"))
    jobs = audio_jobs(plan, speech, a.group)
    cd.write_json(jp(a.job, "jobs", "lip_audio_grouped.json"), jobs)
    for c in range(0, len(jobs), 5):
        with open(jp(a.job, "jobs", "lipcall%d.json" % (c // 5 + 1)), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(jobs[c:c + 5], separators=(",", ":")))
    print("%d audio jobs for %d pieces, %d run_ffmpeg calls" % (len(jobs), len(plan), (len(jobs) + 4) // 5))
    return 0


def cmd_audio_urls(a):
    path = jp(a.job, "lip_audio_urls.json")
    d = cd.read_json(path, default={})
    plan = load_plan(a.job)
    for p in a.pairs:
        k, _, u = p.partition("=")
        if k not in plan:
            raise LipError("%r is not a piece in lip_plan.json" % k)
        d[k] = u
    cd.write_json(path, d, indent=1)
    missing = [k for k in plan if k not in d]
    print("audio links %d of %d pieces%s" % (len(d), len(plan), (", missing " + ",".join(missing)) if missing else ""))
    return 0


def cmd_next(a):
    plan = load_plan(a.job)
    au = cd.read_json(jp(a.job, "lip_audio_urls.json"))
    keys = list(plan.keys())[a.a:a.b]
    if not keys:
        raise LipError("no pieces in %d..%d" % (a.a, a.b))
    for k in keys:
        if k not in au:
            raise LipError("piece %s has no audio link (audio-urls)" % k)
    calls = [{"video_url": plan[k]["url"], "audio_url": au[k], "model": MODEL} for k in keys]
    est = [dict(c, kind="lipsync") for c in calls]
    for k, c in zip(keys, calls):
        cd.write_json(jp(a.job, "calls", "lipsync_%s.draft.json" % key_file(k)), c)
    print("EST=" + json.dumps(est, separators=(",", ":")))
    print("pieces", keys, "audio seconds", [plan[k]["L"] for k in keys])
    print("one generate_lipsync call per piece, each with its own quote_id; save the call to calls/ before sending")
    return 0


def cmd_record(a):
    plan = load_plan(a.job)
    keys = list(plan.keys())[a.a:a.b]
    gens = [g for g in a.gens.split(",") if g]
    if len(gens) != len(keys):
        raise LipError("%d generation ids for %d pieces" % (len(gens), len(keys)))
    path = jp(a.job, "lip_gen.json")
    lg = cd.read_json(path, default={})
    credits = None
    if a.credits:
        credits = cd.credit_list(a.credits, len(keys))
    for i, (k, g) in enumerate(zip(keys, gens)):
        lg[k] = g
        if credits:
            cd.ledger_row(a.job, "lipsync", "lip-" + key_file(k), credits[i], g)
    cd.write_json(path, lg)
    print("recorded", len(lg), "of", len(plan))
    return 0


def cmd_save(a):
    plan = load_plan(a.job)
    keys = list(plan.keys())
    text = sys.stdin.read()
    rows = [r.strip() for r in text.splitlines() if r.strip()]
    st = cd.load_state(a.job)
    path = jp(a.job, "lip_results_urls.json")
    d = cd.read_json(path, default={})
    bad = []
    for i, row in enumerate(rows):
        if "=" in row and not row.startswith("http"):
            k, _, v = row.partition("=")
        else:
            if a.a + i >= len(keys):
                raise LipError("row %d is past the %d pieces" % (i + 1, len(keys)))
            k, v = keys[a.a + i], row
        if k not in plan:
            raise LipError("%r is not a piece in lip_plan.json" % k)
        url = cd.full(st, v.strip(), "video")
        if a.verify and not cd.head_ok(url):
            bad.append(k)
        d[k] = url
    cd.write_json(path, d)
    print(len(d), "of", len(keys), "pieces saved, unreachable", bad)
    if len(d) == len(keys) and not bad:
        cd.write_json(jp(a.job, "lip_results.json"),
                      {k: {"url": d[k], "L": round(plan[k]["L"] - TAIL_TRIM, 2)} for k in keys})
        print("lip_results.json written: re-run cut_builder.py build to splice them in")
    return 1 if bad else 0


def build_parser():
    ap = argparse.ArgumentParser(description="Lipsync plan, audio, calls and results (sync-3 recipe).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan")
    p.add_argument("job")
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("audio")
    p.add_argument("job")
    p.add_argument("--group", type=int, default=5, help="pieces per ffmpeg job")
    p.set_defaults(fn=cmd_audio)
    p = sub.add_parser("audio-urls")
    p.add_argument("job")
    p.add_argument("pairs", nargs="+")
    p.set_defaults(fn=cmd_audio_urls)
    p = sub.add_parser("next")
    p.add_argument("job")
    p.add_argument("a", type=int)
    p.add_argument("b", type=int)
    p.set_defaults(fn=cmd_next)
    p = sub.add_parser("record")
    p.add_argument("job")
    p.add_argument("a", type=int)
    p.add_argument("b", type=int)
    p.add_argument("gens")
    p.add_argument("--credits", help="credits per piece (one value or one per piece); writes ledger rows of kind lipsync")
    p.set_defaults(fn=cmd_record)
    p = sub.add_parser("save")
    p.add_argument("job")
    p.add_argument("a", type=int)
    p.add_argument("--verify", action="store_true", help="HEAD each link (network)")
    p.set_defaults(fn=cmd_save)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except (LipError, cd.DriverError) as exc:
        print("FAIL: %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
