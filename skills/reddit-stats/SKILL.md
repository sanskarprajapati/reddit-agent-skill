---
name: reddit-stats
description: >-
  A light read of how the user's own Reddit posts and comments did: score, replies,
  which subs and which kind did well, help against promo, and any that Reddit labels
  as removed. Reads the user's own profile pages in their Chrome. Writes
  reddit/stats.md and suggests changes for /reddit-plan. Use when the user says "how did
  my posts do", "reddit stats", "what worked", "did my comment get removed", or
  "review my week".
argument-hint: "[days, e.g. 7 or 30]"
---

# reddit-stats

What worked, from the user's own profile, read the way they would read it.

What the user typed after `/reddit-stats`: `$ARGUMENTS`

**You click Post.** This skill only reads the user's own profile pages.

## The tools

```bash
python3 "${CLAUDE_SKILL_DIR}/stats.py" build [--days N]
python3 "${CLAUDE_SKILL_DIR}/../reddit-setup/capture.py" start|add FILE|halt NOTE|budget
python3 "${CLAUDE_SKILL_DIR}/../reddit-setup/log.py" add|ratio
```

Read `${CLAUDE_SKILL_DIR}/../reddit-setup/BROWSER.md` before opening any page,
and use the `profile` shape in `${CLAUDE_SKILL_DIR}/../reddit-setup/CAPTURES.md`.

## Step 1: read the profile pages

`profile.json` needs the username (set it with `/reddit-setup`). Then `capture.py start` and open, as the
budget allows:

1. `https://www.reddit.com/user/<name>/comments/`
2. `https://www.reddit.com/user/<name>/submitted/`

Scroll a screen or two for the period asked about (a week by default). For each
item, copy the link, sub, type, title or first lines, score, reply count and
age, and set `removed` to true where Reddit shows its removed label on the item.
Add one `profile` capture per page.

Only the user's own profile. Never open another person's profile for this.

## Step 2: build and read it

Run `stats.py build`, with `--days 7` for a week or `--days 30` for a month
if the user asked for a period, and show `reddit/stats.md` in short:

- totals: items, median score, replies, removed;
- by sub, by kind (comment or post), and help against promo (from the log);
- the best and weakest few, with links;
- removed items, and comments or posts logged with their own link that are
  not on the pages read (open those to check; they may be removed or just not
  loaded).

Then three or four plain observations, each tied to numbers in the report: which
sub answers best, whether posts or comments did better, whether promo did
worse than help. With fewer than 10 items, say it is too early to read much
into it.

Do not invent causes. "This one did well" is a fact; "because of the timing"
is a guess, and should be marked as one.

## Step 3: feed back

If something should change (drop a sub where replies get removed, slow down
promo), say what and run `/reddit-plan` again. Removals in a sub are a reason to
read its rules again with `/reddit-subs`, not to try harder there.
