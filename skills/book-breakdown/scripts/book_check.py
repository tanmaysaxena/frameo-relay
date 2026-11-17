#!/usr/bin/env python3
"""book_check.py: book-level contract, budget and sync checks for the book-breakdown skill.

Standard library only. No network, no Frameo calls. Free.

Commands:
  init     BREAKDOWN.json --out book.json --book-id ID [--title T] [--aspect 9:16] [--budget N]
           [--headroom 25] [--retake-allowance 30] [--jobs-dir frameo-jobs/ID]
      Builds a draft book.json from book_extract.py's breakdown.json: one chapter record per chapter with its own
      module name, runtime, flags and a per-chapter cap, and a null content ceiling for you to fill in.
  validate book.json [--strict]
      Structure, runtimes, the one-module-per-chapter rule, caps, ceilings, the bible and each chapter's relay.json.
  allocate book.json [--write]
      Per-chapter caps: share = budget * runtime / total runtime, cap = share * (1 + headroom). Prints them.
  budget   book.json [--write]
      Cost dashboard from the chapters' ledgers: spent, cap, remaining, status. Exit 1 if a chapter is over its cap or
      the book is over its total.
  sync-plan book.json
      What to copy into which chapter module (free import_media_url batches) and which characters to save to the
      project cast, from the bible and each chapter's shared locks.

Exit codes: 0 ok, 1 a check failed, 2 unreadable input.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

ID_RE = re.compile(r"^ch\d{2,3}[a-z]?$")
BIBLE_ID_RE = re.compile(r"^bible:[a-z0-9][a-z0-9_-]*$")
CAST_LIMIT = 30                      # Frameo: at most 30 saved characters per project
IMPORT_BATCH = 10                    # import_media_url: 10 files per call, 10 files a minute per account
STATUSES = ("draft", "planned", "approved", "in_production", "done")
LATE = ("approved", "in_production", "done")


class Report:
    def __init__(self):
        self.fails, self.warns, self.infos = [], [], []

    def fail(self, m): self.fails.append(m)
    def warn(self, m): self.warns.append(m)
    def info(self, m): self.infos.append(m)

    def print(self) -> int:
        for m in self.infos:
            print("INFO: " + m)
        for m in self.warns:
            print("WARN: " + m)
        for m in self.fails:
            print("FAIL: " + m)
        print("FAIL" if self.fails else "OK")
        return 1 if self.fails else 0


def load(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read {path}: {exc}")
        sys.exit(2)
    if not isinstance(d, dict):
        print(f"FAIL: {path} must hold a JSON object")
        sys.exit(2)
    return d


def nonempty(v) -> bool:
    return isinstance(v, str) and bool(v.strip())


def base_dir(book_path: str, root: str | None = None) -> str:
    """Paths inside book.json (the bible, each chapter's job_dir) are relative to the folder that holds `book/` and
    `frameo-jobs/`: the parent of the folder book.json sits in, or --root."""
    if root:
        return os.path.abspath(root)
    return os.path.dirname(os.path.dirname(os.path.abspath(book_path)))


def read_ledger(path: str) -> list:
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                raise ValueError(f"{path} line {n} is not valid JSON")
    return rows


def net_spent(rows: list) -> float:
    return float(sum((r.get("credits_charged") or 0) for r in rows if not r.get("refunded")))


# ------------------------------------------------------------------ caps

def compute_caps(book: dict) -> list:
    """[(chapter id, share, cap)] by runtime share of the book budget, plus headroom."""
    b = book.get("budget") or {}
    total = b.get("total_credits")
    head = b.get("headroom_pct", 25)
    chapters = book.get("chapters") or []
    rt = sum(c.get("runtime_s") or 0 for c in chapters)
    out = []
    for c in chapters:
        if not isinstance(total, (int, float)) or total <= 0 or rt <= 0:
            out.append((c.get("id"), None, None))
            continue
        share = total * (c.get("runtime_s") or 0) / rt
        out.append((c.get("id"), share, share * (1 + head / 100.0)))
    return out


# ------------------------------------------------------------------ init

def cmd_init(a) -> int:
    with open(a.breakdown, encoding="utf-8") as fh:
        bd = json.load(fh)
    jobs = a.jobs_dir or ("frameo-jobs/" + a.book_id)
    st = bd.get("settings", {})
    book = {
        "version": 1, "book_id": a.book_id, "title": a.title or bd.get("title") or a.book_id,
        "source": bd.get("source"), "aspect_ratio": a.aspect,
        "frameo": {"workspace_id": None, "project_id": None, "bible_module_id": None},
        "runtime": {"min_s": st.get("min_s", 180), "max_s": st.get("max_s", 900),
                    "words_per_film_minute": st.get("words_per_film_minute", 800)},
        "budget": {"total_credits": a.budget, "headroom_pct": a.headroom, "retake_allowance_pct": a.retake_allowance},
        "bible": {"path": "book/bible.json", "module_name": "Series Bible", "ledger": jobs + "/bible/ledger.jsonl"},
        "chapters": [],
    }
    for c in bd["chapters"]:
        book["chapters"].append({
            "id": c["id"], "number": c["number"], "title": c["title"], "kind": c.get("kind", "chapter"),
            "module_name": "%s - %s" % (c["id"].upper().replace("CH", "Ch"), c["title"][:60]),
            "module_id": None, "words": c["words"], "runtime_s": c["runtime_s"], "flags": c.get("flags", []),
            "text_file": c.get("file"), "ceiling": None, "status": "draft", "cap_credits": None,
            "job_dir": jobs + "/" + c["id"]})
    for cid, share, cap in compute_caps(book):
        for c in book["chapters"]:
            if c["id"] == cid and cap is not None:
                c["cap_credits"] = int(round(cap))
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(book, fh, indent=1, ensure_ascii=False)
    print(f"wrote {a.out}: {len(book['chapters'])} chapters")
    return 0


# ------------------------------------------------------------------ validate

def check_book(book: dict, bdir: str, strict: bool) -> Report:
    r = Report()
    if book.get("version") != 1:
        r.fail("version must be 1")
    for key in ("book_id", "title"):
        if not nonempty(book.get(key)):
            r.fail(f"{key} missing")
    if book.get("aspect_ratio") not in ("9:16", "16:9"):
        r.fail("aspect_ratio must be 9:16 or 16:9")
    rt = book.get("runtime") or {}
    lo, hi = rt.get("min_s"), rt.get("max_s")
    if not (isinstance(lo, (int, float)) and isinstance(hi, (int, float)) and 0 < lo <= hi):
        r.fail("runtime.min_s and runtime.max_s must be numbers with 0 < min <= max")
        lo, hi = 0, 10 ** 9
    chapters = book.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        r.fail("chapters must be a non-empty list")
        return r

    fr = book.get("frameo") or {}
    created = nonempty(fr.get("project_id"))
    bible_mod = fr.get("bible_module_id")
    if created and not nonempty(bible_mod):
        r.fail("frameo.bible_module_id missing although the project exists")
    seen_ids, seen_mods = set(), {}
    for c in chapters:
        cid = c.get("id")
        if not (isinstance(cid, str) and ID_RE.match(cid)):
            r.fail(f"chapter id {cid!r} must look like ch01 (or ch07a for a part)")
            continue
        if cid in seen_ids:
            r.fail(f"duplicate chapter id {cid}")
        seen_ids.add(cid)
        rs = c.get("runtime_s")
        if not isinstance(rs, (int, float)) or rs <= 0:
            r.fail(f"{cid}: runtime_s missing")
        elif not (lo <= rs <= hi) and not nonempty(c.get("override")):
            r.warn(f"{cid}: runtime {rs}s is outside the window {lo} to {hi}s and has no `override` reason")
        if c.get("status") not in STATUSES:
            r.fail(f"{cid}: status must be one of {list(STATUSES)}")
        # the one-module-per-chapter rule
        mid = c.get("module_id")
        if created:
            if not nonempty(mid):
                r.fail(f"{cid}: no module_id although the project exists: every chapter takes its own new module")
            else:
                if mid == bible_mod:
                    r.fail(f"{cid}: uses the Series Bible module; every chapter needs its own module")
                if mid in seen_mods and not nonempty(c.get("shared_module_reason")):
                    r.fail(f"{cid}: shares module {mid} with {seen_mods[mid]}; by default every chapter takes a new module "
                           f"(set `shared_module_reason` to override on purpose)")
                seen_mods.setdefault(mid, cid)
        elif strict:
            r.warn(f"{cid}: no Frameo module yet (create the project and modules after the breakdown is confirmed)")
        # content ceiling per chapter
        if c.get("status") in LATE and not nonempty(c.get("ceiling")):
            r.fail(f"{cid}: status {c.get('status')} but no content ceiling chosen for this chapter")
        elif "heat" in (c.get("flags") or []) and not nonempty(c.get("ceiling")):
            (r.fail if strict else r.warn)(f"{cid}: flagged heat, choose its content ceiling in words")
        elif not nonempty(c.get("ceiling")) and strict:
            r.warn(f"{cid}: no content ceiling chosen yet")

    # budget and caps
    b = book.get("budget") or {}
    total = b.get("total_credits")
    if total is None:
        r.warn("budget.total_credits not set: no cap can be enforced")
    elif not isinstance(total, (int, float)) or total <= 0:
        r.fail("budget.total_credits must be a positive number")
    else:
        head = b.get("headroom_pct", 25)
        if not isinstance(head, (int, float)) or head < 0:
            r.fail("budget.headroom_pct must be a number >= 0")
        else:
            caps = {cid: cap for cid, _s, cap in compute_caps(book)}
            for c in chapters:
                cap = c.get("cap_credits")
                want = caps.get(c.get("id"))
                if want is not None and (not isinstance(cap, (int, float)) or abs(cap - want) > max(2.0, want * 0.01)):
                    r.warn(f"{c.get('id')}: cap_credits {cap} differs from the runtime share plus headroom ({want:.0f}); "
                           f"run `allocate --write`")
            r.info("caps sum to %.0f against a book budget of %.0f (headroom is per chapter and not carried over)" % (
                sum(v for v in caps.values() if v), total))

    # bible
    bpath = (book.get("bible") or {}).get("path")
    bible = None
    if nonempty(bpath):
        full = os.path.join(bdir, bpath)
        if os.path.isfile(full):
            try:
                with open(full, encoding="utf-8") as fh:
                    bible = json.load(fh)
            except json.JSONDecodeError as exc:
                r.fail(f"bible {bpath} is not valid JSON: {exc}")
        else:
            (r.fail if any(c.get("status") in LATE for c in chapters) else r.warn)(f"bible file {bpath} not found")
    bible_ids = set()
    if isinstance(bible, dict):
        chars = bible.get("characters") or []
        recurring = [x for x in chars if isinstance(x, dict) and len(x.get("chapters") or []) >= 2]
        if len(chars) > CAST_LIMIT:
            r.fail(f"bible has {len(chars)} characters but a Frameo project's cast holds at most {CAST_LIMIT}: "
                   f"keep the recurring ones (or those needed most) and describe the rest per chapter")
        r.info("bible: %d characters (%d recurring), %d locations" % (len(chars), len(recurring), len(bible.get("locations") or [])))
        for sec in ("characters", "locations", "props", "styles"):
            for it in bible.get(sec) or []:
                if isinstance(it, dict) and nonempty(it.get("id")):
                    bible_ids.add("bible:" + it["id"])
                    for v in it.get("variants") or []:
                        if isinstance(v, dict) and nonempty(v.get("id")):
                            bible_ids.add("bible:" + v["id"])
    # each chapter's relay.json
    for c in chapters:
        job = os.path.join(bdir, c.get("job_dir") or "", "relay.json")
        if not os.path.isfile(job):
            if c.get("status") in LATE:
                r.fail(f"{c.get('id')}: status {c.get('status')} but {c.get('job_dir')}/relay.json is missing")
            continue
        try:
            with open(job, encoding="utf-8") as fh:
                rj = json.load(fh)
        except json.JSONDecodeError as exc:
            r.fail(f"{c.get('id')}: relay.json is not valid JSON: {exc}")
            continue
        ser = rj.get("series")
        if not isinstance(ser, dict):
            r.fail(f"{c.get('id')}: relay.json has no `series` block")
            continue
        if ser.get("book_id") != book.get("book_id"):
            r.fail(f"{c.get('id')}: series.book_id {ser.get('book_id')!r} does not match this book")
        if ser.get("chapter_id") != c.get("id"):
            r.fail(f"{c.get('id')}: series.chapter_id is {ser.get('chapter_id')!r}")
        jm = ((rj.get("job") or {}).get("frameo") or {}).get("module_id")
        if nonempty(c.get("module_id")) and jm and jm != c.get("module_id"):
            r.fail(f"{c.get('id')}: relay.json module {jm} is not the chapter's module {c.get('module_id')}")
        if jm and jm == bible_mod:
            r.fail(f"{c.get('id')}: relay.json points at the Series Bible module")
        for lk in ((rj.get("locks") or {}).get("items") or []):
            sf = lk.get("shared_from")
            if sf is not None and bible_ids and sf not in bible_ids:
                r.fail(f"{c.get('id')}: lock {lk.get('id')} shared_from {sf} is not in the bible")
    r.info("%d chapters, total runtime %d s" % (len(chapters), sum(int(c.get("runtime_s") or 0) for c in chapters)))
    return r


def cmd_validate(a) -> int:
    book = load(a.book)
    return check_book(book, base_dir(a.book, a.root), a.strict).print()


# ------------------------------------------------------------------ allocate and budget

def cmd_allocate(a) -> int:
    book = load(a.book)
    caps = compute_caps(book)
    if all(c[2] is None for c in caps):
        print("FAIL: set budget.total_credits (and runtimes) first")
        return 1
    print("| chapter | runtime | share | cap (+%s%% headroom) |" % (book.get("budget", {}).get("headroom_pct", 25)))
    print("|---|---|---|---|")
    byid = {c["id"]: c for c in book["chapters"]}
    for cid, share, cap in caps:
        print("| %s | %ds | %d | %d |" % (cid, byid[cid].get("runtime_s") or 0, round(share), round(cap)))
        byid[cid]["cap_credits"] = int(round(cap))
    if a.write:
        with open(a.book, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(book, fh, indent=1, ensure_ascii=False)
        print("wrote cap_credits into", a.book)
    return 0


def budget_rows(book: dict, bdir: str):
    rows = []
    for c in book.get("chapters") or []:
        led = os.path.join(bdir, c.get("job_dir") or "", "ledger.jsonl")
        spent = net_spent(read_ledger(led))
        rows.append({"id": c.get("id"), "title": c.get("title"), "status": c.get("status"), "spent": spent,
                     "cap": c.get("cap_credits")})
    bl = (book.get("bible") or {}).get("ledger")
    bible_spent = net_spent(read_ledger(os.path.join(bdir, bl))) if nonempty(bl) else 0.0
    return rows, bible_spent


def render_dashboard(book: dict, rows: list, bible_spent: float) -> tuple:
    total = (book.get("budget") or {}).get("total_credits")
    spent_all = sum(r["spent"] for r in rows) + bible_spent
    problems = []
    lines = ["# Credit dashboard: %s" % book.get("title"), "",
             "| chapter | title | status | spent | cap | % of cap | remaining |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        cap = r["cap"]
        pct = ("%.0f%%" % (100.0 * r["spent"] / cap)) if cap else "-"
        rem = ("%d" % (cap - r["spent"])) if cap else "-"
        mark = ""
        if cap and r["spent"] > cap:
            mark = " OVER"
            problems.append(f"{r['id']} is over its cap ({r['spent']:.0f} > {cap})")
        elif cap and r["spent"] >= 0.8 * cap:
            mark = " near cap"
        lines.append("| %s | %s | %s | %d | %s | %s | %s |%s" % (r["id"], (r["title"] or "")[:40], r["status"], r["spent"],
                                                          cap if cap else "-", pct, rem, mark))
    lines.append("| bible | Series Bible | - | %d | - | - | - |" % bible_spent)
    lines.append("")
    if isinstance(total, (int, float)) and total > 0:
        lines.append("Book total: **%d of %d** credits spent (%.1f%%), %d remaining." % (spent_all, total, 100.0 * spent_all / total, total - spent_all))
        if spent_all > total:
            problems.append(f"the book is over its total budget ({spent_all:.0f} > {total})")
    else:
        lines.append("Book total spent: %d credits (no budget set)." % spent_all)
    return "\n".join(lines), problems


def cmd_budget(a) -> int:
    book = load(a.book)
    bdir = base_dir(a.book, a.root)
    try:
        rows, bible_spent = budget_rows(book, bdir)
    except ValueError as exc:
        print("FAIL: " + str(exc))
        return 2
    text, problems = render_dashboard(book, rows, bible_spent)
    print(text)
    if a.write:
        with open(os.path.join(os.path.dirname(os.path.abspath(a.book)), "dashboard.md"), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text + "\n")
    for p in problems:
        print("FAIL: " + p)
    return 1 if problems else 0


# ------------------------------------------------------------------ sync plan

def cmd_sync(a) -> int:
    book = load(a.book)
    bdir = base_dir(a.book, a.root)
    fr = book.get("frameo") or {}
    bpath = os.path.join(bdir, (book.get("bible") or {}).get("path") or "")
    try:
        with open(bpath, encoding="utf-8") as fh:
            bible = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"FAIL: cannot read the bible {bpath}: {exc}")
        return 2
    chars = [c for c in bible.get("characters") or [] if isinstance(c, dict)]
    cast = [c for c in chars if len(c.get("chapters") or []) >= 2][:CAST_LIMIT]
    plan = {"project_id": fr.get("project_id"), "bible_module_id": fr.get("bible_module_id"),
            "save_character": [], "imports": [], "pending": [], "note": "import_media_url is free: 10 files per call, 10 files per minute per account"}
    for c in cast:
        imgs = [u for u in (c.get("images") or []) if nonempty(u)][:6]
        if imgs:
            plan["save_character"].append({"name": c.get("name") or c.get("id"), "image_urls": imgs, "voice_id": (c.get("voice") or {}).get("voice_id")})
        else:
            plan["pending"].append(f"character {c.get('id')} has no images yet (build the bible first)")
    assets = {}
    for sec in ("locations", "props", "styles"):
        for it in bible.get(sec) or []:
            if isinstance(it, dict) and nonempty(it.get("id")):
                assets["bible:" + it["id"]] = it
    for c in book.get("chapters") or []:
        used = set()
        jp = os.path.join(bdir, c.get("job_dir") or "", "relay.json")
        if os.path.isfile(jp):
            try:
                with open(jp, encoding="utf-8") as fh:
                    rj = json.load(fh)
                for lk in ((rj.get("locks") or {}).get("items") or []):
                    if lk.get("shared_from") in assets:
                        used.add(lk["shared_from"])
            except json.JSONDecodeError:
                plan["pending"].append(f"{c.get('id')}: relay.json is not valid JSON")
        else:
            used = {k for k, v in assets.items() if c.get("id") in (v.get("chapters") or [])}
        urls, names = [], []
        for k in sorted(used):
            it = assets[k]
            for n, u in enumerate([u for u in (it.get("plates") or it.get("images") or []) if nonempty(u)]):
                urls.append(u)
                names.append("%s-%d" % (it["id"], n + 1))
        if not nonempty(c.get("module_id")):
            plan["pending"].append(f"{c.get('id')}: no module yet")
        for i in range(0, len(urls), IMPORT_BATCH):
            plan["imports"].append({"chapter": c.get("id"), "module_id": c.get("module_id"),
                                    "urls": urls[i:i + IMPORT_BATCH], "names": names[i:i + IMPORT_BATCH]})
    print(json.dumps(plan, indent=1))
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Book-level contract, budget and sync checks (free).")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("breakdown")
    i.add_argument("--out", required=True)
    i.add_argument("--book-id", required=True)
    i.add_argument("--title")
    i.add_argument("--aspect", default="9:16")
    i.add_argument("--budget", type=float)
    i.add_argument("--headroom", type=float, default=25)
    i.add_argument("--retake-allowance", type=float, default=30)
    i.add_argument("--jobs-dir")
    i.set_defaults(fn=cmd_init)
    v = sub.add_parser("validate")
    v.add_argument("book")
    v.add_argument("--strict", action="store_true", help="before approval: missing modules and ceilings are failures or warnings")
    v.add_argument("--root", help="folder holding book/ and frameo-jobs/ (default: the parent of book.json's folder)")
    v.set_defaults(fn=cmd_validate)
    al = sub.add_parser("allocate")
    al.add_argument("book")
    al.add_argument("--write", action="store_true")
    al.set_defaults(fn=cmd_allocate)
    b = sub.add_parser("budget")
    b.add_argument("book")
    b.add_argument("--write", action="store_true")
    b.add_argument("--root")
    b.set_defaults(fn=cmd_budget)
    s = sub.add_parser("sync-plan")
    s.add_argument("book")
    s.add_argument("--root")
    s.set_defaults(fn=cmd_sync)
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
