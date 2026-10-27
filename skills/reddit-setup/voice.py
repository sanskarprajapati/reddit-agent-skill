#!/usr/bin/env python3
"""How the user really writes. Drafts follow it.

reddit/voice.md holds what the user says about their writing. reddit/samples.jsonl holds
comments they wrote themselves, one JSON line each, kept apart so their text can never
turn into headings or quirks.

  python3 voice.py init            [--dir reddit]   # write the voice.md template
  python3 voice.py add-sample FILE [--dir reddit]   # one sample per file, the whole file
  python3 voice.py import-profile  [--dir reddit]   # your own comments from profile captures
  python3 voice.py check           [--dir reddit]   # every quirk backed by a sample, enough samples
  python3 voice.py measure         [--dir reddit]   # plain numbers from the samples
"""

import argparse
import collections
import json
import os
import re
import sys
from urllib.parse import urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import capture  # noqa: E402
import profile as user_profile  # noqa: E402
import store  # noqa: E402

DEFAULT_DIR = "reddit"
FILE = "voice.md"
SAMPLES = "samples.jsonl"
MIN_SAMPLES = 5
MIN_EXAMPLE_CHARS = 6
SECTIONS = {"about me": "about", "things i know first-hand": "knows", "words i use": "use",
            "words i never use": "never", "quirks": "quirks"}
_COMMENT = re.compile(r"<!--.*?-->", re.S)
_HEADING = re.compile(r"^#{2,}\s")
_QUIRK = re.compile(r'^(.*?):\s*"(.+)"\s*$')
_SENTENCE = re.compile(r"[^.!?\n]+[.!?]*")
_WORD = re.compile(r"[\w']+")

TEMPLATE = """# My Reddit voice

<!-- Drafts follow this file. Write it the way you talk. Lines inside these
arrows are help text and are ignored. Your sample comments are kept in
samples.jsonl, not here. -->

## About me
<!-- A few lines: what you do, where you are coming from. -->

## Things I know first-hand
<!-- One per line, starting with "- ". Drafts only claim what is here. -->

## Words I use
<!-- Slang, short forms, how you say yes and no. -->

## Words I never use
<!-- Words that are not you. Drafts avoid them. -->

## Quirks
<!-- One per line, with an example copied word for word from one of your samples:
- lowercase almost everywhere: "honestly i just use a moka pot"
Only habits you really have. The check refuses an example it cannot find. -->
"""


def _bullets(lines):
    return [line[2:].strip() for line in lines if line.startswith("- ") and line[2:].strip()]


def parse(text):
    text = _COMMENT.sub("", text)
    parts = {key: [] for key in SECTIONS.values()}
    unknown, current = [], None
    for line in text.splitlines():
        if _HEADING.match(line):
            heading = line.lstrip("#").strip()
            current = SECTIONS.get(heading.lower())
            if current is None:
                unknown.append(heading)
            continue
        if current:
            parts[current].append(line.rstrip())
    quirks = []
    for item in _bullets(parts["quirks"]):
        match = _QUIRK.match(item)
        quirks.append({"what": match.group(1).strip(), "example": match.group(2)} if match
                      else {"what": item.rstrip(":").strip(), "example": ""})
    return {"about": "\n".join(parts["about"]).strip(), "knows": _bullets(parts["knows"]),
            "use": _bullets(parts["use"]), "never": _bullets(parts["never"]), "quirks": quirks,
            "unknown_sections": unknown}


def _thin(example):
    return len(example.split()) < 2 and (len(example) < MIN_EXAMPLE_CHARS or not re.search(r"[^\W\d_]", example))


def check(doc, samples):
    """A list of problems, empty when the voice file is ready."""
    problems = []
    if len(samples) < MIN_SAMPLES:
        problems.append("need at least %d samples of your own writing, found %d" % (MIN_SAMPLES, len(samples)))
    if not doc["knows"]:
        problems.append("Things I know first-hand needs at least one line")
    for heading in doc["unknown_sections"]:
        problems.append('"%s" is not a section this pack reads. Use About me, Things I know first-hand, '
                        "Words I use, Words I never use or Quirks" % heading)
    for quirk in doc["quirks"]:
        example = quirk["example"]
        if not example:
            problems.append('quirk "%s" needs an example in quotes, copied from a sample' % quirk["what"])
        elif _thin(example):
            problems.append('quirk example "%s" is too short to prove anything: use two words or more' % example)
        elif not any(store.verbatim(example, s, min_words=1) for s in samples):
            problems.append('quirk example "%s" is not in any sample word for word' % example)
    return problems


def measure(samples):
    """Plain numbers that describe the samples. Claude reads them; nothing is scored."""
    if not samples:
        return {"samples": 0}
    sentences = [s.strip() for text in samples for s in _SENTENCE.findall(text) if s.strip()]
    starts = [s for s in sentences if s[0].isalpha()]
    words = [len(_WORD.findall(text)) for text in samples]
    first = collections.Counter(_WORD.findall(text.lower())[0] for text in samples if _WORD.findall(text))
    joined = "\n".join(samples)
    return {
        "samples": len(samples),
        "avg_words": round(sum(words) / len(samples), 1),
        "avg_sentence_words": round(sum(len(_WORD.findall(s)) for s in sentences) / max(len(sentences), 1), 1),
        "lowercase_start": round(sum(1 for s in starts if s[0].islower()) / max(len(starts), 1), 2),
        "ends_without_stop": round(sum(1 for t in samples if t.rstrip()[-1:] not in ".!?") / len(samples), 2),
        "questions": joined.count("?"),
        "exclamations": joined.count("!"),
        "em_dashes": joined.count("—"),
        "openers": sorted(word for word, n in first.items() if n >= 2),
    }


def read_samples(folder):
    return [row["text"] for row in store.load_jsonl(os.path.join(folder, SAMPLES)) if row.get("text")]


def add_samples(folder, texts, source="pasted"):
    """Add samples, skipping blanks and ones already kept. Returns how many were added."""
    path = os.path.join(folder, SAMPLES)
    old = store.load_jsonl(path)
    have = [row.get("text") for row in old]
    new = []
    for text in texts:
        text = str(text or "").strip()
        if text and text not in have:
            have.append(text)
            new.append({"text": text, "source": source})
    if new:
        store.save_jsonl(path, old + new)
    return len(new)


def samples_from_profile(cap, username):
    """The user's own comments from a capture of their own profile page, and nobody else's."""
    if not username:
        raise ValueError("set your username in profile.json first, so only your own comments are used")
    path = urlparse(cap.get("url", "")).path.lower().strip("/").split("/")
    if len(path) < 2 or path[0] not in ("user", "u") or path[1] != username.lower():
        raise ValueError("%s is not your own profile page (u/%s)" % (cap.get("url"), username))
    return [i["text"] for i in cap.get("items", []) if i.get("type") == "comment" and i.get("text", "").strip()]


def import_profile(folder):
    username = user_profile.read(folder).get("username", "")
    username = re.sub(r"^/?u/", "", str(username or "").strip(), flags=re.I)
    texts = []
    for cap in capture.load_all(os.path.join(folder, "captures"), kind="profile"):
        texts += samples_from_profile(cap, username)
    return add_samples(folder, texts, source="profile")


def init(folder):
    path = os.path.join(folder, FILE)
    if os.path.exists(path):
        raise FileExistsError("%s already exists" % path)
    store.write_text(path, TEMPLATE)
    return path


def _read(folder):
    path = os.path.join(folder, FILE)
    if not os.path.exists(path):
        raise ValueError("no %s yet: run /reddit-setup first" % path)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _main(argv=None):
    parser = argparse.ArgumentParser(description="Your Reddit voice file")
    parser.add_argument("--dir", default=DEFAULT_DIR)
    parser.add_argument("cmd", choices=("init", "add-sample", "import-profile", "check", "measure"))
    parser.add_argument("file", nargs="?")
    args = parser.parse_args(argv)
    try:
        if args.cmd == "init":
            print("wrote %s" % init(args.dir))
        elif args.cmd == "add-sample":
            if not args.file:
                raise ValueError("give the file that holds one sample")
            with open(args.file, encoding="utf-8") as fh:
                print("added %d sample" % add_samples(args.dir, [fh.read()]))
        elif args.cmd == "import-profile":
            print("added %d of your comments as samples" % import_profile(args.dir))
        elif args.cmd == "measure":
            print(json.dumps(measure(read_samples(args.dir)), indent=2))
        else:
            samples = read_samples(args.dir)
            doc = parse(_read(args.dir))
            problems = check(doc, samples)
            for p in problems:
                print("- " + p)
            if problems:
                return 1
            print("voice file ready: %d samples, %d quirks" % (len(samples), len(doc["quirks"])))
    except (ValueError, OSError) as err:
        print("error: %s" % err, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main())
