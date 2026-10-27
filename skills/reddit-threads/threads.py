#!/usr/bin/env python3
"""Rank threads worth replying to, from the listings and threads Claude read in the browser.

  python3 threads.py build [--dir reddit] [--top 15]   # reddit/threads.jsonl and reddit/threads.md

Score out of 100, fixed weights: relevance 40, freshness 25, room to help 20 (few
or no good answers yet), a real question 15. Left out, with the reason: locked,
archived (over 180 days), your own, a bot's, already replied to or drafted, off
topic, or in a sub that bans AI-written content.
"""

import argparse
import datetime
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "reddit-setup"))
sys.path.insert(0, os.path.join(HERE, "..", "reddit-subs"))
sys.path.insert(0, os.path.join(HERE, "..", "reddit-plan"))
import capture  # noqa: E402
import mdsafe  # noqa: E402
import plan  # noqa: E402
import profile as user_profile  # noqa: E402
import rules as sub_rules  # noqa: E402
import store  # noqa: E402

DEFAULT_DIR = "reddit"
WEIGHTS = {"relevance": 40, "fresh": 25, "room": 20, "question": 15}
FRESH = ((6, 1.0), (24, 0.8), (48, 0.5), (24 * 7, 0.2))  # hours old or less -> score
ROOM = ((0, 1.0), (2, 0.8), (5, 0.5), (15, 0.2))  # comments or fewer -> score
ARCHIVED_DAYS = 180
GOOD_ANSWER_SCORE, GOOD_ANSWER_WORDS = 5, 20
STOP = {"the", "and", "for", "with", "about", "your", "from", "that", "this", "how", "what", "are", "you"}
_WORD = re.compile(r"[a-z0-9]+")
_QUESTION = re.compile(r"\?|^\s*(how|what|why|which|should|is|are|can|does|do|any|anyone|help|advice|need)\b", re.I)


def _words(profile):
    words = set()
    for phrase in profile.get("topics", []) + profile.get("terms", []):
        words |= {w for w in _WORD.findall(phrase.lower()) if len(w) >= 3 and w not in STOP}
    return words


def _near(a, b):
    short, long_ = sorted((a, b), key=len)
    return a == b or (len(short) >= 4 and long_.startswith(short) and long_[len(short):] in ("s", "es", "ed", "ing"))


def _band(value, bands):
    for limit, score in bands:
        if value <= limit:
            return score
    return 0.0


def _hours(post, now):
    created = capture.parse_iso(post.get("created"))
    return None if created is None else max((now - created).total_seconds() / 3600, 0)


def score(post, profile, now):
    wanted = _words(profile)
    text = set(_WORD.findall((post.get("title", "") + " " + post.get("body", "")).lower()))
    matched = sum(1 for w in wanted if any(_near(w, t) for t in text))
    hours, comments = _hours(post, now), post.get("comments")
    parts = {"relevance": min(matched / min(len(wanted), 3), 1.0) if wanted else 0.0,
             "fresh": _band(hours, FRESH) if hours is not None else 0.0,
             "room": _band(comments, ROOM) if comments is not None else 0.3,
             "question": 1.0 if _QUESTION.search(post.get("title", "")) or "?" in post.get("body", "") else 0.0}
    out = dict(post)
    out["parts"] = {k: round(v, 2) for k, v in parts.items()}
    out["score"] = int(round(sum(WEIGHTS[k] * v for k, v in parts.items())))
    out["age_hours"] = round(hours, 1) if hours is not None else None
    out["unknown"] = [name for name, value in (("age", hours), ("comments", comments)) if value is None]
    return out


def answered_well(thread):
    """A non-bot comment with some upvotes and some substance. Rough, and said to be rough."""
    for c in thread.get("items", []):
        if not c.get("bot") and (c.get("score") or 0) >= GOOD_ANSWER_SCORE \
                and len(c.get("text", "").split()) >= GOOD_ANSWER_WORDS:
            return True
    return False


def _thread_ids(rows):
    return {store.reddit_id(r.get("url", "")) for r in rows} | {
        "t3_" + m.group(1) for r in rows for m in [re.search(r"/comments/([a-z0-9]+)", r.get("url", ""), re.I)] if m}


def _why_out(p, profile, verdicts, replied, now):
    if p.get("locked"):
        return "locked"
    hours = _hours(p, now)
    if hours is not None and hours > ARCHIVED_DAYS * 24:
        return "archived: replies are closed after about six months"
    if profile.get("username") and p.get("author", "").lower() == profile["username"].lower():
        return "your own post"
    if p.get("bot") or store.is_bot(p.get("author")):
        return "posted by a bot"
    if verdicts.get(p["sub"].lower()) == "skip":
        return "r/%s bans AI-written content" % p["sub"]
    if p["id"] in replied:
        return "already replied or drafted"
    if p["parts"]["relevance"] == 0:
        return "off topic"
    return None


def rank(caps, profile, verdicts, log, drafts, now, top=15):
    posts, found_in, answered, newest = {}, {}, set(), None
    for cap in sorted(caps, key=lambda c: c.get("captured", "")):
        if cap.get("blocked"):
            continue
        when = capture.parse_iso(cap.get("captured"))
        newest = max(newest, when) if newest and when else (when or newest)
        items = cap.get("items", []) if cap["kind"] == "listing" else [cap["post"]] if cap["kind"] == "thread" else []
        for item in items:
            if not item.get("id", "").startswith("t3_"):
                continue
            posts[item["id"]] = dict(posts.get(item["id"], {}), **{k: v for k, v in item.items() if v is not None})
            source = cap.get("source", "thread")
            found_in.setdefault(item["id"], [])
            if source not in found_in[item["id"]]:
                found_in[item["id"]].append(source)
        if cap["kind"] == "thread" and answered_well(cap):
            answered.add(cap["post"]["id"])
    replied = _thread_ids([e for e in log if e.get("status") == "posted"]) | _thread_ids(
        [d for d in drafts if d.get("status") != "skipped"])
    ranked, left_out = [], []
    for pid, p in posts.items():
        p = score(p, profile, now)
        p["found_in"] = found_in[pid]
        p["answered_well"] = pid in answered
        if p["answered_well"]:
            p["score"] -= int(round(WEIGHTS["room"] * p["parts"]["room"]))
        p["rules"] = verdicts.get(p["sub"].lower(), "missing")
        why = _why_out(p, profile, verdicts, replied, now)
        if why:
            p["why_left_out"] = why
            left_out.append(p)
        else:
            ranked.append(p)
    ranked.sort(key=lambda t: (-t["score"], t["id"]))
    hours = int((now - newest).total_seconds() // 3600) if newest else None
    return {"ranked": ranked[:top], "left_out": left_out, "newest_capture_hours": hours}


def report(result, now):
    lines = ["# Threads worth a reply", "",
             "Ranked %s. Score out of 100: relevance %d, freshness %d, room to help %d, a real question %d." %
             ((now.strftime("%Y-%m-%d %H:%M UTC"),) + tuple(WEIGHTS.values()))]
    if result["newest_capture_hours"] is not None and result["newest_capture_hours"] >= 12:
        lines.append("The newest page read is %d hours old. Read the New tabs again for fresh threads."
                     % result["newest_capture_hours"])
    lines += ["", "| # | score | sub | thread | age (h) | comments | rules | link |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for n, t in enumerate(result["ranked"], 1):
        lines.append("| %d | %d | r/%s | %s%s | %s | %s | %s | %s |" % (
            n, t["score"], mdsafe.md(t["sub"]), mdsafe.md(t.get("title", "")[:120]),
            " (answered well already)" if t["answered_well"] else "",
            t["age_hours"] if t["age_hours"] is not None else "?",
            t.get("comments") if t.get("comments") is not None else "?", t["rules"], mdsafe.cite(t["id"], t["url"])))
    if result["left_out"]:
        lines += ["", "Left out: %d (%s)." % (len(result["left_out"]), ", ".join(sorted(
            {t["why_left_out"].split(":")[0] for t in result["left_out"]})))]
    return "\n".join(lines) + "\n"


def build(folder, now, top=15):
    today = now.date()
    caps = [c for c in capture.load_all(os.path.join(folder, "captures")) if c["kind"] in ("listing", "thread")]
    result = rank(caps, user_profile.load(folder, today), sub_rules.verdicts(folder, today),
                  store.load_jsonl(os.path.join(folder, "log.jsonl")),
                  store.load_jsonl(os.path.join(folder, plan.DRAFTS)), now, top)
    store.save_jsonl(os.path.join(folder, "threads.jsonl"), result["ranked"])
    store.write_text(os.path.join(folder, "threads.md"), report(result, now))
    return result


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Threads worth replying to")
    parser.add_argument("--dir", default=DEFAULT_DIR)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("cmd", choices=("build",))
    args = parser.parse_args(argv)
    try:
        result = build(args.dir, datetime.datetime.now(datetime.timezone.utc), args.top)
    except (ValueError, OSError) as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    for t in result["ranked"]:
        print("%3d  r/%-18s %-8s %s" % (t["score"], t["sub"], t["rules"], t.get("title", "")[:70]))
    print(json.dumps({"left_out": len(result["left_out"]), "newest_capture_hours": result["newest_capture_hours"]}))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
