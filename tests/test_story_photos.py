import hashlib
import json
import sys
import tempfile
import unittest
import urllib.parse
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import story_photos
from daily_travel_brief import canonical_digest, load_editions
from weekly_digest import freeze_issue, load_issue, publish_story_links
from weekly_sender import payload

PAGES = {
    'Air Canada': {'title': 'Air Canada', 'pageimage': 'Plane.jpg'},
    'Canada': {'title': 'Canada', 'coordinates': [{}], 'pageimage': 'Flag.jpg'},
    'Sunnyvale, California': {'title': 'Sunnyvale, California', 'coordinates': [{}], 'pageimage': 'Murphy_Avenue.jpg'},
    'Montréal': {'title': 'Montréal', 'coordinates': [{}], 'pageimage': 'Montreal_skyline.jpg'},
    'Delta': {'title': 'Delta', 'pageprops': {'disambiguation': ''}},
}
FILES = {
    'Murphy_Avenue.jpg': ('image/jpeg', 3000, 1500, 'CC BY-SA 4.0', 'https://creativecommons.org/licenses/by-sa/4.0', '<a href="x">A. Photographer</a>'),
    'Montreal_skyline.jpg': ('image/jpeg', 3000, 1500, 'CC BY-NC 2.0', 'https://creativecommons.org/licenses/by-nc/2.0', 'Someone'),
}
JPEG = b'\xff\xd8\xff\xe0 test photo'


def reader(url):
    query = dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))
    if url.startswith(story_photos.WIKIPEDIA):
        redirects = [{'from': 'Sunnyvale', 'to': 'Sunnyvale, California'}]
        pages = [PAGES[t] for t in {next((r['to'] for r in redirects if r['from'] == t), t) for t in query['titles'].split('|')} if t in PAGES]
        return json.dumps({'query': {'redirects': redirects, 'pages': pages}}).encode()
    if url.startswith(story_photos.COMMONS):
        name = query['titles'].removeprefix('File:')
        if name not in FILES:
            return json.dumps({'query': {'pages': [{'missing': True}]}}).encode()
        mime, width, height, license, license_url, artist = FILES[name]
        meta = {'LicenseShortName': {'value': license}, 'LicenseUrl': {'value': license_url},
                'Artist': {'value': artist}, 'Restrictions': {'value': ''}, 'Assessments': {'value': 1.5}}
        return json.dumps({'query': {'pages': [{'imageinfo': [{
            'mime': mime, 'width': width, 'height': height, 'extmetadata': meta,
            'thumburl': f'https://upload.wikimedia.org/thumb/{name}/960px-{name}?utm_source=x',
            'descriptionurl': f'https://commons.wikimedia.org/wiki/File:{name}'}]}]}}).encode()
    if url.startswith('https://upload.wikimedia.org/'):
        return JPEG
    raise AssertionError(url)


def edition(day, stories):
    data = {'schemaVersion': 1, 'editionId': day, 'revision': 1, 'status': 'ready', 'policyVersion': 'travel-impact-v1',
            'cutoffAt': day + 'T14:00:00Z', 'generatedAt': day + 'T14:05:00Z', 'stories': [
                {'storyId': story_id, 'section': section, 'rank': 100, 'title': title, 'summary': 'A reported fact.',
                 'verification': 'reported', 'sourcePublishedAt': day + 'T12:00:00Z',
                 'sources': [{'publisher': 'Example', 'url': 'https://example.com/story'}]}
                for story_id, section, title in stories]}
    data['contentDigest'] = canonical_digest(data)
    return data


class StoryPhotoTest(unittest.TestCase):
    def test_place_photo_is_licensed_credited_and_skips_brands(self):
        photo = story_photos.find_photo({'title': 'M Social Hotel Sunnyvale to open in December'}, reader)
        self.assertEqual(photo['credit'], 'Photo: A. Photographer.')
        self.assertEqual(photo['license'], 'CC BY-SA 4.0')
        self.assertEqual(photo['url'], 'https://upload.wikimedia.org/thumb/Murphy_Avenue.jpg/960px-Murphy_Avenue.jpg')
        self.assertIn('not the featured venue', photo['caption'])
        # "Canada" is part of the airline name, and the Montréal photo is non-commercial.
        self.assertIsNone(story_photos.find_photo({'title': 'Air Canada to launch Montréal–Seville service'}, reader))
        self.assertIsNone(story_photos.find_photo({'title': 'Delta previews a new suite'}, reader))

    def test_lookups_are_recorded_once_and_attached_without_touching_the_edition(self):
        with tempfile.TemporaryDirectory() as tmp:
            briefs = Path(tmp) / 'travel-briefs'
            briefs.mkdir()
            raw = edition('2026-10-20', [('a', 'hotels', 'M Social Hotel Sunnyvale opens'), ('b', 'airlines', 'Delta adds Wi-Fi'),
                                         ('c', 'cards', 'Sunnyvale card offer'), ('d', 'hotels', 'Hyatt in Sunnyvale')])
            (briefs / '2026-10-20-r1.json').write_text(json.dumps(raw))
            path = Path(tmp) / 'story-photos.json'
            calls = []
            def failing(url):
                calls.append(url)
                if 'Hyatt' in url:
                    raise OSError('timeout')
                return reader(url)
            self.assertEqual(story_photos.enrich(briefs, path, failing, today=date(2026, 10, 24)), (1, 2))
            photos = json.loads(path.read_text())['photos']
            self.assertEqual(sorted(photos), ['a', 'b'])
            self.assertIsNone(photos['b'])
            calls.clear()
            story_photos.enrich(briefs, path, lambda url: calls.append(url) or reader(url), today=date(2026, 10, 24))
            # Only the story whose lookup failed is retried; recorded entries never change.
            searched = [url for url in calls if url.startswith(story_photos.WIKIPEDIA)]
            self.assertEqual(len(searched), 1)
            self.assertIn('Hyatt', urllib.parse.unquote(searched[0]))
            self.assertEqual(json.loads(path.read_text())['photos']['a'], photos['a'])
            loaded = load_editions(briefs)[0]
            self.assertEqual(loaded['stories'][0]['image']['credit'], 'Photo: A. Photographer.')
            self.assertEqual(json.loads((briefs / '2026-10-20-r1.json').read_text()), raw)


class WeeklyPhotoTest(unittest.TestCase):
    def issue(self, image):
        story = {'storyId': 'a', 'section': 'hotels', 'rank': 90, 'title': 'Sunnyvale opening', 'summary': 'A reported fact.',
                 'briefUrl': 'https://travelpal.now/blog/travel-brief-2026-10-24/#story-' + hashlib.sha256(b'a').hexdigest()[:16]}
        if image:
            story['image'] = story_photos.find_photo({'title': 'M Social Hotel Sunnyvale'}, reader)
        return {'weekEnding': '2026-10-24', 'windowStart': '2026-10-18', 'stories': [story]}

    def test_frozen_photo_replaces_illustration_and_is_credited(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            issue = freeze_issue(self.issue(True), root / 'issues', reader)
            self.assertTrue(issue['stories'][0]['emailPhoto'])
            self.assertEqual((root / 'issues/2026-10-24/story-1.jpg').read_bytes(), JPEG)
            publish_story_links(load_issue(root / 'issues/2026-10-24.json'), root / 'weekly', root / 'issues')
            self.assertEqual((root / 'weekly/2026-10-24/story-1.jpg').read_bytes(), JPEG)
            text = payload({**issue, 'frozenIssue': True})['WeeklyHighlight1']
            self.assertIn('Photo: A. Photographer, CC BY-SA 4.0, via Wikimedia Commons', text)

    def test_unavailable_photo_falls_back_to_illustration(self):
        def broken(url):
            raise OSError('unreachable')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            issue = freeze_issue(self.issue(True), root / 'issues', broken)
            self.assertNotIn('emailPhoto', issue['stories'][0])
            self.assertNotIn('image', issue['stories'][0])
            publish_story_links(issue, root / 'weekly', root / 'issues')
            self.assertNotEqual((root / 'weekly/2026-10-24/story-1.jpg').read_bytes(), JPEG)
            self.assertNotIn('Photo:', payload({**issue, 'frozenIssue': True})['WeeklyHighlight1'])

    def test_owner_test_issue_never_touches_the_sent_saturday_issue(self):
        from weekly_digest import TEST_ISSUES
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sent = freeze_issue(self.issue(False), root / 'issues', reader)
            test = freeze_issue(self.issue(True), root / 'issues/test', reader, key='test-123')
            self.assertEqual(load_issue(root / 'issues/2026-10-24.json'), sent)
            self.assertNotIn('emailPhoto', sent['stories'][0])
            self.assertTrue(test['stories'][0]['emailPhoto'])
            publish_story_links(test, root / 'weekly', root / 'issues/test')
            self.assertEqual((root / 'weekly/test-123/story-1.jpg').read_bytes(), JPEG)
            self.assertTrue((root / 'weekly/test-123/story-1/index.html').exists())
            self.assertFalse((root / 'weekly/2026-10-24').exists())
            self.assertEqual(payload({**test, 'frozenIssue': True})['WeeklyPeriod'], 'test-123')
            self.assertEqual(TEST_ISSUES.name, 'test')


if __name__ == '__main__':
    unittest.main()
