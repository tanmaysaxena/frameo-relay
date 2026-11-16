"""Tests for skills/panel-writer/scripts/panel_check.py. Run: python -m pytest tests/  (or python -m unittest)."""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "skills", "panel-writer", "scripts"))
import panel_check as pc  # noqa: E402

EXAMPLE = os.path.join(HERE, "..", "skills", "panel-writer", "references", "example-panel-script.md")


def example_text() -> str:
    with open(EXAMPLE, encoding="utf-8") as fh:
        return fh.read()


def run_check(text: str):
    return pc.check(pc.parse(text))


class PanelCheckTests(unittest.TestCase):
    def test_example_passes(self):
        fails, _warns, infos = run_check(example_text())
        self.assertEqual(fails, [])
        self.assertTrue(any("3 shots" in i for i in infos))

    def test_parse_gives_ordered_line_ids_and_generated_source(self):
        data = pc.to_json(pc.parse(example_text()))
        self.assertEqual([s["id"] for s in data["shots"]], ["S01", "S02", "S03"])
        ids = [ln["id"] for s in data["shots"] for ln in s["dialogue"]]
        self.assertEqual(ids, ["l01", "l02", "l03", "l04", "l05", "l06"])
        gen = [ln for s in data["shots"] for ln in s["dialogue"] if ln["source"] == "generated"]
        self.assertEqual(len(gen), 1)
        self.assertEqual(data["shots"][2]["join"], {"mode": "continues", "from": "S02"})
        self.assertEqual(data["shots"][0]["setup"]["place"], "a narrow market lane with shuttered stalls")
        self.assertEqual(data["cast"], ["NIA", "OMAR"])

    def test_missing_required_row_fails(self):
        text = example_text().replace("| Camera | Low-angle tracking shot alongside her bicycle, one slow move, no cut. | | |\n", "", 1)
        fails, _, _ = run_check(text)
        self.assertTrue(any("row 'camera' is missing" in f for f in fails))

    def test_timecode_gap_fails(self):
        text = example_text().replace("## SHOT 02 — 0:12–0:26", "## SHOT 02 — 0:14–0:28")
        fails, _, _ = run_check(text)
        self.assertTrue(any("without a gap" in f for f in fails))

    def test_length_must_match_heading(self):
        text = example_text().replace("| Length | 14 s |", "| Length | 20 s |")
        fails, _, _ = run_check(text)
        self.assertTrue(any("Length is 20 s" in f for f in fails))

    def test_speaker_not_in_cast_fails(self):
        text = example_text().replace('OMAR: "You are early."', 'ZED: "You are early."')
        fails, _, _ = run_check(text)
        self.assertTrue(any("ZED is not a CHARACTERS entry" in f for f in fails))

    def test_too_many_words_per_second_fails(self):
        long_line = " ".join(["word"] * 40)
        text = example_text().replace('NIA: "Last one. Then I\'m free."', f'NIA: "{long_line}"')
        fails, _, _ = run_check(text)
        self.assertTrue(any("words/s" in f for f in fails))

    def test_cross_shot_reference_fails(self):
        text = example_text().replace("She never looks into the camera.", "Same as in shot 2. She never looks into the camera.")
        fails, _, _ = run_check(text)
        self.assertTrue(any("refers to another shot" in f for f in fails))

    def test_setup_cell_may_not_refer_to_another_shot(self):
        text = example_text().replace("Props: a bicycle with a wicker basket", "Outfit: as the previous shot. Props: a bicycle with a wicker basket", 1)
        fails, _, _ = run_check(text)
        self.assertTrue(any("refers to another shot" in f for f in fails))

    def test_generated_line_needs_the_additions_section(self):
        text = example_text().split("## GENERATED ADDITIONS")[0]
        fails, _, _ = run_check(text)
        self.assertTrue(any("GENERATED ADDITIONS" in f for f in fails))

    def test_bad_join_fails(self):
        text = example_text().replace("| Join | continues from SHOT 02 |", "| Join | continues from SHOT 07 |")
        fails, _, _ = run_check(text)
        self.assertTrue(any("not an earlier shot" in f for f in fails))

    def test_unparseable_dialogue_entry_fails(self):
        text = example_text().replace('OMAR: "You are early."', "OMAR says you are early")
        fails, _, _ = run_check(text)
        self.assertTrue(any("NAME:" in f for f in fails))

    def test_style_bible_labels_may_carry_a_parenthetical(self):
        text = example_text().replace("**CHARACTERS:**", "**CHARACTERS (comic style):**").replace("**ENVIRONMENT:**", "ENVIRONMENT (painted): ")
        doc = pc.parse(text)
        self.assertEqual(doc["cast"], ["NIA", "OMAR"])
        self.assertIn("ENVIRONMENT", doc["bible"])

    def test_adapted_marker_needs_the_approvals_section_and_is_unapproved_in_json(self):
        text = example_text().replace('NIA: "My dear Omar, I kept my promise."', 'NIA: "My dear Omar, I kept my promise." [adapted]')
        fails, _, infos = run_check(text)
        self.assertEqual(fails, [])
        self.assertTrue(any("adapted line" in i for i in infos))
        data = pc.to_json(pc.parse(text))
        marked = [ln for s in data["shots"] for ln in s["dialogue"] if ln["marker"] == "adapted"]
        self.assertEqual(len(marked), 1)
        self.assertEqual((marked[0]["source"], marked[0]["approved"]), ("generated", False))
        no_section = text.split("## GENERATED ADDITIONS")[0]
        fails2, _, _ = run_check(no_section)
        self.assertTrue(any("GENERATED ADDITIONS" in f for f in fails2))

    def test_narration_marker_is_not_spoken_and_counts_for_approval(self):
        text = example_text().replace('"Some deliveries take a lifetime."', '"Some deliveries take a lifetime." [adapted]')
        doc = pc.parse(text)
        self.assertEqual(pc.narration_of(doc["shots"][2]), "Some deliveries take a lifetime.")
        _, _, infos = pc.check(doc)
        self.assertTrue(any("narration marked [adapted]" in i for i in infos))

    def test_cast_on_screen_none_is_allowed_for_a_cutaway(self):
        text = example_text().replace("| Cast on screen | NIA |", "| Cast on screen | None |", 1)
        fails, _, _ = run_check(text)
        self.assertFalse(any("'NONE'" in f for f in fails))

    def test_franchise_name_warns(self):
        text = example_text().replace("hand-painted watercolor streets", "streets in the style of Pixar")
        _, warns, _ = run_check(text)
        self.assertTrue(any("pixar" in w for w in warns))


class PlanRateTests(unittest.TestCase):
    def test_plan_wps_changes_the_no_breath_warning(self):
        text = example_text()
        _f1, w1, _i1 = pc.check(pc.parse(text), 2.0)
        _f2, w2, _i2 = pc.check(pc.parse(text), 6.0)
        self.assertLessEqual(len([w for w in w2 if "no breath" in w]), len([w for w in w1 if "no breath" in w]))

    def test_cli_accepts_plan_wps(self):
        self.assertEqual(pc.main(["panel_check.py", "check", EXAMPLE, "--plan-wps", "3.3"]), 0)
        self.assertEqual(pc.main(["panel_check.py", "check", EXAMPLE, "--plan-wps", "x"]), 2)



if __name__ == "__main__":
    unittest.main()
