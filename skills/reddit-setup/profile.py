#!/usr/bin/env python3
"""reddit/profile.json: who the user is on Reddit, what they care about, their caps.

  python3 profile.py init     [--dir reddit]   # write a template to fill in
  python3 profile.py check    [--dir reddit]   # check it, print the clean version
"""

import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import store  # noqa: E402

DEFAULT_DIR = "reddit"
FILE = "profile.json"
HARD_CEILING = 10  # drafts a day, whatever anyone asks
CAP_KEYS = ("comments_per_day", "posts_per_day")
KEYS = {"username", "topics", "terms", "knows", "account", "product", "caps", "notes", "posting"}
# manual: you click Post. approved: Claude clicks it, only for a draft you approved word for word.
POSTING = ("manual", "approved")
SECOND_ACCOUNT_KEYS = {"accounts", "alt_accounts", "alts", "usernames", "other_accounts"}
_USER = re.compile(r"^[A-Za-z0-9_-]{3,20}$")

TEMPLATE = {
    "username": "",
    "topics": ["what you know and care about, in a few words"],
    "terms": ["words people use when they ask about it"],
    "knows": ["things you know first-hand, one per line"],
    "account": {"created": "YYYY-MM-DD", "karma": 0},
    "product": None,
    "caps": {},
    "notes": "",
    "posting": "manual",
}


def _words(value, name, problems, required=False):
    if value is None:
        value = []
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        problems.append("%s must be a list of text" % name)
        return []
    clean = [" ".join(v.split()) for v in value if v.strip()]
    if required and not clean:
        problems.append("%s needs at least one entry" % name)
    return clean


def _whole(value):
    return not isinstance(value, bool) and isinstance(value, int)


def check(data, today):
    """Return the clean profile, or raise ValueError listing every problem."""
    if not isinstance(data, dict):
        raise ValueError("profile must be a JSON object")
    if SECOND_ACCOUNT_KEYS & set(data):
        raise ValueError("this pack works with one account only, yours. Remove %s"
                         % ", ".join(sorted(SECOND_ACCOUNT_KEYS & set(data))))
    problems = ["unknown key: %s" % k for k in sorted(set(data) - KEYS)]
    out = {"notes": str(data.get("notes") or ""), "posting": data.get("posting") or "manual"}
    if out["posting"] not in POSTING:
        problems.append("posting must be manual or approved; nothing is posted unattended")

    username = re.sub(r"^/?u/", "", str(data.get("username") or "").strip(), flags=re.I)
    if username and not _USER.match(username):
        problems.append("username must be 3 to 20 letters, digits, _ or -")
    out["username"] = username
    out["topics"] = _words(data.get("topics"), "topics", problems, required=True)
    out["terms"] = _words(data.get("terms"), "terms", problems)
    out["knows"] = _words(data.get("knows"), "knows", problems)

    account = data.get("account") or {}
    created = store.read_date(account.get("created")) if isinstance(account, dict) else None
    karma = account.get("karma") if isinstance(account, dict) else None
    if created is None:
        problems.append("account.created must be a real YYYY-MM-DD date")
    elif created > today:
        problems.append("account.created is in the future")
    if not _whole(karma):
        problems.append("account.karma must be a whole number")
    out["account"] = {"created": created.isoformat() if created else None, "karma": karma if _whole(karma) else 0,
                      "age_days": (today - created).days if created and created <= today else 0}

    product = data.get("product")
    if product is not None:
        fields = [product.get(k, "") for k in ("name", "what", "url")] if isinstance(product, dict) else [None]
        if not all(isinstance(f, str) for f in fields) or not fields[0].strip() or not fields[1].strip():
            problems.append("product needs a name and a line on what it is, as text (or set it to null)")
        else:
            product = {"name": product["name"].strip(), "what": " ".join(product["what"].split()),
                       "url": product.get("url", "").strip()}
    out["product"] = product

    caps = data.get("caps") or {}
    if not isinstance(caps, dict):
        problems.append("caps must be an object")
        caps = {}
    for key, value in caps.items():
        if key not in CAP_KEYS:
            problems.append("caps can only set %s, not %s" % (" and ".join(CAP_KEYS), key))
        elif not _whole(value) or value < 0:
            problems.append("caps.%s must be a whole number of 0 or more" % key)
        elif value > HARD_CEILING:
            problems.append("caps.%s is over the hard ceiling of %d a day" % (key, HARD_CEILING))
    out["caps"] = {k: v for k, v in caps.items() if k in CAP_KEYS}
    if all(_whole(v) for v in out["caps"].values()) and sum(out["caps"].values()) > HARD_CEILING:
        problems.append("caps together allow %d drafts a day, over the hard ceiling of %d"
                        % (sum(out["caps"].values()), HARD_CEILING))

    if problems:
        raise ValueError("profile problems: " + " | ".join(problems))
    return out


def init(folder):
    path = os.path.join(folder, FILE)
    if os.path.exists(path):
        raise FileExistsError("%s already exists" % path)
    store.write_json(path, TEMPLATE)
    return path


def read(folder):
    data = store.read_json(os.path.join(folder, FILE))
    if data is None:
        raise ValueError("no %s in %s yet: run /reddit-setup first" % (FILE, folder))
    return data


def load(folder, today=None):
    """The checked profile. Other tools call this."""
    return check(read(folder), today or datetime.date.today())


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Your Reddit profile for this pack")
    parser.add_argument("--dir", default=DEFAULT_DIR)
    parser.add_argument("cmd", choices=("init", "check"))
    args = parser.parse_args(argv)
    try:
        if args.cmd == "init":
            print("wrote %s: fill it in, then run check" % init(args.dir))
        else:
            print(json.dumps(load(args.dir), indent=2, ensure_ascii=False))
    except (ValueError, OSError) as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
