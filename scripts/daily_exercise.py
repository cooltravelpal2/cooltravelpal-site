#!/usr/bin/env python3
"""Read and verify DongDong's current public lesson before teasing it."""
import hashlib
import json
import re
import urllib.request
from datetime import date
from urllib.parse import urlparse

DONGDONG = 'https://dongdong.now'
LESSON_URL = DONGDONG + '/blog/todays-home-exercise/'
TRAVELPAL = 'https://travelpal.now'


def read_url(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'TravelPal-Daily-Exercise/1.0', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError('Daily lesson is not live')
        if urlparse(response.url).netloc != urlparse(url).netloc:
            raise ValueError('Unexpected redirect for daily lesson')
        return response.read(40 * 1024 * 1024 + 1)


def validate(data, day):
    if data.get('schemaVersion') not in {1, 2} or data.get('date') != day.isoformat():
        raise ValueError('Daily exercise is not current for the requested Pacific date')
    if data.get('timezone') != 'America/Los_Angeles' or data.get('url') != LESSON_URL:
        raise ValueError('Unexpected daily lesson URL or timezone')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9]{0,60}', data.get('exerciseId', '')):
        raise ValueError('Invalid exercise identifier')
    if not re.fullmatch(r'[0-9a-f]{64}', data.get('videoSha256', '')):
        raise ValueError('Invalid media hash')
    release = data.get('releaseId', '')
    if not re.fullmatch(re.escape(day.isoformat() + '-' + data['exerciseId']) + r'-r[0-9]+-[0-9a-f]{12}', release):
        raise ValueError('Invalid daily release identifier')
    for key in ['name', 'equipment']:
        for locale in ['en', 'zh-Hans']:
            value = data.get(key, {}).get(locale)
            if not isinstance(value, str) or not 0 < len(value) < 180 or '\n' in value or '\r' in value:
                raise ValueError('Missing or invalid localized daily exercise text')
    if not isinstance(data.get('videoBytes'), int) or not 0 < data['videoBytes'] <= 40 * 1024 * 1024:
        raise ValueError('Invalid media size')
    for field, suffix in [('videoUrl', '.mp4'), ('posterUrl', '.jpg')]:
        value = data.get(field, '')
        if not re.fullmatch(re.escape(DONGDONG + '/daily-media/' + release + '/') + r'[A-Za-z0-9._-]+' + re.escape(suffix), value):
            raise ValueError('Unexpected exercise media URL')
    return data


def load_current(day, verify_travelpal=False):
    data = validate(json.loads(read_url(DONGDONG + '/daily-exercise.json?day=' + day.isoformat())), day)
    marker = f'data-daily-release="{data["releaseId"]}"'.encode()
    if marker not in read_url(LESSON_URL + '?day=' + day.isoformat()):
        raise ValueError('Live lesson does not match daily selection')
    video = read_url(data['videoUrl'])
    if len(video) != data['videoBytes'] or hashlib.sha256(video).hexdigest() != data['videoSha256']:
        raise ValueError('Live exercise video does not match its manifest')
    if verify_travelpal:
        teaser = validate(json.loads(read_url(TRAVELPAL + '/dongdong/daily-exercise.json?day=' + day.isoformat())), day)
        if teaser != data or marker not in read_url(TRAVELPAL + '/dongdong/?day=' + day.isoformat()):
            raise ValueError('TravelPal teaser and DongDong lesson are not synchronized')
    return data


APP_URL = 'https://apps.apple.com/app/id6815518430'


def compose_daily(data):
    prefix = f"Today's home exercise: {data['name']['en']}. Watch the demo with spoken coaching and English/Chinese steps. A different movement each day."
    # X shortens each URL to 23 characters; reserve room for both links/labels.
    available = 280 - 2 * 23 - len("\n\nLesson: \nApp: ")
    if len(prefix) > available:
        prefix = prefix[:available-1].rsplit(' ', 1)[0].rstrip(' ,;:') + '…'
    return prefix + '\n\nLesson: ' + LESSON_URL + '?day=' + data['date'] + '\nApp: ' + APP_URL


def recent_daily_dates(texts):
    pattern = re.escape(LESSON_URL) + r'\?day=(\d{4}-\d{2}-\d{2})'
    return {day for text in texts for day in re.findall(pattern, text)}
