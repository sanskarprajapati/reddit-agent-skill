import unittest

from _load import load

tells = load("reddit-check", "tells")


def ids(text, never=()):
    return {h["id"] for h in tells.detect(text, never)}


class Detect(unittest.TestCase):
    def test_clean_casual_comment_has_none(self):
        text = "grind finer and pull it a bit longer. my gaggia did the same thing till i got a better grinder"
        self.assertEqual(tells.detect(text), [])

    def test_em_dash(self):
        self.assertIn("em_dash", ids("It works — mostly."))

    def test_stock_openers_and_closers(self):
        self.assertIn("stock_opener", ids("Great question! The answer is grind size."))
        self.assertIn("stock_opener", ids("Absolutely! Grind finer."))
        self.assertIn("stock_closer", ids("Grind finer. Hope this helps!"))
        self.assertIn("stock_closer", ids("Grind finer. Feel free to ask if you have questions."))

    def test_ai_vocabulary(self):
        hits = {h["id"]: h for h in tells.detect("Let's delve into this. It's a testament to a robust, seamless "
                                                 "workflow.")}
        self.assertIn("ai_words", hits)
        self.assertGreaterEqual(hits["ai_words"]["count"], 3)
        self.assertIn("delve", [e.lower() for e in hits["ai_words"]["examples"]])

    def test_words_inside_other_words_do_not_count(self):
        self.assertNotIn("ai_words", ids("the robustas were delvery fresh"))

    def test_structure(self):
        self.assertIn("headings", ids("## Summary\nGrind finer."))
        self.assertIn("bold", ids("**Grind** finer and **tamp** evenly and **weigh** it."))
        self.assertIn("list", ids("Try this:\n- grind finer\n- tamp evenly\n- weigh the dose"))

    def test_not_x_but_y(self):
        self.assertIn("not_x_but_y", ids("It's not just about the grinder, it's about the beans."))
        self.assertIn("not_x_but_y", ids("This isn't a grinder problem. It's a bean problem."))

    def test_emoji(self):
        self.assertIn("emoji", ids("Great shot \U0001F525☕ love it \U0001F44D"))
        self.assertNotIn("emoji", ids("Great shot ☕"))

    def test_never_list(self):
        hits = {h["id"]: h for h in tells.detect("This grinder is a game-changer imo", never=["game-changer"])}
        self.assertIn("never_list", hits)

    def test_weights_summed(self):
        self.assertEqual(tells.weight([]), 0)
        self.assertGreater(tells.weight(tells.detect("Great question! Let's delve in — hope this helps!")), 3)


class FalsePositives(unittest.TestCase):
    def test_ordinary_comments(self):
        for text in ("this is not ok. but whatever", "It's not that hard, but it takes practice",
                     "Absolutely not.", "Of course it broke", "$40 \u2013 $60 is normal",
                     "navigate to settings and unlock the steam wand in landscape mode", "Crucial RAM is fine"):
            self.assertEqual(tells.detect(text), [], text)


if __name__ == "__main__":
    unittest.main()
