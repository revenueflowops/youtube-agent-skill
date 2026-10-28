---
name: yt-track
description: >-
  Track posted clips from post to views to dollars: log each post, update its
  views and approval status, and write the weekly summary with what to keep
  and what to drop. Use for "log this post", "update my views", "how much
  did I make", "weekly clipping summary", "which campaign is paying",
  "what's still pending".
---

# yt-track

One row per clip per platform, in `tracking.csv`. The money in clipping is decided by a handful of
posts, so the sheet exists to find those and stop spending hours on the rest.

```bash
python3 track.py post clips/short_01.mp4 --campaign fintech-ramp --platform tiktok --url URL --submitted
python3 track.py update --url URL --views 48200 --status approved
python3 track.py summary
```

The sheet sits in the user's project (`./`, `outputs/` or `data/`, or `--sheet`). Rates, caps and
fees come from `campaigns.json` (see `/yt-campaign`) and are copied into the row when it is
logged. The hook and source moment come from the `clips.csv` that `/yt-clip` wrote next to the clip.

## Posting

Log a post the moment it is live. `post` refuses a platform the campaign does not pay on. If the
campaign wants the link submitted within a time limit, `post` says so; pass `--submitted` once it
is, or run `update --clip ID --platform P --submitted` after.

## Views

There is no API here. Ask the user for the numbers off the marketplace dashboard: paste,
screenshot or a CSV export. Read them yourself and run one `update` per row. Never estimate a view
count. A count that goes down is flagged, because it usually means a typo or the wrong post.

## Payout rules

- gross = views / 1000 x rate, capped at the per-clip cap
- zero if under the campaign's minimum payout, and zero if rejected
- net = gross less the marketplace fee

Approved and pending are kept apart. Pending is money that can still disappear.

## The weekly summary

`summary` covers this week by default (`--week DATE`, `--all`). It shows each campaign's clips,
posts, views, views per post and net money, then views by platform, then the flags:

- **NOT SUBMITTED**: posted but the link was never sent to the campaign.
- **UNDER FLOOR**: the post has not reached the campaign's minimum payout.
- **CAPPED**: it has stopped earning. Post the same moment on a platform it has not hit yet.
- **STILL PENDING** after 10 days, **UNPAID** 14 days after approval: chase both.

It ends with the best post and a markdown table in the campaign log's weekly-review format. Paste
the table into the log. A campaign marked `drop?` has an average post that never clears its own
payout floor. Say that plainly, then ask whether the clips or the campaign are the problem: if
another campaign's clips travel, it is the campaign.

## The gate

Nothing here posts, submits or logs in. This skill writes and you publish. Every output ends in a
block the user copies, and the last line of every run is the question: **ship it, or change it?**
