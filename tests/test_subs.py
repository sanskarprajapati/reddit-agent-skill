import datetime
import unittest

from _load import load

subs = load("reddit-subs", "subs")

TODAY = datetime.date(2026, 10, 27)
PROFILE = {"topics": ["home espresso"], "terms": ["grinder", "sour shot", "espresso machine"]}


def search(query, items):
    return {"kind": "sub_search", "query": query, "captured": "2026-10-27T10:00:00Z",
            "url": "https://www.reddit.com/search/?q=x&type=communities",
            "items": [dict({"members": None, "description": ""}, **i) for i in items]}


def about(name, members, contributions, visitors=None, description=""):
    return {"kind": "sub_about", "captured": "2026-10-27T10:05:00Z", "url": "https://www.reddit.com/r/%s/" % name,
            "items": [{"name": name, "members": members, "weekly_contributions": contributions,
                       "weekly_visitors": visitors, "description": description}]}


class Gather(unittest.TestCase):
    def test_merges_search_and_about(self):
        caps = [search("espresso", [{"name": "espresso", "members": 1200000, "description": "Espresso machines"},
                                    {"name": "Coffee", "members": 3000000}]),
                search("grinder", [{"name": "Espresso", "members": 1200000}]),
                about("espresso", 1250000, 4500, 210000)]
        found = subs.gather(caps)
        self.assertEqual(sorted(found), ["coffee", "espresso"])
        esp = found["espresso"]
        self.assertEqual(esp["members"], 1250000)  # the sub page wins over search
        self.assertEqual(esp["weekly_contributions"], 4500)
        self.assertEqual(esp["queries"], ["espresso", "grinder"])
        self.assertEqual(esp["description"], "Espresso machines")
        self.assertIsNone(found["coffee"]["weekly_contributions"])


class Score(unittest.TestCase):
    def test_size_band_prefers_the_middle(self):
        self.assertLess(subs.size_score(500), subs.size_score(50000))
        self.assertLess(subs.size_score(5000000), subs.size_score(50000))
        self.assertEqual(subs.size_score(None), 0)

    def test_activity_log_scale(self):
        self.assertEqual(subs.activity_score(5), 0)
        self.assertEqual(subs.activity_score(None), 0)
        self.assertEqual(subs.activity_score(10000), 1)
        self.assertLess(subs.activity_score(100), subs.activity_score(1000))

    def test_fit(self):
        good = subs.fit_score({"name": "espresso", "description": "home espresso machines and grinders",
                               "queries": ["espresso", "grinder"]}, PROFILE)
        weak = subs.fit_score({"name": "AskReddit", "description": "ask anything", "queries": ["espresso"]}, PROFILE)
        self.assertGreater(good, weak)
        self.assertLessEqual(good, 1)

    def test_fit_word_edges(self):
        java = {"topics": ["java"], "terms": []}
        self.assertEqual(subs.fit_score({"name": "javascript", "description": "", "queries": []}, java), 0)
        self.assertGreater(subs.fit_score({"name": "learnjava", "description": "", "queries": []}, java), 0)

    def test_fit_splits_camel_case_names(self):
        self.assertGreater(subs.fit_score({"name": "EspressoMachines", "description": "", "queries": []}, PROFILE), 0)

    def test_total_is_0_to_100_and_unknowns_listed(self):
        rec = subs.score({"name": "espresso", "members": 50000, "weekly_contributions": None,
                          "description": "espresso", "queries": ["espresso"]}, PROFILE)
        self.assertTrue(0 <= rec["score"] <= 100)
        self.assertIn("weekly_contributions", rec["unknown"])


class Rank(unittest.TestCase):
    def test_skip_and_needs_confirm(self):
        caps = [search("espresso", [{"name": "espresso", "members": 1200000},
                                    {"name": "NoAIcoffee", "members": 80000},
                                    {"name": "barista", "members": 90000}])]
        verdicts = {"espresso": "ok", "noaicoffee": "skip", "barista": "needs_confirm"}
        out = subs.rank(caps, PROFILE, verdicts)
        self.assertEqual([r["name"] for r in out["skipped"]], ["NoAIcoffee"])
        ranked = {r["name"]: r for r in out["ranked"]}
        self.assertEqual(ranked["barista"]["rules"], "needs_confirm")
        self.assertNotIn("NoAIcoffee", ranked)

    def test_missing_rules_marked(self):
        out = subs.rank([search("espresso", [{"name": "espresso", "members": 1000}])], PROFILE, {})
        self.assertEqual(out["ranked"][0]["rules"], "missing")

    def test_sorted_by_score(self):
        caps = [search("espresso", [{"name": "espresso", "members": 100000, "description": "home espresso"},
                                    {"name": "pics", "members": 30000000}])]
        out = subs.rank(caps, PROFILE, {})
        self.assertEqual(out["ranked"][0]["name"], "espresso")


class Report(unittest.TestCase):
    def test_report_escapes_stranger_text(self):
        caps = [search("espresso", [{"name": "espresso", "members": 1000,
                                     "description": "[click](http://evil.example) <script>"}])]
        text = subs.report(subs.rank(caps, PROFILE, {}), TODAY)
        self.assertNotIn("](http://evil", text)
        self.assertNotIn("<script>", text)
        self.assertIn("r/espresso", text)


if __name__ == "__main__":
    unittest.main()
