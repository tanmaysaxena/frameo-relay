# Edit list (EDL) fields for finish_cut.py

```
canvas      {w, h, fps}                     default 480x854 at 24 (9:16 480p). Use the clips' real size.
clips       {key: link}                     finished clip links a Frameo tool returned
chains[]    one scene each, in play order
  id, clip, windows [[a,b],...], target_s   windows in source seconds; speed = sum(b-a)/target_s (>= 1)
  narration "key"                           plays from chain start + options.narration_offset_s
  dialogue  [{key, t, head_x}]              t = seconds from chain start; head_x = speaker's head, px from left
  sfx       [{name, t, gain, max_s}]        t from chain start, trimmed to max_s
speakers    {id: {tag, color}}              tag printed on the bubble; color is ASS BGR like &H9A3CE0&
narration   {key: {url, seconds, text}}     seconds = measured duration_seconds; text is chunked into caption boxes
dialogue    {key: {url, seconds, speaker, text}}
sfx         {name: {url, seconds}}          "whoosh" (1 s) is laid on every cut when a transition is on
bgm         [{url, seconds, from_chain, gain, fade_in}]   bed k starts 1.5 s before its chain, runs to the next bed
transition  {mode: none|flash|halftone, ...}
            flash:    image_url, alpha, width_s
            halftone: clips {LR,RL,TB,BT,TLBR,BRTL,TRBL,BLTR: link}, seed, dur_s, key_similarity, whoosh_gain
options     {narration_offset_s 0.6, duck true, loudness_lufs -14, max_total_s}
```

Outputs: `picture_job.json` (no audio), `audio_job.json` (first input `film.mp4` = `--picture-url`), `timeline.json` (chain starts and speeds, cut times, dialogue times, total).

The bubble centre is clamped on screen and its tail tip sits on `head_x`. Caption chunks split sentences longer than 85 characters at a comma or conjunction near the middle and share the speech duration in proportion to their length.

## Dialogue entry (bubble placement is mandatory)
`dialogue[]` items: `{key, t, faces: [[x0,y0,x1,y1], ...], speaker_face: 0, head_x?}`. `faces` lists every face visible while the bubble is up, in canvas pixels, read off a viewed frame. The builder sizes the bubble to its text, searches for a spot that overlaps no face (closest to the speaker, above preferred) and aims the tail at the top of `faces[speaker_face]`. Without `faces` the build stops with an error; this is the house rule that a bubble never covers a face.
## Trims and splits
- A clip trimmed in the edit: `windows [[0, N]]` with `target_s` N, and the same N as that clip's seconds in the sound spec.
- A long line that cannot find a free spot: two dialogue entries with the same speaker and consecutive text, each with its own `t` and `seconds` (placement runs per bubble).
