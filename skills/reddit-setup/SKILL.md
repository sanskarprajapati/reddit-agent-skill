---
name: reddit-setup
description: >-
  Sets up the Reddit pack: who the user is on Reddit, what they know and care about,
  their product (optional), account age and karma, and a voice file built from their
  own comments so drafts sound like them. Writes reddit/profile.json and
  reddit/voice.md. Use when the user says "set up reddit", "start the reddit pack",
  "build my voice file", or before any other reddit-* skill on a new project.
argument-hint: "[username]"
---

# reddit-setup

The intake. Everything else in the pack reads what this writes.

What the user typed after `/reddit-setup`: `$ARGUMENTS`

## The rules this pack keeps

Say these to the user in your own words at the start, once:

- **Nothing is posted without your approval.** Claude reads Reddit in your
  Chrome and types drafts into the reply box. In `manual` mode you click Post. In
  `approved` mode Claude clicks it, but only for a draft you approved word for
  word that day. It never votes, joins, follows, awards, reports, hides or DMs.
- One account, yours. No second accounts, no vote help, nothing meant to get
  past Reddit's spam filters or a sub's rules.
- A sub that bans AI-written content gets no drafts. A sub that bans
  self-promotion gets no product mention.
- Drafts sound like you because they copy habits you really have, never flaws
  added to hide that AI helped.

If the user asks for any of the things above, refuse that part, say why in a
line, and carry on with the rest.

## The tools

```bash
python3 "${CLAUDE_SKILL_DIR}/profile.py" init|check
python3 "${CLAUDE_SKILL_DIR}/voice.py" init|add-sample FILE|import-profile|check|measure
python3 "${CLAUDE_SKILL_DIR}/capture.py" start|add FILE|halt NOTE|budget|list
python3 "${CLAUDE_SKILL_DIR}/log.py" add|today|ratio
```

State lives in `reddit/` in the user's project. If the path is not expanded, use
the base directory Claude Code printed for this skill. Before any browser step,
read `${CLAUDE_SKILL_DIR}/BROWSER.md`; its `CAPTURE` is
`python3 "${CLAUDE_SKILL_DIR}/capture.py"`. Capture shapes are in
`${CLAUDE_SKILL_DIR}/CAPTURES.md`.

## Step 1: privacy and Chrome

1. If the project has a `.gitignore` without `reddit/`, offer to add it. The
   folder will hold other people's usernames and posts.
2. Check that the Claude in Chrome tools are connected. If not, tell the user
   that the pack reads Reddit through their own Chrome and point them to the
   Claude in Chrome extension. Until then, everything works by pasting.

## Step 2: the profile

Run `profile.py init`, then fill `reddit/profile.json` with the user. Ask, a few
at a time:

- Their Reddit username (optional, but needed for stats and for reading their
  own comments).
- What they want to be useful about: `topics`, in a few words each.
- The words people use when they ask about it: `terms` (for search).
- What they know first-hand: `knows`. Drafts only claim what is here.
- Account created date and karma. With a username and Chrome: `capture.py
  start`, open `reddit.com/user/<name>/`, write a `user_about` capture and add it,
  then copy the numbers it stored. Otherwise ask.
- Their product, if any: name, one line on what it is, link. `null` if none.
- How drafts go out (`posting`): `manual` (the default: Claude types, they click
  Post) or `approved` (Claude clicks Post for drafts they approved word for word
  that day). Explain both in a line each and let them choose. There is no
  unattended mode.
- Whether they want caps lower than the warm-up defaults (`caps`). They can only
  go down, never above 10 a day.

Run `profile.py check` and fix what it reports. Do not invent answers.

## Step 3: the voice file

Run `voice.py init`. Then get at least five comments the user wrote themselves.
They are kept in `reddit/samples.jsonl`, apart from `voice.md`:

- They paste them. Write each one, exactly as pasted, to its own file in
  `reddit/` and run `voice.py add-sample <file>`, or
- With their username and Chrome: open `reddit.com/user/<name>/comments/` in the
  same run, write a `profile` capture of what you see, `capture.py add` it, then
  `voice.py import-profile`. It only takes comments from the user's own profile.

Run `voice.py measure`. From the numbers and your own read of the samples,
suggest quirks, each with an example copied word for word from a sample:
casing, sentence length, openers, slang, punctuation habits, typos they really
make. Show the list. Keep only what the user agrees is them. Fill in the other
sections with them: about, first-hand knowledge, words they use and never use.

Run `voice.py check` until it passes. It refuses any quirk whose example is not
in a sample. Never add a quirk to make text look less like AI.

## Step 4: what next

Show a short summary: topics, account age and karma, product or none, number of
samples and quirks. Next: `/reddit-subs` to find the right communities.
