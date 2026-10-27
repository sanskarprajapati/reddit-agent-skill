#!/usr/bin/env python3
"""Rank subreddits for the user's topics, from what Claude read in the browser.

  python3 subs.py build   [--dir reddit]   # reddit/subs.json and reddit/subs.md
  python3 subs.py show    [--dir reddit]

The score is out of 100, with fixed weights: fit to your topics 40, activity 35,
size 25. Size favours the middle: a giant sub buries a new account's comments, a
tiny one has nobody to help. A sub whose rules ban AI content is listed apart and
never ranked.
"""

import argparse
import datetime
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "reddit-setup"))
sys.path.insert(0, HERE)
import capture  # noqa: E402
import mdsafe  # noqa: E402
import profile as user_profile  # noqa: E402
import rules as sub_rules  # noqa: E402
import store  # noqa: E402

DEFAULT_DIR = "reddit"
WEIGHTS = {"fit": 40, "activity": 35, "size": 25}
SIZE_BANDS = ((1000, 0.2), (10000, 0.6), (500000, 1.0), (2000000, 0.8))  # members below -> score
SIZE_TOP = 0.5
ACTIVE_LOW, ACTIVE_HIGH = 10, 5000  # weekly contributions for 0 and for 1
STOP = {"the", "and", "for", "with", "about", "your", "from", "that", "this", "how", "what", "are", "you"}
_WORD = re.compile(r"[a-z0-9]+")
_NAME_PART = re.compile(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+")


def gather(caps):
    """{sub lowercased: record} from search results and sub pages. The sub page wins."""
    found = {}
    for cap in sorted(caps, key=lambda c: c["kind"] == "sub_about"):
        for item in cap["items"]:
            key = item["name"].lower()
            rec = found.setdefault(key, {"name": item["name"], "members": None, "weekly_contributions": None,
                                         "weekly_visitors": None, "description": "", "queries": []})
            if cap["kind"] == "sub_search":
                query = cap.get("query") or ""
                if query and query not in rec["queries"]:
                    rec["queries"].append(query)
                if rec["members"] is None:
                    rec["members"] = item.get("members")
                rec["description"] = rec["description"] or item.get("description", "")
            else:
                rec["name"] = item["name"]
                for field in ("members", "weekly_contributions", "weekly_visitors"):
                    if item.get(field) is not None:
                        rec[field] = item[field]
                rec["description"] = item.get("description") or rec["description"]
    for rec in found.values():
        rec["queries"].sort()
    return found


def size_score(members):
    if members is None:
        return 0
    for below, value in SIZE_BANDS:
        if members < below:
            return value
    return SIZE_TOP


def activity_score(contributions):
    if contributions is None or contributions <= ACTIVE_LOW:
        return 0
    if contributions >= ACTIVE_HIGH:
        return 1
    return (math.log10(contributions) - math.log10(ACTIVE_LOW)) / (math.log10(ACTIVE_HIGH) - math.log10(ACTIVE_LOW))


def _profile_words(profile):
    words = set()
    for phrase in profile.get("topics", []) + profile.get("terms", []):
        words |= {w for w in _WORD.findall(phrase.lower()) if len(w) >= 3 and w not in STOP}
    return words


def _near(a, b):
    """Same word, or one is the other plus a plural ending: grinder and grinders, not java and javascript."""
    short, long_ = sorted((a, b), key=len)
    return a == b or (len(short) >= 4 and long_[len(short):] in ("s", "es") and long_.startswith(short))


def fit_score(rec, profile):
    """Share of your topic words found in the sub's name and description, plus a little
    when more than one of your searches found it."""
    wanted = _profile_words(profile)
    if not wanted:
        return 0
    text = {p.lower() for p in _NAME_PART.findall(rec["name"])} | set(_WORD.findall(rec.get("description", "").lower()))
    name = rec["name"].lower()
    matched = sum(1 for w in wanted if any(_near(w, t) for t in text)
                  or (len(w) >= 4 and re.search(r"%s(e?s)?$" % re.escape(w), name)))
    score = matched / min(len(wanted), 4)
    if len(rec.get("queries", [])) >= 2:
        score += 0.25
    return min(score, 1.0)


def score(rec, profile):
    parts = {"fit": fit_score(rec, profile), "activity": activity_score(rec.get("weekly_contributions")),
             "size": size_score(rec.get("members"))}
    out = dict(rec)
    out["parts"] = {k: round(v, 2) for k, v in parts.items()}
    out["score"] = int(round(sum(WEIGHTS[k] * v for k, v in parts.items())))
    out["unknown"] = [f for f in ("members", "weekly_contributions") if rec.get(f) is None]
    return out


def rank(caps, profile, verdicts):
    ranked, skipped = [], []
    for key, rec in gather(caps).items():
        rec = score(rec, profile)
        rec["rules"] = verdicts.get(key, "missing")
        (skipped if rec["rules"] == "skip" else ranked).append(rec)
    ranked.sort(key=lambda r: (-r["score"], r["name"].lower()))
    skipped.sort(key=lambda r: r["name"].lower())
    return {"ranked": ranked, "skipped": skipped}


def _num(value):
    return "{:,}".format(value) if value is not None else "?"


def report(result, today):
    lines = ["# Subreddits", "", "Ranked %s. Score out of 100: fit %d, activity %d, size %d. "
             "`?` means the number was not on the pages read." % ((today.isoformat(),) + tuple(WEIGHTS.values())),
             "", "| # | sub | score | members | weekly contributions | rules | found by |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for n, r in enumerate(result["ranked"], 1):
        lines.append("| %d | r/%s | %d | %s | %s | %s | %s |" % (
            n, mdsafe.md(r["name"]), r["score"], _num(r["members"]), _num(r["weekly_contributions"]),
            r["rules"], mdsafe.md(", ".join(r["queries"]))))
    lines += ["", "Rules: `ok` you can draft there, `needs_confirm` read the AI rule yourself first, "
              "`stale` or `missing` read the rules before drafting."]
    if result["skipped"]:
        lines += ["", "## Skipped: these ban AI-written content", ""]
        lines += ["- r/%s" % mdsafe.md(r["name"]) for r in result["skipped"]]
    described = [r for r in result["ranked"] if r.get("description")]
    if described:
        lines += ["", "## What they say about themselves", ""]
        lines += ["- r/%s: %s" % (mdsafe.md(r["name"]), mdsafe.md(r["description"][:160])) for r in described]
    return "\n".join(lines) + "\n"


def build(folder, today):
    caps = capture.load_all(os.path.join(folder, "captures"))
    caps = [c for c in caps if c["kind"] in ("sub_search", "sub_about") and not c.get("blocked")]
    result = rank(caps, user_profile.load(folder, today), sub_rules.verdicts(folder, today))
    store.write_json(os.path.join(folder, "subs.json"), result)
    store.write_text(os.path.join(folder, "subs.md"), report(result, today))
    return result


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Rank subreddits for your topics")
    parser.add_argument("--dir", default=DEFAULT_DIR)
    parser.add_argument("cmd", choices=("build", "show"))
    args = parser.parse_args(argv)
    today = datetime.date.today()
    try:
        if args.cmd == "build":
            result = build(args.dir, today)
            for r in result["ranked"]:
                print("%3d  r/%-24s %-14s members=%s weekly=%s" % (r["score"], r["name"], r["rules"],
                                                                   _num(r["members"]), _num(r["weekly_contributions"])))
            for r in result["skipped"]:
                print("skip r/%s (bans AI-written content)" % r["name"])
        else:
            print(json.dumps(store.read_json(os.path.join(args.dir, "subs.json"), {}), indent=2, ensure_ascii=False))
    except (ValueError, OSError) as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
