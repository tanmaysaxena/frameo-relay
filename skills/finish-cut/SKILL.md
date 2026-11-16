---
name: finish-cut
description: Use after the conductor's clips and speech exist, to assemble the finished cut of a Frameo job. Reviews long clips for morph zones, cuts clean windows at a chosen pace, adds edge-to-edge halftone transitions, comic speech bubbles with name tags, narration caption boxes, a voice lane, ducked music beds, sound effects and a loudness-normalised mix, then listens to the result. Two free run_ffmpeg jobs (picture, then sound). Never touches the picture in the sound step.
---

# Finish cut

The step after the conductor: clips, speech, music and effects exist as links; this makes the one film. Everything here is free `run_ffmpeg` work except `generate_music` / `generate_sound_effect` (inside the approved total) and the final `analyze_media` listen (a few credits per minute). Code: `${CLAUDE_PLUGIN_ROOT}/skills/finish-cut/scripts/` (`finish_cut.py`, `halftone_transition.py`). Sandbox facts: `references/sandbox-facts.md`. Every edit-list field: `references/edl.md`. Bubbles and captions: `references/bubbles-and-captions.md`. Transitions: `references/transitions.md`.

## Rules
1. **Words are text added in the edit, never made by a video model.** Bubbles and caption boxes are an `.ass` file; the clips were generated with clear empty space in the upper third (bubbles) and the lower fifth (captions).
2. **Voices are measured, not guessed.** Place every line from its `duration_seconds` (`wait_task`); a bubble lives from its start to its end plus 0.35 s.
3. **Look at the picture before the sound.** The sound step copies the picture (`-c:v copy`); a picture fix means re-running the picture, then the sound.
4. Only approved dialogue is voiced or shown. Narration may also appear as caption boxes (ask in the plan).
5. The owner sets a length target and maximum; `finish_cut.py` warns when over (`options.max_total_s`).
6. **User defaults:** if the user keeps a personal defaults file (`../script-injector/references/user-defaults.md`), apply its standing rules (dialogue display, transition mode, music mood, voices). Without one the skill's own defaults apply: every dialogue line gets a bubble, transitions are halftone sweeps (edge-to-edge halftone-dot wipes, direction shuffled per cut), and the BGM is shaped by the story's theme (one bed per mood). Craft rules for bubbles and eyelines: `../script-injector/references/prompt-quality-rules.md`.

## Steps
1. **Contact sheets.** For every clip longer than about 10 s: `run_ffmpeg` (5 jobs a call) `-vf fps=1/2,scale=150:-1,tile=5x3 -frames:v 1 out.jpg`, then `view_image` at `resolution="high"`. Each tile is 2 s. Look for two bodies merging, a body appearing from nowhere, a room that reshapes, a flare on an eye, a "cut" that is really a morph. Note clean windows `[start, end]` per beat, 0.5 to 1.5 s clear of every boundary.
2. **Edit list.** One chain per scene: clip, windows, `target_s`. Speed = total window seconds / `target_s`, never below 1.0 and rarely above about 2.0 (tender scenes stay near 1.5 or lower, montages go faster). A chain lasts at least its narration + 1.2 s; dialogue lines follow each other about 0.6 s apart; set `head_x` from a frame where the speaker is visible. Dropping a weak chain and merging its narration into the previous one is allowed and is often the best cut for length.
3. **Transitions.** Default: edge-to-edge halftone dots, direction shuffled per cut. Make the 8 direction clips with `halftone_transition.py jobs` (free), then `transition.mode: halftone`. Fallback `flash`, or `none`.
4. **Build.** `python finish_cut.py edl.json OUT` writes `picture_job.json`, `audio_job.json`, `timeline.json`. Send the picture job with `run_ffmpeg` (`timeout_seconds` 600; about 5 min for a 4-minute 480p film).
5. **Check the picture.** `view_image` a frame inside every bubble (does the tail touch the right head, is the name tag right?), one caption, one transition peak, one cut. Fix `head_x` or windows, rebuild, re-run. Do not judge a bubble on a frame that sits on a transition.
6. **Sound.** For hard-cut films write a small spec and run `python build_sound.py spec.json > audio_job.json` (each dialogue clip is its own gated input placed at its film start, so a retake never shifts later lines; silhouette shots take dub lines placed at chosen times; beds follow the shots they cover; the mix is padded for the title card). For a single-take film rebuild with `--picture-url <picture link>` and run `audio_job.json`. Voices full level; beds ducked by sidechain from the voice lane (bed 0.28 to 0.30, `threshold=0.04 ratio=6`); effects 0.3 to 0.8; a soft whoosh on every cut; `loudnorm I=-14` once, last. One bed per mood, crossfaded 1.5 s where the mood changes: upbeat for playful acts, slow for intimate ones.
7. **Listen.** `analyze_media` on the final file, `detect_shots=false`, a question that names each line and its expected voice (male or female) and asks for continuous music, effects heard, music too loud over speech, clipping, long silences. One re-mix at most, then ship and name the defect. A repeated word in one take: regenerate that line (1 credit) and redo the sound step.
8. **Present** (`show_generations` with `final: true`): length, what was cut and why, what was not done (720p finals, retakes, lipsync).

## Pacing (the owner called a first cut slow and dull)
Longer than the voice needs, one speed everywhere, soft joins and a flat bed read as dull. Cut at beat boundaries, speed up montages, put a directional transition on every cut, keep romantic moments slower, lift the music in the playful acts. Check the total against the budget before rendering.

7. **Bubbles never cover a face and never overflow.** Every dialogue entry in the EDL carries `faces` (all visible faces, canvas px) and optionally `speaker_face` (index); `finish_cut.py` sizes the bubble to its text, places it clear of every face and points the tail at the speaker, and fails without `faces`. Verify with a frame inside every bubble (step 5).

## Trims, dubs and long bubbles (from a 17-shot run)
- **Trim a clip in the edit** by setting its `seconds` (and chain window) shorter, for example a clip whose bound line repeated after 12.7 s ends at 12.6 s; set the same `seconds` in the sound spec so later starts shift.
- **Gate the native audio:** clips also carry sighs, laughs, invented voices and music; only the measured line windows (and a clip whose ambience you want, such as a ticking clock) are opened.
- **Long line, crowded frame:** if `finish_cut.py` reports no free spot for a bubble, split the line into two timed entries at a natural pause (same speaker) instead of dropping faces from the list. Inset panels that show faces count as faces.
- **One-job final:** `python assemble_final.py picture_job.json --mix <mix url> --title <title url> --out final.mp4 [--size 1080x1920 --clip-map up.json --ht-map ht.json]` adds the title card and the approved mix to the picture job; the audio fade is set from the picture length.

## Finals at 1080p
Cut and approve at 720p, then upscale the clips (`upscale_video`, factor 1.5, about 0.9 credit per second) and re-run the same EDL at 1080x1920: render halftone transition clips at the new size, keep the `.ass` as is (PlayRes scales), and take the audio from the approved mix (`-map` the audio of the approved final, `-shortest`). `assemble_final.py --size 1080x1920 --clip-map` (upscaled clip URLs in chain order) and `--ht-map` do this. Details and costs: `../conductor/references/frameo-gotchas.md`, section "vertical 4-minute run".
