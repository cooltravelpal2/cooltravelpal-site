#!/usr/bin/env python3
"""Publish a prewritten Cool TravelPal article teaser to X.

The article title and teaser come from the site's checked-in blog index. No AI
model runs in this workflow, so scheduled posts cannot invent facts.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
BLOG_INDEX = ROOT / "blog" / "index.html"
SITE = "https://cooltravelpal.com"
TIMEZONE = ZoneInfo("America/Los_Angeles")
START_DATE = date(2026, 7, 16)
SLOTS = {"morning": 0, "midday": 1, "evening": 2}
SLOT_HOURS = {9: "morning", 13: "midday", 18: "evening"}
X_POST_URL = "https://api.x.com/2/tweets"
URL_LENGTH = 23

# Launch the queue with the stories we want to introduce first. The remaining
# articles are interleaved by category so the feed does not become repetitive.
PINNED_SLUGS = [
    "how-i-built-cardpecker-with-ai-vibe-coding",
    "akinoya-yakisoba-nikko-review",
    "dubai-first-time-guide",
    "louvre-egyptian-antiquities-route",
    "adora-magic-city-cruise-guide",
    "best-transferable-points-cards-business-class-awards",
]

CUSTOM_COPY = {
    "how-i-built-cardpecker-with-ai-vibe-coding": (
        "A beginner can build a working app with AI in hours. Turning it into "
        "a product took weeks: product decisions, architecture, testing, "
        "privacy, and polish. Here is how I built CardPecker with no coding "
        "background."
    ),
    "akinoya-yakisoba-nikko-review": (
        "A bowl of yakisoba can be a destination in itself. Akinoya was one of "
        "my favorite food stops in Nikko—simple, satisfying, and worth knowing "
        "before your visit."
    ),
    "dubai-first-time-guide": (
        "Dubai works best when you plan by area instead of zigzagging across "
        "the city. This realistic three-day plan groups Old Dubai, Downtown, "
        "and the coast or desert into a practical route."
    ),
}


@dataclass(frozen=True)
class Article:
    slug: str
    title: str
    summary: str
    category: str

    @property
    def url(self) -> str:
        return f"{SITE}/blog/{self.slug}/"


def plain_text(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", fragment)).split())


def load_articles(path: Path = BLOG_INDEX) -> list[Article]:
    source = path.read_text(encoding="utf-8")
    cards = re.findall(
        r'<a\s+class="story-card[^"]*"\s+href="/blog/([^"/]+)/"[^>]*>(.*?)</a>',
        source,
        flags=re.DOTALL,
    )
    articles: list[Article] = []
    for slug, body in cards:
        title_match = re.search(r"<h3>(.*?)</h3>", body, flags=re.DOTALL)
        summary_match = re.search(r'<p(?!\s+class="story-meta")[^>]*>(.*?)</p>', body, flags=re.DOTALL)
        category_match = re.search(r'<span\s+class="badge-cat\s+([^"\s]+)[^"]*">', body)
        if not (title_match and summary_match and category_match):
            raise ValueError(f"Incomplete blog card for {slug}")
        articles.append(
            Article(
                slug=slug,
                title=plain_text(title_match.group(1)),
                summary=plain_text(summary_match.group(1)),
                category=category_match.group(1),
            )
        )

    if not articles:
        raise ValueError(f"No blog cards found in {path}")
    if len({article.slug for article in articles}) != len(articles):
        raise ValueError("Duplicate blog article slugs found")
    return articles


def build_queue(articles: list[Article]) -> list[Article]:
    by_slug = {article.slug: article for article in articles}
    pinned = [by_slug[slug] for slug in PINNED_SLUGS if slug in by_slug]
    pinned_set = {article.slug for article in pinned}

    category_order = ["appg", "travel", "exp", "cards"]
    buckets: dict[str, list[Article]] = {key: [] for key in category_order}
    for article in articles:
        if article.slug not in pinned_set:
            buckets.setdefault(article.category, []).append(article)
    for bucket in buckets.values():
        bucket.sort(key=lambda article: article.slug)

    interleaved: list[Article] = []
    while any(buckets.values()):
        for category in category_order + sorted(set(buckets) - set(category_order)):
            if buckets.get(category):
                interleaved.append(buckets[category].pop(0))
    return pinned + interleaved


def weighted_length(text: str) -> int:
    urls = re.findall(r"https?://\S+", text)
    without_urls = re.sub(r"https?://\S+", "", text)
    return len(without_urls) + URL_LENGTH * len(urls)


def trim_for_x(prefix: str, url: str, limit: int = 280) -> str:
    available = limit - URL_LENGTH - 2
    if len(prefix) > available:
        shortened = prefix[: available - 1].rsplit(" ", 1)[0].rstrip(" ,;:-")
        prefix = shortened + "…"
    post = f"{prefix}\n\n{url}"
    if weighted_length(post) > limit:
        raise ValueError("Post is longer than X's 280-character weighted limit")
    return post


def compose(article: Article) -> str:
    prefix = CUSTOM_COPY.get(article.slug, f"{article.title}: {article.summary}")
    return trim_for_x(prefix, article.url)


def resolve_slot(requested: str, now: datetime) -> str:
    if requested != "auto":
        return requested
    try:
        return SLOT_HOURS[now.astimezone(TIMEZONE).hour]
    except KeyError as exc:
        raise ValueError(
            "Automatic runs are allowed only at 9:00, 13:00, or 18:00 Pacific"
        ) from exc


def choose_article(queue: list[Article], run_date: date, slot: str) -> tuple[int, Article]:
    days = (run_date - START_DATE).days
    if days < 0:
        raise ValueError(f"Queue starts on {START_DATE.isoformat()}")
    index = (days * len(SLOTS) + SLOTS[slot]) % len(queue)
    return index, queue[index]


def percent(value: str) -> str:
    return urllib.parse.quote(value, safe="~-._")


def oauth_header(method: str, url: str, credentials: dict[str, str]) -> str:
    oauth = {
        "oauth_consumer_key": credentials["X_API_KEY"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": credentials["X_ACCESS_TOKEN"],
        "oauth_version": "1.0",
    }
    parameter_string = "&".join(
        f"{percent(key)}={percent(value)}" for key, value in sorted(oauth.items())
    )
    signature_base = "&".join(
        [method.upper(), percent(url), percent(parameter_string)]
    )
    signing_key = "&".join(
        [percent(credentials["X_API_SECRET"]), percent(credentials["X_ACCESS_TOKEN_SECRET"])]
    )
    digest = hmac.new(
        signing_key.encode(), signature_base.encode(), hashlib.sha1
    ).digest()
    oauth["oauth_signature"] = base64.b64encode(digest).decode()
    return "OAuth " + ", ".join(
        f'{percent(key)}="{percent(value)}"' for key, value in sorted(oauth.items())
    )


def publish(text: str) -> dict[str, object]:
    names = ["X_API_KEY", "X_API_SECRET", "X_ACCESS_TOKEN", "X_ACCESS_TOKEN_SECRET"]
    credentials = {name: os.environ.get(name, "") for name in names}
    missing = [name for name, value in credentials.items() if not value]
    if missing:
        raise ValueError("Missing GitHub Secrets: " + ", ".join(missing))

    payload = json.dumps({"text": text}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        X_POST_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": oauth_header("POST", X_POST_URL, credentials),
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "CoolTravelPal-X-Automation/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
            if response.status != 201:
                raise RuntimeError(f"Unexpected X response status: {response.status}")
            return body
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"X API returned HTTP {exc.code}: {detail[:500]}") from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", choices=["auto", *SLOTS], default="auto")
    parser.add_argument("--date", help="Pacific run date (YYYY-MM-DD), primarily for tests")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    now = datetime.now(TIMEZONE)
    run_date = date.fromisoformat(args.date) if args.date else now.date()
    slot = resolve_slot(args.slot, now)
    queue = build_queue(load_articles())
    index, article = choose_article(queue, run_date, slot)
    text = compose(article)

    print(f"Queue item: {index + 1}/{len(queue)}")
    print(f"Slot: {slot}")
    print(f"Article: {article.slug}")
    print(f"Weighted length: {weighted_length(text)}/280")
    print("---")
    print(text)

    if args.dry_run:
        print("---\nDry run: nothing was published.")
        return 0

    result = publish(text)
    post_id = result.get("data", {}).get("id") if isinstance(result.get("data"), dict) else None
    if not post_id:
        raise RuntimeError("X accepted the request but returned no post ID")
    print(f"---\nPublished: https://x.com/cooltravelpal/status/{post_id}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
