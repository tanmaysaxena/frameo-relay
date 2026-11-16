# Transitions

**Halftone, edge to edge, shuffled directions** (`scripts/halftone_transition.py`). A magenta dot grid with a cyan layer lagging and offset a few pixels (misregistered print) grows from one edge until the frame is covered, the cut happens at that peak, and the dots shrink away in the same direction, so the motion flows through the cut. Eight directions (LR, RL, TB, BT, four diagonals) are dealt from a shuffled deck so neighbours never repeat. 0.9 s each: 0.45 grow, 0.45 shrink.

- Make the 8 clips once: `python halftone_transition.py jobs [W H FPS DUR]` prints 8 `run_ffmpeg` jobs (`geq` on a black `lavfi` source). Send 5, then 3. Keep the links.
- `finish_cut.py` keys black to transparent (`colorkey`), delays each clip so its peak lands on the cut, and overlays it (`overlay=eof_action=pass`). One input per direction, split per use.
- Tune in `halftone_transition.py`: `PITCH` dot spacing, `RMAX` above 0.7072 for full coverage, `DUR`. A dark fringe: raise `key_similarity`.
- Written without a local ffmpeg, so not yet proven in the sandbox: render ONE direction first and `view_image` its peak frame before making all eight. If `geq` is too slow, make the clips at a lower size and scale them up in the overlay.

**Fallback flash**: one pattern image overlaid for 0.24 s on every cut (`transition.mode: flash`). It worked and the owner found it boring: use only when halftone is not available.

Lay a soft whoosh effect on each cut (gain 0.35, 0.2 s before the cut). Do not put a bubble on a frame where a transition peaks.
