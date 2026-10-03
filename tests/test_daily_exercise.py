import json
import sys
import unittest
import urllib.error
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import daily_exercise as daily
import post_to_x as posting


def fixture():
    return {'schemaVersion':1, 'date':'2026-10-03', 'timezone':'America/Los_Angeles',
            'releaseId':'2026-10-03-marchInPlace-r1-'+'a'*12, 'exerciseId':'marchInPlace',
            'name':{'en':'March in Place','zh-Hans':'原地踏步'},
            'equipment':{'en':'No equipment','zh-Hans':'无需器材'},
            'url':daily.LESSON_URL, 'videoSha256':'a'*64, 'videoBytes':100,
            'videoUrl':daily.DONGDONG+'/daily-media/2026-10-03-marchInPlace-r1-'+'a'*12+'/march.mp4',
            'posterUrl':daily.DONGDONG+'/daily-media/2026-10-03-marchInPlace-r1-'+'a'*12+'/poster.jpg'}


class DailyExerciseTests(unittest.TestCase):
    def test_wrong_date_and_external_urls_are_rejected(self):
        data=fixture()
        daily.validate(data, date(2026,10,3))
        with self.assertRaises(ValueError): daily.validate(data,date(2026,10,4))
        for field in ['url','posterUrl','videoUrl']:
            with self.assertRaises(ValueError):
                daily.validate({**data,field:'https://example.com/injected'},date(2026,10,3))

    def test_once_per_day_and_only_morning(self):
        data=fixture();day=date(2026,10,3)
        with patch.object(posting,'load_current',return_value=data) as load:
            text=posting.choose_daily_text(day,'morning',[])
            self.assertIn('March in Place',text)
            self.assertIn(daily.APP_URL,text)
            self.assertLessEqual(posting.weighted_length(text),280)
            self.assertIsNone(posting.choose_daily_text(day,'morning',[text]))
            self.assertIsNone(posting.choose_daily_text(day,'midday',[]))
            self.assertIsNone(posting.choose_daily_text(day,'evening',[]))
            self.assertEqual(load.call_count,1)
        self.assertEqual(daily.recent_daily_dates([text]),{'2026-10-03'})

    def test_stale_or_failed_deploy_falls_back_without_daily_promotion(self):
        with patch.object(posting,'load_current',side_effect=ValueError('stale')):
            self.assertIsNone(posting.choose_daily_text(date(2026,10,3),'morning',[]))
        with patch.object(posting,'load_current',side_effect=urllib.error.URLError('unreachable')):
            self.assertIsNone(posting.choose_daily_text(date(2026,10,3),'morning',[]))

    def test_live_marker_and_media_verification(self):
        import hashlib
        data=fixture();video=b'verified video';sha=hashlib.sha256(video).hexdigest()
        release='2026-10-03-marchInPlace-r1-'+sha[:12]
        data.update(videoSha256=sha,videoBytes=len(video),releaseId=release,
                    videoUrl=daily.DONGDONG+'/daily-media/'+release+'/march.mp4',
                    posterUrl=daily.DONGDONG+'/daily-media/'+release+'/poster.jpg')
        marker=f'data-daily-release="{release}"'.encode()
        with patch.object(daily,'read_url',side_effect=[json.dumps(data).encode(),marker,video,json.dumps(data).encode(),marker]):
            self.assertEqual(daily.load_current(date(2026,10,3),True),data)
        with patch.object(daily,'read_url',side_effect=[json.dumps(data).encode(),b'old release']):
            with self.assertRaises(ValueError):daily.load_current(date(2026,10,3),True)
        with patch.object(daily,'read_url',side_effect=[json.dumps(data).encode(),marker,b'bad video']):
            with self.assertRaises(ValueError):daily.load_current(date(2026,10,3),True)

    def test_teaser_is_outside_blog_and_feed(self):
        import build_site
        data=fixture()
        teaser=build_site.teaser_html(data)
        self.assertIn(data['releaseId'],teaser)
        self.assertIn(data['url'],teaser)
        self.assertNotIn('How to do it',teaser)
        self.assertNotIn('/dongdong/',(ROOT/'blog/index.html').read_text())
        self.assertNotIn('/dongdong/',(ROOT/'feed.xml').read_text())
        self.assertIn('/dongdong/',(ROOT/'apps/index.html').read_text())


if __name__ == '__main__': unittest.main()
