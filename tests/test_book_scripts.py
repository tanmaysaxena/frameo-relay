"""Tests for the book-production scripts: conductor/scripts/chapter_driver.py, conductor/scripts/lipsync_plan.py and
finish-cut/scripts/cut_builder.py. Tiny synthetic job folders, no network. Run: python -m pytest tests -q"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
ROOT = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(ROOT, "skills", "conductor", "scripts"))
sys.path.insert(0, os.path.join(ROOT, "skills", "finish-cut", "scripts"))
import chapter_driver as cd  # noqa: E402
import cut_builder as cb  # noqa: E402
import lipsync_plan as lp  # noqa: E402

IMG = "https://img.example/"
CLIPS = "https://vid.example/"
SPEECH = "https://aud.example/"


def run(main, argv, stdin=None):
    out = io.StringIO()
    old = sys.stdin
    if stdin is not None:
        sys.stdin = io.StringIO(stdin)
    try:
        with contextlib.redirect_stdout(out):
            rc = main(argv)
    finally:
        sys.stdin = old
    return rc, out.getvalue()


def relay_doc(n_shots=3):
    segs = []
    for i in range(1, n_shots + 1):
        segs.append({"id": "s%02d" % i, "duration_s": 8, "refs_used": ["neha", "lakshay", "office", "style-ref"],
                     "keyframe_prompt": "KF prompt %d" % i, "prompt": "Clip prompt %d" % i})
    segs[1]["refs_used"] = ["neha", "neha-party", "office", "style-ref"]
    locks = [
        {"id": "neha", "kind": "character", "media_id": "m1", "shared_from": "bible:neha"},
        {"id": "neha-party", "kind": "character", "media_id": "m2", "shared_from": "bible:neha-party", "variant_of": "bible:neha"},
        {"id": "lakshay", "kind": "character", "media_id": "m3", "shared_from": "bible:lakshay"},
        {"id": "office", "kind": "location", "media_id": "m4", "shared_from": "bible:office"},
        {"id": "style-ref", "kind": "style", "media_id": "m5", "shared_from": "bible:style-ref"},
        {"id": "narrator", "kind": "character", "voice_only": True, "voice_id": "v-nar"},
        {"id": "chapter-only", "kind": "prop", "media_id": "m9"},
    ]
    locks[0]["voice_id"] = "v-neha"
    locks[2]["voice_id"] = "v-lak"
    return {"version": 1,
            "job": {"id": "j", "aspect_ratio": "9:16", "resolution": "720p", "model": "seedance_2_5"},
            "style": {"anchor": "A", "reference_lock_ids": ["style-ref"], "avoid": ["clothed only"]},
            "dialogue": {"lines": [
                {"id": "l1", "segment": "s01", "speaker": "neha", "text": "Hello  there", "language": "en"},
                {"id": "l2", "segment": "s01", "speaker": "lakshay", "text": "Hi", "language": "en"},
                {"id": "n1", "segment": "s02", "speaker": "narrator", "text": "Meanwhile", "language": "en"},
                {"id": "p1", "segment": "s03", "speaker": "lakshay", "text": "Call me", "language": "en", "bubble": "phone"},
            ]},
            "locks": {"items": locks},
            "chains": [{"id": "c1", "scene_ids": ["a"], "segments": segs}]}


def bible_doc():
    return {"characters": [
        {"id": "neha", "name": "Neha", "images": [IMG + "neha.png"],
         "variants": [{"id": "neha-party", "state": "black evening dress", "images": [IMG + "neha-party.png"]}]},
        {"id": "lakshay", "name": "Lakshay", "images": [IMG + "lakshay.png"]}],
        "locations": [{"id": "office", "name": "the office", "plates": [IMG + "office.png"]}],
        "props": [], "styles": [{"id": "style-ref", "refs": [IMG + "style.png"]}]}


def put(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def get(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class JobCase(unittest.TestCase):
    n_shots = 3

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.job = os.path.join(self.tmp.name, "frameo-jobs", "book", "ch01")
        self.bible = os.path.join(self.tmp.name, "book", "bible.json")
        put(os.path.join(self.job, "relay.json"), relay_doc(self.n_shots))
        put(self.bible, bible_doc())

    def drv(self, *argv, stdin=None):
        return run(cd.main, list(argv), stdin)

    def p(self, *parts):
        return os.path.join(self.job, *parts)


class DriverTests(JobCase):
    def test_init_reads_assets_from_the_bible_and_reports_gaps(self):
        rc, out = self.drv("init", self.job, "--bible", self.bible)
        st = get(self.p("state.json"))
        self.assertEqual(rc, 0)
        self.assertEqual(st["assets"]["neha"], IMG + "neha.png")
        self.assertEqual(st["assets"]["style-ref"], IMG + "style.png")
        self.assertEqual(st["labels"]["neha-party"], "the model sheet of NEHA in black evening dress")
        self.assertEqual(st["kinds"]["office"], "location")
        self.assertEqual(st["supersedes"], {"neha-party": "neha"})
        self.assertNotIn("narrator", st["assets"])          # voice-only: never an image
        self.assertIn("chapter-only", out)                   # no link anywhere: reported, not invented
        self.assertNotIn("chapter-only", st["assets"])

    def test_init_takes_missing_assets_from_a_file_and_is_strict_on_request(self):
        rc, _ = self.drv("init", self.job, "--bible", self.bible, "--strict")
        self.assertEqual(rc, 1)
        extra = os.path.join(self.tmp.name, "assets.json")
        put(extra, {"chapter-only": {"url": IMG + "prop.png", "kind": "prop", "label": "the prop image of the ring"}})
        rc, _ = self.drv("init", self.job, "--bible", self.bible, "--assets", extra, "--strict")
        self.assertEqual(rc, 0)
        self.assertEqual(get(self.p("state.json"))["labels"]["chapter-only"], "the prop image of the ring")

    def test_init_finds_the_bible_through_the_series_block_and_keeps_results(self):
        r = relay_doc(self.n_shots)
        r["series"] = {"bible": "book/bible.json"}
        put(self.p("relay.json"), r)
        put(self.p("state.json"), {"kf": {"1": "keep"}})
        self.drv("init", self.job)
        st = get(self.p("state.json"))
        self.assertEqual(st["kf"], {"1": "keep"})
        self.assertIn("neha", st["assets"])

    def test_kf_draft_orders_references_and_drops_the_superseded_sheet(self):
        self.drv("init", self.job, "--bible", self.bible)
        rc, out = self.drv("kf", self.job, "1", "2")
        items = get(self.p("calls", "kf_1_2.draft.json"))
        self.assertEqual(rc, 0)
        self.assertEqual(items[0]["image_urls"], [IMG + "neha.png", IMG + "lakshay.png", IMG + "office.png", IMG + "style.png"])
        self.assertEqual(items[1]["image_urls"], [IMG + "neha-party.png", IMG + "office.png", IMG + "style.png"])
        self.assertNotIn(IMG + "neha.png", items[1]["image_urls"])          # neha-party supersedes neha
        self.assertIn("1 = the model sheet of NEHA", items[0]["prompt"])
        self.assertTrue(items[0]["prompt"].endswith("KF prompt 1"))
        self.assertEqual((items[0]["model"], items[0]["aspect_ratio"], items[0]["resolution"]), ("nano-banana-pro", "9:16", "2K"))
        est = json.loads(re.search(r"EST=(.*)", out).group(1))
        self.assertEqual(est[0]["kind"], "image")
        self.assertEqual(est[0]["prompt"], "draft for pricing")
        self.assertNotIn("index", est[0])

    def test_clip_needs_a_recorded_keyframe_then_builds_from_it(self):
        self.drv("init", self.job, "--bible", self.bible)
        rc, out = self.drv("clip", self.job, "1", "1")
        self.assertEqual(rc, 2)
        self.assertIn("no recorded", out)
        self.drv("record", self.job, "kf", "1=abc-123")
        self.assertEqual(get(self.p("state.json"))["kf"]["1"], cd.DEFAULT_PREFIXES["image"] + "abc-123.png")  # bare id expanded
        rc, out = self.drv("clip", self.job, "1", "1")
        it = get(self.p("calls", "clip_1_1.draft.json"))[0]
        self.assertEqual(rc, 0)
        self.assertEqual(it["first_frame_url"], cd.DEFAULT_PREFIXES["image"] + "abc-123.png")
        self.assertEqual(it["reference_image_urls"], [IMG + "neha.png", IMG + "lakshay.png"])   # characters only
        self.assertEqual((it["model"], it["resolution"], it["duration"]), ("seedance_2_5", "720p", 8))
        self.assertEqual(json.loads(re.search(r"EST=(.*)", out).group(1))[0]["kind"], "video")

    def test_gen_merges_quotes_and_refuses_a_count_mismatch(self):
        self.drv("init", self.job, "--bible", self.bible)
        self.drv("kf", self.job, "1", "2")
        rc, out = self.drv("gen", self.job, "kf_1_2", "q1")
        self.assertEqual(rc, 2)
        self.assertFalse(os.path.exists(self.p("calls", "kf_1_2.json")))
        rc, out = self.drv("gen", self.job, "kf_1_2", "q1,q2")
        saved = get(self.p("calls", "kf_1_2.json"))
        self.assertEqual([i["quote_id"] for i in saved], ["q1", "q2"])
        self.assertEqual(json.loads(out), saved)

    def test_retake_appends_the_lock_and_gen_strips_the_shot_number(self):
        self.drv("init", self.job, "--bible", self.bible)
        self.drv("record", self.job, "kf", "2=k2,3=k3")
        rc, out = self.drv("retake", self.job, "2,3", "--lock", "Identity lock.", "--extra", "No hats.")
        items = get(self.p("calls", "retake_2_3.draft.json"))
        self.assertEqual(items[0]["prompt"], "Clip prompt 2 Identity lock. No hats.")
        self.assertEqual([i["shot_number"] for i in items], [2, 3])
        self.assertNotIn("shot_number", json.loads(re.search(r"EST=(.*)", out).group(1))[0])
        self.drv("gen", self.job, "retake_2_3", "qa,qb")
        self.assertNotIn("shot_number", get(self.p("calls", "retake_2_3.json"))[0])

    def test_rkf_and_rclip_use_the_spec(self):
        self.drv("init", self.job, "--bible", self.bible)
        spec = os.path.join(self.tmp.name, "spec.json")
        put(spec, {"masters": {"room": ["https://m.example/room.jpg"]},
                   "keyframe_tail": "No text.", "clip_tail": "No logos.", "replace": [["flush", "tension"]],
                   "shots": {"2": {"master": "room", "keyframe_lock": "Hair in a bun.", "clip_lock": "Keep outfits.",
                                   "action": "She feels a flush — and stops."}}})
        rc, out = self.drv("rkf", self.job, "2", "--spec", spec)
        it = get(self.p("calls", "rkf_2.draft.json"))[0]
        self.assertEqual(rc, 0)
        self.assertEqual(it["image_urls"], [IMG + "neha-party.png", "https://m.example/room.jpg", IMG + "style.png"])
        self.assertIn("2 = the SCENE MASTER", it["prompt"])
        self.assertIn("Hair in a bun. Shot: KF prompt 2. No text.", it["prompt"])
        self.drv("record", self.job, "rkf", "2=https://r.example/rk.png")
        rc, out = self.drv("rclip", self.job, "2", "--spec", spec)
        c = get(self.p("calls", "rclip_2.draft.json"))[0]
        self.assertEqual(rc, 0)
        self.assertEqual(c["prompt"], "She feels a tension - and stops. Keep outfits. No logos.")
        self.assertEqual(c["first_frame_url"], "https://r.example/rk.png")

    def test_record_and_ledger_write_state_and_rows(self):
        self.drv("record", self.job, "clip", "1=u1,2=u2")
        st = get(self.p("state.json"))
        self.assertEqual(st["clip"]["2"], cd.DEFAULT_PREFIXES["video"] + "u2.mp4")
        rc, out = self.drv("record", self.job, "clip", "3=https://x.example/3.mp4")
        self.assertIn("missing shots (0)", out)
        self.drv("ledger", self.job, "clip", "1=g1,2=g2", "--credits", "224")
        self.drv("ledger", self.job, "rkf", "2=g3", "--credits", "18.5")
        rows = [json.loads(x) for x in open(self.p("ledger.jsonl"), encoding="utf-8")]
        self.assertEqual([(r["kind"], r["segment"], r["credits_charged"]) for r in rows],
                         [("clip", "s01", 224), ("clip", "s02", 224), ("retake", "s02", 18.5)])
        self.assertFalse(any(r["refunded"] for r in rows))
        self.assertEqual(get(self.p("state.json"))["clip_gen"], {"1": "g1", "2": "g2"})

    def test_speech_batching_estimates_with_a_stub_for_short_lines(self):
        long_text = "word " * 30
        r = relay_doc(self.n_shots)
        r["dialogue"]["lines"][1]["text"] = long_text
        put(self.p("relay.json"), r)
        rc, out = self.drv("speech-items", self.job, "--language-code", "en-IN")
        items = get(self.p("speech_items.json"))
        self.assertEqual(len(items), 4)
        self.assertEqual(items[0]["text"], "Hello  there")
        self.assertEqual(items[2]["voice_id"], "v-nar")
        self.assertEqual(get(self.p("lines_by_shot.json")), {"1": ["l1", "l2"], "2": ["n1"], "3": ["p1"]})
        rc, out = self.drv("speech-est", self.job, "0", "2")
        est = json.loads(re.search(r"EST=(.*)", out).group(1))
        self.assertEqual(est[0], {"kind": "speech", "voice_id": "v-neha", "text": "x", "language_code": "en-IN"})
        self.assertEqual(est[1]["text"], long_text.strip())
        self.drv("speech-gen", self.job, "0", "ga,gb", "--credits", "1,2")
        self.assertEqual(get(self.p("speech_gen.json")), {"l1": "ga", "l2": "gb"})
        rows = [json.loads(x) for x in open(self.p("ledger.jsonl"), encoding="utf-8")]
        self.assertEqual([(r["kind"], r["segment"], r["credits_charged"]) for r in rows], [("speech", "l1", 1), ("speech", "l2", 2)])
        self.drv("speech-urls", self.job, "0", stdin="aud1 2.5\nhttps://other.example/b.mp3 1.25\n")
        u = get(self.p("speech_urls.json"))
        self.assertEqual(u["l1"], {"url": cd.DEFAULT_PREFIXES["audio"] + "aud1.mp3", "dur": 2.5})
        self.assertEqual(u["l2"]["dur"], 1.25)
        rc, out = self.drv("speech-urls", self.job, "0", stdin="onlyonefield\n")
        self.assertEqual(rc, 2)

    def test_speaker_without_a_voice_is_an_error(self):
        r = relay_doc(self.n_shots)
        r["dialogue"]["lines"][0]["speaker"] = "ghost"
        put(self.p("relay.json"), r)
        rc, out = self.drv("speech-items", self.job)
        self.assertEqual(rc, 2)
        self.assertIn("ghost", out)

    def test_briefs_cover_only_finished_clips(self):
        self.drv("init", self.job, "--bible", self.bible)
        self.drv("record", self.job, "kf", "1=k1")
        self.drv("record", self.job, "clip", "1=https://x.example/1.mp4")
        rc, out = self.drv("briefs", self.job)
        files = sorted(os.listdir(self.p("reviews")))
        self.assertEqual(files, ["brief-01.md"])
        txt = open(self.p("reviews", "brief-01.md"), encoding="utf-8").read()
        self.assertIn("On screen: NEHA, LAKSHAY", txt)
        self.assertIn("Content ceiling for this job: clothed only", txt)
        self.assertIn("Clip prompt 1", txt)

    def test_a_missing_relay_is_reported_not_a_traceback(self):
        rc, out = self.drv("kf", self.tmp.name, "1", "1")
        self.assertEqual(rc, 2)
        self.assertIn("no relay.json", out)


class CutCase(JobCase):
    n_shots = 18

    def setUp(self):
        super().setUp()
        r = relay_doc(self.n_shots)
        # shot 1: neha + lakshay talk; shot 2 narrator; shot 3 phone; shot 5 nolip speaker; shot 6 narrator + neha later
        r["dialogue"]["lines"].append({"id": "l5", "segment": "s05", "speaker": "neha", "text": "Silhouette", "language": "en"})
        r["dialogue"]["lines"].append({"id": "l6", "segment": "s06", "speaker": "neha", "text": "A long line", "language": "en"})
        put(self.p("relay.json"), r)
        put(self.p("state.json"), {
            "clip": {str(i): CLIPS + "c%d.mp4" % i for i in range(1, 19)},
            "rclip": {"4": CLIPS + "r4.mp4"}, "gclip": {"7": CLIPS + "g7.mp4"}})
        put(self.p("speech_urls.json"), {
            "l1": {"url": SPEECH + "l1.mp3", "dur": 2.0}, "l2": {"url": SPEECH + "l2.mp3", "dur": 1.0},
            "n1": {"url": SPEECH + "n1.mp3", "dur": 3.0}, "p1": {"url": SPEECH + "p1.mp3", "dur": 1.5},
            "l5": {"url": SPEECH + "l5.mp3", "dur": 1.0}, "l6": {"url": SPEECH + "l6.mp3", "dur": 12.0}})
        put(self.p("cut_spec.json"), {"use": {"7": "gclip"}, "trim": {"8": [[0, 4.8], [6.0, None]]},
                                      "nolip": [5], "keep_len": [9]})

    def build(self, *extra):
        rc, out = run(cb.main, ["build", self.job] + list(extra))
        self.assertEqual(rc, 0, out)
        return out


class CutBuilderTests(CutCase):
    def test_sources_follow_use_then_retake_then_original(self):
        lay = cb.layout(self.job)
        urls = {n: u for n, u, a, b, pad in lay["segs"]}
        self.assertEqual(urls[7], CLIPS + "g7.mp4")      # cut_spec use
        self.assertEqual(urls[4], CLIPS + "r4.mp4")      # a recorded retake clip wins by default
        self.assertEqual(urls[1], CLIPS + "c1.mp4")

    def test_use_of_an_unrecorded_result_is_an_error(self):
        put(self.p("cut_spec.json"), {"use": {"2": "gclip"}})
        rc, out = run(cb.main, ["build", self.job])
        self.assertEqual(rc, 2)
        self.assertIn("gclip", out)

    def test_pad_extends_a_short_shot_to_fit_its_speech_and_starts_follow(self):
        lay = cb.layout(self.job)
        pads = {n: pad for n, u, a, b, pad in lay["segs"]}
        # shot 1: 8 s picture; need 0.4 + (2+0.35) + (1+0.35) = 4.1 -> no pad
        self.assertEqual(pads[1], 0)
        # shot 6: need 0.4 + 12.35 = 12.75 over an 8 s clip -> 4.75 s hold
        self.assertEqual(pads[6], 4.75)
        self.assertEqual(lay["starts"][2], 8.0)
        self.assertEqual(lay["starts"][7], 8.0 * 5 + 8 + 4.75)   # shots 1..5, then shot 6 with its pad
        # shot 8 is trimmed to [0,4.8] + [6,end] = 4.8 + 2 s
        self.assertAlmostEqual(lay["starts"][9] - lay["starts"][8], 6.8)
        # keep_len pads shot 9 back to its planned 8 s only when it was cut shorter; untouched here
        self.assertEqual(lay["starts"][10] - lay["starts"][9], 8.0)

    def test_keep_len_pads_a_trimmed_shot_back_to_its_planned_length(self):
        put(self.p("cut_spec.json"), {"trim": {"9": [[0, 5.0]]}, "keep_len": [9]})
        lay = cb.layout(self.job)
        self.assertEqual(lay["starts"][10] - lay["starts"][9], 8.0)
        put(self.p("cut_spec.json"), {"trim": {"9": [[0, 5.0]]}})
        lay = cb.layout(self.job)
        self.assertEqual(lay["starts"][10] - lay["starts"][9], 5.0)

    def test_trim_ranges_become_segments_and_the_last_one_takes_the_pad(self):
        lay = cb.layout(self.job)
        s8 = [s for s in lay["segs"] if s[0] == 8]
        self.assertEqual([(a, b) for n, u, a, b, pad in s8], [(0, 4.8), (6.0, None)])

    def test_lip_plan_excludes_narrator_phone_nolip_and_offscreen_voices(self):
        lay = cb.layout(self.job)
        plan = lay["lipplan"]
        self.assertEqual(sorted(plan, key=lambda k: float(k)), ["1.0", "6.0"])   # not 2 (narrator), 3 (phone), 5 (nolip)
        p1 = plan["1.0"]
        self.assertEqual(p1["lines"], [("l1", 0.3), ("l2", 2.65)])
        self.assertEqual(p1["L"], round(2.65 + 1.0 + 0.15, 2))
        self.assertEqual(p1["url"], CLIPS + "c1.mp4")

    def test_a_voice_only_lock_is_never_lipsynced_even_when_not_called_narrator(self):
        r = get(self.p("relay.json"))
        r["locks"]["items"].append({"id": "host", "kind": "character", "voice_only": True, "voice_id": "v-h"})
        r["dialogue"]["lines"].append({"id": "h1", "segment": "s10", "speaker": "host", "text": "x", "language": "en"})
        put(self.p("relay.json"), r)
        su = get(self.p("speech_urls.json"))
        su["h1"] = {"url": SPEECH + "h1.mp3", "dur": 1.0}
        put(self.p("speech_urls.json"), su)
        self.assertNotIn("10.0", cb.layout(self.job)["lipplan"])

    def test_missing_speech_is_named(self):
        su = get(self.p("speech_urls.json"))
        del su["l6"]
        put(self.p("speech_urls.json"), su)
        rc, out = run(cb.main, ["build", self.job])
        self.assertEqual(rc, 2)
        self.assertIn("l6", out)

    def test_picture_parts_hold_at_most_16_segments_and_use_the_job_size(self):
        self.build()
        jobs = get(self.p("jobs", "cut_picture.json"))
        n_segs = len(cb.layout(self.job)["segs"])
        self.assertEqual(len(jobs), 2)
        self.assertEqual(len(jobs[0]["inputs"]), 16)
        self.assertEqual(len(jobs[0]["inputs"]) + len(jobs[1]["inputs"]), n_segs)
        fc = jobs[0]["argv"][jobs[0]["argv"].index("-filter_complex") + 1]
        self.assertIn("scale=720:1280,setsar=1,fps=24[v0]", fc)
        self.assertIn("concat=n=16:v=1:a=0[v]", fc)
        self.assertEqual(jobs[1]["outputs"][0]["name"], "part2.mp4")
        self.assertTrue(os.path.isfile(self.p("jobs", "picture_call1.json")))
        self.build("--part-size", "6", "--size", "540x960")
        jobs = get(self.p("jobs", "cut_picture.json"))
        self.assertEqual(len(jobs), (n_segs + 5) // 6)
        self.assertIn("scale=540:960", jobs[0]["argv"][jobs[0]["argv"].index("-filter_complex") + 1])

    def test_frame_size_follows_resolution_and_aspect(self):
        self.assertEqual(cb.frame_size({"job": {"resolution": "720p", "aspect_ratio": "9:16"}}), (720, 1280))
        self.assertEqual(cb.frame_size({"job": {"resolution": "1080p", "aspect_ratio": "16:9"}}), (1920, 1080))

    def test_a_held_shot_gets_a_tpad_clone(self):
        self.build()
        jobs = get(self.p("jobs", "cut_picture.json"))
        fc = " ".join(j["argv"][j["argv"].index("-filter_complex") + 1] for j in jobs)
        self.assertIn("tpad=stop_mode=clone:stop_duration=4.75", fc)
        self.assertIn("trim=start=6.0,setpts=PTS-STARTPTS", fc)          # open-ended trim window

    def test_voice_track_places_every_line_from_measured_starts(self):
        self.build()
        job = get(self.p("jobs", "cut_voice.json"))
        fc = job["argv"][job["argv"].index("-filter_complex") + 1]
        starts = get(self.p("jobs", "starts.json"))
        self.assertEqual(len(job["inputs"]), 6)
        self.assertIn("[0:a]adelay=300|300", fc)                      # l1 at 0.3 s into shot 1
        self.assertIn("[1:a]adelay=2650|2650", fc)                    # l2 after l1's 2.0 + 0.35
        s2 = int(round((starts["starts"]["2"] + 0.3) * 1000))
        self.assertIn("[2:a]adelay=%d|%d" % (s2, s2), fc)             # narrator in shot 2
        self.assertIn("amix=inputs=6:normalize=0:dropout_transition=0,apad=whole_dur=%s[voice]" % round(starts["total"], 2), fc)

    def test_a_retake_that_changes_a_length_moves_later_voice_starts(self):
        a = cb.layout(self.job)["events"]
        spec = get(self.p("cut_spec.json"))
        spec["trim"]["1"] = [[0, 3.0]]          # shot 1 is now 3 s (its speech needs 4.1: pad 1.1)
        put(self.p("cut_spec.json"), spec)
        b = cb.layout(self.job)["events"]
        self.assertEqual(a[0], b[0])
        self.assertEqual(round(b[2][1] - a[2][1], 3), round(4.1 - 8.0, 3))

    def test_music_beds_follow_sections_and_loop_to_fit(self):
        put(self.p("music_urls.json"), {
            "tracks": {"a": {"url": "https://m.example/a.mp3", "dur": 20.0}, "b": {"url": "https://m.example/b.mp3", "dur": 30.0}},
            "sections": [{"from": 1, "to": 2, "tracks": ["a"]}, {"from": 3, "to": 4, "tracks": ["a", "b"]}]})
        self.build()
        job = get(self.p("jobs", "cut_music.json"))
        starts = get(self.p("jobs", "starts.json"))["starts"]
        fc = job["argv"][job["argv"].index("-filter_complex") + 1]
        # section 1..2 is 16 s: one bed of 16 s from 0
        self.assertIn("[0:a]atrim=duration=16.0,afade=t=in:d=1.5,afade=t=out:st=14.0:d=2.0,adelay=0|0,volume=0.2[m0]", fc)
        s3 = int(round(starts["3"] * 1000))
        self.assertIn("adelay=%d|%d,volume=0.2[m1]" % (s3, s3), fc)
        self.assertEqual(job["outputs"][0]["name"], "music.mp3")
        self.build("--music-gain", "0.35")
        mj = get(self.p("jobs", "cut_music.json"))
        self.assertIn("volume=0.35[m0]", mj["argv"][mj["argv"].index("-filter_complex") + 1])

    def test_no_music_file_means_no_music_job(self):
        self.build()
        self.assertFalse(os.path.exists(self.p("jobs", "cut_music.json")))

    def test_music_section_with_an_unknown_track_fails_clearly(self):
        put(self.p("music_urls.json"), {"tracks": {}, "sections": [{"from": 1, "to": 2, "tracks": ["zz"]}]})
        rc, out = run(cb.main, ["build", self.job])
        self.assertEqual(rc, 2)
        self.assertIn("zz", out)

    def test_final_join_stretches_by_planned_over_actual_and_loudnorms(self):
        put(self.p("music_urls.json"), {"tracks": {"a": {"url": "https://m.example/a.mp3", "dur": 400.0}},
                                        "sections": [{"from": 1, "to": 18, "tracks": ["a"]}]})
        self.build()
        total = get(self.p("jobs", "starts.json"))["total"]
        run(cb.main, ["outputs", self.job, "part1=https://o.example/p1.mp4", "part2=https://o.example/p2.mp4",
                      "voice=https://o.example/v.mp3", "music=https://o.example/m.mp3"])
        actual = round(total + 1.0, 2)
        rc, out = run(cb.main, ["final", self.job, "--actual", str(actual)])
        self.assertEqual(rc, 0, out)
        job = get(self.p("jobs", "final.json"))
        fc = job["argv"][job["argv"].index("-filter_complex") + 1]
        self.assertEqual([i["name"] for i in job["inputs"]], ["part1.mp4", "part2.mp4", "voice.mp3", "music.mp3"])
        self.assertIn("concat=n=2:v=1:a=0,setpts=PTS*%.6f,format=yuv420p[v]" % (total / actual), fc)
        self.assertIn("[2:a][3:a]amix=inputs=2:normalize=0:dropout_transition=0,loudnorm=I=-16:TP=-1.5:LRA=11[a]", fc)
        self.assertEqual(job["argv"][job["argv"].index("-t") + 1], "%.2f" % total)
        self.assertEqual(job["outputs"][0]["name"], "final.mp4")
        rc, out = run(cb.main, ["final", self.job, "--factor", "1.0"])
        self.assertNotIn("setpts", get(self.p("jobs", "final.json"))["argv"][get(self.p("jobs", "final.json"))["argv"].index("-filter_complex") + 1])

    def test_final_refuses_a_wild_stretch_and_both_options(self):
        self.build()
        run(cb.main, ["outputs", self.job, "part1=https://o.example/p1.mp4", "part2=https://o.example/p2.mp4", "voice=https://o.example/v.mp3"])
        rc, out = run(cb.main, ["final", self.job, "--actual", "1000"])
        self.assertEqual(rc, 2)
        rc, out = run(cb.main, ["final", self.job, "--actual", "100", "--factor", "1.0"])
        self.assertEqual(rc, 2)
        rc, out = run(cb.main, ["final", self.job, "--factor", "1.0"])
        self.assertEqual(rc, 0)       # voice only: no music input, no amix
        job = get(self.p("jobs", "final.json"))
        self.assertIn("[2:a]anull,loudnorm", job["argv"][job["argv"].index("-filter_complex") + 1])


class LipsyncTests(CutCase):
    def setUp(self):
        super().setUp()
        self.lip = lambda *a, stdin=None: run(lp.main, list(a), stdin)

    def test_plan_matches_the_cut_builders_plan(self):
        rc, out = self.lip("plan", self.job)
        self.assertEqual(rc, 0, out)
        self.assertEqual(sorted(get(self.p("lip_plan.json"))), ["1.0", "6.0"])

    def test_audio_jobs_delay_each_line_to_clip_time_and_group_pieces(self):
        self.lip("plan", self.job)
        rc, out = self.lip("audio", self.job, "--group", "1")
        jobs = get(self.p("jobs", "lip_audio_grouped.json"))
        self.assertEqual(len(jobs), 2)
        fc = jobs[0]["argv"][jobs[0]["argv"].index("-filter_complex") + 1]
        self.assertEqual(fc, "[0:a]adelay=300|300[x0];[1:a]adelay=2650|2650[x1];[x0][x1]amix=inputs=2:normalize=0:dropout_transition=0[o1_0]")
        self.assertEqual(jobs[0]["outputs"], [{"name": "lip_1_0.mp3", "mime_type": "audio/mpeg"}])
        self.assertEqual([i["url"] for i in jobs[0]["inputs"]], [SPEECH + "l1.mp3", SPEECH + "l2.mp3"])
        self.assertTrue(os.path.isfile(self.p("jobs", "lipcall1.json")))
        self.lip("audio", self.job)                      # grouped by 5: both pieces in one job
        self.assertEqual(len(get(self.p("jobs", "lip_audio_grouped.json"))), 1)

    def full_flow(self):
        self.lip("plan", self.job)
        self.lip("audio-urls", self.job, "1.0=https://a.example/1.mp3", "6.0=https://a.example/6.mp3")

    def test_next_composes_sync3_calls_and_demands_audio_links(self):
        self.lip("plan", self.job)
        rc, out = self.lip("next", self.job, "0", "2")
        self.assertEqual(rc, 2)
        self.full_flow()
        rc, out = self.lip("next", self.job, "0", "2")
        est = json.loads(re.search(r"EST=(.*)", out).group(1))
        self.assertEqual(est[0], {"video_url": CLIPS + "c1.mp4", "audio_url": "https://a.example/1.mp3", "model": "sync-3", "kind": "lipsync"})
        self.assertEqual(len(est), 2)
        self.assertTrue(os.path.isfile(self.p("calls", "lipsync_1_0.draft.json")))

    def test_record_writes_ids_and_optional_ledger_rows(self):
        self.full_flow()
        rc, out = self.lip("record", self.job, "0", "2", "g1,g2", "--credits", "40,300")
        self.assertEqual(get(self.p("lip_gen.json")), {"1.0": "g1", "6.0": "g2"})
        rows = [json.loads(x) for x in open(self.p("ledger.jsonl"), encoding="utf-8")]
        self.assertEqual([(r["kind"], r["credits_charged"]) for r in rows], [("lipsync", 40), ("lipsync", 300)])
        rc, out = self.lip("record", self.job, "0", "2", "only-one")
        self.assertEqual(rc, 2)

    def test_save_writes_results_once_complete_and_the_cut_splices_them(self):
        self.full_flow()
        rc, out = self.lip("save", self.job, "0", stdin="lipA\n")
        self.assertFalse(os.path.exists(self.p("lip_results.json")))
        rc, out = self.lip("save", self.job, "1", stdin="https://l.example/6.mp4\n")
        res = get(self.p("lip_results.json"))
        plan = get(self.p("lip_plan.json"))
        self.assertEqual(res["1.0"]["url"], cd.DEFAULT_PREFIXES["video"] + "lipA.mp4")
        self.assertEqual(res["1.0"]["L"], round(plan["1.0"]["L"] - 0.15, 2))
        lay = cb.layout(self.job)
        s1 = [s for s in lay["segs"] if s[0] == 1]
        self.assertEqual(len(s1), 2)
        self.assertEqual((s1[0][1], s1[0][2], s1[0][3]), (cd.DEFAULT_PREFIXES["video"] + "lipA.mp4", 0, res["1.0"]["L"]))
        self.assertEqual((s1[1][1], s1[1][2], s1[1][3]), (CLIPS + "c1.mp4", res["1.0"]["L"], None))
        # the shot's length does not change when a piece is spliced
        self.assertEqual(lay["starts"][2], 8.0)

    def test_save_accepts_key_value_rows_and_rejects_unknown_pieces(self):
        self.full_flow()
        rc, out = self.lip("save", self.job, "0", stdin="6.0=https://l.example/6.mp4\n1.0=https://l.example/1.mp4\n")
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(self.p("lip_results.json")))
        rc, out = self.lip("save", self.job, "0", stdin="9.9=https://l.example/x.mp4\n")
        self.assertEqual(rc, 2)


class HygieneTests(unittest.TestCase):
    FILES = [("skills", "conductor", "scripts", "chapter_driver.py"), ("skills", "conductor", "scripts", "lipsync_plan.py"),
             ("skills", "finish-cut", "scripts", "cut_builder.py")]

    def test_no_local_paths_ids_or_stdlib_escapes(self):
        for parts in self.FILES:
            text = open(os.path.join(ROOT, *parts), encoding="utf-8").read()
            self.assertNotRegex(text, r"(?<![A-Za-z])[A-Za-z]:[\\/]", parts[-1])
            self.assertNotRegex(text, r"/Users/|/home/", parts[-1])
            imports = set(re.findall(r"^(?:from|import) ([a-zA-Z_.]+)", text, re.M))
            self.assertLessEqual(imports - {"__future__", "argparse", "json", "os", "re", "sys", "urllib.request", "urllib",
                                            "chapter_driver", "cut_builder"}, set(), parts[-1])


if __name__ == "__main__":
    unittest.main()
