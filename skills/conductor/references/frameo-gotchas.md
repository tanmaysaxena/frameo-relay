# Verified Frameo behaviour (read from the live MCP on 2026-11-15; session lessons added 2026-11-16)

Re-check before relying on any of it: the MCP changes. Sources are the tool descriptions and `get_skill` texts.

## Frames and continuation
- On Seedance, `first_frame_url` / `last_frame_url` "guide the clip rather than pin it"; "the end follows the image loosely"; both count as reference images (folded into `reference_image_urls`). A shared image is therefore NOT a guaranteed join. Frameo's own method for a continuation is serial: extract the last frame of the finished clip, open the next clip on it.
- On models other than Seedance, frames combined with reference images or audio are refused; the clip takes the first frame's shape.
- Every image (folded frames included) needs width/height between 0.4 and 2.5 on all Seedance models; a bad one fails only after the call started.
- Adding a last frame shifts the `@Image` slot numbers the prompt cites. Cite by slot as the Seedance guide says, with folded frames first.
- Seedance 2.0 models silently drop reference images past 9. `seedance_2_5` takes 30.
- `seedance_2_5` clips are 4 to 30 s, whole seconds.
- Seedance treats most video-to-video requests as an edit; the source clip must be on record in the module Library. `wan_3_0` is the "edit or extend" model (spike candidate).
- Prompts must be sealed: the model never saw the other clips. Never "previous", "as before", or a shot number.
- **The server rewrites a clip prompt** to open with "begins on exactly @Image1 (the first frame) and ends on exactly @Image2 (the last frame)". With both frames set, cite the references from **@Image3**: first frame = @Image1, last frame = @Image2, refs follow. Cite by that slot order, not by the order you passed them.
- **A 30 s multi-beat Seedance clip morphs and deforms at its beat boundaries** (two characters fusing, a body appearing behind another, a room reshaping) and drifts in long continuous takes; first-to-last interpolation makes it worse. Prefer single-beat clips of 6 to 10 s with their own first and last stills, or keep the long clip and cut windows around the morph zones (see `finish-cut`: ffmpeg `fps=1/2,scale=150:-1,tile=5x3` contact sheet, one image per clip, viewed at high resolution).
- Lens flares or glowing eyes can appear mid-clip on close-ups; check close-up clips at 2 s steps, not just first and last frame.

## Quotes, spend, replays
- `estimate_cost` returns one `quote_id` per item: single-use, valid 15 minutes, bound to that item's settings and links (first/last frame, reference images, audio, video references). A different setting is refused uncharged.
- **The prompt is not part of a video or image quote.** Quote with a placeholder prompt ("draft for pricing") and send the real prompt in the generate call; the links, frames, references, model, duration and resolution must be identical. This saves pasting every prompt twice.
- `estimate_cost` and `generate_videos` / `generate_images` take 1 to 10 items per call (`bad_item_count` above that): split 18 clips into 10 + 8. `generate_speech`, `generate_music` and `generate_sound_effect` are ONE item per call: send many calls in one message, quote them in estimates of up to 10.
- `generate_videos` takes 1 to 10 items; `confirmed_by_user` is set once for the whole call. The items render in parallel on Frameo's side.
- **A stuck clip is usually just slow**: one ran 3 to 5 times its estimate (about 40 min against 8) and then finished and was charged. First `wait_task`, then re-send the SAME call (it returns `replayed`, no charge). A second quote for the same shot is a second charge (a double-charge happened once: 780 credits for one clip). Only after a long wait, and only with the owner's budget, make a retake.
- A clip failed by the content filter (`CONTENT_POLICY_OUTPUT_VIDEO`) is refunded and its quote is spent: rephrase (drop the unusual framing, "empty of people" plus people appearing at the end tripped it once), take a new quote, and mark the old ledger row `refunded: true`. It does not use the retake allowance.
- Image charges often come in at about half the quote (`charge_note`); clips and speech match. Log `credits_charged` from `wait_task`, not the quote.
- If the outcome of a call is unclear, send the SAME call again: items that started return their work marked replayed and charge nothing. A new quote starts new work.
- An `out_of_credits` refusal still uses up its quote. A charge can differ from its quote (`credits_charged`, `credits_quoted`, `charge_note` on the finished result).
- `analyze_media` is paid with NO quote. `run_ffmpeg` is free but serial.
- `whoami.spent_by_this_connection` is a cross-check for the ledger. It also drifts by a few credits while work is running; reconcile by the balance change (`credits` before minus after). Typical ledger errors: a duplicate row for a replayed or slow clip, a refunded failure still counted as spent, a placeholder quote logged instead of the charge.
- Speech quotes by text length (1 to 3 credits a line); lipsync is per second of voiceover; music is per second of bed (120 s about 66 credits); sound effects 1 to 2 credits each. A 30 s 480p Seedance 2.5 clip is 390, 720p 840.
- `generate_music` is 10 to 120 s per call: use one bed per mood, looped or crossfaded in the mix.

## Links and media
- Media links open for about an hour. An expired link still works as an input to every Frameo tool, so refreshing is only for opening the file. Refreshing before a call can desync it from its quote: do not.
- Use `media_id` as identity. Only a link "generated, uploaded or imported here" is accepted as a media input.

## Serial and rate limits
- One `run_ffmpeg` or `analyze_media` call per module at a time (`module_busy`); about 80 runs an hour; `save_note` is refused while a run is going.
- The account's real concurrency limit is not documented anywhere I could read: measure it (the smoke job does) and set `job.max_parallel` from what happens.

## Workspace
- The connection works in one workspace at a time. `switch_workspace` changes it for every tool from the next call and discards unredeemed quotes. Pin one workspace per job, check `whoami` before every paid wave.
- If the credits turn out to live in another workspace: stop, tell the owner which workspace and its balance, switch only on their word, then **re-pin**: new project and module there (projects do not move), update `job.workspace_id`, `job.frameo`, re-check that the chosen voices exist there (`search_voices`), and tell them where to look in the web app (the workspace selector). Earlier media stays in the old workspace.

## Audio
- Native clip audio invents the voice afresh in every clip. One character speaking in more than one clip keeps one voice only through `generate_speech` with the same `voice_id`, then `generate_lipsync` for on-screen speakers.
- Read `get_skill("video-prompting", path="video-guide-seedance-dialogue.md")` before any spoken line in a Seedance prompt.
- Dialogue that is shown as speech bubbles needs no lipsync: render the clips silent, voice each line with `generate_speech`, time the bubble to the measured `duration_seconds`. Mouths will not match; say so. Lipsync stays for plans that promise it.
- One voice per character; a narrator who is not on screen is a **voice-only character lock** (`voice_only: true`, `voice_id`, no image). Give the narrator a voice different from every character unless the owner says the story is told by one of them.
- A voice found in one workspace may not exist in another: re-run `search_voices` after any workspace change. Bracketed delivery cues (`[warm, playful]`) work on elevenlabs voices; a repeated word can appear in a take ("Oh? Oh?"): listen, regenerate that one line (1 credit).
- Video models cannot spell: text, titles, bubbles and captions are always added in the edit (`run_ffmpeg` with an `.ass` file), and prompts keep clear empty space for them.


## Lessons from a 720p finals pass
- A 720p regeneration of the same prompt and frames is a NEW take: every cut window picked on the 480p drafts is invalid. Budget a contact sheet per clip (`fps=1,scale=132:-1,tile=10x3`) and re-pick windows. Keep dialogue bubble tails (`hx`) tied to the speaker's head position in the new clip.
- Upscaling the 480p clips instead keeps the edit but `upscale_video` refuses clips over 30 s (generated clips are 30.04 s): cut to <=30 s first.
- Story logic beats per-clip polish: if a scene ends with the characters in bed, the next shot must not be an empty bed. Check the implied location and state of every cast member across chain joins before the review gate.
- Hand-pasting a 30 KB `run_ffmpeg` job is error-prone (a bubble lost its ellipse, a caption got zero duration). Keep generated sidecars small, diff what was sent, and verify caption frames with a `select='between(t,...)'` tile before the audio pass.
- Intimacy tiers: the owner-chosen level stays non-explicit (clothed, covered, implied). Quote once, if a clip is filtered rephrase once, do not probe the filter.

## Lessons from a vertical 4-minute run (1080p and paperwork)
- **Finals by upscale, not re-render**: `upscale_video` (BytePlus Standard, factor 1.5 turns 720x1280 into 1080x1920) costs about 0.9 credit per second (203 credits for 12 clips, 234 s) against 72 credits per second for a Seedance 1080p re-render (about 17,000). Quote each clip with `estimate_cost` (kind `upscale`, same `video_url`, `factor`, `model`), then fire one call per clip with its own `quote_id`; all 12 finish together in about 10 minutes. Upscale only after the 720p cut is approved; it sharpens what exists and cannot add detail. The upscaled clips can come out a few frames shorter than the 720p originals, so reuse the approved mix audio with `-shortest`.
- **Re-cutting at 1080p**: render halftone clips again at 1080x1920 (`halftone_transition.py jobs 1080 1920 24 0.9`, then an `hflip` copy), re-run the same `.ass` (its `PlayRes` stays 720x1280, libass scales it) and scale each upscaled clip with `scale=1080:1920,setsar=1`. Bubbles and timing carry over unchanged; map the audio from the approved final instead of rebuilding it.
- **Do not skip Phase A**: one early run went a whole job without `relay.json`/`plan.md`, and the paperwork had to be rebuilt afterwards from the session transcript (the exact `generate_videos` prompts are in the tool-call inputs, the clip ids in the EDL builder). Draft and validate before the first paid call so `check-ready`, the ledger audit and the locks exist while they can still catch something. If it is ever done late, `lock` only after the owner has approved the references and style, then `check-ready` each segment.
- **Generated lines**: after the owner approves them, set `approved: true` in `relay.json` and mark them approved in the plan's "Generated dialogue" table (with the date). Lines already voiced and cut stay in the film; a later change means regenerating that speech and re-cutting that window.
- **Spend counter**: `whoami.spent_by_this_connection` moved about 2,000 to 2,500 credits more than the ledger across the V2 run. State the gap in the report instead of presenting the ledger as the total; the counter may include other activity on the same connection.
- `extract_frames` can return `still_running` once on a long file; call it again (it is free).

## Lessons from retaking one shot after the cut
- A retake changes more than the clip: re-measure the line times with `analyze_media` on the new clip, move that shot's bubble `Start`/`End` in the `.ass` (the new speech runs earlier or later), rebuild the dialogue lane by splicing the new clip's audio over its time range (`atrim` both, `concat`, `apad` the new part to the clip length), and re-check every mute window in the sound mix: a gate that silences the tail of a shot (here 14.8 s) clipped the last word "Ours." until it moved to 15.25 s.
- Reuse the finished video: when only the audio changes, mux with `-map 0:v -c:v copy` (about 4 minutes instead of 12 for a 1080p re-encode); build the new mix as an audio-only job (`-vn`).
- Listen-check cheaply: cut the first 30 s of audio with `-vn -c:a copy` and run `analyze_media` on that (about 5 credits) instead of the whole film (about 31).
- Retake wording that fixed a half-spoken line: "speaks the COMPLETE @Audio1 from its very first word to its very last word, including the small pause after his name, only her lips move for the whole N seconds", with the start second moved slightly earlier (6.4 s instead of 6.6 s).
- Script and the picture builder files live with the job: `edit/build_picture_1080.py` rebuilds the 1080 picture from the approved 720 job.

## Lessons from a 5-minute, 17-shot hard-cut film (panel-writer run)
- **Reference sheets leak**: a character's base sheet passed alongside an outfit sheet leaks its old outfit into keyframes. Pass the outfit sheets only (they already carry the face) and call the base sheet "face, hair and build only" only when no outfit sheet exists for that person.
- **Vehicle shots start from a passing keyframe**: edits of an empty-plate or exterior image give an exterior car, boxes in the cabin or a doubled steering wheel. Rebuild the interior keyframe from scratch with the passing plate as the only layout reference, one wheel on the driving side, no props.
- **Never trust the planned line times**: models start speech late or early (a line planned at 0.8 s came at 1.45 s, another came 7 s late). Join all clip audio once (`atrim` each clip to its length, `concat`, mono mp3), run ONE `analyze_media` on it, subtract each clip's start to get clip-local times, and run a short `analyze_media` on any clip where a line looks displaced (silhouette or cutaway shots drift most). Place narration and bubbles from the measured times, not the plan.
- **Gate the native audio**: clips also generate sighs, laughs, kisses, an invented phone voice and unrequested music. Build the dialogue lane by muting the joined audio except the measured line windows (`volume=0:enable='not(between(...)+...)'`), keep a whole clip open only when its ambience is wanted (a ticking clock). A retaken clip goes in as its own input with `adelay` at the picture start (the joined audio still holds the old take).
- **Retake timing shifts every later start**: a retake that is 0.03 s longer moves every later narration start; compute film starts from the clip durations in `state`, not from the joined audio.
- **Long bubbles**: when a bubble must clear several faces and finish_cut reports no free spot, split the line into two timed bubbles at a natural pause (two entries, same speaker) instead of dropping faces from the list; keep inset-panel faces in the list as faces.
- **Queue stalls**: a `run_ffmpeg` join of 17 clips sat `running` for about 1.5 hours and blocked the module (`module_busy`) while generations kept working. Plan the audio join as soon as the clips exist, give clip audio extraction its own job, and expect later jobs in the module to wait. An `analyze_media` that never returns blocks the same queue.
- **`estimate_cost` limits**: 1 to 10 items per call; upscale quotes are per video (`kind: "upscale"`). `generate_videos` items need `index` as well as the quoted settings. Estimates use a placeholder prompt; the real prompt can differ if settings match. `view_image` takes `media_url` and `at_seconds` and shows a frame of any video, which `extract_frames` (first and last frame only) does not.
- **Costs seen**: 720p Seedance clip 28 credits per second; 1080p upscale 0.9 per second (257 credits for 300 s); a 5-minute listen check about 38 credits.
- A content-policy refusal on one narration line was dropped from the shot, not reworded or retried.

## Lessons from the motion and fix passes
- **Stiff shots are a prompt problem**: put an action in every 2 to 3 seconds of the prompt ("something moves every second", then a concrete beat per time slice: stands, walks, circles, slings a bag, hand on head). A static camera plus "keep the upper third calm" produces still frames; a slow sideways slide or arc and a "never closer than a medium two-shot" limit gives movement without crops.
- **Speech that never shows lips**: for silhouette or cutaway shots generate the clip with no audio references and lay the speech file in the edit at chosen times. The model otherwise starts the line 7 seconds late and idles before it.
- **A longer motion prompt can make the model repeat a bound line**: after the line it played the reference audio a second time and invented a line for the other character. Check every retake with `analyze_media`; if the repeat comes late, trim the clip in the edit and set the clip's seconds in the state so later starts shift correctly.
- **Logos and borders live in the keyframe**: a laptop with a fruit logo and a cream margin came from the opening still, so the clip prompt could not remove them. Edit the still first (nano-banana-pro, 18 credits, "change only X") and use it as the first frame. The same worked for adding seatbelts.
- **Music beds follow the picture**: compute bed starts and fade-outs from the film start of the shots they cover, not from fixed seconds, or a retake that shortens a shot leaves the wrong bed under it. Put the final audio fade at the real mix length.
- **Close the task list**: mark every wave task completed when the deliverable is out; a stale in_progress wave looks like a hung job to the owner.
## Tool facts confirmed in the long run
- `generate_videos` and `generate_images` items take `index` (and no `kind`); `estimate_cost` items take `kind` (`video`, `image`, `upscale`, ...), 1 to 10 per call. An upscale quote is per video URL.
- Quotes are single use and 15 minutes long; rebuild the quote if the call is delayed. Upscale and image charges can differ from the quote by 1 credit.
- `analyze_media` shows its price only after the run (about 38 credits for 5 minutes, 8 to 11 for one clip); the counter (`whoami.spent_by_this_connection`) does not seem to include it. The counter otherwise matched the ledger exactly in this run.
- `extract_frames` returns only the first and last frame; use `view_image(media_url, at_seconds)` for others (files under 100 MB).
- `show_generations` and long `wait_task` calls return after about 30 seconds even with a longer timeout; loop.
- `run_ffmpeg` and `analyze_media` share one serial queue per module; generation and upscale calls run in parallel with it.
- Content-policy refusals on a narration line charge nothing; drop or adapt the line once, never probe.
- Edit a keyframe with `generate_images` (nano-banana-pro, 18 credits, the old still as `image_urls`, "change only X"): removes logos and borders, adds missing safety gear.
- Retake costs scale with length (28 credits per second at 720p); count them before offering a retake.

## Lessons from the first full book (read 2026-11-18)
- `INVALID_INPUT_INACCESSIBLE` on a still or clip generation is intermittent: retry with a NEW quote (the failed charge is refunded; confirm on the balance).
- A quote is bound to the exact link count: send the same number of links you quoted.
- `generate_speech`: the quote is voice-bound and length-tiered; estimate with text "x" for lines of 110 characters or fewer, generate with the real text.
- `generate_lipsync` (sync-3, `cut_off`): output covers the audio length from the clip start; about 17-19 credits per audio second; one per call. It animates the visible face whatever voice is sent, so never send narrator, phone or off-screen voices.
- `extract_frames` on a finished clip returns merged-video keyframe jpg URLs that work as reference images for a scene-master repair keyframe.
- Seedance turns skin red or orange on "flush", "colouring", "blush": write "skin colour unchanged and never red".
- `run_ffmpeg`: one job at a time per module (`module_busy`, retry), at most 5 jobs per call; a 108-input voice track and a 16-segment picture part both work; a 550 s final join with loudnorm takes about 10 minutes. Use each chapter's own module for parallel chapters.
- `wait_task` returns about every 28 s with `still_running`; wait on the slowest id and loop. Foreground `sleep` is blocked in the harness: use Monitor until-loops.
