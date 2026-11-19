#!/usr/bin/env python3
"""chapter_driver.py: the conductor's bookkeeping for one job (or one chapter of a book). No network by default, no credits.

It composes the exact paid calls (keyframes, clips, retakes, speech) from `relay.json`, splits every call into a free
ESTIMATE (what you pass to `estimate_cost`) and the GENERATE call (saved to `calls/` before it is sent), and records what
came back (result links, generation ids, ledger rows) in `state.json`. It never talks to Frameo: you run the tools, it
holds the paperwork.

JOB is the job folder: the one that holds relay.json (for a book, `frameo-jobs/<book>/<chapter>/`). Files it keeps there:
  state.json   assets (lock id -> url, kind, label), supersedes, and the recorded results per kind (kf, clip, rkf, rclip, ...)
  calls/       <name>.draft.json (no quote ids) and <name>.json (quote ids merged, exactly what was sent)
  ledger.jsonl one row per charge (appended; read by relay_check.py ledger and book_check.py budget)
  speech_items.json, speech_gen.json, speech_urls.json    speech batching

Shots are numbered from 1 over the flattened segments of relay.json (chain order).

Usage:
  chapter_driver.py init JOB [--bible book/bible.json] [--assets assets.json]    # build state.json assets from locks + bible
  chapter_driver.py kf JOB A B            # EST + draft for keyframes of shots A..B   (--image-model, --image-resolution)
  chapter_driver.py clip JOB A B          # EST + draft for clips of shots A..B       (--video-model, --video-resolution, --max-refs)
  chapter_driver.py retake JOB 5,9 --lock "identity lock text"      # clips again from the existing keyframes
  chapter_driver.py rkf JOB 5,9 --spec retake_spec.json             # repair keyframes from scene-master frames
  chapter_driver.py rclip JOB 5,9 --spec retake_spec.json           # repair clips from the repair keyframes
  chapter_driver.py gen JOB NAME q1,q2,.. # merge quote ids into calls/NAME.draft.json -> calls/NAME.json, print it
  chapter_driver.py record JOB KIND 3=URL,4=URL [--verify]          # remember result links (bare ids are expanded)
  chapter_driver.py ledger JOB KIND 3=GEN,4=GEN --credits 18        # generation ids + ledger rows
  chapter_driver.py speech-items JOB [--language-code en-IN]        # dialogue lines -> speech_items.json
  chapter_driver.py speech-est JOB A B    # EST for items A..B (0-based slice), listing the real texts
  chapter_driver.py speech-gen JOB A id1,id2 [--credits 1]          # record generation ids for items A.. + ledger rows
  chapter_driver.py speech-urls JOB A < rows                        # rows "<link or id> <seconds>" (stdin) for items A..
  chapter_driver.py briefs JOB [--kind clip] [--prefix brief-]      # one review brief per finished clip

Run it as `python "$RELAY_HOME/skills/conductor/scripts/chapter_driver.py" ...`. Python 3.10+, stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request

# Frameo's content hosts as read from the live tools. Bare ids are expanded with these; override per job with a
# "prefixes" object in state.json ({"image": ..., "video": ..., "audio": ...}) if Frameo changes them.
DEFAULT_PREFIXES = {
    "image": "https://content.dashtoon.ai/stability-images/",
    "video": "https://content.dashtoon.ai/saved-videos/",
    "audio": "https://content.dashtoon.ai/studio-generated-audio/",
}
EXT = {"image": ".png", "video": ".mp4", "audio": ".mp3"}
LEDGER_KIND = {"kf": "keyframe", "clip": "clip", "rkf": "retake", "rclip": "retake"}
KIND_ORDER = {"character": 0, "location": 1, "prop": 2}
STATE_DICTS = ("assets", "kinds", "labels", "supersedes", "kf", "clip", "rkf", "rclip",
               "kf_gen", "clip_gen", "rkf_gen", "rclip_gen")
FLAT_PRICE_CHARS = 110  # speech up to this many characters is priced flat: estimate with a stub text
SPEECH_STUB = "x"


class DriverError(Exception):
    pass


# ---------------------------------------------------------------- files
def read_json(path, default=None):
    if not os.path.isfile(path):
        if default is not None:
            return default
        raise DriverError("missing file: " + path)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise DriverError("%s is not valid JSON: %s" % (path, exc))


def write_json(path, data, **kw):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, **kw)


def jp(job, *parts):
    return os.path.join(job, *parts)


def load_relay(job):
    if not os.path.isfile(jp(job, "relay.json")):
        raise DriverError("no relay.json in %s (pass the job folder)" % job)
    return read_json(jp(job, "relay.json"))


def shots_of(relay):
    return [s for c in relay.get("chains", []) for s in c.get("segments", [])]


def load_state(job):
    st = read_json(jp(job, "state.json"), default={})
    for k in STATE_DICTS:
        st.setdefault(k, {})
    return st


def save_state(job, st):
    write_json(jp(job, "state.json"), st, indent=1)


def prefixes(st):
    p = dict(DEFAULT_PREFIXES)
    p.update(st.get("prefixes") or {})
    return p


def full(st, u, media="image"):
    """A bare id becomes a link; a link stays as it is."""
    if u.startswith("http"):
        return u
    return prefixes(st)[media] + u + EXT[media]


def media_of_kind(kind):
    return "image" if kind in ("kf", "rkf") or kind.endswith("kf") else "video"


def shot_numbers(text, total):
    out = []
    for x in text.split(","):
        x = x.strip()
        if not x:
            continue
        n = int(x)
        if not 1 <= n <= total:
            raise DriverError("shot %d is outside 1..%d" % (n, total))
        out.append(n)
    if not out:
        raise DriverError("no shots given")
    return out


def pairs(text):
    out = {}
    for p in text.split(","):
        if p.strip():
            if "=" not in p:
                raise DriverError("expected N=value, got %r" % p)
            n, v = p.split("=", 1)
            out[str(int(n))] = v.strip()
    return out


def orientation(aspect):
    try:
        w, h = [float(x) for x in aspect.split(":")]
    except (ValueError, AttributeError):
        return "vertical"
    return "vertical" if w < h else ("horizontal" if w > h else "square")


# ---------------------------------------------------------------- assets (init)
BIBLE_SECTIONS = (("characters", "character"), ("locations", "location"), ("props", "prop"), ("styles", "style"))
URL_KEYS = ("images", "plates", "refs")


def first_url(entry):
    for k in URL_KEYS:
        v = entry.get(k)
        if isinstance(v, list):
            for u in v:
                if isinstance(u, str) and u.strip():
                    return u.strip()
    for k in ("url", "image", "image_url", "sheet"):
        if isinstance(entry.get(k), str) and entry[k].strip():
            return entry[k].strip()
    return None


def bible_index(bible):
    """'bible:<id>' -> (kind, entry, parent_entry_or_None) for entries and character variants."""
    idx = {}
    for sec, kind in BIBLE_SECTIONS:
        for it in (bible or {}).get(sec) or []:
            if not isinstance(it, dict) or not it.get("id"):
                continue
            idx["bible:" + it["id"]] = (kind, it, None)
            for v in it.get("variants") or []:
                if isinstance(v, dict) and v.get("id"):
                    idx["bible:" + v["id"]] = (kind, v, it)
    return idx


def label_for(kind, entry, parent):
    base = parent or entry
    name = base.get("name") or base.get("id")
    if kind == "character":
        state = (entry.get("state") or "").strip() if parent else ""
        return "the model sheet of %s%s" % (str(name).upper(), (" in " + state) if state else "")
    if kind == "location":
        return "the location plate of %s" % name
    if kind == "prop":
        return "the prop image of %s" % name
    return "the style still"


def build_assets(relay, bible, extra):
    """Returns (assets, kinds, labels, supersedes, missing). Sources, in order: `extra` (assets file), a lock's own
    url, the bible entry the lock points at with shared_from."""
    idx = bible_index(bible)
    items = [i for i in (relay.get("locks") or {}).get("items") or [] if isinstance(i, dict) and i.get("id")]
    ids = {i["id"] for i in items}
    by_shared = {i.get("shared_from"): i["id"] for i in items if i.get("shared_from")}
    assets, kinds, labels, sup, missing = {}, {}, {}, {}, []
    for lk in items:
        lid, lkind = lk["id"], lk.get("kind")
        if lkind == "voice" or lk.get("voice_only"):
            continue
        url = kind = label = None
        ex = extra.get(lid)
        if isinstance(ex, str):
            ex = {"url": ex}
        if isinstance(ex, dict):
            url, kind, label = ex.get("url"), ex.get("kind"), ex.get("label")
        ref = lk.get("shared_from")
        hit = idx.get(ref) if ref else None
        if not url and lk.get("url"):
            url = lk["url"]
        if not url and hit:
            url = first_url(hit[1])
        kind = kind or (hit[0] if hit else lkind) or "character"
        if not label:
            label = label_for(kind, hit[1], hit[2]) if hit else "the %s reference of %s" % (kind, lid)
        kinds[lid], labels[lid] = kind, label
        if url:
            assets[lid] = url
        else:
            missing.append(lid)
        vo = lk.get("variant_of")
        if vo:
            tail = vo.split(":", 1)[-1]
            base = by_shared.get(vo) or (tail if tail in ids else None)
            if base and base != lid:
                sup[lid] = base
    return assets, kinds, labels, sup, missing


def find_bible(job, relay):
    rel = (relay.get("series") or {}).get("bible")
    if not rel:
        return None
    d = os.path.abspath(job)
    for _ in range(6):  # series.bible is relative to the folder that holds book/ and frameo-jobs/
        if os.path.isfile(os.path.join(d, rel)):
            return os.path.join(d, rel)
        d = os.path.dirname(d)
    return None


def cmd_init(a):
    relay = load_relay(a.job)
    bpath = a.bible or find_bible(a.job, relay)
    bible = read_json(bpath) if bpath else {}
    extra = read_json(a.assets) if a.assets else {}
    assets, kinds, labels, sup, missing = build_assets(relay, bible, extra)
    st = load_state(a.job)
    st["assets"].update(assets)
    st["kinds"].update(kinds)
    st["labels"].update(labels)
    st["supersedes"].update(sup)
    save_state(a.job, st)
    print("assets %d of %d locks, supersedes %d, bible %s" % (len(assets), len(kinds), len(sup), bpath or "none"))
    if missing:
        print("missing (no image link in the bible or the assets file): " + ", ".join(missing))
        print('give them with --assets file.json  {"<lock id>": {"url": "...", "kind": "character", "label": "the model sheet of X"}}')
    return 1 if missing and a.strict else 0


# ---------------------------------------------------------------- call composition
def filter_refs(st, refs):
    """Drop a base sheet when one of its outfit variants is also referenced (stops outfit leakage)."""
    sup = st.get("supersedes", {})
    drop = {sup[x] for x in refs if x in sup}
    return [x for x in refs if x not in drop]


def ref_urls(st, refs):
    refs = filter_refs(st, refs)
    out, seen = [], set()
    for x in sorted(refs, key=lambda r: KIND_ORDER.get(st["kinds"].get(r), 3)):
        if x not in st["assets"]:
            continue
        u = full(st, st["assets"][x])
        if u not in seen:
            seen.add(u)
            out.append((u, st["labels"].get(x, x)))
    return out


def character_urls(st, refs, limit):
    urls = []
    for x in filter_refs(st, refs):
        if st["kinds"].get(x) == "character" and x in st["assets"]:
            u = full(st, st["assets"][x])
            if u not in urls:
                urls.append(u)
    return urls[:limit]


def short_labels(rs):
    return "; ".join("%d = %s" % (i + 1, lab.split(" (")[0]) for i, (u, lab) in enumerate(rs))


def kf_item(st, relay, seg, idx, model, resolution):
    rs = ref_urls(st, seg.get("refs_used") or [])
    aspect = relay["job"].get("aspect_ratio", "9:16")
    pre = ""
    if rs:
        pre = ("Reference images: %s. Keep each character's exact face, hair, build and outfit from its sheet, the place "
               "from its plate, the look from the style still. " % short_labels(rs))
    pre += "One %s still, the opening frame of this shot. " % orientation(aspect)
    return {"index": idx, "model": model, "resolution": resolution, "aspect_ratio": aspect,
            "image_urls": [u for u, _ in rs], "prompt": pre + (seg.get("keyframe_prompt") or seg["prompt"])}


def clip_item(st, relay, seg, idx, first_frame, model, resolution, max_refs, prompt=None):
    job = relay["job"]
    return {"index": idx, "model": model or job.get("model", "seedance_2_5"),
            "resolution": resolution or job.get("resolution", "720p"), "aspect_ratio": job.get("aspect_ratio", "9:16"),
            "duration": int(seg["duration_s"]), "first_frame_url": first_frame,
            "reference_image_urls": character_urls(st, seg.get("refs_used") or [], max_refs),
            "prompt": prompt if prompt is not None else seg["prompt"]}


def estimate_of(items, kind):
    est = []
    for it in items:
        e = {k: v for k, v in it.items() if k not in ("prompt", "index", "shot_number")}
        e["kind"] = kind
        e["prompt"] = "draft for pricing"
        est.append(e)
    return est


def need_frame(st, key, n):
    if str(n) not in st.get(key, {}):
        raise DriverError("shot %d has no recorded %r result yet (record it first)" % (n, key))
    return full(st, st[key][str(n)], media_of_kind(key))


def emit(job, name, items, kind):
    write_json(jp(job, "calls", name + ".draft.json"), items, ensure_ascii=True)
    print("EST=" + json.dumps(estimate_of(items, kind), separators=(",", ":")))
    print("draft: calls/%s.draft.json   next: gen %s <quote ids, one per item>" % (name, name))


def cmd_range(a):
    relay, st = load_relay(a.job), load_state(a.job)
    S = shots_of(relay)
    if not 1 <= a.a <= a.b <= len(S):
        raise DriverError("range %d..%d is outside 1..%d" % (a.a, a.b, len(S)))
    items = []
    for n in range(a.a, a.b + 1):
        s = S[n - 1]
        if a.cmd == "kf":
            items.append(kf_item(st, relay, s, n - a.a, a.image_model, a.image_resolution))
        else:
            items.append(clip_item(st, relay, s, n - a.a, need_frame(st, "kf", n), a.video_model, a.video_resolution, a.max_refs))
    emit(a.job, "%s_%d_%d" % (a.cmd, a.a, a.b), items, "image" if a.cmd == "kf" else "video")
    print("shots", [S[n - 1]["id"] for n in range(a.a, a.b + 1)], "seconds", [S[n - 1]["duration_s"] for n in range(a.a, a.b + 1)])
    return 0


def cmd_retake(a):
    """Clips again from the recorded keyframes, with an identity-lock sentence appended (the free-text lock is yours)."""
    relay, st = load_relay(a.job), load_state(a.job)
    S = shots_of(relay)
    shots = shot_numbers(a.shots, len(S))
    lock = open(a.lock_file, encoding="utf-8").read().strip() if a.lock_file else (a.lock or "")
    items = []
    for i, n in enumerate(shots):
        it = clip_item(st, relay, S[n - 1], i, need_frame(st, "kf", n), a.video_model, a.video_resolution, a.max_refs)
        it["prompt"] = " ".join(x for x in (it["prompt"], lock, a.extra or "") if x)
        it["shot_number"] = n
        items.append(it)
    emit(a.job, "retake_" + "_".join(map(str, shots)), items, "video")
    print("shots", shots, "seconds", [S[n - 1]["duration_s"] for n in shots])
    return 0


def scrub(text, replace=()):
    text = text.replace("�", "-")
    text = "".join(c if ord(c) < 0x2000 else "-" for c in text)
    for old, new in replace:
        text = text.replace(old, new)
    return text


def spec_for(spec, n):
    d = dict(spec.get("defaults") or {})
    d.update((spec.get("shots") or {}).get(str(n)) or {})
    return d


def master_urls(spec, sp):
    m = sp.get("master") or []
    if isinstance(m, str):
        m = (spec.get("masters") or {}).get(m)
        if m is None:
            raise DriverError("master %r is not in the spec's masters" % sp.get("master"))
    return [m] if isinstance(m, str) else list(m)


def cmd_rkf(a):
    """Repair keyframes: model sheets + scene-master frames + style still, a short prompt and a lock line per shot."""
    relay, st = load_relay(a.job), load_state(a.job)
    spec = read_json(a.spec)
    S = shots_of(relay)
    shots = shot_numbers(a.shots, len(S))
    aspect = relay["job"].get("aspect_ratio", "9:16")
    style_ids = (relay.get("style") or {}).get("reference_lock_ids") or []
    items = []
    for n in shots:
        s, sp = S[n - 1], spec_for(spec, n)
        urls, labs = [], []
        for k in filter_refs(st, s.get("refs_used") or []):
            if st["kinds"].get(k) == "character" and k in st["assets"]:
                u = full(st, st["assets"][k])
                if u not in urls:
                    urls.append(u)
                    labs.append("the model sheet of %s" % k.upper().replace("-", " "))
        for mu in master_urls(spec, sp):
            urls.append(mu)
            labs.append("the SCENE MASTER (same room, outfits, props, light)")
        for k in style_ids:
            if k in st["assets"] and full(st, st["assets"][k]) not in urls:
                urls.append(full(st, st["assets"][k]))
                labs.append("the style still")
        kp = s.get("keyframe_prompt") or s["prompt"]
        still = sp.get("still")
        if not still and spec.get("still_regex"):
            m = re.search(spec["still_regex"], kp, re.S)
            still = (m.group(1) if m.groups() else m.group(0)).strip() if m else None
        still = still or kp
        pre = ("Reference images: " + "; ".join("%d = %s" % (i + 1, l) for i, l in enumerate(labs)) + ". ") if labs else ""
        prompt = (pre + "Make one %s still, the opening frame of this shot, in the SAME room with the SAME outfits, props and light "
                  "as the scene master frame; keep each face exactly as on its sheet and master. " % orientation(aspect)
                  + (sp.get("keyframe_lock") or "") + " Shot: " + still + ". " + (spec.get("keyframe_tail") or "")).strip()
        items.append({"index": len(items), "model": a.image_model, "resolution": a.image_resolution, "aspect_ratio": aspect,
                      "image_urls": urls, "prompt": prompt, "shot_number": n})
    emit(a.job, "rkf_" + "_".join(map(str, shots)), items, "image")
    return 0


def cmd_rclip(a):
    """Repair clips: the repair keyframe as first frame, the shot's action text plus a lock line."""
    relay, st = load_relay(a.job), load_state(a.job)
    spec = read_json(a.spec)
    S = shots_of(relay)
    shots = shot_numbers(a.shots, len(S))
    items = []
    for n in shots:
        s, sp = S[n - 1], spec_for(spec, n)
        p = s["prompt"]
        act = sp.get("action")
        if not act and spec.get("action_regex"):
            m = re.search(spec["action_regex"], p, re.S)
            act = m.group(0) if m else None
        act = scrub(act or p, [tuple(x) for x in (sp.get("replace") or spec.get("replace") or [])])
        prompt = " ".join(x for x in (act, sp.get("clip_lock") or "", spec.get("clip_tail") or "") if x)
        it = clip_item(st, relay, s, len(items), need_frame(st, "rkf", n), a.video_model, a.video_resolution, a.max_refs, prompt)
        it["shot_number"] = n
        items.append(it)
    emit(a.job, "rclip_" + "_".join(map(str, shots)), items, "video")
    print("shots", shots, "seconds", sum(i["duration"] for i in items))
    return 0


def cmd_gen(a):
    path = jp(a.job, "calls", a.name + ".draft.json")
    items = read_json(path)
    qs = [q for q in a.quotes.split(",") if q]
    if len(qs) != len(items):
        raise DriverError("%d quote ids for %d items: a quote is bound to its exact items" % (len(qs), len(items)))
    for it, q in zip(items, qs):
        it["quote_id"] = q
        it.pop("shot_number", None)
    write_json(jp(a.job, "calls", a.name + ".json"), items, ensure_ascii=True)
    print(json.dumps(items, ensure_ascii=False))
    return 0


# ---------------------------------------------------------------- recording
def head_ok(url):
    try:
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status == 200
    except Exception:
        return False


def cmd_record(a):
    relay, st = load_relay(a.job), load_state(a.job)
    S = shots_of(relay)
    st.setdefault(a.kind, {})
    bad = []
    for n, v in pairs(a.pairs).items():
        if not 1 <= int(n) <= len(S):
            raise DriverError("shot %s is outside 1..%d" % (n, len(S)))
        url = full(st, v, media_of_kind(a.kind))
        if a.verify and not head_ok(url):
            bad.append(n)
        st[a.kind][n] = url
    save_state(a.job, st)
    print("recorded %d %s, unreachable %s" % (len(st[a.kind]), a.kind, bad))
    if a.kind in ("kf", "clip"):
        missing = [str(i) for i in range(1, len(S) + 1) if str(i) not in st[a.kind]]
        print("missing shots (%d): %s" % (len(missing), ",".join(missing)))
    return 1 if bad else 0


def ledger_row(job, kind, segment, credits, gen):
    c = float(credits)
    row = {"kind": kind, "segment": segment, "credits_charged": int(c) if c == int(c) else c,
           "generation_id": gen, "refunded": False}
    with open(jp(job, "ledger.jsonl"), "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(row) + "\n")


def credit_list(text, n):
    cr = [c for c in text.split(",") if c]
    if len(cr) == 1:
        cr = cr * n
    if len(cr) != n:
        raise DriverError("%d credit values for %d generations" % (len(cr), n))
    return cr


def cmd_ledger(a):
    relay, st = load_relay(a.job), load_state(a.job)
    S = shots_of(relay)
    gens = pairs(a.pairs)
    cr = credit_list(a.credits, len(gens))
    key = a.kind + "_gen"
    st.setdefault(key, {})
    for (n, g), c in zip(gens.items(), cr):
        if not 1 <= int(n) <= len(S):
            raise DriverError("shot %s is outside 1..%d" % (n, len(S)))
        st[key][n] = g
        ledger_row(a.job, LEDGER_KIND.get(a.kind) or a.ledger_kind or "clip", S[int(n) - 1]["id"], c, g)
    save_state(a.job, st)
    print("recorded %d generation ids and ledger rows" % len(gens))
    return 0


# ---------------------------------------------------------------- speech
def clean_text(t):
    return t.replace("�", ", ").replace(" ,", ",").strip()


def cmd_speech_items(a):
    relay = load_relay(a.job)
    S = shots_of(relay)
    idx = {s["id"]: i + 1 for i, s in enumerate(S)}
    voices = {i["id"]: i["voice_id"] for i in relay["locks"]["items"] if i.get("voice_id")}
    items, by = [], {}
    for ln in (relay.get("dialogue") or {}).get("lines", []):
        if ln["speaker"] not in voices:
            raise DriverError("line %s: speaker %r has no voice_id lock" % (ln["id"], ln["speaker"]))
        it = {"id": ln["id"], "voice_id": voices[ln["speaker"]], "text": clean_text(ln["text"]), "speaker": ln["speaker"]}
        lc = ln.get("language_code") or a.language_code
        if lc:
            it["language_code"] = lc
        items.append(it)
        by.setdefault(str(idx[ln["segment"]]), []).append(ln["id"])
    write_json(jp(a.job, "speech_items.json"), items, ensure_ascii=False)
    write_json(jp(a.job, "lines_by_shot.json"), by)
    print("%d lines; shots with lines %d" % (len(items), len(by)))
    return 0


def load_items(job):
    return read_json(jp(job, "speech_items.json"))


def cmd_speech_est(a):
    sl = load_items(a.job)[a.a:a.b]
    est = []
    for x in sl:
        e = {"kind": "speech", "voice_id": x["voice_id"],
             "text": x["text"] if len(x["text"]) > FLAT_PRICE_CHARS else SPEECH_STUB}
        if x.get("language_code"):
            e["language_code"] = x["language_code"]
        est.append(e)
    print("EST=" + json.dumps(est, separators=(",", ":")))
    for k, x in enumerate(sl):
        print(a.a + k, x["id"], x["voice_id"], "|", x["text"])
    return 0


def cmd_speech_gen(a):
    items = load_items(a.job)
    gp = jp(a.job, "speech_gen.json")
    g = read_json(gp, default={})
    ids = [i for i in a.ids.split(",") if i]
    cr = credit_list(a.credits, len(ids))
    if a.a + len(ids) > len(items):
        raise DriverError("items %d..%d are past the %d speech items" % (a.a, a.a + len(ids), len(items)))
    for k, (i, c) in enumerate(zip(ids, cr)):
        lid = items[a.a + k]["id"]
        g[lid] = i
        ledger_row(a.job, "speech", lid, c, i)
    write_json(gp, g)
    print(len(g), "speech generations recorded")
    return 0


def cmd_speech_urls(a):
    items = load_items(a.job)
    text = open(a.rows_file, encoding="utf-8").read() if a.rows_file else sys.stdin.read()
    rows = [r.split() for r in text.splitlines() if r.strip()]
    up = jp(a.job, "speech_urls.json")
    d = read_json(up, default={})
    st = load_state(a.job)
    for k, row in enumerate(rows):
        if len(row) != 2:
            raise DriverError("row %d: expected '<link or id> <seconds>', got %r" % (k + 1, " ".join(row)))
        if a.a + k >= len(items):
            raise DriverError("row %d is past the %d speech items" % (k + 1, len(items)))
        d[items[a.a + k]["id"]] = {"url": full(st, row[0], "audio"), "dur": float(row[1])}
    write_json(up, d)
    print(len(d), "speech links known;", len(rows), "added")
    return 0


# ---------------------------------------------------------------- review briefs
def cmd_briefs(a):
    relay, st = load_relay(a.job), load_state(a.job)
    S = shots_of(relay)
    fin = read_json(jp(a.job, "final_clips.json"), default={})
    ceiling = ((relay.get("style") or {}).get("avoid") or [""])[0]
    os.makedirs(jp(a.job, "reviews"), exist_ok=True)
    count = 0
    for n, s in enumerate(S, 1):
        clip = fin.get(str(n)) or st.get(a.kind, {}).get(str(n))
        if not clip:
            continue
        names = [r.upper().replace("-", " ") for r in filter_refs(st, s.get("refs_used") or []) if st["kinds"].get(r) == "character"]
        kf = st["kf"].get(str(n), "")
        kf = full(st, kf) if kf else "(none recorded)"
        dur = s["duration_s"]
        ts = sorted({0.4, round(dur * 0.3, 1), round(dur * 0.6, 1), round(dur - 0.5, 1)})
        txt = ("# Review brief: shot %d (segment %s), planned %s s, silent clip\nClip: %s\nOpening keyframe: %s\nOn screen: %s\n"
               "Content ceiling for this job: %s\nPlanned action:\n%s\n\n"
               "Check with view_image(media_url=<clip>, at_seconds=...) at about these seconds: %s. "
               "Also view the keyframe once if a face or outfit looks wrong.\n"
               % (n, s["id"], dur, clip, kf, ", ".join(names) or "no characters", ceiling, s["prompt"][:1500], ts))
        with open(jp(a.job, "reviews", "%s%02d.md" % (a.prefix, n)), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(txt)
        count += 1
    print("briefs written:", count)
    return 0


# ---------------------------------------------------------------- cli
def build_parser():
    ap = argparse.ArgumentParser(description="Conductor bookkeeping for one job: compose calls, record results.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def models(p):
        p.add_argument("--image-model", default="nano-banana-pro")
        p.add_argument("--image-resolution", default="2K")
        p.add_argument("--video-model", default=None, help="default: job.model")
        p.add_argument("--video-resolution", default=None, help="default: job.resolution")
        p.add_argument("--max-refs", type=int, default=3, help="character sheets passed to a clip")

    p = sub.add_parser("init")
    p.add_argument("job")
    p.add_argument("--bible", help="book/bible.json (default: found through relay.json series.bible)")
    p.add_argument("--assets", help='JSON {"<lock id>": {"url","kind","label"}} for locks the bible does not cover')
    p.add_argument("--strict", action="store_true", help="exit 1 when a lock has no image link")
    p.set_defaults(fn=cmd_init)
    for name in ("kf", "clip"):
        p = sub.add_parser(name)
        p.add_argument("job")
        p.add_argument("a", type=int)
        p.add_argument("b", type=int)
        models(p)
        p.set_defaults(fn=cmd_range)
    p = sub.add_parser("retake")
    p.add_argument("job")
    p.add_argument("shots", help="comma list of shot numbers")
    p.add_argument("--lock", help="identity-lock sentence appended to each prompt")
    p.add_argument("--lock-file")
    p.add_argument("--extra", help="one more sentence appended")
    models(p)
    p.set_defaults(fn=cmd_retake)
    for name, fn in (("rkf", cmd_rkf), ("rclip", cmd_rclip)):
        p = sub.add_parser(name)
        p.add_argument("job")
        p.add_argument("shots")
        p.add_argument("--spec", required=True, help="retake spec JSON (see book-production-scripts.md)")
        models(p)
        p.set_defaults(fn=fn)
    p = sub.add_parser("gen")
    p.add_argument("job")
    p.add_argument("name", help="draft name, e.g. kf_1_6 or rclip_5_9")
    p.add_argument("quotes", help="comma list of quote ids, one per item, in order")
    p.set_defaults(fn=cmd_gen)
    p = sub.add_parser("record")
    p.add_argument("job")
    p.add_argument("kind", help="state key: kf, clip, rkf, rclip or your own (e.g. gclip)")
    p.add_argument("pairs", help="N=link-or-id,N=link-or-id")
    p.add_argument("--verify", action="store_true", help="HEAD each link (network)")
    p.set_defaults(fn=cmd_record)
    p = sub.add_parser("ledger")
    p.add_argument("job")
    p.add_argument("kind")
    p.add_argument("pairs", help="N=generation_id,...")
    p.add_argument("--credits", required=True, help="credits per generation (one value or one per id)")
    p.add_argument("--ledger-kind", help="ledger kind for a custom state key (default clip)")
    p.set_defaults(fn=cmd_ledger)
    p = sub.add_parser("speech-items")
    p.add_argument("job")
    p.add_argument("--language-code", help="e.g. en-IN, added to every item that has no language_code of its own")
    p.set_defaults(fn=cmd_speech_items)
    p = sub.add_parser("speech-est")
    p.add_argument("job")
    p.add_argument("a", type=int)
    p.add_argument("b", type=int)
    p.set_defaults(fn=cmd_speech_est)
    p = sub.add_parser("speech-gen")
    p.add_argument("job")
    p.add_argument("a", type=int)
    p.add_argument("ids")
    p.add_argument("--credits", default="1", help="credits per line (speech is 1 to 3 by length)")
    p.set_defaults(fn=cmd_speech_gen)
    p = sub.add_parser("speech-urls")
    p.add_argument("job")
    p.add_argument("a", type=int)
    p.add_argument("--rows-file", help="read rows from a file instead of stdin")
    p.set_defaults(fn=cmd_speech_urls)
    p = sub.add_parser("briefs")
    p.add_argument("job")
    p.add_argument("--kind", default="clip", help="state key of the clips to brief")
    p.add_argument("--prefix", default="brief-")
    p.set_defaults(fn=cmd_briefs)
    return ap


def main(argv=None):
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except DriverError as exc:
        print("FAIL: %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
