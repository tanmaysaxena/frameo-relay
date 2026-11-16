# Panel script template

Copy this shape exactly; `scripts/panel_check.py` reads it. Rules of the format:

- One `# Title` line, one meta line, then `## GLOBAL STYLE BIBLE`, then the shots in order, then `## PRODUCTION CHECKLIST & SIGN-OFF`, then (only if any line is `[generated]`) `## GENERATED ADDITIONS`.
- Shot heading: `## SHOT 01 — 0:00–0:12 — TITLE` (two digits; the dashes may be `—`, `–` or `-`; timecodes `m:ss`, running on without a gap from `0:00`).
- Every shot is a four-column table. The first two columns are written by the panel writer; **AI Fill** (generation status and notes) and **User Fill** (approve, reject, change) stay blank.
- No `|` inside a cell. Separate dialogue bubbles with ` / `.
- Cast names are UPPERCASE everywhere (style bible, Cast on screen, bubble speaker).

````markdown
# TITLE
Production Script | Runtime ~M:SS | N shots | <aspect> | <look in a few words> | Dialogue bubbles: <on/off>

## GLOBAL STYLE BIBLE — prepend to EVERY shot prompt
**CHARACTERS:** NAME — build, hair, palette, signature gear, how they carry themselves. NAME2 — ...
**ENVIRONMENT:** the look of places, light and texture, in plain visible terms.
**DIALOGUE RULE:** how spoken lines are shown (for example: every spoken line is a comic bubble, white, bold lettering, tail to the speaker; no captions).
**NARRATION:** the narrator's voice and delivery; narration is audio only, never in a bubble.
**TRANSITIONS:** how shots join (for example: halftone-dot wipes between shots; a hard cut inside a scene).
**SETTING:** country and everyday details that must stay consistent (for example: right-hand-drive cars, traffic on the left).

## HOW TO USE THIS DOCUMENT
- **For the video-generator AI:** for each shot, combine the Global Style Bible with the shot's Setup, Camera and Visual prompt cells into one prompt. Render the Dialogue bubbles cell as on-screen bubbles, never captions. Narration, SFX and BGM are audio direction for the sound pass, not visual prompts. Write status and notes in the AI FILL column.
- **For the human reviewer:** approve, reject or request changes per shot in the USER FILL column. A shot is locked when both columns agree.

---

## SHOT 01 — 0:00–0:12 — TITLE IN CAPITALS
| Field | Content | AI Fill | User Fill |
|---|---|---|---|
| Length | 12 s | | |
| Join | hard cut | | |
| Setup | Place: where, in one concrete line. Time and light: time of day, light direction and colour. Props: objects that must look the same in every shot of this place. | | |
| Cast on screen | NAME, NAME2 | | |
| Camera | One move, one framing, one lens feel. | | |
| Visual prompt | What the frame shows, in visible terms: who stands or sits where, which way each head is turned, what each hand does, what the face does, what the background does. Eyelines. | | |
| Dialogue bubbles | NAME: "Exact line." / NAME2: "Exact reply." | | |
| Narration (VO) | "Exact narration line." | | |
| SFX | Short cues, in order. | | |
| BGM | Mood and instrumentation, and what changes from the previous bed. | | |

## SHOT 02 — 0:12–0:24 — NEXT TITLE
(same eight-plus rows; `Join` is `hard cut` or `continues from SHOT 01`)

---

## PRODUCTION CHECKLIST & SIGN-OFF
| Item | Spec | AI Fill | User Fill |
|---|---|---|---|
| Aspect ratio | 16:9 default / 9:16 vertical cut | | |
| Resolution | draft 720p, final by upscale to 1080p | | |
| Frame rate | 24 fps | | |
| Narrator voice | who, how | | |
| Bubble policy | Bubbles ON in every prompt, never captions or subtitles | | |
| Sensuality boundary | the ceiling, in words (only if a shot needs one) | | |
| Delivery | One video file, N shots, about M:SS | | |
| Final sign-off | All N shots approved by both columns | | |

## GENERATED ADDITIONS
| Shot | Kind | Content | Why |   (kind: line, narration, beat; mark adapted author's lines with `[adapted]` in the cell and say so in Kind)
|---|---|---|---|
| 03 | line | NAME: "Invented line." | Dialogue was under 5% of runtime |
````

## Optional rows

Add a row only when the shot needs it, below `Visual prompt`: `On-screen text` (title cards, onomatopoeia, exact lettering), `Continuity` (what must match the shot before or after), `Fallback` (the one softer prompt for a heated shot, written in advance), `Notes`.
