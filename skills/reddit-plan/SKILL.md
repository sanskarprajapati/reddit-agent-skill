---
name: reddit-plan
description: >-
  The warm-up and the week. Works out the user's phase (new, building, established)
  from account age, karma and their log, with a cap per day and what each phase
  allows: no links and no product at first. Plans the next seven days across the
  subs whose rules are ok, keeps promotion at 1 in 10 or less, and writes today's
  queue with an optional calendar file for reminders. Use when the user says
  "warm up my account", "plan my week", "what should I do on reddit today",
  "how many can I post", or "make me a schedule".
argument-hint: "[week | today]"
---

# reddit-plan

How much, where, and when. It never posts on a timer: the queue is a list and
the calendar file holds reminders for the user.

What the user typed after `/reddit-plan`: `$ARGUMENTS`

**You click Post.** This skill writes plans. It never opens Reddit.

## The tools

```bash
python3 "${CLAUDE_SKILL_DIR}/plan.py" phase|left|week
python3 "${CLAUDE_SKILL_DIR}/drafts.py" list|today
python3 "${CLAUDE_SKILL_DIR}/../reddit-setup/log.py" add|today|ratio
```

## Step 1: catch up the log

Ask whether the user posted anything on Reddit by hand since the last session
that is not in `reddit/log.jsonl` (`log.py today` and `drafts.py list` show
what is there). Log each one with `log.py add`, marking it `help` or `promo`
honestly: a reply that names or links their product is promo. The caps and the
ratio are only as good as the log.

## Step 2: the phase

Run `plan.py phase` and explain it in a few lines:

| phase | when | per day | allowed |
| --- | --- | --- | --- |
| new | warm-up days 0 to 6 | 3 comments, no posts | no links, no product |
| building | days 7 to 27 | 5 comments, 1 post | links to other people's sources only, no product |
| established | day 28 on | 8 comments, 2 posts | product only where the rules allow, at most 1 in 10 |

Warm-up days are the account's age while it is young. An old account with under
100 karma warms up from its first logged post. Negative karma holds it at new.
The user can lower any cap in `profile.json`, never raise one. The hard ceiling
is 10 drafts a day.

If the user asks to go faster, use more accounts, or time posts to dodge
filters, say no and why in a line. The caps are the plan.

## Step 3: the week

Run `plan.py week`. It writes `reddit/plan.md`: seven days, the phase each day,
the caps, and up to three subs a day, rotating through the ranked subs whose
rules verdict is `ok`. Show it. If no sub is `ok` yet, send the user to
`/reddit-subs`.

Add your own notes under the table where they help: which sub suits a first
post, what kind of thread to look for, what to avoid in a sub's rules. Never
raise a number the tool gave.

## Step 4: today's queue

After `/reddit-draft` has made drafts, run `drafts.py today`. It writes
`reddit/queue.md` (what to post, roughly when, one at a time) and
`reddit/queue.ics`, a calendar file with one 15-minute reminder per draft. The
user can import it into their own calendar. Nothing is posted by a timer; a
reminder only says it is time to read the draft and decide.

Next: `/reddit-threads` to find where to help today.
