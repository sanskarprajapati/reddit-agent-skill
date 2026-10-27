import json
import os
import tempfile
import unittest

from _load import load

store = load("reddit-setup", "store")


class CleanText(unittest.TestCase):
    def test_strips_html_and_entities(self):
        raw = "I can&#x27;t stand it.<p>Second &amp; last <a href=\"x\">link</a>"
        self.assertEqual(store.clean_text(raw), "I can't stand it.\nSecond & last link")

    def test_collapses_whitespace_keeps_paragraphs(self):
        self.assertEqual(store.clean_text("  a \t b\n\n\n c  "), "a b\n\nc")

    def test_empty(self):
        self.assertEqual(store.clean_text(None), "")

    def test_keeps_less_than_and_greater_than(self):
        raw = "No posts <50 words or >3 links. Accounts <10 karma or >1 year"
        self.assertEqual(store.clean_text(raw), raw)

    def test_files_are_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.json")
            store.write_json(path, {})
            self.assertEqual(os.stat(path).st_mode & 0o777, 0o600)


class Verbatim(unittest.TestCase):
    TEXT = "Honestly the moka pot is fine, but grind size matters more than the pot."

    def test_real_quote(self):
        self.assertTrue(store.verbatim("grind size matters more", self.TEXT))

    def test_spacing_and_curly_quotes_may_differ(self):
        self.assertTrue(store.verbatim("the  moka   pot is", "I think the moka pot is great"))
        self.assertTrue(store.verbatim("it’s too bitter", "it's too bitter for me"))

    def test_changed_word_fails(self):
        self.assertFalse(store.verbatim("grind size matters less", self.TEXT))

    def test_too_short_by_default(self):
        self.assertFalse(store.verbatim("grind size", self.TEXT))

    def test_min_words_can_be_lowered(self):
        self.assertTrue(store.verbatim("definately", "i definately use a scale", min_words=1))

    def test_word_edges(self):
        self.assertFalse(store.verbatim("ill", "the bill came", min_words=1))
        self.assertFalse(store.verbatim("onestly the moka", self.TEXT))


class RedditId(unittest.TestCase):
    def test_post(self):
        url = "https://www.reddit.com/r/espresso/comments/1abc2d/my_first_shot/"
        self.assertEqual(store.reddit_id(url), "t3_1abc2d")

    def test_comment(self):
        url = "https://old.reddit.com/r/espresso/comments/1abc2d/my_first_shot/kx9zz1/"
        self.assertEqual(store.reddit_id(url), "t1_kx9zz1")

    def test_short_comment_link(self):
        url = "https://www.reddit.com/r/espresso/comments/1abc2d/comment/kx9zz1/"
        self.assertEqual(store.reddit_id(url), "t1_kx9zz1")

    def test_not_a_thread(self):
        self.assertIsNone(store.reddit_id("https://www.reddit.com/r/espresso/new/"))


class RedditUrl(unittest.TestCase):
    def test_accepts_reddit_hosts(self):
        for url in ("https://www.reddit.com/r/a/", "https://old.reddit.com/r/a/", "https://reddit.com/",
                    "https://new.reddit.com/r/a/", "https://sh.reddit.com/r/a/"):
            self.assertTrue(store.is_reddit_url(url), url)

    def test_rejects_others(self):
        for url in ("https://evilreddit.com/r/a", "http://www.reddit.com.evil.io/", "javascript:alert(1)",
                    "https://redd.it.example.com/", "ftp://reddit.com/"):
            self.assertFalse(store.is_reddit_url(url), url)


class SubName(unittest.TestCase):
    def test_normalises(self):
        for raw in ("espresso", "r/espresso", "/r/espresso", " R/Espresso "):
            self.assertEqual(store.sub_name(raw).lower(), "espresso")

    def test_rejects_bad(self):
        for raw in ("", "r/", "has space", "x" * 30, "a"):
            with self.assertRaises(ValueError):
                store.sub_name(raw)


class Bots(unittest.TestCase):
    def test_bots(self):
        for handle in ("AutoModerator", "RemindMeBot", "sports_bot", "Foo-Bot2"):
            self.assertTrue(store.is_bot(handle), handle)

    def test_people(self):
        for handle in ("Abbott", "Talbot", "ROBOT", "", None):
            self.assertFalse(store.is_bot(handle), handle)


class Files(unittest.TestCase):
    def test_jsonl_round_trip_and_append(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "x.jsonl")
            store.save_jsonl(path, [{"a": 1}])
            store.append_jsonl(path, {"b": "ü"})
            self.assertEqual(store.load_jsonl(path), [{"a": 1}, {"b": "ü"}])

    def test_missing_jsonl_is_empty(self):
        self.assertEqual(store.load_jsonl("/nonexistent/none.jsonl"), [])

    def test_bad_line_names_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.jsonl")
            with open(path, "w") as fh:
                fh.write('{"a":1}\nnot json\n')
            with self.assertRaisesRegex(ValueError, "line 2"):
                store.load_jsonl(path)

    def test_json_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "d", "x.json")
            store.write_json(path, {"k": [1, 2]})
            self.assertEqual(store.read_json(path), {"k": [1, 2]})
            with open(path) as fh:
                self.assertEqual(json.load(fh), {"k": [1, 2]})

    def test_read_json_missing_gives_default(self):
        self.assertIsNone(store.read_json("/nonexistent/x.json"))
        self.assertEqual(store.read_json("/nonexistent/x.json", default={}), {})


if __name__ == "__main__":
    unittest.main()
