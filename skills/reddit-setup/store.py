"""Shared helpers: clean page text, quote it word for word, name things, save files.

Cut down from validator-skill's store.py. No tool in this pack talks to Reddit:
Claude reads pages in the user's browser and these helpers handle what it wrote down.
"""

import contextlib
import datetime
import html
import json
import os
import re
import tempfile
import time
from urllib.parse import urlparse

_TAG_BREAK = re.compile(r"<\s*/?\s*(p|br|li|div)\b[^>]*>", re.I)
_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9]*\b[^>]*>")  # real tags only: "<50 words" stays
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")  # keeps \t and \n
_CURLY = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})

REDDIT_HOSTS = {"reddit.com", "www.reddit.com", "old.reddit.com", "new.reddit.com", "sh.reddit.com"}
_THREAD = re.compile(r"^/r/\w+/comments/([a-z0-9]+)(?:/[^/]*)?(?:/(?:comment/)?([a-z0-9]+))?/?$", re.I)
_SUB = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_]{1,20}$")


def clean_text(raw):
    """HTML and entities out, whitespace tidied, paragraph breaks kept."""
    if not raw:
        return ""
    text = _TAG_BREAK.sub("\n", str(raw))
    text = _CONTROL.sub("", html.unescape(_TAG.sub("", text)))
    paragraphs = []
    for block in re.split(r"\n\s*\n", text):
        lines = (" ".join(line.split()) for line in block.split("\n"))
        joined = "\n".join(line for line in lines if line)
        if joined:
            paragraphs.append(joined)
    return "\n\n".join(paragraphs)


def _squash(text):
    return " ".join(text.translate(_CURLY).split())


def _edge_ok(text, start, end, quote):
    """A quote may not begin or end in the middle of a word ("ill" out of "bill")."""
    if quote[0].isalnum() and start > 0 and text[start - 1].isalnum():
        return False
    return not (quote[-1].isalnum() and end < len(text) and text[end].isalnum())


def verbatim(quote, text, min_words=3):
    """Is quote really in text, word for word? Whitespace and curly quotes may differ,
    nothing else may. It must start and end on word edges and have min_words words."""
    quote, text = _squash(quote or ""), _squash(text or "")
    if not quote or len(quote.split()) < min_words:
        return False
    start = text.find(quote)
    while start >= 0:
        if _edge_ok(text, start, start + len(quote), quote):
            return True
        start = text.find(quote, start + 1)
    return False


def is_reddit_url(url):
    """An https link on reddit.com itself, nothing that only looks like it."""
    try:
        parts = urlparse(str(url).strip())
    except ValueError:
        return False
    return parts.scheme == "https" and (parts.hostname or "").lower() in REDDIT_HOSTS


def reddit_id(url):
    """Reddit's own id from a thread link: t3_<post> or t1_<comment>, else None."""
    if not is_reddit_url(url):
        return None
    match = _THREAD.match(urlparse(str(url).strip()).path)
    if not match:
        return None
    post, comment = match.group(1).lower(), match.group(2)
    return "t1_" + comment.lower() if comment else "t3_" + post


def sub_name(raw):
    """'r/Espresso', '/r/espresso' and 'espresso' all give 'Espresso' or 'espresso'."""
    name = re.sub(r"^/?r/", "", str(raw or "").strip(), flags=re.I).strip("/")
    if not _SUB.match(name):
        raise ValueError("not a subreddit name: %r" % raw)
    return name


KNOWN_BOTS = {"automoderator", "remindmebot", "savevideo", "repostsleuthbot", "sneakpeekbot", "wikitextbot"}


def is_bot(handle):
    """AutoModerator, RemindMeBot, sports_bot, Foo-Bot2. Not Abbott, Talbot or ROBOT:
    the 'bot' has to read as its own word."""
    handle = re.sub(r"\d+$", "", str(handle or ""))
    if handle.lower() in KNOWN_BOTS:
        return True
    if len(handle) <= 3 or not handle.lower().endswith("bot"):
        return False
    before = handle[-4]
    return before in "_-" or (handle[-3] == "B" and (before.islower() or before.isdigit()))


def read_date(raw):
    """'2026-10-27' as a date, else None."""
    if isinstance(raw, datetime.date) and not isinstance(raw, datetime.datetime):
        return raw
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", str(raw or "")):
        return None
    try:
        return datetime.date.fromisoformat(str(raw))
    except ValueError:
        return None


def write_text(path, text):
    """A crash never leaves half a file behind. Private to the user: these files hold
    other people's posts."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, exist_ok=True)
    handle, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
    os.chmod(tmp, 0o600)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


@contextlib.contextmanager
def locked(path, wait=10.0, stale=120.0):
    """One writer at a time for path: a lock file made with O_EXCL. A lock older than
    `stale` seconds is left over from a crash and is cleared."""
    lock = path + ".lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock)), exist_ok=True)
    deadline = time.monotonic() + wait
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600))
            break
        except FileExistsError:
            try:
                if time.time() - os.path.getmtime(lock) > stale:
                    os.remove(lock)
                    continue
            except OSError:
                continue
            if time.monotonic() > deadline:
                raise ValueError("%s is busy: another step is changing it. Try again in a moment" % path)
            time.sleep(0.05)
    try:
        yield
    finally:
        try:
            os.remove(lock)
        except OSError:
            pass


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, encoding="utf-8") as fh:
        for number, line in enumerate(fh, 1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as err:
                raise ValueError("%s line %d is not valid JSON: %s" % (path, number, err.msg))
    return rows


def save_jsonl(path, rows):
    write_text(path, "".join(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n" for r in rows))


def append_jsonl(path, row):
    save_jsonl(path, load_jsonl(path) + [row])


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as err:
            raise ValueError("%s is not valid JSON: %s (line %d)" % (path, err.msg, err.lineno))


def write_json(path, data):
    write_text(path, json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
