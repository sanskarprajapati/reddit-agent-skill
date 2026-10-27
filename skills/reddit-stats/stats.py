#!/usr/bin/env python3
"""How your own posts and comments did, from your profile pages as Claude read them.

  python3 stats.py build [--days 7] [--dir reddit]   # reddit/stats.md

Only captures of your own overview, comments or submitted pages are used. Scores
are as Reddit showed them when the page was read; a later read replaces them.
"""

import argparse
import datetime
import json
import os
import re
import statistics
import sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "reddit-setup"))
import capture  # noqa: E402
import log as post_log  # noqa: E402
import mdsafe  # noqa: E402
import profile as user_profile  # noqa: E402
import store  # noqa: E402

DEFAULT_DIR = "reddit"
FEW = 10
SHOW = 3
OWN_PAGES = ("", "overview", "comments", "submitted")
PREFIX = {"comment": "t1_", "post": "t3_"}
_POST = re.compile(r"/comments/([a-z0-9]+)", re.I)


def _own(cap, username):
    parts = urlparse(cap.get("url", "")).path.lower().strip("/").split("/") + [""]
    return parts[0] in ("user", "u") and parts[1] == username.lower() and parts[2] in OWN_PAGES


def _item_id(item):
    """The item's id, worked out from a /user/me/comments/<id>/ link for a post on the profile itself."""
    if item.get("id"):
        return item["id"]
    match = _POST.search(item.get("url", ""))
    return "t3_" + match.group(1).lower() if match and item.get("type") == "post" else None


def gather(caps, username):
    """{id: item} from captures of the user's own profile, the latest read of each item winning.
    Items whose link does not fit their type (a comment linking to a post) are left out."""
    username = re.sub(r"^/?u/", "", str(username or "").strip(), flags=re.I)
    if not username:
        raise ValueError("set your username with /reddit-setup first, so only your own profile is read")
    items = {}
    for cap in sorted(caps, key=lambda c: c.get("captured", "")):
        if cap.get("kind") != "profile" or cap.get("blocked") or not _own(cap, username):
            continue
        for item in cap.get("items", []):
            rid = _item_id(item)
            if rid and rid.startswith(PREFIX.get(item.get("type"), "?")):
                items[rid] = dict(item, id=rid, read=cap.get("captured"))
    return items


def _post_of(url):
    match = _POST.search(url or "")
    return "t3_" + match.group(1).lower() if match else None


def _group(items):
    scores = [i["score"] for i in items if i.get("score") is not None]
    return {"count": len(items), "median_score": statistics.median(scores) if scores else None,
            "total_score": sum(scores), "replies": sum(i.get("comments") or 0 for i in items),
            "removed": sum(1 for i in items if i.get("removed"))}


def _purposes(rows, log):
    """{item id: help or promo}. A comment logged with only the thread link matches when exactly
    one of your comments sits in that thread."""
    out = {}
    for e in log:
        rid = store.reddit_id(e.get("url", ""))
        if not rid:
            continue
        if rid.startswith("t1_") or e.get("kind") == "post":
            out[rid] = e.get("purpose", "unknown")
            continue
        fits = [r["id"] for r in rows if r.get("type") == "comment" and _post_of(r.get("url")) == rid
                and str(r.get("sub", "")).lower() == str(e.get("sub", "")).lower() and r["id"] not in out]
        if len(fits) == 1:
            out[fits[0]] = e.get("purpose", "unknown")
    return out


def summary(items, log, today, days=None):
    log = [e for e in log if isinstance(e, dict)]
    rows = list(items.values())
    if days:
        since = (today - datetime.timedelta(days=days - 1)).isoformat()
        rows = [r for r in rows if (r.get("created") or "")[:10] >= since]
    purpose = _purposes(rows, log)
    names = {}
    for r in rows:
        r["purpose"] = purpose.get(r["id"], "unknown")
        r["sub_key"] = names.setdefault(r.get("sub", "").lower(), r.get("sub", ""))
    by = lambda key: {k: _group([r for r in rows if r.get(key) == k]) for k in sorted({r.get(key) for r in rows})}
    scored = sorted([r for r in rows if r.get("score") is not None], key=lambda r: (-r["score"], r["id"]))
    latest = max((r["read"] for r in rows if r.get("read")), default="")
    newest_read = [r for r in rows if r.get("read") == latest]
    floor = min(((r.get("created") or latest)[:10] for r in newest_read), default=latest[:10])
    not_seen = []
    for e in log:
        rid = store.reddit_id(e.get("url", ""))
        checkable = rid and (rid.startswith("t1_") or e.get("kind") == "post")
        if e.get("status") == "posted" and checkable and rid not in items \
                and floor <= str(e.get("date", "")) < latest[:10]:
            not_seen.append(e)
    out = _group(rows)
    out.update(total=len(rows), by_sub=by("sub_key"), by_kind=by("type"), by_purpose=by("purpose"),
               best=scored[:SHOW], worst=scored[max(SHOW, len(scored) - SHOW):][::-1],
               removed_items=[r for r in rows if r.get("removed")], not_seen=not_seen, few=len(rows) < FEW,
               read=latest[:10], days=days)
    return out


def _excerpt(item):
    return mdsafe.md((item.get("title") or item.get("text") or "")[:90])


def _num(value):
    return "?" if value is None else value


def _table(groups, label):
    lines = ["| %s | count | median score | replies | removed |" % label, "| --- | --- | --- | --- | --- |"]
    for name, g in groups.items():
        lines.append("| %s | %d | %s | %d | %d |" % (mdsafe.md(name), g["count"], _num(g["median_score"]),
                                                   g["replies"], g["removed"]))
    return lines


def report(out, today):
    window = " (last %d days)" % out["days"] if out.get("days") else ""
    lines = ["# How it went%s" % window, "",
             "From your own profile pages, read %s. Scores are as shown then." % (out.get("read") or "never"), ""]
    if not out["total"]:
        return "\n".join(lines + ["Nothing read yet. Open your profile's comments and posts pages first."]) + "\n"
    lines.append("%d item%s, median score %s, %d replies, %d removed." % (
        out["total"], "" if out["total"] == 1 else "s", _num(out["median_score"]), out["replies"], out["removed"]))
    if out["few"]:
        lines.append("Fewer than %d items: too few to read much into." % FEW)
    lines += [""] + _table({"r/" + k: v for k, v in out["by_sub"].items()}, "sub")
    lines += [""] + _table(out["by_kind"], "kind") + [""] + _table(out["by_purpose"], "purpose")
    for title, group in (("Did best", out["best"]), ("Did least well", out["worst"]),
                         ("Removed (Reddit's own label)", out["removed_items"])):
        if group:
            lines += ["", "## " + title, ""]
            lines += ["- %s in r/%s, score %s: %s" % (mdsafe.cite(i["id"], i["url"]), mdsafe.md(i.get("sub", "")),
                                                       _num(i.get("score")), _excerpt(i)) for i in group]
    if out["not_seen"]:
        lines += ["", "## Logged but not on the profile pages read", "",
                  "Open these to check. They may be removed, or just not loaded.", ""]
        lines += ["- %s in r/%s, %s" % (mdsafe.cite("link", e.get("url", "")), mdsafe.md(e.get("sub", "")),
                                       mdsafe.md(e.get("date", ""))) for e in out["not_seen"]]
    return "\n".join(lines) + "\n"


def build(folder, today, days=None):
    prof = user_profile.load(folder, today)
    items = gather(capture.load_all(os.path.join(folder, "captures"), kind="profile"), prof["username"])
    out = summary(items, post_log.read(folder), today, days)
    store.write_text(os.path.join(folder, "stats.md"), report(out, today))
    return out


def _main(argv=None):
    parser = argparse.ArgumentParser(description="How your own posts did")
    parser.add_argument("--dir", default=DEFAULT_DIR)
    parser.add_argument("--days", type=int)
    parser.add_argument("cmd", choices=("build",))
    args = parser.parse_args(argv)
    try:
        if args.days is not None and args.days < 1:
            raise ValueError("days must be 1 or more")
        out = build(args.dir, datetime.date.today(), args.days)
    except (ValueError, OSError) as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    print(json.dumps({k: out[k] for k in ("total", "median_score", "replies", "removed", "few")}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
