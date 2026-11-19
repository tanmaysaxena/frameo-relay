# Overlay pass: bubbles, captions and designed transitions on a finished cut

`scripts/overlay_pass.py` finishes a chapter that already has a final cut with audio (a book film built by `cut_builder.py`, or any film whose shot starts and measured voice lines are known). It overlays on the existing picture and never changes the length or the audio:

- **Speech bubbles for every dialogue line**: angular (chamfered) polygon, triangular tail to the speaker's face, skewed name tag in the character's colour, hard offset shadow in that colour, pale triangle "halftone" shading in the lower-right corner, bold DejaVu Sans. Timed from the measured line start to its end plus 0.35 s. Long lines (over 70 characters) become consecutive timed bubbles split at sentence ends, commas or conjunctions. A bubble never overlaps a face box, never leaves the frame and stays out of the lower fifth.
- **Narration** as a yellow angular caption box in the lower fifth (moved to the top band only when a face sits in the lower band). **Phone lines** (`bubble: "phone"`) as a pale-cyan bubble hugging the left or right frame edge with a zigzag tail to the edge and a `(PHONE)` name tag.
- **Cuts inside a scene**: a halftone dot wipe (magenta dots, cyan layer lagging, 0.7 s, flat peak of about 0.14 s that hides the cut), one of 8 directions, dealt from a shuffled deck so the same direction never plays twice in a row.
- **Scene changes** (new place or time): the outgoing shot zooms in 14 % over its last 0.5 s and dips to black; the incoming shot starts zoomed in, fades up from black and settles to normal over its first 0.5 s. Bubbles are drawn above the zoom and are not scaled.

Everything is free `run_ffmpeg` work. The script itself needs no network; only `run-local` downloads job inputs when you run jobs on your own machine.

## Order of steps

```
S="$RELAY_HOME/skills/finish-cut/scripts/overlay_pass.py"
python "$S" ht-jobs JOB          # once per frame size; the 8 clips are reusable by every chapter (send ht_call1.json, ht_call2.json)
python "$S" outputs JOB ht_LR=URL ht_RL=URL ...      # or keep them in a series-wide file and pass --ht-clips
python "$S" measure JOB          # optional, needs a local ffmpeg: real cut frames vs starts.json (plan then uses them)
python "$S" sheet JOB            # face contact sheets (jobs); look at them, write JOB/face_boxes.json
python "$S" plan JOB --speakers series/speakers.json
python "$S" window JOB 15.5 21   # proof clip for any time window; send it, view_image the result
# send finish/jobs/ov_call1.json, ov_call2.json ... (each is one run_ffmpeg call of up to 5 jobs, one after the other)
python "$S" outputs JOB ov01=URL ov02=URL ...
python "$S" join JOB             # send finish/jobs/ov_join.json (stream copy, seconds)
python "$S" record JOB URL       # writes JOB/cut_finish.json
```

`plan` exits 1 if a bubble could not be placed clear of the faces, 2 on bad input (`FAIL:` message). It prints the number of bubbles, captions, wipes and scene changes, the part count and each job's JSON size.

## Files read from JOB

| File | Needed | Holds |
|---|---|---|
| `relay.json` | yes | dialogue lines (`id`, `segment`, `speaker`, `text`, optional `bubble: "phone"`), chains with `scene_ids`, segments with `refs_used`, character locks (names for the tags) |
| `speech_urls.json` | yes | `{"<line id>": {"url", "dur"}}`, the measured line lengths |
| `jobs/starts.json` | yes | film start of every shot: `{"1": 0.0, ...}` or `{"starts": {...}, "total": S}` (`cut_builder.py` writes the second form) |
| `cut_final.json` | or `--video URL --duration S` | `{"final": "<link>", "duration": 550.21}` |
| `face_boxes.json` | yes (or `--missing-faces top`) | see below |
| `speakers.json` | optional | `{"neha": {"tag": "NEHA", "color": "#D6336C"}}`; keep one series-wide file and pass `--speakers` so a character has the same colour in every chapter |
| `scenes.json` | optional | `{"break_before": [27, 33], "same_scene": [9]}`: force a shot's incoming cut to be a scene change or a cut inside a scene |
| `finish/cuts_measured.json` | optional | `{"<shot>": seconds}` from `measure`; overrides `starts.json` for transition timing |

**Line times** follow the cut builder's rule: a line starts `--first-offset` (0.3 s) after its shot start, the next follows `--gap` (0.35 s) after the previous ends. If your voice track was built differently, pass the matching offsets.

**Scene classification.** `--scene-mode auto` uses the chains' `scene_ids` when they repeat, and the shot's location locks (`refs_used` entries whose lock `kind` is `location`) when `scene_ids` are unique per shot, which is how a book run numbers its shots. Use `scenes.json` for time jumps inside one place.

## face_boxes.json

```
{"size": [720, 1280],
 "shots": {
   "3":  {"faces": [{"who": "jyoti", "box": [200, 415, 400, 640]}, {"who": "neha", "box": [610, 390, 720, 665]}]},
   "12": {"samples": [{"t": 4.0,  "faces": [{"who": "neha", "box": [...]}, {"who": "lakshay", "box": [...]}]},
                      {"t": 11.0, "faces": [...]}]},
   "20": {"faces": []}
 }}
```

`box` is `[x0, y0, x1, y1]` in pixels of the final picture (rescaled if `size` differs). `who` is the speaker id in `relay.json`; the tail of a bubble points at the face whose `who` equals the speaker, and a speaker with no box in the shot (back to camera, off screen) gets a short stub tail. `t` is seconds into the shot; a bubble avoids every sample whose `t` lies within 0.8 s of its window (or the nearest sample). List every visible face (also listeners) so no bubble covers one. Loose boxes are fine: a face plus the hair around it.

How to get the boxes: `sheet JOB` writes jobs that render, for every shot, two frames (20 % and 75 % in) with a white grid every 100 px of the 720x1280 frame and a yellow line every 500 px, three shots per image. Send them (or `run-local` them), look at each sheet with `view_image`, and read the boxes off the grid.

## Jobs and limits

- Each part job reads the final picture with `-ss` (frame accurate: it starts half a frame early), renders about 55 s (`--part-seconds`), is video only (`-an`), and ends with `-frames:v` so the frame count is exact. Part boundaries are never inside a transition window. Zoom uses `zoompan`, the dip a black overlay with an alpha fade, the wipes the 8 keyed halftone clips, bubbles the `ass` filter with a sidecar `b.ass` shifted to the part.
- Send at most 5 jobs per `run_ffmpeg` call (the module is serial: wait for a call to finish before sending the next). Timeout 600 s each. For a 550 s film that is 10 parts in 2 calls, plus the join. The workspace allows about 80 runs an hour, shared: a chapter uses about 15.
- The join job concatenates the overlay parts with the concat demuxer (`-c copy`) and maps the audio from the original final (`-c copy`), so the audio is bit-identical and the length is the original's within one frame.
- Each job JSON is about 15 to 20 KB. Send exactly the file `plan` wrote.
- Check before the full run: `window JOB 15.5 21` (a bubble), `window JOB 36.5 40` (a wipe), `window JOB 253.5 256.5` (a scene change); send, then `view_image` frames inside the bubble, at the wipe peak and at the dark frame.

## Local fallback

`run-local FILE.json --workdir DIR` runs the same jobs with a local ffmpeg (libass, zoompan and geq needed; `imageio-ffmpeg` is fine, set `FFMPEG` or `--ffmpeg`), downloading inputs into `DIR/_cache`. Use it to test a plan before spending run_ffmpeg runs, or to build when the workspace is saturated; upload the result with `create_upload_url`. Input `url` values that are local paths are used as they are.

## Measured on a 550 s, 720x1280 chapter (57 shots, 91 bubbles, 24 captions)
- 10 parts of 55 s: 9 to 14 KB of JSON each (about 120 KB in all), each part 3 to 4 minutes in the sandbox (two or three side by side), 8 halftone clips about a minute, the join seconds. The final was 113 MB: `view_image` refuses a video over 100 MB, so grab check frames with a free `run_ffmpeg` job (one input opened several times with `-ss`, `xstack` into one jpg).
- Checked: duration identical (13205 frames), the audio stream's md5 equals the source's, frames away from overlays match the source at 43 to 46 dB PSNR (the parts start on the exact frame).
- **Hand-pasting these jobs corrupts them.** Two of ten pasted parts came back with altered digits in the ASS (a tag 20 px off, a garbled bubble) and were caught only by comparing against a local render with `psnr`. Prefer `run-local` and upload the parts, or paste at most 2 or 3 jobs a call and compare each result against a local render of the same job.

## Pitfalls

- A bubble placed from `face_boxes.json` is only as good as the boxes. After a retake, redo the boxes of that shot and re-run `plan`.
- The wipe peak is flat for about 0.14 s so a cut one or two frames off still hides; if cuts drift more than that from `starts.json`, run `measure`.
- A caption that needs more than four lines is reported as a warning: lower `--caption-chars`.
- A font other than DejaVu Sans Bold is not measured: the width table is DejaVu's. Keep the default font unless you re-check overflow with `window`.
- `--missing-faces top` places bubbles without a tail target and warns; use it only for a quick look.
