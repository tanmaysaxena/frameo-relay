# House defaults (example)

Copy this file to `./frameo-jobs/house-defaults.md` (this project) or `~/.frameorelay/house-defaults.md` (all projects) and edit it. frameorelay applies it without asking and mentions each rule once in the plan. Delete any section you do not want. See `skills/script-injector/references/user-defaults.md`.

## Look
- Style anchor (pasted verbatim into every keyframe and clip prompt, 60 words or fewer, plain visible description, no brand or director names):
  "Warm hand-painted animated look, soft lighting, gentle film grain, expressive characters with clean silhouettes."
- Reference stills first (character sheets, then location plates, then shot keyframes), then clips.

## Voices
- Spoken language and accent: <for example Indian English, UK English, Hindi>.
- Default female voice: <voice name and id from search_voices>.
- Default male voice: <voice name and id>.
- Narrator: <voice name and id>, different from every character.
- Anyone beyond these has no default: ask per story with 2 to 4 `search_voices` candidates.
- Check each id exists in the pinned workspace before quoting.

## Music
- Instrumental bed shaped by the story's theme and arc, one bed per mood, crossfaded where the mood changes, sitting under speech, with a resolved ending.

## Dialogue display
- Every spoken line appears as a speech bubble with a name tag and a tail to the speaker; narration is audio only.

## Transitions
- Edge-to-edge halftone sweeps between shots, direction shuffled per cut (`finish-cut` `transition.mode: halftone`).

## Setting
- Default country, era and everyday details: <for example "modern city apartment">.
- Vehicle drive side if relevant: <left-hand or right-hand drive and which side traffic keeps>.
