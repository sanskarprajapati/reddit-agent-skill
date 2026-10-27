import datetime
import unittest

from _load import load

stats = load("reddit-stats", "stats")

TODAY = datetime.date(2026, 10, 27)
ME = "quiet_brewer"


def item(cid, sub="espresso", type_="comment", score=3, comments=0, removed=False, created="2026-10-20T10:00:00Z",
         text="grind finer"):
    return {"id": "t1_" + cid if type_ == "comment" else "t3_" + cid, "sub": sub, "type": type_, "score": score,
            "comments": comments, "removed": removed, "created": created, "text": text, "title": "",
            "url": "https://www.reddit.com/r/%s/comments/1abc2d/x/%s/" % (sub, cid)}


def cap(items, user=ME, captured="2026-10-27T10:00:00Z"):
    return {"kind": "profile", "url": "https://www.reddit.com/user/%s/comments/" % user, "captured": captured,
            "items": items, "blocked": False}


class Gather(unittest.TestCase):
    def test_only_own_profile_and_latest_numbers(self):
        caps = [cap([item("a", score=1)], captured="2026-10-26T10:00:00Z"),
                cap([item("a", score=7)], captured="2026-10-27T10:00:00Z"),
                cap([item("b")], user="someone_else")]
        items = stats.gather(caps, ME)
        self.assertEqual(list(items), ["t1_a"])
        self.assertEqual(items["t1_a"]["score"], 7)

    def test_needs_username(self):
        with self.assertRaisesRegex(ValueError, "username"):
            stats.gather([cap([item("a")])], "")


class Summary(unittest.TestCase):
    def test_totals_by_sub_kind_and_purpose(self):
        items = stats.gather([cap([item("a", score=10, comments=2), item("b", score=2), item("c", sub="Coffee", score=-1,
                                                                                           removed=True),
                                   item("d", type_="post", score=30, comments=12)])], ME)
        log = [{"url": "https://www.reddit.com/r/espresso/comments/1abc2d/x/a/", "purpose": "promo",
                "status": "posted", "date": "2026-10-20", "sub": "espresso", "kind": "comment"}]
        out = stats.summary(items, log, TODAY)
        self.assertEqual(out["total"], 4)
        self.assertEqual(out["removed"], 1)
        self.assertEqual(out["by_sub"]["espresso"]["count"], 3)
        self.assertEqual(out["by_sub"]["Coffee"]["removed"], 1)
        self.assertEqual(out["by_kind"]["post"]["median_score"], 30)
        self.assertEqual(out["by_purpose"]["promo"]["count"], 1)
        self.assertEqual(out["by_purpose"]["unknown"]["count"], 3)
        self.assertEqual(out["best"][0]["id"], "t3_d")
        self.assertTrue(out["few"])

    def test_logged_but_not_seen(self):
        items = stats.gather([cap([item("a")])], ME)
        log = [{"url": "https://www.reddit.com/r/espresso/comments/1abc2d/x/zz9/", "purpose": "help",
                "status": "posted", "date": "2026-10-21", "sub": "espresso", "kind": "comment"},
               {"url": "https://www.reddit.com/r/espresso/comments/1abc2d/x/", "purpose": "help",
                "status": "posted", "date": "2026-10-21", "sub": "espresso", "kind": "comment"}]
        out = stats.summary(items, log, TODAY)
        self.assertEqual([e["url"] for e in out["not_seen"]], [log[0]["url"]])

    def test_empty(self):
        out = stats.summary({}, [], TODAY)
        self.assertEqual(out["total"], 0)


class Report(unittest.TestCase):
    def test_escapes(self):
        items = stats.gather([cap([item("a", text="[click](http://evil.example) <b>")])], ME)
        text = stats.report(stats.summary(items, [], TODAY), TODAY)
        self.assertNotIn("](http://evil", text)
        self.assertIn("r/espresso", text)


if __name__ == "__main__":
    unittest.main()
