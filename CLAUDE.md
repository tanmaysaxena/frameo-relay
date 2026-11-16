# CLAUDE.md: frameorelay

A Claude Code / Cowork plugin that runs Frameo video jobs through a validated contract (`relay.json`). Standalone; nothing in it depends on any other repo.

- Layout: `skills/<name>/SKILL.md` (panel-writer, script-injector, conductor, scene-prep, review, finish-cut, frameo-knowledge), `agents/` (the two subagent roles), `scripts/relay_check.py` (the one validator, stdlib only), `skills/finish-cut/scripts/` (edit-list, sound and final-render builders and halftone transitions, stdlib only), `skills/panel-writer/scripts/panel_check.py` (panel-script checker and JSON parser, stdlib only), `tests/`, `examples/` (a sample `relay.json` and an example defaults file).
- Design rules, in order: only the conductor spends; draft then approval then write; a continuing segment opens on the real extracted last frame; media identity is `media_id`; never refresh links before a generate call; save a paid call before sending it and recover by re-sending the same call.
- No hardcoded paths. Skills reference the validator as `${CLAUDE_PLUGIN_ROOT}/scripts/relay_check.py`. Never commit `frameo-jobs/`, media, credentials, account or project ids, or personal taste (style, voices, music): that belongs in the user's own defaults file (`skills/script-injector/references/user-defaults.md`).
- Commit with your own configured git identity.
- Before committing: `python -m pytest tests -q`, `python scripts/generate_skill_index.py --check`, `python scripts/build_distributable.py` (its private-string scan must pass).
- Frameo facts the skills rely on are in `skills/conductor/references/frameo-gotchas.md` with the date they were read; re-verify against the live MCP when it changes.
