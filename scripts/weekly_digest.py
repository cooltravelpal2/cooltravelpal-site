"""Compile a seven-day EmailOctopus draft from finalized briefs; never sends mail."""
import argparse
import hashlib
import html
import json
import shutil
import re
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
            stories.append({**story, 'briefUrl': article_url(edition) + '#story-' + hashlib.sha256(story['storyId'].encode()).hexdigest()[:16]})
    return {'weekEnding': end.isoformat(), 'windowStart': start.isoformat(), 'editions': included, 'stories': stories}


PALETTES = {
    'hotels': ('#215b45', '#edf5ef', 'hotels'),
    'airlines': ('#225c85', '#edf4fa', 'airports'),
    'cards': ('#8a481c', '#fff3e7', 'rewards'),
    'destinations': ('#654683', '#f4eef8', 'museums'),
}


def select_highlights(digest, limit=5):
    """Lead with one important story per topic; never let one topic fill the email."""
    ranked = sorted(digest['stories'], key=lambda s: (-s.get('rank', 0), s['storyId']))
    chosen = []
    for section in SECTIONS:
        first = next((s for s in ranked if s['section'] == section), None)
        if first:
            chosen.append(first)
    # The email has one slot per topic plus a single extra slot, so a week
    # missing a topic gets fewer highlights rather than a second extra.
    extra = next((s for s in ranked if s not in chosen), None)
    if extra and len(chosen) < limit:
        chosen.append(extra)
    return chosen[:limit]


def short_copy(story):
    # Card terms stay together rather than losing the spending hurdle in an excerpt.
    terms = story.get('terms') or {}
    if terms.get('rewardPoints') is not None and terms.get('minSpend') is not None:
        text = f"{terms['rewardPoints']:,} points after ${terms['minSpend']:,} in purchases"
        if terms.get('spendWindow'):
            text += ' within the ' + terms['spendWindow']
        text += '.'
        if terms.get('annualFee') is not None:
            text += f" Annual fee: ${terms['annualFee']:,}."
        if terms.get('offerDeadline'):
            text += ' Offer deadline: ' + terms['offerDeadline'] + '.'
        text += ' Issuer eligibility and terms apply.'
        return text
    import re
    text = re.sub(r'(?:\s+\.)+\s*$', '', story['summary'].strip())
    sentences = re.split(r'(?<=[.!?])\s+', text)
    kept = []
    for sentence in sentences:
        if kept and len((' '.join(kept + [sentence])).split()) > 45:
            break
        kept.append(sentence)
    excerpt = ' '.join(kept)
    if len(excerpt.split()) > 45:
        excerpt = ' '.join(excerpt.split()[:45]).rstrip(',.') + '…'
    return excerpt


def render(digest, test=False):
    esc = html.escape
    selected = select_highlights(digest)
    digest['highlightStoryIds'] = [s['storyId'] for s in selected]
    period = f"{digest['windowStart']} – {digest['weekEnding']}"
    intro = ('Preview edition. ' if test else '') + 'A short selection of the week’s travel and rewards news. Follow the links for the details, key points and practical tips.'
    blocks = [f'<tr><td style="padding:32px 28px;background:#215b45;color:#ffffff"><p style="margin:0 0 12px;font-size:13px;letter-spacing:2px">TRAVELPAL.NOW · THE WEEKLY EDIT</p><h1 style="margin:0;font-size:30px;line-height:1.2">A little inspiration.<br>The news worth knowing.</h1><p style="margin:16px 0 0;color:#dbeadd">{esc(period)}</p></td></tr>',
              f'<tr><td style="padding:24px 28px"><p style="margin:0">{esc(intro)}</p></td></tr>']
    for section, label in SECTIONS.items():
        stories = [s for s in selected if s['section'] == section]
        if not stories:
            continue
        color, background, topic = PALETTES[section]
        variant = 1 + int(hashlib.sha256((digest['weekEnding'] + section).encode()).hexdigest()[:8], 16) % 3
        image = f'https://travelpal.now/images/editorial-{topic}-v{variant}.jpg'
        blocks.append(f'<tr><td style="padding:0 28px 12px"><h2 style="border-left:5px solid {color};padding:8px 14px;background:{background};color:{color};font-size:20px;margin:0">{esc(label)}</h2></td></tr>')
        blocks.append(f'<tr><td style="padding:0 28px 18px"><img src="{image}" alt="Conceptual {esc(label.lower())} illustration" width="260" style="display:block;width:100%;max-width:260px;height:auto;border-radius:12px"><p style="font-size:11px;color:#69726e;margin:6px 0 0">AI-generated editorial illustration; not a photograph of the featured venue.</p></td></tr>')
        for story in stories:
            blocks.append(f'<tr><td style="padding:0 28px 22px"><h3 style="font-size:19px;line-height:1.35;margin:0 0 8px;color:#25312d">{esc(story["title"])}</h3><p style="margin:0 0 10px">{esc(short_copy(story))}</p><a href="{esc(story["briefUrl"], quote=True)}" style="color:{color};font-weight:bold">Read the brief →</a></td></tr>')
    if not selected:
        blocks.append('<tr><td style="padding:24px 28px">No qualifying stories were published during this period. Do not send this empty draft.</td></tr>')
    blocks.append('<tr><td style="padding:24px 28px;background:#f4f0e8"><p style="margin:0 0 12px;font-weight:bold">Keep exploring</p><a href="https://travelpal.now/blog/" style="color:#215b45">All travel briefs and stories →</a><p style="font-size:13px;margin:16px 0 0">TravelPal.now · TravelPal LLC</p></td></tr>')
    body = '\n'.join(blocks)
    digest['contentSha256'] = hashlib.sha256(body.encode()).hexdigest()
    digest['sendEligible'] = bool(selected)
    digest['newsletterFormat'] = 'illustrated-highlights-v1'
    return '<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TravelPal.now weekly edit</title></head><body style="margin:0;padding:24px 12px;background:#f4f0e8;font-family:Arial,sans-serif;color:#25312d;line-height:1.6"><table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:640px;margin:auto;background:#ffffff;border-radius:16px;overflow:hidden">' + body + '</table></body></html>'



ISSUES = Path('data/weekly-newsletter-issues')


def load_issue(path):
    issue = json.loads(path.read_text())
    date.fromisoformat(issue['weekEnding'])
    if not 0 < len(issue['stories']) <= 5:
        raise ValueError('Invalid newsletter issue size')
    seen = set()
    for story in issue['stories']:
        if story['storyId'] in seen or story['section'] not in SECTIONS:
            raise ValueError('Invalid newsletter story')
        seen.add(story['storyId'])
        if not re.fullmatch(r'https://travelpal\.now/blog/travel-brief-\d{4}-\d{2}-\d{2}/#story-[a-f0-9]{16}', story['briefUrl']):
            raise ValueError('Invalid newsletter blog link')
    return issue


def freeze_issue(digest, directory=ISSUES):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (digest['weekEnding'] + '.json')
    if path.exists():
        return load_issue(path)
    issue = {**digest, 'stories': select_highlights(digest)}
    if not issue['stories']:
        return None
    path.write_text(json.dumps(issue, ensure_ascii=False, indent=2) + '\n')
    return load_issue(path)


def story_slots(stories):
    slots = {}
    section_slots = {section: n for n, section in enumerate(SECTIONS, 1)}
    for story in stories:
        slot = section_slots[story['section']]
        if slot in slots:
            slot = 5
        if slot in slots:
            raise ValueError('Too many extra newsletter articles')
        slots[slot] = story
    return slots


def publish_story_links(issue, output):
    # Freeze each issue's numbered links so later revisions never repoint a sent
    # email to a different article. Blog pages themselves retain current corrections.
    for n, story in story_slots(issue['stories']).items():
        path = output / issue['weekEnding'] / ('story-' + str(n)) / 'index.html'
        path.parent.mkdir(parents=True, exist_ok=True)
        target = html.escape(story['briefUrl'], quote=True)
        path.write_text('<!doctype html><html><head><meta charset="utf-8">'
                        + '<meta http-equiv="refresh" content="0;url=' + target + '">'
                        + '<link rel="canonical" href="' + target + '">'
                        + '<meta name="robots" content="noindex"><title>' + html.escape(story['title'])
                        + '</title></head><body><a href="' + target + '">Read full article</a></body></html>')
        topic = PALETTES[story['section']][2]
        variant = 1 + (int(hashlib.sha256(issue['weekEnding'].encode()).hexdigest()[:8], 16) + n) % 3
        image = Path('images') / f'editorial-{topic}-v{variant}.jpg'
        shutil.copy2(image, output / issue['weekEnding'] / f'story-{n}.jpg')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--end', default=datetime.now(ZoneInfo("America/Los_Angeles")).date().isoformat())
    parser.add_argument('--archive', type=Path, default=Path('data/travel-briefs'))
    parser.add_argument('--output', type=Path, default=Path('weekly-drafts'))
    parser.add_argument('--test', action='store_true')
    parser.add_argument('--web-output', type=Path)
    parser.add_argument('--freeze-issue', action='store_true')
    args = parser.parse_args()
    digest = collect(load_editions(args.archive), date.fromisoformat(args.end))
    document = render(digest, args.test)
    if args.freeze_issue:
        freeze_issue(digest)
    args.output.mkdir(parents=True, exist_ok=True)
    stem = f"travelpal-weekly-{digest['weekEnding']}" + ('-test' if args.test else '')
    (args.output / f'{stem}.html').write_text(document)
    (args.output / f'{stem}.json').write_text(json.dumps(digest, indent=2, ensure_ascii=False) + '\n')
    if args.web_output and load_editions(args.archive):
        editions = load_editions(args.archive)
        first = min(date.fromisoformat(e['editionId']) for e in editions)
        end = date.fromisoformat(args.end)
        for n in range((end - first).days + 1):
            day = first + timedelta(days=n)
            if day.weekday() != 5 and day != end:
                continue
            archived = collect(editions, day)
            page_document = render(archived)
            issue_path = ISSUES / (day.isoformat() + '.json')
            if issue_path.exists():
                publish_story_links(load_issue(issue_path), args.web_output)
            if not archived['sendEligible']:
                continue
            page = args.web_output / day.isoformat() / 'index.html'
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text(page_document)
    print(f"Weekly draft {stem}: {len(digest['editions'])} editions, {len(digest['stories'])} unique stories. No mail sent.")

if __name__ == '__main__':
    main()
