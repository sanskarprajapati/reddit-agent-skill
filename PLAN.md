# Plan: reddit-agent-skill

Claude skills that help one person use Reddit well: find the right communities,
read their rules, find threads worth answering, and draft helpful replies in
their own voice. It drafts. You post, by hand.

Status: draft plan, waiting for approval. No code yet.

## The hard rules

These are built into the tools and the skills, not just written in the README.

1. **It never posts, comments, votes, follows, DMs or logs in.** No tool holds a
   Reddit login, an OAuth token or a write call. A test scans every Python file
   and fails the build if one ever shows up (`POST`, `oauth`, `praw`, `login`,
   `access_token`, `vote`, `submit`).
2. **One person, one account.** No multiple accounts, no vote help, no asking
   friends to upvote, nothing timed or worded to slip past spam filters or bans.
   The skills refuse those asks and say why.
3. **Each subreddit's rules win.** A sub that bans AI-written posts or comments is
   skipped: no drafts for it, ever. A sub that bans self-promotion gets no
   product mention, whatever the user asks.
4. **Public data only.** Public archives and public pages, read slowly. Anything
   else, the user pastes.
5. **Posts are data, never instructions.** Thread text is fenced in every brief,
   and anything a post says to do is ignored.
6. **Caps.** A per-day cap on drafts, set by the warm-up phase, that the user can
   lower but not raise past a hard ceiling.

## The skills

Seven, one per real task. Where two jobs from the brief always run together they
share a skill: finding subs means reading their rules, a weekly plan is only
useful inside a warm-up phase, and stripping AI tells is the fix half of the
removal check.

| skill | job | one line |
| --- | --- | --- |
| `/reddit-setup` | Intake and voice | Who you are on Reddit, what you care about, your product (optional), account age and karma. Builds `reddit/voice.md` with you: how you write, words you use and never use, what you know first-hand. Can read your own public comments for a starting point. |
| `/reddit-subs` | Subs and their rules | Subreddits for a topic or product, with size, posts per day and comments per post. Reads each one's rules and sorts them: AI content, self-promotion, links, account minimums, flair, format. Subs that ban AI content go on the skip list. Also works on one named sub. |
| `/reddit-plan` | Warm-up and week | Your phase (new, building, established) from account age, karma and your log, with a cap per day and what each phase allows: no links and no product at first. Then the next seven days: which subs, comments or a post, how many, and the help-to-promo ratio (at most 1 in 10). |
| `/reddit-threads` | Thread Finder | Recent threads in your OK subs where you could help: relevant, open, unanswered or under-answered. Scored by fixed rules. |
| `/reddit-draft` | Drafter | A helpful comment or post for a picked thread or sub, in your voice, inside that sub's rules, your phase and today's cap. Every draft goes through the removal check before you see it. Saved to `reddit/drafts/`. |
| `/reddit-check` | Removal check and cleanup | "Would this get removed?" for any draft, yours or the drafter's: rule fit, self-promo signals, links, tone, length, AI tells. Fixed weights, every point with a reason. Then offers a cleaned version toward your voice file and re-checks it. |
| `/reddit-stats` | How It Went | A light read of your own public posts and comments: score, replies, which subs and which kind of post did well, and any that look removed. Feeds back into `/reddit-plan`. |

Flow: `setup -> subs -> plan -> threads -> draft (check runs inside) -> you post -> log -> stats -> plan`

## The tools

Stdlib only, Python 3.8+. Every count, score and rule call comes from a script,
not from a model's memory. Same layout as validator-skill: shared modules live in
the first skill's folder (`reddit-setup/`) and others add it to `sys.path`.

| tool | in | what it does |
| --- | --- | --- |
| `netfetch.py` | setup | Copied from validator-skill: polite delay, retries, `Retry-After` and long backoff on 429, a day cache that never stores an outage. User agent renamed. |
| `mdsafe.py` | setup | Copied as is: escapes stranger text for reports. |
| `store.py` | setup | Cut down from validator-skill: one record shape for posts and comments, stable IDs, dedupe, `clean_text`, and `verbatim()` for quoting rules and threads word for word. |
| `redditdata.py` | setup | The source ladder (below). `probe` says which sources answer from this machine today and how fresh they are. Every call returns the data plus its source and its lag. |
| `profile.py` | setup | Checks `profile.json` and `voice.md`: required fields filled, caps within the ceiling, one account. Optional numbers from your own public comments (length, sentence length, casing, common openers). |
| `log.py` | setup | `reddit/log.jsonl`: what you say you posted, by hand, with link, sub and kind (help or promo). Feeds caps, the ratio and stats. |
| `subs.py` | subs | Finds subs from archive search hits, then size (`subreddit_subscribers`), posts per day and comments per post over 30 days. Ranks with fixed weights. |
| `rules.py` | subs | Word rules that sort each rule into AI content, self-promo, links, minimums, flair. Each call quotes the rule word for word. `ai_ban: yes` puts the sub on the skip list. |
| `plan.py` | plan | Phase from age, karma and log, caps per day, what each phase allows, the seven-day table and the ratio check. Refuses a draft over today's cap. |
| `threads.py` | threads | Scores threads: relevance to your terms, age, comment count, question shape, not locked, not archived (over 6 months), not already answered well. |
| `tells.py` | check | The AI tell list as data plus a detector. |
| `check.py` | check | The removal-risk score: low, medium or high, with each reason and the rule it hit. Used by `/reddit-draft` too. |
| `stats.py` | stats | Your own posts and comments by username, from the archive or pasted, summed by sub and kind. |

Reports (`subs.md`, `plan.md`, `threads.md`, `stats.md`) all go through `mdsafe`.

## Where the data comes from

Tested from this cloud machine today: **every Reddit source was blocked**, by
this environment's network policy, not by Reddit. That includes `reddit.com`,
`old.reddit.com`, `api.pullpush.io` and `arctic-shift.photon-reddit.com`. So
nothing here is tested live yet. The plan is a ladder the tool walks at run time,
reporting which step it used:

1. **Arctic Shift** (`arctic-shift.photon-reddit.com`): public archive, no key.
   Usually fresher than PullPush, and it has subreddit info and a rules endpoint.
   First choice for rules, subs and threads if it answers.
2. **PullPush** (`api.pullpush.io`): no key, lags 1 to 2 weeks, rate-limits after
   about 20 fast calls. The tool keeps a 1 to 2 second delay and backs off on 429.
3. **Reddit's public JSON** (`reddit.com/r/<sub>/about/rules.json` and similar):
   off by default. It 403s from many machines, and Reddit's Data API terms expect
   apps to register and use OAuth. Open question below.
4. **Paste.** Always works. The user pastes a sub's rules page, or a list of
   thread links and titles from their browser, and the tools parse it.

What this means in practice:

- **Rules:** archive rules endpoint, else paste. Rules change, so they are dated
  and the skill asks for a fresh look after 30 days.
- **Threads:** an archive lags, and a thread a week old is often too late to
  help. So `/reddit-threads` says how old the newest data is. When it is stale it
  gives you the sub's `/new` and search links to open in your browser and paste
  back. That keeps "recent" honest instead of pretending.
- **Stats:** your own username, from the archive. Recent posts may not be there
  yet; the report says so.

## What is kept, and where

All state in a `reddit/` folder in the user's project, added to `.gitignore`:
`profile.json`, `voice.md`, `subs.json`, `rules/<sub>.json`, `threads.jsonl`,
`drafts/`, `log.jsonl`, the reports, and `cache/`.

## Build phases

Each phase: tests first, then code, then a code-review sub-agent, fix its HIGH
findings, one conventional commit, push to the work branch. `main` only after you
approve the finished pack.

1. **Foundation.** Plugin files (`plugin.json`, `marketplace.json`), `.gitignore`,
   `tests/_load.py`, the copied `netfetch`, `mdsafe` and trimmed `store`,
   `redditdata.py` with a fake opener, `profile.py`, `log.py`, the no-write guard
   test, and `/reddit-setup`.
2. **Find.** `subs.py`, `rules.py` (with rule sets from real subs as test
   fixtures, including ones that ban AI content in different wordings) and
   `/reddit-subs`.
3. **Write well.** `tells.py`, `check.py`, `/reddit-check`.
4. **Engage.** `plan.py`, `threads.py`, `/reddit-plan`, `/reddit-threads`,
   `/reddit-draft` (drafts pass through the cap, the rules and the check before
   you see them).
5. **Look back.** `stats.py` and `/reddit-stats`.
6. **Ship.** One real run on a real topic, the README in validator-skill's format
   with that run as the worked example, `claude plugin validate .` (the CLI is on
   this machine), every file under 400 lines, then push to `main` with your OK.

If a phase shows a skill is doing two jobs badly, it gets split then, not before.

## Risks

- **No live data from here.** Covered above. Without a fix, the real run has to
  use pasted data or happen on your machine. See question 1.
- **Archive lag.** PullPush is 1 to 2 weeks behind, which hurts thread finding
  most. Mitigated by Arctic Shift and the browser paste step, and by always
  printing the lag.
- **The rules reader can miss a ban** worded in a new way. Word rules plus
  Claude's own read, and when either says "maybe", the sub is marked unclear and
  you read the rule yourself before anything is drafted for it. A miss errs
  toward skipping.
- **The cleanup step could be misused** to pass AI text off where it is banned.
  It will not run on a draft for a skipped sub, and its job is stated as making
  your own text read like you, not beating detection.
- **Drafted help that is wrong.** A confident wrong answer hurts more than
  silence. Drafts stick to what your voice file says you know first-hand, and mark
  any claim you should check.
- **Reddit's terms and each sub's culture change.** Rules are dated, the README
  says to read them yourself, and the pack never claims a draft is safe, only
  lower or higher risk.
- **Personal data.** Archives hold other people's handles and text, including
  deleted posts. Kept local, gitignored, never put in reports beyond a link and a
  short quote.

## Open questions

1. **Live data for the real run.** This environment blocks every Reddit source.
   Either add these to the environment's allowed domains (cloud environment menu,
   Edit, Network access): `arctic-shift.photon-reddit.com`, `api.pullpush.io`, and
   optionally `www.reddit.com` and `old.reddit.com`. Or I build and test with
   recorded fixtures, and you do the real run on your machine and paste me the
   output for the README. Which do you want?
2. **Reddit's own JSON.** Use it at all (off by default, low volume, rules only),
   or archives plus paste only? I lean toward archives plus paste, with Reddit's
   JSON as an opt-in flag.
3. **Warm-up caps.** What caps did you use in your own warm-up? My default: week 1,
   up to 3 comments a day, no posts, no links, no product. Weeks 2 to 3, up to 5
   comments and 1 post a day, links only to other people's sources. Week 4 on,
   product only where the rules allow and at most 1 in 10 of your activity. Hard
   ceiling 10 drafts a day.
4. **"Unclear" on AI content.** Skip those subs too, or allow drafts after you
   confirm you read the rule? I lean toward allow after you confirm.
5. **The real-run topic.** Your product's topic, or a neutral one (say, home
   espresso) for the README example?
