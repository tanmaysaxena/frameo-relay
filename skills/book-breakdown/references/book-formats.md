# Book file formats

Paths inside `book.json` (the bible, each chapter's `job_dir`) are relative to the working folder that holds `book/` and `frameo-jobs/`; the book scripts resolve them against the parent of the folder `book.json` is in, or `--root`. All files live in the working folder: `book/` for the book-level files, `frameo-jobs/<book-id>/<chapter-id>/` for each chapter's job. Every file is plain JSON or Markdown; the scripts only read and write local files.

## `book/breakdown.json` (written by `book_extract.py`)
```
{version, title, source, pages, words,
 settings {words_per_film_minute, min_s, max_s},
 chapters [{id "ch01", number, kind chapter|prologue|epilogue|..., title, start_page, end_page, words,
            raw_runtime_s, runtime_s (clamped to the window), flags [tiny|thick|heat], scene_breaks, heat_hits, file}],
 skipped [{kind front matter|back matter, words, ...}], warnings [...]}
```
`runtime_s = clamp(words / words_per_film_minute * 60, min_s, max_s)` rounded to 10 s. Flags: `tiny` = the raw runtime is under the minimum (propose a merge), `thick` = over the maximum (propose parts), `heat` = one strong heated-passage term or five soft ones (a prompt to choose the chapter's ceiling; false positives and misses are both normal, so the ceiling is still asked for every chapter). `names.json` lists proper nouns with counts per chapter as a skeleton for the bible.

## `book/book.json` (the book contract, `book_check.py init` starts it)
```
{version 1, book_id, title, source, aspect_ratio "9:16"|"16:9",
 frameo {workspace_id, project_id, bible_module_id},
 runtime {min_s, max_s, words_per_film_minute},
 budget {total_credits, headroom_pct 25, retake_allowance_pct 30},
 bible {path "book/bible.json", module_name "Series Bible", ledger "frameo-jobs/<book-id>/bible/ledger.jsonl"},
 chapters [{id, number, title, kind, module_name, module_id, words, runtime_s, flags, text_file,
            ceiling (null until chosen, in words), status draft|planned|approved|in_production|done,
            cap_credits, job_dir, override?, shared_module_reason?}]}
```
Rules `book_check.py validate` enforces: every chapter has its **own** `module_id` (never the bible module, never shared unless `shared_module_reason` is set); runtimes inside the window or carrying an `override` reason; `cap_credits` equal to the runtime share of `budget.total_credits` plus `headroom_pct`; an approved chapter has a `ceiling`; the bible has at most 30 characters; each chapter's `relay.json` has a matching `series` block and its `shared_from` locks exist in the bible.

## `book/bible.json` (the series bible)
```
{book_id, title,
 style {anchor (60 words or fewer, plain visible description), notes},
 characters [{id, name, aliases [], chapters [1, 2, ...], base_look, voice {voice_id, name},
              images [urls, up to 6, set when the conductor builds the sheets],
              variants [{id, chapters [..], state "red wedding dress", notes}]}],
 locations [{id, name, chapters [..], look, plates [urls]}],
 props [{id, name, chapters [..], look, images [urls]}],
 styles [{id, refs [urls]}]}
```
Recurring means two or more chapters. Only recurring items are shared; one-off items stay in their chapter. Lock ids in a chapter's `relay.json` point at bible entries as `shared_from: "bible:<id>"`; an outfit or state variant also sets `variant_of: "bible:<base id>"`.

## Chapter job `frameo-jobs/<book-id>/<chapter-id>/`
The ordinary relay job (`relay.json`, `plan.md`, `ledger.jsonl`, `calls/`, ...) plus `panel.md`, with a `series` block in `relay.json`: `{book_id, chapter_id, chapter_no, bible: "book/bible.json", bible_module_id}` and `job.frameo.module_id` set to the chapter's own module. See `$RELAY_HOME/skills/conductor/references/relay-schema.md`.

## Cost dashboard
`book_check.py budget book/book.json [--write]` sums each chapter's `ledger.jsonl` (refunded rows excluded) plus the bible ledger and prints spent, cap, percent and remaining per chapter and for the book; `--write` saves `dashboard.md`. It exits 1 when a chapter is over its cap or the book is over its total.
