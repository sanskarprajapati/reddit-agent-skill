#!/usr/bin/env python3
"""Would this get removed? A fixed-weight risk score for one draft in one subreddit.

  python3 check.py FILE --sub NAME --kind comment|post [--title "..."] [--flair "..."] [--dir reddit]

Risk is low (0 to 2 points), medium (3 to 5) or high (6 or more), with every point
explained. Some things are not risk but a hard stop ("blocked"): a sub that bans AI
content, rules not read or not confirmed, or your product where self-promotion is banned.
Exit code: 0 low or medium, 3 high, 4 blocked.
"""

import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "reddit-setup"))
sys.path.insert(0, os.path.join(HERE, "..", "reddit-subs"))
sys.path.insert(0, HERE)
import profile as user_profile  # noqa: E402
import rules as sub_rules  # noqa: E402
import signals  # noqa: E402
import tells  # noqa: E402
import voice  # noqa: E402

DEFAULT_DIR = "reddit"
LOW_MAX, MEDIUM_MAX = 2, 5
BLOCKING_VERDICTS = {
    "skip": "r/%s bans AI-written content. No drafts there.",
    "needs_confirm": "r/%s has an unclear AI rule. Read it yourself and confirm it first (/reddit-subs).",
    "missing": "the rules of r/%s have not been read yet. Run /reddit-subs first.",
    "stale": "the rules of r/%s were read over 30 days ago. Read them again first.",
}


def _rule(rules, topic):
    for e in rules.get("evidence", []):
        if e["topic"] == topic:
            return e["rule"], e["quote"]
    return None, None


def check(text, kind, rules, profile, title=None, flair=None, never=()):
    """rules is a rules.py record plus its "verdict". profile is a checked profile.json."""
    if kind not in ("comment", "post"):
        raise ValueError("kind must be comment or post")
    if kind == "post" and not str(title or "").strip():
        raise ValueError("a post needs a title")
    text = str(text or "")
    sub = rules.get("sub", "?")
    reasons, blocked = [], []

    def add(points, why, topic=None):
        rule, quote = _rule(rules, topic) if topic else (None, None)
        reasons.append({"points": points, "why": why, "rule": rule, "quote": quote})

    verdict = rules.get("verdict", "missing")
    if verdict in BLOCKING_VERDICTS:
        blocked.append(BLOCKING_VERDICTS[verdict] % sub)

    full = signals.normalise((str(title or "") + "\n" + text) if kind == "post" else text)
    links = signals.links(full)
    hosts = [signals.host_of(link) for link in links]
    product = profile.get("product") or {}
    mentions = signals.names_product(full, product.get("name", ""))
    links_own = signals.links_product(full, product.get("url", ""))
    promo = mentions or links_own

    if promo and rules.get("self_promo") == "banned":
        blocked.append("this mentions or links your product, and r/%s bans self-promotion" % sub)
    elif links_own:
        add(3, "links to your own product", "self_promo")
    elif mentions:
        add(2, "mentions your product", "self_promo")

    phrases = signals.promo_phrases(full)
    if phrases:
        each = 3 if rules.get("self_promo") == "banned" else 2
        add(min(each * len(phrases), 6), "reads like self-promotion: %s" % ", ".join(phrases), "self_promo")
        promo = True

    for link, host in zip(links, hosts):
        if host in signals.SHORTENERS:
            add(6, "link shortener (%s): spam filters remove these" % host)
        elif signals.tracking(link):
            add(4, "affiliate or tracking link (%s): reads as promotion" % host)
    if links and rules.get("links") == "banned":
        add(6 * len(links), "r/%s bans links, and this has %d" % (sub, len(links)), "links")
    elif links and rules.get("links") == "limited":
        add(2, "r/%s limits links: check this one is allowed" % sub, "links")
    elif len(links) > 1:
        add(1, "%d links: more than one looks like spam" % len(links))

    account = profile.get("account") or {}
    for field, minimum, what in (("karma", rules.get("min_karma"), "karma"),
                                 ("age_days", rules.get("min_age_days"), "account age in days")):
        have = account.get(field)
        if minimum and (have is None or have < minimum):
            add(6, "your %s (%s) is below the sub's minimum of %d, so AutoModerator usually removes it"
                % (what, "unknown" if have is None else have, minimum))

    if kind == "post" and rules.get("flair") and not str(flair or "").strip():
        add(3, "r/%s requires post flair, and none is set" % sub)
    words = len(text.split())
    if (kind == "comment" and words < 5) or (kind == "post" and words < 20):
        add(2, "very short (%d words): can read as low effort" % words)
    if kind == "comment" and words > 350:
        add(1, "long (%d words): most replies that do well are shorter" % words)
    if signals.shouting(full):
        add(2, "shouting: capitals or !!!")

    found = tells.detect(full, never)
    ai_found = [h for h in found if h["id"] != "never_list"]
    if ai_found:
        add(min(tells.weight(ai_found) // 2, 4), "reads like AI: %s" % ", ".join(h["label"] for h in ai_found))
    if len(ai_found) < len(found):
        add(2, "uses words on your never list: %s" % ", ".join(found[-1]["examples"]))

    points = sum(r["points"] for r in reasons)
    risk = "blocked" if blocked else "low" if points <= LOW_MAX else "medium" if points <= MEDIUM_MAX else "high"
    return {"risk": risk, "points": points, "blocked": blocked, "reasons": [r for r in reasons if r["points"]],
            "tells": found, "promo": promo, "links": links}


def never_list(folder):
    path = os.path.join(folder, voice.FILE)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return voice.parse(fh.read())["never"]


def run(folder, text, sub, kind, title=None, flair=None, today=None):
    """check() with the rules, profile and never list read from the reddit/ folder."""
    today = today or datetime.date.today()
    rec = sub_rules.read(folder, sub) or {"sub": sub}
    whole = all(k in rec for k in ("ai", "captured", "digest"))
    rec = dict(rec, verdict=sub_rules.verdict(rec if whole else None, today))
    try:
        profile = user_profile.load(folder, today)
    except ValueError:
        if rec["verdict"] not in BLOCKING_VERDICTS:
            raise
        profile = {}  # blocked anyway: say so rather than fail on the profile
    return check(text, kind, rec, profile, title, flair, never_list(folder))


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Would this draft get removed?")
    parser.add_argument("file")
    parser.add_argument("--sub", required=True)
    parser.add_argument("--kind", required=True, choices=("comment", "post"))
    parser.add_argument("--title")
    parser.add_argument("--flair")
    parser.add_argument("--dir", default=DEFAULT_DIR)
    args = parser.parse_args(argv)
    try:
        with open(args.file, encoding="utf-8") as fh:
            out = run(args.dir, fh.read(), args.sub, args.kind, args.title, args.flair)
    except (ValueError, OSError) as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    print(json.dumps(out, indent=2, ensure_ascii=False))
    return {"blocked": 4, "high": 3}.get(out["risk"], 0)


if __name__ == "__main__":
    sys.exit(_main())
