# Cell rules: what goes in each row, and what to keep out

Each rule exists because a real run lost time or credits without it. An agent reading one shot has only that shot's table and the style bible, so every cell must stand alone.

## Length and Join
- **Length**: whole seconds, 4 to 30. Size it from the speech: spoken seconds ≈ words ÷ 2, plus about 1 s of breath before and after; a shot with 25 words needs about 13 to 14 s. Quiet shots (a held look, an establishing frame) can be 6 to 10 s.
- **Join**: `hard cut` is the default. Use `continues from SHOT NN` only when the same take carries on (a character walks from one room into the next with no cut). A hard cut renders in parallel with everything else; a continuation renders after the shot it continues. When unsure, choose `hard cut`.

## Setup (the scene, made unambiguous)
Three parts in one cell: `Place:` (the one concrete location, named the same way in every shot that returns to it), `Time and light:` (time of day, where the light comes from, its colour), `Props:` (objects that must look identical wherever they appear, such as a toolbox, a parcel, a lamp). State the **layout facts that get mirrored by mistake**: which side the driver sits on, which hand holds what, which side of the room the door is on.

## Cast on screen
Names in UPPERCASE separated by commas, exactly those visible in the frame. A speaker who is off screen is written in the bubble line as `NAME (off screen): "..."`, not added here.

## Camera
One framing and at most one move per shot ("low-angle tracking shot alongside the car", "slow push-in on the two of them"). In small spaces (a car cabin, a bathroom) say **locked off**: free camera moves in cramped rooms made models duplicate furniture and turn people to face the lens.

## Visual prompt (what the frame shows)
Write the visible, not the mood. Include, in this order, what applies:
1. Who is where, in screen terms ("NIA kneels at the sink, frame left; OMAR stands in the doorway, frame right").
2. **Eyelines**: who looks at whom. Characters look at each other and never into the camera lens unless the story clearly says so. Write the sentence: "they look at each other when they speak; nobody looks into the camera."
3. What the hands and bodies do (verbs, not adjectives), **in time slices**: a concrete action every 2 to 3 seconds (stands, steps, picks up the bag, turns on the spot, hand to her chin). A shot written as one held pose renders as a still; the owner called such shots "not moving". Prefer a slow camera slide or arc to a push-in that crops heads.
4. What the face does, including in held beats before a line: blinks, a glance, a small smile. "Dead stare" and "zombie eyes" come from leaving this out.
5. What the background does (steam drifting, traffic streaming).
6. Solid things stay solid: vehicles are closed bodies with a visible dashboard, nothing and no one passes through a wall, door or glass (behind frosted glass there are only silhouettes and shadows).
7. For a heated or intimate shot: the ceiling in words (clothed, above the shoulders, silhouettes, steam, shadows) and what is shown instead.
8. Space for bubbles: leave a calm area of the frame free of faces for each bubble.

### Words to keep out of prompts
- Franchise, brand, studio and living-artist names. Translate a look into what it looks like: "hand-drawn halftone-dot shading, chromatic-offset outlines, painted watercolor backgrounds" rather than a film or game name. (The validator warns on common ones.)
- Shot numbers, "previous", "as before", "same as": the video model sees only this shot.
- Brand marks: write "matte grey laptop, lid completely blank, no logo" for any device, bottle or vehicle; models add a fruit or car logo unprompted, and it cannot be fixed in the clip if it is already in the opening frame.
- Readable lettering the model must spell (long signs, brand labels): video models garble text. Put exact text in an `On-screen text` row so it is added in the edit.

## Dialogue bubbles
- Format: `NAME: "exact line."` entries separated by ` / `, in speaking order. A parenthetical after the name is allowed: `OMAR (muffled, from behind the door): "..."`. A stage direction between entries is written `(beat: she pulls him back in)`.
- Copy the author's words exactly, including the ellipses and emphasis capitals. Generated lines end with ` [generated]`; a line of the author's that you changed ends with ` [adapted]` (the same applies to a narration cell); both must be listed in `## GENERATED ADDITIONS`.
- One speaker per entry; keep each line short enough to read in one glance (about 12 words); split long speeches into turns with a reaction between them.
- At most 10 lines per shot (the video model takes at most 10 reference audio clips), and the speech must fit the Length.
- `None` when nobody speaks.
- Narration is never in a bubble.

## Narration (VO)
The narrator's exact lines in quotes, or `None`. Narration is audio only. Put narration in windows where the cast is not speaking, and keep it from restating what the picture already shows.

## SFX and BGM
- SFX: short cues in the order they happen ("door creak, footsteps, birdsong"). On-screen onomatopoeia (a drawn letterform) belongs in `On-screen text`, not here.
- BGM: mood plus instrumentation, shaped by the story's theme, and what changes from the previous shot's bed ("continue the hopeful theme, add strings"; "strip to soft piano"). One bed per mood, not per shot.

## Things reviewers will fail
A speaker looking into the lens; a bubble over a face; a see-through or toy-like car; clothing or hands through glass; a dead-eyed held beat; invented words not marked `[generated]`; shot text that depends on another shot.
