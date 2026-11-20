#!/usr/bin/env python3
"""relay_check.py -- mechanical checks for a frameorelay job contract (relay.json).

Standard library only, no network, no Frameo calls. It proves STRUCTURE and
IDENTITY (ids, hashes of the locked fields, chain order, budget arithmetic,
prompt sealing). It can NOT prove a join looks right or that a media id really
exists in Frameo: the conductor checks those with Frameo's own tools and a
vision review. See README.md "What the validator does not prove".

Exit codes: 0 ok, 1 a check failed, 2 usage or unreadable input.

Commands
  validate <relay.json> [--scratch]      full structural check (scratch = a draft
                                         before approval: approval/lock fields
                                         are not required)
  lock <relay.json>                      freeze locks+style, write the fingerprint
  verify-locks <relay.json>              locks+style unchanged since `lock`
  check-chains <relay.json>              chain / segment structure and continuity
  check-style <relay.json>               style anchor in every prompt
  check-dialogue <relay.json> [--allow-unapproved]
  check-ready <relay.json> <segment-id> [--workspace-id ID]
                                         gate before any paid call for a segment
  check-result <relay.json> <segment-id>
  ledger <relay.json>                    spend so far vs the approved total
  snapshot <jobdir>                      hash every job file (before a subagent step)
  verify-snapshot <jobdir> [--allow GLOB ...]
                                         fail if any file outside GLOB changed
  manifest <relay.json>                  ordered clip list (only when all done+passed)
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import sys

MAX_SEGMENT_SECONDS = 30
DEFAULT_WORDS_PER_SECOND = 2.5
MAX_ANCHOR_WORDS = 80
SNAPSHOT_NAME = ".relay-snapshot.json"

LOCK_KINDS = {"character", "location", "prop", "style", "voice"}
JOIN_MOTION = {"low", "mid", "high"}
SEGMENT_STATUS = {"draft", "ready", "generating", "done", "failed"}
DIALOGUE_MODES = {"as_written", "fill_gaps", "full_creative"}
LINE_SOURCES = {"script", "generated"}
# Seedance guide: every prompt must be sealed, the model never saw the others.
UNSEALED = re.compile(
    r"\b(previous|as before|earlier shot|last shot|same as (the )?(last|previous))\b"
    r"|\bshot\s*#?\d+\b",
    re.IGNORECASE,
)


class Report:
    def __init__(self) -> None:
        self.fails: list[str] = []
        self.warns: list[str] = []
        self.infos: list[str] = []

    def fail(self, msg: str) -> None:
        self.fails.append(msg)

    def warn(self, msg: str) -> None:
        self.warns.append(msg)

    def info(self, msg: str) -> None:
        self.infos.append(msg)

    def merge(self, other: "Report") -> None:
        self.fails += other.fails
        self.warns += other.warns
        self.infos += other.infos

    def emit(self) -> int:
        for m in self.infos:
            print(f"INFO: {m}")
        for m in self.warns:
            print(f"WARN: {m}")
        for m in self.fails:
            print(f"FAIL: {m}")
        if self.fails:
            print(f"{len(self.fails)} check(s) failed")
            return 1
        print("OK")
        return 0


# ---------------------------------------------------------------- helpers

def load(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read {path}: {exc}")
        sys.exit(2)
    if not isinstance(data, dict):
        print(f"FAIL: {path} must hold a JSON object")
        sys.exit(2)
    return data


def segments(d: dict):
    """Yield (chain, index_in_chain, segment) in chain then segment order."""
    for chain in d.get("chains") or []:
        for i, seg in enumerate(chain.get("segments") or []):
            yield chain, i, seg


def find_segment(d: dict, seg_id: str):
    for chain, i, seg in segments(d):
        if seg.get("id") == seg_id:
            return chain, i, seg
    return None


def lock_items(d: dict) -> list[dict]:
    return (d.get("locks") or {}).get("items") or []


def fingerprint(d: dict) -> str:
    payload = {"items": lock_items(d), "style": d.get("style") or {}}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def is_nonempty_str(v) -> bool:
    return isinstance(v, str) and v.strip() != ""


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def read_ledger(jobdir: str) -> list[dict]:
    path = os.path.join(jobdir, "ledger.jsonl")
    rows: list[dict] = []
    if not os.path.exists(path):
        return rows
    with open(path, "r", encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                raise ValueError(f"ledger.jsonl line {n} is not valid JSON")
    return rows


# ------------------------------------------------------------ the checks

def check_structure(d: dict, scratch: bool) -> Report:
    r = Report()
    if d.get("version") != 1:
        r.fail("version must be 1")
    job = d.get("job")
    if not isinstance(job, dict):
        r.fail("job object missing")
        return r
    for key in ("id", "workspace_id", "aspect_ratio", "model"):
        if not is_nonempty_str(job.get(key)):
            (r.warn if scratch and key == "workspace_id" else r.fail)(f"job.{key} missing")
    frameo = job.get("frameo") or {}
    if not scratch:
        for key in ("project_id", "module_id"):
            if not is_nonempty_str(frameo.get(key)):
                r.fail(f"job.frameo.{key} missing")
    if not isinstance(job.get("limits"), dict) or not (job.get("limits") or {}).get("models"):
        r.warn("job.limits.models missing: model limits cannot be checked (copy them from list_models)")

    # approval and locks
    approval = d.get("approval") or {}
    total = approval.get("approved_total_credits")
    if not scratch:
        if not isinstance(total, (int, float)) or total <= 0:
            r.fail("approval.approved_total_credits must be a positive number")
        if not is_nonempty_str(approval.get("approved_at")):
            r.fail("approval.approved_at missing: nothing may be generated before approval")
    pct = approval.get("retake_allowance_pct", 15)
    if not isinstance(pct, (int, float)) or pct < 0:
        r.fail("approval.retake_allowance_pct must be a number >= 0")

    ids: set[str] = set()
    for item in lock_items(d):
        iid = item.get("id")
        if not is_nonempty_str(iid):
            r.fail("a lock has no id")
            continue
        if iid in ids:
            r.fail(f"duplicate lock id {iid}")
        ids.add(iid)
        if item.get("kind") not in LOCK_KINDS:
            r.fail(f"lock {iid}: kind must be one of {sorted(LOCK_KINDS)}")
        if item.get("kind") == "voice":
            if not is_nonempty_str(item.get("voice_id")):
                (r.warn if scratch else r.fail)(f"lock {iid}: voice lock needs voice_id")
        elif item.get("voice_only") is True:
            # a narrator that never appears on screen: needs a voice_id, never an image
            if not is_nonempty_str(item.get("voice_id")):
                (r.warn if scratch else r.fail)(f"lock {iid}: voice-only character needs voice_id")
        elif not is_nonempty_str(item.get("media_id")):
            (r.warn if scratch else r.fail)(f"lock {iid}: no media_id yet")

    r.merge(check_series(d, scratch=scratch))
    r.merge(check_chains(d, scratch=scratch))
    r.merge(check_style(d, scratch=scratch))
    r.merge(check_dialogue(d, require_approved=not scratch))
    return r


SHARED_RE = re.compile(r"^bible:[a-z0-9][a-z0-9_-]*$")


def check_series(d: dict, scratch: bool) -> Report:
    """Optional `series` block for a chapter of a book (see skills/book-breakdown). Absent means a normal single job."""
    r = Report()
    ser = d.get("series")
    items = lock_items(d)
    if ser is None:
        for item in items:
            if "shared_from" in item or "variant_of" in item:
                r.warn(f"lock {item.get('id')}: shared_from/variant_of only make sense with a `series` block")
        return r
    if not isinstance(ser, dict):
        r.fail("series must be an object")
        return r
    for key in ("book_id", "chapter_id", "bible"):
        if not is_nonempty_str(ser.get(key)):
            r.fail(f"series.{key} missing")
    no = ser.get("chapter_no")
    if not isinstance(no, int) or isinstance(no, bool) or no < 1:
        r.fail("series.chapter_no must be an integer >= 1")
    frameo = (d.get("job") or {}).get("frameo") or {}
    bible_mod = ser.get("bible_module_id")
    if is_nonempty_str(bible_mod) and bible_mod == frameo.get("module_id"):
        r.fail("a chapter job must not use the Series Bible module: every chapter takes its own module")
    if not scratch and not is_nonempty_str(frameo.get("module_id")):
        r.fail("a chapter job needs its own job.frameo.module_id")
    for item in items:
        for key in ("shared_from", "variant_of"):
            v = item.get(key)
            if v is not None and not (isinstance(v, str) and SHARED_RE.match(v)):
                r.fail(f"lock {item.get('id')}: {key} must look like 'bible:<id>', got {v!r}")
    return r


def check_chains(d: dict, scratch: bool = False) -> Report:
    r = Report()
    chains = d.get("chains")
    if not isinstance(chains, list) or not chains:
        r.fail("chains must be a non-empty list")
        return r
    limits_models = ((d.get("job") or {}).get("limits") or {}).get("models") or {}
    model = (d.get("job") or {}).get("model")
    mlim = limits_models.get(model) or {}
    secs_range = mlim.get("seconds")
    chain_ids: set[str] = set()
    seg_ids: set[str] = set()
    scene_seen: dict[str, str] = {}
    lock_ids = {i.get("id") for i in lock_items(d)}

    for chain in chains:
        cid = chain.get("id")
        if not is_nonempty_str(cid):
            r.fail("a chain has no id")
            continue
        if cid in chain_ids:
            r.fail(f"duplicate chain id {cid}")
        chain_ids.add(cid)
        scene_ids = chain.get("scene_ids") or []
        if not scene_ids:
            r.fail(f"chain {cid}: scene_ids empty")
        for sc in scene_ids:
            if sc in scene_seen:
                r.fail(f"scene {sc} is in chains {scene_seen[sc]} and {cid}")
            scene_seen[sc] = cid
        segs = chain.get("segments") or []
        if not segs:
            r.fail(f"chain {cid}: no segments")
            continue
        covered: list[str] = []
        prev = None
        for i, seg in enumerate(segs):
            sid = seg.get("id")
            if not is_nonempty_str(sid):
                r.fail(f"chain {cid}: segment {i} has no id")
                continue
            if sid in seg_ids:
                r.fail(f"duplicate segment id {sid}")
            seg_ids.add(sid)
            dur = seg.get("duration_s")
            if not isinstance(dur, int) or isinstance(dur, bool):
                r.fail(f"segment {sid}: duration_s must be a whole number of seconds")
            else:
                if dur > MAX_SEGMENT_SECONDS:
                    r.fail(f"segment {sid}: {dur}s is over the {MAX_SEGMENT_SECONDS}s clip limit; split the chain")
                if dur < 1:
                    r.fail(f"segment {sid}: duration_s must be at least 1")
                if isinstance(secs_range, list) and len(secs_range) == 2 and not (secs_range[0] <= dur <= secs_range[1]):
                    r.fail(f"segment {sid}: {dur}s outside {model}'s {secs_range[0]}-{secs_range[1]}s")
            if seg.get("status") not in SEGMENT_STATUS:
                r.fail(f"segment {sid}: status must be one of {sorted(SEGMENT_STATUS)}")
            if seg.get("join_motion") not in JOIN_MOTION:
                r.fail(f"segment {sid}: join_motion must be low, mid or high")
            for ref in seg.get("refs_used") or []:
                if ref not in lock_ids:
                    r.fail(f"segment {sid}: refs_used {ref} is not a lock")
            covered += seg.get("scene_ids") or []
            ff = seg.get("first_frame") or {}
            if ff.get("source") not in ("keyframe", "extract"):
                r.fail(f"segment {sid}: first_frame.source must be 'keyframe' or 'extract' (an end_target never counts as continuity)")
            if i == 0:
                if ff.get("source") != "keyframe":
                    r.fail(f"segment {sid}: the first segment of a chain opens on a keyframe")
            else:
                if ff.get("source") != "extract":
                    r.fail(f"segment {sid}: a continuing segment must open on the extracted real last frame of {prev.get('id')}")
                elif ff.get("from_segment") != prev.get("id"):
                    r.fail(f"segment {sid}: first_frame.from_segment must be {prev.get('id')}")
                else:
                    prev_last = (prev.get("result") or {}).get("last_frame_media_id")
                    if prev_last and ff.get("media_id") != prev_last:
                        r.fail(
                            f"segment {sid}: first frame {ff.get('media_id')} is not the extracted last frame {prev_last} of {prev.get('id')}"
                        )
            if not scratch and seg.get("status") in ("ready", "generating", "done") and not is_nonempty_str(ff.get("media_id")):
                r.fail(f"segment {sid}: first_frame.media_id missing")
            prev = seg
        if covered != scene_ids:
            r.fail(f"chain {cid}: segments cover scenes {covered}, chain lists {scene_ids} (same scenes, same order)")
    r.merge(check_continuity_groups(d))
    return r


def check_continuity_groups(d: dict) -> Report:
    """Warn when consecutive chains share a place lock and nothing says the story breaks between them.

    A chain is a continuity group: shots of one place and unbroken time render one after another, each opening on
    the real extracted last frame of the one before (and are reviewed before the next starts), while groups that
    are really separate (new place, a time jump, a cutaway) fan out in parallel. A chapter planned as one chain per
    shot loses that carry-over (faces, clothes, props drift), so adjacent chains in the same place must either be
    merged or carry a `break_reason`.
    """
    r = Report()
    chains = d.get("chains") or []
    kinds = {i.get("id"): i.get("kind") for i in ((d.get("locks") or {}).get("items") or [])}

    def places(chain: dict) -> frozenset:
        found = set()
        for seg in chain.get("segments") or []:
            for ref in seg.get("refs_used") or []:
                if kinds.get(ref) == "location":
                    found.add(ref)
        return frozenset(found)

    for prev, cur in zip(chains, chains[1:]):
        shared = places(prev) & places(cur)
        if shared and not is_nonempty_str(cur.get("break_reason")):
            r.warn(
                f"chains {prev.get('id')} and {cur.get('id')} both use place lock(s) {', '.join(sorted(shared))} with no break_reason: "
                "merge them into one chain (sequential, each shot opens on the extracted last frame of the one before) "
                "or set chain.break_reason (new place, time jump, cutaway)"
            )
    return r


def check_style(d: dict, scratch: bool = False) -> Report:
    r = Report()
    style = d.get("style")
    if not isinstance(style, dict):
        r.fail("style missing (set style.none = true to render with no style direction)")
        return r
    if style.get("none") is True:
        r.info("style.none is set: no style direction enforced")
        return r
    anchor = style.get("anchor")
    if not is_nonempty_str(anchor):
        (r.warn if scratch else r.fail)("style.anchor missing")
        return r
    n = word_count(anchor)
    if n > MAX_ANCHOR_WORDS:
        r.fail(f"style.anchor is {n} words; keep it under {MAX_ANCHOR_WORDS}")
    lock_ids = {i.get("id") for i in lock_items(d)}
    ref_ids = style.get("reference_lock_ids") or []
    for ref in ref_ids:
        if ref not in lock_ids:
            r.fail(f"style.reference_lock_ids {ref} is not a lock")
    for _, _, seg in segments(d):
        sid = seg.get("id")
        if anchor not in (seg.get("prompt") or ""):
            r.fail(f"segment {sid}: prompt does not contain style.anchor verbatim")
        missing = [x for x in ref_ids if x not in (seg.get("refs_used") or [])]
        if missing:
            r.fail(f"segment {sid}: refs_used lacks the style reference(s) {missing}")
        kf = seg.get("keyframe_prompt")
        if kf is not None and anchor not in kf:
            r.fail(f"segment {sid}: keyframe_prompt does not contain style.anchor verbatim")
    return r


def check_dialogue(d: dict, require_approved: bool = True) -> Report:
    r = Report()
    dia = d.get("dialogue")
    if dia is None:
        r.info("no dialogue block")
        return r
    if dia.get("mode") not in DIALOGUE_MODES:
        r.fail(f"dialogue.mode must be one of {sorted(DIALOGUE_MODES)}")
    wps = dia.get("max_words_per_second", DEFAULT_WORDS_PER_SECOND)
    if not isinstance(wps, (int, float)) or wps <= 0:
        r.fail("dialogue.max_words_per_second must be > 0")
        wps = DEFAULT_WORDS_PER_SECOND
    # a speaker is a character lock, or a bare voice lock (a narrator who is never on screen)
    voices = {i.get("id"): i for i in lock_items(d) if i.get("kind") == "voice"}
    chars = {i.get("id"): i for i in lock_items(d) if i.get("kind") in ("character", "voice")}
    seg_words: dict[str, int] = {}
    line_ids: set[str] = set()
    for line in dia.get("lines") or []:
        lid = line.get("id")
        if not is_nonempty_str(lid) or lid in line_ids:
            r.fail(f"dialogue line id missing or duplicate: {lid!r}")
        line_ids.add(lid)
        seg = find_segment(d, line.get("segment"))
        if seg is None:
            r.fail(f"line {lid}: segment {line.get('segment')!r} does not exist")
            continue
        if line.get("source") not in LINE_SOURCES:
            r.fail(f"line {lid}: source must be 'script' or 'generated'")
        if not is_nonempty_str(line.get("text")):
            r.fail(f"line {lid}: empty text")
        speaker = line.get("speaker")
        if speaker not in chars:
            r.fail(f"line {lid}: speaker {speaker!r} is not a character lock")
        else:
            vlock = chars[speaker].get("voice_lock_id")
            voice_id = chars[speaker].get("voice_id") or (voices.get(vlock) or {}).get("voice_id")
            if not is_nonempty_str(voice_id):
                r.fail(f"line {lid}: speaker {speaker} has no locked voice_id")
        if line.get("source") == "generated":
            r.info(f"line {lid} ({line.get('segment')}) is GENERATED, review it: {line.get('text')!r}")
        if require_approved and line.get("approved") is not True:
            r.fail(f"line {lid}: not approved; nothing is spoken, voiced or lipsynced until the owner approves it")
        seg_words[line["segment"]] = seg_words.get(line["segment"], 0) + word_count(line.get("text", ""))
    for sid, words in seg_words.items():
        seg = find_segment(d, sid)[2]
        dur = seg.get("duration_s")
        if isinstance(dur, int) and dur > 0 and words > dur * wps:
            r.fail(f"segment {sid}: {words} spoken words will not fit {dur}s at {wps} words/second")
    return r


def check_locks(d: dict) -> Report:
    r = Report()
    locks = d.get("locks") or {}
    if not is_nonempty_str(locks.get("locked_at")) or not is_nonempty_str(locks.get("fingerprint")):
        r.fail("locks are not frozen: run `lock` after the owner approves references and style")
    elif locks["fingerprint"] != fingerprint(d):
        r.fail("locks or style changed after they were frozen (fingerprint mismatch)")
    return r


def spent_so_far(jobdir: str) -> float:
    total = 0.0
    for row in read_ledger(jobdir):
        if row.get("refunded") is True:
            continue
        total += float(row.get("credits_charged") or 0)
    return total


def check_ready(d: dict, seg_id: str, jobdir: str, workspace_id: str | None) -> Report:
    r = Report()
    found = find_segment(d, seg_id)
    if found is None:
        r.fail(f"segment {seg_id} does not exist")
        return r
    chain, idx, seg = found
    job = d.get("job") or {}
    if workspace_id is not None and workspace_id != job.get("workspace_id"):
        r.fail(f"workspace is {workspace_id} but the job is pinned to {job.get('workspace_id')}")
    approval = d.get("approval") or {}
    if not is_nonempty_str(approval.get("approved_at")):
        r.fail("no approval recorded: nothing may be generated")
    r.merge(check_locks(d))
    r.merge(check_style(d))
    r.merge(check_dialogue(d, require_approved=True))
    r.merge(check_chains(d))

    prompt = seg.get("prompt")
    if not is_nonempty_str(prompt):
        r.fail(f"segment {seg_id}: prompt missing")
    elif UNSEALED.search(prompt):
        r.fail(f"segment {seg_id}: prompt is not sealed (mentions previous/as before/a shot number); the model never saw other clips")
    ff = seg.get("first_frame") or {}
    if not is_nonempty_str(ff.get("media_id")):
        r.fail(f"segment {seg_id}: first frame media_id missing")
    for item in lock_items(d):
        if (item.get("id") in (seg.get("refs_used") or []) and item.get("kind") != "voice"
                and item.get("voice_only") is not True and not is_nonempty_str(item.get("media_id"))):
            r.fail(f"segment {seg_id}: reference {item.get('id')} has no media_id")

    # model limits taken from list_models
    model = job.get("model")
    mlim = (((job.get("limits") or {}).get("models")) or {}).get(model)
    if mlim is None:
        r.warn(f"no limits recorded for model {model}; limits not checked")
    else:
        aspects = mlim.get("aspect_ratios")
        if aspects and job.get("aspect_ratio") not in aspects:
            r.fail(f"{model} does not take aspect ratio {job.get('aspect_ratio')} (allowed {aspects})")
        cap = mlim.get("max_reference_images")
        if isinstance(cap, int):
            used = len(seg.get("refs_used") or []) + 1 + (1 if seg.get("end_target") else 0)
            if used > cap:
                r.fail(f"segment {seg_id}: {used} images (references + folded frames) exceed {model}'s {cap}")

    quote = seg.get("quote") or {}
    q = quote.get("credits")
    if not isinstance(q, (int, float)) or q <= 0 or not is_nonempty_str(quote.get("quote_id")):
        r.fail(f"segment {seg_id}: needs a quote {{credits, quote_id}} from estimate_cost")
    else:
        total = approval.get("approved_total_credits") or 0
        try:
            spent = spent_so_far(jobdir)
        except ValueError as exc:
            r.fail(str(exc))
            spent = 0.0
        outstanding = 0.0
        for _, _, s in segments(d):
            if s.get("status") in ("ready", "generating"):
                outstanding += float((s.get("quote") or {}).get("credits") or 0)
        if s_status_not_counted(seg):
            outstanding += float(q)
        if spent + outstanding > total:
            r.fail(
                f"budget: spent {spent:g} + outstanding quotes {outstanding:g} exceeds approved total {total:g}"
            )
    return r


def s_status_not_counted(seg: dict) -> bool:
    """A segment still in draft is not yet in the outstanding-quotes sum."""
    return seg.get("status") not in ("ready", "generating")


def check_result(d: dict, seg_id: str) -> Report:
    r = Report()
    found = find_segment(d, seg_id)
    if found is None:
        r.fail(f"segment {seg_id} does not exist")
        return r
    chain, idx, seg = found
    if seg.get("status") != "done":
        r.fail(f"segment {seg_id}: status is {seg.get('status')}, not done")
    res = seg.get("result") or {}
    # a last frame is only needed when another segment continues from this one (a hard cut needs none)
    has_next = idx + 1 < len(chain["segments"]) and (chain["segments"][idx + 1].get("first_frame") or {}).get("source") == "extract"
    for key in ("generation_id", "video_media_id", "last_frame_media_id"):
        if key == "last_frame_media_id" and not has_next:
            continue
        if not is_nonempty_str(res.get(key)):
            r.fail(f"segment {seg_id}: result.{key} missing")
    cc = res.get("credits_charged")
    if not isinstance(cc, (int, float)) or cc < 0:
        r.fail(f"segment {seg_id}: result.credits_charged missing")
    review = seg.get("review") or {}
    if review.get("verdict") not in ("pass", "fail"):
        r.fail(f"segment {seg_id}: no review verdict (pass or fail)")
    cited = set(review.get("edge_frames_cited") or [])
    if idx > 0:
        prev = chain["segments"][idx - 1]
        need = {
            (prev.get("result") or {}).get("last_frame_media_id"),
            res.get("first_frame_extract_media_id"),
        }
        if None in need or "" in need:
            r.fail(f"segment {seg_id}: join review needs the previous clip's last frame and this clip's extracted first frame")
        elif not need <= cited:
            r.fail(f"segment {seg_id}: the join review must cite both real edge frames {sorted(need)}; it cited {sorted(cited)}")
    if review.get("verdict") == "pass" and not is_nonempty_str(review.get("notes")):
        r.fail(f"segment {seg_id}: a pass verdict needs written notes")
    return r


def check_ledger(d: dict, jobdir: str) -> Report:
    r = Report()
    approval = d.get("approval") or {}
    total = approval.get("approved_total_credits")
    if not isinstance(total, (int, float)):
        r.fail("approval.approved_total_credits missing")
        return r
    pct = approval.get("retake_allowance_pct", 15)
    try:
        rows = read_ledger(jobdir)
    except ValueError as exc:
        r.fail(str(exc))
        return r
    spent = 0.0
    retake = 0.0
    for row in rows:
        if row.get("refunded") is True:
            continue
        c = float(row.get("credits_charged") or 0)
        spent += c
        if row.get("kind") == "retake":
            retake += c
    base = total / (1 + pct / 100.0)
    r.info(f"spent {spent:g} of approved {total:g} (retakes {retake:g}, allowance {total - base:g})")
    if spent > total:
        r.fail(f"spent {spent:g} exceeds the approved total {total:g}")
    if retake > (total - base) + 1e-9:
        r.fail(f"retake spend {retake:g} exceeds the retake allowance {total - base:g}")
    return r


def make_manifest(d: dict) -> tuple[Report, list[dict]]:
    r = Report()
    out: list[dict] = []
    for chain, i, seg in segments(d):
        sub = check_result(d, seg.get("id", "?"))
        r.merge(sub)
        if (seg.get("review") or {}).get("verdict") != "pass":
            r.fail(f"segment {seg.get('id')}: review verdict is not pass")
        out.append(
            {
                "chain": chain.get("id"),
                "segment": seg.get("id"),
                "scene_ids": seg.get("scene_ids"),
                "duration_s": seg.get("duration_s"),
                "video_media_id": (seg.get("result") or {}).get("video_media_id"),
                "join_motion": seg.get("join_motion"),
            }
        )
    return r, out


# --------------------------------------------------------- snapshot guard

def file_hashes(jobdir: str) -> dict[str, str]:
    hashes: dict[str, str] = {}
    for root, _dirs, files in os.walk(jobdir):
        for name in files:
            if name == SNAPSHOT_NAME:
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, jobdir).replace(os.sep, "/")
            h = hashlib.sha256()
            with open(full, "rb") as fh:
                for block in iter(lambda: fh.read(65536), b""):
                    h.update(block)
            hashes[rel] = h.hexdigest()
    return hashes


def cmd_snapshot(jobdir: str) -> int:
    if not os.path.isdir(jobdir):
        print(f"FAIL: {jobdir} is not a directory")
        return 2
    hashes = file_hashes(jobdir)
    with open(os.path.join(jobdir, SNAPSHOT_NAME), "w", encoding="utf-8") as fh:
        json.dump(hashes, fh, sort_keys=True, indent=1)
    print(f"OK: snapshot of {len(hashes)} file(s)")
    return 0


def cmd_verify_snapshot(jobdir: str, allow: list[str]) -> int:
    path = os.path.join(jobdir, SNAPSHOT_NAME)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            before = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: no usable snapshot at {path}: {exc}")
        return 2
    after = file_hashes(jobdir)
    r = Report()
    for rel in sorted(set(before) | set(after)):
        if before.get(rel) == after.get(rel):
            continue
        if any(fnmatch.fnmatch(rel, g) for g in allow):
            continue
        what = "added" if rel not in before else "removed" if rel not in after else "changed"
        r.fail(f"{rel} was {what} by a subagent step but is not an allowed output")
    return r.emit()


# ------------------------------------------------------------------- CLI

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="relay_check.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add(name, *args, **kw):
        sp = sub.add_parser(name)
        for a in args:
            sp.add_argument(a)
        return sp

    sp = add("validate", "relay")
    sp.add_argument("--scratch", action="store_true")
    add("lock", "relay")
    add("verify-locks", "relay")
    add("check-chains", "relay")
    add("check-style", "relay")
    sp = add("check-dialogue", "relay")
    sp.add_argument("--allow-unapproved", action="store_true")
    sp = add("check-ready", "relay", "segment")
    sp.add_argument("--workspace-id")
    add("check-result", "relay", "segment")
    add("ledger", "relay")
    add("manifest", "relay")
    add("snapshot", "jobdir")
    sp = add("verify-snapshot", "jobdir")
    sp.add_argument("--allow", action="append", default=[])
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "snapshot":
        return cmd_snapshot(args.jobdir)
    if args.cmd == "verify-snapshot":
        return cmd_verify_snapshot(args.jobdir, args.allow)

    d = load(args.relay)
    jobdir = os.path.dirname(os.path.abspath(args.relay))

    if args.cmd == "validate":
        return check_structure(d, scratch=args.scratch).emit()
    if args.cmd == "lock":
        r = check_structure(d, scratch=True)
        if r.fails:
            return r.emit()
        import datetime

        d.setdefault("locks", {})["locked_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        d["locks"]["fingerprint"] = fingerprint(d)
        with open(args.relay, "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=2)
        print(f"OK: locked, fingerprint {d['locks']['fingerprint'][:12]}")
        return 0
    if args.cmd == "verify-locks":
        return check_locks(d).emit()
    if args.cmd == "check-chains":
        return check_chains(d).emit()
    if args.cmd == "check-style":
        return check_style(d).emit()
    if args.cmd == "check-dialogue":
        return check_dialogue(d, require_approved=not args.allow_unapproved).emit()
    if args.cmd == "check-ready":
        return check_ready(d, args.segment, jobdir, args.workspace_id).emit()
    if args.cmd == "check-result":
        return check_result(d, args.segment).emit()
    if args.cmd == "ledger":
        return check_ledger(d, jobdir).emit()
    if args.cmd == "manifest":
        r, out = make_manifest(d)
        if r.fails:
            return r.emit()
        print(json.dumps(out, indent=2))
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
