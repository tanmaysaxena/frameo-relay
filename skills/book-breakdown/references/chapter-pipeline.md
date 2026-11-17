# Chapter pipelines and subagent contracts

Two subagent roles run in parallel, one instance per chapter, all dispatched in a single message. Neither has any Frameo tool; neither spends. Before dispatching, take a snapshot of the folders they will write to (`python "$RELAY_HOME/scripts/relay_check.py" snapshot <folder>`); after they return, `verify-snapshot` with `--allow` for exactly the files each role may write. A FAIL means a subagent touched something else: stop and report.

## `bible-scout` (stage 3)
Input: the chapter's text file (`book/chapters/NN-*.txt`), `book/names.json` as hints, the chapter id.
Writes only `book/scouts/<chapter-id>.json`:
```
{chapter_id,
 characters [{name, aliases [], first_seen_quote, looks {hair, build, age, clothing, marks}, state "what changed this chapter",
              speaks (true|false), key_beats [..]}],
 places [{name, look, scenes [..]}], props [{name, look}],
 mood, time_of_day_range, heat_notes ["page range and what the passage asks for, in words"],
 unclear [questions about who someone is or what something looks like]}
```
Quote only a few words as evidence. Never invent a look the text does not give: put it in `unclear`.

## `chapter-planner` (stage 6)
Input: the chapter's text file, `book/bible.json`, the chapter's record in `book/book.json`, `book/frameo-limits.json`, the user's defaults file if any, and the adaptation rules.
Writes only inside `frameo-jobs/<book-id>/<chapter-id>/`:
1. `panel.md`: a panel script following `$RELAY_HOME/skills/panel-writer/SKILL.md` (shot tables, dialogue exact, prose condensed `[adapted]`, an "Omitted from the chapter" table), runtime from `book.json`. Run `python "$RELAY_HOME/skills/panel-writer/scripts/panel_check.py" check panel.md` and fix every FAIL.
2. `plan.md` and a draft `relay.json` following `$RELAY_HOME/skills/script-injector/SKILL.md` steps 1 to 6, with: a `series` block (`book_id`, `chapter_id`, `chapter_no`, `bible`, `bible_module_id`); `job.frameo.project_id` and the chapter's own `module_id` from `book.json`; one lock per cast, place and prop the chapter uses, with `shared_from: "bible:<id>"` for anything in the bible (and `variant_of` for an outfit or state variant), and chapter-only locks for everything else; the chapter's ceiling in `style.avoid`; the bible's style anchor. Run `python "$RELAY_HOME/scripts/relay_check.py" validate relay.json --scratch` and fix every FAIL.
3. A short `NOTES.md` for the main session: new variants the chapter needs, questions, the estimated first-take credits (28 per second of clip at 720p), and anything the ceiling forced out.
It does not show the plan to the user and does not wait for approval: the main session presents all chapters together.

## Main-session merge (after stage 6)
Read every `NOTES.md`, add new variants and characters to `book/bible.json` (respecting the 30-character cap), update `book/book.json` (`status: planned`, runtime, flags), then run `book_check.py validate --strict`.

## Paid stage (the conductor, book mode)
1. **Bible build** (once, approved): in the Series Bible module, make the master sheets and variants for recurring characters, the place plates and the style reference with the conductor's usual reference step; `save_character` each recurring character into the project cast with its voice; write the image links back into `book/bible.json`.
2. **Sync** (free): `python "$RELAY_HOME/skills/book-breakdown/scripts/book_check.py" sync-plan book/book.json` prints the `save_character` calls and the `import_media_url` batches per chapter module; run them (10 files per call, 10 files per minute).
3. **Chapters in waves:** each chapter is an ordinary conductor job in its own module with its own ledger, capped by `cap_credits`. Interleave chapters wave by wave (no more than `job.max_parallel` calls in flight in total). Before every wave run `book_check.py budget book/book.json`; a chapter at its cap stops until the user raises it.
