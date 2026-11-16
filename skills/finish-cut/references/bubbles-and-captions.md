# Bubbles and captions (ASS)

- **Bubble**: white ellipse (4 px black outline) at the top, 27 px bold DejaVu Sans, wrapped at 17 characters, a small coloured speaker tag (for example ANNA pink, BEN blue) above the words. The tail is a triangle from the ellipse bottom to `head_x`, so the bubble points at its speaker. The ellipse centre is clamped on screen. Choose `head_x` by looking at a frame: a female line whose tail pointed at the male figure is the most common review complaint.
- **Caption box**: yellow (`&H4FD9F9&`) rectangle with a black outline, bottom centre, 24 px bold text wrapped at 27 characters, height from its line count. Chunks follow sentences and commas, 85 characters at most, so a box stays under about four lines.
- **Timing**: bubble from line start minus 0.1 s to start plus measured seconds plus 0.35 s; caption chunks share the narration's measured seconds in proportion to their length.
- Say in every clip prompt: clear empty space in the upper third for speech bubbles, no lettering, no text.
- Do not place a bubble where a transition peaks.
- A bubble that cannot clear every face becomes two shorter bubbles split at a pause; inset panels that show faces count as faces. Re-check every bubble after a retake: line times and face positions move.

- **Updated rule**: bubbles are sized to their wrapped text (no overflow) and placed by `place_bubble()` so they never overlap any face in `faces`; the tail tip sits on the speaker's face top. A frame inside every bubble must be viewed before shipping.
