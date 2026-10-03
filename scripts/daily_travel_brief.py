#!/usr/bin/env python3
"""Validate and render server-owned travel editions; never search or invent facts."""
import argparse
import hashlib
import html
import json
import re
import sys
import urllib.request
import urllib.parse
from datetime import date, datetime
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SITE = 'https://travelpal.now'
FEED = 'https://cardpecker-feed.azurewebsites.net'
SECTIONS = {'hotels': 'Hotels & exceptional stays', 'airlines': 'Airlines & loyalty',
            'cards': 'Cards & points', 'destinations': 'Destinations & access'}
PUBLISHABLE = {'ready', 'ready_with_limited_coverage'}


def canonical_digest(data):
    value = {k: v for k, v in data.items() if k != 'contentDigest'}
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def public_https(value):
    if not isinstance(value, str):
        return False
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError:
        return False
    return parsed.scheme == 'https' and parsed.hostname and not parsed.username and not parsed.password and not port and ':' not in parsed.hostname and not re.match(r'^\d+\.\d+\.\d+\.\d+$', parsed.hostname) and parsed.hostname != 'localhost' and not parsed.hostname.endswith('.local')


def validate(data):
    if not isinstance(data, dict) or data.get('schemaVersion') != 1:
        raise ValueError('Unsupported edition schema')
    day = data.get('editionId', '')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        raise ValueError('Invalid edition date')
    date.fromisoformat(day)
    if type(data.get('revision')) is not int or data['revision'] < 1:
        raise ValueError('Invalid edition revision')
    if data.get('status') not in PUBLISHABLE | {'no_qualifying_news'}:
        raise ValueError('Edition is not finalized')
    if data.get('policyVersion') != 'travel-impact-v1':
        raise ValueError('Unsupported editorial policy')
    if canonical_digest(data) != data.get('contentDigest'):
        raise ValueError('Edition digest mismatch')
    for field in ['cutoffAt', 'generatedAt']:
        datetime.fromisoformat(data[field].replace('Z', '+00:00'))
    if not isinstance(data.get('stories'), list) or len(data['stories']) > 100:
        raise ValueError('Invalid story collection')
    seen = set()
    for story in data.get('stories', []):
        if not isinstance(story, dict):
            raise ValueError('Invalid story')
        if not isinstance(story.get('storyId'), str) or story['storyId'] in seen:
            raise ValueError('Missing or duplicate story ID')
        seen.add(story['storyId'])
        if story.get('section') not in SECTIONS:
            raise ValueError('Unknown story section')
        if story.get('verification') not in {'officially_confirmed', 'reported'}:
            raise ValueError('Unsupported verification')
        if not isinstance(story.get('sources'), list) or not 1 <= len(story['sources']) <= 10 or any(not isinstance(s, dict) or not public_https(s.get('url', '')) or not isinstance(s.get('publisher'), str) for s in story['sources']):
            raise ValueError('Missing or invalid story evidence')
        if not isinstance(story.get('title'), str) or not 1 <= len(story['title']) <= 240:
            raise ValueError('Invalid title')
        if not isinstance(story.get('summary'), str) or len(story['summary']) > 1000:
            raise ValueError('Invalid summary')
        datetime.fromisoformat(story['sourcePublishedAt'].replace('Z', '+00:00'))
        if story.get('image') is not None:
            validate_image(story['image'])
    return data


def validate_image(image):
    if not isinstance(image, dict) or image.get('rightsReviewed') is not True:
        raise ValueError('Image reuse must be reviewed')
    for field in ['url', 'sourceUrl', 'licenseUrl']:
        if not public_https(image.get(field)):
            raise ValueError('Invalid image URL')
    for field in ['alt', 'caption', 'credit', 'license']:
        if not isinstance(image.get(field), str) or not 1 <= len(image[field]) <= 600:
            raise ValueError('Missing image attribution or description')
    return image


def image_html(image):
    validate_image(image)
    esc = html.escape
    return (f'<figure class="brief-photo"><img src="{esc(image["url"], quote=True)}" '
            f'alt="{esc(image["alt"], quote=True)}" loading="lazy" decoding="async">'
            f'<figcaption>{esc(image["caption"])} {esc(image["credit"])} '
            f'<a href="{esc(image["sourceUrl"], quote=True)}">Photo source</a> · '
            f'<a href="{esc(image["licenseUrl"], quote=True)}">{esc(image["license"])}</a>'
            '</figcaption></figure>')


class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            raise ValueError('Cross-host redirect rejected')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def read_url(url, max_bytes=2_000_000):
    if not public_https(url):
        raise ValueError('Invalid public URL')
    request = urllib.request.Request(url, headers={'User-Agent': 'TravelPal.nowBrief/1.0'})
    with urllib.request.build_opener(RestrictedRedirect).open(request, timeout=15) as response:
        content = response.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError('Response too large')
    return content


def sync(directory, base=FEED, reader=read_url):
    if base != FEED:
        raise ValueError('Unexpected feed origin')
    editions, cursor = {}, ''
    for _ in range(20):
        page = json.loads(reader(base + '/v1/briefs?limit=50&after=' + urllib.parse.quote(cursor)))
        for value in page.get('editions', []):
            value = validate(value)
            editions[(value['editionId'], value['revision'])] = value
        next_cursor = page.get('nextCursor')
        if next_cursor and (not isinstance(next_cursor, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', next_cursor)):
            raise ValueError('Invalid pagination cursor')
        if not next_cursor:
            break
        if next_cursor <= cursor:
            raise ValueError('Invalid pagination cursor')
        cursor = next_cursor
    else:
        raise ValueError('Archive synchronization exceeded bounded page count')
    # Validate every response before changing local snapshots.
    directory.mkdir(parents=True, exist_ok=True)
    pending = []
    for (day, revision), value in editions.items():
        path = directory / f'{day}-r{revision}.json'
        if path.exists():
            if json.loads(path.read_text()) != value:
                raise ValueError('Immutable edition revision changed')
            continue
        pending.append((path, value))
    created = []
    try:
        for path, value in pending:
            temporary = path.with_suffix('.tmp')
            temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
            temporary.replace(path)
            created.append(path)
    except OSError:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return len(created)


def load_editions(directory):
    latest = {}
    if not directory.exists():
        return []
    for path in sorted(directory.glob('*.json')):
        value = validate(json.loads(path.read_text()))
        expected = f'{value["editionId"]}-r{value["revision"]}.json'
        if path.name != expected:
            raise ValueError('Edition filename mismatch')
        previous = latest.get(value['editionId'])
        if previous is None or previous['revision'] < value['revision']:
            latest[value['editionId']] = value
    return sorted(latest.values(), key=lambda e: e['editionId'], reverse=True)


def article_url(edition):
    return f'{SITE}/blog/travel-brief-{edition["editionId"]}/'


def article_html(edition, template=None):
    esc = html.escape
    day = edition['editionId']
    title = f'TravelPal.now Travel Brief — {day}'
    blocks = []
    if edition.get('coverageStatus') == 'limited':
        blocks.append('<p class="brief-notice">This edition covers the verified developments available from the sources checked. Coverage is limited.</p>')
    if edition.get('correctionNotice'):
        blocks.append(f'<p class="brief-notice">Updated: {esc(edition["correctionNotice"])}</p>')
    for section, label in SECTIONS.items():
        stories = [s for s in edition['stories'] if s['section'] == section]
        if not stories:
            continue
        blocks.append(f'<section><h2>{esc(label)}</h2>')
        for story in stories:
            blocks.append(f'<article class="brief-story" data-story-id="{esc(story["storyId"], quote=True)}"><h3>{esc(story["title"])}</h3>')
            if not story.get('active', True):
                links = [f'<a href="{esc(source["url"], quote=True)}">{esc(source["publisher"])}</a>' for source in story['sources']]
                blocks.append('<p>This item has been withdrawn. Consult the original source for current information: ' + ' · '.join(links) + '</p></article>')
                continue
            if story.get('image'):
                blocks.append(image_html(story['image']))
            trust = 'Officially confirmed' if story['verification'] == 'officially_confirmed' else 'Reported; not independently confirmed'
            blocks.append(f'<p class="story-meta">{trust} · Source published {esc(story["sourcePublishedAt"][:10])}</p><p>{esc(story["summary"])}</p>')
            if story.get('effectiveAt'):
                blocks.append(f'<p>Effective: {esc(story["effectiveAt"])}</p>')
            terms = story.get('terms') or {}
            if terms.get('rewardPoints') and terms.get('minSpend') is not None and terms.get('spendWindow'):
                points = html.escape(f'{terms["rewardPoints"]:,.0f}')
                spend = html.escape(f'${terms["minSpend"]:,.0f}')
                blocks.append(f'<aside class="brief-offer-visual"><strong>{points}</strong><span>bonus points</span>'
                              f'<p>After {spend} in purchases within the {esc(terms["spendWindow"])}.</p>'
                              f'<p>Annual fee: {esc(str(terms.get("annualFee", "See issuer")))} USD. '
                              f'Launch offer through {esc(terms.get("offerDeadline", "See issuer"))}. '
                              f'{esc(terms.get("eligibilityNote", "Issuer terms apply."))}</p></aside>')
            labels = {'issuer': 'Issuer', 'program': 'Program', 'minSpend': 'Required spend',
                      'creditAmount': 'Credit', 'rewardPoints': 'Points / miles', 'activateBy': 'Enroll by'}
            entries = [f'{label}: {terms[key]}' for key, label in labels.items() if terms.get(key) is not None]
            if entries:
                blocks.append('<p>' + esc(' · '.join(entries)) + '</p>')
            if story.get('expiresAt'):
                blocks.append(f'<p>Offer ends: {esc(story["expiresAt"])[:10]}. Check the source for current availability and full terms.</p>')
            links = [f'<a href="{esc(s["url"], quote=True)}" rel="noopener">{esc(s["publisher"])}</a>' for s in story['sources']]
            blocks.append('<p class="brief-sources">Sources: ' + ' · '.join(links) + '</p></article>')
        blocks.append('</section>')
    template = template or (ROOT / 'templates/travel-brief.html').read_text()
    replacements = {'TITLE': esc(title), 'DATE': day, 'URL': esc(article_url(edition), quote=True),
                    'DIGEST': edition['contentDigest'], 'REVISION': str(edition['revision']),
                    'BODY': '\n'.join(blocks), 'MODIFIED': edition.get('updatedAt', edition['generatedAt']),
                    'HEADLINE': esc(edition.get('title', 'What’s changing in travel')),
                    'DEK': esc(edition.get('dek', 'Selected hotel, airline, credit-card and destination developments, with source links.'))}
    for key, value in replacements.items():
        template = template.replace('{{' + key + '}}', value)
    return template


def render(output, editions):
    visible = [e for e in editions if e['status'] in PUBLISHABLE]
    if not visible:
        return
    links, cards, rss = [], [], []
    for edition in visible:
        day = edition['editionId']
        url = article_url(edition)
        path = output / 'blog' / f'travel-brief-{day}'
        path.mkdir(parents=True, exist_ok=True)
        (path / 'index.html').write_text(article_html(edition))
        links.append(f'<li><a href="/blog/travel-brief-{day}/">Travel brief · {day}</a></li>')
        active = [s for s in edition['stories'] if s.get('active', True)]
        summary = ' · '.join(s['title'] for s in active[:3]) or 'An updated edition with withdrawn information.'
        stamp = date.fromisoformat(day).strftime('%B %-d, %Y')
        cards.append(f'<a class="story-card" href="/blog/travel-brief-{day}/" data-travel-brief><div class="fc-body"><span class="badge-cat travel">Daily travel brief</span><h3>Travel brief · {day}</h3><p>{html.escape(summary)}</p><p class="story-meta">{stamp}</p></div></a>')
        rss.append((edition, summary))
    archive = output / 'travel-briefs'
    archive.mkdir(exist_ok=True)
    (archive / 'index.html').write_text('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Daily travel briefs — TravelPal.now</title><link rel="stylesheet" href="/css/style.css"><main class="wrap"><h1>Daily travel briefs</h1><p>Hotels, airlines, cards, and destination developments.</p><ul>' + ''.join(links) + '</ul><a href="/blog/">All TravelPal.now stories</a></main></html>')
    blog = output / 'blog/index.html'
    if blog.exists():
        source = blog.read_text()
        block = '<section class="wrap"><h2>Daily travel brief</h2><p><a href="/travel-briefs/">Browse the archive</a></p><div class="story-grid">' + ''.join(cards[:7]) + '</div></section>'
        source = source.replace('<main', block + '<main', 1)
        blog.write_text(source)
    feed_path = output / 'feed.xml'
    if feed_path.exists():
        tree = ET.parse(feed_path)
        channel = tree.getroot().find('channel')
        updated_urls = {article_url(edition) for edition in visible}
        for existing in list(channel.findall('item')):
            if existing.findtext('guid') in updated_urls:
                channel.remove(existing)
        for edition, summary in reversed(rss):
            node = ET.Element('item')
            for key, value in {'title': f'TravelPal.now Travel Brief — {edition["editionId"]}',
                               'link': article_url(edition), 'guid': article_url(edition),
                               'pubDate': format_datetime(datetime.fromisoformat(edition['generatedAt'].replace('Z', '+00:00'))),
                               'description': summary}.items():
                ET.SubElement(node, key).text = value
            channel.append(node)
        items = channel.findall('item')
        for item in items:
            channel.remove(item)
        items.sort(key=lambda item: parsedate_to_datetime(item.findtext('pubDate')).timestamp(), reverse=True)
        channel.extend(items)
        built = channel.find('lastBuildDate')
        if built is not None:
            latest_update = max(edition.get('updatedAt', edition['generatedAt']) for edition in visible)
            updated = datetime.fromisoformat(latest_update.replace('Z', '+00:00'))
            if updated.timestamp() > parsedate_to_datetime(built.text).timestamp():
                built.text = format_datetime(updated)
        tree.write(feed_path, encoding='utf-8', xml_declaration=True)
    sitemap_path = output / 'sitemap.xml'
    if sitemap_path.exists():
        tree = ET.parse(sitemap_path)
        namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
        ET.register_namespace('', namespace)
        for edition in visible:
            node = ET.SubElement(tree.getroot(), '{' + namespace + '}url')
            ET.SubElement(node, '{' + namespace + '}loc').text = article_url(edition)
            ET.SubElement(node, '{' + namespace + '}lastmod').text = edition.get('updatedAt', edition['generatedAt'])[:10]
        tree.write(sitemap_path, encoding='utf-8', xml_declaration=True)
    latest = visible[0]
    active = [s for s in latest['stories'] if s.get('active', True)]
    homepage = output / 'index.html'
    if homepage.exists() and active:
        esc = html.escape
        headline = latest.get('title', 'What’s changing in travel')
        description = latest.get('dek', ' · '.join(s['title'] for s in active[:3]))
        photo = next((s.get('image') for s in active if s.get('image')), None)
        visual = image_html(photo) if photo else ''
        feature = (f'<section class="brief-highlight section" data-travel-brief-highlight="{esc(latest["editionId"])}">'
                   f'<div class="wrap brief-highlight-grid"><div><p class="eyebrow">Latest travel brief · {esc(latest["editionId"])}</p>'
                   f'<h2>{esc(headline)}</h2><p>{esc(description)}</p>'
                   f'<a class="btn btn-primary" href="/blog/travel-brief-{esc(latest["editionId"])}/">Read the travel brief →</a>'
                   f'<p><a href="/travel-briefs/">Browse all editions</a></p></div>{visual}</div></section>')
        source = homepage.read_text()
        source = re.sub(r'<!-- TRAVEL_BRIEF_HIGHLIGHT_START -->.*?<!-- TRAVEL_BRIEF_HIGHLIGHT_END -->',
                        lambda _: '<!-- TRAVEL_BRIEF_HIGHLIGHT_START -->' + feature + '<!-- TRAVEL_BRIEF_HIGHLIGHT_END -->', source, flags=re.S)
        homepage.write_text(source)
    manifest = {'schemaVersion': 1, 'editionId': latest['editionId'], 'revision': latest['revision'],
                'url': article_url(latest), 'contentDigest': latest['contentDigest'],
                'status': latest['status'] if active else 'withdrawn',
                'headlines': [s['title'] for s in active[:3]], 'publishedAt': latest['generatedAt']}
    (output / 'daily-travel-brief.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')


def load_live(day, reader=read_url):
    value = json.loads(reader(SITE + '/daily-travel-brief.json'))
    if value.get('schemaVersion') != 1 or value.get('editionId') != day.isoformat() or value.get('status') not in PUBLISHABLE:
        raise ValueError('No current published brief')
    expected = f'{SITE}/blog/travel-brief-{day.isoformat()}/'
    if value.get('url') != expected or not re.fullmatch(r'[a-f0-9]{64}', value.get('contentDigest', '')):
        raise ValueError('Invalid brief manifest')
    article = reader(expected).decode('utf-8')
    marker = f'name="travel-brief-digest" content="{value["contentDigest"]}"'
    if marker not in article or f'data-edition-revision="{value["revision"]}"' not in article:
        raise ValueError('Live article does not match manifest')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--sync', action='store_true')
    parser.add_argument('--verify-live', action='store_true')
    args = parser.parse_args()
    try:
        if args.sync:
            print('New archive snapshots:', sync(ROOT / 'data/travel-briefs'))
        if args.verify_live:
            from zoneinfo import ZoneInfo
            print('Verified live brief:', load_live(datetime.now(ZoneInfo('America/Los_Angeles')).date())['editionId'])
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f'Travel brief unavailable: {error}', file=sys.stderr)
        sys.exit(1)
