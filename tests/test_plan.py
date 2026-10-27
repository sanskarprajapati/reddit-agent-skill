import datetime
import unittest

from _load import load

plan = load("reddit-plan", "plan")

TODAY = datetime.date(2026, 10, 27)


def prof(age_days=3, karma=5, caps=None, product=None):
    created = (TODAY - datetime.timedelta(days=age_days)).isoformat()
    return {"account": {"created": created, "karma": karma, "age_days": age_days}, "caps": caps or {},
            "product": product}


def logged(day, kind="comment", purpose="help", sub="espresso"):
    return {"date": day, "kind": kind, "purpose": purpose, "status": "posted", "sub": sub,
            "url": "https://www.reddit.com/r/espresso/comments/1abc2d/x/"}


class Phase(unittest.TestCase):
    def test_new_account_by_age(self):
        self.assertEqual(plan.phase(prof(age_days=3), [], TODAY)["name"], "new")
        self.assertEqual(plan.phase(prof(age_days=10), [], TODAY)["name"], "building")
        self.assertEqual(plan.phase(prof(age_days=30, karma=200), [], TODAY)["name"], "established")

    def test_old_quiet_account_warms_up_from_first_log(self):
        self.assertEqual(plan.phase(prof(age_days=900, karma=3), [], TODAY)["name"], "new")
        log = [logged((TODAY - datetime.timedelta(days=12)).isoformat())]
        self.assertEqual(plan.phase(prof(age_days=900, karma=3), log, TODAY)["name"], "building")

    def test_backdated_log_does_not_skip_warm_up(self):
        log = [logged("2019-01-01")]
        self.assertEqual(plan.phase(prof(age_days=900, karma=3), log, TODAY)["name"], "new")

    def test_no_drop_back_at_day_28(self):
        self.assertEqual(plan.phase(prof(age_days=27, karma=3), [], TODAY)["name"], "building")
        self.assertNotEqual(plan.phase(prof(age_days=28, karma=3), [], TODAY)["name"], "new")

    def test_young_account_with_karma_still_warms_up(self):
        self.assertEqual(plan.phase(prof(age_days=2, karma=5000), [], TODAY)["name"], "new")

    def test_negative_karma_holds_at_new(self):
        self.assertEqual(plan.phase(prof(age_days=60, karma=-5), [], TODAY)["name"], "new")

    def test_rules_per_phase(self):
        new = plan.phase(prof(age_days=3), [], TODAY)
        self.assertEqual((new["comments"], new["posts"], new["links"], new["product"]), (3, 0, "none", False))
        building = plan.phase(prof(age_days=10), [], TODAY)
        self.assertEqual((building["comments"], building["posts"], building["links"], building["product"]),
                         (5, 1, "others only", False))
        est = plan.phase(prof(age_days=40, karma=300), [], TODAY)
        self.assertLessEqual(est["comments"] + est["posts"], plan.HARD_CEILING)
        self.assertTrue(est["product"])


class Caps(unittest.TestCase):
    def test_user_caps_only_lower(self):
        caps = plan.caps(prof(age_days=10, caps={"comments_per_day": 2, "posts_per_day": 7}), [], TODAY)
        self.assertEqual((caps["comment"], caps["post"]), (2, 1))

    def test_left_today_counts_drafts(self):
        drafts = [{"date": TODAY.isoformat(), "kind": "comment", "status": "drafted"},
                  {"date": TODAY.isoformat(), "kind": "comment", "status": "skipped"},
                  {"date": TODAY.isoformat(), "kind": "comment", "status": "posted"},
                  {"date": "2026-10-26", "kind": "comment", "status": "drafted"}]
        left = plan.left_today(prof(age_days=3), [], drafts, TODAY)
        self.assertEqual(left, {"comment": 1, "post": 0})


class Promo(unittest.TestCase):
    PRODUCT = {"name": "Brewlog", "what": "x", "url": ""}

    def test_not_before_established(self):
        ok, why = plan.promo_allowed(prof(age_days=10, product=self.PRODUCT), [], TODAY)
        self.assertFalse(ok)
        self.assertIn("phase", why)

    def test_no_product(self):
        ok, _ = plan.promo_allowed(prof(age_days=60, karma=300), [], TODAY)
        self.assertFalse(ok)

    def test_ratio(self):
        p = prof(age_days=60, karma=300, product=self.PRODUCT)
        days = [(TODAY - datetime.timedelta(days=d)).isoformat() for d in range(9)]
        helpful = [logged(d) for d in days]
        self.assertTrue(plan.promo_allowed(p, helpful, TODAY)[0])
        ok, why = plan.promo_allowed(p, helpful + [logged(days[0], purpose="promo")], TODAY)
        self.assertFalse(ok)
        self.assertIn("1 in 10", why)

    def test_needs_some_help_first(self):
        ok, _ = plan.promo_allowed(prof(age_days=60, karma=300, product=self.PRODUCT), [], TODAY)
        self.assertFalse(ok)


class Week(unittest.TestCase):
    SUBS = {"ranked": [{"name": "espresso", "rules": "ok", "score": 80},
                       {"name": "Coffee", "rules": "ok", "score": 70},
                       {"name": "barista", "rules": "needs_confirm", "score": 90},
                       {"name": "pourover", "rules": "ok", "score": 50}],
            "skipped": [{"name": "NoAI", "rules": "skip"}]}

    def test_seven_days_only_ok_subs(self):
        rows = plan.week(prof(age_days=3), self.SUBS, [], TODAY)
        self.assertEqual(len(rows), 7)
        self.assertEqual(rows[0]["date"], TODAY.isoformat())
        used = {s for r in rows for s in r["subs"]}
        self.assertTrue(used <= {"espresso", "Coffee", "pourover"})

    def test_phase_advances_inside_the_week(self):
        rows = plan.week(prof(age_days=5), self.SUBS, [], TODAY)
        self.assertEqual(rows[0]["phase"], "new")
        self.assertEqual(rows[2]["phase"], "building")
        self.assertEqual(rows[2]["posts"], 1)

    def test_no_subs(self):
        rows = plan.week(prof(age_days=3), {"ranked": [], "skipped": []}, [], TODAY)
        self.assertEqual(rows[0]["subs"], [])


if __name__ == "__main__":
    unittest.main()
