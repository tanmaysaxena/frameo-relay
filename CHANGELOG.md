# Changelog

## 0.5.0 (2026-11-17): whole books

- New skill `book-breakdown`: give it a text-based book PDF and it finds the chapters (`book_extract.py`), sets each chapter's runtime proportional to its size (3 to 15 minutes by default) and flags tiny, thick and possibly heated chapters, builds one shared series bible (recurring characters with per-chapter variants, places, style, voices), creates one Frameo project with a Series Bible module and a **new module per chapter**, plans every chapter in parallel with subagents, asks the content ceiling per chapter, and ends in one book plan with a credit cap per chapter (runtime share plus 25% headroom).
- New subagent roles `bible-scout` and `chapter-planner` (no Frameo tools, free); the installer writes them as Codex custom agents too.
- `book_check.py`: `init`, `validate` (own module per chapter, cast limit of 30, ceilings, caps, each chapter's `relay.json`), `allocate`, `budget` (book cost dashboard across chapter ledgers) and `sync-plan` (the free `import_media_url` and `save_character` calls that share the bible).
- `relay.json` gains an optional `series` block and `shared_from` / `variant_of` on locks; `relay_check.py` validates them. Single-script jobs are unchanged. Small additions to `conductor` (book mode), `panel-writer`, `script-injector`, `scene-prep`, `review` and `frameo-knowledge` (project, module and cast facts).
- README: whole-book pipeline, defaults and book-scale cost projections (not yet measured on a whole book).

## 0.4.0 (2026-11-17): Apache-2.0 license

- Relicensed from MIT to the Apache License 2.0: `LICENSE` is the standard Apache-2.0 text, `NOTICE` carries the copyright line, and every manifest says `Apache-2.0`. Contributions are accepted under Apache-2.0 (see `CONTRIBUTING.md`).
- Versions 0.2.0 to 0.3.1 were published under the MIT license and remain available under it for anyone who already has them; 0.4.0 and later are Apache-2.0.
- No functional changes.

## 0.3.1 (2026-11-17): credit economics, pipeline and getting-started docs

- README opens with the measured credit comparison (about 77% fewer credits on average, about 55,000 credits saved per 4:30 film, against the 65,000 to 80,000 baseline), the pipeline, how to get started, what to expect, and what to change and when. Full method, per-run table, cost breakdown, budget formula and caveats in `docs/credit-economics.md`.
- Skills now default to 720p clips finished by upscale to 1080p (the ledgers show a separate 480p draft pass was 31% of one run's spend and did not carry over), propose a 30% retake allowance (real runs spent 30% to 80% on retakes), and quote a measured budget range in the plan.

## 0.3.0 (2026-11-17): works beyond Claude

- Host-neutral skills: `${CLAUDE_PLUGIN_ROOT}` and relative `../` paths replaced by `$RELAY_HOME` (each skill opens with a Host note saying what it is on each host); tool-name and subagent fallbacks stated.
- `scripts/install.py`: installs the skills as `frameorelay-<name>` for Codex, Gemini CLI, Cursor, the shared `~/.agents/skills` folder, or any `--target`; installs a bundle to `~/.frameorelay`; writes the `scene-prep` and `review` roles as Codex custom agents; `--dry-run` and `--uninstall`.
- Codex plugin manifest (`.codex-plugin/plugin.json`) and marketplace file (`.agents/plugins/marketplace.json`), `AGENTS.md` (`CLAUDE.md` now imports it), `docs/hosts.md`.
- Personal defaults are also read from `~/.frameorelay/house-defaults.md` (the `~/.claude/frameorelay/` location still works).
- Tests for the installer. Codex, Gemini CLI and Cursor support follows the hosts' published conventions and is not yet tested end to end.

## Unreleased

Lessons from a 17-shot hard-cut film (retakes, motion pass, fix pass):
- `finish-cut/scripts/build_sound.py`: per-clip gated sound job from a small spec (dialogue clips placed at their film start, dub lines for silhouette shots, narration, beds that follow the shots, ducked, loudnorm, title padding). `finish-cut/scripts/assemble_final.py`: one-job final (picture + title + approved mix) at the picture size or 1080x1920 with upscaled clips. Tests in `tests/test_finish_cut_tools.py`.
- `relay_check.py check-result`: a hard-cut segment (no continuation) no longer needs a last frame. `panel_check.py check --plan-wps N` sets the planning speech rate (measured narration ran about 3.3 words/s).
- panel-writer: action beats in time slices and blank-device wording in the cell rules; scene-prep: action beats, opening-frame defects, bound-line behaviour, silent clips with dubbed speech; review: motion rating, logo and border checks, repeated or invented lines, view_image facts; conductor: measure-before-edit, close what you open, sandbox retry, motion gate; finish-cut: trims, gating, split bubbles, one-job final; gotchas: three new sections of verified behaviour and costs.

- New skill `panel-writer` with `skills/panel-writer/scripts/panel_check.py`: turns a plain story into a production panel script (global style bible, one table per shot with length, join, setup, cast, camera, visual prompt, dialogue bubbles, narration, SFX, BGM and AI-fill/owner-fill columns, production checklist, generated-additions table). The checker validates structure, timecodes, speech rate, speakers against cast, unsealed or franchise wording and generated lines, and `parse` emits `panels.json` for the script-injector. References: template, cell rules, a worked example. Tests in `tests/test_panel_check.py`. script-injector now routes un-tabulated scripts to it and maps a panel script straight onto scenes, chains, locks, dialogue and sound.

## 0.2.0 (2026-11-16): first public release

Release preparation:
- MIT license, public README (install from GitHub, cost and safety section, known limits), CONTRIBUTING, SECURITY, issue and pull-request templates, CI on Linux and Windows (Python 3.10 and 3.13).
- Personal taste removed from the skills. Look, voices, music, dialogue display and setting now come from an optional user defaults file (`skills/script-injector/references/user-defaults.md`, example in `examples/house-defaults.example.md`); the craft rules that apply to every story moved to `skills/script-injector/references/prompt-quality-rules.md`.
- New skill `panel-writer` (plain story to a per-shot panel script, with `panel_check.py` to validate it), and two more finish-cut builders: `build_sound.py` (per-clip sound job for hard-cut films) and `assemble_final.py` (one-job final render at the picture's own size or an upscaled one). More lessons in `frameo-gotchas.md`: measured line times, audio gating, split bubbles, queue stalls, action beats, silent clips, repeated lines, keyframe edits, bed timing.
- Job-specific names removed from the docs; lessons kept.
- `scripts/build_distributable.py` now scans every file in the repository (not only the zip) for local paths, email addresses, token-shaped strings and any private strings you list in `~/.claude/frameorelay/forbidden.txt`.
- Marketplace renamed to `frameo-relay`; manifests carry license, repository and homepage.

## Run notes for 0.2.0 (2026-11-16)

Lessons from the first full run (a 9:16 story, 19 clips, voiced bubbles, music and effects).

- New skill `finish-cut` with `skills/finish-cut/scripts/finish_cut.py` (edit list in, `picture_job.json` and `audio_job.json` out) and `skills/finish-cut/scripts/halftone_transition.py` (edge-to-edge halftone transitions in shuffled directions): contact-sheet review for morph zones, clean-window cuts and speed, comic speech bubbles with name tags and tails that follow the speaker, narration caption boxes timed to measured speech, voice lane, ducked music beds, effects and whooshes, loudnorm -14, listen check. References: edit list, transitions, bubbles and captions, ffmpeg sandbox facts.
- conductor and `frameo-gotchas.md`: placeholder prompts for quotes, 10 items per call, one speech item per call, server-rewritten `@Image1`/`@Image2` frame slots (references start at `@Image3`), 30 s clips morph at beat boundaries, slow clips are replayed not re-quoted (double charge), content-filter refunds, half-price image charges, ledger reconciliation, workspace re-pin, check-ready prerequisites, voice-only narrator, no lipsync for bubble dialogue.
- script-injector: asks for style split with franchise names translated to visible terms, dialogue delivery and voices, on-screen text, target and maximum length, music and effects, resolution tiers, first and last frame per shot, the explicit-content boundary, and checks voices exist in the pinned workspace. Plan template gains voices, on-screen text, sound plan, length and tiers, last-frame column.
- `relay_check.py`: a bare `voice` lock or a `voice_only` character may speak dialogue and needs no `media_id`. Tests added.
