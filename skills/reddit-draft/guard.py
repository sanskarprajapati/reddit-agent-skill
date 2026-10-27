#!/usr/bin/env python3
"""An optional PreToolUse hook: a backstop that stops browser actions this pack never takes.

Add to .claude/settings.json in your project (see the README for the full snippet):

  "PreToolUse": [{"matcher": "mcp__claude-in-chrome__.*|mcp__playwright__.*",
                  "hooks": [{"type": "command", "command": "python3 <path>/guard.py"}]}]

Always denied: every page script; typing with submit on; clicks on a vote arrow,
Join, Follow, Award, Share, Report, Hide, Block, Message or Chat; and Reddit's
messages, chat, mod mail, notifications, settings and login pages.

Sending (Comment, Post, Reply, Save, Submit, Send, or Ctrl/Cmd plus Enter) works
through the handoff marker that `drafts.py gate` leaves in reddit/.handoff:
- posting "manual", or a draft the user did not approve: once the draft is typed,
  every click and Enter is denied until done or skip. The user sends it.
- posting "approved" and this exact text approved today: after the draft is typed,
  one click or one Ctrl+Enter is allowed, which is the send. Then everything locks.
A click given only as a ref or screen position carries no label, which is why the
lock works on "typed" and "sent" rather than on what the button says.
"""

import json
import os
import re
import sys
from urllib.parse import urlparse

BROWSER_TOOL = re.compile(r"chrome|playwright|browser|puppeteer", re.I)
SCRIPT_TOOL = re.compile(r"javascript|evaluate|execute|script|run_code", re.I)
CLICK_TOOL = re.compile(r"click|tap|drag|select_option|hover", re.I)
TYPE_TOOL = re.compile(r"type|fill|form_input", re.I)
KEY_TOOL = re.compile(r"press|key", re.I)
SEND = re.compile(r"\b(comment|post|save|submit|send|reply)\b", re.I)
NEVER = re.compile(r"\b(upvote|downvote|vote|join|joined|leave|follow|award|share|report|block|hide|message|chat)\b",
                   re.I)
EDITOR = re.compile(r"add a comment|join the conversation|comment box|reply box|text box|editor|text field|"
                    r"input|title field|body field|reply link", re.I)
SUBMIT_KEYS = re.compile(r"(ctrl|control|cmd|command|meta|super|win|controlormeta)\s*\+\s*(kp_)?(return|enter)", re.I)
ENTER = re.compile(r"\b(return|enter|kp_enter)\b", re.I)
URL = re.compile(r"(?:https?://)?(?:[\w-]+\.)*reddit\.com(?::\d+)?/[^\s'\"<>]*|https?://[^\s'\"<>]+", re.I)
PRIVATE_PATHS = {"message", "messages", "chat", "notifications", "settings", "prefs", "login", "register", "account",
                 "password", "mail"}
PRIVATE_HOSTS = {"chat.reddit.com", "mod.reddit.com"}
TARGET_KEYS = ("element", "text", "selector", "query", "name", "label", "target", "description")


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
        first = parts.path.strip("/").split("/")[0].lower()
        if host in PRIVATE_HOSTS or first in PRIVATE_PATHS:
            return True
    return False


def _label(target, words):
    """Does a click's description name one of these controls? Editor boxes do not count."""
    rest = EDITOR.sub(" ", target)
    return bool(words.search(rest)) and ("button" in target.lower() or "arrow" in target.lower()
                                         or len(target.split()) <= 3)


def _deny(why):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": "reddit-agent-skill: %s. You click Post: "
                                                               "do this yourself if you want it." % why}}


def _marker_path(folder):
    return os.path.join(folder, ".handoff") if folder else None


def _read_marker(folder):
    path = _marker_path(folder)
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (TypeError, OSError, ValueError):
        return None


def _write_marker(folder, mark):
    try:
        with open(_marker_path(folder), "w", encoding="utf-8") as fh:
            json.dump(mark, fh)
    except OSError:
        pass


def _one_send(mark, folder):
    """The single send an approved, typed draft may have. True if it is still unused."""
    if mark and mark.get("may_submit") and mark.get("typed") and not mark.get("submitted"):
        mark["submitted"] = True
        _write_marker(folder, mark)
        return True
    return False


def decide(event, folder=None):
    """None to allow, or the deny output. folder is the reddit/ folder holding the handoff marker."""
    tool = str(event.get("tool_name", ""))
    data = event.get("tool_input") or {}
    if not BROWSER_TOOL.search(tool) or not isinstance(data, dict):
        return None
    every = list(_strings(data))
    action = str(data.get("action", "")).lower()
    if SCRIPT_TOOL.search(tool):
        return _deny("this pack never runs scripts on a page")
    if any(_private(s) for s in every):
        return _deny("this pack never opens messages, chat, mod mail, notifications, settings or login pages")
    if data.get("submit") or data.get("submitForm"):
        return _deny("type first, then send with one click")
    clicking = bool(CLICK_TOOL.search(tool)) or "click" in action or "drag" in action
    typing = bool(TYPE_TOOL.search(tool)) or action == "type"
    pressing = (bool(KEY_TOOL.search(tool)) and not typing) or action == "key"
    targets = [str(data[k]) for k in TARGET_KEYS if isinstance(data.get(k), str)] if clicking else []
    for target in targets:
        if _label(target, NEVER):
            return _deny("this pack never votes, joins, follows, awards, reports, hides or messages")
    mark = _read_marker(folder)
    keyed_send = any(SUBMIT_KEYS.search(s) for s in every)
    named_send = any(_label(t, SEND) for t in targets)
    typed = bool(mark and mark.get("typed"))
    if keyed_send or named_send or (typed and (clicking or (pressing and any(ENTER.search(s) for s in every)))):
        if _one_send(mark, folder):
            return None
        if mark and mark.get("submitted"):
            return _deny("draft %s was sent. Say done, and nothing more is clicked" % mark.get("id", ""))
        if mark and mark.get("may_submit") and not typed:
            return _deny("type the approved draft first")
        return _deny("this draft is not approved for posting, so the user clicks Post")
    if mark is not None and typing and not typed:
        mark["typed"] = True
        _write_marker(folder, mark)
    return None
    every = list(_strings(data))
    action = str(data.get("action", "")).lower()
    if SCRIPT_TOOL.search(tool):
        return _deny("this pack never runs scripts on a page")
    if any(_private(s) for s in every):
        return _deny("this pack never opens messages, chat, mod mail, notifications, settings or login pages")
    if any(SUBMIT_KEYS.search(s) for s in every):
        return _deny("Ctrl, Cmd or Meta plus Enter would send the comment")
    if data.get("submit") or data.get("submitForm"):
        return _deny("typing with submit on would send the comment")
    clicking = bool(CLICK_TOOL.search(tool)) or "click" in action or "drag" in action
    typing = bool(TYPE_TOOL.search(tool)) or action == "type"
    pressing = (bool(KEY_TOOL.search(tool)) and not typing) or action == "key"
    if clicking:
        for target in (str(data[k]) for k in TARGET_KEYS if isinstance(data.get(k), str)):
            if _sending_label(target):
                return _deny("clicking %r could send, vote, join or message" % target[:60])
    mark = _read_marker(folder)
    if mark is not None:
        if mark.get("typed") and (clicking or (pressing and any(ENTER.search(s) for s in every))):
            return _deny("draft %s is in the box. From here on only the user clicks" % mark.get("id", ""))
        if typing and not mark.get("typed"):
            mark["typed"] = True
            _write_marker(folder, mark)
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
