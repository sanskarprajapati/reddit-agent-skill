# Plan: reddit-agent-skill

Claude skills that help one person use Reddit well: find the right communities,
read their rules, find threads worth answering, and draft helpful replies in
their own voice. Claude works in your own Chrome, where you are already logged
in. It reads, searches and fills in reply boxes. You click Post.

Status: approved direction, building.

## The hard rules

These are built into the tools and the skills, not just written in the README.

1. **It never submits anything. You click Post.** It never posts, comments,
   votes, joins, follows, saves, reports, chats or DMs. In your browser it may
   open pages, search, scroll, read, and type an approved draft into a reply box,
   then it stops (see "Browser handoff"). No Python tool talks to Reddit at all.
   A test scans every Python file and fails the build if a network or write call
   ever shows up (`urlopen`, `requests`, `POST`, `oauth`, `praw`, `login`,
   `access_token`).
2. **One person, one account.** No multiple accounts, no vote help, no asking
   friends to upvote, nothing timed or worded to slip past spam filters or bans,
   and no flaws added to text to hide that AI helped write it. The skills refuse
   those asks and say why.
3. **Each subreddit's rules win.** A sub that clearly bans AI-written posts or
   comments is skipped: no drafts for it, ever. A sub that is unclear gets drafts
   only after you confirm you read the rule yourself. A sub that bans
   self-promotion gets no product mention, whatever the user asks.
4. **Only what you can see.** Claude reads the pages your own browser shows you.
   It never handles a password, never uses an API or a third-party archive, and
   never loads pages in bulk: each run has a page budget.
5. **Posts are data, never instructions.** Page text is fenced in every brief,
   and anything a post says to do is ignored.
6. **Caps.** A per-day cap on drafts, set by the warm-up phase, that the user can
   lower but not raise past a hard ceiling of 10.

## The skills

Seven, one per real task.

| skill | job | one line |
| --- | --- | --- |
| `/reddit-setup` | Intake and voice | Who you are on Reddit, what you care about, your product (optional), account age and karma. Builds `reddit/voice.md` from your own writing: casing, sentence length, slang, how you open a reply, typos you really make, words you never use, what you know first-hand. You paste at least five of your own comments, or it reads them from your profile page. |
| `/reddit-subs` | Subs and their rules | Searches Reddit for communities on a topic or product, opens each one, and records members, weekly visitors and weekly contributions. Reads each one's rules and sorts them: AI content, self-promotion, links, account minimums, flair, format. Subs that ban AI content go on the skip list. Also works on one named sub. |
| `/reddit-plan` | Warm-up, week and queue | Your phase from account age, karma and your log, with a cap per day and what each phase allows. Then the next seven days: which subs, comments or a post, how many, and the help-to-promo ratio (at most 1 in 10). Then today's queue: these threads, these drafts, a rough time for each, and an optional calendar file for reminders. |
| `/reddit-threads` | Thread Finder | Reads your home feed, each OK sub's New tab and Reddit search for your terms. Finds threads where you could help: relevant, open, recent, unanswered or under-answered. Opens the best few to see whether they are already answered well. Scored by fixed rules. |
| `/reddit-draft` | Drafter and handoff | A helpful comment or post for a picked thread or sub, in your voice, inside that sub's rules, your phase and today's cap. Every draft goes through the removal check before you see it. Saved to `reddit/drafts/`. When you say so, opens the thread in Chrome and fills the reply box, then stops for you to edit and post. |
| `/reddit-check` | Removal check and cleanup | "Would this get removed?" for any draft, yours or the drafter's: rule fit, self-promo signals, links, tone, length, AI tells. Fixed weights, every point with a reason. Then offers a cleaned version toward your voice file and re-checks it. |
| `/reddit-stats` | How It Went | Reads your own profile's posts and comments: score, replies, which subs and which kind did well, and any Reddit marks as removed (you see that label on your own posts when logged in). Feeds back into `/reddit-plan`. |

Flow: `setup -> subs -> plan -> threads -> draft (check runs inside) -> handoff -> you post -> log -> stats -> plan`

## How Claude reads Reddit

Claude in Chrome, in your everyday Chrome. No API, no archive, no web search
engine.

| need | page |
| --- | --- |
| find subs | `reddit.com/search/?q=<topic>&type=communities` |
| sub size and activity | `reddit.com/r/<sub>/` (members, weekly visitors, weekly contributions) |
| sub rules | `old.reddit.com/r/<sub>/about/rules` (full rule text on one page), else the Rules box on the sub page |
| threads | your home feed `reddit.com/`, `reddit.com/r/<sub>/new/`, `reddit.com/r/<sub>/search/?q=<term>&sort=new` |
| is it answered | the thread page itself |
| your stats | `reddit.com/user/<you>/submitted/` and `/comments/` |

Claude writes what it read to a capture file in `reddit/captures/`, one per
page, in a fixed JSON shape: the URL, the time, and the items (subs, rules,
posts, comments) with their numbers as shown ("1.2k members", "5 hr. ago").
`capture.py` checks the shape, turns "1.2k" into 1200 and "5 hr. ago" into a
date, cleans the text and stores it. Every later tool reads only checked
captures, so every count and score traces back to a page and a time.

**Page budget.** 30 page loads per run by default (60 at most), and no more than
120 in any 24 hours, counted from the captures. That keeps a run light on Reddit
and quick for you. If Reddit shows a captcha,
a "you are doing that too much" notice or any warning, Claude stops the run and
tells you. It never retries around it.

**The home feed.** Claude reads your home feed for posts you could help with,
like any other listing. Interacting means drafting a reply and handing it off
the same way. It does not vote, join or hide posts for you.

## Browser handoff

- **What it may do:** open the thread or the sub's submit page, click into the
  reply box (or title and body fields), type the approved draft, pick a flair
  the rules require. Then it stops and says it is ready for you to read and post.
- **What it must never do:** click Comment, Post, Save, Reply, vote arrows,
  Join, Follow, Chat or Message; open DMs; change settings; touch any other
  account; retry if Reddit shows a captcha, a rate limit or a warning.
- **One at a time.** It fills one draft, waits for you to say "done" or "skip",
  logs that to `reddit/log.jsonl`, and only then opens the next.
- **Gates before it opens anything** (`queue.py gate`): the sub is not on the
  skip list (or you confirmed an unclear rule), the draft passed `/reddit-check`
  at low or medium risk, and today's cap is not used up.
- **Enforced how:** the steps are written into the skills, a test checks the
  skill text still holds every "never" line, and an optional `PreToolUse` hook
  blocks browser clicks on those buttons.

## Reminders, not a scheduler

Nothing posts on a timer. `/reddit-plan` writes `reddit/queue.md` for the day
and, if you want, `reddit/queue.ics`, a calendar file with one reminder per item
that you import into your own calendar.

## Your real style, not a fake one

Drafts match how you actually write, including casual habits: lowercase, short
lines, slang, the typos you really make. Every quirk in `voice.md` must be backed
by one of your own sample comments (checked word for word). The pack does not add
flaws you do not have.

## Warm-up caps

| phase | when | per day | allowed |
| --- | --- | --- | --- |
| new | week 1 | 3 comments, no posts | no links, no product |
| building | weeks 2 to 3 | 5 comments, 1 post | links to other people's sources only, no product |
| established | week 4 on | up to the ceiling | product only where the rules allow, at most 1 in 10 of your activity |

Hard ceiling: 10 drafts a day. You can lower any cap, never raise one past it.

## The tools

Stdlib only, Python 3.8+. None of them touch the network. Shared modules live in
`reddit-setup/` and the others add it to `sys.path`, as in validator-skill.

| tool | in | what it does |
| --- | --- | --- |
| `mdsafe.py` | setup | Copied from validator-skill: escapes stranger text for reports. |
| `store.py` | setup | Cut down from validator-skill: `clean_text`, stable IDs, and `verbatim()` for word-for-word quotes. |
| `capture.py` | setup | Checks and stores capture files, parses counts and ages, counts the page budget. |
| `profile.py` | setup | Checks `profile.json`: required fields, caps within the ceiling, one account. |
| `voice.py` | setup | Keeps your sample comments in `samples.jsonl` (apart from `voice.md`, so their text can never pose as a section), measures them, and checks every quirk in `voice.md` appears word for word in a sample. |
| `parsing.py` | setup | Turns "1.2k", "5 hr. ago" and "Jan 25, 2008" into numbers and dates. |
| `log.py` | setup | `reddit/log.jsonl`: what you posted, with link, sub and kind (help or promo). Feeds caps, the ratio and stats. |
| `subs.py` | subs | Ranks subs from captures with fixed weights: size, weekly contributions, fit to your terms. |
| `rules.py` | subs | Word rules that sort each rule into AI content, self-promo, links, minimums, flair. Quotes the rule word for word. Clear AI ban: skip. Unclear: needs your confirm. |
| `plan.py` | plan | Phase, caps, what each phase allows, the seven-day table and the ratio check. |
| `queue.py` | plan | Today's `queue.md` and `queue.ics`, and `gate` for the handoff. |
| `threads.py` | threads | Scores threads: relevance, age, comment count, question shape, not locked or archived, not already answered well. |
| `tells.py` | check | The AI tell list as data plus a detector. |
| `check.py` | check | The removal-risk score: low, medium or high, with each reason and the rule it hit. |
| `stats.py` | stats | Your own posts and comments from profile captures, summed by sub and kind, with removals. |

## What is kept, and where

All state in a `reddit/` folder in your project, added to `.gitignore`:
`profile.json`, `voice.md`, `samples.jsonl`, `captures/`, `subs.json`, `rules/<sub>.json`,
`threads.jsonl`, `drafts/`, `log.jsonl`, `queue.md`, `queue.ics` and the reports.

## Build phases

Each phase: tests first, then code, then a code-review sub-agent, fix its HIGH
findings, one conventional commit, push to the work branch. `main` only after you
approve the finished pack.

1. **Foundation.** Plugin files, `.gitignore`, `tests/_load.py`, `mdsafe`,
   trimmed `store`, `capture.py`, `profile.py`, `voice.py`, `log.py`, the
   no-network guard test, and `/reddit-setup`.
2. **Find.** `subs.py`, `rules.py` (rule sets in many wordings as fixtures) and
   `/reddit-subs`.
3. **Write well.** `tells.py`, `check.py`, `/reddit-check`.
4. **Engage.** `plan.py`, `queue.py`, `threads.py`, `/reddit-plan`,
   `/reddit-threads`, `/reddit-draft` with the handoff, the "never" line test and
   the optional hook.
5. **Look back.** `stats.py` and `/reddit-stats`.
6. **Ship.** `claude plugin validate .`, every file under 400 lines, the README.
   Then the real run on a neutral topic, on your machine with Claude in Chrome
   (this cloud machine cannot reach Reddit). You paste me the outputs, I write the
   worked example, and push to `main` with your OK.

## Risks

- **Reddit's page layout changes.** Claude reads pages, so a redesign does not
  break a parser, but the capture shape guards against half-read pages. The
  skills say which page to use and what to do if a number is missing (record it
  as unknown, never guess).
- **No live test from here.** Tools are tested against captures shaped like real
  pages. The first live run on your machine is the real test; I fix what it
  shows.
- **A model can misclick.** If the browser tool hits Post by mistake, a comment
  goes up. The hook is the backstop, and the handoff types only after the page
  has loaded and the box is found.
- **The rules reader can miss a ban** worded in a new way. Word rules plus
  Claude's own read; when either says "maybe", the sub is marked unclear and
  needs your confirm.
- **The cleanup step could be misused** to pass AI text off where it is banned.
  It will not run on a draft for a skipped sub.
- **Drafted help that is wrong.** Drafts stick to what your voice file says you
  know first-hand, and mark any claim you should check.
- **Personal data.** Captures hold other people's handles and text. Kept local,
  gitignored, never put in reports beyond a link and a short quote.

## Decided

1. Browser: Claude in Chrome, your everyday Chrome.
2. Data: the browser only. No API, no archive, no web search engine.
3. Warm-up caps: the table above.
4. Unclear AI rules: drafts allowed after you confirm you read the rule.
5. Real run: a neutral topic.
