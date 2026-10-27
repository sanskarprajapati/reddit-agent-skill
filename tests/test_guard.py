import json
import unittest

from _load import load

guard = load("reddit-draft", "guard")


def decide(tool, **tool_input):
    return guard.decide({"tool_name": tool, "tool_input": tool_input})


class Guard(unittest.TestCase):
    def test_ignores_other_tools(self):
        self.assertIsNone(decide("Bash", command="ls"))
        self.assertIsNone(decide("Read", file_path="x"))

    def test_allows_reading_and_typing(self):
        self.assertIsNone(decide("mcp__claude-in-chrome__navigate", url="https://www.reddit.com/r/espresso/new/"))
        self.assertIsNone(decide("mcp__claude-in-chrome__get_page_text"))
        self.assertIsNone(decide("mcp__claude-in-chrome__find", query="Reply button under the top comment"))
        self.assertIsNone(decide("mcp__claude-in-chrome__computer", action="type", text="grind finer"))
        self.assertIsNone(decide("mcp__claude-in-chrome__computer", action="left_click", coordinate=[300, 400]))
        self.assertIsNone(decide("mcp__playwright__browser_click", element="Add a comment box"))
        self.assertIsNone(decide("mcp__playwright__browser_click", element="Join the conversation"))

    def test_blocks_sending_clicks_by_name(self):
        for label in ("Comment button", "Post", "Save", "Submit", "Send", "upvote arrow", "Join", "Follow",
                      "Award", "Report"):
            self.assertIsNotNone(decide("mcp__playwright__browser_click", element=label), label)
        self.assertIsNotNone(decide("mcp__claude-in-chrome__computer", action="left_click", ref="ref_12",
                                    text="Comment"))

    def test_blocks_keyboard_submit(self):
        for key in ("ctrl+Return", "cmd+Return", "Control+Enter", "Meta+Enter", "ctrl+enter"):
            self.assertIsNotNone(decide("mcp__claude-in-chrome__computer", action="key", text=key), key)
        self.assertIsNotNone(decide("mcp__playwright__browser_press_key", key="Control+Enter"))
        self.assertIsNone(decide("mcp__claude-in-chrome__computer", action="key", text="Return"))

    def test_blocks_private_pages(self):
        for url in ("https://www.reddit.com/message/compose/", "https://chat.reddit.com/", "https://www.reddit.com/settings",
                    "https://www.reddit.com/notifications", "https://old.reddit.com/prefs/", "https://www.reddit.com/login"):
            self.assertIsNotNone(decide("mcp__claude-in-chrome__navigate", url=url), url)

    def test_blocks_scripts_that_act(self):
        self.assertIsNotNone(decide("mcp__claude-in-chrome__javascript_tool", text="document.querySelector('b').click()"))
        self.assertIsNotNone(decide("mcp__playwright__browser_evaluate", function="() => form.submit()"))
        self.assertIsNone(decide("mcp__claude-in-chrome__javascript_tool", text="document.title"))

    def test_output_shape(self):
        out = guard.decide({"tool_name": "mcp__playwright__browser_click", "tool_input": {"element": "Post"}})
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        self.assertIn("You click Post", out["hookSpecificOutput"]["permissionDecisionReason"])
        json.dumps(out)


if __name__ == "__main__":
    unittest.main()
