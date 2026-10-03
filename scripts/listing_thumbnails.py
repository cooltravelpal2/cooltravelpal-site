"""Reuse article media on listing cards; supply original editorial artwork when absent."""
import html
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

class ArticleMedia(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_main = False
        self.image = None
        self.in_caption = False
        self.caption = []
        self.caption_done = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'main':
            self.in_main = True
        if tag == 'img' and self.in_main and self.image is None:
            src = attrs.get('src', '')
            if not src or any(word in src for word in ('-icon', '-teaser', 'travelpal-logo', 'avatar')):
                return
            if src.startswith('/') or urlsplit(src).scheme == 'https':
                self.image = {'src': src, 'alt': attrs.get('alt', '')}
        if tag == 'figcaption' and self.image and not self.caption_done:
            self.in_caption = True

    def handle_endtag(self, tag):
        if tag == 'main':
            self.in_main = False
        if tag == 'figcaption' and self.in_caption:
            self.in_caption = False
            self.caption_done = True

    def handle_data(self, text):
        if self.in_caption:
            self.caption.append(text)

class AnchorAttrs(HTMLParser):
    def handle_starttag(self, tag, attrs):
        self.attrs = dict(attrs)


def add_thumbnails(output: Path):
    cache = {}
    counts = {'article_images': 0, 'illustrations': 0}
    def decorate(match):
        start, body = match.groups()
        attrs = AnchorAttrs()
        attrs.feed(start)
        classes = attrs.attrs.get('class', '').split()
        path = urlsplit(attrs.attrs.get('href', '')).path
        is_article = path.startswith('/blog/') and path != '/blog/'
        is_destination = 'story-card' in classes and path.startswith('/experiences/') and path != '/experiences/'
        if not {'story-card', 'guide-card'}.intersection(classes) or not (is_article or is_destination):
            return match.group(0)
        if 'listing-thumb' in body:
            return match.group(0)
        if path not in cache:
            media = ArticleMedia()
            article = output / path.lstrip('/') / 'index.html'
            if article.exists():
                media.feed(article.read_text())
            cache[path] = media
        media = cache[path]
        category = ('cards' if re.search(r'badge-cat cards|Cards &amp; Points', body) else
                    'experiences' if re.search(r'badge-cat exp|Experiences', body) else
                    'apps' if re.search(r'badge-cat (product|tech)|Product update', body, re.I) else 'travel')
        fallback = f'/images/listing-{category}.svg'
        credit = ''
        contain = ''
        if media.image:
            src, alt = media.image['src'], media.image['alt']
            counts['article_images'] += 1
            if 'wikimedia.org' in (urlsplit(src).hostname or ''):
                # Keep the existing license/credit and show the whole image.
                credit = '<span class="listing-credit">' + html.escape(' '.join(media.caption)) + '</span>'
                contain = ' listing-thumb-contain'
        else:
            src, alt = fallback, ''
            counts['illustrations'] += 1
        visual = (f'<span class="listing-visual{contain}"><img class="listing-thumb" src="{html.escape(src, quote=True)}" '
                  f'alt="{html.escape(alt, quote=True)}" data-fallback="{fallback}" width="640" height="400" loading="lazy" decoding="async">{credit}</span>')
        return start + visual + body + '</a>'

    for page in output.rglob('*.html'):
        source = page.read_text()
        result = re.sub(r'(<a\b[^>]*>)(.*?)</a>', decorate, source, flags=re.S)
        if result != source:
            page.write_text(result)
    print('Listing thumbnails:', counts)
