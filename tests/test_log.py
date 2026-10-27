import datetime
import os
import tempfile
import unittest

from _load import load

log = load("reddit-setup", "log")

TODAY = datetime.date(2026, 10, 27)
THREAD = "https://www.reddit.com/r/espresso/comments/1abc2d/x/"


class Entry(unittest.TestCase):
    def test_good(self):
        e = log.entry(url=THREAD, sub="r/espresso", kind="comment", purpose="help", today=TODAY)
        self.assertEqual(e["sub"], "espresso")
        self.assertEqual(e["date"], "2026-10-27")
        self.assertEqual(e["status"], "posted")

    def test_bad_values(self):
        with self.assertRaisesRegex(ValueError, "kind"):
            log.entry(url=THREAD, sub="espresso", kind="vote", purpose="help", today=TODAY)
        with self.assertRaisesRegex(ValueError, "purpose"):
            log.entry(url=THREAD, sub="espresso", kind="comment", purpose="spam", today=TODAY)
        with self.assertRaisesRegex(ValueError, "status"):
            log.entry(url=THREAD, sub="espresso", kind="comment", purpose="help", status="queued", today=TODAY)
        with self.assertRaisesRegex(ValueError, "url"):
            log.entry(url="https://x.com/a", sub="espresso", kind="comment", purpose="help", today=TODAY)

    def test_date_at_most_a_week_back(self):
        with self.assertRaisesRegex(ValueError, "7 days"):
            log.entry(url=THREAD, sub="espresso", kind="comment", purpose="help", date="2026-10-01", today=TODAY)

    def test_date_not_in_future(self):
        with self.assertRaisesRegex(ValueError, "future"):
            log.entry(url=THREAD, sub="espresso", kind="comment", purpose="help", date="2026-10-28", today=TODAY)


class Counts(unittest.TestCase):
    def entries(self):
        mk = lambda d, kind="comment", purpose="help", status="posted": log.entry(
            url=THREAD, sub="espresso", kind=kind, purpose=purpose, status=status, date=d, today=TODAY)
        return [mk("2026-10-27"), mk("2026-10-27", kind="post"), mk("2026-10-27", status="skipped"),
                mk("2026-10-26", purpose="promo"), dict(mk("2026-10-26", purpose="promo"), date="2026-09-01")]

    def test_counts_on_day_ignore_skipped(self):
        self.assertEqual(log.counts_on(self.entries(), TODAY), {"comment": 1, "post": 1})

    def test_promo_ratio_in_window(self):
        r = log.promo_ratio(self.entries(), TODAY, days=30)
        self.assertEqual((r["promo"], r["total"]), (1, 3))
        self.assertAlmostEqual(r["ratio"], 1 / 3)

    def test_ratio_empty(self):
        self.assertEqual(log.promo_ratio([], TODAY)["ratio"], 0.0)

    def test_hand_edited_rows_do_not_crash(self):
        rows = self.entries() + [{"status": "posted"}, {"date": "2026-10-27", "status": "posted"}]
        self.assertEqual(log.counts_on(rows, TODAY), {"comment": 1, "post": 1, "unknown": 1})
        self.assertEqual(log.promo_ratio(rows, TODAY)["total"], 4)

    def test_days_at_least_one(self):
        with self.assertRaisesRegex(ValueError, "days"):
            log.promo_ratio([], TODAY, days=0)


class Files(unittest.TestCase):
    def test_add_and_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            log.add(tmp, log.entry(url=THREAD, sub="espresso", kind="comment", purpose="help", today=TODAY))
            self.assertEqual(len(log.read(tmp)), 1)
            self.assertTrue(os.path.exists(os.path.join(tmp, "log.jsonl")))


if __name__ == "__main__":
    unittest.main()
