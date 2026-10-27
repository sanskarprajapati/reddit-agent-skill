"""Shared paths, and a loader for tools that live in hyphenated skill folders."""

import importlib.util
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILLS_DIR = os.path.join(ROOT, "skills")
FIXTURES = os.path.join(ROOT, "tests", "fixtures")


def load(folder, name):
    path = os.path.join(SKILLS_DIR, folder, name + ".py")
    spec = importlib.util.spec_from_file_location("reddit_" + name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod
