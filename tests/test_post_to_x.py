#!/usr/bin/env python3

import importlib.util
import sys
import unittest
from datetime import date
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "post_to_x.py"
SPEC = importlib.util.spec_from_file_location("post_to_x", MODULE_PATH)
post_to_x = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
sys.modules[SPEC.name] = post_to_x
SPEC.loader.exec_module(post_to_x)


class PostToXTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.articles = post_to_x.load_articles()
        cls.queue = post_to_x.build_queue(cls.articles)

    def test_blog_index_is_parsed(self):
        self.assertGreaterEqual(len(self.articles), 80)
        self.assertEqual(len(self.articles), len({item.slug for item in self.articles}))

    def test_launch_order(self):
        self.assertEqual(
            [item.slug for item in self.queue[:3]],
            [
                "how-i-built-cardpecker-with-ai-vibe-coding",
                "akinoya-yakisoba-nikko-review",
                "dubai-first-time-guide",
            ],
        )

    def test_first_automatic_day_slots_follow_manual_test(self):
        expected = [item.slug for item in self.queue[1:4]]
        actual = [
            post_to_x.choose_article(self.queue, date(2026, 7, 17), slot)[1].slug
            for slot in ("morning", "midday", "evening")
        ]
        self.assertEqual(actual, expected)

    def test_every_post_fits_x(self):
        for article in self.queue:
            with self.subTest(article=article.slug):
                self.assertLessEqual(post_to_x.weighted_length(post_to_x.compose(article)), 280)


if __name__ == "__main__":
    unittest.main()
