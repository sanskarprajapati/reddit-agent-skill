# The Reddit skill

Seven Claude skills that help you use Reddit well: find the communities where you
can be useful, read their rules, find threads worth answering, and draft replies
that sound like you. Free and MIT licensed. Nothing to sign up for, no API key.

Claude works in your own Chrome, where you are already logged in. It searches,
reads, and can type a draft into the reply box for you. Then it stops.

**You click Post.** It never posts, comments, votes, joins, follows or sends a
message. It never logs in, never uses a second account, and never does anything
meant to get past Reddit's spam filters or a community's rules. A subreddit that
bans AI-written content gets no drafts.

## Install

Paste this into Claude:

```
https://github.com/sanskarprajapati/reddit-agent-skill

install skill
```

Or as a plugin, from your shell:

```
claude plugin install reddit-agent-skill --marketplace sanskarprajapati/reddit-agent-skill
```

Or in two steps inside Claude Code:

```
/plugin marketplace add sanskarprajapati/reddit-agent-skill
/plugin install reddit-agent-skill@reddit-agent-skill
```

Installed as a plugin, the skills show up as `/reddit-agent-skill:reddit-setup`
and so on. Copy the folders instead if you want plain `/reddit-setup`:

```bash
git clone https://github.com/sanskarprajapati/reddit-agent-skill.git
cp -r reddit-agent-skill/skills/reddit-* ~/.claude/skills/
```

Install all seven together: the later skills use the tools in the earlier ones.

You need Claude Code on your own computer, Python 3.8 or newer (nothing to pip
install), and the Claude in Chrome extension so Claude can read Reddit in your
browser. Without the extension everything still works: you open the pages and
paste what you see.

### Optional: the browser guard

A small hook that stops the browser actions this pack never takes, as a second
line behind the skills' own rules. Add to `.claude/settings.json` in your project.
The path below is for the copy install; for a plugin install, point it at
`skills/reddit-draft/guard.py` inside the plugin's folder under `~/.claude/plugins/`.

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "mcp__claude-in-chrome__.*|mcp__playwright__.*",
        "hooks": [{"type": "command", "command": "python3 ~/.claude/skills/reddit-draft/guard.py"}]
      }
    ]
  }
}
```

It always denies page scripts, typing with submit on, Ctrl or Cmd plus Enter,
clicks on controls named Comment, Post, Save, Submit, Send, a vote arrow, Join,
Follow, Award, Share, Report, Hide or Block, and Reddit's messages, chat, mod
mail, notifications, settings and login pages. During a handoff, once the draft
is typed, it denies every click and every Enter until you say done or skip. That
matters because a click given as a page reference or screen position carries no
label the hook could read. In a project where it is set up, it applies to all
browser use through Claude there, not only Reddit.

## First run

1. Open Claude Code in any project folder and type `/reddit-setup`. Say what you
   know about and care about. Paste five or more comments you wrote yourself, or
   let it read your own profile. It builds your voice file from them.
2. `/reddit-subs` finds the communities and reads their rules.
3. `/reddit-plan` tells you your phase and your caps, and plans the week.
4. `/reddit-threads`, then `/reddit-draft` on the thread you pick.

## The seven

| command | job | what it does |
| --- | --- | --- |
| `/reddit-setup` | Intake and voice | Your topics, what you know first-hand, account age and karma, your product if any. A voice file built from comments you really wrote: every habit in it has to appear word for word in one of them. |
| `/reddit-subs` | Subs and their rules | Searches Reddit for communities, opens each for members and weekly activity, ranks them, and reads every rule: AI content, self-promotion, links, account minimums, flair. A sub that bans AI-written content is skipped. |
| `/reddit-plan` | Warm-up, week and queue | Your phase from account age, karma and your log, the cap per day, the week across your OK subs, and today's queue with a calendar file for reminders. Promotion stays at 1 in 10 or less. |
| `/reddit-threads` | Thread finder | Reads your home feed, the New tab of your subs and Reddit search. Ranks threads by relevance, freshness, room to help and whether it is a real question. Leaves out locked, archived, your own and bot threads. |
| `/reddit-draft` | Drafter and handoff | A reply in your voice that answers the question, within the rules, the phase and the cap. Checked before you see it. On your word, typed into the reply box in Chrome. You read it, edit it, and click Post, or not. |
| `/reddit-check` | Removal check | "Would this get removed?" Fixed points for rule fit, self-promotion, links, account minimums, flair, length, shouting and AI tells, each with a reason. Then a cleaned version in your voice, checked again. |
| `/reddit-stats` | How it went | Your own profile pages: score and replies by sub, by kind, help against promo, and anything Reddit marks as removed. |

## How to use it

```
setup -> subs -> plan -> threads -> draft (the check runs inside) -> you post -> stats -> plan
```

The warm-up, with the caps the tools enforce:

| phase | when | per day | allowed |
| --- | --- | --- | --- |
| new | days 0 to 6 | 3 comments, no posts | no links, no product |
| building | days 7 to 27 | 5 comments, 1 post | links to other people's sources only |
| established | day 28 on | 8 comments, 2 posts | your product only where the rules allow, at most 1 in 10 |

Days count from the account's creation. You can lower any cap in
`reddit/profile.json`; nothing goes above 10 a day. An account 90 days old or
more with under 100 karma warms up from your first post logged in the last 60
days, as if it were new.

## The tools

Plain Python, no dependencies, and none of them touch the network. Claude reads
the pages; the tools check what it wrote down, and do the counting and scoring,
so no number comes from a model's memory.

| tool | what it does |
| --- | --- |
| `reddit-setup/capture.py` | Checks each page Claude read (a "capture") against a fixed shape, turns "1.2k" and "5 hr. ago" into numbers and dates, and keeps a page budget: 30 a run by default (60 at most), 120 in any 24 hours. A captcha or warning halts everything until a day passes or you say it is fine. |
| `reddit-setup/profile.py` | Your profile: one account, caps that only go down. |
| `reddit-setup/voice.py` | Your samples and voice file. Refuses a quirk it cannot find in your own words. |
| `reddit-setup/log.py` | What you posted by hand, help or promo. Caps and the ratio read it. |
| `reddit-subs/rules.py` | Reads rules sentence by sentence. A sentence that names AI, says no and is about writing is a ban. Unclear rules wait for your confirm, which lapses when the rules change. Claude's own flags can only make a reading stricter. |
| `reddit-subs/subs.py` | Ranks subs: fit 40, activity 35, size 25, favouring the middle. |
| `reddit-plan/plan.py` | Phase, caps, the promo ratio and the week. |
| `reddit-plan/drafts.py` | Registers each draft against the cap and gates the handoff: rules, risk, phase and ratio checked again on the text as it is, one at a time. Writes the queue and the calendar file. |
| `reddit-threads/threads.py` | Ranks threads: relevance 40, freshness 25, room to help 20, a real question 15. |
| `reddit-check/check.py` | The removal-risk score and the hard stops. |
| `reddit-check/signals.py` | Finds your product's name and links however they are spelled, and self-promotion however it is worded. |
| `reddit-check/tells.py` | The AI tells: em dashes, stock openers and closers, words AI leans on, "not X, it's Y", headings, bold, tidy lists, emoji, and your own never list. |
| `reddit-stats/stats.py` | Your profile, summed. |
| `reddit-draft/guard.py` | The optional browser hook. |

## Safeguards

- **Posting.** There is no send, vote or message code anywhere, and a test fails
  if a tool ever imports a network library or names a login.
- **Rules.** No draft is registered for a sub whose rules are not read,
  are over 30 days old, or are unclear about AI and not confirmed by you. A ban
  on AI-written content is final.
- **Voice.** Drafts follow habits you really have, proven by your own samples. The pack refuses to add typos or flaws to hide that AI
  helped, and refuses to make anything "undetectable".
- **Caps.** Per phase, per day, a ceiling of 10, and promotion at 1 in 10
  or less over 30 days. One handoff at a time.
- **Page text.** Text on Reddit is written by strangers. Anything in it that
  reads like an instruction is ignored.

## Fine print

**Read Reddit's rules and each community's rules yourself.** The pack reads them
with fixed word rules and Claude's own read. It can miss things. It never says a
draft is safe, only lower or higher risk.

**It reads what you can see, slowly.** Pages are read in your own browser, a few
dozen per run, with a daily limit. No API, no scraping service, no archive.

**Keep your `reddit/` folder private.** It holds other people's usernames and
posts as Claude read them. Add `reddit/` to your project's `.gitignore` and delete
what you no longer need.

**Check what you post.** Drafts only claim what your voice
file says you know first-hand, and mark anything else for you to check. You are
the one posting it.

Not affiliated with Reddit.

## Files

```
skills/reddit-setup/     SKILL.md, BROWSER.md, CAPTURES.md, capture.py, parsing.py, profile.py, voice.py, log.py, store.py, mdsafe.py
skills/reddit-subs/      SKILL.md, subs.py, rules.py
skills/reddit-plan/      SKILL.md, plan.py, drafts.py
skills/reddit-threads/   SKILL.md, threads.py
skills/reddit-draft/     SKILL.md, guard.py
skills/reddit-check/     SKILL.md, check.py, signals.py, tells.py
skills/reddit-stats/     SKILL.md, stats.py
tests/                   python3 -m unittest discover -s tests
```

## License

MIT. See `LICENSE`.
