import json
import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import daily_travel_brief as brief
import post_to_x as posting


def fixture(day='2026-10-03', revision=1):
    value = {'schemaVersion': 1, 'editionId': day, 'revision': revision, 'status': 'ready_with_limited_coverage',
             'policyVersion': 'travel-impact-v1', 'sourceRunIds': ['fixture-run'],
             'cutoffAt': day + 'T14:30:00Z', 'generatedAt': day + 'T14:30:00Z', 'coverageStatus': 'limited',
             'coverage': [], 'stories': [{'storyId': 'fixture-hotel', 'storyRevision': 1, 'section': 'hotels',
                'rank': 90, 'title': 'Hyatt opens a new mountain resort — test fixture',
                'summary': 'Synthetic preview data. This is not a real hotel announcement.',
                'verification': 'officially_confirmed', 'sourcePublishedAt': day + 'T10:00:00Z',
                'sources': [{'publisher': 'Hyatt', 'url': 'https://newsroom.hyatt.com/'}],
                'terms': None, 'active': True}]}
    value['contentDigest'] = brief.canonical_digest(value)
    return value


class TravelBriefTests(unittest.TestCase):
    def test_reviewed_image_and_homepage_highlight(self):
        data = fixture()
        data['stories'][0]['image'] = {'url': 'https://upload.wikimedia.org/photo.jpg',
            'alt': 'Destination <photo>', 'caption': 'Destination, not the hotel.',
            'credit': 'Photographer', 'sourceUrl': 'https://commons.wikimedia.org/photo',
            'licenseUrl': 'https://creativecommons.org/licenses/by/2.0/',
            'license': 'CC BY 2.0', 'rightsReviewed': True}
        data['contentDigest'] = brief.canonical_digest(data)
        brief.validate(data)
        rendered = brief.article_html(data)
        self.assertIn('Destination &lt;photo&gt;', rendered)
        self.assertIn('Photo source', rendered)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / 'index.html').write_text('<main><!-- TRAVEL_BRIEF_HIGHLIGHT_START --><!-- TRAVEL_BRIEF_HIGHLIGHT_END --></main>')
            brief.render(output, [data])
            self.assertIn('data-travel-brief-highlight', (output / 'index.html').read_text())
            self.assertIn('/blog/travel-brief-2026-10-03/', (output / 'index.html').read_text())
        for key, value in [('url', 'javascript:alert(1)'), ('rightsReviewed', False)]:
            bad = json.loads(json.dumps(data)); bad['stories'][0]['image'][key] = value
            bad['contentDigest'] = brief.canonical_digest(bad)
            with self.assertRaises(ValueError):
                brief.validate(bad)

    def test_validation_rejects_changed_digest_date_and_unsafe_urls(self):
        data = fixture()
        brief.validate(data)
        with self.assertRaises(ValueError):
            brief.validate({**data, 'editionId': '../bad'})
        bad = fixture(); bad['stories'][0]['title'] = 'changed'
        with self.assertRaises(ValueError):
            brief.validate(bad)
        bad = fixture(); bad['stories'][0]['sources'][0]['url'] = 'javascript:alert(1)'
        bad['contentDigest'] = brief.canonical_digest(bad)
        with self.assertRaises(ValueError):
            brief.validate(bad)

    def test_snapshot_archive_keeps_editions_and_latest_revision(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            def reader(_):
                return json.dumps({'editions': [fixture(), fixture('2026-10-02')], 'nextCursor': None}).encode()
            self.assertEqual(brief.sync(directory, reader=reader), 2)
            self.assertEqual(brief.sync(directory, reader=reader), 0)
            def revised(_):
                return json.dumps({'editions': [fixture(revision=2)], 'nextCursor': None}).encode()
            brief.sync(directory, reader=revised)
            editions = brief.load_editions(directory)
            self.assertEqual([e['revision'] for e in editions], [2, 1])
            self.assertEqual(len(list(directory.glob('*.json'))), 3)

    def test_malformed_sync_writes_nothing(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                brief.sync(Path(temp), reader=lambda _: json.dumps({'editions': [fixture(), {'schemaVersion': 999}]}).encode())
            self.assertEqual(list(Path(temp).glob('*.json')), [])

    def test_immutable_revision_collision_writes_no_other_snapshots(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            brief.sync(directory, reader=lambda _: json.dumps({'editions': [fixture()]}).encode())
            changed = fixture(); changed['stories'][0]['summary'] = 'Changed facts under the same revision'
            changed['contentDigest'] = brief.canonical_digest(changed)
            with self.assertRaises(ValueError):
                brief.sync(directory, reader=lambda _: json.dumps({'editions': [fixture('2026-10-02'), changed]}).encode())
            self.assertEqual(len(list(directory.glob('*.json'))), 1)

    def test_withdrawal_removes_summary_and_disables_daily_promotion(self):
        data = fixture(); data['stories'][0]['active'] = False
        data['contentDigest'] = brief.canonical_digest(data)
        rendered = brief.article_html(data)
        self.assertIn('withdrawn', rendered)
        self.assertNotIn(data['stories'][0]['summary'], rendered)
        with tempfile.TemporaryDirectory() as temp:
            brief.render(Path(temp), [data])
            manifest = json.loads((Path(temp) / 'daily-travel-brief.json').read_text())
            self.assertEqual(manifest['status'], 'withdrawn')
            self.assertEqual(manifest['headlines'], [])

    def test_render_rebuild_preserves_archive_and_escapes_content(self):
        data = fixture(); data['stories'][0]['summary'] = '<script>alert(1)</script>'
        data['contentDigest'] = brief.canonical_digest(data)
        rendered = brief.article_html(data)
        self.assertIn('&lt;script&gt;', rendered)
        self.assertNotIn('<script>alert', rendered)
        self.assertIn('TravelPal.now', rendered)
        self.assertIn('Coverage is limited', rendered)
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            for day in range(2):
                brief.render(output, [fixture(), fixture('2026-10-02')])
                self.assertTrue((output / 'blog/travel-brief-2026-10-02/index.html').exists())
                self.assertEqual(json.loads((output / 'daily-travel-brief.json').read_text())['editionId'], '2026-10-03')

    def test_daily_rss_is_current_ordered_and_revision_safe(self):
        import xml.etree.ElementTree as ET
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            (output / 'feed.xml').write_text('<rss><channel><lastBuildDate>Fri, 02 Oct 2026 10:00:00 +0000</lastBuildDate><item><title>Earlier story</title><guid>earlier</guid><pubDate>Fri, 02 Oct 2026 10:00:00 +0000</pubDate></item></channel></rss>')
            brief.render(output, [fixture(), fixture('2026-10-02')])
            brief.render(output, [fixture(revision=2), fixture('2026-10-02')])
            channel = ET.parse(output / 'feed.xml').getroot().find('channel')
            items = channel.findall('item')
            self.assertEqual(len(items), 3)
            self.assertEqual(items[0].findtext('guid'), brief.article_url(fixture()))
            self.assertIn('03 Oct 2026', channel.findtext('lastBuildDate'))

    def test_live_marker_and_midday_duplicate_protection(self):
        data = fixture()
        manifest = {'schemaVersion': 1, 'editionId': data['editionId'], 'revision': 1, 'status': data['status'],
                    'url': brief.article_url(data), 'contentDigest': data['contentDigest'], 'headlines': ['Hyatt opens a mountain resort']}
        replies = [json.dumps(manifest).encode(), brief.article_html(data).encode()]
        self.assertEqual(brief.load_live(date(2026, 10, 3), reader=lambda _: replies.pop(0)), manifest)
        with self.assertRaises(ValueError):
            brief.load_live(date(2026, 10, 3), reader=lambda url: json.dumps(manifest).encode() if url.endswith('.json') else b'old article')
        with patch.dict(os.environ, {'TRAVEL_BRIEF_X_ENABLED': 'true'}), patch.object(posting, 'load_live_brief', return_value=manifest):
            text = posting.choose_brief_text(date(2026, 10, 3), 'midday', [])
            self.assertIn('TravelPal.now', text)
            self.assertLessEqual(posting.weighted_length(text), 280)
            self.assertIsNone(posting.choose_brief_text(date(2026, 10, 3), 'evening', [text]))
            self.assertIsNone(posting.choose_brief_text(date(2026, 10, 3), 'morning', []))

    def test_old_briefs_never_enter_evergreen_rotation(self):
        article = posting.Article(slug='travel-brief-2026-09-01', title='Old news', summary='Old news', category='travel', published_on=date(2026, 9, 1))
        self.assertNotIn(article, posting.build_queue([article, *posting.load_articles()]))

    def test_disabled_or_unpublished_brief_falls_back(self):
        with patch.dict(os.environ, {'TRAVEL_BRIEF_X_ENABLED': 'false'}), patch.object(posting, 'load_live_brief') as load:
            self.assertIsNone(posting.choose_brief_text(date(2026, 10, 3), 'midday', []))
            load.assert_not_called()
        with patch.dict(os.environ, {'TRAVEL_BRIEF_X_ENABLED': 'true'}), patch.object(posting, 'load_live_brief', side_effect=ValueError('unpublished')):
            self.assertIsNone(posting.choose_brief_text(date(2026, 10, 3), 'midday', []))


if __name__ == '__main__':
    unittest.main()
