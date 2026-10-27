#!/usr/bin/env python3
"""Captures: what Claude read off a Reddit page in the user's browser, checked and kept.

Claude writes one raw JSON file per page it read (shapes in CAPTURES.md), then:

  python3 capture.py start  [--limit 30] [--user-checked]   # begin or continue a run
  python3 capture.py add    FILE                              # check, store, count against the budget
  python3 capture.py halt   "what Reddit showed"              # stop everything after a block or warning
  python3 capture.py budget                                   # pages used and left
  python3 capture.py list   [--kind listing]

Every later tool reads only checked captures in reddit/captures/. Page loads are
counted per run (30 by default, 60 at most) and over any 24 hours (120 at most).
"""

import argparse
import datetime
import json
import os
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402
from parsing import iso, parse_age, parse_count, parse_iso  # noqa: E402,F401

DEFAULT_DIR = "reddit"
DEFAULT_LIMIT = 30
MAX_LIMIT = 60
DAILY_MAX = 120
RUN_WINDOW = datetime.timedelta(hours=4)  # a start within this of the last one continues it
COOLDOWN = datetime.timedelta(hours=24)
DAY = datetime.timedelta(hours=24)
MAX_TEXT = 4000
MAX_TITLE = 300
LISTING_SOURCES = ("home", "new", "hot", "top", "rising", "search")
PROFILE_TYPES = ("post", "comment")
RUN_FILE = "run.json"
_FILE = re.compile(r"^(\d{4,})-([a-z_]+)\.json$")

# field -> how to read it. Each kind lists its required and optional item fields.
POST_FIELDS = {"url": "url", "title": "title", "sub": "sub", "author": "author", "age": "age",
               "created": "age", "score": "count", "comments": "count", "flair": "text",
               "locked": "bool", "body": "text"}
KINDS = {
    "sub_search": {"required": ("name",), "fields": {"name": "sub", "members": "count", "description": "text",
                                                     "url": "url"}},
    "sub_about": {"required": ("name",), "fields": {"name": "sub", "members": "count",
                                                    "weekly_visitors": "count", "weekly_contributions": "count",
                                                    "description": "text", "created": "age"}},
    "user_about": {"required": ("name",), "fields": {"name": "author", "karma": "count", "created": "age"}},
    "rules": {"required": ("title",), "fields": {"title": "title", "text": "text"}},
    "listing": {"required": ("url", "title", "sub"), "fields": POST_FIELDS},
    "thread": {"required": ("text",), "fields": {"text": "text", "author": "author", "age": "age",
                                                 "created": "age", "score": "count", "url": "url",
                                                 "depth": "int"}},
    "profile": {"required": ("url", "sub", "type"), "fields": {"url": "url", "sub": "sub", "type": "type",
                                                               "title": "title", "text": "text", "score": "count",
                                                               "comments": "count", "age": "age",
                                                               "created": "age", "removed": "bool"}},
}
TOP_FIELDS = {"kind", "url", "captured", "pages", "blocked", "note", "items", "source", "query", "sub", "post"}
NON_NEGATIVE = ("members", "weekly_visitors", "weekly_contributions")
_AUTHOR = re.compile(r"^[A-Za-z0-9_-]{1,20}$")


def _author(raw):
    name = re.sub(r"^/?u/", "", str(raw or "").strip(), flags=re.I)
    if name in ("", "[deleted]", "[removed]"):
        return name
    if not _AUTHOR.match(name):
        raise ValueError("not a Reddit username: %r" % raw)
    return name


def _field(how, value, now, out, name):
    """Read one field into out. Raises ValueError with a plain reason."""
    if how == "url":
        if not store.is_reddit_url(value):
            raise ValueError("%s is not a reddit.com link: %r" % (name, value))
        out[name] = str(value).strip()
    elif how == "sub":
        out[name] = store.sub_name(value)
    elif how == "author":
        out[name] = _author(value)
    elif how == "count":
        out[name] = parse_count(value)
    elif how == "int":
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("%s must be a whole number of 0 or more" % name)
        out[name] = value
    elif how == "bool":
        if not isinstance(value, bool):
            raise ValueError("%s must be true or false" % name)
        out[name] = value
    elif how == "type":
        if value not in PROFILE_TYPES:
            raise ValueError("type must be one of %s, got %r" % (", ".join(PROFILE_TYPES), value))
        out[name] = value
    elif how == "age":
        out["created"] = parse_age(value, now) or out.get("created")
        if name == "age":
            out["age_text"] = str(value or "").strip()
    else:  # text and title
        text = store.clean_text(value)
        limit = MAX_TITLE if how == "title" else MAX_TEXT
        if len(text) > limit:
            text, out["truncated"] = text[:limit], True
        out[name] = text


def _item(raw, kind, now):
    spec = KINDS[kind]
    if not isinstance(raw, dict):
        raise ValueError("is not an object")
    unknown = sorted(set(raw) - set(spec["fields"]))
    if unknown:
        raise ValueError("unknown field(s): %s" % ", ".join(unknown))
    problems = ["%s is missing" % f for f in spec["required"] if raw.get(f) in (None, "")]
    out = {"truncated": False}
    for name, how in spec["fields"].items():
        if name in raw and raw[name] is not None:
            try:
                _field(how, raw[name], now, out, name)
            except ValueError as err:
                problems.append(str(err))
    for name in NON_NEGATIVE:
        if out.get(name) is not None and out[name] < 0:
            problems.append("%s cannot be negative" % name)
    if problems:
        raise ValueError("; ".join(problems))
    for name, how in spec["fields"].items():
        if how in ("text", "title") and name not in out:
            out[name] = ""
        if how == "bool":
            out.setdefault(name, False)
    if "author" in spec["fields"]:
        out["bot"] = store.is_bot(out.get("author"))
    if "url" in out:
        out["id"] = store.reddit_id(out["url"])
    out.setdefault("created", None)
    return out


def _any_reddit_host(url):
    try:
        parts = urlparse(str(url or "").strip())
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and (host == "reddit.com" or host.endswith(".reddit.com"))


def _blocked(raw, now):
    """A block page: record what it said and where, nothing else is checked."""
    if not _any_reddit_host(raw.get("url")):
        raise ValueError("url must be the reddit.com page that showed the block")
    return {"kind": raw.get("kind") if raw.get("kind") in KINDS else "listing", "url": str(raw["url"]).strip(),
            "pages": 1, "blocked": True, "captured": iso(now), "items": [],
            "note": store.clean_text(raw.get("note"))[:500] or "Reddit showed a block or warning"}


def normalise(raw, now):
    """Check one raw capture and return the clean version. Every problem is listed at once."""
    if not isinstance(raw, dict):
        raise ValueError("a capture must be a JSON object")
    if raw.get("blocked") is True:
        return _blocked(raw, now)
    kind = raw.get("kind")
    if kind not in KINDS:
        raise ValueError("kind must be one of %s, got %r" % (", ".join(sorted(KINDS)), kind))
    problems = ["unknown field: %s" % k for k in sorted(set(raw) - TOP_FIELDS)]
    if not store.is_reddit_url(raw.get("url")):
        problems.append("url must be the reddit.com page that was read, got %r" % raw.get("url"))
    pages = raw.get("pages", 1)
    if isinstance(pages, bool) or not isinstance(pages, int) or pages < 1:
        problems.append("pages must be a whole number of 1 or more")
    if raw.get("blocked", False) is not False:
        problems.append("blocked must be true or false")
    captured = parse_iso(raw["captured"]) if raw.get("captured") else now
    if captured is None:
        problems.append("captured must be an ISO date-time")
        captured = now
    out = {"kind": kind, "url": str(raw.get("url", "")).strip(), "pages": pages, "blocked": False,
           "note": store.clean_text(raw.get("note"))[:500], "captured": iso(captured)}
    if kind == "listing":
        if raw.get("source") not in LISTING_SOURCES:
            problems.append("source must be one of %s" % ", ".join(LISTING_SOURCES))
        out["source"] = raw.get("source")
    if kind in ("listing", "sub_search"):
        out["query"] = store.clean_text(raw.get("query"))[:200]
    if kind == "rules" or (kind == "listing" and raw.get("sub")):
        try:
            out["sub"] = store.sub_name(raw.get("sub"))
        except ValueError:
            problems.append("sub must be the subreddit this page belongs to")
    if kind == "thread":
        try:
            out["post"] = _item(raw.get("post"), "listing", captured)
        except ValueError as err:
            problems.append("post: %s" % err)
    items = raw.get("items", [])
    if not isinstance(items, list):
        problems.append("items must be a list")
        items = []
    out["items"] = []
    for number, item in enumerate(items, 1):
        try:
            clean = _item(item, kind, captured)
        except ValueError as err:
            problems.append("item %d: %s" % (number, err))
            continue
        if kind == "rules":
            clean["number"] = number
        out["items"].append(clean)
    if problems:
        raise ValueError("capture problems: " + " | ".join(problems))
    return out


def _read_run(folder):
    return store.read_json(os.path.join(folder, RUN_FILE)) or {}


def _write_run(folder, run):
    store.write_json(os.path.join(folder, RUN_FILE), run)


def _pages_last_day(run, now):
    since = iso(now - DAY)
    return sum(h["pages"] for h in run.get("history", []) if h["at"] > since)


def budget(folder, now=None):
    run = _read_run(folder)
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if not run.get("started"):
        return {"started": None, "limit": 0, "used": 0, "left": 0, "halted": run.get("halted"),
                "last_24h": _pages_last_day(run, now)}
    return {"started": run["started"], "limit": run["limit"], "used": run["used"],
            "left": max(run["limit"] - run["used"], 0), "halted": run.get("halted"),
            "last_24h": _pages_last_day(run, now)}


def halt(folder, note, now):
    """Stop all reading. Works with or without a run."""
    run = _read_run(folder)
    run["halted"], run["halted_at"] = store.clean_text(note)[:500] or "Reddit showed a block", iso(now)
    _write_run(folder, run)


def start(folder, now, limit=DEFAULT_LIMIT, user_checked=False):
    """Begin a run, or continue the last one if it started within RUN_WINDOW and did not halt.
    After a halt: wait a day, or the user checks Reddit themselves and says it is fine."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= MAX_LIMIT:
        raise ValueError("limit must be 1 to %d pages" % MAX_LIMIT)
    old = _read_run(folder)
    if old.get("halted"):
        halted_at = parse_iso(old.get("halted_at"))
        if not user_checked and halted_at and now - halted_at < COOLDOWN:
            raise ValueError("the last run halted (%s). Ask the user to open Reddit and check their account "
                             "themselves. Only when they say it is fine, start with --user-checked. "
                             "Or wait a day" % old["halted"])
    else:
        began = parse_iso(old.get("started"))
        if began and now - began < RUN_WINDOW:
            return old
    history = [h for h in old.get("history", []) if h["at"] > iso(now - DAY)]
    run = {"started": iso(now), "limit": limit, "used": 0, "halted": None, "halted_at": None, "history": history}
    _write_run(folder, run)
    return run


def _next_seq(folder):
    seqs = [int(m.group(1)) for m in (_FILE.match(n) for n in os.listdir(folder)) if m]
    return max(seqs, default=0) + 1


def add(folder, raw_path, now):
    """Check the raw capture at raw_path, store it, count its pages. Returns the stored path.
    A capture that fails the check stays where it is so Claude can fix it."""
    if os.path.dirname(os.path.abspath(raw_path)) == os.path.abspath(folder) and \
            _FILE.match(os.path.basename(raw_path)):
        raise ValueError("%s is already stored" % raw_path)
    with open(raw_path, encoding="utf-8") as fh:
        try:
            raw = json.load(fh)
        except json.JSONDecodeError as err:
            raise ValueError("%s is not valid JSON: %s" % (raw_path, err.msg))
    clean = normalise(raw, now)
    run = _read_run(folder)
    if not clean["blocked"]:
        if not run.get("started"):
            raise ValueError("no run started: run `capture.py start` first")
        if run.get("halted"):
            raise ValueError("the run halted (%s). Stop reading Reddit and tell the user" % run["halted"])
        if run["used"] + clean["pages"] > run["limit"]:
            raise ValueError("page budget used up (%d of %d). Stop here and work with what you have"
                             % (run["used"], run["limit"]))
        if _pages_last_day(run, now) + clean["pages"] > DAILY_MAX:
            raise ValueError("%d pages read in the last 24 hours, the most allowed. Stop for today" % DAILY_MAX)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "%04d-%s.json" % (_next_seq(folder), clean["kind"]))
    store.write_json(path, clean)
    run["used"] = run.get("used", 0) + clean["pages"]
    run["history"] = run.get("history", []) + [{"at": iso(now), "pages": clean["pages"]}]
    _write_run(folder, run)
    if clean["blocked"]:
        halt(folder, clean["note"], now)
    os.remove(raw_path)
    return path


def load_all(folder, kind=None):
    if not os.path.isdir(folder):
        return []
    named = [(int(m.group(1)), n, m.group(2)) for n, m in ((n, _FILE.match(n)) for n in os.listdir(folder)) if m]
    return [store.read_json(os.path.join(folder, n)) for _, n, k in sorted(named) if kind is None or k == kind]


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Check and keep what Claude read on Reddit")
    parser.add_argument("--dir", default=DEFAULT_DIR)
    sub = parser.add_subparsers(dest="cmd", required=True)
    begin = sub.add_parser("start")
    begin.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    begin.add_argument("--user-checked", action="store_true")
    sub.add_parser("add").add_argument("file")
    sub.add_parser("halt").add_argument("note")
    sub.add_parser("budget")
    sub.add_parser("list").add_argument("--kind")
    args = parser.parse_args(argv)
    folder = os.path.join(args.dir, "captures")
    os.makedirs(folder, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc)
    try:
        if args.cmd == "start":
            run = start(folder, now, args.limit, args.user_checked)
            print("run: %d of %d pages used" % (run["used"], run["limit"]))
        elif args.cmd == "add":
            path = add(folder, args.file, now)
            state = budget(folder, now)
            print("stored %s (%d of %d pages used)" % (path, state["used"], state["limit"]))
        elif args.cmd == "halt":
            halt(folder, args.note, now)
        elif args.cmd == "budget":
            print(json.dumps(budget(folder, now), indent=2))
        else:
            for cap in load_all(folder, args.kind):
                print("%s %-10s %3d items  %s" % (cap["captured"], cap["kind"], len(cap["items"]), cap["url"]))
        if args.cmd in ("add", "halt") and budget(folder, now)["halted"]:
            print("STOP: Reddit showed a block or warning (%s). Do not load more pages. "
                  "Tell the user." % budget(folder, now)["halted"])
            return 2
    except (ValueError, OSError) as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
