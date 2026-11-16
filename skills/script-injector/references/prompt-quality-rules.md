# Prompt and review quality rules

Craft rules the injector, scene-prep and review apply to every story. They came from real runs; each one prevents a failure that cost retakes.

## Dialogue shown as bubbles
- Bubble text comes from the edit (the `finish-cut` `.ass` layer), never from the video model: baked-in lettering garbles anything past a few words and can invent brand names on props. Generate clips bubble-free and leave the upper (or lower) third of the frame calm.
- **A bubble never overlays a face**, the speaker's or the listener's. `finish_cut.py` refuses to build a bubble unless each dialogue entry lists the visible faces (`faces: [[x0,y0,x1,y1], ...]`, canvas pixels, from a frame you actually viewed). It places the bubble on a grid spot that overlaps none of them, closest to the speaker, with the tail on the speaker's face. If no spot is free, re-frame or shorten the line.
- Bubbles are sized to their text, so no word spills outside; the name tag sits inside the top. Look at a frame inside every bubble before shipping.
- Narration is audio, optionally with caption boxes; it is never in a bubble.

## Eyelines: characters talk to each other, not to the camera
- Characters never look into the lens or address the viewer unless the script clearly asks for it. Silence in the script is not permission.
- Every prompt with two characters states the gaze: "ANNA and BEN look at each other when they speak (eyelines on each other, never into the camera)". Stage two-shots three-quarter or in profile toward each other; listeners look at the speaker.
- Write blocking in screen terms: who stands or kneels where, which way each head is turned, who looks up or down at whom. Characters doing a task glance at the work and at their partner, never at the lens.
- Review checks the speaker's gaze at every spoken line; a speaker looking into the lens fails the shot and gets one retake with the blocking sentence strengthened.

## Faces and bodies must look alive
- No dead-eyed stares, including in held beats before a line. Write blinks, eye shifts, glances at the partner, small smiles and head tilts into every window where nobody is speaking, and describe the expression in words.
- Nothing passes through solid surfaces: no clothing, hands or bodies emerge through or in front of walls, doors or glass. Behind frosted glass or a wall there are only silhouettes and cast shadows.
- End on the story's last image. No "chapter complete" or similar title text unless the user asks for it.

## Vehicles and props must look real
- A car is a solid, closed vehicle: roof, doors and body opaque, only window glass transparent. Never a cutaway or see-through body. Show passengers from an interior angle or through real window glass.
- State the layout explicitly in every vehicle prompt (which side the steering wheel is on, which side traffic keeps) so nothing is mirrored, and verify driver and wheel sides on the keyframe before making a clip. Modern interiors by default unless the story's era says otherwise.

## Dialogue length
- Size clips from measured speech, not word counts: generate or measure the lines first (`duration_seconds`), roughly 2 words per second in accented delivery with pauses.
- If the user wants the dialogue to be a bigger part of the film and the script is thin on it, write extra in-character lines for the moments the script shows the characters together. Keep every original line exactly. Every invented line is marked `source: "generated"`, listed on its own in the plan ("Generated dialogue"), kept in character and within `conductor/references/content-boundaries.md`, and not voiced until the user has had the chance to approve or edit it.
