#!/usr/bin/env python3
"""The draft register, the handoff gate and today's queue.

  python3 drafts.py new  --sub S --kind comment|post --url URL --file F --purpose help|promo
                        [--title T] [--flair F] [--when HH:MM] [--title-hint "thread title"]
  python3 drafts.py gate ID        # may Claude open this draft in the browser now? prints what to type
  python3 drafts.py done ID [--url URL_OF_YOUR_COMMENT]
  python3 drafts.py skip ID
  python3 drafts.py list
  python3 drafts.py today          # reddit/queue.md and reddit/queue.ics

A draft is only registered inside today's cap, in a sub whose rules are ok, at low
or medium risk, and within what the warm-up phase allows. The gate checks it all
again on the text as it is now, and only one draft is handed off at a time.
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
sys.path.insert(0, os.path.join(HERE, "..", "reddit-check"))
sys.path.insert(0, HERE)
import check as removal  # noqa: E402
import log as post_log  # noqa: E402
import mdsafe  # noqa: E402
import plan  # noqa: E402
import store  # noqa: E402

DEFAULT_DIR = "reddit"
OPEN = ("drafted", "handed")
MARKER = ".handoff"  # read by guard.py while a draft is in the reply box
SLOTS_FROM, SLOT_MINUTES, LAST_SLOT = 12 * 60, 90, 22 * 60
_WHEN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def _path(folder):
    return os.path.join(folder, plan.DRAFTS)


def read(folder):
    return store.load_jsonl(_path(folder))


def _save(folder, drafts):
    store.save_jsonl(_path(folder), drafts)


def _find(drafts, draft_id):
    for d in drafts:
        if d["id"] == draft_id:
            return d
    raise ValueError("no draft %s" % draft_id)


def _read_text(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read().strip()


def _vet(folder, sub, kind, url, text, purpose, today, title=None, flair=None):
    """Every rule a draft must meet, on its text as it is now. Returns the check result."""
    if purpose not in ("help", "promo"):
        raise ValueError("purpose must be help or promo")
    if kind == "comment" and not (store.reddit_id(url) or "").startswith(("t3_", "t1_")):
        raise ValueError("a comment needs the thread link it answers, not %s" % url)
    if not store.is_reddit_url(url):
        raise ValueError("url must be a reddit.com link")
    path = re.sub(r"^https://[^/]+", "", url.strip()).split("?")[0]
    if not re.match(r"^/r/%s(/|$)" % re.escape(sub), path, re.I):
        raise ValueError("the link is not in r/%s" % sub)
    if kind == "post" and not re.match(r"^/r/[^/]+/?(submit/?)?$", path, re.I):
        raise ValueError("a post needs the sub's page or its /submit page, not a thread")
    profile, _, log, _ = plan.load(folder, today)
    result = removal.run(folder, text, sub, kind, title, flair, today)
    if result["risk"] == "blocked":
        raise ValueError("blocked: " + " ".join(result["blocked"]))
    if result["risk"] == "high":
        raise ValueError("high risk of removal (%d points): %s. Fix it with /reddit-check first"
                         % (result["points"], "; ".join(r["why"] for r in result["reasons"])))
    ph = plan.phase(profile, log, today)
    if ph["links"] == "none" and result["links"]:
        raise ValueError("no links in the %s phase" % ph["name"])
    if result["promo"] and not ph["product"]:
        raise ValueError("no product mentions or self-promotion in the %s phase" % ph["name"])
    if result["promo"] and purpose != "promo":
        raise ValueError("this mentions your product or reads as self-promotion: register it as promo")
    if purpose == "promo":
        ok, why = plan.promo_allowed(profile, log, today)
        if not ok:
            raise ValueError(why)
    return result


def new_draft(folder, sub, kind, url, file, purpose, today, title=None, flair=None, when="", title_hint=""):
    """Register one draft against today's cap. Raises ValueError with the reason if it may not be made."""
    sub = store.sub_name(sub)
    if kind not in ("comment", "post"):
        raise ValueError("kind must be comment or post")
    if when and not _WHEN.match(when):
        raise ValueError("when must be a time like 18:30")
    with store.locked(_path(folder)):
        profile, _, log, drafts = plan.load(folder, today)
        if plan.left_today(profile, log, drafts, today)[kind] < 1:
            raise ValueError("today's cap for %ss is used up" % kind)
        result = _vet(folder, sub, kind, url, _read_text(file), purpose, today, title, flair)
        draft = {"id": "D%04d" % (len(drafts) + 1), "date": today.isoformat(), "sub": sub, "kind": kind,
                 "url": url.strip(), "file": file, "purpose": purpose, "status": "drafted", "risk": result["risk"],
                 "title": title or "", "flair": flair or "", "when": when, "title_hint": str(title_hint)[:300],
                 "handed": False}
        _save(folder, drafts + [draft])
    return draft


def _marker(folder):
    return os.path.join(folder, MARKER)


def gate(folder, draft_id, today):
    """Yes to a handoff, with what to type, or a ValueError saying why not. Marks the draft handed
    and leaves a marker the optional browser guard reads."""
    with store.locked(_path(folder)):
        drafts = read(folder)
        draft = _find(drafts, draft_id)
        if draft["status"] not in OPEN:
            raise ValueError("%s is %s already" % (draft_id, draft["status"]))
        busy = [d["id"] for d in drafts if d["status"] == "handed" and d["id"] != draft_id]
        if busy:
            raise ValueError("finish %s first: say done or skip" % busy[0])
        profile, _, log, _ = plan.load(folder, today)
        others = [d for d in drafts if d["id"] != draft_id]
        kind = draft["kind"]
        if plan.used_today(log, others, today)[kind] >= plan.caps(profile, log, today)[kind]:
            raise ValueError("today's cap for %ss is used up, so %s waits for another day" % (kind, draft_id))
        text = _read_text(draft["file"])
        _vet(folder, draft["sub"], kind, draft["url"], text, draft["purpose"], today, draft["title"] or None,
             draft["flair"] or None)
        draft.update(status="handed", handed=True, date=today.isoformat())
        _save(folder, drafts)
        mark = store.read_json(_marker(folder))
        if not (mark and mark.get("id") == draft_id):  # a second gate must not undo "typed"
            store.write_json(_marker(folder), {"id": draft_id, "url": draft["url"], "typed": False})
    return {"id": draft_id, "url": draft["url"], "kind": kind, "text": text, "title": draft["title"],
            "flair": draft["flair"]}


def _close(folder, draft_id, today, status, url=None):
    with store.locked(_path(folder)):
        drafts = read(folder)
        draft = _find(drafts, draft_id)
        if draft["status"] not in OPEN:
            raise ValueError("%s is %s already" % (draft_id, draft["status"]))
        entry = post_log.entry(url or draft["url"], draft["sub"], draft["kind"], draft["purpose"], status,
                               today=today, draft=draft_id)
        draft["status"] = status
        if status == "posted":
            draft["date"] = today.isoformat()  # it counts on the day it went up
        post_log.add(folder, entry)
        _save(folder, drafts)
        mark = store.read_json(_marker(folder))
        if mark and mark.get("id") == draft_id:
            os.remove(_marker(folder))
    return draft


def done(folder, draft_id, today, url=None):
    return _close(folder, draft_id, today, "posted", url)


def skip(folder, draft_id, today):
    return _close(folder, draft_id, today, "skipped")


def _slots(drafts, day):
    todays = [d for d in drafts if d["date"] == day.isoformat() and d["status"] in OPEN]
    out, minute = [], SLOTS_FROM
    for d in todays:
        if d.get("when"):
            h, m = d["when"].split(":")
            out.append((d, int(h) * 60 + int(m)))
        else:
            out.append((d, minute))
            minute = min(minute + SLOT_MINUTES, LAST_SLOT)
    return sorted(out, key=lambda pair: pair[1])


def queue_md(drafts, day):
    lines = ["# Today's queue, %s" % day.isoformat(), "",
             "Times are rough. Post when you are there, one at a time. You click Post.", "",
             "| time | draft | sub | kind | thread |", "| --- | --- | --- | --- | --- |"]
    for d, minute in _slots(drafts, day):
        lines.append("| %02d:%02d | %s | r/%s | %s | %s |" % (
            minute // 60, minute % 60, d["id"], mdsafe.md(d["sub"]), d["kind"],
            mdsafe.md(d.get("title_hint") or d.get("title") or "") or mdsafe.cite("link", d["url"])))
    if len(lines) == 6:
        lines.append("| | nothing queued | | | |")
    return "\n".join(lines) + "\n"


def ics_escape(text):
    return str(text).replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _fold(line):
    """Lines of at most 75 bytes; a continuation starts with one space."""
    out, current, limit = [], "", 75
    for ch in line:
        if len((current + ch).encode("utf-8")) > limit:
            out.append(current)
            current, limit = " " + ch, 75
        else:
            current += ch
    out.append(current)
    return "\r\n".join(out)


def ics(drafts, day, now=None):
    """A calendar file with one reminder per draft queued for day, or None when nothing is queued."""
    if not _slots(drafts, day):
        return None
    now = now or datetime.datetime.now(datetime.timezone.utc)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//reddit-agent-skill//queue//EN", "CALSCALE:GREGORIAN"]
    for d, minute in _slots(drafts, day):
        start = "%sT%02d%02d00" % (day.strftime("%Y%m%d"), minute // 60, minute % 60)
        what = "post" if d["kind"] == "post" else "reply"
        lines += ["BEGIN:VEVENT", "UID:%s-%s@reddit-agent-skill" % (d["id"], day.isoformat()),
                  "DTSTAMP:%s" % now.strftime("%Y%m%dT%H%M%SZ"), "DTSTART:%s" % start, "DURATION:PT15M",
                  "SUMMARY:%s" % ics_escape("Reddit: %s %s in r/%s" % (what, d["id"], d["sub"])),
                  "DESCRIPTION:%s" % ics_escape("Read the draft, edit it, and post it yourself if you still want "
                                                "to.\n%s\nDraft: %s" % (d["url"], d["file"])),
                  "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(line) for line in lines) + "\r\n"


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Drafts, the handoff gate and today's queue")
    parser.add_argument("--dir", default=DEFAULT_DIR)
    sub = parser.add_subparsers(dest="cmd", required=True)
    new = sub.add_parser("new")
    for name in ("sub", "url", "file"):
        new.add_argument("--" + name, required=True)
    new.add_argument("--kind", required=True, choices=("comment", "post"))
    new.add_argument("--purpose", required=True, choices=("help", "promo"))
    for name in ("title", "flair", "when", "title-hint"):
        new.add_argument("--" + name, default="")
    for name in ("gate", "skip"):
        sub.add_parser(name).add_argument("id")
    closer = sub.add_parser("done")
    closer.add_argument("id")
    closer.add_argument("--url")
    sub.add_parser("list")
    sub.add_parser("today")
    args = parser.parse_args(argv)
    today = datetime.date.today()
    try:
        if args.cmd == "new":
            d = new_draft(args.dir, args.sub, args.kind, args.url, args.file, args.purpose, today,
                          args.title or None, args.flair or None, args.when, args.title_hint)
            print("registered %s (%s risk)" % (d["id"], d["risk"]))
        elif args.cmd == "gate":
            print(json.dumps(gate(args.dir, args.id, today), indent=2, ensure_ascii=False))
        elif args.cmd in ("done", "skip"):
            d = done(args.dir, args.id, today, args.url) if args.cmd == "done" else skip(args.dir, args.id, today)
            print("%s %s and logged" % (d["id"], d["status"]))
        elif args.cmd == "list":
            for d in read(args.dir):
                print("%s %s %-8s r/%-20s %-7s %s" % (d["id"], d["date"], d["status"], d["sub"], d["kind"], d["file"]))
        else:
            drafts = read(args.dir)
            store.write_text(os.path.join(args.dir, "queue.md"), queue_md(drafts, today))
            calendar, path = ics(drafts, today), os.path.join(args.dir, "queue.ics")
            if calendar:
                store.write_text(path, calendar)
            elif os.path.exists(path):
                os.remove(path)
            print("wrote queue.md%s in %s" % (" and queue.ics" if calendar else "", args.dir))
    except (ValueError, OSError) as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
