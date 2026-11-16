#!/usr/bin/env python3
"""panel_check.py: read and check a panel script (the markdown format in references/panel-template.md).

Standard library only, no network. Commands:
  check <panel.md> [--plan-wps N]   structure, timing and wording checks; exit 0 ok, 1 a check failed, 2 unreadable.
                     --plan-wps sets the planning speech rate used for the "no breath" warning (default 2.0;
                     measured narration voices ran about 3.3 words/s, so pass --plan-wps 3.3 once you have measured)
  parse <panel.md>   print the panel script as JSON (shots, cast, dialogue with line ids) for the script-injector
"""
from __future__ import annotations

import json
import re
import sys

REQUIRED_ROWS = ["length", "join", "setup", "cast on screen", "camera", "visual prompt",
                 "dialogue bubbles", "narration (vo)", "sfx", "bgm"]
CHECKLIST_ROWS = ["aspect ratio", "resolution", "frame rate", "narrator voice", "bubble policy",
                  "delivery", "final sign-off"]
MAX_WPS = 2.5        # hard cap, words per second (matches relay_check)
PLAN_WPS = 2.0       # planning rate for voiced delivery
MAX_LINES = 10       # reference-audio limit per clip
FRANCHISES = ["valorant", "spider-verse", "spiderverse", "spider verse", "miles morales", "marvel", "disney",
              "pixar", "ghibli", "dc comics", "star wars", "pokemon", "anime studio"]
EYELINE = re.compile(r"eyeline|at each other|toward each other|never look|nobody looks|neither (?:of them )?looks?|not (?:into|at) the (?:camera|lens)"
                     r"|looks? (?:up |down )?at (?:him|her|them)|never into the (?:camera|lens)", re.I)
UNSEALED = re.compile(r"\bshot\s*\d+\b|\bprevious\b|\bas before\b|\bsame as\b", re.I)
HEAD = re.compile(r"^##\s+SHOT\s+(\d+)\s*[—–-]\s*(\d+):(\d\d)\s*[—–-]\s*(\d+):(\d\d)\s*[—–-]\s*(.+?)\s*$")
ROW = re.compile(r"^\|\s*(.+?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*$")
LINE = re.compile(r'^([A-Z][A-Z0-9_]*)\s*(\([^)]*\))?\s*:\s*[“"](.+)[”"]\s*(\[(?:generated|adapted)\])?\s*$')
MARKER = re.compile(r"\[(generated|adapted)\]", re.I)
CAST_LINE = re.compile(r"\b([A-Z][A-Z0-9_]+)\s+[—-]\s+")


def secs(m: str, s: str) -> int:
    return int(m) * 60 + int(s)


def words(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9][A-Za-z0-9'’-]*", text))


def split_entries(cell: str) -> list:
    if cell.strip().lower() in ("", "none", "-", "—", "(none)"):
        return []
    return [e.strip() for e in cell.split(" / ") if e.strip()]


def parse(text: str) -> dict:
    lines = text.splitlines()
    doc = {"title": "", "meta": "", "bible": {}, "cast": [], "shots": [], "checklist": {}, "generated": [], "has_generated_section": False}
    section = None
    shot = None
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith("# ") and not doc["title"]:
            doc["title"] = s[2:].strip()
            nxt = next((x.strip() for x in lines[i + 1:] if x.strip()), "")
            doc["meta"] = nxt
            continue
        m = HEAD.match(s)
        if m:
            shot = {"n": int(m.group(1)), "start": secs(m.group(2), m.group(3)), "end": secs(m.group(4), m.group(5)),
                    "title": m.group(6), "rows": {}, "line": i + 1}
            doc["shots"].append(shot)
            section = "shot"
            continue
        if s.startswith("## "):
            up = s.upper()
            shot = None
            if "GLOBAL STYLE BIBLE" in up:
                section = "bible"
            elif "PRODUCTION CHECKLIST" in up:
                section = "checklist"
            elif "GENERATED ADDITIONS" in up or "ADAPTED LINES" in up:
                section = "generated"
                doc["has_generated_section"] = True
            else:
                section = "other"
            continue
        if section == "bible":
            b = re.match(r"^[-*]?\s*\*{0,2}([A-Z][A-Z ]+?)\s*(?:\([^)]*\))?\s*\*{0,2}\s*:\s*\*{0,2}\s*(.+)$", s)
            if b:
                doc["bible"][b.group(1).strip()] = b.group(2).strip()
            continue
        r = ROW.match(s)
        if not r or set(s) <= set("|- :"):
            continue
        key = r.group(1).strip().strip("*").lower()
        if key in ("field", "item", "shot"):
            continue
        if section == "shot" and shot is not None:
            shot["rows"][key] = r.group(2).strip()
        elif section == "checklist":
            doc["checklist"][key] = r.group(2).strip()
        elif section == "generated":
            doc["generated"].append([r.group(1).strip(), r.group(2).strip(), r.group(3).strip()])
    doc["cast"] = CAST_LINE.findall(doc["bible"].get("CHARACTERS", ""))
    return doc


def dialogue_of(shot: dict) -> tuple:
    """Return (entries, errors): entries are dicts speaker/note/text/generated."""
    out, errs = [], []
    for e in split_entries(shot["rows"].get("dialogue bubbles", "")):
        if e.startswith("("):
            continue  # stage direction such as (beat: she pulls him back in)
        m = LINE.match(e)
        if not m:
            errs.append(e)
            continue
        marker = (m.group(4) or "").strip("[]").lower()
        out.append({"speaker": m.group(1), "note": (m.group(2) or "").strip("() "), "text": m.group(3).strip(),
                    "generated": bool(marker), "marker": marker})
    return out, errs


def narration_of(shot: dict) -> str:
    cell = shot["rows"].get("narration (vo)", "")
    cell = MARKER.sub("", cell).strip()
    return "" if cell.lower() in ("", "none", "-", "—") else cell.strip('"“” ')


def check(doc: dict, plan_wps: float = PLAN_WPS) -> tuple:
    fails, warns, infos = [], [], []
    shots = doc["shots"]
    if not doc["title"]:
        fails.append("no '# Title' line")
    if not shots:
        fails.append("no '## SHOT NN — m:ss–m:ss — TITLE' headings found")
        return fails, warns, infos
    if not doc["cast"]:
        fails.append("GLOBAL STYLE BIBLE has no CHARACTERS line with 'NAME — description' entries")
    for key in ("CHARACTERS", "ENVIRONMENT", "DIALOGUE RULE", "NARRATION", "TRANSITIONS"):
        if key not in doc["bible"]:
            warns.append(f"style bible has no {key} line")
    claimed = re.search(r"(\d+)\s+shots?", doc["meta"], re.I)
    if claimed and int(claimed.group(1)) != len(shots):
        warns.append(f"meta line says {claimed.group(1)} shots but {len(shots)} shot tables were found")
    total_len, prev_end, n_generated = 0, 0, 0
    for idx, sh in enumerate(shots, 1):
        tag = f"SHOT {sh['n']:02d}"
        if sh["n"] != idx:
            fails.append(f"{tag}: shots must be numbered 1, 2, 3 in order (expected {idx:02d})")
        if sh["start"] != prev_end:
            fails.append(f"{tag}: starts at {sh['start']} s but the previous shot ends at {prev_end} s (timecodes must run on without a gap)")
        prev_end = sh["end"]
        rows = sh["rows"]
        for need in REQUIRED_ROWS:
            if not rows.get(need, "").strip():
                fails.append(f"{tag}: row '{need}' is missing or empty")
        lm = re.match(r"\s*(\d+)", rows.get("length", ""))
        length = int(lm.group(1)) if lm else 0
        if lm and abs((sh["end"] - sh["start"]) - length) > 1:
            fails.append(f"{tag}: heading timecodes span {sh['end'] - sh['start']} s but Length is {length} s")
        if length and not 4 <= length <= 30:
            fails.append(f"{tag}: Length {length} s is outside 4 to 30 s (one clip)")
        total_len += length or (sh["end"] - sh["start"])
        join = rows.get("join", "").strip().lower()
        if join:
            jm = re.match(r"continues from (?:shot |s)?0*(\d+)$", join)
            if join != "hard cut" and not jm:
                fails.append(f"{tag}: Join must be 'hard cut' or 'continues from SHOT NN', got '{rows['join']}'")
            elif jm and not (1 <= int(jm.group(1)) < sh["n"]):
                fails.append(f"{tag}: Join refers to SHOT {jm.group(1)}, which is not an earlier shot")
        setup = rows.get("setup", "")
        if setup and not re.search(r"place\s*:", setup, re.I):
            warns.append(f"{tag}: Setup has no 'Place:' part")
        if setup and not re.search(r"light", setup, re.I):
            warns.append(f"{tag}: Setup says nothing about time and light")
        onscreen = [c.strip().upper() for c in rows.get("cast on screen", "").split(",")
                    if c.strip() and c.strip().lower() not in ("none", "-", "—", "(none)")]
        for c in onscreen:
            if doc["cast"] and c not in doc["cast"]:
                fails.append(f"{tag}: '{c}' is on screen but has no entry in the style bible CHARACTERS line")
        entries, bad = dialogue_of(sh)
        for b in bad:
            fails.append(f"{tag}: dialogue entry not in NAME: \"line\" form: {b[:70]}")
        if len(entries) > MAX_LINES:
            fails.append(f"{tag}: {len(entries)} dialogue lines; a clip takes at most {MAX_LINES} voice references")
        for e in entries:
            if doc["cast"] and e["speaker"] not in doc["cast"]:
                fails.append(f"{tag}: speaker {e['speaker']} is not a CHARACTERS entry")
            elif e["speaker"] not in onscreen and "off screen" not in e["note"].lower() and "muffled" not in e["note"].lower():
                warns.append(f"{tag}: {e['speaker']} speaks but is not in 'Cast on screen' (write '(off screen)' after the name if intended)")
            if e["generated"]:
                n_generated += 1
                infos.append(f"{tag}: {e['marker']} line for owner approval: {e['speaker']}: \"{e['text'][:60]}\"")
        for mk in MARKER.findall(rows.get("narration (vo)", "")):
            n_generated += 1
            infos.append(f"{tag}: narration marked [{mk.lower()}] for owner approval")
        spoken = sum(words(e["text"]) for e in entries) + words(narration_of(sh))
        if length:
            if spoken / length > MAX_WPS:
                fails.append(f"{tag}: {spoken} spoken words in {length} s is {spoken / length:.1f} words/s (cap {MAX_WPS}); lengthen the shot or trim the words")
            elif spoken / plan_wps > 0.9 * length:
                warns.append(f"{tag}: about {spoken / plan_wps:.0f} s of speech in a {length} s shot leaves no breath; lengthen it")
        vis = rows.get("visual prompt", "")
        if UNSEALED.search(vis) or UNSEALED.search(rows.get("camera", "")) or UNSEALED.search(rows.get("setup", "")):
            fails.append(f"{tag}: setup/camera/visual text refers to another shot ('shot N', 'previous', 'as before'); every shot must stand alone")
        low = (vis + " " + rows.get("camera", "") + " " + doc["bible"].get("ENVIRONMENT", "")).lower()
        for f in FRANCHISES:
            if f in low:
                warns.append(f"{tag}: franchise or brand name '{f}' in the prompt text; describe the look in visible terms instead")
        if len(onscreen) >= 2 and vis and not EYELINE.search(vis):
            warns.append(f"{tag}: {len(onscreen)} people on screen but the visual prompt states no eyelines (who looks at whom; nobody into the camera)")
    if n_generated and not doc["has_generated_section"]:
        fails.append("there are [generated] or [adapted] lines but no '## GENERATED ADDITIONS' section listing them")
    if doc["has_generated_section"] and not doc["generated"]:
        warns.append("'## GENERATED ADDITIONS' section has no rows")
    for need in CHECKLIST_ROWS:
        if need not in doc["checklist"]:
            warns.append(f"production checklist has no '{need}' row")
    rt = re.search(r"~\s*(\d+):(\d\d)", doc["meta"])
    if rt:
        target = secs(rt.group(1), rt.group(2))
        if target and abs(total_len - target) / target > 0.10:
            warns.append(f"shot lengths add up to {total_len} s but the meta line says about {target} s")
    infos.append(f"{len(shots)} shots, {total_len} s, {n_generated} generated line(s)")
    return fails, warns, infos


def to_json(doc: dict) -> dict:
    n = 0
    shots = []
    for sh in doc["shots"]:
        entries, _ = dialogue_of(sh)
        lines = []
        for e in entries:
            n += 1
            lines.append({"id": f"l{n:02d}", "speaker": e["speaker"], "note": e["note"], "text": e["text"],
                          "source": "generated" if e["generated"] else "script", "marker": e["marker"] or None,
                          "approved": not e["generated"]})
        r = sh["rows"]
        jm = re.match(r"continues from (?:shot |s)?0*(\d+)$", r.get("join", "").strip().lower())
        place = re.search(r"place\s*:\s*(.*?)(?=\s*(?:time and light|props)\s*:|$)", r.get("setup", ""), re.I)
        light = re.search(r"time and light\s*:\s*(.*?)(?=\s*props\s*:|$)", r.get("setup", ""), re.I)
        props = re.search(r"props\s*:\s*(.*)$", r.get("setup", ""), re.I)
        shots.append({
            "id": f"S{sh['n']:02d}", "n": sh["n"], "title": sh["title"], "start_s": sh["start"], "end_s": sh["end"],
            "length_s": int(re.match(r"\s*(\d+)", r.get("length", "0")).group(1)) if re.match(r"\s*(\d+)", r.get("length", "")) else None,
            "join": {"mode": "continues" if jm else "hard_cut", "from": f"S{int(jm.group(1)):02d}" if jm else None},
            "setup": {"place": (place.group(1).strip(" .;") if place else r.get("setup", "")),
                      "time_and_light": (light.group(1).strip(" .;") if light else ""),
                      "props": (props.group(1).strip(" .;") if props else "")},
            "cast": [c.strip().upper() for c in r.get("cast on screen", "").split(",") if c.strip()],
            "camera": r.get("camera", ""), "visual_prompt": r.get("visual prompt", ""),
            "dialogue": lines, "narration": narration_of(sh) or None,
            "sfx": r.get("sfx", ""), "bgm": r.get("bgm", ""),
            "extra": {k: v for k, v in r.items() if k not in REQUIRED_ROWS},
        })
    return {"title": doc["title"], "meta": doc["meta"], "style_bible": doc["bible"], "cast": doc["cast"],
            "shots": shots, "checklist": doc["checklist"], "generated_additions": doc["generated"]}


def main(argv: list) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    args = list(argv[1:])
    plan_wps = PLAN_WPS
    if "--plan-wps" in args:
        i = args.index("--plan-wps")
        try:
            plan_wps = float(args[i + 1])
            del args[i:i + 2]
        except (IndexError, ValueError):
            print("--plan-wps needs a number, for example --plan-wps 3.3")
            return 2
    if len(args) != 2 or args[0] not in ("check", "parse"):
        print(__doc__)
        return 2
    cmd, path = args
    try:
        with open(path, encoding="utf-8") as fh:
            doc = parse(fh.read())
    except OSError as exc:
        print(f"cannot read {path}: {exc}")
        return 2
    if cmd == "parse":
        print(json.dumps(to_json(doc), ensure_ascii=False, indent=2))
        return 0
    fails, warns, infos = check(doc, plan_wps)
    for x in infos:
        print("INFO:", x)
    for x in warns:
        print("WARN:", x)
    for x in fails:
        print("FAIL:", x)
    print("OK" if not fails else f"{len(fails)} check(s) failed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
