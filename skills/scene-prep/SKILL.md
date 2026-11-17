---
name: scene-prep
description: Subagent role for the relay conductor. For ONE chain, finalize and seal its segment prompts against the locked style, cast and limits, and judge the keyframe still against the locks. Free, read-only against Frameo; writes only its own prep note. Never spends credits.
---

# Scene prep (one chain)

> **Host note.** `$RELAY_HOME` below is the folder that holds `scripts/relay_check.py` and `skills/`. In Claude Code and Cowork it is `${CLAUDE_PLUGIN_ROOT}`. In any other agent (Codex, Gemini CLI, Cursor, ...) it is `$FRAMEORELAY_HOME` if set, else `~/.frameorelay` (made by `scripts/install.py`), else the folder of the clone or plugin copy this skill came from. Resolve it once and reuse it. Tool names here are the Frameo MCP's own (`generate_videos`, ...); your host may prefix them (for example `mcp__frameo__generate_videos`). Subagent steps: if your host cannot spawn subagents, do them yourself in sequence. Details: `$RELAY_HOME/docs/hosts.md`.

You are dispatched by `frameorelay:conductor` for one chain id. You never generate, quote, confirm or spend anything, and you never edit `relay.json`.

## Inputs
The job folder (`frameo-jobs/<job-id>/`) and your chain id. Read `relay.json`, `plan.md`, `references/` of the conductor skill if you need the schema.

## Do
1. `get_skill(skill_id="video-prompting", path="video-guide-seedance.md")`, and `video-guide-seedance-dialogue.md` if the chain has approved dialogue.
2. For each segment of your chain, produce the final prompt text:
   - starts with `style.anchor` verbatim;
   - sealed: no "previous", "as before", shot numbers, no reliance on other clips;
   - cites the first frame as `@Image1` and each reference by slot with a role ("@Image2: Maya, 100% matches the reference");
   - states the first frame, where light comes from, the camera, the action, and where the people and the camera END UP;
   - one level of timing control; a run of up to 30 s is "one continuous shot, the camera does not cut on its own";
   - spoken lines only if approved, and only for a silent-then-lipsynced plan, never invented here.
3. If the keyframe still exists, `view_image` it and judge it against the locked references and the style: same face, outfit, props, place, light; no extra people; text and hands clean.
4. Write ONE file: `chains/<your-chain-id>/prep-<n>.json`:
   `{"chain": "...", "segments": [{"id","prompt","keyframe_verdict":"pass|fail","notes":"..."}], "concerns": ["..."]}`
   Report any contradiction (a line too long for its segment, a join at `high` motion, an aspect the model does not take) as a concern; do not silently fix the plan.

## Never
Touch `relay.json`, another chain's folder, `ledger.jsonl` or `calls/`; call any paid tool; refresh media links.

## Craft rules to bake into every sealed prompt (full text: `$RELAY_HOME/skills/script-injector/references/prompt-quality-rules.md`)
- **Eyelines:** two characters speaking to each other look AT EACH OTHER, never into the camera; stage two-shots three-quarter or in profile toward each other, listeners look at the speaker. Write it as a sentence in the prompt.
- **Bubble room:** leave a calm, face-free area (upper or lower third) for bubbles that are added in the edit; no lettering from the model.
- Vehicles and props: state the layout explicitly (for example right-hand-drive car, which side the driver sits, hands on the wheel) so nothing is mirrored or reversed.
- **Alive faces:** describe expressions in every silent window (blinks, glances, smiles); never leave a frozen stare. **Solid surfaces:** nothing and no one passes through walls, doors or glass; bodies stay behind them as silhouettes or shadows only.
- **Vehicles are solid and modern:** closed body, opaque roof and doors, only glass is see-through; write the dashboard (digital cluster, touchscreen, vents, gear selector), steering-wheel side and driving side into the prompt and check the keyframe for them before any clip is made.
- **No camera gaze:** unless the script says a character addresses the camera, write explicit screen-direction blocking (positions, head turns, up/down looks) and "neither looks into the camera lens, no smile to the camera" into every two-person prompt, especially for characters busy with a task.
- **Style split:** when the user's defaults file separates the look of the characters from the look of everything else (environments, light, effects, graphics), write BOTH clauses into the prompt, never one blended style, and judge the keyframe on both halves (figures read as the character style; world reads as the world style). A keyframe whose characters or world drift to the wrong half fails.
- **Setting and drive side:** use the setting the script or the user's defaults file names (`$RELAY_HOME/skills/script-injector/references/user-defaults.md`) and write the drive side that setting implies into every vehicle prompt (for example right-hand drive with traffic on the left, or the reverse).
- **Lock the camera for interior/vehicle shots:** write "the camera is locked off in the position of the opening frame, do not duplicate objects, nobody turns to face the camera"; moving cameras in a cabin make the model duplicate geometry and turn people toward the lens.
## Motion, first frames and bound lines (from a 17-shot run)
- **Action beats:** write a concrete action for every 2 to 3 seconds of the clip ("0 to 3 s: she taps the lid and glances at the clock; 3 to 5.5 s: she stands and slings the bag"), plus "something moves every second". Add ambient motion (curtain, clock hand, a train outside, dust). A clip written as one pose came back still. Camera: a slow slide or arc that never gets closer than the framing you name; fast push-ins crop heads and remove the calm area.
- **Judge the opening frame for things the clip cannot fix:** a brand logo, a border or paper margin, a missing seatbelt, mismatched shoes, an extra object. Fail the keyframe and say which edit to make (nano-banana-pro edit, "change only X", 18 credits) instead of writing a longer clip prompt.
- **Bound lines:** the model starts a bound line late or early, may play it again after it ends, and may invent a reply for the other character. After the last bound line write "nobody speaks" and give the remaining seconds no dialogue action; flag in `concerns` that the conductor must measure the line and may need to trim the clip.
- **Silhouette and cutaway shots** (no lips visible): do NOT bind the speech. Seal the prompt as silent ("nobody speaks, a voice is added later; room tone and the clock only") and tell the conductor to lay the speech file in the edit at chosen times; list the intended times.
- **Devices and props:** name them blank ("lid completely blank, no logo, no emblem") and write safety gear (seatbelt) into the sentence when the setting needs it.

## Book chapters
For a chapter of a book (`series` block), the recurring cast and places are the bible's: judge keyframes against the chapter module's copies of the bible sheets, use the right outfit or state variant for this chapter, and never accept a different face for a recurring character.
