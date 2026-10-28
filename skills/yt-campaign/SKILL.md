---
name: yt-campaign
description: >-
  Log the clipping campaigns you are in (Whop Content Rewards, Promote.fun,
  Vyro and the rest) with their rate, budget, cap and rules, and check a clip
  against a campaign before posting it. Use for "add this campaign", "which
  campaigns am I in", "is this clip ok for X", "check before I post",
  "how much budget is left".
---

# yt-campaign

A clipping campaign pays for views on clips that meet its brief, and rejects the rest after the
views are already spent. This keeps the brief in a file and checks every clip against it first.

```bash
python3 campaign.py list
python3 campaign.py check clips/short_01.mp4 --campaign fintech-ramp --platform tiktok
```

## The file

`campaigns.json` lives in the user's project: `./campaigns.json`, `data/` or `docs/`, or pass
`--db`. Write it yourself; there is no add command, because a brief never fits a fixed form.

```json
{"campaigns": [{
  "id": "fintech-ramp",
  "name": "Fintech Podcast Clipping, Month 4",
  "marketplace": "Content Rewards",
  "url": "https://contentrewards.com/...",
  "status": "active",
  "joined": "2026-10-28",
  "ends": null,
  "rate_per_1k": 2.50,
  "fee_pct": 0.10,
  "per_clip_cap": 315,
  "min_payout": 4,
  "budget_total": 2925,
  "budget_left": 2925,
  "budget_checked": "2026-10-28",
  "burn_per_day": null,
  "platforms": ["tiktok", "instagram", "youtube"],
  "min_seconds": 20,
  "max_seconds": 60,
  "captions_required": true,
  "geo": "40% of viewers in US/UK/CA/AU",
  "banned_words": [],
  "submit_within_minutes": 30,
  "rules": ["Lead with the idea, not an intro", "No ad reads"]
}]}
```

`status` is `shortlisted` (not joined yet), `active`, `paused` or `ended`. Only `id`, `name` and
`rate_per_1k` are required. Leave a field out rather than guessing it; a
missing rule is a CHECK line, a wrong one is a silent pass.

## Adding a campaign

1. Get the brief from the user: paste, screenshot, or the campaign page if they are signed in.
   Briefs behind a sign-in are theirs to open. Never sign in for them.
2. Copy the numbers exactly. Rate, cap, minimum payout, length window, platforms.
3. Every rule a machine cannot test goes into `rules` as a short imperative line, in the brief's
   own words.
4. Run `list` and show the user the row.

## Before every post

Run `check` on the clip for the platform it is going to. Any FAIL means do not post it there.
Read the CHECK lines out to the user as a checklist; they are the rules the clip is most often
rejected on. A budget figure older than three days is flagged because budgets drain in days.

## Weekly

When the user asks which campaigns to keep, update `budget_left` and `budget_checked` from the
campaign pages, then run `list`, then `/yt-track summary` for what each one actually paid.
Drop a campaign whose clips stall, not one that is merely slow.

## The gate

Nothing here posts or submits. This skill writes and you publish. Every output ends in a block the
user copies, and the last line of every run is the question: **ship it, or change it?**
