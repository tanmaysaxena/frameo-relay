# Contributing

Thanks for helping. frameorelay is a set of agent skills (instructions for Claude Code, Codex and other agents) plus small standard-library Python scripts, so most contributions are careful edits to Markdown and a test.

## Ground rules

- **Keep the design rules** (see `AGENTS.md`): only the conductor spends; draft, then approval, then write; a continuing segment opens on the real extracted last frame; media identity is `media_id`; never refresh links before a generate call; save a paid call before sending it and recover by re-sending the same call.
- **Python scripts are standard library only** and make no network calls.
- **Stay host-neutral**: skills use `$RELAY_HOME` and the Frameo MCP's own tool names, and anything that needs subagents has a sequential fallback. If you change host support, update the status table in `docs/hosts.md` and say whether you tested it in that host.
- **No personal data in the repo**: no names, emails, workspace or project ids, voice ids that belong to an account, local paths, job output, media or credentials. Personal taste (style, voices, music) belongs in a user's own defaults file, not in a skill (see `skills/script-injector/references/user-defaults.md`).
- **Facts about Frameo carry a date.** If you add a limit, price or behaviour to `frameo-gotchas.md` or `skills-map.md`, say when you read it and how you verified it.
- **No explicit content and no filter evasion.** See `skills/conductor/references/content-boundaries.md`.

## Before you open a pull request

```
python -m pytest tests -q
python scripts/generate_skill_index.py        # rewrites SKILLS.md; commit the result
python scripts/build_distributable.py         # must print OK; it scans for private strings
```

Add or update a test in `tests/test_relay_check.py` when you change `scripts/relay_check.py` or `skills/finish-cut/scripts/`. Describe what you ran against a real Frameo job, if anything, and what it cost.

## License of contributions

By submitting a pull request you agree that the maintainer may include your contribution in the project under its current terms ([LICENSE](LICENSE) and [COMMERCIAL-LICENSE.md](COMMERCIAL-LICENSE.md)) and license it to organisations under commercial licences.

## Reporting a problem

Open an issue with the skill involved, what you expected, what happened, and the relevant part of `relay.json` with ids removed. For security issues use [SECURITY.md](SECURITY.md) instead.
