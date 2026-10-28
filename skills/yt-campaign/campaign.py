#!/usr/bin/env python3
"""campaign.py - the clipping campaigns you are in, and whether a clip meets one's rules.

    python3 campaign.py list                                  # every campaign, rate, budget, runway
    python3 campaign.py check clips/short_01.mp4 --campaign fintech-ramp --platform tiktok
    python3 campaign.py check clips/short_01.mp4 --campaign fintech-ramp --json

Reads campaigns.json (./campaigns.json, ./data/campaigns.json or ./docs/campaigns.json, or
--db PATH). The file is a list of campaigns under "campaigns"; SKILL.md has the fields.

CHECK measures the clip with ffprobe and tests what a machine can: campaign active and not past its
end date, budget left, platform allowed, length inside the campaign's window, 9:16 and at least
1080 wide, and the hook and first line against the campaign's banned words. Every rule it cannot
test (approval criteria, "no ad reads", geo) is printed as a CHECK line for a human. Exit code 1
if anything FAILs. Nothing here posts or submits.
"""
import datetime, json, os, re, shutil, subprocess, sys, csv

PLATFORMS = {"tiktok": "tiktok", "tt": "tiktok", "instagram": "instagram", "ig": "instagram",
             "reels": "instagram", "youtube": "youtube", "yt": "youtube", "shorts": "youtube"}

def die(msg): print(msg, file=sys.stderr); sys.exit(1)

def find(name, given=None):
    for p in ([given] if given else [name, os.path.join("data", name), os.path.join("docs", name)]):
        if p and os.path.exists(p): return p
    die(f"no {name} found (looked in ., data/, docs/). Pass --db PATH or create one - see SKILL.md")

def load(path):
    d = json.load(open(path))
    return d["campaigns"] if isinstance(d, dict) else d

def get(camps, cid):
    for c in camps:
        if c["id"] == cid: return c
    die(f"no campaign '{cid}'. Known: {', '.join(c['id'] for c in camps)}")

def runway(c):
    """Days of budget left at the campaign's recent burn rate, if the file has one."""
    burn = c.get("burn_per_day")
    return c["budget_left"] / burn if burn else None

def cmd_list(camps):
    today = datetime.date.today()
    print(f"{'id':<22} {'status':<11} {'$/1K':>5} {'net/1K':>6} {'left':>8} {'runway':>7} {'cap':>5}  platforms")
    for c in sorted(camps, key=lambda c: (c.get("status") != "active", -c.get("rate_per_1k", 0))):
        fee = fee_frac(c.get("fee_pct", 0))
        rw = runway(c)
        ends = c.get("ends")
        if ends and datetime.date.fromisoformat(ends) < today: status = "ended"
        else: status = c.get("status", "active")
        print(f"{c['id']:<22} {status:<11} {c['rate_per_1k']:>5.2f} {c['rate_per_1k'] * (1 - fee):>6.2f} "
              f"{c.get('budget_left', 0):>8,.0f} {(f'{rw:.0f}d' if rw else '-'):>7} "
              f"{c.get('per_clip_cap') or '-':>5}  {','.join(c.get('platforms', []))}")
        checked = c.get("budget_checked")
        if checked and (today - datetime.date.fromisoformat(checked)).days > 3:
            print(f"{'':<22} budget last checked {checked} - re-check before cutting for it")

def fee_frac(f): return f / 100 if f > 1 else f

def probe(path):
    exe = next((p for p in [os.environ.get("YT_FFPROBE"), "/opt/homebrew/opt/ffmpeg-full/bin/ffprobe",
                            shutil.which("ffprobe")] if p and os.path.exists(p)), None)
    if not exe: die("ffprobe not found - install ffmpeg")
    out = subprocess.run([exe, "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:format=duration", "-of", "json", path],
                         capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    s = d["streams"][0]
    return s["width"], s["height"], float(d["format"]["duration"])

def clip_row(path):
    """The row yt-clip wrote for this file, if clips.csv sits next to it."""
    log = os.path.join(os.path.dirname(os.path.abspath(path)), "clips.csv")
    if not os.path.exists(log): return {}
    for r in csv.DictReader(open(log)):
        if r.get("clip") == os.path.basename(path): return r
    return {}

def cmd_check(camps, clip, cid, platform):
    c = get(camps, cid)
    res = []
    def add(kind, msg): res.append((kind, msg))
    today = datetime.date.today()

    status = c.get("status", "active")
    if status == "shortlisted": add("WARN", "not joined yet - join it, then set status to active")
    elif status != "active": add("FAIL", f"campaign status is '{status}'")
    if c.get("ends") and datetime.date.fromisoformat(c["ends"]) < today: add("FAIL", f"campaign ended {c['ends']}")
    left = c.get("budget_left")
    if left is not None:
        if left <= 0: add("FAIL", "budget is spent")
        elif c.get("budget_total") and left / c["budget_total"] < 0.15:
            add("WARN", f"only ${left:,.0f} of ${c['budget_total']:,.0f} left - post today or skip")
        else: add("PASS", f"${left:,.0f} budget left")
    checked = c.get("budget_checked")
    if checked and (today - datetime.date.fromisoformat(checked)).days > 3:
        add("WARN", f"budget figure is from {checked} - re-check it on the campaign page")

    allowed = [PLATFORMS.get(p.lower(), p.lower()) for p in c.get("platforms", [])]
    if platform:
        p = PLATFORMS.get(platform.lower(), platform.lower())
        if allowed and p not in allowed: add("FAIL", f"{p} does not pay on this campaign (only {', '.join(allowed)})")
        else: add("PASS", f"{p} is a paying platform")
    elif allowed:
        add("CHECK", f"post only to: {', '.join(allowed)}")

    w, h, dur = probe(clip)
    lo, hi = c.get("min_seconds", 0), c.get("max_seconds", 180)
    if dur < lo - 0.25: add("FAIL", f"{dur:.1f}s is under the {lo}s minimum")
    elif dur > hi + 0.25: add("FAIL", f"{dur:.1f}s is over the {hi}s maximum")
    else: add("PASS", f"{dur:.1f}s is inside {lo}-{hi}s")
    if abs(w / h - 9 / 16) > 0.01: add("FAIL", f"{w}x{h} is not 9:16")
    elif w < 1080: add("WARN", f"{w}x{h} is under 1080 wide")
    else: add("PASS", f"{w}x{h}")

    row = clip_row(clip)
    text = " ".join([row.get("hook", ""), row.get("first_line", "")]).lower()
    for word in c.get("banned_words", []):
        if text and re.search(r"\b" + re.escape(word.lower()) + r"\b", text):
            add("FAIL", f"hook or first line says '{word}', which the brief bans")
    if c.get("captions_required"):
        add("PASS" if row else "CHECK", "captions burned by yt-clip" if row else "captions required - confirm they are burned in")
    if c.get("min_payout"):
        add("CHECK", f"pays only once a clip earns ${c['min_payout']} "
                     f"(~{c['min_payout'] / c['rate_per_1k'] * 1000:,.0f} views)")
    if c.get("geo"): add("CHECK", f"geo: {c['geo']}")
    for rule in c.get("rules", []): add("CHECK", rule)
    if c.get("submit_within_minutes"):
        add("CHECK", f"submit the link within {c['submit_within_minutes']} min of posting")
    return c, res

def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("list", "check"): print(__doc__); sys.exit(1)
    db = find("campaigns.json", a[a.index("--db") + 1] if "--db" in a else None)
    camps = load(db)
    if a[0] == "list": return cmd_list(camps)
    if len(a) < 2 or not os.path.exists(a[1]): die("check needs a clip file")
    if "--campaign" not in a: die("check needs --campaign ID")
    plat = a[a.index("--platform") + 1] if "--platform" in a else None
    c, res = cmd_check(camps, a[1], a[a.index("--campaign") + 1], plat)
    if "--json" in a:
        print(json.dumps([{"result": k, "detail": m} for k, m in res], indent=1))
    else:
        print(f"{os.path.basename(a[1])} against {c['name']} ({c['id']})")
        for k, m in res: print(f"  {k:<5} {m}")
        fails = sum(k == "FAIL" for k, _ in res)
        print(f"\n{'NOT READY' if fails else 'READY'} - {fails} fail, "
              f"{sum(k == 'CHECK' for k, _ in res)} to confirm by hand")
    sys.exit(1 if any(k == "FAIL" for k, _ in res) else 0)

if __name__ == "__main__":
    main()
