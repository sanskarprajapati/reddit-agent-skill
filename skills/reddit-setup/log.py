#!/usr/bin/env python3
"""reddit/log.jsonl: what the user posted or skipped, by hand. Caps and the promo ratio read it.

  python3 log.py add --url URL --sub NAME --kind comment|post --purpose help|promo [--status posted|skipped]
  python3 log.py today
  python3 log.py ratio [--days 30]
"""

import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402

DEFAULT_DIR = "reddit"
FILE = "log.jsonl"
KINDS = ("comment", "post")
PURPOSES = ("help", "promo")
STATUSES = ("posted", "skipped")
MAX_BACK = 7  # an old date could fake a warm-up that never happened


def entry(url, sub, kind, purpose, status="posted", date=None, today=None, draft="", note=""):
    """One checked log line. date defaults to today."""
    today = today or datetime.date.today()
    problems = []
    if not store.is_reddit_url(url):
        problems.append("url must be the reddit.com link of the thread or your comment")
    try:
        sub = store.sub_name(sub)
    except ValueError as err:
        problems.append(str(err))
    if kind not in KINDS:
        problems.append("kind must be comment or post")
    if purpose not in PURPOSES:
        problems.append("purpose must be help or promo")
    if status not in STATUSES:
        problems.append("status must be posted or skipped")
    day = store.read_date(date) if date else today
    if day is None:
        problems.append("date must be YYYY-MM-DD")
    elif day > today:
        problems.append("date is in the future")
    elif (today - day).days > MAX_BACK:
        problems.append("date can be at most %d days back: log posts as you go" % MAX_BACK)
    if problems:
        raise ValueError("log problems: " + " | ".join(problems))
    return {"date": day.isoformat(), "url": url.strip(), "sub": sub, "kind": kind, "purpose": purpose,
            "status": status, "draft": str(draft or ""), "note": str(note or "")}


def _posted(entries):
    return [e for e in entries if isinstance(e, dict) and e.get("status") == "posted"]


def counts_on(entries, day):
    """{'comment': n, 'post': n} posted on day. A row with no kind counts as 'unknown'."""
    counts = {}
    for e in _posted(entries):
        if e.get("date") == day.isoformat():
            kind = e.get("kind") if e.get("kind") in KINDS else "unknown"
            counts[kind] = counts.get(kind, 0) + 1
    return counts


def promo_ratio(entries, today, days=30):
    if isinstance(days, bool) or not isinstance(days, int) or days < 1:
        raise ValueError("days must be 1 or more")
    since = (today - datetime.timedelta(days=days - 1)).isoformat()
    window = [e for e in _posted(entries) if since <= str(e.get("date", "")) <= today.isoformat()]
    promo = sum(1 for e in window if e.get("purpose") == "promo")
    return {"promo": promo, "total": len(window), "ratio": promo / len(window) if window else 0.0, "days": days}


def read(folder):
    return store.load_jsonl(os.path.join(folder, FILE))


def add(folder, row):
    store.append_jsonl(os.path.join(folder, FILE), row)


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Your hand-posted log")
    parser.add_argument("--dir", default=DEFAULT_DIR)
    sub = parser.add_subparsers(dest="cmd", required=True)
    adder = sub.add_parser("add")
    for name in ("url", "sub"):
        adder.add_argument("--" + name, required=True)
    adder.add_argument("--kind", required=True, choices=KINDS)
    adder.add_argument("--purpose", required=True, choices=PURPOSES)
    adder.add_argument("--status", default="posted", choices=STATUSES)
    adder.add_argument("--date")
    adder.add_argument("--draft", default="")
    adder.add_argument("--note", default="")
    sub.add_parser("today")
    ratio = sub.add_parser("ratio")
    ratio.add_argument("--days", type=int, default=30)
    args = parser.parse_args(argv)
    today = datetime.date.today()
    try:
        if args.cmd == "add":
            row = entry(args.url, args.sub, args.kind, args.purpose, args.status, args.date, today,
                        args.draft, args.note)
            add(args.dir, row)
            print("logged: %s %s in r/%s" % (row["status"], row["kind"], row["sub"]))
        elif args.cmd == "today":
            print(json.dumps(counts_on(read(args.dir), today)))
        else:
            print(json.dumps(promo_ratio(read(args.dir), today, args.days)))
    except (ValueError, OSError) as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
