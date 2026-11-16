---
name: panel-writer
description: Use when a story, treatment or outline has NOT been broken down into a per-shot table, before the script-injector. Turns it into a production panel script made of a global style bible, then one table per shot (length, join, setup, cast, camera, visual prompt, dialogue bubbles, narration, SFX, BGM, AI-fill and owner-fill columns) and a production checklist, so parallel agents get every shot as a self-contained, unambiguous work order. Keeps the author's words exact, marks every invented line, checks the result with a validator, never spends credits.
---

# Panel writer

Turns a loose story into a **panel script**: the same kind of document a producer hands a video team, with the story cut into shots and every shot written as a small table. The point is parallel work: when each shot carries its own place, cast, camera, visual, words and sound, an agent can render, review or voice shot 7 without reading shots 1 to 6.

Hard rules, in order of importance:

1. **The author's words stay exact.** Every line of dialogue and narration the author wrote is copied unchanged. Anything you invent (a beat, a line, a prop) is marked `[generated]`, and any author's line you had to change (to stay inside a content ceiling, for example) is marked `[adapted]`, in the cell and listed in the "Generated additions" section for the owner to approve; omissions are listed in a "Content adaptation" table. Never present invention as the author's.
2. **You never call a paid Frameo tool.** Free reads only. The panel script is a document; it generates nothing.
3. **Every cell is filled, in visible terms.** A shot with an empty cell is not finished. Write what the camera sees and the ears hear, not the mood (see `references/cell-rules.md`).
4. **Taste comes from the owner, not from you.** Look, characters' style, voices, music direction, transitions and setting come from the owner's defaults file (`../script-injector/references/user-defaults.md`, and a `house-defaults.md` beside it if one exists) and from what the owner said. Ask only what they do not cover.
5. **The sensuality ceiling is written in words, never tested** (`../conductor/references/content-boundaries.md`). For a romantic or heated shot, put the ceiling in the shot's visual cell and in the checklist.
6. **Check before you show.** Run the validator and fix every FAIL.

## Is a panel script needed? (the 30-second test)

Skip this skill and go straight to `frameorelay:script-injector` when the script already has, for every shot: an id, a length or timecode, a camera cell, a visual cell, dialogue with named speakers, narration, and sound cues, in a table or an equivalent list. Run the validator on it (`check`); if it passes, it is already a panel script.

Use this skill when the input is prose, a synopsis, a scene list without camera or sound, a dialogue-only draft, or a table missing most of those cells.

## Ask first (skip what is already answered or covered by the defaults file)

- The story (pasted, a file path, or attached; a PDF with no reader: `pdftotext -layout`).
- Shape: aspect ratio and a target and a maximum runtime. If the owner gives only a runtime, treat it as the target and size shots from the measured speech (Step 5), which usually runs longer than word counts suggest.
- Who speaks, and how: voiced, bubbles only, or both; narrator or none. (Voices themselves belong to the script-injector.)
- Whether the story is a single take or hard cuts between places (default: hard cut at every change of place or time).
- Anything the defaults file does not cover: for example the look if there is no defaults file, or the setting (country) for vehicles, signs and street life.

## Steps

1. **Read the story once and list.** Cast (name, role, look in one phrase), places, props that must persist, every line of dialogue (speaker, exact words), every narration line, the emotional beat of each stretch, and any content the boundary rule touches.
2. **Cut into shots.** One shot per continuous action in one place. Use `../script-injector/references/scene-splitting.md`: a change of place, time, camera set-up or speaking character that needs a cut starts a new shot. Prefer shots of 8 to 20 seconds; never more than 30 (the clip limit). Mark each shot's **Join**: `hard cut`, or `continues from SHOT NN` only when the action carries straight on with no cut. When unsure, write `hard cut` and say so in the hand-off note.
3. **Write the Global Style Bible** from the defaults file and the story (if the defaults file splits the character style from the world style, keep them in the separate CHARACTERS and ENVIRONMENT lines and name each half's style in its own line; never blend them): characters (one line each: build, hair, palette, signature gear), environment look, the dialogue rule (bubbles or not), narration (voice and "audio only"), transitions. Describe looks in plain visible terms; never name a franchise or a living artist (`references/cell-rules.md`, "Words to keep out").
4. **Write each shot's table** with the fields in `references/panel-template.md`. Follow `references/cell-rules.md` for every cell. Keep dialogue exactly as the author wrote it, one bubble per speaker turn, in order, split with ` / `.
5. **Size the shots from the speech.** Spoken seconds are about 2 words per second for voiced delivery (more with pauses); a shot must be at least its spoken seconds plus a breath before and after, and the validator fails any shot above 2.5 words per second. A narrator voice measured about 3.3 words per second in a real run, so once speech is measured, re-run the check with `--plan-wps 3.3` and size from the measured seconds; the default 2.0 only warns pessimistically. Set each `Length`, then the heading timecodes so they run on without gaps from `0:00`. Add up and compare with the target.
6. **Check the dialogue share.** If the characters' dialogue is under about 5% of the runtime, tell the owner and offer to extend it (new lines marked `[generated]`, in character, listed in "Generated additions"); only do it when the owner's defaults or the owner say so.
7. **Add the Production Checklist** (aspect ratio, resolution, frame rate, narrator voice, bubble policy, sensuality boundary if relevant, delivery, final sign-off) and, if any line is `[generated]`, the "Generated additions" table.
8. **Validate.** Run
   `python "${CLAUDE_PLUGIN_ROOT}/skills/panel-writer/scripts/panel_check.py" check <panel-script.md>`
   (try `python3` or `py` if `python` is not found). Fix every FAIL. Read the WARN lines and fix the ones that are real.
9. **Write the files and show them.** Save `<name>.panel.md` next to the story (the working folder unless the owner says where). Also write `<name>.panels.json` with
   `python "${CLAUDE_PLUGIN_ROOT}/skills/panel-writer/scripts/panel_check.py" parse <panel-script.md> > <name>.panels.json`
   (machine-readable shots, cast, line ids; the script-injector reads it directly). Show the owner the shot list (id, title, length, join), the generated additions, anything you were unsure about (joins, ceiling, lengths), and ask for changes or a yes. A change means edit the markdown and re-run the check.
10. **Hand off.** On the owner's yes, offer `frameorelay:script-injector` with the panel script as the script. The mapping it uses: shot = scene, `Join` = chain, `Length` = segment seconds, `Setup` and `Cast` = locks, `Camera` + `Visual prompt` = the sealed prompt, `Dialogue bubbles` = dialogue lines (ids `l01`, `l02`... in order; `[generated]` = `source: "generated"`), `Narration (VO)` = the narrator's lines, `SFX` and `BGM` = the sound plan. The AI Fill and User Fill columns stay blank: the relay writes status there, the owner approves there.

## Done

A validated `.panel.md` (and `.panels.json`) the owner has seen; every invented word is marked and listed; no credit was spent; the owner knows the next step is the script-injector.
