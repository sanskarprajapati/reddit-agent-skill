#!/usr/bin/env python3
"""The AI tells: phrasing and layout that make a Reddit reply read as machine-written.

  python3 tells.py FILE [--never "word, word"]

The list is data, so it can grow. Each hit says what it found and gives up to three
examples. Finding no tells does not mean a text is human; it means none of these.
"""

import argparse
import json
import re
import sys

_I = re.I
AI_WORDS = ("delve", "delves", "delving", "tapestry", "testament", "showcase", "showcases", "showcasing", "pivotal",
            "robust", "seamless", "seamlessly", "leverage", "leveraging", "game-changer", "elevate",
            "embark", "realm", "foster", "furthermore", "moreover", "myriad", "plethora",
            "ever-evolving", "intricate", "nuanced", "meticulous", "meticulously",
            "comprehensive", "streamline", "holistic", "synergy", "paramount", "underscore", "underscores",
            "notably", "vibrant", "bustling", "invaluable")

# id, label, pattern, weight per hit kind, minimum count to be a hit
TELLS = (
    # an en dash between numbers or prices is a range, not a tell
    ("em_dash", "em dashes", re.compile("—|(?<![\\d$€£]) – (?![\\d$€£])"), 2, 1),
    ("stock_opener", "stock opener", re.compile(
        r"^\W*(great question|good question|excellent question|great point|absolutely|certainly|of course|"
        r"sure thing|i'?d be happy to|as an ai)\s*[,!.:]", _I), 2, 1),
    ("stock_closer", "stock closer", re.compile(
        r"\b(i )?hope (this|that) (answer )?helps|feel free to (ask|reach out|let me know)|"
        r"let me know if you have (any )?(other |more )?questions|happy to help|best of luck on your journey",
        _I), 2, 1),
    ("ai_words", "words AI leans on", re.compile(r"\b(%s)\b" % "|".join(re.escape(w) for w in AI_WORDS), _I), 1, 1),
    ("not_x_but_y", '"not X, it\'s Y" framing', re.compile(
        r"\b(?:it'?s|it is|this is|this|that'?s|that is)\s+(?:not|isn'?t)\s+(?:just\s+|only\s+)?[^.!?\n]{1,60}?"
        r"(?:[,;]\s*(?:it'?s|it is|rather)|\.\s*(?:it'?s|it is))\b", _I), 2, 1),
    ("headings", "markdown headings", re.compile(r"(?m)^#{1,6}\s"), 2, 1),
    ("bold", "bold phrases", re.compile(r"\*\*[^*\n]+\*\*"), 1, 2),
    ("list", "tidy bullet list", re.compile("(?m)^\\s*(?:[-*•]|\\d+[.)])\\s+"), 1, 3),
    ("emoji", "emoji", re.compile("[\U0001F300-\U0001FAFF☀-➿]"), 1, 2),
)


def _never_patterns(never):
    phrases = []
    for entry in never or ():
        phrases += [p.strip() for p in str(entry).split(",") if p.strip()]
    return [re.compile(r"(?<!\w)%s(?!\w)" % re.escape(p), _I) for p in phrases]


def detect(text, never=()):
    """Every tell found in text, with a count and up to three examples."""
    text = str(text or "")
    hits = []
    for tell_id, label, pattern, weight, minimum in TELLS:
        found = [m.group(0).strip() for m in pattern.finditer(text)]
        if len(found) >= minimum:
            count = len(set(f.lower() for f in found)) if tell_id == "ai_words" else len(found)
            hits.append({"id": tell_id, "label": label, "count": count, "examples": found[:3],
                         "weight": min(weight * count, 3) if tell_id == "ai_words" else weight})
    never_found = [m.group(0) for p in _never_patterns(never) for m in p.finditer(text)]
    if never_found:
        hits.append({"id": "never_list", "label": "words on your never list", "count": len(never_found),
                     "examples": never_found[:3], "weight": 2})
    return hits


def weight(hits):
    return sum(h["weight"] for h in hits)


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Find AI tells in a draft")
    parser.add_argument("file")
    parser.add_argument("--never", default="")
    args = parser.parse_args(argv)
    try:
        with open(args.file, encoding="utf-8") as fh:
            hits = detect(fh.read(), [args.never])
    except (OSError, ValueError) as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    print(json.dumps({"weight": weight(hits), "tells": hits}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
