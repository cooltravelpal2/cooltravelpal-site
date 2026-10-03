# DongDong daily preview and X integration

DongDong's preview has its own permanent section at `/dongdong/`, linked from
**More from TravelPal LLC** on the apps page and the homepage footer. It does
not add stories to the travel blog index or RSS feed. One current teaser is
updated in place; the full demonstration and bilingual steps stay on DongDong.

## Publishing

GitHub Pages uses the **GitHub Actions** build source. `publish-site.yml` builds
on pushes to main and daily at 00:47 America/Los_Angeles, with recovery runs
at 06:47 and 07:17 before the morning X slot. It fetches
`https://dongdong.now/daily-exercise.json`, requires today's Pacific date,
checks the live lesson marker, and verifies the actual exercise video hash.
It generates the teaser, release JSON and sitemap lastmod in `dist/` and
deploys the artifact. A post-deployment check verifies both sites agree.
Source scripts/tests/editorial docs are excluded from the public artifact.

```sh
python3 -m unittest discover -s tests -v
bash tests/check_routes.sh
python3 scripts/build_site.py
# Local preview only, before DongDong is live:
python3 scripts/build_site.py --fixture /path/to/daily-exercise.json
```

Use **Publish TravelPal and daily exercise preview → Run workflow** for preview
(default dry run) or recovery. Scheduled jobs can run late. A failed daily
source verification aborts deployment, leaving the previous site available.

## Existing X action

The existing 08:17/12:17/17:17 Pacific action still uses BUFFER_API_KEY and
X_AUTOMATION_ENABLED. The morning slot offers the daily exercise instead of an
article only after checking today's DongDong lesson, media, TravelPal teaser
and both release identifiers. Midday/evening retain the travel article queue.
If the daily lesson is stale, unavailable, or already queued/sent, the morning
slot falls back to the existing article selection.

The daily post includes both the complete DongDong lesson and a direct App Store link. A `?day=YYYY-MM-DD`
query identifies the promotional date for duplicate checking in Buffer's most
recent 60 scheduled/sent posts; it does not create an archived lesson. The page
canonical stays the permanent URL. Workflow concurrency serializes posting,
and uncertain createPost failures are not retried automatically.

A run with a historical date is allowed only in dry-run mode. Manual runs can
use the existing **Post blog stories to X** workflow's dry-run input to preview
live selection without publishing. Buffer controls the eventual queue time;
workflow success is evidence of queuing, not proof of delivery on X.

No new cross-repository credential or Azure runtime secret is required.
