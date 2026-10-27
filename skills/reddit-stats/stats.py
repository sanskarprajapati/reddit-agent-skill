#!/usr/bin/env python3
"""How your own posts and comments did, from your profile pages as Claude read them.

  python3 stats.py build [--dir reddit]   # reddit/stats.md

Only captures of your own profile (reddit.com/user/<your name>/...) are used. Scores
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


def _own(cap, username):
    parts = urlparse(cap.get("url", "")).path.lower().strip("/").split("/")
    return len(parts) >= 2 and parts[0] in ("user", "u") and parts[1] == username.lower()


def gather(caps, username):
    """{id: item} from captures of the user's own profile, the latest read of each item winning."""
    username = re.sub(r"^/?u/", "", str(username or "").strip(), flags=re.I)
    if not username:
        raise ValueError("set your username in profile.json first, so only your own profile is read")
    items = {}
    for cap in sorted(caps, key=lambda c: c.get("captured", "")):
        if cap.get("kind") != "profile" or cap.get("blocked") or not _own(cap, username):
            continue
        for item in cap.get("items", []):
            if item.get("id"):
                items[item["id"]] = dict(item, read=cap.get("captured"))
    return items


def _ids(url):
    """The comment id and the post id a link points at."""
    rid = store.reddit_id(url or "")
    post = re.search(r"/comments/([a-z0-9]+)", url or "", re.I)
    return rid, ("t3_" + post.group(1).lower()) if post else None


def _group(items):
    scores = [i["score"] for i in items if i.get("score") is not None]
    return {"count": len(items), "median_score": statistics.median(scores) if scores else None,
            "total_score": sum(scores), "replies": sum(i.get("comments") or 0 for i in items),
            "removed": sum(1 for i in items if i.get("removed"))}


def summary(items, log, today):
    purpose_by_id = {}
    for e in log:
        if e.get("status") == "posted":
            rid, _ = _ids(e.get("url"))
            if rid:
                purpose_by_id[rid] = e.get("purpose", "unknown")
    rows = list(items.values())
    for r in rows:
        r["purpose"] = purpose_by_id.get(r["id"], "unknown")
    by = lambda key: {k: _group([r for r in rows if r.get(key) == k]) for k in sorted({r.get(key) for r in rows})}
    scored = sorted([r for r in rows if r.get("score") is not None], key=lambda r: (-r["score"], r["id"]))
    reads = [r["read"] for r in rows if r.get("read")]
    since = min(reads)[:10] if reads else today.isoformat()
    not_seen = []
    for e in log:
        rid, _ = _ids(e.get("url"))
        if e.get("status") == "posted" and rid and rid.startswith("t1_") and rid not in items \
                and e.get("date", "") < since:
            not_seen.append(e)
    out = _group(rows)
    out.update(total=len(rows), by_sub=by("sub"), by_kind=by("type"), by_purpose=by("purpose"),
               best=scored[:SHOW], worst=scored[-SHOW:][::-1] if len(scored) > SHOW else [],
               removed_items=[r for r in rows if r.get("removed")], not_seen=not_seen, few=len(rows) < FEW)
    return out


def _excerpt(item):
    return mdsafe.md((item.get("title") or item.get("text") or "")[:90])


def _table(groups, label):
    lines = ["| %s | count | median score | replies | removed |" % label, "| --- | --- | --- | --- | --- |"]
    for name, g in groups.items():
        lines.append("| %s | %d | %s | %d | %d |" % (mdsafe.md(name), g["count"],
                                                   g["median_score"] if g["median_score"] is not None else "?",
                                                   g["replies"], g["removed"]))
    return lines


def report(out, today):
    lines = ["# How it went", "", "Read %s from your own profile pages. Scores are as shown when read." %
             today.isoformat(), ""]
    if not out["total"]:
        return "\n".join(lines + ["Nothing read yet. Open your profile's posts and comments pages first."]) + "\n"
    lines.append("%d items, median score %s, %d replies, %d removed." % (
        out["total"], out["median_score"], out["replies"], out["removed"]))
    if out["few"]:
        lines.append("Fewer than %d items: too few to read much into." % FEW)
    lines += [""] + _table({"r/" + k: v for k, v in out["by_sub"].items()}, "sub")
    lines += [""] + _table(out["by_kind"], "kind") + [""] + _table(out["by_purpose"], "purpose")
    for title, group in (("Did best", out["best"]), ("Did least well", out["worst"]),
                         ("Removed (Reddit's own label)", out["removed_items"])):
        if group:
            lines += ["", "## " + title, ""]
            lines += ["- %s in r/%s, score %s: %s" % (mdsafe.cite(i["id"], i["url"]), mdsafe.md(i["sub"]),
                                                       i.get("score"), _excerpt(i)) for i in group]
    if out["not_seen"]:
        lines += ["", "## Logged but not on the profile pages read", "",
                  "Open these to check. They may be removed, or just not loaded.", ""]
        lines += ["- %s in r/%s, %s" % (mdsafe.cite("link", e["url"]), mdsafe.md(e["sub"]), e["date"])
                  for e in out["not_seen"]]
    return "\n".join(lines) + "\n"


def build(folder, today):
    prof = user_profile.load(folder, today)
    items = gather(capture.load_all(os.path.join(folder, "captures"), kind="profile"), prof["username"])
    out = summary(items, post_log.read(folder), today)
    store.write_text(os.path.join(folder, "stats.md"), report(out, today))
    return out


def _main(argv=None):
    parser = argparse.ArgumentParser(description="How your own posts did")
    parser.add_argument("--dir", default=DEFAULT_DIR)
    parser.add_argument("cmd", choices=("build",))
    args = parser.parse_args(argv)
    try:
        out = build(args.dir, datetime.date.today())
    except (ValueError, OSError) as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    print(json.dumps({k: out[k] for k in ("total", "median_score", "replies", "removed", "few")}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
