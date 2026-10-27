#!/usr/bin/env python3
"""An optional PreToolUse hook: a backstop that stops browser actions this pack never takes.

Add to .claude/settings.json (see the README for the full snippet):

  "PreToolUse": [{"matcher": "mcp__claude-in-chrome__.*|mcp__playwright__.*",
                  "hooks": [{"type": "command", "command": "python3 <path>/guard.py"}]}]

It denies: clicks on a control named Comment, Post, Reply-and-send, Save, Submit,
Send, a vote arrow, Join, Follow, Award, Share, Report or Block; Ctrl or Cmd plus
Enter; scripts that click or submit; and Reddit's messages, chat, notifications,
settings and login pages. What it cannot see: a click given only as screen
coordinates. The skill's own rules cover that; this is the second line.
"""

import json
import re
import sys

BROWSER_TOOL = re.compile(r"chrome|playwright|browser|puppeteer", re.I)
SCRIPT_TOOL = re.compile(r"javascript|evaluate|execute|script", re.I)
CLICK_TOOL = re.compile(r"click|tap", re.I)
SENDING = re.compile(r"\b(comment|post|save|submit|send|reply|upvote|downvote|vote|join|follow|award|share|report|"
                     r"block|message|chat)\b", re.I)
EDITOR = re.compile(r"\b(add a comment|join the conversation|comment box|reply box|text box|editor|text field|"
                    r"input|title field|body field|reply link)\b", re.I)
SUBMIT_KEYS = re.compile(r"\b(ctrl|control|cmd|command|meta)\s*\+\s*(return|enter)\b", re.I)
ACTING_SCRIPT = re.compile(r"\.click\s*\(|submit\s*\(|dispatchEvent|requestSubmit|fetch\s*\(|XMLHttpRequest|"
                           r"sendBeacon", re.I)
PRIVATE_PAGE = re.compile(r"(?:^|//)(?:[\w-]+\.)*reddit\.com/(?:message|messages|chat|notifications|settings|prefs|"
                          r"login|register|account|password)\b|//chat\.reddit\.com", re.I)
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


def _deny(why):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": "reddit-agent-skill: %s. You click Post: "
                                                               "do this yourself if you want it." % why}}


def decide(event):
    """None to allow, or the deny output."""
    tool = str(event.get("tool_name", ""))
    data = event.get("tool_input") or {}
    if not BROWSER_TOOL.search(tool) or not isinstance(data, dict):
        return None
    every = list(_strings(data))
    if any(PRIVATE_PAGE.search(s) for s in every):
        return _deny("this pack never opens messages, chat, notifications, settings or login pages")
    if any(SUBMIT_KEYS.search(s) for s in every):
        return _deny("Ctrl or Cmd plus Enter would send the comment")
    if SCRIPT_TOOL.search(tool) and any(ACTING_SCRIPT.search(s) for s in every):
        return _deny("scripts that click, submit or send are not used by this pack")
    action = str(data.get("action", ""))
    if CLICK_TOOL.search(tool) or "click" in action.lower():
        targets = [str(data[k]) for k in TARGET_KEYS if isinstance(data.get(k), str)]
        for target in targets:
            if SENDING.search(target) and not EDITOR.search(target):
                return _deny("clicking %r could send, vote, join or message" % target[:60])
    return None


def main():
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0  # not ours to judge
    out = decide(event)
    if out:
        print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
