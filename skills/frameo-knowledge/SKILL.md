---
name: frameo-knowledge
description: Use before planning or costing any Frameo job, and whenever Frameo's skills, models or prices may have changed. Reads the saved skills map, diffs it against the live Frameo MCP (free calls only), re-reads only changed skills, and updates the map so later plans are faster and cheaper. Never generates media or spends credits.
---

# Frameo knowledge

Keeps `references/skills-map.md` (what each Frameo skill is for and how to use it) and `references/skills-versions.json` (version of each skill as last read) current, and tells planners which skill to read first.

## Free calls only
`list_skills`, `get_skill`, `list_models`, `list_presets`, `get_presets`, `search_voices`, `whoami`. No `generate_*`, `analyze_media`, `run_ffmpeg`, `upscale_*`.

## When to run
1. At the start of every new job plan (cheap: one `list_skills` call plus a diff).
2. When a Frameo tool refuses, changes its arguments, or a price differs from the map.
3. After a job taught something new (a limit, a failure mode, a cheaper route): record it immediately in the map's "Deep notes".

## Refresh procedure
1. Read `references/skills-versions.json` and `references/skills-map.md`.
2. `list_skills`. Compare every `skill_id` and `version` to the registry.
   - New skill: add a row to the map (purpose from its summary and "when", neighbour to prefer) and to the registry.
   - Version changed: `get_skill` that skill (and its listed files that are procedures or rules), update its entry, set the new version.
   - Removed skill: delete the row and say so in the report.
3. `list_models` for video, image, speech, lipsync: update the credits-per-second/-image lines in the map; flag any price that moved by more than 10%.
4. For the skill the current job will use, do a **deep read** (full `get_skill` plus procedure files) and distil: ordered steps with tool names, hard limits, what saves credits, what can run in parallel. Add it under "Deep notes" and mark `deep_read` in the registry. Catalog-only entries get upgraded this way, one job at a time.
5. Set `read_on` in the registry. Report: what changed, what was deep-read, which skill the planner should read first for this job.

## Planning use
Before writing a plan: pick the job skill from the map, deep-read it if not yet, apply the map's "rules that save credits", and put any deviation from that skill's own procedure in the plan with the reason. Keep notes factual and dated; never store user data, ids of private projects, or credentials in these files.
