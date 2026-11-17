# Using frameorelay with different agents

frameorelay is written as [Agent Skills](https://agentskills.io/) (folders with a `SKILL.md`), Python scripts that use only the standard library, and a Frameo MCP connection. None of that is tied to one product. This page says how to run it in each host and what is and is not verified.

## Status at a glance

| Host | How you install it | Tested by the author |
|---|---|---|
| Claude Code | plugin marketplace | yes: every real run so far |
| Claude Cowork | upload the zip from `scripts/build_distributable.py` | no (see README "Known limits") |
| OpenAI Codex (CLI, IDE, app) | plugin marketplace, or `scripts/install.py --host codex` | **no**: written from OpenAI's docs, not yet run in Codex |
| Gemini CLI | `scripts/install.py --host gemini` | no |
| Cursor | `scripts/install.py --host cursor` (or `--host agents`) | no |
| Any other Agent Skills host | `scripts/install.py --target <its skills folder>` | no |

"Not tested" means the install layout and file formats follow the host's published documentation and the installer is covered by this repository's own tests, but nobody has yet driven a full Frameo job through that host. If you try one, please open an issue with what worked and what did not.

## What every host needs

1. **The Frameo MCP server**, connected and signed in, registered under the name `frameo`.
2. **Python 3.10+** on the machine, for the validator and the edit builders (`python` or `python3`).
3. **Skills support**, so the agent can read the `SKILL.md` files, and ideally **subagent support** (see below).

## The one path variable: `$RELAY_HOME`

The skills refer to scripts and to each other through `$RELAY_HOME`, the folder that contains `scripts/relay_check.py` and `skills/`.

| Where | `$RELAY_HOME` is |
|---|---|
| Claude Code, Cowork | `${CLAUDE_PLUGIN_ROOT}` (set by the host) |
| Codex plugin install | the plugin folder (a cached copy under `~/.codex/plugins/`; search for `relay_check.py` if unsure) |
| `scripts/install.py` | `~/.frameorelay` (or `$FRAMEORELAY_HOME`, or whatever you pass as `--home`) |
| A plain clone | the clone's root |

Every skill opens with a short "Host note" that says this, so an agent that has not seen this page still resolves it.

## Codex

Facts below are from OpenAI's Codex documentation ([skills](https://developers.openai.com/codex/skills), [plugins](https://developers.openai.com/codex/plugins/build), [MCP](https://developers.openai.com/codex/mcp), [subagents](https://developers.openai.com/codex/agent-configuration/subagents), [customization](https://developers.openai.com/codex/concepts/customization)).

**Connect the Frameo MCP**

```
codex mcp add frameo --url https://mcp.frameo.ai/mcp
codex mcp login frameo
```

or in `~/.codex/config.toml`:

```toml
[mcp_servers.frameo]
url = "https://mcp.frameo.ai/mcp"
```

**Install, route 1: plugin marketplace.** This repository carries a Codex plugin manifest (`.codex-plugin/plugin.json`) and marketplace file (`.agents/plugins/marketplace.json`):

```
codex plugin marketplace add tanmaysaxena/frameo-relay
```

then install `frameorelay` from the plugins directory in the Codex app. The CLI manages marketplace sources; per OpenAI's docs the install step itself is done in the app.

**Install, route 2: skills + agents from the installer.**

```
git clone https://github.com/tanmaysaxena/frameo-relay
cd frameo-relay
python scripts/install.py --host codex                   # user scope: ~/.agents/skills and ~/.codex/agents
python scripts/install.py --host codex --scope project   # this repository only: .agents/skills and .codex/agents
```

Skills appear as `frameorelay-script-injector`, `frameorelay-conductor`, and so on (invoke with `$frameorelay-script-injector` or `/skills`, or just describe the task and let Codex match the description). Restart Codex if it does not see them.

**Subagents.** Codex spawns subagents when you ask or when a skill says to. The installer writes the four roles as custom agents: `frameorelay_scene_prep` and `frameorelay_review` (conductor), and `frameorelay_bible_scout` and `frameorelay_chapter_planner` (book-breakdown). Tell Codex, for example: "run the conductor; for each chain spawn a `frameorelay_scene_prep` agent in parallel", or "for each chapter spawn a `frameorelay_chapter_planner` agent". Codex subagents inherit the parent's MCP servers and permissions and a custom agent file cannot restrict them, so the "free tools only" rule for the Frameo-facing roles is an instruction the agent must follow, not a sandbox (the two book roles have no Frameo tool at all, only file access and the validators). The conductor's snapshot check (`relay_check.py snapshot` / `verify-snapshot`) still catches a subagent that touched files it should not. Without subagents the conductor does the prep and review itself in sequence (see its "Degraded modes").

**Approvals.** Codex can ask before each MCP tool call (`default_tools_approval_mode` per server). For a paid Frameo job leave generating tools on "prompt" so every spend needs your yes, on top of the plan approval.

## Gemini CLI, Cursor and other Agent Skills hosts

Gemini CLI reads skills from `.gemini/skills/` or `.agents/skills/`; Cursor reads `.cursor/skills/` and `.agents/skills/` (and the Claude and Codex skill folders) ([Gemini CLI skills](https://geminicli.com/docs/cli/skills/), [Cursor skills](https://cursor.com/docs/skills)). `.agents/skills` is the folder several tools share.

```
python scripts/install.py --host gemini      # ~/.gemini/skills
python scripts/install.py --host cursor      # ~/.cursor/skills
python scripts/install.py --host agents      # ~/.agents/skills, the shared folder
python scripts/install.py --target /path/to/your/tools/skills   # anything else
```

Add the Frameo MCP server through your host's MCP settings, as a streamable-HTTP server named `frameo` at `https://mcp.frameo.ai/mcp`. Subagents are optional: where the host has none, the skills fall back to doing the prep and review steps in sequence.

If you want a different skills folder than the defaults (hosts change), use `--target`. The installer only ever writes the `frameorelay-*` folders, the bundle folder and the Codex agent files, and `--uninstall` removes exactly those.

## Tool names

The skills use the Frameo MCP's own tool names (`generate_videos`, `estimate_cost`, ...). Some hosts show them with a prefix (Claude Code: `mcp__frameo__generate_videos`). Use whichever your host exposes; the meaning is identical. The `tools:` line in `agents/*.md` uses the Claude Code spelling and is ignored elsewhere.

## Personal defaults

A defaults file (look, voices, music, setting) is read from `./frameo-jobs/house-defaults.md`, then `~/.frameorelay/house-defaults.md`, then (older location) `~/.claude/frameorelay/house-defaults.md`. See `skills/script-injector/references/user-defaults.md`.

## What stays the same everywhere

The rules that protect your money do not depend on the host: only the conductor spends, nothing is generated before an approved plan and total, every paid call is saved before it is sent, and the validator and ledger audit run the same Python.
