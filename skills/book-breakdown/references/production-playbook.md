# Production playbook: a whole book into a chapter-film series

Learned the first time a full book (10 chapters, about 9 minutes each, 9:16) was produced end to end. Read it before the first paid wave. Measured on Seedance 2.5 at 720p, nano-banana-pro 2K stills, ElevenLabs speech and music, sync-3 lipsync; re-verify prices against the live MCP.

## First rule: the style charter
Write `STYLE-CHARTER.md` at the book root before anything is made (art style, bubbles on every dialogue line, narration captions, transition rules) and make it part of every chapter's definition of done. What went wrong the first time: bubbles and halftone/zoom-fade transitions were requested at the start, then dropped because (1) the custom cut builder skipped the finish-cut defaults, (2) an answer "lipsync as I don't see any bubbles" was read as replacing bubbles with lipsync, (3) every report said "not done" but nothing scheduled it, (4) context summaries lost it. Fix: charter file + gate in conductor and finish-cut + finish pass (`overlay_pass.py`) as a scheduled step, run after the last picture fix.

## Order of work (per chapter, own module, own cap)
Keyframes (heated shots first) -> clips (silent) -> strict face review -> scene-master repairs -> speech -> music -> lipsync -> cut plan -> picture parts -> voice track -> music track -> final join with audio. **Every chapter is closed WITH audio**, so the owner can verify it; a silent rough cut is not a deliverable.

## Costs (720p, per chapter of about 45-55 shots, 550-590 s)
- Keyframes 18 cr each (about 900); clips 28 cr/s (about 16,000); repairs about 25% of shots (keyframe 18 + clip 28/s, 2,000-5,000); speech 1 cr per line (about 100 lines); music 66 cr per 120 s bed (5-7 beds); lipsync sync-3 17-19 cr per audio second (230-300 s of dialogue = 4,000-5,500). A closed chapter lands at 25,000-40,000 credits. Plan the book at about 3,000 cr per film minute all in, with a cap per chapter of 130% of its runtime share.

## Continuity: the scene-master method (the fix that worked)
Per-shot clips drift: faces change, hair and outfits swap, skin turns red or grey, extra people appear. What fixed it, in order of cost:
1. **Review every shot strictly** (a `review` subagent per shot, at least 6 frames each, against the character sheets and the neighbouring shots of the same scene). Record `clean_until_s`, `clean_from_s` and defects.
2. **Scene master**: extract a clean frame from the best clip of the scene (`extract_frames` returns merged-video keyframe jpgs usable as references). A repair keyframe = the cast's model sheets + 1-2 scene-master frames + the style still, with a SHORT prompt plus lock lines (hair, outfit, skin tone, "same room, same light, same props, exactly one man"). Then a repair clip from that keyframe as first frame, with the same lock line in the action text.
3. **Trim and hold** when the repair is still flawed: use only the clean window and freeze the last clean frame (free).
4. Keep the decision per shot in `cut_spec.json` (`use`, `trim`, `keep_len`, `nolip`), never in ad hoc edits.

Prompt rules learned: never write "flush", "colouring" or "blush" (skin goes red); add "skin colour unchanged and never red"; for a pale or grey face add "natural warm brown skin, not grey, not blue"; the character sheet wins over a contradicting plan (black dress vs midnight blue), because keyframes follow the sheet; remove contradictions between prompt and sheet (no bracelet vs "twisting her bracelet"); add "nobody looks into the camera lens".

## Dialogue: lipsync, not bubbles (the owner's choice)
- Speech first (`generate_speech`, one item per call, `en-IN`); quotes are voice-bound and length-tiered, so estimate with text "x" when the line is 110 characters or fewer and generate with the real text. Measure each line's duration.
- Per shot piece with an on-screen non-narrator speaker, build a dialogue-only audio: each line at `0.3 s + sum(previous durations + 0.35 s)`, mapped to clip time. Lipsync input is the clip used plus that mp3; sync-3 `cut_off` mode returns video for the audio length; the cut = lipsync `[a, L]` + original `[L, b]` with `L = plan L - 0.15`.
- **Exclude** narrator lines, phone voices (`bubble == "phone"`) and shots in `nolip` (silhouettes, nobody visibly speaking, off-screen speakers: lipsync would make the wrong face talk).
- Tell the owner: lipsync is weak on wide shots; it works on close and medium shots with one clearly visible speaker.

## Audio and the final cut
- Voice track: all lines at `film_start[shot] + 0.3 + running offset`; `film_start` comes from the real clip lengths plus pads, never from a joined file.
- Music: 5-7 beds per chapter chosen by scene mood, placed by shot ranges, 0.20 volume, 1.5 s fade in and 2 s fade out, instrumental.
- Picture parts of at most 16 segments (scale 720x1280, fps 24, libx264 crf 21), at most 5 `run_ffmpeg` jobs per call, serial per module. Final join: concat the parts, `setpts=PTS*(planned/actual)`, amix voice + music (`normalize=0`), `loudnorm I=-16 TP=-1.5 LRA=11`, `-t planned`, libx264 crf 24 + aac. A drift of about 1 s over 550 s is absorbed by the stretch.

## Parallel production
Chapters are independent after the bible: run one worker per chapter, each in its own module (`run_ffmpeg` is serial per module, so a shared module queues every chapter behind one), each bound to its chapter cap and ledger. The main session owns book.json, memory and the final report. Put the whole runbook in a file the workers read first (stages, helper commands, budget rules, ceiling text), tell them not to wait for the owner and to choose the safe default and note it. Get the owner's yes to parallel spending before starting, then do not stop to ask.

## Ceilings
Ask per chapter in words (clothed / implied-silhouette / mainstream-drama nudity with nothing explicit); tiers are in `skills/conductor/references/content-boundaries.md`. Heated shots are keyframed first, each has one pre-written weaker fallback; a refusal is never reworded upward. A ceiling raised after a chapter is closed needs a targeted re-shoot of its heated shots only: keep their durations and lines so speech, music and lipsync of the other shots stay valid, store the new clips under a new state key (`gclip`) and `use` it in the cut spec.

## Known weak spots to tell the owner at the end
Faces drift late in long clips; lipsync is weak on wide shots; supporting-cast voices and [adapted] narration were provisional; no bubbles or halftone transitions unless asked; outfit variance in crowd shots; flares and logo-like marks. List every flaw per chapter in `cut.json`.

## Lessons from running ten chapters in parallel
- Usage limits: ten workers at once hit the 5-hour usage limit; resume them with the same agent ids after the reset time shown in the error. Their notes and state files make a restart cheap, so keep a progress log in each chapter's NOTES.md.
- Shared helper scripts that write by name collide across workers (one wrote chapter 4 lipsync results into chapter 10). Give each worker chapter-suffixed copies, and check results files hold only that chapter's keys.
- `run_ffmpeg` is limited to about 80 runs per hour across the whole workspace and to a few concurrent runs: reuse old audio and old picture parts when a re-cut keeps shot starts identical, rebuild only the parts that changed, and retry after a wait on `rate_limited` / `too_many_runs`.
- Keyframe prompts containing "leave the upper third calm" produced blank bands and stacked panels; use "full-bleed, edge to edge" instead. Thin cream borders from style stills can be hidden with a 5% crop and rescale.
- Viewers cannot open files past about 600 s: check long final cuts with an ffmpeg contact sheet of the late section, or frames from the part files.
- A late ceiling change is cheap if shot durations and lines are kept: about 2,000-3,500 credits per chapter for 5-10 shots, voice and music reused, only the affected picture parts rebuilt. Do not touch non-sensual beats (assault, rescue) when raising a sensuality ceiling.
- Frameo has no zip/export tool; a text request through the feedback channel returns only a report id.

## Lipsync correctness rules (learned in the sweep after the first full cut)
- **sync-3 animates ONE face (or every face) per piece, chosen by how the picture looks, never by whose voice it is.** In two-person shots, or when one piece carries both speakers' lines, the wrong face (often the other sex) mouths the line. Across the book this affected roughly a third to two thirds of the lipsynced pieces in chapters with many two-person shots (ch02 26/41, ch04 36/88 line windows, ch08 13, ch10 34 lines, ch01 19 lines).
- **Plan lipsync per speaker, not per shot piece:** only lipsync a window where exactly one clearly visible speaker's face is the target, with that speaker's audio alone. Never mix two voices into one lipsync audio.
- **Always audit the result before the cut:** diff the lipsync output against its source clip every 0.5 s (run_ffmpeg `blend=difference` or similar) and map the change to a face; compare with the speaker of each line. Keep the lipsync result only in windows where the speaker's own face moved; elsewhere use the original clip.
- **Best technique found (ch06):** composite the lipsync result into the original clip only inside a box around the speaker's face during that speaker's lines. It keeps sync for the speaker and leaves the listener untouched.
- **Silent source clips also open the listener's mouth** (Seedance, mostly the woman). For two-person dialogue shots write the prompt with explicit speaking turns ("only X speaks during seconds a-b; Y's lips stay closed and still") and review the lip motion per line before lipsync.
- Never lipsync narrator, phone or off-screen voices, silhouettes, or backs to camera.

## Clothing continuity rules
- Within a scene a garment that is off stays off (or is replaced by an obvious covering) until an explicit dress action; check the clothing state of every character at the first and last second of every shot, in cut order, before the final cut. A re-shot or inserted shot must start from the real last frame (or a keyframe built from real frames) of its neighbour.
- Sheet/outfit mismatches that read as flips: dress length (knee vs floor gown), shirt on/off, jackets, hair ribbons, sunglasses/watches. Fix the odd shot out; never rebuild the scene.
- Raising a content ceiling after the cut is the main source of flips: the re-shot shots inherit different clothing than their neighbours. Re-shoot the whole intimate sequence's boundary shots, or audit immediately after.

## Finish pass lessons (bubbles, captions, transitions)
- Run the finish pass (`skills/finish-cut/scripts/overlay_pass.py`) as the LAST step on the final picture; it overlays bubbles, captions and transitions without changing duration, frame count or audio (copy the audio stream; compare the audio md5).
- Hand-pasting long ffmpeg job JSONs corrupts digits; render parts locally (`run-local`) and upload the result, or paste at most 2-3 jobs per call and PSNR-check against a local render.
- Face positions are the weak point: read them from 2 gridded frames per shot, add samples for shots with cuts or movement, describe cut-heavy shots in segments; check 12+ bubbles per chapter in frames, including shots with close-ups, plus a wipe peak, a scene change and the first and last second.
- A final cut with a mid-stream decoder reconfig makes `-ss` seeks land seconds off: re-encode the base once locally (same frames and timestamps) before overlaying.
- Per-chapter speaker tags: the series speakers file must list every speaker (a missing name produced a tag "THE"); add a chapter speakers file.
- Local renders fill the disk: scratch on a big drive, delete media when done.
