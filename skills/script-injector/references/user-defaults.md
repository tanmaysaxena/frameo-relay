# Optional personal defaults

frameorelay ships with no personal taste baked in. If you want the same look, voices, music, bubbles or setting applied to every story without being asked each time, keep them in a defaults file. The injector, conductor and finish-cut read it when it exists and skip it when it does not.

## Where it is looked up (first match wins)
1. `./frameo-jobs/house-defaults.md` in the folder you are working in (this project only).
2. `~/.claude/frameorelay/house-defaults.md` (all your projects; on Windows `%USERPROFILE%\.claude\frameorelay\house-defaults.md`).

Never put credentials or private ids you do not want in a transcript in this file: the agent reads it into the conversation.

## What happens when it exists
- Apply it without asking, state each rule you used once in the plan ("Defaults applied: ..."), and ask only about what it does not cover (for example the voice of an extra character).
- A rule the user overrides for one story wins for that story.
- If a rule conflicts with `conductor/references/content-boundaries.md`, the content boundary wins.

## What to put in it
Start from `examples/house-defaults.example.md` in this repository. Typical sections: look (style anchor, 60 words or fewer, plain visible description), voices (preferred voice per role and accent), music mood, how dialogue is shown (bubbles, captions), transitions, and the default setting (country, drive side, era).

## What does not belong in it
General craft rules that apply to every story (bubbles never cover faces, eyelines, no dead stares, solid objects) already live in `prompt-quality-rules.md`.
