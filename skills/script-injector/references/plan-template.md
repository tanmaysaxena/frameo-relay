# plan.md template

```
# <title>: plan for approval

Shape: <aspect> · <resolution> · model <model> · workspace <name> (pinned)
Length: <total seconds> in <N> chains, <M> segments

## Style direction
Look: ...
Anchor (pasted into every prompt): "..."
Avoid: ...

## Cast, places, props, voices
| id | kind | description | voice |
|---|---|---|---|

## Chains and segments
### Chain c1 (scenes s1, s2) - continuous, rendered in order
| segment | seconds | first frame | last frame | what happens | join motion |
|---|---|---|---|---|---|

### Chain c2 (scene s3) - hard cut
...

## Voices
| who | kind | voice (name, id) | found in the pinned workspace |
|---|---|---|---|
(narrator = voice-only character, a different voice from the characters unless you said otherwise)

## On-screen text
Speech bubbles: <who, how shown>. Narration caption boxes: <yes/no>. Nothing is ever written by the video model.

## Sound plan
Music beds (mood, where they change), sound effects (cue, scene), ducked under speech, loudness -14 LUFS.

## Length and tiers
Target <s>, maximum <s>. 720p clips <n> (28 credits per second), 1080p upscale <n> (about 0.9 per second), retake allowance <30>% = <n>. Optional 480p draft pass <n> (13 per second, does not carry over): only if you want to judge the story before paying for 720p.

## Dialogue
Lines from the script (kept exactly): ...

## Generated dialogue (written by Claude, not in your script - approve or change each)
| id | segment | speaker | line |
|---|---|---|---|

## Not being generated
...

## Cost
Rough floor from list_models: <credits_per_second x seconds>. The conductor quotes exactly with
estimate_cost and asks for ONE up-front approval covering references, keyframes, clips, a retake
allowance (30% proposed) and speech analysis. Nothing is generated before that approval.
```

The scratch `relay.json` has the same content in the shape documented in
`skills/conductor/references/relay-schema.md`. A worked example is `examples/relay.sample.json`.
