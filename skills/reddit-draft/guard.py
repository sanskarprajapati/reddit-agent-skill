#!/usr/bin/env python3
"""The browser guard: a PreToolUse hook that stops browser actions this pack never takes.
Optional in manual posting mode; required for approved mode (drafts.py checks it is set up).

Add to .claude/settings.json in your project (the README has the full snippet):

  "PreToolUse": [{"matcher": "mcp__claude-in-chrome__.*|mcp__playwright__.*|Bash|Write|Edit|MultiEdit",
                  "hooks": [{"type": "command", "command": "python3 <path>/guard.py"}]}]

Always denied: every page script; typing with submit on; a click whose label names a
vote, Save (Reddit's bookmark), Join, Follow, Award, Share, Report, Hide, Block,
Message or Chat; and Reddit's messages, chat, mod mail, notifications, settings and
login pages. Approving a draft, and any change to reddit/.handoff, drafts.jsonl or
profile.json, makes Claude Code ask the user first.

Sending runs through the handoff marker that `drafts.py gate` writes (reddit/.handoff).
Once anything is typed, every click and Enter is denied, with one exception: one click
on a control named Comment, Reply, Post, Submit or Send (or one Ctrl/Cmd+Enter), and
only when all of these hold: the marker says may_submit, it is dated today,
profile.json still says posting "approved", what was typed hashes to the approved
title and body with nothing extra, and the marker records the send before it happens.
A click given only as a ref or screen position carries no label, so it never sends.
After typing, every key is denied except that one Ctrl/Cmd+Enter. The send must happen
on the thread the draft was approved for. Typing outside a handoff leaves a "stray"
marker that blocks sending until the user checks the box and drafts.py clear runs.

What it cannot do: see what a ref-only click lands on before typing (so a vote by
ref is stopped by the skill's rules, not by this hook), or stop a model that sets
out to get round it. It is a seatbelt against mistakes, not a lock.
"""

import datetime
import hashlib
import json
import os
import re
import sys
import tempfile
from urllib.parse import urlparse

BROWSER_TOOL = re.compile(r"chrome|playwright|browser|puppeteer", re.I)
SCRIPT_TOOL = re.compile(r"javascript|evaluate|execute|script|run_code", re.I)
CLICK_TOOL = re.compile(r"click|tap|drag|select_option|hover", re.I)
TYPE_TOOL = re.compile(r"type|fill|form_input", re.I)
KEY_TOOL = re.compile(r"press|key", re.I)
SEND = re.compile(r"\b(comment|post|reply|submit|send)\b", re.I)
NEVER = re.compile(r"\b(upvote|downvote|vote|save|saved|join|joined|leave|follow|award|share|report|block|hide|"
                   r"message|chat)\b", re.I)
EDITOR = re.compile(r"add a comment|join the conversation|comment box|reply box|text box|editor|text field|"
                    r"input|title field|body field|reply link", re.I)
SUBMIT_KEYS = re.compile(r"(ctrl|control|cmd|command|meta|super|win|controlormeta)\s*\+\s*(kp_)?(return|enter)", re.I)
URL = re.compile(r"(?:https?://)?(?:[\w-]+\.)*reddit\.com(?::\d+)?/[^\s'\"<>]*|https?://[^\s'\"<>]+", re.I)
PRIVATE_PATHS = {"message", "messages", "chat", "notifications", "settings", "prefs", "login", "register", "account",
                 "password", "mail"}
PRIVATE_HOSTS = {"chat.reddit.com", "mod.reddit.com"}
TARGET_KEYS = ("element", "text", "selector", "query", "name", "label", "target", "description")
TYPED_KEYS = ("text", "value", "values")
STATE_FILES = re.compile(r"\.handoff\b|drafts\.jsonl|profile\.json")
EDIT_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")
_THREAD = re.compile(r"^(/r/[^/]+/comments/[a-z0-9]+)", re.I)


def sha(text):
    return hashlib.sha256(str(text).strip().encode("utf-8")).hexdigest()


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _private(text):
    for found in URL.findall(text):
        parts = urlparse(found if "://" in found else "https://" + found)
        host = (parts.hostname or "").lower()
        if not (host == "reddit.com" or host.endswith(".reddit.com")):
            continue
        if host in PRIVATE_HOSTS or parts.path.strip("/").split("/")[0].lower() in PRIVATE_PATHS:
            return True
    return False


def _names_never(target):
    return bool(NEVER.search(EDITOR.sub(" ", target)))


def _names_send(target):
    rest = EDITOR.sub(" ", target)
    return bool(SEND.search(rest)) and ("button" in target.lower() or len(target.split()) <= 3)


def _decision(kind, why):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": kind,
                                   "permissionDecisionReason": "reddit-agent-skill: %s" % why}}


def _deny(why):
    return _decision("deny", why)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (TypeError, OSError, ValueError):
        return None


def _read_marker(folder):
    return _read_json(os.path.join(folder, ".handoff")) if folder else None


def _write_marker(folder, mark):
    """True only if the marker is safely on disk."""
    try:
        handle, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
        with os.fdopen(handle, "w", encoding="utf-8") as fh:
            json.dump(mark, fh)
        os.replace(tmp, os.path.join(folder, ".handoff"))
        return True
    except (OSError, TypeError):
        return False


def _approved_text(mark):
    """Was exactly the approved title (if any) and body typed, and nothing else?"""
    typed = mark.get("typed_sha", [])
    want = [mark.get("body_sha")] + ([mark["title_sha"]] if mark.get("title_sha") else [])
    return bool(mark.get("body_sha")) and sorted(typed) == sorted(want)


def _may_send(mark, folder):
    profile = _read_json(os.path.join(folder, "profile.json")) or {}
    return (mark.get("may_submit") is True and not mark.get("submitted")
            and mark.get("date") == datetime.date.today().isoformat()
            and profile.get("posting") == "approved" and _approved_text(mark))


def _state(tool, data):
    """Approving, and changing the files that decide what may be sent, need the user's own click."""
    if tool in EDIT_TOOLS:
        path = str(data.get("file_path") or data.get("notebook_path") or "")
        if STATE_FILES.search(os.path.basename(path)):
            return _decision("ask", "%s decides what Claude may post. Allow this change only if you asked for it"
                             % os.path.basename(path))
        return None
    command = str(data.get("command", ""))
    if re.search(r"\bapprove\b", command) and "drafts" in command:
        return _decision("ask", "approving drafts lets Claude post them word for word today. Approve only text "
                                "you have read: %s" % command[-160:])
    if STATE_FILES.search(command):
        return _decision("ask", "this command touches a file that decides what Claude may post: %s" % command[-160:])
    return None


def _typed_values(data):
    out = []
    for key in TYPED_KEYS:
        value = data.get(key)
        out += [value] if isinstance(value, str) else [v for v in value if isinstance(v, str)] \
            if isinstance(value, list) else []
    for field in data.get("fields") or []:
        if isinstance(field, dict):
            out += [str(field[k]) for k in ("value", "text") if isinstance(field.get(k), str)]
    return out


def _thread(url):
    path = urlparse(str(url or "") if "://" in str(url or "") else "https://" + str(url or "")).path.lower()
    match = _THREAD.match(path)
    return match.group(1) if match else path.rstrip("/")


def decide(event, folder=None):
    """None to allow, or the hook output. folder is the reddit/ folder holding the marker and profile."""
    tool = str(event.get("tool_name", ""))
    data = event.get("tool_input") or {}
    if not isinstance(data, dict):
        return None
    if tool == "Bash" or tool in EDIT_TOOLS:
        return _state(tool, data)
    if not BROWSER_TOOL.search(tool):
        return None
    every = list(_strings(data))
    action = str(data.get("action", "")).lower()
    if SCRIPT_TOOL.search(tool):
        return _deny("this pack never runs scripts on a page")
    if any(_private(s) for s in every):
        return _deny("this pack never opens messages, chat, mod mail, notifications, settings or login pages")
    if data.get("submit") or data.get("submitForm"):
        return _deny("type first; a send is its own step")
    clicking = bool(CLICK_TOOL.search(tool)) or "click" in action or "drag" in action
    typing = bool(TYPE_TOOL.search(tool)) or action == "type"
    pressing = not typing and (bool(KEY_TOOL.search(tool)) or action == "key")
    targets = [str(data[k]) for k in TARGET_KEYS if isinstance(data.get(k), str)] if clicking else []
    if any(_names_never(t) for t in targets):
        return _deny("this pack never votes, saves, joins, follows, awards, reports, hides or messages")
    mark = _read_marker(folder)
    if mark is not None and ("navigate" in tool.lower() or action == "navigate") and data.get("url"):
        mark["last_url"] = str(data["url"])
        if not _write_marker(folder, mark):
            return _deny("could not record the page, so nothing more happens in this draft")
    if typing:
        if folder:
            mark = mark if mark is not None else {"id": None, "stray": True, "may_submit": False}
            mark["typed"] = True
            mark["typed_sha"] = mark.get("typed_sha", []) + [sha(t) for t in _typed_values(data)]
            if not _write_marker(folder, mark):
                return _deny("could not record the typing, so it is not done")
        return None
    keyed_send = pressing and any(SUBMIT_KEYS.search(s) for s in every)
    named_send = any(_names_send(t) for t in targets)
    typed = bool(mark and mark.get("typed"))
    if not (keyed_send or named_send or (typed and (clicking or pressing))):
        return None
    if not typed:
        return _deny("nothing is sent before the draft is typed")
    if not (keyed_send or named_send):
        return _deny("draft %s is in the box. Only a named Comment, Reply or Post button can send it, "
                     "and only if it was approved" % mark.get("id", ""))
    if mark.get("submitted"):
        return _deny("draft %s was already sent. Say done" % mark.get("id", ""))
    if mark.get("url") and _thread(mark.get("last_url")) != _thread(mark["url"]):
        return _deny("this page is not the thread draft %s was approved for" % mark.get("id", ""))
    if not _may_send(mark, folder):
        return _deny("draft %s is not approved as typed, today, in approved mode. The user clicks Post"
                     % mark.get("id", ""))
    mark["submitted"] = True
    if not _write_marker(folder, mark):
        return _deny("could not record the send, so it is not made")
    return None


def _folder():
    if len(sys.argv) > 1:
        return sys.argv[1]
    return os.path.join(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd(), "reddit")


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0  # not ours to judge
    out = decide(event, _folder())
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
