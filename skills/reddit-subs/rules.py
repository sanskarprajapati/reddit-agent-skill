#!/usr/bin/env python3
"""Read each subreddit's rules with fixed word rules, and decide skip, confirm or ok.

  python3 rules.py build                         # from every rules capture, newest per sub
  python3 rules.py status  SUB                   # ok, skip, needs_confirm, stale or missing
  python3 rules.py show    SUB
  python3 rules.py confirm SUB                   # the user read an unclear AI rule themselves
  python3 rules.py flag    SUB --ai unclear|banned --reason "..."   # Claude's read, stricter only
  python3 rules.py reread  SUB                   # after the rules changed: drop old flags, read again
  python3 rules.py report                        # reddit/rules.md

Each sentence is read on its own. A sentence that names AI, says no, and is about
writing or content is an AI ban, and the sub is skipped. No confirm can undo that.
"""

import argparse
import datetime
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "reddit-setup"))
import capture  # noqa: E402
import mdsafe  # noqa: E402
import store  # noqa: E402
from parsing import parse_count  # noqa: E402

DEFAULT_DIR = "reddit"
STALE_DAYS = 30
AI_LEVELS = ("not mentioned", "unclear", "banned")
PROMO_LEVELS = ("not mentioned", "limited", "banned")

_I = re.I
AI_STRONG = re.compile(r"\b(ai|ais|artificial intelligence|chat\s?gpt|gpt-?\d*|llms?|large language models?|"
                       r"generative|gen-?ai|chatbots?|(?:machine|computer|auto|ai)[- ](?:generated|written|made))\b",
                       _I)
AI_WEAK = re.compile(r"\b(bots?|claude|gemini|copilot|bard|grok)\b", _I)  # count only with writing words
CREATION = re.compile(r"\b(generat\w*|writ\w*|wrote|made|creat\w*|produc\w*|assist\w*|content|posts?|comments?|"
                      r"answers?|replies|repl(?:y|ied)|responses?|text|art|images?|slop|output|use|using|used)\b", _I)
PROMO_TOPIC = re.compile(r"\b(self[- ]?promo\w*|promot\w*|advertis\w*|affiliate|referral|shill\w*|"
                         r"marketing|solicit\w*|your own (product|business|blog|channel|app|website|content|stuff))\b",
                         _I)
LINK_TOPIC = re.compile(r"\b(links?|urls?|link shorteners?)\b", _I)
BAN = re.compile(r"\b(no|not allowed|aren't allowed|isn't allowed|not permitted|not tolerated|not welcome|ban|bans|"
                 r"banned|prohibited|forbidden|disallowed|removed|deleted?|don't|do not|never|zero tolerance|can't|"
                 r"cannot|may not|must not|won't be|result in a (?:permanent )?ban|unwelcome|human[- ]written only|"
                 r"only human)\b", _I)
NOT = r"(?<!not )(?<!n't )"
AI_ALLOW = re.compile(NOT + r"\b(allowed|permitted|welcome|fine|okay|ok)\b|\bas long as\b|\bprovided\b|"
                      r"\bdon't mind\b|\bif you (disclose|label|flair|tag|mark|say|note|mention)\b|"
                      r"\bmust be (clearly )?(labell?ed|flaired|tagged|marked|disclosed)\b|\bdisclose\w*\b", _I)
HEDGE = re.compile(r"\bmay\b(?! not)|\bmight\b|\bsome\b|\bdiscretion\b|\bcase[- ]by[- ]case\b|\bdepending\b", _I)
ALLOWANCE = re.compile(r"\bexcept\w*|\bexception\b|\bonly (in|on|during|within)\b|\boutside (of )?the\b|" + NOT +
                       r"\b(allowed|permitted|welcome|ok|okay|fine)\b|\d+\s*%|\b(1|one)[- ](in|of)[- ](10|ten)\b|"
                       r"\b1/10\b|\b10:1\b|\b9:1\b|\bratio\b|\b(mon|tues|wednes|thurs|fri|satur|sun)days?\b|"
                       r"\bdesignated\b|\bask (the )?mods?\b|\bmod(erator)? (approval|permission)\b|"
                       r"\bwith (prior )?(approval|permission)\b", _I)
LINK_ALLOWANCE = re.compile(ALLOWANCE.pattern + r"|\boriginal source\b|\bmust\b|\bonly\b", _I)
FLAIR_REQUIRED = re.compile(r"\b(must|required|require|mandatory|need to|needs to)\b", _I)
_KARMA = re.compile(r"(\d[\d,]*(?:\.\d+)?\s*[km]?)\s*\+?\s*(?:combined |comment |post |link )?karma\b", _I)
_KARMA_AFTER = re.compile(r"karma\D{0,25}?(\d[\d,]*(?:\.\d+)?\s*[km]?)\b", _I)
_AGE = re.compile(r"\b(\d+|an?|one|two|three|four|five|six|seven|eight|nine|ten|fourteen|thirty)\s*"
                  r"(hour|day|week|month|year)s?\b", _I)
_AGE_CONTEXT = re.compile(r"\b(old|young\w*|new\w*|age)\b", _I)
_WORDS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
          "eight": 8, "nine": 9, "ten": 10, "fourteen": 14, "thirty": 30}
_DAYS = {"hour": 1 / 24.0, "day": 1, "week": 7, "month": 30, "year": 365}
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+|\n")
_EVEN_IF = re.compile(r"\beven if\b[^.!?\n]*", _I)


def _norm(text):
    text = text.replace("’", "'").replace("‘", "'")
    return re.sub(r"\ba\.i\.", "AI", text, flags=_I)


def sentences(rule):
    return [s.strip() for s in _SENTENCE_BREAK.split(_norm(rule["title"] + "\n" + rule["text"])) if s.strip()]


def ai_level(sentence):
    """One sentence's reading of AI-written content, or None if it does not name AI."""
    strong, weak = AI_STRONG.search(sentence), AI_WEAK.search(sentence)
    writing = CREATION.search(sentence)
    if not strong and not (weak and writing):
        return None
    if not BAN.search(sentence):
        return "unclear"
    rest = _EVEN_IF.sub("", sentence)
    if AI_ALLOW.search(rest) or HEDGE.search(rest):
        return "unclear"
    short_no = strong and re.match(r"^\s*no\b", sentence, _I) and len(sentence.split()) <= 4
    return "banned" if writing or short_no else "unclear"


def _topic_level(rule, pattern, allowance):
    """Self-promotion or links: banned if a sentence on the topic says no and the rule allows nothing."""
    parts = sentences(rule)
    on_topic = [s for s in parts if pattern.search(s)]
    if not on_topic:
        return None
    whole = " ".join(parts)
    if any(BAN.search(s) for s in on_topic) and not allowance.search(_EVEN_IF.sub("", whole)):
        return "banned"
    return "limited"


def _strictest(levels, order):
    return max(levels, key=order.index) if levels else order[0]


def _minimums(rule):
    karma = age = None
    for s in sentences(rule):
        if re.search(r"\bkarma\b", s, _I):
            match = _KARMA.search(s) or _KARMA_AFTER.search(s)
            value = parse_count(match.group(1)) if match else None
            if value:
                karma = max(karma or 0, value)
        if re.search(r"\baccounts?\b", s, _I) and _AGE_CONTEXT.search(s):
            match = _AGE.search(s)
            if match:
                n = _WORDS.get(match.group(1).lower()) or int(match.group(1))
                days = max(1, int(-(-n * _DAYS[match.group(2).lower()] // 1)))
                age = max(age or 0, days)
    return karma, age


def _quote(rule, test):
    for s in sentences(rule):
        if test(s) and store.verbatim(s, _norm(rule["title"] + "\n" + rule["text"]), min_words=1):
            return s
    return rule["title"]


def digest(items):
    text = "\n".join("%s\n%s" % (r["title"], r["text"]) for r in items)
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


def classify(cap, today):
    """One rules capture -> one rules record with the word-rule reading and its evidence."""
    rules = [{"number": r.get("number", n), "title": r.get("title", ""), "text": r.get("text", "")}
             for n, r in enumerate(cap["items"], 1)]
    ai, promo, links, evidence = [], [], [], []
    min_karma = min_age = None
    flair = False
    for rule in rules:
        levels = [lvl for lvl in (ai_level(s) for s in sentences(rule)) if lvl]
        if levels:
            level = _strictest(levels, AI_LEVELS)
            ai.append(level)
            evidence.append({"topic": "ai", "level": level, "rule": rule["number"],
                             "quote": _quote(rule, lambda s, lv=level: ai_level(s) == lv)})
        for topic, pattern, allowance, bucket in (("self_promo", PROMO_TOPIC, ALLOWANCE, promo),
                                                  ("links", LINK_TOPIC, LINK_ALLOWANCE, links)):
            level = _topic_level(rule, pattern, allowance)
            if level:
                bucket.append(level)
                evidence.append({"topic": topic, "level": level, "rule": rule["number"],
                                 "quote": _quote(rule, pattern.search)})
        karma, age = _minimums(rule)
        min_karma = max(filter(None, (min_karma, karma)), default=None)
        min_age = max(filter(None, (min_age, age)), default=None)
        text = rule["title"] + "\n" + rule["text"]
        if re.search(r"\bflair", text, _I) and FLAIR_REQUIRED.search(text):
            flair = True
    captured = capture.parse_iso(cap.get("captured"))
    day = min(captured.date(), today) if captured else today
    word_ai = _strictest(ai, AI_LEVELS) if ai else "not mentioned"
    return {
        "sub": store.sub_name(cap["sub"]), "url": cap.get("url", ""), "captured": day.isoformat(),
        "checked": today.isoformat(), "digest": digest(rules), "rules": rules,
        "ai_words": word_ai, "ai": word_ai,
        "self_promo": _strictest(promo, PROMO_LEVELS) if promo else "not mentioned",
        "links": _strictest(links, PROMO_LEVELS) if links else "not mentioned",
        "min_karma": min_karma, "min_age_days": min_age, "flair": flair,
        "evidence": evidence, "flags": [], "confirmed": None, "reread": False,
    }


def _with_flags(rec, flags):
    out = dict(rec)
    out["flags"] = flags
    out["ai"] = _strictest([rec.get("ai_words", rec["ai"])] + [f["level"] for f in flags], AI_LEVELS)
    return out


def verdict(rec, today):
    if not rec:
        return "missing"
    if rec["ai"] == "banned":
        return "skip"
    if (today - datetime.date.fromisoformat(rec["captured"])).days > STALE_DAYS:
        return "stale"
    if rec["ai"] == "unclear" and not (rec.get("confirmed") and rec["confirmed"].get("digest") == rec["digest"]):
        return "needs_confirm"
    return "ok"


def confirm(rec, today):
    if rec["ai"] == "banned":
        raise ValueError("r/%s bans AI-written content, so it stays skipped" % rec["sub"])
    if rec.get("reread"):
        raise ValueError("the rules of r/%s changed. Read them again first (rules.py reread)" % rec["sub"])
    out = dict(rec)
    out["confirmed"] = {"date": today.isoformat(), "digest": rec["digest"]}
    return out


def flag(rec, level, reason, today):
    """Claude's own read of a rule. It can only make the reading stricter."""
    if level not in AI_LEVELS[1:]:
        raise ValueError("level must be unclear or banned")
    if AI_LEVELS.index(level) < AI_LEVELS.index(rec["ai"]):
        raise ValueError("flags can only make a reading stricter (it is already %s)" % rec["ai"])
    entry = {"level": level, "reason": str(reason)[:300], "date": today.isoformat(), "digest": rec["digest"]}
    out = _with_flags(rec, rec.get("flags", []) + [entry])
    if level == "unclear":
        out["confirmed"] = None  # a new doubt needs a new look from the user
    return out


def merge_previous(new, old):
    """Same rules text: keep flags and a confirm. Changed text: drop the confirm, but keep
    any ban flag until Claude has read the new rules (reread)."""
    if not old:
        return new
    if old.get("digest") == new["digest"]:
        out = _with_flags(new, old.get("flags", []))
        out["confirmed"], out["reread"] = old.get("confirmed"), old.get("reread", False)
        return out
    carried = [f for f in old.get("flags", []) if f["level"] == "banned"]
    out = _with_flags(new, carried)
    out["reread"] = bool(carried)
    return out


def reread(rec):
    """Claude has read the changed rules: flags made on older text go, and Claude flags again if needed."""
    out = _with_flags(rec, [f for f in rec.get("flags", []) if f.get("digest") == rec["digest"]])
    out["reread"] = False
    return out


def _path(folder, sub):
    return os.path.join(folder, "rules", store.sub_name(sub).lower() + ".json")


def save(folder, rec):
    store.write_json(_path(folder, rec["sub"]), rec)


def read(folder, sub):
    return store.read_json(_path(folder, sub))


def read_all(folder):
    path = os.path.join(folder, "rules")
    if not os.path.isdir(path):
        return []
    return [store.read_json(os.path.join(path, n)) for n in sorted(os.listdir(path)) if n.endswith(".json")]


def verdicts(folder, today):
    """{sub lowercased: verdict} for every sub with a rules file."""
    return {r["sub"].lower(): verdict(r, today) for r in read_all(folder)}


def build(folder, today):
    newest = {}
    for cap in capture.load_all(os.path.join(folder, "captures"), kind="rules"):
        if cap.get("blocked") or not cap.get("sub") or not cap.get("items"):
            continue
        key = store.sub_name(cap["sub"]).lower()
        if key not in newest or cap["captured"] >= newest[key]["captured"]:
            newest[key] = cap
    out = []
    for key, cap in sorted(newest.items()):
        rec = merge_previous(classify(cap, today), read(folder, key))
        save(folder, rec)
        out.append(rec)
    return out


def report(records, today):
    lines = ["# Subreddit rules", "", "Read %s. Word rules plus Claude's read; read the rules yourself too." %
             today.isoformat(), "",
             "| sub | verdict | AI content | self-promo | links | min karma | min age (days) | flair |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in records:
        lines.append("| r/%s | %s | %s | %s | %s | %s | %s | %s |" % (
            mdsafe.md(r["sub"]), verdict(r, today), r["ai"], r["self_promo"], r["links"],
            r["min_karma"] if r["min_karma"] is not None else "", r["min_age_days"] or "",
            "required" if r["flair"] else ""))
    for r in records:
        if r["evidence"] or r["flags"]:
            lines += ["", "## r/%s" % mdsafe.md(r["sub"]), ""]
            for e in r["evidence"]:
                lines.append("- %s, %s, rule %s: \"%s\"" % (e["topic"], e["level"], e["rule"], mdsafe.md(e["quote"])))
            for f in r["flags"]:
                lines.append("- Claude flagged AI content as %s: %s" % (f["level"], mdsafe.md(f["reason"])))
            if r.get("reread"):
                lines.append("- The rules changed since a ban flag. Read them again.")
    return "\n".join(lines) + "\n"


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Subreddit rules")
    parser.add_argument("--dir", default=DEFAULT_DIR)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build")
    sub.add_parser("report")
    for name in ("status", "show", "confirm", "reread"):
        sub.add_parser(name).add_argument("sub")
    flagger = sub.add_parser("flag")
    flagger.add_argument("sub")
    flagger.add_argument("--ai", required=True, choices=AI_LEVELS[1:])
    flagger.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    today = datetime.date.today()
    try:
        if args.cmd == "build":
            for r in build(args.dir, today):
                print("r/%-24s %-14s ai=%s promo=%s links=%s%s" % (
                    r["sub"], verdict(r, today), r["ai"], r["self_promo"], r["links"],
                    "  (rules changed: reread)" if r.get("reread") else ""))
        elif args.cmd == "report":
            path = os.path.join(args.dir, "rules.md")
            store.write_text(path, report(read_all(args.dir), today))
            print("wrote %s" % path)
        else:
            rec = read(args.dir, args.sub)
            if args.cmd == "status":
                print(verdict(rec, today))
                return 0
            if rec is None:
                raise ValueError("no rules read for r/%s yet" % args.sub)
            if args.cmd == "show":
                print(json.dumps(rec, indent=2, ensure_ascii=False))
                return 0
            if args.cmd == "confirm":
                rec = confirm(rec, today)
            elif args.cmd == "reread":
                rec = reread(rec)
            else:
                rec = flag(rec, args.ai, args.reason, today)
            save(args.dir, rec)
            print("r/%s is now %s" % (rec["sub"], verdict(rec, today)))
    except (ValueError, OSError, KeyError) as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
