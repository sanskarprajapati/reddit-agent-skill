import json
import os
import tempfile
import unittest

from _load import load

guard = load("reddit-draft", "guard")
store = load("reddit-setup", "store")


def decide(tool, folder=None, **tool_input):
    return guard.decide({"tool_name": tool, "tool_input": tool_input}, folder)


class Guard(unittest.TestCase):
    def test_ignores_other_tools(self):
        self.assertIsNone(decide("Bash", command="ls"))
        self.assertIsNone(decide("Read", file_path="x"))

    def test_allows_reading_and_opening_the_editor(self):
        self.assertIsNone(decide("mcp__claude-in-chrome__navigate", url="https://www.reddit.com/r/espresso/new/"))
        self.assertIsNone(decide("mcp__claude-in-chrome__get_page_text"))
        self.assertIsNone(decide("mcp__claude-in-chrome__find", query="Reply button under the top comment"))
        self.assertIsNone(decide("mcp__claude-in-chrome__computer", action="type", text="grind finer"))
        self.assertIsNone(decide("mcp__claude-in-chrome__computer", action="left_click", coordinate=[300, 400]))
        self.assertIsNone(decide("mcp__claude-in-chrome__computer", action="left_click", ref="ref_42"))
        self.assertIsNone(decide("mcp__playwright__browser_click", element="Add a comment box"))
        self.assertIsNone(decide("mcp__playwright__browser_click", element="Join the conversation"))
        self.assertIsNone(decide("mcp__playwright__browser_click", element="Reply link under the comment by pro"))

    def test_blocks_sending_clicks_by_name(self):
        for label in ("Comment button", "Post", "Save", "Submit", "Send", "upvote arrow", "Join", "Joined", "Follow",
                      "Award", "Report", "Hide", "Comment button below the comment box",
                      "Post button under the text field"):
            self.assertIsNotNone(decide("mcp__playwright__browser_click", element=label), label)

    def test_blocks_keyboard_submit(self):
        for key in ("ctrl+Return", "cmd+Return", "Control+Enter", "Meta+Enter", "ctrl+enter", "ControlOrMeta+Enter",
                    "super+Return", "ctrl+KP_Enter"):
            self.assertIsNotNone(decide("mcp__claude-in-chrome__computer", action="key", text=key), key)
        self.assertIsNotNone(decide("mcp__playwright__browser_press_key", key="Control+Enter"))
        self.assertIsNone(decide("mcp__claude-in-chrome__computer", action="key", text="Return"))

    def test_blocks_type_with_submit(self):
        self.assertIsNotNone(decide("mcp__playwright__browser_type", element="Add a comment box", text="hi",
                                    submit=True))
        self.assertIsNone(decide("mcp__playwright__browser_type", element="Add a comment box", text="hi"))

    def test_blocks_private_pages(self):
        for url in ("https://www.reddit.com/message/compose/", "https://chat.reddit.com/",
                    "https://www.reddit.com/settings", "https://www.reddit.com/notifications",
                    "https://old.reddit.com/prefs/", "https://www.reddit.com/login",
                    "https://www.reddit.com:443/message/compose?to=x", "https://mod.reddit.com/mail/all"):
            self.assertIsNotNone(decide("mcp__claude-in-chrome__navigate", url=url), url)

    def test_blocks_every_script(self):
        for tool, arg in (("mcp__claude-in-chrome__javascript_tool", {"text": "document.title"}),
                          ("mcp__playwright__browser_evaluate", {"function": "() => 1"}),
                          ("mcp__playwright__browser_run_code", {"code": "page.title()"})):
            self.assertIsNotNone(decide(tool, **arg), tool)

    def test_output_shape(self):
        out = decide("mcp__playwright__browser_click", element="Post")
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("reddit-agent-skill", out["hookSpecificOutput"]["permissionDecisionReason"])
        json.dumps(out)


class AfterTyping(unittest.TestCase):
    """Once the draft is typed during a handoff, no more clicks or Enter until done or skip."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        store.write_json(os.path.join(self.dir, ".handoff"), {"id": "D0001", "typed": False})

    def tearDown(self):
        self.tmp.cleanup()

    def test_clicks_allowed_before_typing_then_denied(self):
        click = dict(action="left_click", ref="ref_42")
        self.assertIsNone(decide("mcp__claude-in-chrome__computer", self.dir, **click))
        self.assertIsNone(decide("mcp__claude-in-chrome__computer", self.dir, action="type", text="grind finer"))
        self.assertTrue(store.read_json(os.path.join(self.dir, ".handoff"))["typed"])
        self.assertIsNotNone(decide("mcp__claude-in-chrome__computer", self.dir, **click))
        self.assertIsNotNone(decide("mcp__claude-in-chrome__computer", self.dir, action="left_click",
                                    coordinate=[10, 10]))
        self.assertIsNotNone(decide("mcp__claude-in-chrome__computer", self.dir, action="key", text="Return"))
        self.assertIsNotNone(decide("mcp__playwright__browser_click", self.dir, element="Add a comment box"))
        self.assertIsNone(decide("mcp__claude-in-chrome__get_page_text", self.dir))

    def test_form_input_counts_as_typing(self):
        decide("mcp__claude-in-chrome__form_input", self.dir, ref="ref_3", value="grind finer")
        self.assertIsNotNone(decide("mcp__claude-in-chrome__computer", self.dir, action="left_click", ref="ref_9"))

    def test_no_marker_no_lock(self):
        os.remove(os.path.join(self.dir, ".handoff"))
        decide("mcp__claude-in-chrome__computer", self.dir, action="type", text="x")
        self.assertIsNone(decide("mcp__claude-in-chrome__computer", self.dir, action="left_click", ref="ref_42"))


def sha(text):
    import hashlib
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


TODAY = __import__("datetime").date.today().isoformat()


class ApprovedSend(unittest.TestCase):
    """An approved draft gets one named send, only after exactly the approved text is typed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        store.write_json(os.path.join(self.dir, "profile.json"), {"posting": "approved"})
        self.mark({})

    def mark(self, extra):
        base = {"id": "D0001", "typed": False, "may_submit": True, "date": TODAY, "body_sha": sha("grind finer"),
                "title_sha": ""}
        base.update(extra)
        store.write_json(os.path.join(self.dir, ".handoff"), base)

    def tearDown(self):
        self.tmp.cleanup()

    def type_(self, text="grind finer"):
        return decide("mcp__claude-in-chrome__computer", self.dir, action="type", text=text)

    def send(self):
        return decide("mcp__playwright__browser_click", self.dir, element="Comment button")

    def test_no_send_before_typing(self):
        self.assertIsNotNone(self.send())

    def test_one_named_send_after_typing(self):
        self.type_()
        self.assertIsNone(self.send())
        self.assertTrue(store.read_json(os.path.join(self.dir, ".handoff"))["submitted"])
        self.assertIsNotNone(self.send())

    def test_unlabelled_click_after_typing_is_not_a_send(self):
        self.type_()
        self.assertIsNotNone(decide("mcp__claude-in-chrome__computer", self.dir, action="left_click", ref="ref_9"))
        self.assertIsNone(self.send())

    def test_extra_typing_voids_the_send(self):
        self.type_()
        self.type_(" check out mytool.com")
        self.assertIsNotNone(self.send())

    def test_different_text_is_not_sent(self):
        self.type_("grind coarser")
        self.assertIsNotNone(self.send())

    def test_post_needs_title_and_body(self):
        self.mark({"title_sha": sha("Sour shots")})
        decide("mcp__claude-in-chrome__form_input", self.dir, ref="ref_1", value="Sour shots")
        self.assertIsNotNone(decide("mcp__playwright__browser_click", self.dir, element="Post button"))
        decide("mcp__claude-in-chrome__form_input", self.dir, ref="ref_2", value="grind finer")
        self.assertIsNone(decide("mcp__playwright__browser_click", self.dir, element="Post button"))

    def test_mode_switched_back_to_manual(self):
        store.write_json(os.path.join(self.dir, "profile.json"), {"posting": "manual"})
        self.type_()
        self.assertIsNotNone(self.send())

    def test_marker_from_another_day(self):
        self.mark({"date": "2000-01-01"})
        self.type_()
        self.assertIsNotNone(self.send())

    def test_failed_marker_write_blocks_the_send(self):
        self.type_()
        original = guard._write_marker
        guard._write_marker = lambda folder, mark: False
        try:
            self.assertIsNotNone(self.send())
        finally:
            guard._write_marker = original

    def test_never_votes_saves_joins_or_messages(self):
        self.type_()
        for label in ("upvote arrow", "Upvote this comment by u/foo", "Save", "Join", "Follow", "Award", "Report",
                      "Hide", "Message"):
            self.assertIsNotNone(decide("mcp__playwright__browser_click", self.dir, element=label), label)
        self.assertIsNone(self.send())

    def test_keyboard_send(self):
        self.type_()
        self.assertIsNone(decide("mcp__claude-in-chrome__computer", self.dir, action="key", text="ctrl+Return"))
        self.assertIsNotNone(decide("mcp__claude-in-chrome__computer", self.dir, action="key", text="ctrl+Return"))

    def test_typing_text_that_mentions_ctrl_enter(self):
        self.mark({"body_sha": sha("press ctrl+enter to run the cell")})
        self.assertIsNone(self.type_("press ctrl+enter to run the cell"))
        self.assertIsNone(self.send())


class ApproveNeedsTheUser(unittest.TestCase):
    def test_approve_command_asks(self):
        out = guard.decide({"tool_name": "Bash", "tool_input": {
            "command": 'python3 "$D/../reddit-plan/drafts.py" approve D0003 D0004'}}, None)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "ask")

    def test_other_bash_untouched(self):
        self.assertIsNone(guard.decide({"tool_name": "Bash", "tool_input": {"command": "python3 drafts.py list"}},
                                       None))


if __name__ == "__main__":
    unittest.main()
