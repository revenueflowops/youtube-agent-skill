#!/usr/bin/env python3
"""clip.py - long video in, vertical captioned Shorts out.

    python3 clip.py transcribe video.mp4 --out clips/          # words.json + transcript.txt
    python3 clip.py cut video.mp4 --words clips/video.words.json --start 61.2 --end 104.8 \\
        --hook "Nobody tells you this" --out clips/
    python3 clip.py cut video.mp4 --words clips/video.words.json --plan plan.json --out clips/

TRANSCRIBE runs whisper.cpp (`whisper-cli`) at word level and writes two files: <name>.words.json,
every word with its start and end, and <name>.transcript.txt, the same words grouped into
sentences with timecodes. Read the .txt to pick moments; the cutter reads the .json.

CUT snaps each span to word boundaries, crops the frame to 9:16 (centre by default, --x 0.0-1.0
to slide the window), scales to 1080x1920, burns word-by-word captions with the spoken word
highlighted, puts the --hook on screen for the first two seconds, and appends a row to clips.csv,
the cut log /yt-campaign and /yt-track read the hook and source moment from. A --plan file is a
JSON list of {"start", "end", "hook", "name", "x"} objects, one per clip.

WHAT IT NEEDS. ffmpeg built with libass (`brew install ffmpeg-full`; the plain `ffmpeg` bottle has
no subtitles filter), whisper.cpp (`brew install whisper-cpp`) and one ggml model in
~/.cache/whisper/. Override any of them with YT_FFMPEG, YT_WHISPER, YT_WHISPER_MODEL. The script
itself is plain Python 3. Nothing here uploads anything.
"""
import csv, datetime, glob, json, os, re, shutil, subprocess, sys, tempfile

W, H = 1080, 1920
HIGHLIGHT = "&H0000E5FF"   # ASS colours are &HAABBGGRR - this is yellow
PAD = 0.12                 # breath kept either side of the first and last word

def die(msg): print(msg, file=sys.stderr); sys.exit(1)

def ffmpeg():
    cands = [os.environ.get("YT_FFMPEG"), "/opt/homebrew/opt/ffmpeg-full/bin/ffmpeg",
             "/usr/local/opt/ffmpeg-full/bin/ffmpeg", shutil.which("ffmpeg")]
    for c in cands:
        if c and os.path.exists(c):
            out = subprocess.run([c, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
            if re.search(r"\sass\s", out): return c
    die("no ffmpeg with libass found. Install it: brew install ffmpeg-full (or set YT_FFMPEG)")

def whisper():
    exe = os.environ.get("YT_WHISPER") or shutil.which("whisper-cli")
    if not exe: die("whisper-cli not found. Install it: brew install whisper-cpp (or set YT_WHISPER)")
    model = os.environ.get("YT_WHISPER_MODEL")
    if not model:
        found = glob.glob(os.path.expanduser("~/.cache/whisper/ggml-*.bin"))
        # Prefer the bigger models - the tiny ones mangle names and numbers, which are the words a
        # caption most needs to get right.
        rank = ["large", "medium", "small", "base", "tiny"]
        found.sort(key=lambda p: next((i for i, r in enumerate(rank) if r in os.path.basename(p)), 9))
        model = found[0] if found else None
    if not model or not os.path.exists(model):
        die("no whisper model. Download one:\n  mkdir -p ~/.cache/whisper && curl -L -o "
            "~/.cache/whisper/ggml-small.en.bin https://huggingface.co/ggerganov/whisper.cpp/"
            "resolve/main/ggml-small.en.bin")
    return exe, model

def stem(path): return os.path.splitext(os.path.basename(path))[0]

def ts(t): return f"{int(t // 60):02d}:{t % 60:04.1f}"

def transcribe(video, out):
    os.makedirs(out, exist_ok=True)
    exe, model = whisper()
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "audio.wav")
        subprocess.run([ffmpeg(), "-v", "error", "-y", "-i", video, "-ac", "1", "-ar", "16000", wav], check=True)
        base = os.path.join(tmp, "w")
        # -ml 1 -sow: one segment per word, split on word boundaries rather than tokens.
        subprocess.run([exe, "-m", model, "-f", wav, "-ml", "1", "-sow", "-oj", "-of", base, "-np"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raw = json.load(open(base + ".json", encoding="utf-8", errors="replace"))
    words = []
    for seg in raw.get("transcription", []):
        t = seg.get("text", "").strip()
        if not t or re.fullmatch(r"\[.*\]|\(.*\)", t): continue   # [BLANK_AUDIO], (music)
        s, e = seg["offsets"]["from"] / 1000, seg["offsets"]["to"] / 1000
        if words and not re.match(r"[\w$£€#]", t):                 # stray punctuation token
            words[-1]["w"] += t; words[-1]["end"] = e; continue
        words.append({"w": t, "start": round(s, 3), "end": round(e, 3)})
    n = stem(video)
    json.dump({"source": os.path.abspath(video), "words": words},
              open(os.path.join(out, n + ".words.json"), "w"), indent=0)
    with open(os.path.join(out, n + ".transcript.txt"), "w") as f:
        for s, e, text in sentences(words):
            f.write(f"[{ts(s)} - {ts(e)}] {text}\n")
    print(f"{len(words)} words -> {out}/{n}.words.json, {out}/{n}.transcript.txt")

def sentences(words):
    # Whisper often writes commas where the speaker ended a sentence, so a line also ends on a pause
    # or on a comma once it is long enough to read as a sentence.
    cur = []
    for i, w in enumerate(words):
        cur.append(w)
        gap = words[i + 1]["start"] - w["end"] if i + 1 < len(words) else 0
        if (re.search(r"[.!?]['\")]?$", w["w"]) or gap > 0.6 or len(cur) > 40
                or (len(cur) >= 12 and w["w"].endswith(","))):
            yield cur[0]["start"], cur[-1]["end"], " ".join(x["w"] for x in cur); cur = []
    if cur: yield cur[0]["start"], cur[-1]["end"], " ".join(x["w"] for x in cur)

def snap(words, start, end):
    """The words inside [start, end], with the span widened to whole words."""
    inside = [w for w in words if w["end"] > start + 0.05 and w["start"] < end - 0.05]
    if not inside: die(f"no speech between {start} and {end}")
    return inside

def chunks(words):
    """Caption pages: up to three words, never more than ~18 characters, break after punctuation."""
    page = []
    for w in words:
        if page and (len(page) == 3 or len(" ".join(x["w"] for x in page + [w])) > 18):
            yield page; page = []
        page.append(w)
        if re.search(r"[.,!?;:]$", w["w"]): yield page; page = []
    if page: yield page

def ass_time(t):
    t = max(t, 0); cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"

def ass_text(s): return s.replace("\\", "").replace("{", "(").replace("}", ")")

def build_ass(words, t0, dur, hook):
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Cap,Arial Black,92,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,7,3,2,60,60,560,1
Style: Hook,Arial Black,70,&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,1,0,0,0,100,100,0,0,3,18,0,8,80,80,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    if hook:
        ev.append(f"Dialogue: 1,{ass_time(0)},{ass_time(min(2.0, dur))},Hook,,0,0,0,,{ass_text(hook)}")
    pages = list(chunks(words))
    for i, page in enumerate(pages):
        # A page stays up until the next one starts, so the screen never blinks empty mid-sentence.
        # Gaps longer than a second do clear it.
        nxt = pages[i + 1][0]["start"] if i + 1 < len(pages) else page[-1]["end"] + 0.4
        page_end = nxt if nxt - page[-1]["end"] < 1.0 else page[-1]["end"] + 0.3
        for j, w in enumerate(page):
            s = w["start"]
            e = page[j + 1]["start"] if j + 1 < len(page) else page_end
            parts = [("{\\c" + HIGHLIGHT + "}" if k == j else "") + ass_text(x["w"].upper()) +
                     ("{\\c&H00FFFFFF&}" if k == j else "") for k, x in enumerate(page)]
            ev.append(f"Dialogue: 0,{ass_time(s - t0)},{ass_time(min(e, t0 + dur) - t0)},Cap,,0,0,0,,{' '.join(parts)}")
    return head + "\n".join(ev) + "\n"

def cut_one(video, words, start, end, out, hook="", name=None, x=0.5, track=None):
    span = snap(words, start, end)
    t0 = max(span[0]["start"] - PAD, 0)
    t1 = span[-1]["end"] + PAD
    dur = t1 - t0
    os.makedirs(out, exist_ok=True)
    name = name or f"{stem(video)}_{int(t0 // 60):02d}m{int(t0 % 60):02d}s"
    dst = os.path.abspath(os.path.join(out, name + ".mp4"))
    with tempfile.TemporaryDirectory() as tmp:
        open(os.path.join(tmp, "c.ass"), "w", encoding="utf-8").write(build_ass(span, t0, dur, hook))
        vf = (f"crop='min(iw,ih*9/16)':'min(ih,iw*16/9)':'(iw-ow)*{x}':'(ih-oh)/2',"
              f"scale={W}:{H},setsar=1,ass=c.ass")
        # Run from the temp dir so the ass= path needs no escaping - filter-graph quoting of an
        # absolute path with spaces or colons in it is where this kind of script usually breaks.
        cmd = [ffmpeg(), "-v", "error", "-y", "-ss", f"{t0:.3f}", "-i", os.path.abspath(video),
               "-t", f"{dur:.3f}", "-vf", vf, "-c:v", "libx264", "-preset", "medium", "-crf", "20",
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", dst]
        r = subprocess.run(cmd, cwd=tmp, capture_output=True, text=True)
        if r.returncode: die(r.stderr[-2000:])
    first = " ".join(w["w"] for w in span[:14])
    track = track or os.path.join(out, "clips.csv")
    new = not os.path.exists(track)
    with open(track, "a", newline="") as f:
        cw = csv.writer(f)
        if new: cw.writerow(["cut_date", "source", "clip", "start", "end", "seconds", "first_line", "hook"])
        cw.writerow([datetime.date.today().isoformat(), os.path.basename(video), os.path.basename(dst),
                     round(t0, 2), round(t1, 2), round(dur, 1), first, hook])
    print(f"{ts(t0)}-{ts(t1)}  {dur:4.1f}s  {dst}")
    if dur < 15 or dur > 60:
        print(f"  WARNING {dur:.0f}s is outside the 15-60s Shorts window", file=sys.stderr)
    return dst

def arg(a, k, default=None):
    return a[a.index(k) + 1] if k in a else default

def main():
    a = sys.argv[1:]
    if len(a) < 2 or a[0] not in ("transcribe", "cut") or not os.path.exists(a[1]):
        print(__doc__); sys.exit(1)
    cmd, video, out = a[0], a[1], arg(a, "--out", "clips")
    if cmd == "transcribe": return transcribe(video, out)
    wpath = arg(a, "--words") or os.path.join(out, stem(video) + ".words.json")
    if not os.path.exists(wpath): die(f"no {wpath} - run: python3 clip.py transcribe {video} --out {out}")
    words = json.load(open(wpath))["words"]
    if "--plan" in a:
        plan = json.load(open(arg(a, "--plan")))
        for c in plan:
            cut_one(video, words, float(c["start"]), float(c["end"]), out, c.get("hook", ""),
                    c.get("name"), float(c.get("x", 0.5)), arg(a, "--track"))
    else:
        if "--start" not in a or "--end" not in a: die("cut needs --start and --end, or --plan")
        cut_one(video, words, float(arg(a, "--start")), float(arg(a, "--end")), out, arg(a, "--hook", ""),
                arg(a, "--name"), float(arg(a, "--x", 0.5)), arg(a, "--track"))

if __name__ == "__main__":
    main()
