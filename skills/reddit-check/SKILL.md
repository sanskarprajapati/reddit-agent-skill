---
name: reddit-check
description: >-
  "Would this get removed?" for a Reddit comment or post draft, in a named subreddit.
  Scores rule fit, self-promotion signals, links, account minimums, flair, length,
  tone and AI tells with fixed weights, every point with a reason. Then offers a
  cleaned version in the user's own voice and checks it again. Use when the user
  says "check this draft", "will this get removed", "is this too promotional",
  "does this sound like AI", or pastes a draft with a subreddit.
argument-hint: "r/name [file or pasted draft]"
---

# reddit-check

A second pair of eyes before anything goes near Reddit. `/reddit-draft` runs it
on every draft; the user can also run it on text they wrote.

What the user typed after `/reddit-check`: `$ARGUMENTS`

**You click Post.** This skill reads files and writes files. It never opens a
reply box and never posts.

If the user asks to add typos, make a text "undetectable", get it past the mods
or past an AI ban, refuse that part and say why in a line: drafts sound like the
user because they follow habits the user really has, not to hide anything.

## The tools

```bash
python3 "${CLAUDE_SKILL_DIR}/check.py" FILE --sub NAME --kind comment|post [--title "..."] [--flair "..."]
python3 "${CLAUDE_SKILL_DIR}/tells.py" FILE [--never "word, word"]
```

`check.py` reads `reddit/profile.json`, `reddit/voice.md` (the never list) and
`reddit/rules/<sub>.json`. Exit code 0 is low or medium risk, 3 high, 4 blocked,
and 1 an error: stop and treat the draft as not checked.

## Step 1: get the draft

Take the sub and the draft from what the user typed or a file in
`reddit/drafts/`. If the draft was pasted, save it exactly as given to
`reddit/drafts/check-<short name>.txt` first. Ask whether it is a comment or a
post; a post needs its title.

## Step 2: run the check

Run `check.py`. Show the result plainly:

- **blocked**: say why in one line each, and stop there for that sub. A sub that
  bans AI-written content gets no draft and no cleanup, whatever the user asks.
  If the block is "rules not read", "rules over 30 days old" or "unclear AI
  rule", point to `/reddit-subs`. If it is "your product where self-promotion is
  banned", offer a version without the product.
- **low, medium or high**: list each reason with its points, and the rule it
  hit (number and quote) where there is one.

Points are fixed. You may disagree with a score in words; never change it.

Then read the draft yourself for self-promotion the word list missed (an
ownership hint, a link to something the user runs, a nudge to their profile)
and say what you found. That adds no points, but it goes in the summary.

## Step 3: offer a cleaned version

Only if there are tells or other fixable reasons, and only after a `check.py`
run in this session, for a named sub, that was not blocked. `tells.py` on its
own never unlocks a cleanup. Write a new version to a new file next to the old
one (`...-clean.txt`). Never overwrite the user's text.

How to clean:

- Keep the meaning, the facts and the user's point. Cut, do not pad.
- Remove each tell `check.py` listed: em dashes become a comma, a full stop or
  "and"; stock openers and closers go; AI words become plain ones; headings,
  bold and tidy lists go in a comment unless the sub's own style uses them.
- Follow `reddit/voice.md`: the words they use, the words they never use, and
  their quirks. Use a quirk only as often as their samples show it. Never add a
  typo, slang or a flaw that is not in their voice file. The aim is their real
  voice, not a disguise.
- Claim only what `voice.md` lists under first-hand knowledge. Mark any other
  claim with `[check this]` for the user.
- Drop promo phrases and links the rules do not allow.

Run `check.py` on the new file. Show both versions side by side with their risk
and points, and let the user choose or edit. Do not pick for them.

## Step 4: hand back

Say where the files are. If this came from `/reddit-draft`, go back there for
the handoff. Otherwise the user posts it themselves, when and if they want to.
