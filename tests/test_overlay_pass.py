"""Tests for skills/finish-cut/scripts/overlay_pass.py. Run: python -m pytest tests/"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "finish-cut", "scripts"))
import overlay_pass as op  # noqa: E402


def make_job(d, scenes=("s1", "s1", "s2", "s2", "s2"), phone=True):
    """A five-shot job: shots 1-2 one place, 3-5 another; 1 has narration, 2 and 3 dialogue, 4 a phone line."""
    segs = []
    for i, sc in enumerate(scenes, 1):
        segs.append({"id": "c%02ds1" % i, "duration_s": 8, "refs_used": ["place-a" if i <= 2 else "place-b"]})
    relay = {
        "job": {"id": "t", "aspect_ratio": "9:16", "resolution": "720p"},
        "locks": {"items": [{"id": "ana", "kind": "character", "voice_id": "V1", "description": "Ana Rao: tall woman"},
                            {"id": "ben", "kind": "character", "voice_id": "V2", "description": "Ben Shah: broad man"},
                            {"id": "place-a", "kind": "location"}, {"id": "place-b", "kind": "location"}]},
        "chains": [{"id": "c%02d" % (i + 1), "scene_ids": ["s%02d" % (i + 1)], "segments": [segs[i]]} for i in range(len(segs))],
        "dialogue": {"lines": [
            {"id": "l1", "segment": "c01s1", "speaker": "narrator", "text": "It was a long night, and she had not slept."},
            {"id": "l2", "segment": "c02s1", "speaker": "ana", "text": "I did not think you would come tonight, and honestly I am not sure that I ever wanted you to."},
            {"id": "l3", "segment": "c03s1", "speaker": "ben", "text": "Here I am."},
            {"id": "l4", "segment": "c04s1", "speaker": "ben", "text": "Pick up, Ana!", "bubble": "phone"}]},
    }
    starts = {"1": 0.0, "2": 8.0, "3": 16.0, "4": 24.0, "5": 32.0}
    speech = {"l1": {"url": "u/l1.mp3", "dur": 3.0}, "l2": {"url": "u/l2.mp3", "dur": 5.0}, "l3": {"url": "u/l3.mp3", "dur": 1.0},
              "l4": {"url": "u/l4.mp3", "dur": 1.5}}
    faces = {"size": [720, 1280], "shots": {
        "1": {"faces": [{"who": "ana", "box": [300, 500, 420, 640]}]},
        "2": {"faces": [{"who": "ana", "box": [100, 300, 260, 480]}, {"who": "ben", "box": [420, 320, 580, 500]}]},
        "3": {"faces": [{"who": "ben", "box": [250, 600, 470, 860]}]},
        "4": {"faces": [{"who": "ana", "box": [250, 600, 470, 860]}]},
        "5": {"faces": [{"who": "ana", "box": [250, 600, 470, 860]}]}}}
    for name, data in (("relay.json", relay), ("speech_urls.json", speech), ("face_boxes.json", faces),
                       ("cut_final.json", {"final": "https://example.invalid/final.mp4", "duration": 40.0})):
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            json.dump(data, fh)
    os.makedirs(os.path.join(d, "jobs"), exist_ok=True)
    with open(os.path.join(d, "jobs", "starts.json"), "w", encoding="utf-8") as fh:
        json.dump(starts, fh)
    return relay


def ns(job, **kw):
    argv = ["plan", job] + sum([["--" + k.replace("_", "-"), str(v)] for k, v in kw.items()], [])
    return op.build_parser().parse_args(argv)


class TextTests(unittest.TestCase):
    def test_fix_text_repairs_utf8_read_as_cp1252(self):
        bad = "Iâ€”well"
        self.assertEqual(op.fix_text(bad), "I—well")
        self.assertEqual(op.fix_text("plain"), "plain")

    def test_split_text_keeps_chunks_short_and_whole(self):
        t = "Really? I well, I have thought of that, of course, but most husbands are jealous because they love their wives too much."
        parts = op.split_text(t, 60)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= 70 for p in parts), parts)
        self.assertEqual(" ".join(parts), t)

    def test_wrap_never_exceeds_width(self):
        lines = op.wrap_text("the quick brown fox jumps over the lazy dog again and again", 34, 300)
        self.assertTrue(all(op.text_w(l, 34) <= 300 or " " not in l for l in lines), lines)


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        make_job(self.d)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_line_times_follow_the_cut_builder_rule(self):
        a = ns(self.d)
        ctx = op.compute_overlays(a)
        l2 = [l for l in ctx["lines"] if l["id"] == "l2"][0]
        self.assertAlmostEqual(l2["t0"], 8.3)
        self.assertAlmostEqual(l2["t1"], 13.3)

    def test_scene_change_by_place_when_scene_ids_are_unique(self):
        ctx = op.compute_overlays(ns(self.d))
        kinds = {c["shot"]: c["kind"] for c in ctx["cuts"]}
        self.assertEqual(ctx["mode"], "place")
        self.assertEqual(kinds, {2: "inscene", 3: "scene", 4: "inscene", 5: "inscene"})

    def test_scenes_override_wins(self):
        with open(os.path.join(self.d, "scenes.json"), "w") as fh:
            json.dump({"break_before": [5], "same_scene": [3]}, fh)
        ctx = op.compute_overlays(ns(self.d))
        kinds = {c["shot"]: c["kind"] for c in ctx["cuts"]}
        self.assertEqual(kinds[5], "scene")
        self.assertEqual(kinds[3], "inscene")

    def test_halftone_direction_never_repeats_back_to_back(self):
        for seed in range(30):
            ctx = op.compute_overlays(ns(self.d, seed=seed, scene_mode="place"))
            ds = [c["dir"] for c in ctx["cuts"] if c["kind"] == "inscene"]
            self.assertTrue(all(x != y for x, y in zip(ds, ds[1:])), ds)

    def test_every_dialogue_line_has_a_bubble_clear_of_every_face(self):
        ctx = op.compute_overlays(ns(self.d))
        faces = op.Faces(json.load(open(os.path.join(self.d, "face_boxes.json"))), (720, 1280))
        ids = {x["id"] for x in ctx["items"] if x["kind"] in ("speech", "phone")}
        self.assertEqual(ids, {"l2", "l3", "l4"})
        for it in ctx["items"]:
            if it["kind"] == "caption":
                continue
            boxes = [f["box"] for _, fs in faces.shots[it["shot"]] for f in fs]
            for b in boxes:
                self.assertFalse(op.rect_hit(it["rect"], b), (it, b))
            self.assertGreaterEqual(it["rect"][0], 0)
            self.assertLessEqual(it["rect"][2], 720)

    def test_long_line_is_split_into_consecutive_timed_bubbles(self):
        ctx = op.compute_overlays(ns(self.d))
        l2 = [x for x in ctx["items"] if x["id"] == "l2"]
        self.assertGreaterEqual(len(l2), 2)
        for x, y in zip(l2, l2[1:]):
            self.assertAlmostEqual(x["b"], y["a"], places=1)
        self.assertAlmostEqual(l2[0]["a"], 8.3, places=1)
        self.assertAlmostEqual(l2[-1]["b"], 13.3 + 0.35, places=1)

    def test_tail_tip_touches_the_speakers_face_not_the_listeners(self):
        ctx = op.compute_overlays(ns(self.d))
        it = [x for x in ctx["items"] if x["id"] == "l3"][0]
        tip = it["tip"]
        box = [250, 600, 470, 860]
        self.assertTrue(box[0] - 60 <= tip[0] <= box[2] + 60 and box[1] - 60 <= tip[1] <= box[3] + 60, tip)

    def test_narration_is_a_caption_in_the_lower_fifth(self):
        ctx = op.compute_overlays(ns(self.d))
        c = [x for x in ctx["items"] if x["id"] == "l1"][0]
        self.assertEqual(c["kind"], "caption")
        self.assertGreater(c["rect"][1], 1024 - 60)

    def test_missing_face_boxes_fail_loudly_unless_asked(self):
        os.remove(os.path.join(self.d, "face_boxes.json"))
        with self.assertRaises(op.OverlayError):
            op.compute_overlays(ns(self.d))
        ctx = op.compute_overlays(ns(self.d, missing_faces="top"))
        self.assertTrue(ctx["warnings"])

    def test_parts_tile_the_film_and_no_boundary_sits_in_a_transition(self):
        a = ns(self.d, part_seconds=10)
        ctx = op.compute_overlays(a)
        wins = op.windows_of(ctx["cuts"], a, 24)
        b = op.choose_parts(ctx["nframes"], 24, wins, 10, 12)
        self.assertEqual(b[0], 0)
        self.assertEqual(b[-1], ctx["nframes"])
        self.assertTrue(all(y > x for x, y in zip(b, b[1:])))
        for f in b[1:-1]:
            t = f / 24.0
            self.assertTrue(all(not (w0 <= t <= w1) for w0, w1, _ in wins), (t, wins))

    def test_part_job_overlays_without_changing_length_or_audio(self):
        a = ns(self.d)
        ctx = op.compute_overlays(a)
        job, cuts = op.build_part(ctx, a, 0, ctx["nframes"], "ov01.mp4", {d: "https://example.invalid/ht_%s.mp4" % d for d in op.DIRS})
        argv = job["argv"]
        self.assertIn("-an", argv)                                   # video only: audio is joined later from the original
        self.assertEqual(argv[argv.index("-frames:v") + 1], str(ctx["nframes"]))
        fc = argv[argv.index("-filter_complex") + 1]
        self.assertIn("ass=b.ass", fc)
        self.assertIn("zoompan", fc)                                 # the scene change at shot 3
        self.assertIn("colorkey", fc)                                # halftone clips keyed over the picture
        self.assertTrue(job["sidecars"][0]["content"].count("Dialogue:") > 3)
        self.assertLessEqual(job["timeout_seconds"], 600)

    def test_ass_events_are_shifted_into_the_part(self):
        a = ns(self.d)
        ctx = op.compute_overlays(a)
        text = ctx["ass"].render(ctx["st"], offset=8.0, t_from=8.0, t_to=16.0)
        self.assertIn("Dialogue: ", text)
        self.assertIn("0:00:00.30", text)                            # l2 starts 8.3 s into the film

    def test_plan_writes_calls_of_at_most_five_jobs(self):
        a = ns(self.d, part_seconds=6)
        self.assertEqual(op.cmd_plan(a), 0)
        for n in os.listdir(os.path.join(self.d, "finish", "jobs")):
            if n.startswith("ov_call"):
                self.assertLessEqual(len(json.load(open(os.path.join(self.d, "finish", "jobs", n)))), 5)

    def test_join_copies_video_parts_and_the_original_audio(self):
        a = ns(self.d, part_seconds=15)
        op.cmd_plan(a)
        plan = json.load(open(os.path.join(self.d, "finish", "overlay_plan.json")))
        op.cmd_outputs(op.build_parser().parse_args(["outputs", self.d] + ["%s=https://example.invalid/%s" % (p["name"][:-4], p["name"]) for p in plan["parts"]]))
        op.cmd_join(op.build_parser().parse_args(["join", self.d]))
        j = json.load(open(os.path.join(self.d, "finish", "jobs", "ov_join.json")))[0]
        argv = j["argv"]
        self.assertEqual(argv[argv.index("-c") + 1], "copy")
        self.assertIn("1:a:0", argv)
        self.assertTrue(j["sidecars"][0]["content"].startswith("ffconcat version 1.0"))
        self.assertEqual(j["inputs"][-1]["url"], "https://example.invalid/final.mp4")

    def test_ht_jobs_make_eight_distinct_directions(self):
        op.cmd_ht_jobs(op.build_parser().parse_args(["ht-jobs", self.d]))
        a = json.load(open(os.path.join(self.d, "finish", "jobs", "ht_call1.json")))
        b = json.load(open(os.path.join(self.d, "finish", "jobs", "ht_call2.json")))
        self.assertEqual(len(a) + len(b), 8)
        self.assertEqual(len({j["argv"][j["argv"].index("-filter_complex") + 1] for j in a + b}), 8)

    def test_no_private_paths_in_the_generated_jobs(self):
        a = ns(self.d)
        op.cmd_plan(a)
        blob = open(os.path.join(self.d, "finish", "jobs", "overlay_parts.json"), encoding="utf-8").read()
        self.assertNotIn("Users", blob)


@unittest.skipUnless(shutil.which("ffmpeg"), "needs a local ffmpeg with libass")
class RenderTests(unittest.TestCase):
    def test_window_job_renders_with_the_exact_frame_count(self):
        d = tempfile.mkdtemp()
        try:
            make_job(d)
            src = os.path.join(d, "src.mp4")
            r = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=720x1280:r=24:d=40",
                                "-pix_fmt", "yuv420p", "-c:v", "libx264", "-g", "12", src], capture_output=True)
            if r.returncode:
                self.skipTest("cannot make a test source")
            a = ns(d, video=src, duration=40)
            a.job = d
            ctx = op.compute_overlays(a)
            job, _ = op.build_part(ctx, a, 24 * 14, 24 * 20, "w.mp4", {})
            wd = os.path.join(d, "w")
            os.makedirs(wd)
            shutil.copyfile(src, os.path.join(wd, "final.mp4"))
            with open(os.path.join(wd, "b.ass"), "w", encoding="utf-8") as fh:
                fh.write(job["sidecars"][0]["content"])
            res = subprocess.run(["ffmpeg"] + job["argv"], cwd=wd, capture_output=True, text=True)
            if "No such filter" in res.stderr or "ass" in res.stderr and res.returncode:
                self.skipTest("ffmpeg lacks a needed filter: " + res.stderr[-200:])
            self.assertEqual(res.returncode, 0, res.stderr[-400:])
            probe = subprocess.run(["ffmpeg", "-i", os.path.join(wd, "w.mp4"), "-f", "null", "-"], capture_output=True, text=True)
            self.assertIn("frame=  144", probe.stderr.replace("frame= 144", "frame=  144"))
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
