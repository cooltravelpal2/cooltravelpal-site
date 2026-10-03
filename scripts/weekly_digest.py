"""Compile a seven-day EmailOctopus draft from finalized briefs; never sends mail."""
import argparse
import hashlib
import html
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from daily_travel_brief import load_editions, article_url, SECTIONS


def collect(editions, end):
    start = end - timedelta(days=6)
    seen = set()
    stories = []
    included = []
    for edition in sorted(editions, key=lambda e: e['editionId'], reverse=True):
        if not start <= date.fromisoformat(edition['editionId']) <= end:
            continue
        if not edition['status'].startswith('ready'):
            continue
        included.append({'editionId': edition['editionId'], 'revision': edition['revision'], 'url': article_url(edition)})
        for story in edition['stories']:
            if story['storyId'] in seen:
                continue
            seen.add(story['storyId'])
            if not story.get('active', True):
                continue
            stories.append({**story, 'briefUrl': article_url(edition)})
    return {'weekEnding': end.isoformat(), 'windowStart': start.isoformat(), 'editions': included, 'stories': stories}


def render(digest, test=False):
    esc = html.escape
    heading = 'TravelPal.now — Your weekly travel brief'
    period = f"{digest['windowStart']} to {digest['weekEnding']}"
    intro = ('This is a test edition of our new weekly newsletter. ' if test else '') + 'The travel and rewards developments worth your attention, collected from our daily briefs.'
    blocks = [f'<h1>{heading}</h1><p>{period}</p><p>{intro}</p>']
    for key, label in SECTIONS.items():
        stories = [s for s in digest['stories'] if s['section'] == key]
        if not stories:
            continue
        blocks.append(f'<h2><strong>{esc(label)}</strong></h2>')
        for story in stories:
            blocks.append(f'<h3><strong>{esc(story["title"])}</strong></h3>')
            for para in story.get('paragraphs') or [story['summary']]:
                blocks.append(f'<p>{esc(para)}</p>')
            if story.get('keyPoints'):
                blocks.append('<ul>' + ''.join(f'<li>{esc(point)}</li>' for point in story['keyPoints']) + '</ul>')
            if story.get('takeaway'):
                blocks.append(f'<p><strong>Tip:</strong> {esc(story["takeaway"])}</p>')
            links = ' · '.join(f'<a href="{esc(source["url"], quote=True)}">See {esc(source["publisher"])} announcement</a>' for source in story['sources'])
            blocks.append(f'<p style="font-size:14px">{links} · <a href="{esc(story["briefUrl"], quote=True)}">Read the travel brief</a></p>')
    if not digest['stories']:
        blocks.append('<p>No qualifying stories were published during this period. Do not send this empty draft.</p>')
    blocks.append('<hr><p>TravelPal.now · TravelPal LLC<br><a href="https://travelpal.now/">Explore our guides and apps</a></p>')
    body = '\n'.join(blocks)
    digest['contentSha256'] = hashlib.sha256(body.encode()).hexdigest()
    digest['sendEligible'] = bool(digest['stories'])
    return '<!doctype html><html><head><meta charset="utf-8"><title>TravelPal.now weekly digest</title></head><body style="font-family:Arial,sans-serif;color:#25312d;line-height:1.6;max-width:640px;margin:32px auto;padding:20px">' + body + '</body></html>'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--end', default=datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat())
    parser.add_argument('--archive', type=Path, default=Path('data/travel-briefs'))
    parser.add_argument('--output', type=Path, default=Path('weekly-drafts'))
    parser.add_argument('--test', action='store_true')
    args = parser.parse_args()
    digest = collect(load_editions(args.archive), date.fromisoformat(args.end))
    document = render(digest, args.test)
    args.output.mkdir(parents=True, exist_ok=True)
    stem = f"travelpal-weekly-{digest['weekEnding']}" + ('-test' if args.test else '')
    (args.output / f'{stem}.html').write_text(document)
    (args.output / f'{stem}.json').write_text(json.dumps(digest, indent=2, ensure_ascii=False) + '\n')
    print(f"Weekly draft {stem}: {len(digest['editions'])} editions, {len(digest['stories'])} unique stories. No mail sent.")

if __name__ == '__main__':
    main()
