#!/usr/bin/env python3
"""track.py - posted clips, their views, and what they paid.

    python3 track.py post clips/short_01.mp4 --campaign fintech-ramp --platform tiktok --url URL
    python3 track.py update --url URL --views 48200 --status approved
    python3 track.py update --clip short_01 --platform tiktok --submitted
    python3 track.py summary                      # this week (Monday to today)
    python3 track.py summary --week 2026-10-26    # the week containing that date
    python3 track.py summary --all

The sheet is tracking.csv (./, outputs/ or data/, or --sheet PATH), one row per clip per platform.
Rates, caps and fees come from campaigns.json (see /yt-campaign) at the moment of posting and are
copied into the row, so a campaign changing its rate later does not rewrite what you were owed.

Payout per row: views / 1000 x rate, capped at the per-clip cap, zero below the campaign's minimum
payout, zero if rejected. Net is gross less the marketplace fee. PENDING money is shown apart from
APPROVED money, because a pending clip can still be rejected. Views are typed in from the
dashboards - nothing here logs in anywhere or posts anything.
"""
import csv, datetime, json, os, sys

COLS = ["clip_id", "date_posted", "campaign", "marketplace", "platform", "post_url", "source_moment",
        "hook", "submitted_at", "status", "views", "rate_per_1k", "per_clip_cap", "gross_payout",
        "fee_pct", "net_payout", "paid_date", "notes"]
PLATFORMS = {"tt": "tiktok", "ig": "instagram", "reels": "instagram", "yt": "youtube", "shorts": "youtube"}

def die(msg): print(msg, file=sys.stderr); sys.exit(1)

def arg(a, k, default=None): return a[a.index(k) + 1] if k in a else default

def find(name, dirs, given=None, create=False):
    if given: return given
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.exists(p): return p
    if create: return os.path.join("outputs" if os.path.isdir("outputs") else ".", name)
    return None

def campaigns(given):
    p = find("campaigns.json", [".", "data", "docs"], given)
    if not p or not os.path.exists(p): return {}
    d = json.load(open(p))
    return {c["id"]: c for c in (d["campaigns"] if isinstance(d, dict) else d)}

def read(sheet):
    if not os.path.exists(sheet): return []
    return list(csv.DictReader(open(sheet, newline="")))

def write(sheet, rows):
    with open(sheet, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

def num(x, default=0.0):
    try: return float(x)
    except (TypeError, ValueError): return default

def fee_frac(f): return f / 100 if f > 1 else f

def payout(r, camps):
    """(gross, net, note) for one row."""
    if r.get("status") == "rejected": return 0.0, 0.0, "rejected"
    gross = num(r["views"]) / 1000 * num(r["rate_per_1k"])
    note = ""
    cap = num(r.get("per_clip_cap"), None)
    if cap and gross >= cap: gross, note = cap, "capped"
    floor = camps.get(r["campaign"], {}).get("min_payout")
    if floor and gross < floor: gross, note = 0.0, f"under ${floor:g} floor"
    return round(gross, 2), round(gross * (1 - fee_frac(num(r.get("fee_pct")))), 2), note

def clip_row(path):
    log = os.path.join(os.path.dirname(os.path.abspath(path)), "clips.csv")
    if os.path.exists(log):
        for r in csv.DictReader(open(log)):
            if r.get("clip") == os.path.basename(path): return r
    return {}

def cmd_post(a, sheet, camps):
    if len(a) < 2: die("post needs a clip file or id")
    clip, cid, plat, url = a[1], arg(a, "--campaign"), arg(a, "--platform"), arg(a, "--url", "")
    if not cid or not plat: die("post needs --campaign and --platform")
    plat = PLATFORMS.get(plat.lower(), plat.lower())
    c = camps.get(cid)
    if not c: die(f"no campaign '{cid}' in campaigns.json - add it with /yt-campaign first")
    if c.get("platforms") and plat not in [PLATFORMS.get(p, p) for p in c["platforms"]]:
        die(f"{plat} does not pay on {cid} (only {', '.join(c['platforms'])}) - not logged")
    rows = read(sheet)
    clip_id = os.path.splitext(os.path.basename(clip))[0]
    if any(r["clip_id"] == clip_id and r["platform"] == plat and r["campaign"] == cid for r in rows):
        die(f"{clip_id} on {plat} for {cid} is already logged - use update")
    src = clip_row(clip)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    r = {"clip_id": clip_id, "date_posted": arg(a, "--date", datetime.date.today().isoformat()),
         "campaign": cid, "marketplace": c.get("marketplace", ""), "platform": plat, "post_url": url,
         "source_moment": f"{src['source']} {src['start']}-{src['end']}s" if src else "",
         "hook": src.get("hook", ""), "submitted_at": now if "--submitted" in a else "",
         "status": "pending", "views": "0", "rate_per_1k": c["rate_per_1k"],
         "per_clip_cap": c.get("per_clip_cap") or "", "fee_pct": c.get("fee_pct", 0),
         "paid_date": "", "notes": arg(a, "--notes", "")}
    r["gross_payout"], r["net_payout"], _ = payout(r, camps)
    rows.append(r); write(sheet, rows)
    print(f"logged {clip_id} -> {cid} on {plat}" + ("" if r["submitted_at"] else
          f"  (not submitted yet{' - submit within ' + str(c['submit_within_minutes']) + ' min' if c.get('submit_within_minutes') else ''})"))

def cmd_update(a, sheet, camps):
    rows = read(sheet)
    url, clip, plat = arg(a, "--url"), arg(a, "--clip"), arg(a, "--platform")
    if plat: plat = PLATFORMS.get(plat.lower(), plat.lower())
    hits = [r for r in rows if (url and r["post_url"] == url) or
            (clip and r["clip_id"] == clip and (not plat or r["platform"] == plat))]
    if not hits: die("no matching row - pass --url, or --clip with --platform")
    if len(hits) > 1: die(f"{len(hits)} rows match - add --platform or use --url")
    r = hits[0]
    if "--views" in a:
        v = int(arg(a, "--views").replace(",", ""))
        if v < num(r["views"]): print(f"  note: views went DOWN ({r['views']} -> {v}) - check the number")
        r["views"] = str(v)
    if "--status" in a:
        s = arg(a, "--status")
        if s not in ("pending", "approved", "rejected"): die("status is pending, approved or rejected")
        r["status"] = s
    if "--submitted" in a: r["submitted_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    if "--paid" in a: r["paid_date"] = arg(a, "--paid")
    if "--url-set" in a: r["post_url"] = arg(a, "--url-set")
    if "--notes" in a: r["notes"] = arg(a, "--notes")
    r["gross_payout"], r["net_payout"], note = payout(r, camps)
    write(sheet, rows)
    print(f"{r['clip_id']} {r['platform']}: {int(num(r['views'])):,} views, {r['status']}, "
          f"gross ${r['gross_payout']:.2f}, net ${r['net_payout']:.2f}" + (f"  ({note})" if note else ""))

def cmd_summary(a, sheet, camps):
    rows = read(sheet)
    if not rows: die(f"{sheet} has no rows yet")
    if "--all" in a:
        lo, hi, label = datetime.date.min, datetime.date.max, "all time"
    else:
        d = datetime.date.fromisoformat(arg(a, "--week", datetime.date.today().isoformat()))
        lo = d - datetime.timedelta(days=d.weekday()); hi = lo + datetime.timedelta(days=6)
        label = f"week of {lo.isoformat()}"
    rows = [r for r in rows if lo <= datetime.date.fromisoformat(r["date_posted"]) <= hi]
    if not rows: die(f"nothing posted in the {label}")
    by = {}
    for r in rows:
        g, n, note = payout(r, camps)
        r["_g"], r["_n"], r["_note"] = g, n, note
        by.setdefault(r["campaign"], []).append(r)

    print(f"Clipping, {label}\n")
    print(f"{'campaign':<20} {'clips':>5} {'posts':>5} {'views':>9} {'views/post':>10} "
          f"{'approved':>9} {'pending':>8} {'paid':>8}")
    tot = [0, 0, 0, 0.0, 0.0, 0.0]
    for cid, rs in sorted(by.items(), key=lambda kv: -sum(r["_n"] for r in kv[1])):
        clips = len({r["clip_id"] for r in rs}); views = sum(int(num(r["views"])) for r in rs)
        ap = sum(r["_n"] for r in rs if r["status"] == "approved")
        pe = sum(r["_n"] for r in rs if r["status"] == "pending")
        paid = sum(r["_n"] for r in rs if r["paid_date"])
        print(f"{cid:<20} {clips:>5} {len(rs):>5} {views:>9,} {views // len(rs):>10,} "
              f"{ap:>9.2f} {pe:>8.2f} {paid:>8.2f}")
        for i, v in enumerate([clips, len(rs), views, ap, pe, paid]): tot[i] += v
    print(f"{'TOTAL':<20} {tot[0]:>5} {tot[1]:>5} {tot[2]:>9,} {tot[2] // tot[1]:>10,} "
          f"{tot[3]:>9.2f} {tot[4]:>8.2f} {tot[5]:>8.2f}   (net $)")

    plat = {}
    for r in rows: plat.setdefault(r["platform"], []).append(int(num(r["views"])))
    print("\nby platform: " + ", ".join(f"{p} {sum(v):,} views over {len(v)} posts"
                                         for p, v in sorted(plat.items(), key=lambda kv: -sum(kv[1]))))

    flags = []
    today = datetime.date.today()
    for r in rows:
        tag = f"{r['clip_id']} {r['platform']} ({r['campaign']})"
        if not r["submitted_at"]: flags.append(f"NOT SUBMITTED  {tag} - views before submission may not count")
        if r["_note"].startswith("under"): flags.append(f"UNDER FLOOR    {tag} - {int(num(r['views'])):,} views, {r['_note']}")
        if r["_note"] == "capped": flags.append(f"CAPPED         {tag} - it has stopped earning; repost the moment elsewhere")
        age = (today - datetime.date.fromisoformat(r["date_posted"])).days
        if r["status"] == "pending" and age > 10: flags.append(f"STILL PENDING  {tag} - {age} days, chase it")
        if r["status"] == "approved" and not r["paid_date"] and age > 14:
            flags.append(f"UNPAID         {tag} - approved, {age} days, no paid date")
    if flags: print("\n" + "\n".join(flags))
    best = max(rows, key=lambda r: num(r["views"]))
    print(f"\nbest post: {best['clip_id']} on {best['platform']} - {int(num(best['views'])):,} views"
          + (f", hook \"{best['hook']}\"" if best["hook"] else ""))

    # Keep or drop: a campaign whose average post does not clear its own payout floor is paying
    # nothing for the hours, however good the rate looks.
    print("\n| Week of | Campaign | Clips | Views | Net payout | Keep / drop |\n|---|---|---|---|---|---|")
    for cid, rs in by.items():
        views = sum(int(num(r["views"])) for r in rs)
        c = camps.get(cid, {}); floor = c.get("min_payout") or 0
        floor_views = floor / c["rate_per_1k"] * 1000 if floor and c.get("rate_per_1k") else 0
        verdict = "drop?" if floor_views and views / len(rs) < floor_views else "keep"
        if c.get("budget_left") is not None and c["budget_left"] <= 0: verdict = "ended"
        print(f"| {lo.isoformat() if lo != datetime.date.min else 'all'} | {cid} | "
              f"{len({r['clip_id'] for r in rs})} | {views:,} | ${sum(r['_n'] for r in rs):,.2f} | {verdict} |")

def main():
    a = sys.argv[1:]
    if not a or a[0] not in ("post", "update", "summary"): print(__doc__); sys.exit(1)
    sheet = find("tracking.csv", [".", "outputs", "data"], arg(a, "--sheet"), create=True)
    camps = campaigns(arg(a, "--db"))
    {"post": cmd_post, "update": cmd_update, "summary": cmd_summary}[a[0]](a, sheet, camps)

if __name__ == "__main__":
    main()
