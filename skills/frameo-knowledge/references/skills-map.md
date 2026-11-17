# Frameo skills map (planning cheat sheet)

Source: live `list_skills` (56 skills) on 2026-11-16 plus full reads noted per entry. Update with the `frameo-knowledge` skill, never by memory. Entries marked **[deep]** were read in full; the rest are catalog-level (purpose and neighbour choice only) until a job needs them, then the job upgrades the entry.

## How to use Frameo skills when planning (rules that save credits)
1. Pick the job skill FIRST (`list_skills` summary + "when"), read it with `get_skill`, and only then write prompts. A job without its skill runs on untested defaults and costs retakes.
2. Prompting guides are mandatory reads before the matching generate tool: `video-prompting` (+ the model's own file), `image-prompting`, `audio-prompting`, `ffmpeg-recipes`.
3. Use `list_presets`/`get_presets` (free) before writing a camera move, light or framing from scratch.
4. Free reads first: `whoami`, `list_models`, `list_skills`, `get_skill`, `search_voices`, `list_presets`, `list_projects`, `list_characters`, `view_image`. Quote with `estimate_cost` before any paid call.
5. Pilot before bulk: continuity-check (3 hard shots), bulk-from-table (one pilot row), batch-photo-edit (one preview), canary clips before a fan-out.
6. Cheap model for drafts, best model for finals: seedance_2_5 720p is 28 cr/s vs 72 cr/s at 1080p; mini/fast variants are for prompt tests only.

## Production skills (video)
| Skill | Pick it when | Neighbour to prefer instead |
|---|---|---|
| script-to-video | A script with speaking characters becomes a finished video (micro-drama, dialogue ad, sketch). One shot per beat, cast consistent, subtitles. | faceless-story-video (no on-screen speaker); voiceover-to-video (one off-screen narrator) |
| video-script | Words must be written first (text only). | script already exists, skip |
| story-assets | Every character, location and prop of a script made at once as references. | character-sheet for a single character |
| character-sheet | One recurring character/mascot as views + expressions, saved to the project. | ai-persona (influencer/virtual model/photo-based) |
| continuity-check | Before many shots: lock map of what must not drift, plus a tested set of ~3 hard shots. | review-shots for shots already made |
| shot-plan | Camera plan per scene with an opening frame per shot, before animating. | storyboard-sheet (one grid image); script-to-video (whole job) |
| review-shots | Check every image/clip against the plan, retake a failed shot once. | design-feedback (critique of a user's own creative) |
| sound-pass | Music bed + library SFX + one mix ducked under dialogue on a finished video. | subtitles-and-cut for trims/captions/plain music bed |
| voiceover-timing | Narration that must fill fixed windows or a set length; take measured, only misses rewritten. | audio-prompting for voice choice in general |
| subtitles-and-cut | Edit existing footage: trim, resize, join, music, captions. | highlight-reel (auto-pick best parts) |
| faceless-story-video / voiceover-to-video / what-if-shorts / clay-explainer / brand-story-explainer | Narrated or stylised story formats with no talking on-screen characters. | script-to-video when characters speak |
| talking-presenter / presenter-overlay / video-podcast | One person (or two hosts) on camera, lipsynced. | script-to-video for acted scenes |
| ugc-video / website-tour-ad / ad-remake / ad-variations / bulk-from-table | Ads and batches. | n/a |
| cast-swap / video-recast / multi-cam-edit / aspect-reframe / video-dub / hindi-redub / reference-remix / reference-pacing / viral-effect-video | Transform or re-make existing video. | n/a |

## Production skills (images, brand, audio)
product-photoshoot, ad-creatives, static-ad, thumbnail-set, brand-kit, brand-mockups, product-fidelity, portrait-retouch, batch-photo-edit, apply-design-feedback, design-feedback, location-enhance, translate-on-screen-text, resize-for-social, storyboard-sheet, ai-persona: stills and brand work; see `list_skills` "when" text. Prompting guides: image-prompting, audio-prompting, ffmpeg-recipes. `make-skill` saves a repeatable way of working as a skill.

## Deep notes (grow this section as jobs read skills)
### video-prompting / Seedance (read 2026-11-16, v9) **[deep]**
- `seedance_2_5`: 4-30 s whole seconds, 16:9/9:16/1:1/4:3/3:4/21:9, 480p/720p/1080p, up to 30 reference images, 10 reference audios (1.8-30 s each, ~30.2 s combined). Seedance 2.0 family: 9 images, shorter clips.
- No separate frame mode: first/last frames fold into reference images (`@Image1` is the opening frame). Every image needs width/height ratio 0.4-2.5.
- Prompt order: context, references, location, first frame, shots and timing, camera, action, light, audio, style, locks. Write the visible, not the mood. One level of timing control per prompt. Seal each prompt (the model sees no other clip). Whip pans need >=0.8 s. Change angle >=30 degrees between cuts.
- Recorded dialogue: one audio clip per line bound to its speaker and moment, "use the audio clips strictly as-is", duration >= total clip length, short clips under ~1.8 s fail the whole call.
### story-assets / image-prompting / audio-prompting (read 2026-11-16, v8/v10/v8) **[deep]**
- References: `placement_kind` ("character"/"location"/"prop") + `placement_group` (the subject's name, identical on every call incl. retakes) on every reference image; `save_character` saves the face and voice to the cast (free).
- Image models: default `openai-gpt-image-2.5-sunburst` for characters, signs, anything with readable text (2 cr at 2K medium, 6 cr high); `nano-banana-pro` (18 cr at 2K) for scenes with people, edits and identity-keeping compositing; set `aspect_ratio` as a ratio ("16:9"); edits end with "make surgical edits"; first of `image_urls` is the base image, the rest are references; say whether faces/clothes stay identical.
- Quotes: one `estimate_cost` item per image, 1-10 items per call, `quote_id` single-use for 15 min; the generate call may reword the prompt but settings (model, aspect, resolution, quality, image_urls) must match. `generate_speech` is ONE call per line (no batch), 1-2 credits per line; quote 10 lines per `estimate_cost`.
- Speech: set `language_code` on every call ("en-IN" for Indian-English); direct delivery with inline `[cues]` incl. `[Indian accent]`; a bound voice (`list_characters` voice_id, `save_character`) skips the search; an `accent` filter removes every gemini voice. A speech line must be spoken exactly as written; never edit script text when quoting (quote + generate must carry the same text).
- Measured: Indian-English elevenlabs lines run ~2.0 words/s with pauses, so scripted shot lengths set by word count are too short; measure `duration_seconds` first, then size clips (one 42-line story turned a 156 s script into ~208 s).
- Seedance audio references must be 2-15 s each per the tool text (1.8 s in the guide): pad shorter lines with `run_ffmpeg` `-af apad=whole_dur=2.4 -t 2.4`.
- `finish-cut` (this plugin) adds bubbles/captions as text in the edit (.ass), never from the video model; conflicts with baked-in bubbles, so canary baked bubbles before committing.

### Learned on an early story run (2026-11-16): dialogue, bubbles, edit
- **Recorded-dialogue method works**: `generate_audio: true` + one `reference_audio_urls` clip per line + prompt "<Name> speaks @AudioN at 8.0 s word for word, only his lips move" gave correct speakers, accents and timing within about 0.4 s of the requested second (measured with analyze_media). Clip native audio also carries useful foley (drill, water, door) but sometimes adds a stray repeated line or music: gate those windows in the mix.
- **Baked-in bubbles**: short lines (under ~8 words) came out correct; long lines garbled and a brand name appeared on a prop. Use bubble-free clips and overlay.
- **Measure, don't guess**: join the audio of all clips with one `run_ffmpeg` (concat filter), then ONE `analyze_media` on the audio gives per-line start/end for every clip (cumulative offsets); about 2 credits.
- 720p `seedance_2_5` renders take 10-23 min per clip (longer clips slower), all 12 in parallel finished together; 28 cr/s at 720p.
- `run_ffmpeg` needs UTF-8 JSON: write EDL/ASS files with `encoding="utf-8"` on Windows (cp1252 turned an ellipsis into byte 0x85 and broke `finish_cut.py`).
- Halftone transition: one rendered direction (LR) plus an `hflip` copy (RL) is enough for a draft; map the 8 direction keys onto those two. Bubbles sit at a fixed top position, so they cover the head in close-ups (S06/S08): pass a per-chain `cy` or lower the bubble for close-ups next time.
- Edit assembly cost nothing but the final `analyze_media` listen (2 credits): picture job (bubbles + transitions, ~5 min) then sound job (~2 min) then title card append (~4 min).

### Frameo MCP facts that shape plans (see conductor/references/frameo-gotchas.md for the full list)
- `generate_videos` takes 1-10 items per call; quotes are single-use and expire in 15 min; replay the same call instead of re-quoting; `run_ffmpeg` and `analyze_media` are serial per module.
- `list_models(kind=...)` gives live credits/second: seedance_2_5 480p 13, 720p 28, 1080p 72 (silent = with sound). Image: GPT Image 2.5 Sunburst/Flare 2 cr at 1K/2K medium; Seedream 5.0 Pro 0 cr; Nano Banana Pro 18 cr. Lipsync sync-3 17.2 cr/s, lipsync-2-pro 8, lipsync-2 4.8.
- Voices: `search_voices` filters are exact matches; the user's own clones appear with `yours: true`; elevenlabs voice sets the language.

### Learned on a vertical run: finishing (2026-11-16)
- **Upscale for finals**: `list_models(kind="upscale")` default `byteplus_video_upscale_standard` is 0.5 cr/s to 720p and 0.9 cr/s to 1080p (9:16, 30 fps; max source 2560x1440, 30 s per clip). `estimate_cost` item `{kind: "upscale", video_url, factor, model}`, one `upscale_video` call per clip with its `quote_id` and `confirmed_by_user`. Whole 4-minute film at 1080p cost 203 credits instead of about 17,000 for a Seedance 1080p re-render. Use it as the default way to deliver 1080p; draft on 720p.
- `seedvr2_video_upscale` is only for sources above 2560x1440 or when the owner names it (several times slower and dearer).
- Craft rules that apply to every story (bubbles clear of faces, no camera gaze, solid modern cars, no "chapter complete") live in `script-injector/references/prompt-quality-rules.md`; optional personal defaults (look, voices, music, setting) are described in `script-injector/references/user-defaults.md`.

### Projects, modules and sharing (read 2026-11-17, tool definitions)
- One project holds many modules; each module has its own Library and notes. `create_project` makes a project with its first module; `create_modules` adds 1 to 100 named modules (free, idempotent by name, numbered in order); `list_projects` lists up to 200 modules per project.
- The **cast is project-level**: `save_character` adds a character (1 to 6 images, optional voice) to the project's Reference Library and every module sees it; at most 30 characters per project. Places, props and style references are not in the cast: copy them into another module's Library with `import_media_url` (free; 1 to 10 public https links per call, images up to 20 MB; 10 files per minute per account; sign-in links are refused).
- A module's notes can be read from another module of the same project (`list_notes` with a module `scope`); a module writes only its own notes.
