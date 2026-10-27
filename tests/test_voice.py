import os
import tempfile
import unittest

from _load import load

voice = load("reddit-setup", "voice")
store = load("reddit-setup", "store")

SAMPLES = [
    "honestly i just use a moka pot and its fine for me",
    "grind finer. thats it. thats the whole trick",
    "honestly the scale matters more than the grinder imo",
    "i definately had the same issue, turned out the beans were stale",
    "nah, dont buy the bundle. get a hand grinder first and see if you even like it",
]

GOOD = """# My Reddit voice

## About me
I make coffee at home and work in a warehouse.

## Things I know first-hand
- Gaggia Classic for three years
- hand grinders under $100

## Words I use
- imo, nah

## Words I never use
- delve, game-changer

## Quirks
- lowercase almost everywhere: "honestly i just use a moka pot"
- misspells definitely: "definately"
- short punchy lines: "thats the whole trick"
"""


class Parse(unittest.TestCase):
    def test_sections(self):
        doc = voice.parse(GOOD)
        self.assertEqual(len(doc["knows"]), 2)
        self.assertIn("delve, game-changer", doc["never"])
        self.assertEqual(doc["quirks"][1], {"what": "misspells definitely", "example": "definately"})
        self.assertEqual(doc["unknown_sections"], [])

    def test_quirk_without_example(self):
        doc = voice.parse(GOOD.replace('- short punchy lines: "thats the whole trick"', "- short punchy lines"))
        self.assertEqual(doc["quirks"][2], {"what": "short punchy lines", "example": ""})

    def test_unknown_heading_reported(self):
        doc = voice.parse(GOOD + "\n## Quirk notes\n- adds typos: \"teh\"\n")
        self.assertEqual(doc["unknown_sections"], ["Quirk notes"])


class Check(unittest.TestCase):
    def test_good_file_passes(self):
        self.assertEqual(voice.check(voice.parse(GOOD), SAMPLES), [])

    def test_too_few_samples(self):
        problems = voice.check(voice.parse(GOOD), SAMPLES[:3])
        self.assertTrue(any("5" in p and "sample" in p for p in problems), problems)

    def test_quirk_must_be_in_samples(self):
        problems = voice.check(voice.parse(GOOD.replace('"definately"', '"defintely"')), SAMPLES)
        self.assertTrue(any("defintely" in p for p in problems), problems)

    def test_quirk_needs_an_example(self):
        text = GOOD.replace('- misspells definitely: "definately"', "- misspells definitely")
        problems = voice.check(voice.parse(text), SAMPLES)
        self.assertTrue(any("misspells definitely" in p for p in problems), problems)

    def test_quirk_example_too_thin(self):
        for thin in ('","', '"a"', '"imo"'):
            text = GOOD.replace('"definately"', thin)
            problems = voice.check(voice.parse(text), SAMPLES)
            self.assertTrue(any("too short" in p for p in problems), (thin, problems))

    def test_unknown_heading_is_a_problem(self):
        problems = voice.check(voice.parse(GOOD + "\n## Extra quirks\n- x\n"), SAMPLES)
        self.assertTrue(any("Extra quirks" in p for p in problems), problems)

    def test_needs_first_hand_knowledge(self):
        text = GOOD.replace("- Gaggia Classic for three years\n- hand grinders under $100\n", "")
        problems = voice.check(voice.parse(text), SAMPLES)
        self.assertTrue(any("first-hand" in p for p in problems), problems)


class Measure(unittest.TestCase):
    def test_numbers(self):
        m = voice.measure(SAMPLES)
        self.assertEqual(m["samples"], 5)
        self.assertGreater(m["avg_words"], 5)
        self.assertEqual(m["lowercase_start"], 1.0)
        self.assertIn("honestly", m["openers"])
        self.assertEqual(m["em_dashes"], 0)

    def test_empty(self):
        self.assertEqual(voice.measure([])["samples"], 0)


class Samples(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def test_add_and_read_keep_text_whole(self):
        tricky = "first part\n---\n## Quirks\n- fake: \"part\"\n<!-- hide"
        self.assertEqual(voice.add_samples(self.dir, [tricky, "second one here", tricky]), 2)
        self.assertEqual(voice.read_samples(self.dir), [tricky, "second one here"])

    def test_empty_samples_ignored(self):
        self.assertEqual(voice.add_samples(self.dir, ["", "   "]), 0)

    def test_from_profile_only_own_comments(self):
        cap = {"kind": "profile", "url": "https://www.reddit.com/user/Quiet_Brewer/comments/", "items": [
            {"type": "comment", "text": "grind finer and see"},
            {"type": "post", "text": "my setup"},
            {"type": "comment", "text": ""},
        ]}
        self.assertEqual(voice.samples_from_profile(cap, "quiet_brewer"), ["grind finer and see"])
        with self.assertRaisesRegex(ValueError, "own"):
            voice.samples_from_profile(cap, "someone_else")
        with self.assertRaisesRegex(ValueError, "username"):
            voice.samples_from_profile(cap, "")


class Files(unittest.TestCase):
    def test_init_makes_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = voice.init(tmp)
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            for head in ("## Things I know first-hand", "## Quirks", "## Words I never use"):
                self.assertIn(head, text)
            self.assertEqual(voice.parse(text)["unknown_sections"], [])
            with self.assertRaises(FileExistsError):
                voice.init(tmp)
            self.assertTrue(os.path.exists(path))


if __name__ == "__main__":
    unittest.main()
