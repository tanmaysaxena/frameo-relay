# run_ffmpeg sandbox facts (measured 2026-11-16)

- A call holds 1 to 5 jobs (`bad_item_count` above); jobs in one call run side by side; the module is serial (`module_busy`), so send the next call after the last finished. About 80 runs an hour.
- `timeout_seconds` 30 to 600. A 264 s 480p picture with 45 trims, a flash overlay and an .ass layer took about 5 minutes at `-preset veryfast`. Split a longer film into parts and join with `-f concat -safe 0 -c copy` (same codec, size, fps).
- Inputs are links a Frameo tool returned; name each (`c0.mp4`) and use that name in argv. A still used as a video input needs `-loop 1 -t <seconds>` before its `-i`. One input stream feeds one filter: `split` it for several trims.
- Subtitles: `ass=b.ass` with the `.ass` as a sidecar works; bold `DejaVu Sans` renders (other fonts unverified). Vector shapes (`{\p1}` with `\pos`, `\bord`, `\1c`, `\3c`) draw the bubbles and boxes. An ASS line break is a backslash plus N: build it from a backslash constant in code, never inside a Python triple-quoted string.
- Audio: `adelay=<ms>:all=1` places a clip; `amix=...:normalize=0` keeps levels; `asplit` feeds a sidechain; `sidechaincompress=threshold=0.04:ratio=6:attack=20:release=350`; `loudnorm=I=-14:TP=-1.5:LRA=11` last, then `aresample=48000`. A mix of 60 inputs ran fine. `aloop=loop=-1:size=2147483647,atrim=0:N` loops a bed.
- Sound step: `-map 0:v -c:v copy -c:a aac -b:a 192k -movflags +faststart` (audio-only encode, fast).
- Contact sheet: `-vf fps=1/2,scale=150:-1,tile=5x3 -frames:v 1 out.jpg` (mime `image/jpeg`).
- `analyze_media` has no quote; 37 credits for a 4.4 minute film.
- Assume no local ffmpeg: generate the JSON locally, run it with the tool.
- Frame grabs of a finished file: `view_image(media_url, at_seconds)` works for files under 100 MB. For larger ones run a free `run_ffmpeg` with one input per frame (`-ss T -i f1.mp4 -ss T2 -i f2.mp4 -map 0:v -frames:v 1 a.jpg -map 1:v -frames:v 1 b.jpg`; two `-ss` options on one `-i` after an output do not seek separately) and `view_image` the jpg. A 5-minute 1080p final took about 90 minutes in a busy queue, 720p about 40.
- A one-job final (17 clips, 8 transition clips, title, mix and an `.ass` sidecar) is about 16 KB of JSON; send exactly what the script printed.
- Measured 2026-11-19 (overlay pass): libass with DejaVu Sans Bold, `zoompan`, `geq`, `colorkey`, `alphamerge` and `overlay` with `enable` all work; the concat demuxer with a sidecar `ffconcat` list joins `-c copy` parts and the audio of another input maps with `-map 1:a:0 -c copy`; one input name may be opened several times with different `-ss`. A 55 s 720x1280 part with bubbles and wipes takes 3 to 4 minutes. `view_image` cannot take a frame of a video over 100 MB.
