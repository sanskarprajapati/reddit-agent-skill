#!/usr/bin/env python3
"""The warm-up phase, today's caps, the promo ratio and a seven-day plan.

  python3 plan.py phase  [--dir reddit]   # your phase, what it allows, why
  python3 plan.py left   [--dir reddit]   # drafts left today
  python3 plan.py week   [--dir reddit]   # reddit/plan.md: the next seven days

Phases, by warm-up days:
  new          days 0 to 6    3 comments a day, no posts, no links, no product
  building     days 7 to 27   5 comments and 1 post a day, links to other people's sources only
  established  day 28 on      up to 10 a day, product only where the rules allow, at most 1 in 10

Warm-up days are the account's age while it is under four weeks old. An older
account with under 100 karma warms up from its first logged post, as a quiet
account is treated like a new one. Negative karma holds the phase at new.
"""

import argparse
import datetime
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "reddit-setup"))
import log as post_log  # noqa: E402
import mdsafe  # noqa: E402
import profile as user_profile  # noqa: E402
import store  # noqa: E402

DEFAULT_DIR = "reddit"
DRAFTS = "drafts.jsonl"
HARD_CEILING = user_profile.HARD_CEILING
QUIET_KARMA = 100
PROMO_SHARE = 0.1
PHASES = (
    ("new", 0, {"comments": 3, "posts": 0, "links": "none", "product": False}),
    ("building", 7, {"comments": 5, "posts": 1, "links": "others only", "product": False}),
    ("established", 28, {"comments": 8, "posts": 2, "links": "where the rules allow", "product": True}),
)


def _created(profile):
    account = profile.get("account") or {}
    return store.read_date(account.get("created"))


def _first_post(log):
    days = sorted(e["date"] for e in log if isinstance(e, dict) and e.get("status") == "posted" and e.get("date"))
    return store.read_date(days[0]) if days else None


def phase(profile, log, day):
    """The phase on a given day, with its allowances and the reason."""
    account = profile.get("account") or {}
    karma = account.get("karma") or 0
    created = _created(profile)
    age = (day - created).days if created else account.get("age_days", 0)
    if karma < 0:
        warm, why = 0, "negative karma holds the account at new"
    elif age < PHASES[2][1]:
        warm, why = age, "account is %d days old" % age
    elif karma >= QUIET_KARMA:
        warm, why = age, "account is %d days old with %d karma" % (age, karma)
    else:
        start = _first_post(log) or day
        warm = max((day - start).days, 0)
        why = "quiet account (%d karma): warming up from the first logged post, %d days ago" % (karma, warm)
    name, rules = PHASES[0][0], PHASES[0][2]
    for phase_name, from_day, phase_rules in PHASES:
        if warm >= from_day:
            name, rules = phase_name, phase_rules
    out = dict(rules)
    out.update(name=name, warm_days=warm, why=why)
    return out


def caps(profile, log, day):
    """Comments and posts allowed on day: the phase's caps, lowered by the user's own, never over the ceiling."""
    ph = phase(profile, log, day)
    user = profile.get("caps") or {}
    comment = min(ph["comments"], user.get("comments_per_day", HARD_CEILING))
    post = min(ph["posts"], user.get("posts_per_day", HARD_CEILING))
    post = min(post, max(HARD_CEILING - comment, 0))
    return {"comment": comment, "post": post}


def used_today(log, drafts, day):
    """Drafts made today (not skipped), plus posts logged by hand today that had no draft."""
    used = {"comment": 0, "post": 0}
    iso = day.isoformat()
    for d in drafts:
        if d.get("date") == iso and d.get("status") != "skipped" and d.get("kind") in used:
            used[d["kind"]] += 1
    for e in log:
        if e.get("date") == iso and e.get("status") == "posted" and not e.get("draft") and e.get("kind") in used:
            used[e["kind"]] += 1
    return used


def left_today(profile, log, drafts, day):
    cap, used = caps(profile, log, day), used_today(log, drafts, day)
    return {k: max(cap[k] - used[k], 0) for k in cap}


def promo_allowed(profile, log, day):
    """(yes or no, why). One more promo must keep promo at or under 1 in 10 of the last 30 days."""
    ph = phase(profile, log, day)
    if not ph["product"]:
        return False, "no product mentions in the %s phase (from the established phase, day 28)" % ph["name"]
    if not profile.get("product"):
        return False, "no product in profile.json"
    ratio = post_log.promo_ratio(log, day, days=30)
    if (ratio["promo"] + 1) > PROMO_SHARE * (ratio["total"] + 1):
        return False, ("one more would make promo %d of %d in the last 30 days, over 1 in 10. "
                       "Help more first" % (ratio["promo"] + 1, ratio["total"] + 1))
    return True, "promo would be %d of %d in the last 30 days" % (ratio["promo"] + 1, ratio["total"] + 1)


def week(profile, subs, log, today, per_day=3):
    """Seven days from today: phase, caps and which subs, rotating through the ones with rules ok."""
    ok = [r["name"] for r in subs.get("ranked", []) if r.get("rules") == "ok"]
    rows = []
    for i in range(7):
        day = today + datetime.timedelta(days=i)
        ph, cap = phase(profile, log, day), caps(profile, log, day)
        picks = [ok[(i + j) % len(ok)] for j in range(min(per_day, len(ok)))] if ok else []
        rows.append({"date": day.isoformat(), "phase": ph["name"], "comments": cap["comment"], "posts": cap["post"],
                     "links": ph["links"], "product": ph["product"], "subs": picks})
    return rows


def report(profile, subs, log, drafts, today):
    ph = phase(profile, log, today)
    left = left_today(profile, log, drafts, today)
    promo, why = promo_allowed(profile, log, today)
    ratio = post_log.promo_ratio(log, today, days=30)
    lines = ["# Your plan", "", "**Phase: %s.** %s." % (ph["name"], ph["why"]), "",
             "- Today: %d comments and %d posts left." % (left["comment"], left["post"]),
             "- Links: %s. Product mentions: %s." % (ph["links"], "yes, where the rules allow" if ph["product"]
                                                     else "no"),
             "- Last 30 days: %d posted, %d of them promo." % (ratio["total"], ratio["promo"]),
             "- One more promo now: %s (%s)." % ("yes" if promo else "no", why), "",
             "| day | phase | comments | posts | subs |", "| --- | --- | --- | --- | --- |"]
    for r in week(profile, subs, log, today):
        lines.append("| %s | %s | %d | %d | %s |" % (r["date"], r["phase"], r["comments"], r["posts"],
                                                   ", ".join("r/" + mdsafe.md(s) for s in r["subs"]) or "none yet"))
    lines += ["", "Caps are the most, not a target. Skip a day whenever you like."]
    if not week(profile, subs, log, today)[0]["subs"]:
        lines.append("No subs with rules ok yet: run /reddit-subs.")
    return "\n".join(lines) + "\n"


def load(folder, today):
    """profile, subs, log and drafts from the reddit/ folder."""
    return (user_profile.load(folder, today), store.read_json(os.path.join(folder, "subs.json"), {}),
            post_log.read(folder), store.load_jsonl(os.path.join(folder, DRAFTS)))


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Warm-up phase and weekly plan")
    parser.add_argument("--dir", default=DEFAULT_DIR)
    parser.add_argument("cmd", choices=("phase", "left", "week"))
    args = parser.parse_args(argv)
    today = datetime.date.today()
    try:
        profile, subs, log, drafts = load(args.dir, today)
        if args.cmd == "phase":
            out = phase(profile, log, today)
            out["promo"] = promo_allowed(profile, log, today)
            print(json.dumps(out, indent=2))
        elif args.cmd == "left":
            print(json.dumps(left_today(profile, log, drafts, today)))
        else:
            path = os.path.join(args.dir, "plan.md")
            store.write_text(path, report(profile, subs, log, drafts, today))
            print("wrote %s" % path)
    except (ValueError, OSError) as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
