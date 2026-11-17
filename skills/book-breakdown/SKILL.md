---
name: book-breakdown
description: Use when the user gives a whole book (a PDF or its text) to be made into a series of Frameo videos, one film per chapter. Finds the chapter breakpoints, sets each chapter's runtime from its size, builds one shared series bible (recurring characters with per-chapter looks, places, style, voices), gives every chapter its own new Frameo module inside one project, runs the chapter script and plan pipelines in parallel with subagents, and shows one book plan with a budget cap per chapter. Free, it never generates media or spends credits.
---

# Book breakdown

> **Host note.** `$RELAY_HOME` below is the folder that holds `scripts/relay_check.py` and `skills/`. In Claude Code and Cowork it is `${CLAUDE_PLUGIN_ROOT}`. In any other agent (Codex, Gemini CLI, Cursor, ...) it is `$FRAMEORELAY_HOME` if set, else `~/.frameorelay` (made by `scripts/install.py`), else the folder of the clone or plugin copy this skill came from. Resolve it once and reuse it. Tool names here are the Frameo MCP's own (`generate_videos`, ...); your host may prefix them (for example `mcp__frameo__generate_videos`). Subagent steps: if your host cannot spawn subagents, do them yourself in sequence. Details: `$RELAY_HOME/docs/hosts.md`.

Turns a whole book into a set of ready chapter plans that share one cast and one look. After it, each chapter is an ordinary relay job that `frameorelay:conductor` produces in its own module. Formats: `$RELAY_HOME/skills/book-breakdown/references/book-formats.md`. Subagent contracts: `$RELAY_HOME/skills/book-breakdown/references/chapter-pipeline.md`. Adaptation rules: `$RELAY_HOME/skills/book-breakdown/references/adaptation-rules.md`.

Hard rules, in order of importance:

1. **You never spend credits.** Creating a Frameo project and modules, saving notes and `import_media_url` are free and allowed, but only after the user has confirmed the chapter breakdown. Making the bible's images, and every clip, belongs to the conductor under an approval.
2. **Every chapter takes its own new module by default.** One project per book: a `Series Bible` module plus one module per chapter. Never put a chapter in the bible module and never let two chapters share a module unless the user asks and the reason is written in `shared_module_reason`. `book_check.py validate` enforces this.
3. **Recurring characters and places are made once and shared.** The project's cast (`save_character`, at most 30 characters) is shared by every module automatically. Places, props and the style reference live in a module's Library, so the conductor copies them into each chapter module with `import_media_url` (free; 10 files per call, 10 per minute). Only things that appear in two or more chapters are shared; one-off assets stay inside their chapter.
4. **The content ceiling is asked per chapter, in words.** Chapters flagged `heat` are asked first. Nothing above a chosen ceiling is planned, and the moderation filter is never probed (see `$RELAY_HOME/skills/conductor/references/content-boundaries.md`).
5. **Dialogue stays exact, prose is condensed and marked.** Every omitted scene is listed so the user can see what the film leaves out (`adaptation-rules.md`).
6. **Parallel means the free stages.** Scouts and chapter planners run as subagents at once. The paid stage runs in waves under the book budget with a cap per chapter, in the main session (conductor book mode).
7. **Chapter subagents have no Frameo access.** You fetch `list_models` limits and the voice candidates once and write them to `book/frameo-limits.json`; subagents read that file.

## Ask first (skip what is answered or covered by the user's defaults file)

- The book (a PDF path or text) and its title. Text-based PDFs only: a scanned PDF is refused by the extractor, tell the user to run OCR and pass text.
- Aspect ratio (9:16 or 16:9), the runtime window per chapter (default 3:00 to 15:00), book words per film minute (default 800), the book budget in credits and the retake allowance (propose 30%). Show what a chapter costs: about 28 credits per second at 720p for the first take plus the upscale, so a 15-minute chapter is about 25,000 credits before retakes. Read `$RELAY_HOME/docs/credit-economics.md`.
- Style direction and narrator or voice preferences (the user's defaults file covers these: `$RELAY_HOME/skills/script-injector/references/user-defaults.md`).

## Steps

1. **Extract.** `python "$RELAY_HOME/skills/book-breakdown/scripts/book_extract.py" extract <book.pdf> --out book --title "<title>"` (or `--text`). Read the table. Chapters flagged `tiny` are proposed to merge with a neighbour, chapters flagged `thick` as Part 1 / Part 2. **Ask the user** (never decide silently), then apply with `adjust --merge ch05,ch06` and `adjust --split ch07:3`. Missing or doubled headings show up as warnings: use `--heading-regex` or add breaks by hand.
2. **Start the book file.** `python "$RELAY_HOME/skills/book-breakdown/scripts/book_check.py" init book/breakdown.json --out book/book.json --book-id <slug> --budget <credits>`.
3. **Scout the whole book in parallel.** One `bible-scout` subagent per chapter (Codex: `frameorelay_bible_scout`), all in one message, each writes `book/scouts/<chapter>.json` (characters with looks and state in that chapter, places, props, dialogue speakers, heat or ceiling notes). Snapshot first and verify after, as the conductor does (`relay_check.py snapshot` on the folder).
4. **Merge the bible.** From the scout files and `book/names.json` write `book/bible.json` and `book/bible.md`: recurring characters (two or more chapters) with a base look and per-chapter variants (outfit, injury, age, disguise), recurring places and props, the style anchor, voices (`search_voices`, free, bind the choice later with `save_character`). Over 30 characters: keep the recurring ones that matter most and describe the rest per chapter. **Show the bible and let the user edit it** before any asset is made.
5. **Create the Frameo structure** (free, after the user confirms steps 1 and 4). `list_projects` first so a rerun reuses the project; otherwise `create_project` (name = book title, aspect), then `create_modules` with `Series Bible` and one `ChNN - <title>` name per chapter (the call is idempotent). Record the ids in `book/book.json` (`frameo.*`, each chapter's `module_id`). Run `book_check.py validate book/book.json --strict`.
6. **Plan every chapter in parallel.** Fetch limits and voices once into `book/frameo-limits.json`. One `chapter-planner` subagent per chapter (Codex: `frameorelay_chapter_planner`), all in one message: each writes `frameo-jobs/<book>/<chapter>/panel.md`, `plan.md` and a draft `relay.json` with a `series` block and `shared_from` locks, validated with `panel_check.py` and `relay_check.py validate --scratch`. Verify the snapshot, then merge their notes yourself.
7. **Ask the content ceiling for every chapter**, in words (clothed, implied, silhouette, ...), flagged `heat` chapters first. For a long book show one table and let the user answer in one message. Record each in `book/book.json` (`ceiling`) and in that chapter's `style.avoid`.
8. **Allocate and show the book plan.** `book_check.py allocate book/book.json --write` (cap = runtime share of the budget plus 25% headroom, not carried over). Present one table: chapter, runtime, shots, estimated credits, generated lines, ceiling, cap, with the book total against the budget and `docs/credit-economics.md` for the formula. Wait for a real yes per chapter or for the whole book.
9. **Hand off.** Set each approved chapter `status: approved` and its `approval.approved_total_credits` to its cap, then `frameorelay:conductor` in book mode builds the bible assets once, copies them into the chapter modules and produces the chapters in waves. Before every wave run `book_check.py budget book/book.json`; it fails when a chapter or the book is over.

## Done

`book_check.py validate book/book.json` passes, every chapter has its own module, its panel script, plan and validated draft `relay.json`, its ceiling and its cap, the bible is approved, and the user has the book plan with totals. Nothing was generated and no credit was spent by this skill.
