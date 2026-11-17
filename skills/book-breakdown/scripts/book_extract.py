#!/usr/bin/env python3
"""book_extract.py: turn a book PDF (or its text) into chapters, runtimes and flags for the book-breakdown skill.

Standard library only (it calls a local `pdftotext`, `pypdf` or `PyMuPDF` if one is installed to read a PDF; it never
touches the network and never calls Frameo). Free.

Commands:
  extract  <book.pdf | --text book.txt> --out DIR [--title T] [--wpfm 800] [--min-s 180] [--max-s 900]
           [--heading-regex RE] [--split-words N]
      Reads the book, drops running headers and page numbers, finds the chapter breakpoints, and writes
        DIR/text/full.txt  DIR/chapters/NN-slug.txt  DIR/breakdown.json  DIR/names.json
      then prints the breakdown table.
  table    DIR                      print the breakdown table again
  adjust   DIR [--merge ch05,ch06] [--split ch07:3] [--drop ch00]
      Applies your decisions about tiny or thick chapters (merge into the first, split into N parts at scene
      breaks, drop front or back matter), recomputes runtimes and rewrites DIR/breakdown.json and the chapter files.

Scanned PDFs (no text layer) are refused: run OCR first, then use --text.
Exit codes: 0 ok, 1 a check failed, 2 unreadable input.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

WORDS_PER_FILM_MINUTE = 800
MIN_S = 180
MAX_S = 900

NUMBER_WORDS = ("one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
                "seventeen eighteen nineteen twenty thirty forty fifty sixty seventy eighty ninety hundred").split()
_NUM = r"(?:\d{1,3}|[ivxlcdm]{1,8}|(?:%s)(?:[- ](?:%s))*)" % ("|".join(NUMBER_WORDS), "|".join(NUMBER_WORDS))
CHAPTER_RE = re.compile(r"^\s*(?:chapter|ch\.)\s+(%s)\b\s*[:.\-–—]*\s*(.*)$" % _NUM, re.I)
SPECIAL_RE = re.compile(r"^\s*(prologue|epilogue|introduction|preface|foreword|afterword|interlude|author'?s note)\b[\s:.\-–—]*(.*)$", re.I)
PART_RE = re.compile(r"^\s*(?:part|book)\s+(%s)\b\s*[:.\-–—]*\s*(.*)$" % _NUM, re.I)
BARE_NUM_RE = re.compile(r"^\s*(\d{1,3})\s*$")
BACK_MATTER_RE = re.compile(r"^\s*(acknowledg(?:e)?ments?|about the author|also by|bibliography|index|notes|glossary|copyright|"
                            r"table of contents|contents|dedication|praise for|reading group guide)\s*$", re.I)
SCENE_BREAK_RE = re.compile(r"^\s*(?:(?:\*\s*){3,}|[-–—_#~=]{3,}|•\s*•\s*•)\s*$")
WORD_RE = re.compile(r"[A-Za-z0-9À-ɏऀ-ॿ][A-Za-z0-9À-ɏऀ-ॿ'’-]*")

# Words that suggest a heated passage. Used only to FLAG a chapter so you can choose its content ceiling in words;
# false positives are expected (the flag is a prompt to look, never a decision). Two tiers: one strong term flags a
# chapter; several soft terms together flag it too.
HEAT_STRONG = ["naked", "nude", "orgasm", "intercourse", "erection", "erect", "nipple", "nipples", "genitals", "vagina",
               "penis", "clitoris", "clit", "cock", "pussy", "dick", "fuck", "fucked", "fucking", "made love", "making love",
               "thrust", "thrusts", "thrusting", "inside her", "inside him", "climax", "straddled", "aroused", "arousal"]
HEAT_SOFT = ["moan", "moaned", "moaning", "gasp", "gasped", "pleasure", "thigh", "thighs", "hips", "skin", "caress", "caressed",
             "stroke", "stroking", "undress", "undressed", "unbutton", "unbuttoned", "lust", "panting", "throb", "throbbing",
             "stripped", "unzipped", "bare", "breath hitched"]
HEAT_STRONG_RE = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(t) for t in HEAT_STRONG), re.I)
HEAT_SOFT_RE = re.compile(r"\b(?:%s)\b" % "|".join(re.escape(t) for t in HEAT_SOFT), re.I)
HEAT_SOFT_MIN = 5


def heat_score(text: str) -> tuple:
    """(score, flagged): strong hits count 3, soft hits 1; flagged when any strong term or HEAT_SOFT_MIN soft terms."""
    strong = len(HEAT_STRONG_RE.findall(text))
    soft = len(HEAT_SOFT_RE.findall(text))
    return strong * 3 + soft, (strong >= 1 or soft >= HEAT_SOFT_MIN)

STOP_NAMES = set("""I The A An And But Or So If When While After Before Then There Here This That These Those He She It
We You They His Her Its Our Your Their My Mine What Why How Who Where Which Yes No Not Maybe Oh Well Now Just Still
Mr Mrs Ms Dr Sir Madam Chapter Part Book Monday Tuesday Wednesday Thursday Friday Saturday Sunday January February
March April May June July August September October November December God Lord""".split())


# ------------------------------------------------------------------ reading the book

def read_pdf_pages(path: str) -> list[str]:
    """Return one string per page using whichever reader is available. Raises SystemExit with advice if none is."""
    if shutil.which("pdftotext"):
        try:
            out = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", path, "-"], capture_output=True, timeout=600)
            if out.returncode == 0 and out.stdout.strip():
                return out.stdout.decode("utf-8", errors="replace").split("\f")
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        import pypdf  # type: ignore
        reader = pypdf.PdfReader(path)
        return [(p.extract_text() or "") for p in reader.pages]
    except ImportError:
        pass
    except Exception as exc:  # corrupt file, encryption, ...
        raise SystemExit(f"FAIL: cannot read {path}: {exc}")
    try:
        import fitz  # type: ignore
        doc = fitz.open(path)
        return [page.get_text() for page in doc]
    except ImportError:
        pass
    raise SystemExit("FAIL: no PDF reader found. Install poppler's `pdftotext`, or `pip install pypdf`, "
                     "or extract the text yourself and pass it with --text.")


def pages_from_text(text: str, words_per_page: int = 400) -> list[str]:
    if "\f" in text:
        return text.split("\f")
    lines = text.split("\n")
    pages, cur, count = [], [], 0
    for ln in lines:
        cur.append(ln)
        count += len(ln.split())
        if count >= words_per_page and not ln.strip():
            pages.append("\n".join(cur))
            cur, count = [], 0
    if cur:
        pages.append("\n".join(cur))
    return pages


def has_text_layer(pages: list[str]) -> bool:
    if not pages:
        return False
    chars = sum(len(p.strip()) for p in pages)
    return chars / max(1, len(pages)) >= 120


def clean_pages(pages: list[str]) -> list[str]:
    """Drop page numbers and running headers or footers (a line repeated on at least a third of the pages)."""
    def norm(line: str) -> str:
        return re.sub(r"\d+", "#", line.strip().lower())

    counts: dict[str, int] = {}
    for p in pages:
        seen = set()
        lines = [ln for ln in p.split("\n") if ln.strip()]
        for ln in lines[:3] + lines[-3:]:
            seen.add(norm(ln))
        for k in seen:
            counts[k] = counts.get(k, 0) + 1
    limit = max(3, len(pages) // 3)
    repeated = {k for k, v in counts.items() if v >= limit and len(k) < 90}
    out = []
    for p in pages:
        keep = []
        lines = p.split("\n")
        nonempty = [i for i, ln in enumerate(lines) if ln.strip()]
        edge = set(nonempty[:3] + nonempty[-3:])
        for i, ln in enumerate(lines):
            if i in edge and (norm(ln) in repeated or re.fullmatch(r"\s*(?:page\s+)?\d{1,4}\s*", ln, re.I)):
                continue
            keep.append(ln.rstrip())
        out.append("\n".join(keep))
    return out


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text))


# ------------------------------------------------------------------ finding chapters

def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    return s[:40] or "chapter"


def _heading_at(lines: list[str], i: int, rx: re.Pattern | None):
    """Return (kind, number_text, title, consumed_lines) if a heading starts at lines[i], else None."""
    ln = lines[i]
    if rx is not None:
        m = rx.match(ln)
        if m:
            title = (m.group(1) if m.lastindex else ln).strip()
            return ("chapter", "", title, 1)
        return None
    m = CHAPTER_RE.match(ln)
    if m:
        title = m.group(2).strip()
        used = 1
        if not title and i + 1 < len(lines) and lines[i + 1].strip() and len(lines[i + 1].split()) <= 10 \
                and not CHAPTER_RE.match(lines[i + 1]):
            title, used = lines[i + 1].strip(), 2
        return ("chapter", m.group(1), title, used)
    m = SPECIAL_RE.match(ln)
    if m and len(ln.split()) <= 6:
        return (m.group(1).lower(), "", m.group(2).strip(), 1)
    return None


def detect_chapters(pages: list[str], heading_regex: str | None = None) -> dict:
    """Find chapter starts. A heading counts only near the top of a page. TOC pages (many headings) are ignored."""
    rx = re.compile(heading_regex, re.I) if heading_regex else None
    hits = []          # (page_index, line_index, kind, number_text, title)
    toc_pages = []
    for pi, page in enumerate(pages):
        lines = page.split("\n")
        nonempty = [i for i, ln in enumerate(lines) if ln.strip()]
        found_here = []
        for i in nonempty:
            h = _heading_at(lines, i, rx)
            if h:
                found_here.append((i, h))
        if len(found_here) >= 4:                      # a table of contents lists many headings on one page
            toc_pages.append(pi)
            continue
        top = set(nonempty[:8])
        for i, h in found_here:
            if i in top:
                hits.append((pi, i, h[0], h[1], h[2], h[3]))
                break
    # bare numbers ("1", "2", ...) as chapter openers, only when they form a run starting at 1
    if not hits and rx is None:
        cands = []
        for pi, page in enumerate(pages):
            lines = page.split("\n")
            nonempty = [i for i, ln in enumerate(lines) if ln.strip()]
            for i in nonempty[:3]:
                m = BARE_NUM_RE.match(lines[i])
                if m:
                    title = ""
                    j = i + 1
                    while j < len(lines) and not lines[j].strip():
                        j += 1
                    if j < len(lines) and len(lines[j].split()) <= 8:
                        title = lines[j].strip()
                    cands.append((pi, i, "chapter", m.group(1), title, 1))
                    break
        nums = [int(c[3]) for c in cands]
        if len(nums) >= 3 and nums[0] == 1 and all(b == a + 1 for a, b in zip(nums, nums[1:])):
            hits = cands
    return {"hits": hits, "toc_pages": toc_pages}


def _num_to_int(s: str):
    s = (s or "").strip().lower()
    if s.isdigit():
        return int(s)
    roman = {"i": 1, "v": 5, "x": 10, "l": 50, "c": 100, "d": 500, "m": 1000}
    if s and all(ch in roman for ch in s):
        total = 0
        for a, b in zip(s, s[1:] + " "):
            v = roman[a]
            total += -v if b in roman and roman[b] > v else v
        return total
    small = {w: i for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve thirteen "
                                        "fourteen fifteen sixteen seventeen eighteen nineteen twenty".split())}
    parts = re.split(r"[- ]", s)
    tens = {"twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90}
    if parts and all(p in small or p in tens for p in parts):
        return sum(tens.get(p, small.get(p, 0)) for p in parts)
    return None


def build_chapters(pages: list[str], det: dict, wpfm: int, min_s: int, max_s: int) -> dict:
    hits = det["hits"]
    warnings = []
    chapters, skipped = [], []
    if not hits:
        text = "\n\n".join(pages)
        warnings.append("no chapter headings found: the whole book is one chapter. Pass --heading-regex to match your "
                        "headings, or --split-words N to cut at scene breaks.")
        chapters.append({"kind": "chapter", "number": 1, "title": "Whole book", "text": text, "start_page": 1,
                         "end_page": len(pages)})
    else:
        starts = []
        for (pi, li, kind, numtxt, title, used) in hits:
            starts.append((pi, li + used, kind, numtxt, title))
        # front matter before the first heading
        first_pi, first_li = hits[0][0], hits[0][1]
        front = "\n".join(pages[:first_pi] + ["\n".join(pages[first_pi].split("\n")[:first_li])]).strip()
        if front:
            skipped.append({"kind": "front matter", "title": "Front matter", "words": count_words(front),
                            "start_page": 1, "end_page": first_pi + 1})
        for n, (pi, li, kind, numtxt, title) in enumerate(starts):
            if n + 1 < len(starts):
                npi, nli = starts[n + 1][0], hits[n + 1][1]
                body_pages = pages[pi:npi + 1]
                lines = []
                for k, pg in enumerate(body_pages):
                    pl = pg.split("\n")
                    if k == 0:
                        pl = pl[li:]
                    if k == len(body_pages) - 1:
                        pl = pl[:nli] if k > 0 else pl[:max(0, nli - li)]
                    lines.extend(pl)
                end_page = npi + (0 if nli == 0 else 1)
            else:
                lines = []
                for k, pg in enumerate(pages[pi:]):
                    pl = pg.split("\n")
                    lines.extend(pl[li:] if k == 0 else pl)
                end_page = len(pages)
            text = "\n".join(lines).strip()
            # back matter inside the last chapter's tail
            tail = None
            if n + 1 == len(starts):
                tl = text.split("\n")
                for idx, ln in enumerate(tl):
                    if BACK_MATTER_RE.match(ln) and count_words("\n".join(tl[idx:])) < 1500:
                        tail = "\n".join(tl[idx:])
                        text = "\n".join(tl[:idx]).strip()
                        break
            num = _num_to_int(numtxt) if numtxt else None
            chapters.append({"kind": kind, "number": num, "title": title, "text": text,
                             "start_page": pi + 1, "end_page": end_page})
            if tail:
                skipped.append({"kind": "back matter", "title": "Back matter", "words": count_words(tail),
                                "start_page": end_page, "end_page": len(pages)})
    # numbering, ids, runtimes, flags
    out = []
    for i, ch in enumerate(chapters, 1):
        words = count_words(ch["text"])
        raw_s = words / wpfm * 60.0
        runtime = int(min(max_s, max(min_s, round(raw_s / 10.0) * 10)))
        flags = []
        if raw_s < min_s:
            flags.append("tiny")
        if raw_s > max_s:
            flags.append("thick")
        heat, heated = heat_score(ch["text"])
        if heated:
            flags.append("heat")
        scene_breaks = sum(1 for ln in ch["text"].split("\n") if SCENE_BREAK_RE.match(ln))
        out.append({"id": "ch%02d" % i, "number": ch["number"] if ch["number"] is not None else i,
                    "kind": ch["kind"], "title": ch["title"] or ("Chapter %d" % i), "start_page": ch["start_page"],
                    "end_page": ch["end_page"], "words": words, "raw_runtime_s": int(raw_s), "runtime_s": runtime,
                    "flags": flags, "scene_breaks": scene_breaks, "heat_hits": heat, "text": ch["text"]})
    nums = [c["number"] for c in out if c["kind"] == "chapter" and isinstance(c["number"], int)]
    if nums and any(b != a + 1 for a, b in zip(nums, nums[1:])):
        warnings.append("chapter numbers are not consecutive (%s): check for a missed or doubled heading" %
                        ", ".join(str(n) for n in nums[:30]))
    return {"chapters": out, "skipped": skipped, "warnings": warnings}


def name_frequencies(chapters: list[dict]) -> dict:
    """Proper-noun candidates per chapter (a cheap skeleton for the series bible; the bible step does the real work)."""
    # a capitalised word is a name candidate when the book almost never writes it in lowercase ("Anna" yes, "River" no),
    # so names that start sentences are still found
    lower: dict[str, int] = {}
    for ch in chapters:
        for w in re.findall(r"\b[a-z]{3,}\b", ch["text"]):
            lower[w] = lower.get(w, 0) + 1
    names: dict[str, dict] = {}
    rx = re.compile(r"\b([A-Z][a-z]{2,}(?:[ ]+[A-Z][a-z]{2,}){0,2})\b")
    for ch in chapters:
        for m in rx.finditer(ch["text"]):
            nm = m.group(1)
            first = nm.split()[0]
            if first in STOP_NAMES or lower.get(first.lower(), 0) >= 3:
                continue
            e = names.setdefault(nm, {"total": 0, "chapters": {}})
            e["total"] += 1
            e["chapters"][ch["id"]] = e["chapters"].get(ch["id"], 0) + 1
    keep = {k: v for k, v in names.items() if v["total"] >= 3}
    ranked = sorted(keep.items(), key=lambda kv: -kv[1]["total"])[:200]
    return {k: {"total": v["total"], "chapters": v["chapters"], "recurring": len(v["chapters"]) >= 2} for k, v in ranked}


# ------------------------------------------------------------------ writing and table

GENERATED_RE = re.compile(r"^\d{2,3}[a-z]?-[a-z0-9-]*\.txt$")


def clear_generated(cdir: str) -> None:
    """Remove only the chapter files this script wrote (NN-slug.txt), never anything else in the folder."""
    if os.path.isdir(cdir):
        for n in os.listdir(cdir):
            if GENERATED_RE.match(n):
                os.remove(os.path.join(cdir, n))
    os.makedirs(cdir, exist_ok=True)


def write_outputs(out: str, title: str, source: str, pages: list[str], built: dict, settings: dict) -> dict:
    os.makedirs(os.path.join(out, "text"), exist_ok=True)
    cdir = os.path.join(out, "chapters")
    clear_generated(cdir)
    with open(os.path.join(out, "text", "full.txt"), "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n\f".join(pages))
    chapters = []
    for c in built["chapters"]:
        fn = "%s-%s.txt" % (c["id"][2:], _slug(c["title"]))
        with open(os.path.join(cdir, fn), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(c["text"].rstrip() + "\n")
        rec = {k: v for k, v in c.items() if k != "text"}
        rec["file"] = "chapters/" + fn
        chapters.append(rec)
    names = name_frequencies(built["chapters"])
    with open(os.path.join(out, "names.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(names, fh, indent=1, ensure_ascii=False)
    bd = {"version": 1, "title": title, "source": source, "pages": len(pages),
          "words": sum(c["words"] for c in chapters), "settings": settings, "chapters": chapters,
          "skipped": built["skipped"], "warnings": built["warnings"]}
    with open(os.path.join(out, "breakdown.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(bd, fh, indent=1, ensure_ascii=False)
    return bd


def fmt_time(s: int) -> str:
    return "%d:%02d" % (s // 60, s % 60)


def render_table(bd: dict) -> str:
    rows = ["| id | # | title | pages | words | runtime | flags |", "|---|---|---|---|---|---|---|"]
    for c in bd["chapters"]:
        rows.append("| %s | %s | %s | %s-%s | %d | %s | %s |" % (
            c["id"], c["number"], c["title"].replace("|", "/")[:48], c["start_page"], c["end_page"], c["words"],
            fmt_time(c["runtime_s"]), ", ".join(c["flags"]) or ""))
    tot = sum(c["runtime_s"] for c in bd["chapters"])
    rows.append("")
    rows.append("%d chapters, %d words, total runtime %s (window %s to %s per chapter, %d words per film minute)." % (
        len(bd["chapters"]), bd["words"], fmt_time(tot), fmt_time(bd["settings"]["min_s"]), fmt_time(bd["settings"]["max_s"]),
        bd["settings"]["words_per_film_minute"]))
    for sk in bd.get("skipped", []):
        rows.append("Skipped %s: %d words (pages %s-%s)." % (sk["kind"], sk["words"], sk["start_page"], sk["end_page"]))
    for w in bd.get("warnings", []):
        rows.append("WARNING: " + w)
    flagged = [c for c in bd["chapters"] if c["flags"]]
    if flagged:
        rows.append("Flags: tiny = under the minimum runtime (propose merging), thick = over the maximum (propose Part 1/Part 2), "
                    "heat = possible heated passage (choose the content ceiling for this chapter in words).")
    return "\n".join(rows)


# ------------------------------------------------------------------ adjust: merge, split, drop

def _load_breakdown(out: str) -> dict:
    p = os.path.join(out, "breakdown.json")
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read {p}: {exc}")
        sys.exit(2)


def _chapter_text(out: str, c: dict) -> str:
    with open(os.path.join(out, c["file"]), encoding="utf-8") as fh:
        return fh.read()


def _split_text(text: str, parts: int) -> list[str]:
    lines = text.split("\n")
    total = count_words(text)
    target = total / parts
    cuts, acc, want = [], 0, 1
    breaks = [i for i, ln in enumerate(lines) if SCENE_BREAK_RE.match(ln)]
    paras = [i for i, ln in enumerate(lines) if not ln.strip()]
    pool = breaks if len(breaks) >= parts - 1 else paras
    run = 0
    cum = []
    for ln in lines:
        run += len(ln.split())
        cum.append(run)
    for k in range(1, parts):
        goal = target * k
        best = None
        if breaks:
            nb = min(breaks, key=lambda i: abs(cum[i] - goal))
            if abs(cum[nb] - goal) <= 0.25 * target:      # use a scene break only when it keeps the parts balanced
                best = nb
        if best is None:
            best = min(paras, key=lambda i: abs(cum[i] - goal)) if paras else int(len(lines) * k / parts)
        cuts.append(best)
    cuts = sorted(set(cuts))
    segs, prev = [], 0
    for c in cuts:
        segs.append("\n".join(lines[prev:c]).strip())
        prev = c + 1 if SCENE_BREAK_RE.match(lines[c]) else c
    segs.append("\n".join(lines[prev:]).strip())
    return [s for s in segs if s]


def adjust(out: str, merge: list[str], split: list[str], drop: list[str]) -> dict:
    bd = _load_breakdown(out)
    st = bd["settings"]
    texts = {c["id"]: _chapter_text(out, c) for c in bd["chapters"]}
    chapters = [dict(c) for c in bd["chapters"]]
    byid = {c["id"]: c for c in chapters}
    for grp in merge:
        ids = [x.strip() for x in grp.split(",") if x.strip()]
        if len(ids) < 2 or any(i not in byid for i in ids):
            raise SystemExit("FAIL: --merge needs two or more existing chapter ids, got %r" % grp)
        order = [c["id"] for c in chapters]
        idxs = sorted(order.index(i) for i in ids)
        if idxs != list(range(idxs[0], idxs[0] + len(idxs))):
            raise SystemExit("FAIL: --merge can only join neighbouring chapters (%s)" % grp)
        first = byid[order[idxs[0]]]
        for j in idxs[1:]:
            other = byid[order[j]]
            texts[first["id"]] = texts[first["id"]].rstrip() + "\n\n" + texts[other["id"]].lstrip()
            first["title"] = "%s + %s" % (first["title"], other["title"])
            first["end_page"] = other["end_page"]
            chapters.remove(other)
    for sp in split:
        cid, _, n = sp.partition(":")
        if cid not in byid or not n.isdigit() or int(n) < 2:
            raise SystemExit("FAIL: --split needs ch07:3 style (an existing id and a part count >= 2), got %r" % sp)
        base = byid[cid]
        segs = _split_text(texts[cid], int(n))
        pos = chapters.index(base)
        chapters.remove(base)
        for k, seg in enumerate(segs):
            nc = dict(base)
            nc["id"] = "%s%s" % (cid, "abcdefghij"[k])
            nc["title"] = "%s (part %d)" % (base["title"], k + 1)
            texts[nc["id"]] = seg
            chapters.insert(pos + k, nc)
        del texts[cid]
    for cid in drop:
        c = byid.get(cid)
        if c is None:
            raise SystemExit("FAIL: --drop: no chapter %r" % cid)
        if c in chapters:
            chapters.remove(c)
            texts.pop(cid, None)
    # recompute everything, renumber ids that are not split parts
    for c in chapters:
        t = texts[c["id"]]
        words = count_words(t)
        raw = words / st["words_per_film_minute"] * 60.0
        c["words"], c["raw_runtime_s"] = words, int(raw)
        c["runtime_s"] = int(min(st["max_s"], max(st["min_s"], round(raw / 10.0) * 10)))
        flags = []
        if raw < st["min_s"]:
            flags.append("tiny")
        if raw > st["max_s"]:
            flags.append("thick")
        heat, heated = heat_score(t)
        if heated:
            flags.append("heat")
        c["flags"], c["heat_hits"] = flags, heat
        c["scene_breaks"] = sum(1 for ln in t.split("\n") if SCENE_BREAK_RE.match(ln))
    cdir = os.path.join(out, "chapters")
    clear_generated(cdir)
    for c in chapters:
        fn = "%s-%s.txt" % (c["id"][2:], _slug(c["title"]))
        with open(os.path.join(cdir, fn), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(texts[c["id"]].rstrip() + "\n")
        c["file"] = "chapters/" + fn
    bd["chapters"] = chapters
    bd["words"] = sum(c["words"] for c in chapters)
    with open(os.path.join(out, "breakdown.json"), "w", encoding="utf-8", newline="\n") as fh:
        json.dump(bd, fh, indent=1, ensure_ascii=False)
    return bd


# ------------------------------------------------------------------ cli

def cmd_extract(a) -> int:
    if a.text:
        try:
            with open(a.text, encoding="utf-8", errors="replace") as fh:
                pages = pages_from_text(fh.read())
        except OSError as exc:
            print(f"FAIL: cannot read {a.text}: {exc}")
            return 2
        source = os.path.basename(a.text)
    elif a.pdf:
        if not os.path.isfile(a.pdf):
            print(f"FAIL: no such file {a.pdf}")
            return 2
        pages = read_pdf_pages(a.pdf)
        source = os.path.basename(a.pdf)
        if not has_text_layer(pages):
            print("FAIL: this PDF has no text layer (it looks scanned). Run OCR first (for example `ocrmypdf`), then "
                  "pass the text with --text. Scanned books are not supported directly.")
            return 1
    else:
        print("FAIL: give a PDF or --text")
        return 2
    pages = clean_pages(pages)
    det = detect_chapters(pages, a.heading_regex)
    built = build_chapters(pages, det, a.wpfm, a.min_s, a.max_s)
    if a.split_words and len(built["chapters"]) == 1:
        # no headings: cut the whole text at scene breaks into roughly N-word chapters
        whole = built["chapters"][0]["text"]
        parts = max(2, round(count_words(whole) / a.split_words))
        segs = _split_text(whole, parts)
        built["chapters"] = []
        for i, s in enumerate(segs, 1):
            w = count_words(s)
            raw = w / a.wpfm * 60.0
            built["chapters"].append({
                "id": "ch%02d" % i, "number": i, "kind": "chapter", "title": "Section %d" % i, "start_page": 0,
                "end_page": 0, "words": w, "raw_runtime_s": int(raw),
                "runtime_s": int(min(a.max_s, max(a.min_s, round(raw / 10.0) * 10))),
                "flags": (["tiny"] if raw < a.min_s else []) + (["thick"] if raw > a.max_s else []) +
                         (["heat"] if heat_score(s)[1] else []),
                "scene_breaks": 0, "heat_hits": heat_score(s)[0], "text": s})
        built["warnings"].append("no headings: split into %d sections at scene breaks (--split-words %d)" % (len(segs), a.split_words))
    settings = {"words_per_film_minute": a.wpfm, "min_s": a.min_s, "max_s": a.max_s}
    title = a.title or os.path.splitext(source)[0]
    bd = write_outputs(a.out, title, source, pages, built, settings)
    bd["toc_pages"] = det["toc_pages"]
    print(render_table(bd))
    return 0


def cmd_table(a) -> int:
    print(render_table(_load_breakdown(a.dir)))
    return 0


def cmd_adjust(a) -> int:
    bd = adjust(a.dir, a.merge or [], a.split or [], a.drop or [])
    print(render_table(bd))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Book to chapters, runtimes and flags (free).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("pdf", nargs="?")
    e.add_argument("--text")
    e.add_argument("--out", required=True)
    e.add_argument("--title")
    e.add_argument("--wpfm", type=int, default=WORDS_PER_FILM_MINUTE, help="book words per minute of film")
    e.add_argument("--min-s", type=int, default=MIN_S)
    e.add_argument("--max-s", type=int, default=MAX_S)
    e.add_argument("--heading-regex")
    e.add_argument("--split-words", type=int, default=0)
    e.set_defaults(fn=cmd_extract)
    t = sub.add_parser("table")
    t.add_argument("dir")
    t.set_defaults(fn=cmd_table)
    j = sub.add_parser("adjust")
    j.add_argument("dir")
    j.add_argument("--merge", action="append")
    j.add_argument("--split", action="append")
    j.add_argument("--drop", action="append")
    j.set_defaults(fn=cmd_adjust)
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
