# Plan: reddit-agent-skill

Claude skills that help one person use Reddit well: find the right communities,
read their rules, find threads worth answering, and draft helpful replies in
their own voice. It drafts. You post, by hand.

Status: draft plan, waiting for approval. No code yet.

## The hard rules

These are built into the tools and the skills, not just written in the README.

1. **It never submits anything. You click Post.** It never posts, comments,
   votes, follows, DMs or logs in on its own. In your browser it may open a
   thread and put a draft in the reply box, then it stops (see "Browser
   handoff"). No Python tool holds a Reddit login, an OAuth token or a write
   call. A test scans every Python file and fails the build if one ever shows up
   (`POST`, `oauth`, `praw`, `login`, `access_token`, `vote`, `submit`).
2. **One person, one account.** No multiple accounts, no vote help, no asking
   friends to upvote, nothing timed or worded to slip past spam filters or bans,
   and no flaws added to text to hide that AI helped write it. The skills refuse
   those asks and say why.
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
| `/reddit-setup` | Intake and voice | Who you are on Reddit, what you care about, your product (optional), account age and karma. Builds `reddit/voice.md` from your own writing: casing, sentence length, slang, how you open a reply, typos you really make, words you never use, what you know first-hand. You paste at least five of your own comments, or it reads your public ones. |
| `/reddit-subs` | Subs and their rules | Subreddits for a topic or product, with size, posts per day and comments per post. Reads each one's rules and sorts them: AI content, self-promotion, links, account minimums, flair, format. Subs that ban AI content go on the skip list. Also works on one named sub. |
| `/reddit-plan` | Warm-up, week and queue | Your phase (new, building, established) from account age, karma and your log, with a cap per day and what each phase allows: no links and no product at first. Then the next seven days: which subs, comments or a post, how many, and the help-to-promo ratio (at most 1 in 10). Then today's queue: these threads, these drafts, a rough time for each, and an optional calendar file for reminders. |
| `/reddit-threads` | Thread Finder | Recent threads in your OK subs where you could help: relevant, open, unanswered or under-answered. Scored by fixed rules. |
| `/reddit-draft` | Drafter and handoff | A helpful comment or post for a picked thread or sub, in your voice, inside that sub's rules, your phase and today's cap. Every draft goes through the removal check before you see it. Saved to `reddit/drafts/`. When you say so, opens the thread in your browser and fills the reply box, then stops for you to edit and post. |
| `/reddit-check` | Removal check and cleanup | "Would this get removed?" for any draft, yours or the drafter's: rule fit, self-promo signals, links, tone, length, AI tells. Fixed weights, every point with a reason. Then offers a cleaned version toward your voice file and re-checks it. |
| `/reddit-stats` | How It Went | A light read of your own public posts and comments: score, replies, which subs and which kind of post did well, and any that look removed. Feeds back into `/reddit-plan`. |

Flow: `setup -> subs -> plan -> threads -> draft (check runs inside) -> handoff -> you post -> log -> stats -> plan`

## Browser handoff (local Claude Code only)

The busywork goes to the browser; the decision stays with you.

- **Runs on your machine.** Claude Code on your computer, with a browser tool
  such as Claude in Chrome or a Playwright MCP server, in your own browser where
  you are already logged in. The pack never logs in or handles a password.
- **What it may do:** open the thread or the sub's submit page, click into the
  reply box (or title and body fields), type the approved draft, pick a flair
  the rules require. Then it stops and says "ready for you to read and post".
- **What it must never do:** click Comment, Post, Save, Reply, vote arrows,
  Join, Follow, Chat or Message; open DMs; change settings; touch any other
  account; retry if Reddit shows a captcha, a rate limit or a warning (it stops
  and tells you).
- **One at a time.** It fills one draft, waits for you to say "done" or "skip",
  logs that to `reddit/log.jsonl`, and only then opens the next. No batches, no
  timers, no pacing tricks.
- **Gates before it opens anything:** the sub is not on the skip list, the draft
  passed `/reddit-check` at low or medium risk, and today's cap is not used up.
- **Enforced how:** these steps are written into `/reddit-draft`, and a test
  checks the skill text still contains every "never" line. If your setup
  supports hooks, an optional `PreToolUse` hook blocks browser clicks on those
  buttons outright.

## Reminders, not a scheduler

Nothing posts on a timer. `/reddit-plan` writes `reddit/queue.md` for the day
and, if you want, `reddit/queue.ics`, a calendar file with one reminder per item
that you import into your own calendar. You post when you are there.

## Your real style, not a fake one

Drafts match how you actually write, including casual habits: lowercase, short
lines, slang, the typos you really make. Every quirk in `voice.md` must be backed
by one of your own sample comments (checked word for word). The pack does not add
flaws you do not have, and subs that ban AI content stay skipped.

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
| `profile.py` | setup | Checks `profile.json`: required fields filled, caps within the ceiling, one account. |
| `voice.py` | setup | Measures your sample comments (length, sentence length, casing, openers, slang, repeated typos) and checks every quirk in `voice.md` appears word for word in a sample. |
| `log.py` | setup | `reddit/log.jsonl`: what you say you posted, by hand, with link, sub and kind (help or promo). Feeds caps, the ratio and stats. |
| `subs.py` | subs | Finds subs from archive search hits, then size (`subreddit_subscribers`), posts per day and comments per post over 30 days. Ranks with fixed weights. |
| `rules.py` | subs | Word rules that sort each rule into AI content, self-promo, links, minimums, flair. Each call quotes the rule word for word. `ai_ban: yes` puts the sub on the skip list. |
| `plan.py` | plan | Phase from age, karma and log, caps per day, what each phase allows, the seven-day table and the ratio check. Refuses a draft over today's cap. |
| `queue.py` | plan | Today's queue as `queue.md`, and `queue.ics` (plain iCalendar text, stdlib) for reminders. Also `gate`: says yes or no to a browser handoff (skip list, check result, cap). |
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
   `redditdata.py` with a fake opener, `profile.py`, `voice.py`, `log.py`, the
   no-write guard test, and `/reddit-setup`.
2. **Find.** `subs.py`, `rules.py` (with rule sets from real subs as test
   fixtures, including ones that ban AI content in different wordings) and
   `/reddit-subs`.
3. **Write well.** `tells.py`, `check.py`, `/reddit-check`.
4. **Engage.** `plan.py`, `queue.py`, `threads.py`, `/reddit-plan`,
   `/reddit-threads`, `/reddit-draft` (drafts pass through the cap, the rules and
   the check before you see them), the browser handoff steps, the test that
   guards the handoff's "never" lines, and the optional click-blocking hook.
5. **Look back.** `stats.py` and `/reddit-stats`.
6. **Ship.** `claude plugin validate .`, every file under 400 lines, and a
   README in validator-skill's format. Then the real run, on your machine (the
   cloud machine cannot reach Reddit): you run the skills on a real topic,
   including one browser handoff, and paste me the outputs. I write the worked
   example from them, then push to `main` with your OK.

If a phase shows a skill is doing two jobs badly, it gets split then, not before.

## Risks

- **No live data from here.** Covered above. I build and test against recorded
  fixtures shaped like the real archive replies; the live check happens in your
  local run. If the archives answer differently there, I fix the parsers then.
- **The browser handoff can't be unit tested.** Browser tools run inside Claude,
  not in Python. The gate (`queue.py gate`) is tested, the "never" lines are
  guarded by a test, and the optional hook blocks the risky clicks. The first
  handoff in your real run is the live test.
- **A model can misclick.** If the browser tool hits Post by mistake, a comment
  goes up. The hook is the backstop, and the handoff types into the box only
  after the page has loaded and the box is found, never by guessing.
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

1. **Browser tool.** Claude in Chrome (your everyday Chrome, already logged in),
   or a Playwright MCP server (a separate browser you log into once)? I lean
   toward Claude in Chrome, and the skill will work with either.
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
