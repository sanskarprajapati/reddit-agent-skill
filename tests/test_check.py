import unittest

from _load import load

check = load("reddit-check", "check")

PROFILE = {"product": {"name": "Brewlog", "what": "a shot log app", "url": "https://brewlog.app"},
           "account": {"karma": 40, "age_days": 20}}
NO_PRODUCT = {"product": None, "account": {"karma": 40, "age_days": 20}}
HELP = "grind finer and pull a bit longer. my gaggia did the same till i dialed in the grinder"


def rules(**extra):
    rec = {"sub": "espresso", "ai": "not mentioned", "self_promo": "not mentioned", "links": "not mentioned",
           "min_karma": None, "min_age_days": None, "flair": False, "evidence": [], "verdict": "ok"}
    rec.update(extra)
    return rec


class Gates(unittest.TestCase):
    def test_ai_ban_blocks(self):
        out = check.check(HELP, "comment", rules(verdict="skip", ai="banned"), NO_PRODUCT)
        self.assertEqual(out["risk"], "blocked")

    def test_needs_confirm_blocks(self):
        out = check.check(HELP, "comment", rules(verdict="needs_confirm", ai="unclear"), NO_PRODUCT)
        self.assertEqual(out["risk"], "blocked")
        self.assertTrue(any("confirm" in b for b in out["blocked"]))

    def test_missing_and_stale_rules_block(self):
        for verdict in ("missing", "stale"):
            self.assertEqual(check.check(HELP, "comment", rules(verdict=verdict), NO_PRODUCT)["risk"], "blocked")

    def test_product_where_promo_banned_blocks(self):
        out = check.check("i use brewlog for this", "comment", rules(self_promo="banned"), PROFILE)
        self.assertEqual(out["risk"], "blocked")

    def test_product_link_where_promo_banned_blocks(self):
        out = check.check("track it here https://www.brewlog.app/start", "comment", rules(self_promo="banned"),
                          PROFILE)
        self.assertEqual(out["risk"], "blocked")


class Risk(unittest.TestCase):
    def test_plain_help_is_low(self):
        out = check.check(HELP, "comment", rules(), NO_PRODUCT)
        self.assertEqual(out["risk"], "low")
        self.assertEqual(out["reasons"], [])

    def test_promo_phrases_raise_risk(self):
        out = check.check("I built an app for this, check out the free trial and DM me", "comment", rules(),
                          NO_PRODUCT)
        self.assertIn(out["risk"], ("medium", "high"))
        self.assertTrue(any("promo" in r["why"] for r in out["reasons"]))

    def test_links_where_banned_are_high(self):
        out = check.check(HELP + " see https://example.com/guide", "comment",
                          rules(links="banned", evidence=[{"topic": "links", "rule": 3, "quote": "No links"}]),
                          NO_PRODUCT)
        self.assertEqual(out["risk"], "high")
        self.assertTrue(any(r.get("rule") == 3 for r in out["reasons"]))

    def test_shortener_is_high(self):
        out = check.check(HELP + " bit.ly/abc123.", "comment", rules(), NO_PRODUCT)
        self.assertEqual(out["risk"], "high")
        self.assertEqual(out["links"], ["bit.ly/abc123"])

    def test_account_below_minimums_is_high(self):
        out = check.check(HELP, "comment", rules(min_karma=100), NO_PRODUCT)
        self.assertEqual(out["risk"], "high")
        out = check.check(HELP, "comment", rules(min_age_days=30), NO_PRODUCT)
        self.assertEqual(out["risk"], "high")

    def test_post_needs_flair_when_required(self):
        out = check.check(HELP + " " + HELP, "post", rules(flair=True), NO_PRODUCT, title="Sour shots fixed")
        self.assertTrue(any("flair" in r["why"] for r in out["reasons"]))
        out = check.check(HELP + " " + HELP, "post", rules(flair=True), NO_PRODUCT, title="Sour shots fixed",
                          flair="Help")
        self.assertFalse(any("flair" in r["why"] for r in out["reasons"]))

    def test_post_needs_title(self):
        with self.assertRaisesRegex(ValueError, "title"):
            check.check(HELP, "post", rules(), NO_PRODUCT)

    def test_too_short(self):
        out = check.check("this", "comment", rules(), NO_PRODUCT)
        self.assertTrue(any("short" in r["why"] for r in out["reasons"]))

    def test_ai_tells_count(self):
        text = "Great question! Let's delve into it — it's a robust, seamless fix. Hope this helps!"
        out = check.check(text, "comment", rules(), NO_PRODUCT)
        self.assertIn(out["risk"], ("medium", "high"))
        self.assertTrue(out["tells"])

    def test_product_mention_where_allowed_is_promo(self):
        out = check.check("i log shots in brewlog", "comment", rules(self_promo="limited"), PROFILE)
        self.assertNotEqual(out["risk"], "blocked")
        self.assertTrue(out["promo"])

    def test_never_list_used(self):
        out = check.check(HELP + " total game-changer", "comment", rules(), NO_PRODUCT, never=["game-changer"])
        self.assertTrue(any(t["id"] == "never_list" for t in out["tells"]))

    def test_shouting(self):
        out = check.check("THIS IS THE BEST GRINDER EVER, BUY IT NOW!!!", "comment", rules(), NO_PRODUCT)
        self.assertTrue(any("shout" in r["why"] for r in out["reasons"]))


class ReviewFixes(unittest.TestCase):
    BANNED = dict(self_promo="banned")

    def blocked(self, text, profile=PROFILE, **rule):
        return check.check(text, "comment", rules(**(rule or self.BANNED)), profile)["risk"] == "blocked"

    def test_product_name_variants(self):
        for text in ("try Brew Log for this", "brew-log does it", "i use brewlogs app", "brewl\u200bog works",
                     "\uff42\uff52\uff45\uff57\uff4c\uff4f\uff47 is fine"):
            self.assertTrue(self.blocked(text), text)
        multi = {"product": {"name": "Shot Log Pro", "what": "x", "url": ""}, "account": {"karma": 40, "age_days": 20}}
        for text in ("ShotLogPro rocks", "shot-log-pro", "Shot  Log Pro"):
            self.assertTrue(self.blocked(text, multi), text)

    def test_product_domains(self):
        prof = {"product": {"name": "Shotty", "what": "x", "url": "https://slp.tools/home"},
                "account": {"karma": 40, "age_days": 20}}
        for text in ("go to slp.tools/pricing", "see app.slp.tools", "slp[.]tools", "slp (dot) tools",
                     "https://google.com/url?q=https://slp.tools"):
            self.assertTrue(self.blocked(text, prof), text)

    def test_shared_host_needs_path(self):
        prof = {"product": {"name": "Shotty", "what": "x", "url": "https://github.com/me/slp"},
                "account": {"karma": 40, "age_days": 20}}
        self.assertFalse(self.blocked(HELP + " see https://github.com/other/thing", prof))
        self.assertTrue(self.blocked(HELP + " see github.com/me/slp", prof))

    def test_more_promo_wordings(self):
        for text in ("full disclosure, I'm the founder of a shot tracking app", "shameless plug but my side project "
                     "handles this, link on my profile", "I developed an extension for this", "i wrote a little tool "
                     "that does this, it's on my github", "I run a youtube channel about it", "our team ships an app",
                     "affiliate link here, 10% off", "I'm making an app for this", "Check out my new app"):
            out = check.check(HELP + " " + text, "comment", rules(self_promo="banned"), NO_PRODUCT)
            self.assertTrue(out["promo"], text)
            self.assertIn(out["risk"], ("medium", "high"), text)

    def test_ordinary_phrases_are_not_promo(self):
        for text in ("i made the same mistake when i started", "check out the wiki", "we made it work",
                     "costco had a discount", "I subscribe to the theory", "i created a monster lol"):
            out = check.check(HELP + " " + text, "comment", rules(self_promo="banned"), NO_PRODUCT)
            self.assertFalse(out["promo"], text)

    def test_not_links(self):
        for text in ("Thanks.Me too", "yes.At least for me", "mail bob@gmail.com", "edit config.yaml and main.py",
                     "use Node.js", "a 3.5mm jack"):
            self.assertEqual(check.check(HELP + " " + text, "comment", rules(), NO_PRODUCT)["links"], [], text)

    def test_links_found(self):
        out = check.check(HELP + " see example.so/x and amzn.to/3xYz", "comment", rules(), NO_PRODUCT)
        self.assertEqual(len(out["links"]), 2)
        self.assertEqual(out["risk"], "high")  # amzn.to is a shortener

    def test_affiliate_tag(self):
        out = check.check(HELP + " https://www.amazon.com/dp/B0X?tag=me-20", "comment", rules(), NO_PRODUCT)
        self.assertTrue(any("affiliate" in r["why"] for r in out["reasons"]))

    def test_acronyms_are_not_shouting(self):
        out = check.check(HELP + " IMO the OP should RMA it, AFAIK NASA and the FAA agree", "comment", rules(),
                          NO_PRODUCT)
        self.assertFalse(any("shout" in r["why"] for r in out["reasons"]))

    def test_never_list_is_its_own_reason(self):
        out = check.check(HELP + " total game-changer", "comment", rules(), NO_PRODUCT, never=["game-changer"])
        self.assertTrue(any("never list" in r["why"] for r in out["reasons"]))

    def test_unknown_karma(self):
        out = check.check(HELP, "comment", rules(min_karma=10), {"product": None, "account": {}})
        self.assertTrue(any("unknown" in r["why"] for r in out["reasons"]))


if __name__ == "__main__":
    unittest.main()
