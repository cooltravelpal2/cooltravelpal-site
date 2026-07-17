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
        self.assertTrue(all(item.published_on for item in self.articles))

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
        recent = {self.queue[0].slug}
        actual = []
        for slot in ("morning", "midday", "evening"):
            _, article, is_new = post_to_x.choose_article(
                self.queue, date(2026, 7, 17), slot, recent
            )
            self.assertTrue(is_new)
            actual.append(article.slug)
            recent.add(article.slug)
        self.assertEqual(actual, expected)

    def test_new_article_gets_next_slot_then_is_not_repeated(self):
        new_article = post_to_x.Article(
            slug="new-daily-story",
            title="A New Daily Story",
            summary="A useful new article.",
            category="travel",
            published_on=date(2026, 7, 20),
        )
        queue = [new_article, *self.queue]
        _, selected, is_new = post_to_x.choose_article(
            queue, date(2026, 7, 20), "midday", set()
        )
        self.assertEqual(selected.slug, new_article.slug)
        self.assertTrue(is_new)

        _, next_article, next_is_new = post_to_x.choose_article(
            queue, date(2026, 7, 20), "evening", {new_article.slug}
        )
        self.assertNotEqual(next_article.slug, new_article.slug)
        self.assertFalse(next_is_new)

    def test_recent_evergreen_links_are_skipped(self):
        run_date = date(2026, 8, 20)
        _, first, _ = post_to_x.choose_article(
            self.queue, run_date, "midday", set()
        )
        _, second, _ = post_to_x.choose_article(
            self.queue, run_date, "midday", {first.slug}
        )
        self.assertNotEqual(first.slug, second.slug)

    def test_buffer_history_extracts_article_links(self):
        original = post_to_x.buffer_graphql
        post_to_x.buffer_graphql = lambda *_args, **_kwargs: {
            "data": {
                "posts": {
                    "edges": [
                        {
                            "node": {
                                "text": "Read https://cooltravelpal.com/blog/example-story/"
                            }
                        },
                        {"node": {"text": "A post without a site link"}},
                    ]
                }
            }
        }
        try:
            slugs = post_to_x.get_recent_article_slugs(
                "test-key", post_to_x.BufferTarget("org", "channel")
            )
        finally:
            post_to_x.buffer_graphql = original
        self.assertEqual(slugs, {"example-story"})

    def test_every_post_fits_x(self):
        for article in self.queue:
            with self.subTest(article=article.slug):
                self.assertLessEqual(post_to_x.weighted_length(post_to_x.compose(article)), 280)
                self.assertLessEqual(
                    post_to_x.weighted_length(post_to_x.compose(article, is_new=True)),
                    280,
                )


if __name__ == "__main__":
    unittest.main()
