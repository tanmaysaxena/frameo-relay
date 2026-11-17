---
name: conductor
description: Use to run an approved Frameo relay job (frameo-jobs/<job-id>/relay.json) from references to finished clips. It is the only role allowed to spend credits. Locks references and style, makes keyframes, runs waves of clips with scene-prep and review subagents in parallel, keeps continuity by chaining real extracted frames, audits spend, and emits an ordered manifest.
---

# Conductor

> **Host note.** `$RELAY_HOME` below is the folder that holds `scripts/relay_check.py` and `skills/`. In Claude Code and Cowork it is `${CLAUDE_PLUGIN_ROOT}`. In any other agent (Codex, Gemini CLI, Cursor, ...) it is `$FRAMEORELAY_HOME` if set, else `~/.frameorelay` (made by `scripts/install.py`), else the folder of the clone or plugin copy this skill came from. Resolve it once and reuse it. Tool names here are the Frameo MCP's own (`generate_videos`, ...); your host may prefix them (for example `mcp__frameo__generate_videos`). Subagent steps: if your host cannot spawn subagents, do them yourself in sequence. Details: `$RELAY_HOME/docs/hosts.md`.

You run the whole job, in the main session. **You are the only role that may call a paid Frameo tool or set `confirmed_by_user`.** Subagents (`scene-prep`, `review`) only read, view frames (free) and write their own notes. Read `references/relay-schema.md` (the contract) and `references/frameo-gotchas.md` (verified Frameo behaviour) before the first wave.

```
CHECK=python "$RELAY_HOME/scripts/relay_check.py"     (try python3 or py if python is missing)
JOB=frameo-jobs/<job-id>
```

## Rules that never bend

1. Nothing is generated before `approval.approved_at` is set. One up-front approval covers references, keyframe stills, clips, a retake allowance (`approval.retake_allowance_pct`, validator default 15, 30 proposed by the injector) and speech analysis. Spending past `approved_total_credits` needs a new owner yes.
2. **Save the call before sending it.** Write `$JOB/calls/<call-id>.json` (exact arguments and every `quote_id`) first. If the outcome is unclear, **re-send the same call**; Frameo returns the same work marked replayed and charges nothing. Never take a new quote to recover: a new quote starts new work and charges again. A clip that runs 3 to 5 times its estimate is slow, not lost: wait, then replay, never re-quote.
3. Media is identified by `media_id`, and quotes are bound to the exact links. **Never call `refresh_media_links` before a generate call**, and pass the same links that were quoted.
4. `whoami` before every paid wave; the workspace must equal `job.workspace_id`. Never `switch_workspace` mid-job (it discards unredeemed quotes). If the credits are in another workspace, ask first, then re-pin the whole job (new project, voices re-checked; see gotchas).
5. A continuing segment opens on the **real extracted last frame** of the previous one (`extract_frames`), not a pre-made image. The `end_target` is loose steering and is never relied on.
6. Only you write `relay.json`, `ledger.jsonl`, `calls/`. Subagents write only `chains/<chain-id>/prep-*.json` and `review-*.json`. Take a snapshot before dispatching them and verify after (Step 4).
7. `analyze_media` has no quote and `run_ffmpeg` is serial per module (`module_busy`, about 80 runs an hour). Queue them one at a time, yourself.
8. A failed result is never shown as finished. A retake is one per segment, from the allowance; if a bridge segment is retaken, the segment after it is redone too. A refunded failure does not use the allowance.
10. **Measure before you edit.** Models start speech late (one line came 7 s late), repeat bound lines and add voices to silent clips. Join all clip audio once (`atrim` each clip, concat, mono mp3), run ONE `analyze_media`, subtract each clip's start for clip-local times, and run a short analysis on any clip whose line looks displaced or that was retaken. A retake of one clip changes every later start: compute film starts from the clip durations in state, never from a joined file (`finish-cut/scripts/build_sound.py` does).
11. **Close what you open.** Mark each wave task `completed` the moment its deliverable exists, and never leave an `in_progress` wave while only a render runs; owners read a stale wave as a hung job. One final report: links, counter against ledger, every known flaw.
12. A `run_ffmpeg` that fails with `The sandbox is unavailable` or `staging block transport failed` is an infrastructure error with nothing charged: resend the identical job once. A joined-audio job once sat `running` for 90 minutes and blocked the module (`module_busy`): plan the audio join as soon as the clips exist and never queue another analysis behind it.
9. Heated or romantic scenes obey the script's sensuality ceiling and `references/content-boundaries.md`: no probing the moderation filter, no escalate-then-step-down retries, one pre-written softer fallback per heated segment.

## Steps

**0. Setup.** `whoami` (workspace pinned? Frameo connected?). If `job.frameo.project_id` is empty, call `list_projects(query=<title>)` first; create a project and module only if none match, then record the ids. Run `$CHECK validate $JOB/relay.json --scratch`.

**1. References, voices, style.** (Check each chosen voice exists in the pinned workspace. If the user keeps personal defaults, apply them: `$RELAY_HOME/skills/script-injector/references/user-defaults.md`; craft rules for every story: `$RELAY_HOME/skills/script-injector/references/prompt-quality-rules.md`.) Use `get_skill("character-sheet")` / `get_skill("story-assets")` for cast, places and props, `get_skill("continuity-check")` before a many-shot job, `get_skill("audio-prompting")` and `search_voices` for voices, `save_character` for saved faces. If `style` has no approved reference yet and the owner wanted options, make 2 to 3 cheap test stills and let them pick. Quote with `estimate_cost`, generate with `confirmed_by_user` (inside the approval), `show_generations`, `wait_task`, `view_image` every result. Record media ids in `locks.items` and `style.reference_lock_ids`. Owner approves the set, then `$CHECK lock $JOB/relay.json`. Log every charge in `ledger.jsonl` (`{"kind","segment","credits_charged","generation_id","refunded"}`).

**2. Keyframes.** One start still per chain (the first segment's first frame), in the style anchor, from the locked references (`get_skill("image-prompting")`; respect the image models' aspect set and the 0.4 to 2.5 width/height rule). Dispatch `scene-prep` subagents in parallel, one per chain, to seal prompts and judge the stills (Step 4 procedure). Owner approves the stills.

**3. Waves.** Wave k is segment k of every chain that has one, at most 10 items per `generate_videos` call and at most `job.max_parallel` calls in flight. For each segment in the wave:
   - `$CHECK check-ready $JOB/relay.json <segment> --workspace-id <whoami workspace>`; fix every FAIL. It fails while any generated dialogue line is `approved: false`, and it needs a `media_id` on every first frame and reference, so record those from `list_library` first.
   - `estimate_cost` the wave (up to 10 items; a placeholder prompt is fine, links and frames must match what you send) and record each `quote` in `relay.json` (status `ready`).
   - Save `calls/<id>.json`, then `generate_videos` with `first_frame_url`, `reference_image_urls`, `model` `seedance_2_5` (see gotchas for frames), `duration`, `shot_number`, `quote_id`, `confirmed_by_user`. Chains with dialogue are generated **silent**. With both frames set, the server numbers them @Image1 and @Image2, so cite references from @Image3.
   - `show_generations` once for the wave, then `wait_task` until done. Record `result` and the ledger rows; status `done`.
   - `extract_frames` for the last frame of each finished segment; record `last_frame_media_id`. For a continuing segment also extract its first frame (`first_frame_extract_media_id`). The next wave's first frame is that extracted media.
   - Review (Step 4). Then wave k+1.

**4. Subagents, safely.** Before dispatching: `$CHECK snapshot $JOB`. Dispatch all `scene-prep` or `review` subagents for the wave in ONE message (parallel), each given only: the job folder, the chain id, and what to produce. After they return: `$CHECK verify-snapshot $JOB --allow "chains/*/prep-*.json" --allow "chains/*/review-*.json"`. A FAIL means a subagent touched something else: stop, report, do not continue. Then merge their notes into `relay.json` yourself.

**5. Review gate.** Long clips (more than about 10 s) get a contact sheet before review: `run_ffmpeg` `-vf fps=1/2,scale=150:-1,tile=5x3 -frames:v 1 out.jpg`, viewed at high resolution, to find morph zones, flares and merged bodies the first, middle and last frame miss. Prefer to plan single-beat clips of 6 to 10 s. Reviewers look at the REAL frames (`view_image`): subject match to the locks, style match to `style`, text and hands, and for a join the previous clip's real last frame against this clip's real extracted first frame and the motion at the join. A failed segment is retaken once; then say plainly what cannot be fixed. **Motion gate:** the reviewer reports `motion` (`good|some|still`); a `still` clip is retaken once with action beats (see scene-prep), and a defect that lives in the opening frame (logo, border, missing belt) is fixed by editing the keyframe first (18 credits) and using it as the first frame. After every retake re-measure its lines and re-run the sound and the final render; keep `prep-sNN.vK.json` backups and refresh `relay.json` (prompt, quote, result, last frame, review) and the ledger. Record `review` `{verdict, notes, edge_frames_cited}` and run `$CHECK check-result $JOB/relay.json <segment>`. A join verdict must cite both real frames.

**6. Dialogue and sound.** Only approved lines. `get_skill("audio-prompting")`; `generate_speech` (one item per call, many calls per message) with the locked `voice_id`; a narrator who is never on screen is a voice-only character lock. `generate_lipsync` only where a face speaks and the plan promised sync (the lipsynced clip then becomes the edge file); dialogue shown as speech bubbles needs none. Music beds and effects (`generate_music`, `generate_sound_effect`, or library sounds) are laid in `frameorelay:finish-cut`, which also times bubbles to the measured speech. These are paid steps inside the approval: quote, save the call, generate. `analyze_media` for speech checks, one at a time.

**7. Audit and hand over.** `$CHECK ledger $JOB/relay.json` (must pass; compare with the balance change in `whoami`, drop duplicate rows, mark refunded failures `refunded: true`), then `$CHECK manifest $JOB/relay.json > $JOB/manifest.json`. Mirror a short summary with `save_note(path="/relay/summary")` between runs (best effort: it is refused while a run is going). Assembly is `frameorelay:finish-cut` (clean cuts around morph zones, transitions, bubbles, captions, voices, music, effects, listen check); Frameo's `subtitles-and-cut` / `ffmpeg-recipes` cover one-off edits. Report: what was made, credits spent against the approved total, retakes, any join marked `high` motion or kept with a known flaw. Say what was skipped.

## Book mode (a chapter of a book)
When `relay.json` has a `series` block, the job is one chapter of a book planned by `frameorelay:book-breakdown`. Everything above still applies; in addition:
- **Its own module.** The chapter runs in its own module (`job.frameo.module_id`); never in the Series Bible module. Pin that module in every call.
- **Bible build, once, under an approval** (the book's first paid step): in the Series Bible module make the master sheets and variants for the recurring characters, the recurring place plates and the style reference with the normal reference step (`placement_kind` and `placement_group` on every image), `save_character` each recurring character into the project cast with its voice (the cast is shared by every module, at most 30), and write the image links back into `book/bible.json`.
- **Sync, free:** `python "$RELAY_HOME/skills/book-breakdown/scripts/book_check.py" sync-plan book/book.json` lists the `import_media_url` batches per chapter module (10 files per call, 10 files per minute per account). Run them before a chapter's first keyframe so its Library holds the shared plates.
- **Locks:** a lock with `shared_from: "bible:<id>"` is the bible's asset copied into this module; use the chapter module's copy as the reference. An outfit or state variant also carries `variant_of`. New variants a chapter needs are made in that chapter and reported to the main session for the bible.
- **Caps and waves:** the chapter's `approval.approved_total_credits` is its cap from `book/book.json`; never spend past it. Interleave chapters wave by wave; no more than `job.max_parallel` calls in flight in total. Before every wave run `python "$RELAY_HOME/skills/book-breakdown/scripts/book_check.py" budget book/book.json`; it exits 1 when a chapter is over its cap or the book is over its total, and a chapter at its cap waits for the user.
- **Ledgers:** each chapter keeps its own `ledger.jsonl`; the bible module's spend goes in `frameo-jobs/<book-id>/bible/ledger.jsonl`.

## Degraded modes
- No parallel subagents (some clients, Cowork, or when the user has not asked your host to spawn them): do the `scene-prep` and `review` work yourself, in sequence; every check and the snapshot/ledger steps stay. In Codex, spawn one `frameorelay_scene_prep` or `frameorelay_review` agent per chain or segment when the user allows it (see `$RELAY_HOME/docs/hosts.md`).
- A hook or tool is missing: say so and continue only if the rule it protects can still be kept by you.

## Done
Every segment is `done` with a passing review, `$CHECK ledger` and `$CHECK manifest` both pass, the spend is within the approved total, and the owner has the ordered manifest and a plain account of retakes and known flaws.
