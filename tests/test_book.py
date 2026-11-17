"""Tests for the book-breakdown skill: book_extract.py, book_check.py and the `series` block in relay_check.py."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
import random
import sys
from contextlib import redirect_stdout

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import relay_check as rc  # noqa: E402


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bx = _load("book_extract", "skills/book-breakdown/scripts/book_extract.py")
bc = _load("book_check", "skills/book-breakdown/scripts/book_check.py")

WORDS = "river stone morning quiet lantern window bread coat winter harbour letter garden shadow whistle copper bridge candle".split()


def _para(rnd, n):
    return " ".join(rnd.choice(WORDS) for _ in range(n)).capitalize() + "."


def _chapter_pages(rnd, num, title, nwords, extra=""):
    paras, left = [], nwords
    while left > 0:
        n = min(left, 120)
        paras.append(_para(rnd, n))
        left -= n
    pages = ["\n\n".join(paras[i:i + 3]) for i in range(0, len(paras), 3)] or [""]
    head = "Chapter %d: %s" % (num, title)
    pages[0] = head + "\n\n" + pages[0]
    if extra:
        pages[-1] += "\n\n" + extra
    return pages


def make_book_text(tmp_path, with_headings=True) -> str:
    rnd = random.Random(3)
    pages = ["THE LONG LANTERN\nby A. Writer\n",
             "Contents\nChapter 1: The Harbour ........ 5\nChapter 2: The Letter ........ 9\nChapter 3: A Short One ........ 12\n"
             "Chapter 4: Winter Night ........ 13\nChapter 5: The Bridge ........ 20\n"]
    if with_headings:
        pages += _chapter_pages(rnd, 1, "The Harbour", 2400)
        pages += _chapter_pages(rnd, 2, "The Letter", 3300,
                                "* * *\n\nAnna Rao walked on. Anna Rao smiled. Anna Rao waited. Dev Menon came. Dev Menon nodded.")
        pages += _chapter_pages(rnd, 3, "A Short One", 300, "Anna Rao left. Anna Rao sighed. Anna Rao ran.")
        pages += _chapter_pages(rnd, 4, "Winter Night", 1800,
                                "She was naked and aroused, and he moaned. They made love. Her nipple. His erection.")
        last = _chapter_pages(rnd, 5, "The Bridge", 3100)
        last[-1] += "\n\nAcknowledgements\nThanks to everyone."
        pages += last
    else:
        pages += [_para(rnd, 400) for _ in range(12)]
    numbered = ["THE LONG LANTERN\n%s\n\n%d" % (p, i) for i, p in enumerate(pages, 1)]
    path = tmp_path / "book.txt"
    path.write_text("\f".join(numbered), encoding="utf-8")
    return str(path)


def extract(tmp_path, **kw):
    text = make_book_text(tmp_path, kw.pop("with_headings", True))
    out = str(tmp_path / "book")
    argv = ["extract", "--text", text, "--out", out, "--title", "The Long Lantern"]
    for k, v in kw.items():
        argv += ["--" + k.replace("_", "-"), str(v)]
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert bx.main(argv) == 0
    with open(os.path.join(out, "breakdown.json"), encoding="utf-8") as fh:
        return out, json.load(fh), buf.getvalue()


# ----------------------------------------------------------------------------- book_extract

def test_extract_finds_chapters_and_ignores_the_contents_page(tmp_path):
    out, bd, table = extract(tmp_path)
    assert [c["title"] for c in bd["chapters"]] == ["The Harbour", "The Letter", "A Short One", "Winter Night", "The Bridge"]
    assert [c["number"] for c in bd["chapters"]] == [1, 2, 3, 4, 5]
    assert bd["toc_pages"] if "toc_pages" in bd else True
    assert "| ch01 |" in table and "5 chapters" in table
    # running headers and page numbers are gone from the chapter text
    for c in bd["chapters"]:
        text = open(os.path.join(out, c["file"]), encoding="utf-8").read()
        assert "THE LONG LANTERN" not in text


def test_runtime_is_proportional_and_clamped(tmp_path):
    _out, bd, _t = extract(tmp_path)
    ch = {c["id"]: c for c in bd["chapters"]}
    assert ch["ch01"]["runtime_s"] == 180            # 2400 words at 800 per film minute is exactly 3:00
    assert ch["ch02"]["runtime_s"] > ch["ch01"]["runtime_s"]
    assert ch["ch03"]["runtime_s"] == 180 and "tiny" in ch["ch03"]["flags"]   # clamped up to the minimum
    _o, bd2, _t2 = extract(tmp_path, wpfm=100)        # tiny words-per-minute: everything is thick
    big = [c for c in bd2["chapters"] if c["words"] >= 1800]
    assert big and all(c["runtime_s"] == 900 and "thick" in c["flags"] for c in big)
    assert [c for c in bd2["chapters"] if c["id"] == "ch03"][0]["runtime_s"] in (180, 190)   # ~310 words at 100 per minute


def test_heat_flag_and_back_matter(tmp_path):
    _o, bd, _t = extract(tmp_path)
    flags = {c["id"]: c["flags"] for c in bd["chapters"]}
    assert "heat" in flags["ch04"] and "heat" not in flags["ch01"]
    assert any(s["kind"] == "back matter" for s in bd["skipped"])
    assert any(s["kind"] == "front matter" for s in bd["skipped"])


def test_names_json_marks_recurring_names(tmp_path):
    out, _bd, _t = extract(tmp_path)
    names = json.load(open(os.path.join(out, "names.json"), encoding="utf-8"))
    assert names["Anna Rao"]["recurring"] is True and len(names["Anna Rao"]["chapters"]) >= 2
    assert "Dev Menon" not in names                    # only two mentions: below the three-mention threshold
    assert "River" not in names and "Chapter" not in names   # ordinary capitalised words are not names


def test_adjust_merge_split_drop(tmp_path):
    out, bd, _t = extract(tmp_path)
    words = {c["id"]: c["words"] for c in bd["chapters"]}
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert bx.main(["adjust", out, "--merge", "ch03,ch04"]) == 0
    bd2 = json.load(open(os.path.join(out, "breakdown.json"), encoding="utf-8"))
    assert [c["id"] for c in bd2["chapters"]] == ["ch01", "ch02", "ch03", "ch05"]
    assert bd2["chapters"][2]["words"] >= words["ch03"] + words["ch04"] - 5
    assert "heat" in bd2["chapters"][2]["flags"]
    with redirect_stdout(buf):
        assert bx.main(["adjust", out, "--split", "ch02:2"]) == 0
    bd3 = json.load(open(os.path.join(out, "breakdown.json"), encoding="utf-8"))
    assert [c["id"] for c in bd3["chapters"]][:3] == ["ch01", "ch02a", "ch02b"]
    parts = [c["words"] for c in bd3["chapters"] if c["id"].startswith("ch02")]
    assert abs(sum(parts) - bd2["chapters"][1]["words"]) <= 5 and min(parts) > 500
    with redirect_stdout(buf):
        assert bx.main(["adjust", out, "--drop", "ch01"]) == 0
    assert "ch01" not in [c["id"] for c in json.load(open(os.path.join(out, "breakdown.json"), encoding="utf-8"))["chapters"]]
    with pytest.raises(SystemExit):
        bx.main(["adjust", out, "--merge", "ch01,ch05"])     # not neighbours / not existing


def test_no_headings_warns_and_can_split_by_words(tmp_path):
    _o, bd, table = extract(tmp_path, with_headings=False)
    assert len(bd["chapters"]) == 1 and any("no chapter headings" in w for w in bd["warnings"])
    assert "WARNING" in table
    _o2, bd2, _t = extract(tmp_path, with_headings=False, split_words=1200)
    assert len(bd2["chapters"]) >= 3


def test_heading_regex_override(tmp_path):
    _o, bd, _t = extract(tmp_path, with_headings=True, heading_regex=r"^Chapter \d+: (.*)$")
    assert len(bd["chapters"]) == 5


def test_scanned_pdf_is_detected():
    assert bx.has_text_layer(["word " * 100, "word " * 100]) is True
    assert bx.has_text_layer(["", "  \n", ""]) is False
    assert bx.has_text_layer([]) is False


def test_number_parsing():
    assert bx._num_to_int("12") == 12 and bx._num_to_int("IV") == 4 and bx._num_to_int("twenty-one") == 21
    assert bx._num_to_int("seven") == 7 and bx._num_to_int("banana") is None


# ----------------------------------------------------------------------------- book_check

def make_book(tmp_path, budget=20000, created=True):
    out, bd, _t = extract(tmp_path)
    book_path = str(tmp_path / "book" / "book.json")
    with redirect_stdout(io.StringIO()):
        assert bc.main(["init", os.path.join(out, "breakdown.json"), "--out", book_path, "--book-id", "long-lantern",
                        "--budget", str(budget)]) == 0
    book = json.load(open(book_path, encoding="utf-8"))
    if created:
        book["frameo"] = {"workspace_id": "w", "project_id": "p", "bible_module_id": "m0"}
        for i, c in enumerate(book["chapters"], 1):
            c["module_id"] = "m%d" % i
    json.dump(book, open(book_path, "w", encoding="utf-8"), indent=1)
    return book_path, book


def run_check(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = bc.main(argv)
    return code, buf.getvalue()


def test_init_builds_chapters_with_caps_and_null_ceilings(tmp_path):
    _p, book = make_book(tmp_path, created=False)
    assert [c["id"] for c in book["chapters"]] == ["ch01", "ch02", "ch03", "ch04", "ch05"]
    assert all(c["ceiling"] is None and c["status"] == "draft" and c["module_id"] is None for c in book["chapters"])
    assert book["chapters"][0]["module_name"].startswith("Ch01 - ")
    total = sum(c["runtime_s"] for c in book["chapters"])
    c1 = book["chapters"][0]
    assert abs(c1["cap_credits"] - 20000 * c1["runtime_s"] / total * 1.25) <= 1


def test_allocate_is_proportional_with_headroom(tmp_path):
    p, book = make_book(tmp_path)
    caps = {cid: (s, cap) for cid, s, cap in bc.compute_caps(book)}
    assert abs(sum(s for s, _c in caps.values()) - 20000) < 1e-6
    assert all(abs(c - s * 1.25) < 1e-6 for s, c in caps.values())
    code, out = run_check(["allocate", p, "--write"])
    assert code == 0 and "| ch01 |" in out


def test_validate_passes_a_fresh_book_and_strict_flags_open_ceilings(tmp_path):
    p, _b = make_book(tmp_path)
    code, out = run_check(["validate", p])
    assert code == 0, out
    code, out = run_check(["validate", p, "--strict"])
    assert code == 1 and "flagged heat" in out        # ch04 is flagged heat and has no ceiling yet


def test_each_chapter_needs_its_own_module(tmp_path):
    p, book = make_book(tmp_path)
    book["chapters"][1]["module_id"] = book["chapters"][0]["module_id"]
    json.dump(book, open(p, "w", encoding="utf-8"))
    code, out = run_check(["validate", p])
    assert code == 1 and "shares module" in out
    book["chapters"][1]["shared_module_reason"] = "ch02 is a continuation of ch01 on purpose"
    json.dump(book, open(p, "w", encoding="utf-8"))
    assert run_check(["validate", p])[0] == 0
    book["chapters"][2]["module_id"] = "m0"            # the bible module
    json.dump(book, open(p, "w", encoding="utf-8"))
    code, out = run_check(["validate", p])
    assert code == 1 and "Series Bible module" in out
    book["chapters"][2]["module_id"] = None
    json.dump(book, open(p, "w", encoding="utf-8"))
    code, out = run_check(["validate", p])
    assert code == 1 and "no module_id" in out


def test_approved_chapter_needs_a_ceiling_and_a_job_file(tmp_path):
    p, book = make_book(tmp_path)
    book["chapters"][0]["status"] = "approved"
    json.dump(book, open(p, "w", encoding="utf-8"))
    code, out = run_check(["validate", p])
    assert code == 1 and "no content ceiling" in out and "relay.json is missing" in out


def test_runtime_outside_window_needs_an_override(tmp_path):
    p, book = make_book(tmp_path)
    book["chapters"][0]["runtime_s"] = 1200
    json.dump(book, open(p, "w", encoding="utf-8"))
    code, out = run_check(["validate", p])
    assert "outside the window" in out
    book["chapters"][0]["override"] = "the finale gets room"
    json.dump(book, open(p, "w", encoding="utf-8"))
    assert "outside the window" not in run_check(["validate", p])[1]


def write_bible(tmp_path, n_chars=3):
    bible = {"book_id": "long-lantern", "characters": [
        {"id": "c%d" % i, "name": "Char %d" % i, "chapters": [1, 2], "images": ["https://example.test/c%d.png" % i],
         "voice": {"voice_id": "VCE%d" % i}, "variants": [{"id": "c%d-red" % i, "chapters": [2]}]} for i in range(n_chars)],
        "locations": [{"id": "harbour", "name": "Harbour", "chapters": [1, 2], "plates": ["https://example.test/h.png"]}],
        "props": [], "styles": [{"id": "style", "refs": ["https://example.test/s.png"], "chapters": [1, 2, 3, 4, 5]}]}
    os.makedirs(tmp_path / "book", exist_ok=True)
    json.dump(bible, open(tmp_path / "book" / "bible.json", "w", encoding="utf-8"))
    return bible


def test_cast_limit_of_thirty(tmp_path):
    p, _b = make_book(tmp_path)
    write_bible(tmp_path, n_chars=31)
    code, out = run_check(["validate", p])
    assert code == 1 and "at most 30" in out
    write_bible(tmp_path, n_chars=30)
    assert run_check(["validate", p])[0] == 0


def chapter_relay(tmp_path, book, idx, **series_over):
    c = book["chapters"][idx]
    rj = {"series": dict({"book_id": "long-lantern", "chapter_id": c["id"], "chapter_no": c["number"],
                          "bible": "book/bible.json"}, **series_over),
          "job": {"frameo": {"module_id": c["module_id"]}},
          "locks": {"items": [{"id": "anna", "kind": "character", "shared_from": "bible:c0"},
                              {"id": "dock", "kind": "location", "shared_from": "bible:harbour"}]}}
    d = tmp_path / c["job_dir"]
    os.makedirs(d, exist_ok=True)
    json.dump(rj, open(d / "relay.json", "w", encoding="utf-8"))
    return rj


def test_chapter_relay_must_match_the_book(tmp_path):
    p, book = make_book(tmp_path)
    write_bible(tmp_path)
    chapter_relay(tmp_path, book, 0)
    assert run_check(["validate", p])[0] == 0
    chapter_relay(tmp_path, book, 0, book_id="other-book")
    code, out = run_check(["validate", p])
    assert code == 1 and "does not match this book" in out
    rj = chapter_relay(tmp_path, book, 0)
    rj["locks"]["items"][0]["shared_from"] = "bible:ghost"
    json.dump(rj, open(tmp_path / book["chapters"][0]["job_dir"] / "relay.json", "w", encoding="utf-8"))
    code, out = run_check(["validate", p])
    assert code == 1 and "not in the bible" in out
    rj["locks"]["items"][0]["shared_from"] = "bible:c0"
    rj["job"]["frameo"]["module_id"] = "m0"
    json.dump(rj, open(tmp_path / book["chapters"][0]["job_dir"] / "relay.json", "w", encoding="utf-8"))
    code, out = run_check(["validate", p])
    assert code == 1 and "Series Bible module" in out


def _ledger(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_budget_dashboard_excludes_refunds_and_flags_overruns(tmp_path):
    p, book = make_book(tmp_path, budget=3000)
    cap1 = book["chapters"][0]["cap_credits"]
    _ledger(str(tmp_path / book["chapters"][0]["job_dir"] / "ledger.jsonl"),
            [{"kind": "clip", "credits_charged": 400}, {"kind": "clip", "credits_charged": 390, "refunded": True}])
    _ledger(str(tmp_path / "frameo-jobs" / "long-lantern" / "bible" / "ledger.jsonl"), [{"kind": "reference", "credits_charged": 50}])
    code, out = run_check(["budget", p, "--write"])
    assert code == 0, out
    assert "| ch01 |" in out and "400" in out and "390" not in out.split("| bible")[0].replace("400", "")
    assert "| bible |" in out and "Book total: **450 of 3000**" in out
    assert os.path.isfile(tmp_path / "book" / "dashboard.md")
    _ledger(str(tmp_path / book["chapters"][0]["job_dir"] / "ledger.jsonl"), [{"kind": "clip", "credits_charged": cap1 + 10}])
    code, out = run_check(["budget", p])
    assert code == 1 and "over its cap" in out
    _ledger(str(tmp_path / book["chapters"][1]["job_dir"] / "ledger.jsonl"), [{"kind": "clip", "credits_charged": 5000}])
    assert "over its total budget" in run_check(["budget", p])[1]


def test_sync_plan_batches_imports_and_lists_cast(tmp_path):
    p, book = make_book(tmp_path)
    bible = write_bible(tmp_path)
    for i in range(12):
        bible["locations"].append({"id": "place%d" % i, "chapters": [1, 2], "plates": ["https://example.test/p%d.png" % i]})
    json.dump(bible, open(tmp_path / "book" / "bible.json", "w", encoding="utf-8"))
    rj = chapter_relay(tmp_path, book, 0)
    rj["locks"]["items"] = [{"id": "x%d" % i, "kind": "location", "shared_from": "bible:place%d" % i} for i in range(12)]
    json.dump(rj, open(tmp_path / book["chapters"][0]["job_dir"] / "relay.json", "w", encoding="utf-8"))
    code, out = run_check(["sync-plan", p])
    assert code == 0
    plan = json.loads(out)
    assert len(plan["save_character"]) == 3 and plan["save_character"][0]["voice_id"] == "VCE0"
    batches = [b for b in plan["imports"] if b["chapter"] == "ch01"]
    assert len(batches) == 2 and all(len(b["urls"]) <= 10 for b in batches)
    assert batches[0]["module_id"] == "m1"


# ----------------------------------------------------------------------------- relay_check `series`

def series_job():
    return {"version": 1, "job": {"id": "j", "workspace_id": "w", "aspect_ratio": "9:16", "model": "seedance_2_5",
                                  "frameo": {"project_id": "p", "module_id": "m1"}},
            "series": {"book_id": "b", "chapter_id": "ch01", "chapter_no": 1, "bible": "book/bible.json", "bible_module_id": "m0"},
            "locks": {"items": [{"id": "anna", "kind": "character", "media_id": "x", "shared_from": "bible:anna"}]}}


def test_series_block_is_optional_and_checked():
    d = series_job()
    assert not rc.check_series(d, scratch=False).fails
    plain = copy.deepcopy(d)
    del plain["series"]
    assert rc.check_series(plain, scratch=False).warns          # shared_from without a series block is only a warning
    assert not rc.check_series(plain, scratch=False).fails
    bad = copy.deepcopy(d)
    bad["series"]["chapter_no"] = 0
    assert any("chapter_no" in f for f in rc.check_series(bad, scratch=False).fails)
    bad = copy.deepcopy(d)
    bad["job"]["frameo"]["module_id"] = "m0"                     # the bible module
    assert any("Series Bible module" in f for f in rc.check_series(bad, scratch=False).fails)
    bad = copy.deepcopy(d)
    bad["locks"]["items"][0]["shared_from"] = "anna"
    assert any("bible:<id>" in f for f in rc.check_series(bad, scratch=False).fails)
    bad = copy.deepcopy(d)
    del bad["series"]["book_id"]
    assert any("series.book_id" in f for f in rc.check_series(bad, scratch=False).fails)


def test_a_single_script_job_is_unchanged():
    sample_path = os.path.join(ROOT, "examples", "relay.sample.json")
    d = json.load(open(sample_path, encoding="utf-8"))
    assert "series" not in d
    rep = rc.check_structure(d, scratch=False)
    assert not rep.fails


def test_heat_score_tiers():
    assert bx.heat_score("They had tea by the harbour and talked about bread.") == (0, False)
    score, flagged = bx.heat_score("He felt her thigh and her skin, a moan, a gasp.")      # four soft hits: not enough
    assert score == 4 and flagged is False
    assert bx.heat_score("moan gasp pleasure thighs hips")[1] is True                       # five soft hits
    assert bx.heat_score("She was inside her own thoughts.")[1] is True                    # 'inside her' is a strong term: a prompt to look
    assert bx.heat_score("They made love that night.") == (3, True)


# ----------------------------------------------------------------------------- real PDF round trip

def make_pdf(pages):
    """A minimal valid PDF, one text page per string (lines split on newlines). Standard library only."""
    def esc(s):
        bs = chr(92)
        return s.replace(bs, bs + bs).replace("(", bs + "(").replace(")", bs + ")")
    objs = [None, None, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for text in pages:
        lines = text.split("\n")
        body = "BT /F1 10 Tf 50 760 Td 12 TL\n" + "".join("(%s) Tj T*\n" % esc(ln) for ln in lines) + "ET"
        stream = body.encode("latin-1", errors="replace")
        content_no = len(objs) + 2
        page_no = len(objs) + 1
        objs.append(("<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R "
                     "/Resources << /Font << /F1 3 0 R >> >> >>" % content_no).encode())
        objs.append(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        kids.append("%d 0 R" % page_no)
    objs[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objs[1] = ("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join(kids), len(kids))).encode()
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def _have_pdf_reader():
    import shutil
    if shutil.which("pdftotext"):
        return True
    try:
        import pypdf  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.mark.skipif(not _have_pdf_reader(), reason="needs pdftotext or pypdf")
def test_pdf_round_trip(tmp_path):
    pages = ["THE LONG LANTERN"]
    for n, title in enumerate(["The Harbour", "The Letter", "The Bridge"], 1):
        # lines stay shorter than the page width, otherwise the reader crops them
        pages.append("Chapter %d: %s\n\n%s" % (n, title, ("word " * 10 + "\n") * 30))
        pages.append(("more " * 10 + "\n") * 30)
    pdf = tmp_path / "mini.pdf"
    pdf.write_bytes(make_pdf(pages))
    out = tmp_path / "out"
    buf = io.StringIO()
    with redirect_stdout(buf):
        assert bx.main(["extract", str(pdf), "--out", str(out), "--title", "Mini"]) == 0
    bd = json.load(open(out / "breakdown.json", encoding="utf-8"))
    assert [c["title"] for c in bd["chapters"]] == ["The Harbour", "The Letter", "The Bridge"]
    assert all(c["words"] > 300 for c in bd["chapters"])


@pytest.mark.skipif(not _have_pdf_reader(), reason="needs pdftotext or pypdf")
def test_scanned_pdf_is_refused(tmp_path):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(make_pdf([" ", " ", " "]))          # pages with no text layer
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = bx.main(["extract", str(pdf), "--out", str(tmp_path / "o")])
    assert code == 1 and "no text layer" in buf.getvalue()


def test_extract_never_deletes_foreign_files(tmp_path):
    """--out may point at an existing folder: only the chapter files this script wrote are replaced."""
    out = tmp_path / "book"
    (out / "chapters").mkdir(parents=True)
    mine = out / "chapters" / "my-own-notes.md"
    mine.write_text("keep me", encoding="utf-8")
    other = out / "chapters" / "notes.txt"
    other.write_text("keep me too", encoding="utf-8")
    text = make_book_text(tmp_path)
    for _ in range(2):                                           # a rerun must also leave them alone
        with redirect_stdout(io.StringIO()):
            assert bx.main(["extract", "--text", text, "--out", str(out)]) == 0
    assert mine.read_text(encoding="utf-8") == "keep me" and other.read_text(encoding="utf-8") == "keep me too"
    assert len([p for p in (out / "chapters").iterdir() if p.name[0].isdigit()]) == 5
    with redirect_stdout(io.StringIO()):
        assert bx.main(["adjust", str(out), "--drop", "ch01"]) == 0
    assert mine.exists() and other.exists()


def test_blank_pdftotext_output_is_a_read_not_a_failure(monkeypatch, tmp_path):
    """A scanned PDF makes pdftotext succeed with blank pages; that must reach the 'no text layer' check, not
    fall through to 'no PDF reader found' (this broke on Windows CI)."""
    class Done:
        returncode = 0
        stdout = b"\n\f\n\f\n\f"

    monkeypatch.setattr(bx.shutil, "which", lambda name: "pdftotext")
    monkeypatch.setattr(bx.subprocess, "run", lambda *a, **k: Done())
    pages = bx.read_pdf_pages(str(tmp_path / "x.pdf"))
    assert len(pages) == 4 and bx.has_text_layer(pages) is False

    class Failed:
        returncode = 1
        stdout = b""

    monkeypatch.setattr(bx.subprocess, "run", lambda *a, **k: Failed())
    monkeypatch.setitem(sys.modules, "pypdf", None)      # make `import pypdf` raise ImportError
    monkeypatch.setitem(sys.modules, "fitz", None)
    with pytest.raises(SystemExit) as exc:
        bx.read_pdf_pages(str(tmp_path / "x.pdf"))
    assert "no PDF reader found" in str(exc.value)
