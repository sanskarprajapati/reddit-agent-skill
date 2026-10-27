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


class ReviewFixes(unittest.TestCase):
    def test_comment_logged_with_thread_link_matches_one_comment(self):
        items = stats.gather([cap([item("k1"), item("k2", sub="Coffee")])], ME)
        log = [{"url": "https://www.reddit.com/r/espresso/comments/1abc2d/x/", "purpose": "promo", "kind": "comment",
                "status": "posted", "date": "2026-10-20", "sub": "espresso"}]
        out = stats.summary(items, log, TODAY)
        self.assertEqual(out["by_purpose"]["promo"]["count"], 1)

    def test_thread_link_with_two_candidates_stays_unknown(self):
        items = stats.gather([cap([item("k1"), item("k2")])], ME)
        log = [{"url": "https://www.reddit.com/r/espresso/comments/1abc2d/x/", "purpose": "promo", "kind": "comment",
                "status": "posted", "date": "2026-10-20", "sub": "espresso"}]
        self.assertNotIn("promo", stats.summary(items, log, TODAY)["by_purpose"])

    def test_not_seen_window_uses_latest_read(self):
        caps = [cap([item("old", created="2026-09-01T10:00:00Z")], captured="2026-09-02T10:00:00Z"),
                cap([item("a", created="2026-10-18T10:00:00Z")], captured="2026-10-27T10:00:00Z")]
        items = stats.gather(caps, ME)
        row = lambda cid, d: {"url": "https://www.reddit.com/r/espresso/comments/1abc2d/x/%s/" % cid, "kind": "comment",
                              "purpose": "help", "status": "posted", "date": d, "sub": "espresso"}
        out = stats.summary(items, [row("zz1", "2026-10-20"), row("zz2", "2026-01-02")], TODAY)
        self.assertEqual([e["date"] for e in out["not_seen"]], ["2026-10-20"])

    def test_only_own_activity_pages(self):
        for page in ("saved", "upvoted", "hidden", "gilded"):
            c = cap([item("a")])
            c["url"] = "https://www.reddit.com/user/%s/%s/" % (ME, page)
            self.assertEqual(stats.gather([c], ME), {}, page)
        for page in ("", "overview/", "submitted/"):
            c = cap([item("a")])
            c["url"] = "https://www.reddit.com/user/%s/%s" % (ME, page)
            self.assertEqual(len(stats.gather([c], ME)), 1, page)

    def test_type_mismatch_is_left_out(self):
        bad = item("a")
        bad["id"] = "t3_1abc2d"
        self.assertEqual(stats.gather([cap([bad])], ME), {})

    def test_own_profile_post_link(self):
        post = item("p1", type_="post")
        post["id"], post["url"] = None, "https://www.reddit.com/user/%s/comments/9zz9/my_post/" % ME
        self.assertIn("t3_9zz9", stats.gather([cap([post])], ME))

    def test_days_filter(self):
        items = stats.gather([cap([item("a", created="2026-10-25T10:00:00Z"),
                                   item("b", created="2026-09-01T10:00:00Z")])], ME)
        self.assertEqual(stats.summary(items, [], TODAY, days=7)["total"], 1)

    def test_subs_group_case_blind_and_best_worst_apart(self):
        items = stats.gather([cap([item("a", sub="Espresso", score=1), item("b", score=2), item("c", score=3),
                                   item("d", score=4)])], ME)
        out = stats.summary(items, [], TODAY)
        self.assertEqual(len(out["by_sub"]), 1)
        best = {i["id"] for i in out["best"]}
        self.assertFalse(best & {i["id"] for i in out["worst"]})

    def test_bad_log_rows(self):
        items = stats.gather([cap([item("a")])], ME)
        stats.report(stats.summary(items, ["junk", {"status": "posted"}], TODAY), TODAY)

    def test_no_scores(self):
        items = stats.gather([cap([item("a", score=None)])], ME)
        text = stats.report(stats.summary(items, [], TODAY), TODAY)
        self.assertNotIn("None", text)
        self.assertIn("1 item,", text)


class Report(unittest.TestCase):
    def test_escapes(self):
        items = stats.gather([cap([item("a", text="[click](http://evil.example) <b>")])], ME)
        text = stats.report(stats.summary(items, [], TODAY), TODAY)
        self.assertNotIn("](http://evil", text)
        self.assertIn("r/espresso", text)


if __name__ == "__main__":
    unittest.main()
