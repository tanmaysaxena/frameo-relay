# frameorelay

A Claude Code / Claude Cowork plugin that turns a script into a finished video through the [Frameo](https://frameo.ai/mcp) MCP, with a validated contract that keeps many scenes **continuous, on-style and inside an approved budget**.

> Unofficial. Not made by or affiliated with Frameo or Anthropic. It drives the Frameo MCP, which **spends real credits** on your Frameo account: read "Cost and safety" before running a job.

Status: v0.2.0, early. It was built on real runs (a 9:16 story with 19 clips, voiced speech bubbles, music and effects) and the lessons from them are in the skills. Expect rough edges; issues and PRs are welcome.

## What it does

| Skill | Role |
|---|---|
| `frameorelay:panel-writer` | Optional first step for a plain story or outline. Turns it into a production **panel script**: a global style bible, then one table per shot (length, join, setup, cast, camera, visual, dialogue, narration, sound) and a checklist, so every shot is a self-contained work order. Keeps the author's words exact, marks every invented line, checks the result with `skills/panel-writer/scripts/panel_check.py`. Never spends credits. |
| `frameorelay:script-injector` | You share a script. It splits it into scenes and chains, builds the cast, style direction and sealed prompts, writes clearly marked dialogue where the script has none, validates the plan, shows it, and on your yes starts the conductor. Never spends credits. |
| `frameorelay:panel-writer` | Your script is just a story, not a per-shot table. It cuts the story into shots and writes the production panel script: a style bible, then one table per shot (length, join, setup, cast, camera, visual prompt, dialogue bubbles, narration, SFX, BGM, AI-fill and owner-fill columns) and a sign-off checklist, so parallel agents get self-contained work orders. Keeps your words exact, marks invented lines, validates the result with `skills/panel-writer/scripts/panel_check.py`. Never spends credits. |
| `frameorelay:conductor` | Runs the approved job in the main session. The **only** role that may spend. Locks references and style, makes keyframes, runs waves of clips, chains real extracted frames, audits spend, writes the manifest. |
| `frameorelay:scene-prep` (subagent) | One per chain, in parallel: seals prompts and judges the keyframe. Free tools only. |
| `frameorelay:review` (subagent) | One per segment, in parallel: judges the real frames and the join. Free tools only. |
| `frameorelay:finish-cut` | After the clips and speech exist: contact-sheet review for morph zones, clean-window cuts at a chosen pace, edge-to-edge halftone transitions in shuffled directions, comic speech bubbles with name tags, narration caption boxes, voices, ducked music, sound effects, a loudness-normalised mix and a listen check. Two free `run_ffmpeg` jobs built by `skills/finish-cut/scripts/finish_cut.py`; `build_sound.py` builds a per-clip sound job for hard-cut films and `assemble_final.py` makes the one-job final render (title card, approved mix, optional upscaled size). |
| `frameorelay:frameo-knowledge` | Keeps a saved map of Frameo's own skills, models and prices current with free calls, so plans are faster and cheaper. |

`scripts/relay_check.py` is the validator the skills call (`validate`, `lock`, `verify-locks`, `check-chains`, `check-style`, `check-dialogue`, `check-ready`, `check-result`, `ledger`, `snapshot`, `verify-snapshot`, `manifest`). Python 3, standard library only; no network access.

## Requirements

- Claude Code or Claude Cowork with plugin support.
- The Frameo MCP connected and signed in: `claude mcp add --transport http frameo https://mcp.frameo.ai/mcp`
- Python 3.10+ (for the validator and the edit builder; tested on 3.10 and 3.13).
- A Frameo workspace with credits.

## Install

Claude Code (user scope, works from any folder):

```
claude plugin marketplace add tanmaysaxena/frameo-relay
claude plugin install frameorelay@frameo-relay --scope user
```

From a local clone: `claude plugin marketplace add "<path to the clone>"`, then the same `install` line.

Claude Cowork: `python scripts/build_distributable.py` writes `dist/frameorelay-<version>.zip`; upload it as a plugin. See "Known limits" for what is not verified there.

## Use

If your input is a plain story or outline rather than a shot table, start with "use the panel writer on this story"; it produces the panel script the script injector then reads.

Say: "use the script injector on this script", paste or point at the script, and answer its few questions (shape and maximum length, 480p draft then 720p, style direction, dialogue mode and delivery (voiced, bubbles, both), narrator voice, music and effects, first and last frame per shot, language). It shows the plan, including a separate **Generated dialogue** section for every line it invented. Say yes and the conductor takes over. Job files live in `./frameo-jobs/<job-id>/` under the folder you are working in.

Want the same look, voices or music every time? Keep a defaults file: see `skills/script-injector/references/user-defaults.md` and `examples/house-defaults.example.md`.

## Cost and safety

- **Nothing is generated before you approve a plan** and a quoted total. One up-front approval covers references, keyframes, clips, a 15% retake allowance and speech analysis. Spending past it needs a new yes from you.
- Only the conductor may call a paid Frameo tool. Subagents use free tools only, and the conductor checks (by snapshot) that they touched nothing else.
- Every paid call is saved before it is sent and recovered by re-sending the same call, never by taking a new quote (a new quote starts new work and charges again).
- The validator and the audit are arithmetic and structure checks, not a hard spending stop. If you want a hard limit, top up the wallet only to the approved total.
- Content boundaries (`skills/conductor/references/content-boundaries.md`): scripts that ask for more than the chosen sensuality ceiling are flagged, nothing explicit is generated, and the relay never probes or evades Frameo's moderation filter.

## Why chains, not one parallel image per scene

On Seedance, first and last frames only guide a clip; the end follows the image loosely. Two clips that share one picture do not join cleanly. So a continuous run opens each next clip on the **real extracted last frame** of the one before it. That makes continuity serial inside a chain and parallel across chains and hard-cut scenes. A continuous run of 30 seconds or less is one clip, with no join at all. Long (30 s) multi-beat clips morph at their beat boundaries, so prefer single-beat clips of 6 to 10 s, or cut windows around the morph zones in `finish-cut`. Frameo itself renders up to 10 clips per call in parallel; the Claude subagents parallelise the thinking and checking (prompt sealing, frame review).

## What the validator does not prove

It proves structure, ids, frozen locks and style, chain order, prompt sealing, budget arithmetic, and that a join review cited both real frames. It cannot prove a `media_id` exists in Frameo, that a clip matches its frame, or that a join looks right: reviewers look at the real frames.

## Known limits (unverified, test before relying)

- Whether background subagents can use the Frameo MCP tools without permission prompts in your client.
- Claude Cowork: whether it runs the Python script, fans out subagents, honours `${CLAUDE_PLUGIN_ROOT}` and reaches the Frameo MCP. If it has no parallel subagents the conductor does the prep and review itself, in sequence; every check stays.
- Frameo's real concurrency limit is undocumented: set `job.max_parallel` from what you measure.
- The MCP tool names in `agents/*.md` assume the Frameo server is registered as `frameo`.
- Frameo's models, prices and skills change. `skills/conductor/references/frameo-gotchas.md` and the `frameo-knowledge` skill record what was true when they were read; re-verify against the live MCP.

## Development

```
python -m pytest tests -q
python scripts/generate_skill_index.py --check   # SKILLS.md is generated; drop --check to rewrite it
python scripts/build_distributable.py            # builds the zip and scans it for private strings
```

See [CONTRIBUTING.md](CONTRIBUTING.md). Report security issues as described in [SECURITY.md](SECURITY.md).

## License

[MIT](LICENSE)
