# Book-production scripts

Helper scripts the conductor uses to run a long job (a chapter of a book, or any job with dozens of shots) without hand-pasting 30 KB calls. They are the reusable core of the scripts written during the first full book. Python 3.10+, standard library only, no network (except the optional `--verify` link check), no credits: they compose and record calls, you run the Frameo tools.

Every command takes **JOB**, the job folder that holds `relay.json` (for a book: `frameo-jobs/<book>/<chapter>/`). Shots are numbered from 1 over the flattened segments of `relay.json`. `$RELAY_HOME` is resolved as in the conductor's Host note.

```
python "$RELAY_HOME/skills/conductor/scripts/chapter_driver.py"   <command> JOB ...
python "$RELAY_HOME/skills/conductor/scripts/lipsync_plan.py"     <command> JOB ...
python "$RELAY_HOME/skills/finish-cut/scripts/cut_builder.py"     <command> JOB ...
```

Exit codes: 0 ok, 1 a check failed (a link is unreachable, an asset is missing with `--strict`), 2 bad input (the message starts with `FAIL:`).

## Files in the job folder

| File | Written by | Holds |
|---|---|---|
| `state.json` | `chapter_driver` | `assets` (lock id to link), `kinds`, `labels`, `supersedes`, and the recorded results per kind: `kf`, `clip`, `rkf`, `rclip` (plus any key you add, for example `gclip`), `<kind>_gen` generation ids |
| `calls/<name>.draft.json`, `calls/<name>.json` | `chapter_driver` | the exact items before and after the quote ids are merged; the second is what you send |
| `ledger.jsonl` | `chapter_driver`, `lipsync_plan` | one row per charge, kinds `keyframe`, `clip`, `retake`, `speech`, `lipsync` |
| `speech_items.json`, `lines_by_shot.json`, `speech_gen.json`, `speech_urls.json` | `chapter_driver` | speech batching and the measured links and lengths |
| `cut_spec.json`, `music_urls.json`, `final_clips.json` | you | the per-shot cut decisions, music tracks and sections, optional replacement clips |
| `lip_plan.json`, `lip_audio_urls.json`, `lip_gen.json`, `lip_results_urls.json`, `lip_results.json` | `cut_builder`, `lipsync_plan` | the lipsync plan and its results |
| `jobs/*.json` | `cut_builder`, `lipsync_plan` | `run_ffmpeg` jobs, and `*call<N>.json` files holding up to 5 jobs each (one call) |
| `reviews/brief-NN.md` | `chapter_driver briefs` | one review brief per finished clip |

## chapter_driver.py

| Command | What it does |
|---|---|
| `init JOB [--bible book/bible.json] [--assets assets.json] [--strict]` | Builds `state.json` assets. For each lock it takes, in order: the `--assets` file (`{"<lock id>": {"url","kind","label"}}`), the lock's own `url`, then the bible entry named by `shared_from: "bible:<id>"` (first of `images`, `plates`, `refs`; a character variant uses its own image and its `state` in the label). A lock with `variant_of: "bible:<base>"` supersedes the chapter's lock for the base look, so the base sheet is dropped when both are in one shot's `refs_used`. Voice-only locks have no image. Locks it cannot resolve are listed (with `--strict`, exit 1). The bible is found through `series.bible` in `relay.json` when `--bible` is not given. Re-running keeps recorded results. |
| `kf JOB A B` | The free estimate (`EST=` items for `estimate_cost`, prompt replaced by a stub) and `calls/kf_A_B.draft.json` for the keyframes of shots A to B: reference links (characters, then places, props, style), an ordered "Reference images: 1 = ..." preamble, then the segment's `keyframe_prompt` (or `prompt`). Options `--image-model` (nano-banana-pro), `--image-resolution` (2K); aspect comes from the job. |
| `clip JOB A B` | The same for clips: first frame is the recorded `kf` for the shot, up to `--max-refs` (3) character sheets as references, duration from the segment, model and resolution from the job (override with `--video-model`, `--video-resolution`). |
| `retake JOB 5,9 [--lock TEXT / --lock-file F] [--extra TEXT]` | Clips again from the existing keyframes with an identity-lock sentence appended to each prompt. The lock text is yours (hair, outfit, "never looks into the lens"). Draft `calls/retake_5_9.draft.json`. |
| `rkf JOB 5,9 --spec S.json` / `rclip JOB 5,9 --spec S.json` | The scene-master repair (see the playbook): a repair keyframe from the cast's sheets, scene-master frames and the style still plus a lock line, then a repair clip from it. Spec below. Results are recorded as `rkf` and `rclip`. |
| `gen JOB NAME q1,q2,...` | Merges one quote id per item into `calls/NAME.draft.json`, writes `calls/NAME.json` (without `shot_number`) and prints it. Refuses a count mismatch (a quote is bound to its exact items). Save, then send exactly that. |
| `record JOB KIND 3=LINK,4=LINK [--verify]` | Remembers result links under `state.json[KIND]`. A bare id is expanded to a link (`kf`/`rkf` become an image link, anything else a video link). `--verify` does a HEAD request on each. Prints the shots still missing for `kf` and `clip`. |
| `ledger JOB KIND 3=GEN,4=GEN --credits 18[,..]` | Records generation ids (`state.json[KIND_gen]`) and appends ledger rows (`kf` is `keyframe`, `clip` is `clip`, `rkf` and `rclip` are `retake`). |
| `speech-items JOB [--language-code en-IN]` | Turns `dialogue.lines` into `speech_items.json` (the speaker's `voice_id`, cleaned text) and `lines_by_shot.json`. A speaker with no `voice_id` lock is an error. |
| `speech-est JOB A B` | The `EST=` for items A to B (0-based slice) and a listing of their real texts. Lines of 110 characters or fewer are priced flat, so the estimate sends the text `x`; generate with the real text. |
| `speech-gen JOB A id1,id2 [--credits 1,2]` | Records generation ids for items A.. and ledger rows (1 to 3 credits a line by length). |
| `speech-urls JOB A < rows` | Reads rows `<link or id> <seconds>` (seconds are the measured `duration_seconds`) for items A.. into `speech_urls.json`. |
| `briefs JOB [--kind clip] [--prefix brief-]` | One markdown brief per shot that has a clip: the clip and keyframe links, who is on screen, the content ceiling (`style.avoid[0]`), the planned action and the seconds to inspect with `view_image`. |

Bare-id expansion uses Frameo's content hosts as read from the live tools (constants at the top of the script); put `{"prefixes": {"image": "...", "video": "...", "audio": "..."}}` in `state.json` to override them. Prefer recording full links.

### Retake spec (`rkf`, `rclip`)

```json
{
  "masters": {"studio": ["<link to a clean frame of the scene>"]},
  "keyframe_tail": "Nobody looks into the camera lens. No readable text, signs or logos. Vertical 9:16.",
  "clip_tail": "No text, numbers, signs, captions, bubbles or logos anywhere.",
  "still_regex": "opening frame of the clip: (.*?)\\. No text",
  "action_regex": "ACTION: .*?(?= No text, lettering)",
  "replace": [["flush", "tension"]],
  "defaults": {"keyframe_lock": "", "clip_lock": ""},
  "shots": {
    "38": {"master": "studio", "keyframe_lock": "NEHA: heavy low bun, charcoal suit. Natural warm brown skin.",
           "clip_lock": "Keep the first frame's studio, light and outfits the same for the whole clip."}
  }
}
```
`master` is a name from `masters` or a list of links (clean frames from `extract_frames` of the best clip of the scene). `still_regex` and `action_regex` (optional) cut the shot description out of `keyframe_prompt` and `prompt`; without them the whole text is used. `replace` swaps words that make a model drift (for example a word that tints skin red); per-shot `still` and `action` override everything. Non-ASCII dashes are scrubbed from the action text.

## cut_builder.py (in `finish-cut/scripts/`)

Builds the long-film cut: one picture window per shot, voice from measured speech, music beds by scene, final join.

| Command | What it does |
|---|---|
| `build JOB [--part-size 16] [--size WxH] [--fps 24] [--crf 21] [--music-gain 0.20] [--fade-in 1.5] [--fade-out 2.0]` | Writes `jobs/cut_picture.json` (a job per part of at most 16 segments, size from `job.resolution` and `job.aspect_ratio`), `jobs/picture_call<N>.json` (up to 5 jobs per `run_ffmpeg` call), `jobs/cut_voice.json`, `jobs/cut_music.json` (when `music_urls.json` has sections), `jobs/starts.json` (film start of each shot, total length, part count) and `lip_plan.json`. |
| `outputs JOB part1=URL ... voice=URL music=URL` | Remembers the links `run_ffmpeg` returned for the parts, voice and music. |
| `final JOB [--actual S / --factor F] [--out final.mp4] [--loudness -16] [--crf 24]` | Writes `jobs/final.json`: concat the parts, `setpts=PTS*F` with `F = planned / actual` (`--actual` is the measured length of the joined parts; drift of about 1 s over 550 s is absorbed; a factor outside 0.9 to 1.1 is refused), mix voice and music with `amix normalize=0`, `loudnorm I=-16 TP=-1.5 LRA=11`, `-t planned`, libx264 plus aac. About 10 minutes for a 550 s film; the job timeout is the 600 s maximum. |

`cut_spec.json`:

```json
{"use":  {"7": "gclip"},
 "trim": {"8": [[0, 4.8], [6.0, null]], "9": [[0, 5.0, "orig"]]},
 "nolip": [5],
 "keep_len": [9],
 "offscreen_speakers": ["narrator"]}
```
- `use`: which recorded result a shot's picture comes from (any `state.json` key). Default: the recorded `rclip` repair clip if there is one, else `final_clips.json`, else `clip`. Naming a key with no result for the shot is an error.
- `trim`: the windows kept, in order; `null` means to the planned end; a third item `"orig"` takes that window from the original clip instead of the chosen one. The shot's length is the sum of the windows.
- `keep_len`: after trimming, hold the last frame so the shot is back to its planned length.
- `nolip` and `offscreen_speakers`: see lipsync below. Voice-only locks and the speaker `narrator` are never lipsynced.

Timing rules (kept from the first book): a shot lasts at least `0.4 s + sum(line length + 0.35 s)`, a shorter picture is held on its last frame (never stretched); each line starts at `shot start + 0.3 s` and the next follows after the previous length plus 0.35 s; shot starts always come from the real window lengths plus pads, so a retake that changes a length moves only the later starts.

`music_urls.json`: `{"tracks": {"a": {"url": "...", "dur": 118.4}}, "sections": [{"from": 1, "to": 12, "tracks": ["a", "b"]}]}`. Each section runs from the start of shot `from` to the end of shot `to`; its tracks are laid in order and looped to fill it; every bed has a fade in and out and a gain of 0.20.

## lipsync_plan.py

The sync-3 recipe. A *piece* is one trim window of one shot (`key` `"<shot>.<window>"`) with an on-screen, non-narrator, non-phone speaker; shots in `nolip` are skipped.

| Command | What it does |
|---|---|
| `plan JOB` | Writes `lip_plan.json` (the same plan `cut_builder build` writes). |
| `audio JOB [--group 5]` | One dialogue-only mp3 per piece (every line delayed to its clip time, mixed), grouped into `jobs/lip_audio_grouped.json` and `jobs/lipcall<N>.json`. |
| `audio-urls JOB 1.0=URL 6.0=URL` | Remembers the mp3 links `run_ffmpeg` returned. |
| `next JOB A B` | `EST=` for pieces A to B and one draft call each in `calls/lipsync_<key>.draft.json` (`video_url`, `audio_url`, `model: sync-3`). One `generate_lipsync` per call, each with its own quote. |
| `record JOB A B gen1,gen2 [--credits 18]` | Generation ids (`lip_gen.json`) and, with `--credits`, ledger rows of kind `lipsync`. |
| `save JOB A [--verify] < rows` | Result links for pieces A.. (`<link or id>` per line, or `<key>=<link or id>`). When every piece is back it writes `lip_results.json` with `L = planned L - 0.15`; run `cut_builder build` again and each piece plays lipsync `[a, L]` then the original `[L, b]`. |

Tell the owner that lipsync is weak on wide shots and that it animates whatever face is visible, which is why narrator, phone and off-screen voices are excluded.

## A typical run

1. `chapter_driver init JOB`, then `kf JOB 1 6`: `estimate_cost` with the printed `EST=`, `gen JOB kf_1_6 q1,...,q6`, send `calls/kf_1_6.json`, `record JOB kf 1=...`, `ledger JOB kf 1=<gen>... --credits 18`.
2. The same with `clip`; `briefs JOB` for the reviewers; retakes with `retake` or `rkf`/`rclip`.
3. `speech-items`, `speech-est`, generate, `speech-gen`, `speech-urls`.
4. Write `cut_spec.json` and `music_urls.json`; `cut_builder build JOB`; `lipsync_plan audio JOB`, run the audio jobs, `audio-urls`, `next`, generate, `record`, `save`; `cut_builder build JOB` again to splice.
5. Send the `picture_call*.json`, `cut_voice.json` and `cut_music.json` jobs with `run_ffmpeg` (one call at a time per module), `cut_builder outputs`, `cut_builder final`, send `jobs/final.json`, then listen and review.

What these scripts do not do: they never call Frameo, never decide a retake, never reword a refused line, and do not compress prompts (the planners write them short). Order of work, costs and continuity method: `$RELAY_HOME/skills/book-breakdown/references/production-playbook.md`.
