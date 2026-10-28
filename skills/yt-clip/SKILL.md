---
name: yt-clip
description: >-
  Cut a long video into finished vertical Shorts: transcribe it with whisper,
  pick the moments with the /yt-shorts rules, crop to 9:16 with ffmpeg and
  burn word-by-word captions. Use for "clip this video", "make shorts from
  this file", "cut this into vertical clips", "caption this clip", or any
  clipping-campaign job where a video file is the input.
---

# yt-clip

`/yt-shorts` finds the Shorts inside a long video and writes them. This one makes the files.

```bash
python3 clip.py transcribe video.mp4 --out clips/
python3 clip.py cut video.mp4 --plan clips/plan.json --out clips/
python3 clip.py cut video.mp4 --start 61.2 --end 104.8 --hook "Nobody tells you this" --out clips/
```

## Before you start

1. Check the tools once: `python3 clip.py` prints what it needs. It wants ffmpeg built with libass
   (`brew install ffmpeg-full` - the plain `ffmpeg` bottle cannot burn captions), whisper.cpp
   (`brew install whisper-cpp`) and a ggml model in `~/.cache/whisper/`. If something is missing,
   the error says the exact command. Install it rather than working around it.
2. If the video is a URL, ask the user for the file. Clipping someone else's video needs that
   campaign's permission; if `/yt-campaign` has a row for it, read the rules (length, watermark,
   caption style, required tags) before cutting anything.

## The run

1. **Transcribe.** `clip.py transcribe` writes `<name>.words.json` (every word, timed) and
   `<name>.transcript.txt` (sentences with timecodes). Read the `.txt`. Never guess at timings.
2. **Pick.** Apply the `/yt-shorts` picking rules to the transcript exactly as written there: a span
   of 20-55 seconds that opens on a complete thought, has a turn in it, and ends on a line. Rank
   them and show the user the top five with timecode, length and first line.
3. **Write the hook** for each one the user keeps: on-screen text for the first two seconds, five
   words or fewer, different words from the spoken first line. Score it with
   `../yt-script/hookscore.py` if it is doing the job of a first line.
4. **Plan file.** Write `clips/plan.json`:
   ```json
   [{"start": 61.2, "end": 104.8, "hook": "Nobody tells you this", "name": "short_01", "x": 0.5}]
   ```
   `x` slides the 9:16 window across a 16:9 frame: 0.0 is the left edge, 1.0 the right. Leave it at
   0.5 unless the speaker sits off-centre. If you can, grab a frame (`ffmpeg -ss 70 -i video.mp4
   -frames:v 1 frame.jpg`) and look at it before choosing.
5. **Cut.** `clip.py cut --plan`. Each span is snapped to whole words with a breath either side,
   cropped, scaled to 1080x1920, captioned two or three words at a time with the spoken word in
   yellow, and appended to `clips/clips.csv`, the cut log that `/yt-campaign check` and
   `/yt-track post` read.
6. **Check one.** Pull a frame from the middle of the first clip and look at it: are the captions
   clear of the speaker's face, is anyone cut in half by the crop. Fix `x` and recut if not.
7. **Before posting**, run `/yt-campaign check` on each clip for its campaign and platform, then
   log it with `/yt-track post` once it is live.

## What it will not do

It does not reframe on a moving subject - the crop window is fixed for the whole clip. It does not
add music, B-roll or a watermark. It does not fix whisper's spelling of names; if a caption is
wrong, edit the word in `words.json` and recut.

## The gate

Nothing here publishes. This skill writes and you publish. Every output ends in a block the user
copies, and the last line of every run is the question: **ship it, or change it?**
