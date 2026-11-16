"""Tests for scripts/relay_check.py. Run: python -m pytest tests/  (or python -m unittest)."""
from __future__ import annotations

import copy
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import relay_check as rc  # noqa: E402

ANCHOR = "Grainy 16mm film, warm tungsten light, handheld, shallow depth of field."


def sample() -> dict:
    """A valid, approved, locked-ready contract with two chains (3 scenes)."""
    return {
        "version": 1,
        "job": {
            "id": "job-1",
            "workspace_id": "ws-1",
            "frameo": {"project_id": "p1", "module_id": "m1"},
            "aspect_ratio": "9:16",
            "resolution": "480p",
            "model": "seedance_2_5",
            "max_parallel": 3,
            "limits": {"models": {"seedance_2_5": {"seconds": [4, 30], "aspect_ratios": ["9:16", "16:9"], "max_reference_images": 30}}},
        },
        "style": {
            "look": "grainy 16mm",
            "anchor": ANCHOR,
            "reference_lock_ids": ["style-ref"],
            "avoid": [],
        },
        "dialogue": {
            "mode": "fill_gaps",
            "lines": [
                {"id": "l1", "segment": "c1s1", "speaker": "maya", "text": "We leave at dawn.", "language": "en", "source": "script", "approved": True},
                {"id": "l2", "segment": "c2s1", "speaker": "maya", "text": "Not again.", "language": "en", "source": "generated", "approved": True},
            ],
        },
        "approval": {"approved_total_credits": 1000, "retake_allowance_pct": 15, "approved_at": "2026-11-15T10:00:00Z"},
        "locks": {
            "locked_at": None,
            "items": [
                {"id": "maya", "kind": "character", "media_id": "med-maya", "voice_id": "v-1"},
                {"id": "style-ref", "kind": "style", "media_id": "med-style"},
            ],
        },
        "chains": [
            {
                "id": "c1",
                "scene_ids": ["s1", "s2"],
                "segments": [
                    {
                        "id": "c1s1",
                        "scene_ids": ["s1"],
                        "duration_s": 15,
                        "prompt": f"{ANCHOR} Maya walks along the pier, one continuous shot.",
                        "refs_used": ["maya", "style-ref"],
                        "first_frame": {"source": "keyframe", "media_id": "med-kf1"},
                        "end_target": None,
                        "join_motion": "low",
                        "status": "draft",
                        "quote": {"credits": 195, "quote_id": "q1"},
                    },
                    {
                        "id": "c1s2",
                        "scene_ids": ["s2"],
                        "duration_s": 12,
                        "prompt": f"{ANCHOR} Maya reaches the boat and steps aboard.",
                        "refs_used": ["maya", "style-ref"],
                        "first_frame": {"source": "extract", "from_segment": "c1s1", "media_id": None},
                        "join_motion": "low",
                        "status": "draft",
                        "quote": {"credits": 156, "quote_id": "q2"},
                    },
                ],
            },
            {
                "id": "c2",
                "scene_ids": ["s3"],
                "segments": [
                    {
                        "id": "c2s1",
                        "scene_ids": ["s3"],
                        "duration_s": 8,
                        "prompt": f"{ANCHOR} Maya in a kitchen, hard cut in, she shakes her head.",
                        "refs_used": ["maya", "style-ref"],
                        "first_frame": {"source": "keyframe", "media_id": "med-kf3"},
                        "join_motion": "mid",
                        "status": "draft",
                        "quote": {"credits": 104, "quote_id": "q3"},
                    }
                ],
            },
        ],
    }


def run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = rc.main(argv)
    return code, buf.getvalue()


class Job:
    """A temp job folder holding a relay.json."""

    def __init__(self, data):
        self.dir = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.dir.name, "relay.json")
        self.write(data)

    def write(self, data):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(data, fh)

    def read(self):
        with open(self.path, "r", encoding="utf-8") as fh:
            return json.load(fh)

    def ledger(self, rows):
        with open(os.path.join(self.dir.name, "ledger.jsonl"), "w", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row) + "\n")

    def close(self):
        self.dir.cleanup()


class Base(unittest.TestCase):
    def job(self, data=None):
        j = Job(data if data is not None else sample())
        self.addCleanup(j.close)
        return j


class ValidateTests(Base):
    def test_valid_sample_passes(self):
        code, out = run(["validate", self.job().path])
        self.assertEqual(code, 0, out)

    def test_scratch_allows_unapproved_draft(self):
        d = sample()
        d["approval"] = {}
        d["dialogue"]["lines"][0]["approved"] = False
        d["job"]["frameo"] = {}
        j = self.job(d)
        self.assertEqual(run(["validate", j.path])[0], 1)
        self.assertEqual(run(["validate", j.path, "--scratch"])[0], 0)

    def test_segment_over_30s_fails(self):
        d = sample()
        d["chains"][0]["segments"][0]["duration_s"] = 31
        code, out = run(["check-chains", self.job(d).path])
        self.assertEqual(code, 1)
        self.assertIn("30s clip limit", out)

    def test_fractional_duration_fails(self):
        d = sample()
        d["chains"][0]["segments"][0]["duration_s"] = 4.5
        self.assertEqual(run(["check-chains", self.job(d).path])[0], 1)

    def test_duration_outside_model_range_fails(self):
        d = sample()
        d["chains"][1]["segments"][0]["duration_s"] = 2
        code, out = run(["check-chains", self.job(d).path])
        self.assertEqual(code, 1)
        self.assertIn("outside", out)

    def test_continuing_segment_must_open_on_extract_of_previous(self):
        d = sample()
        d["chains"][0]["segments"][1]["first_frame"] = {"source": "keyframe", "media_id": "med-x"}
        code, out = run(["check-chains", self.job(d).path])
        self.assertEqual(code, 1)
        self.assertIn("extracted real last frame", out)

    def test_extract_must_name_the_previous_segment(self):
        d = sample()
        d["chains"][0]["segments"][1]["first_frame"]["from_segment"] = "c2s1"
        self.assertEqual(run(["check-chains", self.job(d).path])[0], 1)

    def test_first_frame_must_equal_recorded_last_frame(self):
        d = sample()
        d["chains"][0]["segments"][0]["result"] = {"last_frame_media_id": "med-last1"}
        d["chains"][0]["segments"][1]["first_frame"]["media_id"] = "med-other"
        code, out = run(["check-chains", self.job(d).path])
        self.assertEqual(code, 1)
        self.assertIn("is not the extracted last frame", out)
        d["chains"][0]["segments"][1]["first_frame"]["media_id"] = "med-last1"
        self.assertEqual(run(["check-chains", self.job(d).path])[0], 0)

    def test_end_target_is_not_a_valid_first_frame_source(self):
        d = sample()
        d["chains"][0]["segments"][1]["first_frame"] = {"source": "end_target", "media_id": "m"}
        self.assertEqual(run(["check-chains", self.job(d).path])[0], 1)

    def test_scene_in_two_chains_fails(self):
        d = sample()
        d["chains"][1]["scene_ids"] = ["s2"]
        d["chains"][1]["segments"][0]["scene_ids"] = ["s2"]
        self.assertEqual(run(["check-chains", self.job(d).path])[0], 1)

    def test_segments_must_cover_chain_scenes_in_order(self):
        d = sample()
        d["chains"][0]["segments"][0]["scene_ids"], d["chains"][0]["segments"][1]["scene_ids"] = ["s2"], ["s1"]
        self.assertEqual(run(["check-chains", self.job(d).path])[0], 1)


class LockTests(Base):
    def test_lock_then_verify_passes_then_tamper_fails(self):
        j = self.job()
        self.assertEqual(run(["lock", j.path])[0], 0)
        self.assertEqual(run(["verify-locks", j.path])[0], 0)
        d = j.read()
        d["locks"]["items"][0]["media_id"] = "med-changed"
        j.write(d)
        code, out = run(["verify-locks", j.path])
        self.assertEqual(code, 1)
        self.assertIn("fingerprint mismatch", out)

    def test_style_edit_after_lock_fails(self):
        j = self.job()
        run(["lock", j.path])
        d = j.read()
        d["style"]["anchor"] += " extra"
        j.write(d)
        self.assertEqual(run(["verify-locks", j.path])[0], 1)

    def test_unlocked_fails(self):
        self.assertEqual(run(["verify-locks", self.job().path])[0], 1)


class StyleAndDialogueTests(Base):
    def test_prompt_without_anchor_fails(self):
        d = sample()
        d["chains"][0]["segments"][0]["prompt"] = "Maya walks along the pier."
        code, out = run(["check-style", self.job(d).path])
        self.assertEqual(code, 1)
        self.assertIn("style.anchor verbatim", out)

    def test_missing_style_reference_in_refs_fails(self):
        d = sample()
        d["chains"][1]["segments"][0]["refs_used"] = ["maya"]
        self.assertEqual(run(["check-style", self.job(d).path])[0], 1)

    def test_style_none_passes(self):
        d = sample()
        d["style"] = {"none": True}
        d["chains"][0]["segments"][0]["prompt"] = "No anchor needed."
        self.assertEqual(run(["check-style", self.job(d).path])[0], 0)

    def test_overlong_anchor_fails(self):
        d = sample()
        d["style"]["anchor"] = " ".join(["word"] * 81)
        for _, _, seg in rc.segments(d):
            seg["prompt"] = d["style"]["anchor"] + " x"
        self.assertEqual(run(["check-style", self.job(d).path])[0], 1)

    def test_unapproved_line_fails_and_generated_is_flagged(self):
        d = sample()
        d["dialogue"]["lines"][1]["approved"] = False
        code, out = run(["check-dialogue", self.job(d).path])
        self.assertEqual(code, 1)
        self.assertIn("not approved", out)
        self.assertIn("GENERATED", out)

    def test_allow_unapproved_flag(self):
        d = sample()
        d["dialogue"]["lines"][1]["approved"] = False
        self.assertEqual(run(["check-dialogue", self.job(d).path, "--allow-unapproved"])[0], 0)

    def test_line_too_long_for_segment_fails(self):
        d = sample()
        d["dialogue"]["lines"][1]["text"] = " ".join(["word"] * 40)
        code, out = run(["check-dialogue", self.job(d).path])
        self.assertEqual(code, 1)
        self.assertIn("will not fit", out)

    def test_speaker_without_voice_fails(self):
        d = sample()
        d["locks"]["items"][0].pop("voice_id")
        code, out = run(["check-dialogue", self.job(d).path])
        self.assertEqual(code, 1)
        self.assertIn("no locked voice_id", out)

    def test_speaker_not_a_character_fails(self):
        d = sample()
        d["dialogue"]["lines"][0]["speaker"] = "ghost"
        self.assertEqual(run(["check-dialogue", self.job(d).path])[0], 1)


class ReadyTests(Base):
    def locked(self, mutate=None):
        d = sample()
        if mutate:
            mutate(d)
        j = self.job(d)
        run(["lock", j.path])
        return j

    def test_ready_passes(self):
        j = self.locked()
        code, out = run(["check-ready", j.path, "c1s1", "--workspace-id", "ws-1"])
        self.assertEqual(code, 0, out)

    def test_workspace_mismatch_fails(self):
        j = self.locked()
        code, out = run(["check-ready", j.path, "c1s1", "--workspace-id", "ws-2"])
        self.assertEqual(code, 1)
        self.assertIn("pinned", out)

    def test_not_locked_fails(self):
        j = self.job()
        self.assertEqual(run(["check-ready", j.path, "c1s1"])[0], 1)

    def test_no_approval_fails(self):
        def m(d):
            d["approval"]["approved_at"] = None
        j = self.locked(m)
        self.assertEqual(run(["check-ready", j.path, "c1s1"])[0], 1)

    def test_missing_prompt_fails(self):
        def m(d):
            d["chains"][0]["segments"][0]["prompt"] = ""
        j = self.locked(m)
        self.assertEqual(run(["check-ready", j.path, "c1s1"])[0], 1)

    def test_unsealed_prompt_fails(self):
        def m(d):
            d["chains"][1]["segments"][0]["prompt"] = f"{ANCHOR} As before, Maya shakes her head."
        j = self.locked(m)
        code, out = run(["check-ready", j.path, "c2s1"])
        self.assertEqual(code, 1)
        self.assertIn("not sealed", out)

    def test_shot_number_in_prompt_fails(self):
        def m(d):
            d["chains"][1]["segments"][0]["prompt"] = f"{ANCHOR} Same as shot 2 but closer."
        j = self.locked(m)
        self.assertEqual(run(["check-ready", j.path, "c2s1"])[0], 1)

    def test_missing_quote_fails(self):
        def m(d):
            d["chains"][1]["segments"][0].pop("quote")
        j = self.locked(m)
        self.assertEqual(run(["check-ready", j.path, "c2s1"])[0], 1)

    def test_budget_below_quotes_refused(self):
        def m(d):
            d["approval"]["approved_total_credits"] = 300
            for _, _, seg in rc.segments(d):
                seg["status"] = "ready"
            d["chains"][0]["segments"][1]["first_frame"]["media_id"] = "med-ex"
            d["chains"][0]["segments"][0]["first_frame"]["media_id"] = "med-kf1"
        j = self.locked(m)
        code, out = run(["check-ready", j.path, "c1s1"])
        self.assertEqual(code, 1)
        self.assertIn("budget", out)

    def test_budget_counts_spend_already_in_ledger(self):
        j = self.locked()
        j.ledger([{"kind": "reference", "credits_charged": 900}])
        code, out = run(["check-ready", j.path, "c1s1"])
        self.assertEqual(code, 1)
        self.assertIn("budget", out)

    def test_refunded_ledger_rows_do_not_count(self):
        j = self.locked()
        j.ledger([{"kind": "reference", "credits_charged": 900, "refunded": True}])
        self.assertEqual(run(["check-ready", j.path, "c1s1"])[0], 0)

    def test_too_many_images_for_model_fails(self):
        def m(d):
            d["job"]["limits"]["models"]["seedance_2_5"]["max_reference_images"] = 2
        j = self.locked(m)
        code, out = run(["check-ready", j.path, "c1s1"])
        self.assertEqual(code, 1)
        self.assertIn("exceed", out)

    def test_unsupported_aspect_fails(self):
        def m(d):
            d["job"]["aspect_ratio"] = "21:9"
        j = self.locked(m)
        self.assertEqual(run(["check-ready", j.path, "c1s1"])[0], 1)


class LedgerTests(Base):
    def test_under_total_passes(self):
        j = self.job()
        j.ledger([{"kind": "clip", "credits_charged": 400}])
        self.assertEqual(run(["ledger", j.path])[0], 0)

    def test_over_total_fails(self):
        j = self.job()
        j.ledger([{"kind": "clip", "credits_charged": 1100}])
        self.assertEqual(run(["ledger", j.path])[0], 1)

    def test_retake_allowance_enforced(self):
        j = self.job()
        # total 1000 with 15% allowance -> allowance is about 130.4
        j.ledger([{"kind": "retake", "credits_charged": 200}])
        code, out = run(["ledger", j.path])
        self.assertEqual(code, 1)
        self.assertIn("retake", out)

    def test_bad_ledger_line_fails(self):
        j = self.job()
        with open(os.path.join(j.dir.name, "ledger.jsonl"), "w") as fh:
            fh.write("not json\n")
        self.assertEqual(run(["ledger", j.path])[0], 1)


class ResultTests(Base):
    def done(self):
        d = sample()
        s1, s2 = d["chains"][0]["segments"]
        s1["status"] = "done"
        s1["result"] = {"generation_id": "g1", "video_media_id": "v1", "last_frame_media_id": "lf1", "credits_charged": 195}
        s1["review"] = {"verdict": "pass", "notes": "pier, warm light holds", "edge_frames_cited": []}
        s2["status"] = "done"
        s2["first_frame"]["media_id"] = "lf1"
        s2["result"] = {
            "generation_id": "g2",
            "video_media_id": "v2",
            "last_frame_media_id": "lf2",
            "first_frame_extract_media_id": "ff2",
            "credits_charged": 156,
        }
        s2["review"] = {"verdict": "pass", "notes": "no hitch at the join", "edge_frames_cited": ["lf1", "ff2"]}
        return d

    def test_complete_result_passes(self):
        j = self.job(self.done())
        self.assertEqual(run(["check-result", j.path, "c1s1"])[0], 0)
        self.assertEqual(run(["check-result", j.path, "c1s2"])[0], 0)

    def test_join_review_must_cite_both_real_frames(self):
        d = self.done()
        d["chains"][0]["segments"][1]["review"]["edge_frames_cited"] = ["lf1"]
        code, out = run(["check-result", self.job(d).path, "c1s2"])
        self.assertEqual(code, 1)
        self.assertIn("must cite both", out)

    def test_hard_cut_segment_needs_no_last_frame(self):
        d = self.done()
        del d["chains"][0]["segments"][1]["result"]["last_frame_media_id"]   # last segment of its chain: nothing continues from it
        self.assertEqual(run(["check-result", self.job(d).path, "c1s2"])[0], 0)

    def test_segment_with_a_continuation_still_needs_its_last_frame(self):
        d = self.done()
        del d["chains"][0]["segments"][0]["result"]["last_frame_media_id"]
        code, out = run(["check-result", self.job(d).path, "c1s1"])
        self.assertEqual(code, 1)
        self.assertIn("last_frame_media_id", out)

    def test_pass_without_notes_fails(self):
        d = self.done()
        d["chains"][0]["segments"][0]["review"]["notes"] = ""
        self.assertEqual(run(["check-result", self.job(d).path, "c1s1"])[0], 1)

    def test_not_done_fails(self):
        self.assertEqual(run(["check-result", self.job().path, "c1s1"])[0], 1)

    def test_manifest_only_when_all_done_and_passed(self):
        self.assertEqual(run(["manifest", self.job().path])[0], 1)
        d = self.done()
        s = d["chains"][1]["segments"][0]
        s["status"] = "done"
        s["result"] = {"generation_id": "g3", "video_media_id": "v3", "last_frame_media_id": "lf3", "credits_charged": 104}
        s["review"] = {"verdict": "pass", "notes": "kitchen ok", "edge_frames_cited": []}
        code, out = run(["manifest", self.job(d).path])
        self.assertEqual(code, 0, out)
        manifest = json.loads(out)
        self.assertEqual([m["video_media_id"] for m in manifest], ["v1", "v2", "v3"])


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name
        os.makedirs(os.path.join(self.root, "chains", "c1"))
        for rel in ("relay.json", "chains/c1/prep-1.json", "chains/c1/notes.md"):
            with open(os.path.join(self.root, rel), "w") as fh:
                fh.write("original")
        self.assertEqual(run(["snapshot", self.root])[0], 0)

    def test_untouched_passes(self):
        self.assertEqual(run(["verify-snapshot", self.root])[0], 0)

    def test_editing_relay_json_fails_naming_the_file(self):
        with open(os.path.join(self.root, "relay.json"), "w") as fh:
            fh.write("edited by a subagent")
        code, out = run(["verify-snapshot", self.root, "--allow", "chains/*/prep-*.json"])
        self.assertEqual(code, 1)
        self.assertIn("relay.json", out)

    def test_allowed_output_may_change(self):
        with open(os.path.join(self.root, "chains/c1/prep-1.json"), "w") as fh:
            fh.write("new prep output")
        self.assertEqual(run(["verify-snapshot", self.root, "--allow", "chains/*/prep-*.json"])[0], 0)

    def test_disallowed_new_file_fails(self):
        with open(os.path.join(self.root, "chains/c1/stray.txt"), "w") as fh:
            fh.write("x")
        code, out = run(["verify-snapshot", self.root, "--allow", "chains/*/prep-*.json"])
        self.assertEqual(code, 1)
        self.assertIn("stray.txt", out)

    def test_removed_file_fails(self):
        os.remove(os.path.join(self.root, "chains/c1/notes.md"))
        self.assertEqual(run(["verify-snapshot", self.root])[0], 1)

    def test_snapshot_file_itself_is_ignored(self):
        self.assertEqual(run(["snapshot", self.root])[0], 0)
        self.assertEqual(run(["verify-snapshot", self.root])[0], 0)

    def test_missing_snapshot_is_usage_error(self):
        empty = tempfile.TemporaryDirectory()
        self.addCleanup(empty.cleanup)
        self.assertEqual(run(["verify-snapshot", empty.name])[0], 2)

class VoiceOnlyNarratorTests(Base):
    def test_voice_lock_can_speak_dialogue(self):
        d = sample()
        d["locks"]["items"].append({"id": "narrator", "kind": "voice", "voice_id": "v-9"})
        d["dialogue"]["lines"].append({"id": "n1", "segment": "c1s1", "speaker": "narrator", "text": "Once.",
                                       "language": "en", "source": "script", "approved": True})
        self.assertEqual(run(["check-dialogue", self.job(d).path])[0], 0)

    def test_voice_only_character_needs_no_image(self):
        d = sample()
        d["locks"]["items"].append({"id": "narrator", "kind": "character", "voice_only": True, "voice_id": "v-9"})
        d["dialogue"]["lines"].append({"id": "n1", "segment": "c1s1", "speaker": "narrator", "text": "Once.",
                                       "language": "en", "source": "script", "approved": True})
        self.assertEqual(run(["validate", self.job(d).path])[0], 0)

    def test_voice_only_character_without_voice_fails_when_not_scratch(self):
        d = sample()
        d["locks"]["items"].append({"id": "narrator", "kind": "character", "voice_only": True})
        self.assertEqual(run(["validate", self.job(d).path])[0], 1)


class FinishCutTests(unittest.TestCase):
    def test_finish_cut_writes_both_jobs(self):
        fc_dir = os.path.join(os.path.dirname(__file__), "..", "skills", "finish-cut", "scripts")
        sys.path.insert(0, fc_dir)
        import finish_cut as fc  # noqa: E402
        edl = {
            "clips": {"a": "https://example.test/a.mp4"},
            "chains": [{"id": "c1", "clip": "a", "windows": [[0, 8], [10, 18]], "target_s": 10, "narration": "n1",
                        "dialogue": [{"key": "d1", "t": 4, "head_x": 240, "faces": [[200, 260, 280, 360]], "speaker_face": 0}]}],
            "speakers": {"M": {"tag": "MAYA", "color": "&H9A3CE0&"}},
            "narration": {"n1": {"url": "https://example.test/n.mp3", "seconds": 3.0, "text": "A short line."}},
            "dialogue": {"d1": {"url": "https://example.test/d.mp3", "seconds": 1.5, "speaker": "M", "text": "Hi."}},
            "sfx": {}, "bgm": [], "transition": {"mode": "none"},
        }
        chains, subs, total = fc.build_timeline(edl)
        pic, events, cuts = fc.build_picture(edl, chains, subs, total)
        aud = fc.build_audio(edl, chains, total, events, cuts, "https://example.test/pic.mp4")
        self.assertAlmostEqual(total, 10.0, places=1)
        self.assertIn("MAYA", pic["sidecars"][0]["content"])
        self.assertIn("-c:v", aud["argv"])
        self.assertEqual(aud["argv"][aud["argv"].index("-c:v") + 1], "copy")

    def test_bubble_never_covers_a_face_and_missing_faces_is_refused(self):
        fc_dir = os.path.join(os.path.dirname(__file__), "..", "skills", "finish-cut", "scripts")
        sys.path.insert(0, fc_dir)
        import finish_cut as fc  # noqa: E402
        faces = [[250, 60, 350, 180], [500, 300, 600, 420]]
        cx, cy, tx, ty = fc.place_bubble(720, 1280, 300, faces, 0)
        box = (cx - 165, cy - 75, cx + 165, cy + 75)
        for f in faces:
            self.assertFalse(fc._hit(*box, *f, m=0), "bubble overlaps a face")
        with self.assertRaises(SystemExit):
            fc.place_bubble(720, 1280, 300, [], 0)


if __name__ == "__main__":
    unittest.main()
