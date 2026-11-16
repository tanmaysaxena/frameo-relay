"""Tests for skills/finish-cut/scripts/build_sound.py and assemble_final.py. Run: python -m pytest tests/"""
from __future__ import annotations

import json
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "finish-cut", "scripts"))
import assemble_final as af  # noqa: E402
import build_sound as bs  # noqa: E402


def spec() -> dict:
    return {
        "clips": [{"id": "s01", "url": "u/s01.mp4", "seconds": 10.0}, {"id": "s02", "url": "u/s02.mp4", "seconds": 12.0},
                  {"id": "s03", "url": "u/s03.mp4", "seconds": 8.0}],
        "lines": [{"clip": "s02", "t": 3.0, "end": 5.0}],
        "keep_whole": ["s03"],
        "dub": [{"id": "l09", "url": "u/l09.mp3", "clip": "s03", "at": 0.8}],
        "narration": [{"id": "n01", "url": "u/n01.mp3", "clip": "s01", "at": 0.5}],
        "beds": [{"id": "mA", "url": "u/mA.mp3", "start_clip": None, "fade_in": 1.5, "fade_out_clip": "s03", "fade_out_lead": 4.0, "fade_out_d": 3.0},
                 {"id": "mB", "url": "u/mB.mp3", "start_clip": "s03", "lead": 1.5, "fade_out_clip": None, "fade_out_lead": 3.0}],
        "title_s": 5.0,
    }


class SoundTests(unittest.TestCase):
    def test_dialogue_clip_is_gated_and_delayed_to_its_film_start(self):
        job = bs.build(spec())
        fc = job["argv"][job["argv"].index("-filter_complex") + 1]
        self.assertIn("between(t,2.85,5.30)", fc)          # t - pad to end + tail
        self.assertIn("adelay=10000|10000[ds02]", fc)      # s02 starts at 10 s
        self.assertIn("adelay=22000|22000[ds03]", fc)

    def test_whole_clip_kept_and_dub_and_narration_placed_from_clip_start(self):
        job = bs.build(spec())
        fc = job["argv"][job["argv"].index("-filter_complex") + 1]
        self.assertIn("between(t,0.00,8.00)", fc)
        self.assertIn("adelay=22800|22800[l09]", fc)
        self.assertIn("adelay=500|500[n01]", fc)
        self.assertIn("volume=1.15", fc)

    def test_beds_follow_the_shots_and_total_includes_title(self):
        job = bs.build(spec())
        fc = job["argv"][job["argv"].index("-filter_complex") + 1]
        self.assertEqual(job["film_seconds"], 30.0)
        self.assertEqual(job["total_seconds"], 35.0)
        self.assertIn("afade=t=out:st=18.0:d=3.0,adelay=0|0[mA]", fc)         # fades out 4 s before s03 (22 s)
        self.assertIn("adelay=20500|20500[mB]", fc)                            # starts 1.5 s before s03
        self.assertIn("atrim=0:35.00", fc)
        self.assertEqual(job["argv"][-1], "mix.m4a")

    def test_a_retake_that_changes_one_clip_length_moves_later_starts_only(self):
        a = bs.build(spec())
        s = spec()
        s["clips"][0]["seconds"] = 12.0
        b = bs.build(s)
        fa = a["argv"][a["argv"].index("-filter_complex") + 1]
        fb = b["argv"][b["argv"].index("-filter_complex") + 1]
        self.assertIn("adelay=12000|12000[ds02]", fb)
        self.assertNotIn("adelay=12000|12000[ds02]", fa)


class AssembleTests(unittest.TestCase):
    def picture(self) -> dict:
        fc = "[0:v]trim=0:10,scale=720:1280,setsar=1[v0];[1:v]trim=0:12,scale=720:1280,setsar=1[v1];[v0][v1]concat=n=2:v=1:a=0[vc];[vc]ass=b.ass[v]"
        return {"reason": "x", "inputs": [{"name": "c0.mp4", "url": "old0"}, {"name": "c1.mp4", "url": "old1"}, {"name": "ht_LR.mp4", "url": "htold"}],
                "sidecars": [{"name": "b.ass", "content": "[Script Info]"}],
                "argv": ["-i", "c0.mp4", "-i", "c1.mp4", "-i", "ht_LR.mp4", "-filter_complex", fc, "-map", "[v]", "-an", "-c:v", "libx264", "-t", "22.00", "picture.mp4"],
                "outputs": [{"name": "picture.mp4", "mime_type": "video/mp4"}]}

    def test_720_final_adds_title_mix_and_fade(self):
        job = af.assemble(self.picture(), "mixurl", "titleurl", "final.mp4")
        fc = job["argv"][job["argv"].index("-filter_complex") + 1]
        self.assertIn("[3:v]fps=24,scale=720:1280", fc)
        self.assertIn("[4:a]afade=t=out:st=19.4:d=2.6,apad=whole_dur=27.00[au]", fc)
        self.assertEqual(job["argv"][-1], "final.mp4")
        self.assertIn("27.00", job["argv"])
        self.assertEqual(job["sidecars"][0]["content"], "[Script Info]")      # bubbles untouched

    def test_1080_final_swaps_clips_and_scales(self):
        job = af.assemble(self.picture(), "m", "t", "f.mp4", (1080, 1920), clip_urls=["new0", "new1"], ht_map={"htold": "htnew"})
        fc = job["argv"][job["argv"].index("-filter_complex") + 1]
        self.assertNotIn("720:1280", fc)
        self.assertIn("scale=1080:1920", fc)
        self.assertEqual([i["url"] for i in job["inputs"][:3]], ["new0", "new1", "htnew"])
        self.assertIn("20", job["argv"])                                         # crf 20 at 1080p

    def test_rejects_a_picture_job_without_the_bubble_tail(self):
        p = self.picture()
        p["argv"][p["argv"].index("-filter_complex") + 1] = "[0:v]trim=0:10[v]"
        with self.assertRaises(ValueError):
            af.assemble(p, "m", "t", "f.mp4")


if __name__ == "__main__":
    unittest.main()
