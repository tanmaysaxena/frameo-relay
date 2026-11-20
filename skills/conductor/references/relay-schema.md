# relay.json: the contract

One file per job at `frameo-jobs/<job-id>/relay.json`. **Only the conductor writes it.** `scripts/relay_check.py` enforces everything marked (check). A full worked example is `examples/relay.sample.json`.

```
version            1
job
  id               string
  workspace_id     string, pinned for the whole job                       (check-ready)
  frameo           {project_id, module_id}
  aspect_ratio     "9:16" | "16:9" | ...
  resolution       "480p" | "720p" | ...
  model            default "seedance_2_5"
  max_parallel     int, calls in flight; measure, do not assume
  max_parallel_agents  int, scene agents in flight (chains fan out, shots inside a chain stay sequential); default 4
  limits.models    {<model>: {seconds:[min,max], aspect_ratios:[...],
                              max_reference_images:int}}  copied from list_models (check-chains, check-ready)
style              (frozen by `lock`)
  look, palette, lighting, lens_and_camera_language, pacing, avoid[]
  anchor           <= 60 words, pasted verbatim into every keyframe and clip prompt   (check-style)
  reference_lock_ids[]  lock ids that must be in every segment's refs_used            (check-style)
  none             true = no style direction
dialogue
  mode             as_written | fill_gaps | full_creative
  max_words_per_second  default 2.5                                          (check-dialogue)
  lines[]          {id, segment, speaker (a character lock id), text, language,
                    source: script|generated, approved: bool}
approval           (nothing is generated without it)
  approved_total_credits   references + keyframes + clips + retake allowance + analysis
  retake_allowance_pct     default 15 (validator); real runs approved 30 and spent 30% to 80% on retakes: see docs/credit-economics.md
  approved_at              ISO timestamp
locks
  locked_at, fingerprint   written by `lock`, checked by `verify-locks`
  items[]          {id, kind: character|location|prop|style|voice,
                    media_id (not for voice), voice_id (voice, or on a character)}
                    voice_only: true on a character = narrator never on screen: voice_id, no media_id.
                    A bare `voice` lock may also be a dialogue speaker.
chains[]           a chain = scenes that flow into each other; a hard cut = a chain of one
  id, scene_ids[]
  segments[]       each at most 30 s, whole seconds                               (check-chains)
    id, scene_ids[]  (together cover the chain's scene_ids, in order)
    duration_s
    prompt           sealed: no "previous", "as before", shot numbers            (check-ready)
    keyframe_prompt  optional, must also contain the style anchor
    refs_used[]      lock ids
    first_frame      {source: "keyframe"|"extract", media_id, from_segment}
                     segment 0 of a chain: keyframe. Segment k>0: extract of segment k-1's real last frame
    end_target       optional loose steering image, never counted as continuity
    join_motion      low | mid | high
    status           draft | ready | generating | done | failed
    quote            {credits, quote_id}  from estimate_cost
    result           {generation_id, video_media_id, last_frame_media_id,
                      first_frame_extract_media_id (segment k>0), credits_charged}
    review           {verdict: pass|fail, notes, edge_frames_cited[]}
                     a join review (segment k>0) must cite BOTH the previous clip's real
                     last frame and this clip's real extracted first frame        (check-result)
```

Companion files in the job folder: `plan.md` (the approved plan), `calls/<id>.json` (exact paid call and quote ids, saved BEFORE sending), `ledger.jsonl` (one row per charge: `{kind: reference|keyframe|clip|retake|speech|lipsync|analysis, segment, credits_charged, generation_id, refunded}`), `chains/<id>/prep-*.json` and `review-*.json` (subagent notes), `manifest.json`.

## What the validator does not prove
- That a `media_id` exists in Frameo, or that a generated clip matches its frame. The conductor checks with Frameo's tools; reviewers look at the real frames.
- That a join looks right. It proves both real edge frames were cited, not that the verdict is correct.
- Spend is held by who may spend (conductor only), per-wave quotes checked by `check-ready`, and a post-wave `ledger` audit. It is not a hard stop inside a running call. For one, put only the approved total in the wallet.

## Optional `series` block (a chapter of a book)
Added by the book-breakdown skill. Absent for a normal single job; nothing else changes.

```
series                  {book_id, chapter_id, chapter_no, bible: path to book/bible.json, bible_module_id?}
locks.items[]           optional shared_from "bible:<id>" (an asset made once in the Series Bible module and copied into
                        this chapter's module) and variant_of "bible:<id>" (an outfit or state variant of a base look)
```
Rules the validator enforces: `book_id`, `chapter_id`, `bible` and an integer `chapter_no` >= 1 are present; the chapter's
`job.frameo.module_id` is its own and never the bible module; `shared_from` and `variant_of` look like `bible:<id>`.
