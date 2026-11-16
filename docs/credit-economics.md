# Credit economics

What a script-to-video job costs with and without frameorelay, where the credits go, and how to budget one. Everything here comes from production ledgers or from Frameo's published rates; the caveats are at the end.

## Headline

A finished 4:30 script-to-video film used to cost **65,000 to 80,000 credits** (the maintainer's earlier productions, made without this package). The three productions made with it cost **about 10,000 to 25,000 credits per 4:30 of film, about 17,000 on average**. That is **66% to 86% fewer credits, about 77% on average, roughly 55,000 credits saved per film**.

## Per-production comparison

Credits are normalised to a 4:30 film (270 s) by scaling linearly with picture length, so runs of different lengths compare fairly. Savings are against the 65,000 to 80,000 baseline; "saved" uses its midpoint, 72,500.

| Production | Finished film | Delivered | Credits spent | Per 4:30 of film | Saved vs 65,000 | Saved vs 80,000 | Credits saved (vs 72,500) |
|---|---|---|---|---|---|---|---|
| Run 1: 19-clip romance short (480p drafts, then 720p, then 1080p; style changed mid-run) | 4:38 (277.6 s) | 1080p | 25,399 | ≈ 24,700 | **62%** | **69%** | **≈ 47,800 (66%)** |
| Run 2: 12-shot vertical film | 4:00 (239.5 s) | 1080p | ≈ 8,700 to 11,000 (a) | ≈ 10,000 to 12,700 | **80% to 85%** | **84% to 88%** | **≈ 59,800 to 62,500 (83% to 86%)** |
| Run 3: 17-shot hard-cut film, two user-requested retake rounds | 5:04 (299 s picture + 5 s title) | 1080p | ≈ 16,400 to 16,600 | ≈ 14,800 to 15,000 | **77%** | **81%** | **≈ 57,500 (79%)** |
| **Average of the three** | | | | **≈ 17,000** | **≈ 74%** | **≈ 79%** | **≈ 55,500 (≈ 77%)** |
| Without the package (baseline) | 4:30 | | 65,000 to 80,000 | 65,000 to 80,000 | | | |

(a) Run 2's ledger was rebuilt after the run and holds only clips and retakes (8,651). The upper figure adds the 2,000 to 2,500 credits by which the account counter exceeded the ledger. That gap may include other activity on the same connection, so the true cost is probably nearer the lower figure; the table keeps the cautious range.

Per finished minute, the baseline is about 14,400 to 17,800 credits. The three runs: 5,500 (Run 1), 2,200 to 2,800 (Run 2), 3,300 (Run 3).

## Where the credits go

Run 3 (the cleanest ledger, 16,439 credits):

| Item | Credits | Share |
|---|---|---|
| Clips (17 first takes + 14 user-requested retakes and fix passes) | 15,036 | 91.5% |
| 1080p upscale | 442 | 2.7% |
| Reference sheets and plates | 404 | 2.5% |
| Keyframe stills | 378 | 2.3% |
| Keyframe retakes | 126 | 0.8% |
| Speech | 53 | 0.3% |

The 17 first takes cost 8,372 (exactly 299 s at 28 credits per second). The 14 retakes and fix passes cost 6,664 more, 44% of clip spend, because the user asked for motion passes and fixes after seeing the cut. Everything except clips was under 9% of the total.

Run 1 (ledger-visible, 25,399 credits): 480p drafts 7,800 (31%), native 720p clips 16,800 (66%), upscale 239, speech 155, keyframes 144, music 116, analysis 77, references 31, stills 21, sound effects 16. The 480p drafts alone (7,800) cost about as much as Run 2's entire ledger-visible spend (8,651), and the 720p finals then regenerated every clip, so every cut window had to be picked again.

## Where the savings come from

Measured or exact arithmetic on published rates (Seedance 2.5: 13 credits per second at 480p, 28 at 720p, 72 at 1080p; BytePlus upscale to 1080p about 0.9 per second):

- **Finish by upscale, never by a native 1080p render.** 270 s upscaled costs about 243 credits; re-rendering it at native 1080p costs 19,440. The baseline of 65,000 to 80,000 is the cost of about 3 to 4 native 1080p passes of the film, or 9 to 11 passes at 720p.
- **Go straight to 720p and skip a separate 480p draft pass.** In Run 1 the draft pass was 31% of the spend and produced clips that were then regenerated. Runs 2 and 3 went straight to 720p. (A 480p draft is still reasonable if you want to judge a story cheaply before paying for 720p; it costs 46% of a 720p pass and does not carry over.)
- **One approved total, quotes before spend, saved calls.** Nothing is generated before approval; a slow clip is replayed, never re-quoted (Run 1 paid for one slow clip twice, an extra 390 credits, before the rule existed); refused clips are refunded and rephrased once.
- **Fix in the edit, not by regenerating.** Cut windows around morph zones, speed changes, bubbles, transitions and mixes cost nothing (ffmpeg). Contact-sheet review finds the bad seconds so a clip is kept rather than retaken.
- **Fix early, where it is cheap.** A reference sheet or keyframe still costs 2 to 18 credits; the clip that depends on it costs 280 to 840. The plan, references and keyframes are approved before any clip is made.
- **Single-beat clips with matched keyframes, rendered in parallel.** No join to pay for, and a retake replaces one shot, not a chain.

These steps are why the numbers above are low; this repository has no ledger for the pre-package runs, so it cannot split the baseline by cause.

## Budgeting a job

For N seconds of finished picture at 720p, finished by upscale:

`total ≈ N × 28 × (1 + retake share) + N × 0.9 + about 800`

The 800 covers references, keyframes, speech, music, sound effects and analysis (about 500 to 1,000 in these runs). For a 4:30 film (N = 270):

| If you expect | Retake share | Total credits |
|---|---|---|
| Few changes after the first cut | 0% | ≈ 8,600 |
| A typical review round (Run 2) | 30% | ≈ 10,900 |
| Motion and fix passes requested after the cut (Run 3) | 80% | ≈ 14,700 |

Set the approved total from that table with some headroom; the conductor will not spend past it without asking. Test a 30 to 60 second piece first (about 840 to 1,700 credits at 720p) to see the look before committing the whole budget.

## Caveats

- The 65,000 to 80,000 baseline is the maintainer's figure from earlier productions made without the package; no ledgers from those runs are kept here. Treat the savings as "against the baseline the maintainer experienced", not as a controlled experiment.
- Three runs, one of them an early run made while the package was still being written, is a small sample. Your script, shot count, retakes and resolution will move the result. Run 3's two retake rounds and Run 1's double generation show the spread.
- Ledger totals can undercount: Run 2's ledger was rebuilt after the fact and omits speech, music and stills, and Run 3's does not log its listen checks (about 40 credits each). `whoami.spent_by_this_connection` can include other activity on the same connection (and did, when two productions ran in parallel), so it is a cross-check, not a total.
- Prices change. Re-check `list_models` (the `frameo-knowledge` skill does this with free calls) before relying on the per-second rates.
