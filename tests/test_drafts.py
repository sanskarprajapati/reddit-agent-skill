import datetime
import os
import tempfile
import unittest

from _load import load

queue = load("reddit-plan", "drafts")
store = load("reddit-setup", "store")
rules = load("reddit-subs", "rules")

TODAY = datetime.date(2026, 10, 27)
THREAD = "https://www.reddit.com/r/espresso/comments/1abc2d/first_shot_sour/"
HELP = "grind finer and pull a bit longer. my gaggia did the same till i dialed in the grinder"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.profile(age_days=3, karma=5)
        self.rules("espresso", [("Be kind", "No personal attacks.")])

    def tearDown(self):
        self.tmp.cleanup()

    def profile(self, age_days, karma, product=None):
        created = (TODAY - datetime.timedelta(days=age_days)).isoformat()
        store.write_json(os.path.join(self.dir, "profile.json"), {
            "username": "quiet_brewer", "topics": ["home espresso"], "terms": [], "knows": ["gaggia"],
            "account": {"created": created, "karma": karma}, "product": product})

    def rules(self, sub, items, captured="2026-10-27T09:00:00Z"):
        cap = {"kind": "rules", "sub": sub, "url": "https://old.reddit.com/r/%s/about/rules" % sub,
               "captured": captured, "items": [{"title": t, "text": x} for t, x in items]}
        rules.save(self.dir, rules.classify(cap, TODAY))

    def draft_file(self, text=HELP, name="d.txt"):
        path = os.path.join(self.dir, "drafts", name)
        store.write_text(path, text)
        return path

    def new(self, text=HELP, **kw):
        name = kw.pop("name", "d.txt")
        args = dict(sub="espresso", kind="comment", url=THREAD, purpose="help", today=TODAY)
        args.update(kw)
        return queue.new_draft(self.dir, file=self.draft_file(text, name=name), **args)


class NewDraft(Base):
    def test_registers(self):
        d = self.new()
        self.assertEqual(d["id"], "D0001")
        self.assertEqual(d["status"], "drafted")
        self.assertEqual(d["risk"], "low")
        self.assertEqual(len(queue.read(self.dir)), 1)

    def test_cap(self):
        for n in range(3):
            self.new(name="d%d.txt" % n)
        with self.assertRaisesRegex(ValueError, "cap"):
            self.new(name="d9.txt")

    def test_no_posts_in_new_phase(self):
        with self.assertRaisesRegex(ValueError, "cap"):
            self.new(HELP + " " + HELP, kind="post", url="https://www.reddit.com/r/espresso/submit", title="Sour")

    def test_rules_must_be_ok(self):
        self.rules("NoAI", [("No AI", "AI-generated posts are removed.")])
        with self.assertRaisesRegex(ValueError, "bans AI"):
            self.new(sub="NoAI", url="https://www.reddit.com/r/NoAI/comments/1abc2d/x/")
        with self.assertRaisesRegex(ValueError, "not been read"):
            self.new(sub="pourover", url="https://www.reddit.com/r/pourover/comments/1abc2d/x/")

    def test_url_must_match_sub_and_be_a_thread(self):
        with self.assertRaisesRegex(ValueError, "thread"):
            self.new(url="https://www.reddit.com/r/espresso/new/")
        with self.assertRaisesRegex(ValueError, "r/espresso"):
            self.new(url="https://www.reddit.com/r/Coffee/comments/1abc2d/x/")

    def test_no_links_in_new_phase(self):
        with self.assertRaisesRegex(ValueError, "links"):
            self.new(HELP + " https://example.com/guide")

    def test_no_product_before_established(self):
        self.profile(age_days=10, karma=50, product={"name": "Brewlog", "what": "a shot log", "url": ""})
        with self.assertRaisesRegex(ValueError, "product"):
            self.new(HELP + " i use brewlog")

    def test_promo_needs_ratio(self):
        self.profile(age_days=60, karma=500, product={"name": "Brewlog", "what": "a shot log", "url": ""})
        with self.assertRaisesRegex(ValueError, "1 in 10"):
            self.new(HELP + " i use brewlog", purpose="promo")

    def test_product_mention_must_be_marked_promo(self):
        self.profile(age_days=60, karma=500, product={"name": "Brewlog", "what": "a shot log", "url": ""})
        with self.assertRaisesRegex(ValueError, "promo"):
            self.new(HELP + " i use brewlog", purpose="help")

    def test_high_risk_refused(self):
        with self.assertRaisesRegex(ValueError, "high"):
            self.new(HELP + " bit.ly/x")


class Handoff(Base):
    def test_gate_then_done(self):
        d = self.new()
        out = queue.gate(self.dir, d["id"], TODAY)
        self.assertEqual(out["url"], THREAD)
        self.assertEqual(out["text"], HELP)
        self.assertEqual(queue.read(self.dir)[0]["status"], "handed")
        queue.done(self.dir, d["id"], TODAY, url=THREAD + "kx9zz1/")
        self.assertEqual(queue.read(self.dir)[0]["status"], "posted")
        logged = store.load_jsonl(os.path.join(self.dir, "log.jsonl"))
        self.assertEqual((logged[0]["status"], logged[0]["draft"], logged[0]["purpose"]), ("posted", "D0001", "help"))

    def test_one_at_a_time(self):
        a, b = self.new(name="a.txt"), self.new(name="b.txt")
        queue.gate(self.dir, a["id"], TODAY)
        with self.assertRaisesRegex(ValueError, "D0001"):
            queue.gate(self.dir, b["id"], TODAY)
        queue.skip(self.dir, a["id"], TODAY)
        queue.gate(self.dir, b["id"], TODAY)

    def test_gate_rechecks_edited_text(self):
        d = self.new()
        store.write_text(d["file"], HELP + " bit.ly/x")
        with self.assertRaisesRegex(ValueError, "high"):
            queue.gate(self.dir, d["id"], TODAY)

    def test_gate_rechecks_rules(self):
        d = self.new()
        self.rules("espresso", [("No AI", "AI-written comments will be removed.")])
        with self.assertRaisesRegex(ValueError, "bans AI"):
            queue.gate(self.dir, d["id"], TODAY)

    def test_closed_drafts_cannot_be_handed(self):
        d = self.new()
        queue.skip(self.dir, d["id"], TODAY)
        with self.assertRaisesRegex(ValueError, "skipped"):
            queue.gate(self.dir, d["id"], TODAY)

    def test_yesterdays_draft_counts_today(self):
        d = self.new()
        later = TODAY + datetime.timedelta(days=1)
        queue.gate(self.dir, d["id"], later)
        self.assertEqual(queue.read(self.dir)[0]["date"], later.isoformat())

    def test_done_needs_reddit_url(self):
        d = self.new()
        queue.gate(self.dir, d["id"], TODAY)
        with self.assertRaisesRegex(ValueError, "url"):
            queue.done(self.dir, d["id"], TODAY, url="https://example.com")


class CapAccounting(Base):
    def test_gate_rechecks_cap_after_hand_posts(self):
        d = self.new()
        log = load("reddit-setup", "log")
        for n in range(3):
            log.add(self.dir, log.entry(url=THREAD, sub="espresso", kind="comment", purpose="help", today=TODAY))
        with self.assertRaisesRegex(ValueError, "cap"):
            queue.gate(self.dir, d["id"], TODAY)

    def test_handed_from_yesterday_counts_today(self):
        d = self.new()
        queue.gate(self.dir, d["id"], TODAY)
        later = TODAY + datetime.timedelta(days=1)
        for n in range(2):
            self.new(name="n%d.txt" % n, today=later)
        with self.assertRaisesRegex(ValueError, "cap"):
            self.new(name="n9.txt", today=later)
        queue.done(self.dir, d["id"], later)
        self.assertEqual(queue.read(self.dir)[0]["date"], later.isoformat())

    def test_skip_after_typing_still_counts(self):
        for n in range(3):
            d = self.new(name="s%d.txt" % n)
            queue.gate(self.dir, d["id"], TODAY)
            queue.skip(self.dir, d["id"], TODAY)
        with self.assertRaisesRegex(ValueError, "cap"):
            self.new(name="s9.txt")

    def test_skip_before_typing_frees_the_slot(self):
        for n in range(3):
            d = self.new(name="f%d.txt" % n)
            queue.skip(self.dir, d["id"], TODAY)
        self.new(name="f9.txt")

    def test_post_needs_sub_page_not_thread(self):
        self.profile(age_days=10, karma=50)
        with self.assertRaisesRegex(ValueError, "post"):
            self.new(HELP + " " + HELP, kind="post", url=THREAD, title="Sour shots")
        self.new(HELP + " " + HELP, kind="post", url="https://www.reddit.com/r/espresso/submit", title="Sour shots",
                 name="p.txt")

    def test_handoff_marker(self):
        d = self.new()
        queue.gate(self.dir, d["id"], TODAY)
        self.assertEqual(store.read_json(os.path.join(self.dir, ".handoff"))["id"], d["id"])
        queue.done(self.dir, d["id"], TODAY)
        self.assertFalse(os.path.exists(os.path.join(self.dir, ".handoff")))

    def test_second_gate_keeps_typed(self):
        d = self.new()
        queue.gate(self.dir, d["id"], TODAY)
        path = os.path.join(self.dir, ".handoff")
        store.write_json(path, dict(store.read_json(path), typed=True))
        queue.gate(self.dir, d["id"], TODAY)
        self.assertTrue(store.read_json(path)["typed"])

    def test_lock_refuses_while_busy(self):
        path = os.path.join(self.dir, "drafts.jsonl")
        with store.locked(path):
            with self.assertRaisesRegex(ValueError, "busy"):
                with store.locked(path, wait=0.1):
                    pass

    def test_empty_day_has_no_calendar_events(self):
        self.assertIsNone(queue.ics([], TODAY))


class Approved(Base):
    def setUp(self):
        super().setUp()
        p = store.read_json(os.path.join(self.dir, "profile.json"))
        p["posting"] = "approved"
        store.write_json(os.path.join(self.dir, "profile.json"), p)
        store.write_json(os.path.join(self.dir, ".claude", "settings.json"), {"hooks": {"PreToolUse": [
            {"matcher": "mcp__.*|Bash", "hooks": [{"type": "command", "command": "python3 x/reddit-draft/guard.py"}]}]}})

    def test_manual_mode_never_submits(self):
        p = store.read_json(os.path.join(self.dir, "profile.json"))
        p["posting"] = "manual"
        store.write_json(os.path.join(self.dir, "profile.json"), p)
        d = self.new()
        with self.assertRaisesRegex(ValueError, "manual"):
            queue.approve(self.dir, [d["id"]], TODAY)

    def test_unapproved_draft_is_typed_not_sent(self):
        d = self.new()
        out = queue.gate(self.dir, d["id"], TODAY)
        self.assertFalse(out["may_submit"])
        self.assertFalse(store.read_json(os.path.join(self.dir, ".handoff"))["may_submit"])

    def test_approved_draft_may_be_sent(self):
        d = self.new()
        queue.approve(self.dir, [d["id"]], TODAY)
        out = queue.gate(self.dir, d["id"], TODAY)
        self.assertTrue(out["may_submit"])
        self.assertTrue(store.read_json(os.path.join(self.dir, ".handoff"))["may_submit"])

    def test_edit_after_approval_voids_it(self):
        d = self.new()
        queue.approve(self.dir, [d["id"]], TODAY)
        store.write_text(d["file"], HELP + " and weigh your dose")
        self.assertFalse(queue.gate(self.dir, d["id"], TODAY)["may_submit"])

    def test_approval_is_for_one_day(self):
        d = self.new()
        queue.approve(self.dir, [d["id"]], TODAY)
        later = TODAY + datetime.timedelta(days=1)
        self.assertFalse(queue.gate(self.dir, d["id"], later)["may_submit"])

    def test_batch_approve(self):
        ids = [self.new(name="b%d.txt" % n)["id"] for n in range(2)]
        self.assertEqual(queue.approve(self.dir, ids, TODAY), 2)

    def test_no_approval_after_typing(self):
        d = self.new()
        queue.gate(self.dir, d["id"], TODAY)
        path = os.path.join(self.dir, ".handoff")
        store.write_json(path, dict(store.read_json(path), typed=True))
        with self.assertRaisesRegex(ValueError, "typed"):
            queue.approve(self.dir, [d["id"]], TODAY)

    def test_regate_never_raises_may_submit(self):
        d = self.new()
        queue.gate(self.dir, d["id"], TODAY)
        p = os.path.join(self.dir, ".handoff")
        store.write_json(p, dict(store.read_json(p), typed=False))
        with self.assertRaisesRegex(ValueError, "skip"):
            queue.approve(self.dir, [d["id"]], TODAY)

    def test_marker_carries_date_and_hashes(self):
        d = self.new()
        queue.approve(self.dir, [d["id"]], TODAY)
        queue.gate(self.dir, d["id"], TODAY)
        mark = store.read_json(os.path.join(self.dir, ".handoff"))
        self.assertEqual(mark["date"], TODAY.isoformat())
        self.assertEqual(len(mark["body_sha"]), 64)

    def test_no_guard_no_send(self):
        os.remove(os.path.join(self.dir, ".claude", "settings.json"))
        d = self.new()
        queue.approve(self.dir, [d["id"]], TODAY)
        out = queue.gate(self.dir, d["id"], TODAY)
        self.assertFalse(out["may_submit"])
        self.assertIn("guard", out["why_not"])

    def test_queue_wording_per_mode(self):
        d = self.new()
        self.assertIn("approved", queue.queue_md(queue.read(self.dir), TODAY, mode="approved"))

    def test_gate_refuses_after_stray_typing(self):
        d = self.new()
        store.write_json(os.path.join(self.dir, ".handoff"), {"id": None, "stray": True, "typed": True})
        with self.assertRaisesRegex(ValueError, "stray|clear"):
            queue.gate(self.dir, d["id"], TODAY)
        queue.clear(self.dir)
        queue.gate(self.dir, d["id"], TODAY)

    def test_closed_drafts_cannot_be_approved(self):
        d = self.new()
        queue.skip(self.dir, d["id"], TODAY)
        with self.assertRaisesRegex(ValueError, "skipped"):
            queue.approve(self.dir, [d["id"]], TODAY)


class Calendar(Base):
    def test_ics(self):
        d = self.new()
        text = queue.ics(queue.read(self.dir), TODAY, now=datetime.datetime(2026, 10, 27, 8, 0))
        self.assertIn("BEGIN:VCALENDAR", text)
        self.assertIn("UID:D0001-2026-10-27@reddit-agent-skill", text)
        self.assertIn("DTSTART:20261027T", text)
        self.assertTrue(all(len(line.encode("utf-8")) <= 75 for line in text.split("\r\n")))
        self.assertTrue(text.endswith("END:VCALENDAR\r\n"))
        self.assertIn(d["sub"], text)

    def test_ics_escapes(self):
        self.assertEqual(queue.ics_escape("a,b;c\\d\ne"), "a\\,b\\;c\\\\d\\ne")

    def test_when(self):
        d = self.new(when="18:30")
        self.assertIn("DTSTART:20261027T183000", queue.ics([d], TODAY))
        with self.assertRaisesRegex(ValueError, "when"):
            self.new(when="6pm", name="x.txt")

    def test_queue_md_escapes(self):
        d = self.new(title_hint="[click](http://evil.example)")
        text = queue.queue_md(queue.read(self.dir), TODAY)
        self.assertIn(d["id"], text)
        self.assertNotIn("](http://evil", text)


if __name__ == "__main__":
    unittest.main()
