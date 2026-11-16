# Splitting a script into scenes, chains and segments

## Scenes
One scene per continuous action or speech. A beat that runs on without a cut, however many lines it spans, is ONE scene. Start a new scene when the place, time, camera set-up or speaking character changes in a way that needs a cut.

## Chains
A chain is an ordered run of scenes that flow into each other (same take, "we follow her through the door", a camera that never cuts). Rules:

- A hard cut (new place, new time, "CUT TO") starts a new chain. A chain of one scene is normal and is most of a marketing video.
- Only group scenes when the script says they are continuous, or when the action physically carries over (a character walks out of one room into the next with no cut). When unsure, do NOT chain: ask the owner. A wrong chain costs serial render time; a missed chain costs a visible jump.
- Chains run in parallel with each other. Segments inside a chain run one after another.

## Segments
- Each segment is one clip of at most 30 seconds (the `seedance_2_5` limit) and a whole number of seconds, at least the model's minimum (4 s on `seedance_2_5`).
- If a chain's scenes add up to 30 s or less, make it ONE segment and write the prompt as one continuous shot ("one continuous shot, the camera does not cut on its own"). Fewer segments means fewer joins.
- If longer, cut the chain at the most low-motion moment available (a held look, a doorway, a pause), never mid-run or mid-turn. Mark that segment's `join_motion`: `low`, `mid`, `high`. Prefer `low`.
- A continuing segment opens on the **extracted real last frame** of the previous segment, never on a pre-made image. The `end_target` of the previous segment is only loose steering; the model follows it loosely.

## Speech inside a segment
- Count words: at most about 2.5 per second of segment length (the validator checks this).
- One visible speaker per clip where a lipsync is planned. Several speakers in a clip means splitting the clip or accepting native audio for a one-off line.
- Chains with dialogue are rendered silent and the speech is added after the join (locked `voice_id` per character, lipsync where a face speaks).
