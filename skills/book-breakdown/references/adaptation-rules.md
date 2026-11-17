# Adapting a chapter into a short film

A book chapter holds far more than a film of 3 to 15 minutes can show. The user chose: **dialogue exact, prose condensed**.

## What stays exact
- Spoken dialogue the film uses is copied word for word, including its punctuation, with the speaker named. If a line is too long for its shot, split it at a natural pause into two bubbles (same speaker); do not reword it.
- If a line must change (to fit a content ceiling or because it refers to something the film cut), keep the author's version in the panel script, mark the film line `[adapted]` and say why in the Kind column.

## What is condensed
- Narration is the book's descriptive and interior prose boiled down to short lines (about 2 to 3 words per second of speech). Mark every condensed narration line `[adapted]`. Use the book's own key phrases where they carry the meaning.
- Scenes are chosen, not skipped at random: keep the beats that move the plot or a character, merge adjacent small scenes, summarise a long passage in one narrated montage.

## What is invented (always flagged)
- A beat or line the book does not have is marked `[generated]`, listed on its own in the plan under "Generated dialogue", and not voiced until the user has approved it. Keep invented lines to the minimum needed to join condensed scenes.

## Listing what was left out
Each chapter's `panel.md` ends with an **Omitted from the chapter** table: the scene or passage (with its page range), why it was cut (runtime, ceiling, redundant) and whether a one-line narration stands in for it. The user reads this to decide whether to add a scene back before any credit is spent.

## Sizing the film
- Runtime comes from `book.json` (`runtime_s`). Size shots from the measured speech rate (about 2 words per second in accented delivery with pauses), not from word counts; set the cut windows after the speech is generated.
- Prefer single-beat clips of 6 to 10 seconds; hard cuts between them with matched keyframes (see the conductor's gotchas).

## Continuity across chapters
- Use the bible's names, base looks and variants verbatim. If a chapter needs a look the bible does not have (a new outfit, an injury), add a variant to the chapter's own notes and tell the main session so it goes into the bible for later chapters; do not invent a different face.
- A place that appears in another chapter uses its bible plate. One-off places are made inside the chapter.
- Do not rely on a chapter ending where the next one begins: chapters are hard cuts. If the story needs a recap, say so in the plan and leave it to the user.
