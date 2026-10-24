#!/usr/bin/env python3
"""Attach openly licensed Wikimedia Commons destination photos to daily stories.

Feed editions are digest-signed and immutable, so photos live in a separate
append-only sidecar keyed by story ID. A photo is only used when the license is
on an allowlist, the author is credited and Commons lists no restrictions.
"""
import html
import json
import re
import sys
import urllib.parse
from datetime import date, timedelta
from pathlib import Path
from daily_travel_brief import ROOT, load_editions, load_photos, read_url, validate_image

PHOTOS = ROOT / 'data/story-photos.json'
USER_AGENT = 'TravelPal.nowBrief/1.0 (https://travelpal.now/)'
WIKIPEDIA = 'https://en.wikipedia.org/w/api.php?'
COMMONS = 'https://commons.wikimedia.org/w/api.php?'
# Card stories rarely name a place, and card or logo imagery raises trademark questions.
PHOTO_SECTIONS = {'hotels', 'airlines', 'destinations'}
LICENSES = re.compile(r'CC0(?: 1\.0)?|CC BY(?:-SA)? (?:2\.0|2\.5|3\.0|4\.0)')
LICENSE_HOST = 'creativecommons.org'
NOT_PHOTOS = re.compile(r'\b(?:map|flag|logo|seal|coat of arms|locator|diagram|chart|sign|emblem)\b', re.I)
# Single words that resolve to places but in travel news usually mean a brand.
BRAND_WORDS = {'Alaska', 'Hawaiian', 'Delta', 'United', 'American', 'Southwest', 'Frontier', 'Spirit',
               'Virgin', 'Emirates', 'Etihad', 'Qatar', 'Turkish', 'Singapore', 'Canada', 'Breeze',
               'Allegiant', 'Sun Country', 'Avelo', 'Norwegian', 'Iberia', 'Atmos', 'Aeroplan'}
LOOKUP_DAYS = 10
LOOKUP_LIMIT = 25


def candidates(title):
    """Capitalized phrases and their sub-phrases, longest first, as place-name guesses."""
    words = re.findall(r"[A-Z][\w.'’]*(?:[ ](?:[A-Z][\w.'’]*|de|del|la|of))*", title.replace('–', ' – '))
    found = []
    for span in words:
        parts = span.split(' ')
        while parts and parts[-1] in {'de', 'del', 'la', 'of'}:
            parts.pop()
        for size in range(min(len(parts), 4), 0, -1):
            for start in range(len(parts) - size + 1):
                phrase = ' '.join(parts[start:start + size]).rstrip('.’\'').removesuffix('’s').removesuffix("'s")
                if phrase and phrase not in found and phrase.lower() not in {'the', 'a', 'an', 'new', 'report', 'reported'}:
                    found.append(phrase)
    return found[:40]


def api(base, params, reader):
    return json.loads(reader(base + urllib.parse.urlencode({**params, 'format': 'json', 'formatversion': 2})))


def find_places(title, reader):
    """Candidates whose Wikipedia article is a mapped place with a free lead image, most specific first."""
    names = candidates(title)
    if not names:
        return []
    query = api(WIKIPEDIA, {'action': 'query', 'redirects': 1, 'prop': 'coordinates|pageprops|pageimages',
                            'coprimary': 'primary', 'ppprop': 'disambiguation', 'piprop': 'name',
                            'pilicense': 'free', 'titles': '|'.join(names)}, reader)['query']
    resolved = {r['from']: r['to'] for r in query.get('redirects', []) + query.get('normalized', [])}
    pages = {p['title']: p for p in query.get('pages', []) if not p.get('missing')}
    # A phrase like "Air Canada" that names a non-place article rules out its parts.
    entities = [n for n in names if resolved.get(n, n) in pages and not pages[resolved.get(n, n)].get('coordinates')]
    places = []
    for name in names:
        page = pages.get(resolved.get(name, name))
        if not page or name in BRAND_WORDS or any(name != e and name in e for e in entities):
            continue
        if (page.get('coordinates') and 'disambiguation' not in page.get('pageprops', {}) and page.get('pageimage')
                and (page['title'], page['pageimage']) not in places):
            places.append((page['title'], page['pageimage']))
    return places


def plain(value):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', '', str(value or '')))).strip()


def commons_photo(place, filename, reader):
    pages = api(COMMONS, {'action': 'query', 'prop': 'imageinfo', 'iiprop': 'url|mime|size|extmetadata',
                          'iiurlwidth': 960, 'titles': 'File:' + filename}, reader)['query']['pages']
    if not pages or pages[0].get('missing') or not pages[0].get('imageinfo'):
        return None
    info = pages[0]['imageinfo'][0]
    meta = {key: plain(value.get('value')) for key, value in info.get('extmetadata', {}).items()}
    license_url = meta.get('LicenseUrl', '').replace('http://', 'https://')
    artist = meta.get('Artist', '')
    if (info.get('mime') != 'image/jpeg' or info.get('width', 0) < 800 or info['width'] <= info.get('height', 0)
            or NOT_PHOTOS.search(filename.replace('_', ' ')) or not LICENSES.fullmatch(meta.get('LicenseShortName', ''))
            or urllib.parse.urlsplit(license_url).hostname != LICENSE_HOST or meta.get('Restrictions')
            or meta.get('NonFree', 'false') != 'false' or not 1 <= len(artist) <= 120 or not info.get('thumburl')):
        return None
    url = info['thumburl'].split('?')[0]
    if urllib.parse.urlsplit(url).hostname not in {'upload.wikimedia.org', 'thumb.wikimedia.org'}:
        return None
    return validate_image({
        'url': url,
        'alt': f'{place}, photograph from Wikimedia Commons',
        'caption': f'{place}. Destination photograph, not the featured venue or company. Displayed without edits.',
        'credit': f'Photo: {artist.rstrip(".")}.',
        'sourceUrl': info['descriptionurl'],
        'licenseUrl': license_url,
        'license': meta['LicenseShortName'],
        'rightsReviewed': True,
        'rightsReview': 'automated Wikimedia Commons license check',
    })


def find_photo(story, reader):
    for place, filename in find_places(story['title'], reader)[:3]:
        photo = commons_photo(place, filename, reader)
        if photo:
            return photo
    return None


def wikimedia_reader(url):
    return read_url(url, user_agent=USER_AGENT)


def enrich(directory, path=PHOTOS, reader=wikimedia_reader, today=None, limit=LOOKUP_LIMIT):
    """Look up photos for recent stories that lack one. Entries are never replaced once recorded."""
    photos = load_photos(path)
    since = (today or date.today()) - timedelta(days=LOOKUP_DAYS)
    added = 0
    for edition in load_editions(directory, photos={}):
        if date.fromisoformat(edition['editionId']) < since:
            continue
        for story in edition['stories']:
            if added >= limit:
                break
            if story['storyId'] in photos or story.get('image') or story['section'] not in PHOTO_SECTIONS or not story.get('active', True):
                continue
            try:
                photos[story['storyId']] = find_photo(story, reader)
            except (OSError, ValueError, KeyError, TypeError) as error:
                # Transient failures are retried on the next run; only completed lookups are recorded.
                print(f'Photo lookup skipped for {story["storyId"]}: {error}', file=sys.stderr)
                continue
            added += 1
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'schemaVersion': 1, 'photos': dict(sorted(photos.items()))}, ensure_ascii=False, indent=2) + '\n')
    temporary.replace(path)
    return sum(1 for value in photos.values() if value), added


if __name__ == '__main__':
    found, checked = enrich(ROOT / 'data/travel-briefs')
    print(f'Story photos: {checked} stories checked; {found} stories have a licensed photo')
