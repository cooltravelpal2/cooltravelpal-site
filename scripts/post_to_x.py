#!/usr/bin/env python3
"""Publish a prewritten Cool TravelPal article teaser to X.

The article title and teaser come from the site's checked-in blog index. No AI
model runs in this workflow, so scheduled posts cannot invent facts.
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]
BLOG_INDEX = ROOT / "blog" / "index.html"
SITE = "https://cooltravelpal.com"
TIMEZONE = ZoneInfo("America/Los_Angeles")
START_DATE = date(2026, 7, 17)
START_OFFSET = 1  # CardPecker was queued manually as the live integration test.
SLOTS = {"morning": 0, "midday": 1, "evening": 2}
SLOT_HOURS = {8: "morning", 12: "midday", 17: "evening"}
BUFFER_API_URL = "https://api.buffer.com"
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
    published_on: date

    @property
    def url(self) -> str:
        return f"{SITE}/blog/{self.slug}/"


@dataclass(frozen=True)
class BufferTarget:
    organization_id: str
    channel_id: str


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
    seen_slugs: set[str] = set()
    for slug, body in cards:
        # An article may appear once in the latest-story list and again in a
        # category section. Keep the first card; it is the same article, not a
        # duplicate queue entry.
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        title_match = re.search(r"<h3>(.*?)</h3>", body, flags=re.DOTALL)
        summary_match = re.search(r'<p(?!\s+class="story-meta")[^>]*>(.*?)</p>', body, flags=re.DOTALL)
        category_match = re.search(r'<span\s+class="badge-cat\s+([^"\s]+)[^"]*">', body)
        meta_match = re.search(r'<p\s+class="story-meta"[^>]*>(.*?)</p>', body, flags=re.DOTALL)
        date_match = re.search(
            r"(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
            plain_text(meta_match.group(1)) if meta_match else "",
        )
        if not (title_match and summary_match and category_match and date_match):
            raise ValueError(f"Incomplete blog card for {slug}")
        articles.append(
            Article(
                slug=slug,
                title=plain_text(title_match.group(1)),
                summary=plain_text(summary_match.group(1)),
                category=category_match.group(1),
                published_on=datetime.strptime(date_match.group(0), "%B %d, %Y").date(),
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

    category_order = ["product", "appg", "travel", "exp", "cards"]
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


def compose(article: Article, *, is_new: bool = False) -> str:
    if is_new:
        prefix = f"New on Cool TravelPal — {article.title}: {article.summary}"
    else:
        prefix = CUSTOM_COPY.get(article.slug, f"{article.title}: {article.summary}")
    return trim_for_x(prefix, article.url)


def resolve_slot(requested: str, now: datetime) -> str:
    if requested != "auto":
        return requested
    try:
        return SLOT_HOURS[now.astimezone(TIMEZONE).hour]
    except KeyError as exc:
        raise ValueError(
            "Automatic runs are allowed only at 8:00, 12:00, or 17:00 Pacific"
        ) from exc


def choose_article(
    queue: list[Article],
    run_date: date,
    slot: str,
    recent_slugs: set[str] | frozenset[str] = frozenset(),
) -> tuple[int, Article, bool]:
    days = (run_date - START_DATE).days
    if days < 0:
        raise ValueError(f"Queue starts on {START_DATE.isoformat()}")

    # A post dated today or yesterday is offered to the next scheduled slot.
    # Buffer history prevents it from being selected again at later slots.
    fresh_cutoff = run_date - timedelta(days=1)
    fresh = [
        article
        for article in queue
        if fresh_cutoff <= article.published_on <= run_date
    ]
    for article in fresh:
        if article.slug not in recent_slugs:
            return queue.index(article), article, True

    # Otherwise continue the deterministic evergreen rotation, skipping links
    # that Buffer has recently scheduled or sent and skipping still-fresh posts.
    start = (START_OFFSET + days * len(SLOTS) + SLOTS[slot]) % len(queue)
    fresh_slugs = {article.slug for article in fresh}
    for offset in range(len(queue)):
        index = (start + offset) % len(queue)
        article = queue[index]
        if article.slug not in recent_slugs and article.slug not in fresh_slugs:
            return index, article, False
    raise RuntimeError("No unrepeated article is available for this slot")


def buffer_graphql(api_key: str, query: str, variables: dict[str, object] | None = None) -> dict[str, object]:
    payload = json.dumps(
        {"query": query, "variables": variables or {}}, ensure_ascii=False
    ).encode("utf-8")
    request = urllib.request.Request(
        BUFFER_API_URL,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
            "User-Agent": "CoolTravelPal-X-Automation/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
            if response.status != 200:
                raise RuntimeError(f"Unexpected Buffer response status: {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Buffer API returned HTTP {exc.code}: {detail[:500]}") from exc
    if body.get("errors"):
        raise RuntimeError(f"Buffer API error: {body['errors']}")
    return body


def find_buffer_target(api_key: str) -> BufferTarget:
    account_query = """
    query AccountOrganizations {
      account { organizations { id name } }
    }
    """
    account = buffer_graphql(api_key, account_query)
    organizations = account.get("data", {}).get("account", {}).get("organizations", [])
    matches: list[BufferTarget] = []
    channel_query = """
    query OrganizationChannels($organizationId: OrganizationId!) {
      channels(input: { organizationId: $organizationId }) {
        id name displayName service
      }
    }
    """
    for organization in organizations:
        result = buffer_graphql(
            api_key, channel_query, {"organizationId": organization["id"]}
        )
        for channel in result.get("data", {}).get("channels", []):
            service = str(channel.get("service", "")).lower()
            identity = " ".join(
                str(channel.get(field, "")) for field in ("name", "displayName")
            ).lower()
            if service in {"twitter", "x"} and "cooltravelpal" in identity:
                matches.append(
                    BufferTarget(
                        organization_id=str(organization["id"]),
                        channel_id=str(channel["id"]),
                    )
                )
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one Buffer X channel for @cooltravelpal; found {len(matches)}"
        )
    return matches[0]


def get_recent_article_slugs(api_key: str, target: BufferTarget) -> set[str]:
    """Return article links from the latest scheduled and sent Buffer posts."""
    query = """
    query RecentPosts($input: PostsInput!) {
      posts(first: 60, input: $input) {
        edges { node { id text status dueAt sentAt } }
      }
    }
    """
    result = buffer_graphql(
        api_key,
        query,
        {
            "input": {
                "organizationId": target.organization_id,
                "filter": {
                    "status": ["sent", "scheduled"],
                    "channelIds": [target.channel_id],
                },
                "sort": [
                    {"field": "dueAt", "direction": "desc"},
                    {"field": "createdAt", "direction": "desc"},
                ],
            }
        },
    )
    edges = result.get("data", {}).get("posts", {}).get("edges", [])
    slugs: set[str] = set()
    for edge in edges:
        text = str(edge.get("node", {}).get("text", ""))
        slugs.update(
            re.findall(
                r"https?://(?:www\.)?cooltravelpal\.com/blog/([^/\s?]+)/?",
                text,
            )
        )
    return slugs


def publish(text: str, api_key: str, target: BufferTarget) -> dict[str, object]:
    mutation = """
    mutation CreatePost($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id text dueAt } }
        ... on MutationError { message }
      }
    }
    """
    result = buffer_graphql(
        api_key,
        mutation,
        {
            "input": {
                "text": text,
                "channelId": target.channel_id,
                "schedulingType": "automatic",
                "mode": "addToQueue",
                "assets": [],
            }
        },
    )
    payload = result.get("data", {}).get("createPost", {})
    if payload.get("message"):
        raise RuntimeError(f"Buffer rejected the post: {payload['message']}")
    if not payload.get("post", {}).get("id"):
        raise RuntimeError("Buffer returned no scheduled post ID")
    return payload["post"]


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
    api_key = os.environ.get("BUFFER_API_KEY", "")
    target: BufferTarget | None = None
    recent_slugs: set[str] = set()
    if api_key:
        target = find_buffer_target(api_key)
        recent_slugs = get_recent_article_slugs(api_key, target)
    elif not args.dry_run:
        raise ValueError("Missing GitHub Secret: BUFFER_API_KEY")

    index, article, is_new = choose_article(queue, run_date, slot, recent_slugs)
    text = compose(article, is_new=is_new)

    print(f"Queue item: {index + 1}/{len(queue)}")
    print(f"Slot: {slot}")
    print(f"Selection: {'new article priority' if is_new else 'evergreen rotation'}")
    print(f"Recent article links skipped: {len(recent_slugs)}")
    print(f"Article: {article.slug}")
    print(f"Weighted length: {weighted_length(text)}/280")
    print("---")
    print(text)

    if args.dry_run:
        print("---\nDry run: nothing was published.")
        return 0

    if target is None:
        raise RuntimeError("Buffer target was not loaded")
    result = publish(text, api_key, target)
    print(f"---\nQueued in Buffer: {result['id']} (due {result.get('dueAt', 'next slot')})")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
