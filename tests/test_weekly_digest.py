import sys
import unittest
from datetime import date
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from weekly_digest import collect, render

class WeeklyDigestTest(unittest.TestCase):
    def test_window_latest_copy_inactive_and_duplicate_exclusion(self):
        def edition(day, title, active=True):
            return {'editionId':day,'revision':1,'status':'ready','stories':[{'storyId':'same','title':title,'active':active}]}
        data = collect([edition('2026-10-03','too old'),edition('2026-10-04','old copy'),edition('2026-10-09','latest copy'),edition('2026-10-11','future')],date(2026,10,10))
        self.assertEqual([s['title'] for s in data['stories']],['latest copy'])
        self.assertEqual(len(data['editions']),2)
        self.assertEqual(collect([edition('2026-10-10','inactive',False),edition('2026-10-09','withdrawn older copy')],date(2026,10,10))['stories'],[])

    def test_empty_draft_is_not_send_eligible(self):
        data = collect([],date(2026,10,10))
        self.assertIn('Do not send',render(data))
        self.assertFalse(data['sendEligible'])

    def test_highlights_are_bounded_and_topic_balanced(self):
        from weekly_digest import select_highlights, short_copy
        stories = [{'storyId':f'{section}-{n}', 'section':section, 'rank':100-n,
                    'title':'A supported development', 'summary':'A supported fact. '*80}
                   for section in ['hotels','airlines','cards','destinations'] for n in range(10)]
        chosen = select_highlights({'stories':stories})
        self.assertEqual(len(chosen),5)
        self.assertEqual({s['section'] for s in chosen}, {'hotels','airlines','cards','destinations'})
        self.assertLessEqual(max(sum(s['section']==t for s in chosen) for t in ['hotels','airlines','cards','destinations']),2)
        missing_topic = select_highlights({'stories':[s for s in stories if s['section']!='destinations']})
        self.assertEqual(len(missing_topic),4)
        from weekly_digest import story_slots
        self.assertEqual(sorted(story_slots(missing_topic)),[1,2,3,5])
        self.assertLessEqual(len(short_copy(stories[0]).split()),70)
        offer = {'summary':'Do not use this vague bonus teaser.', 'terms':{
            'rewardPoints':200000,'minSpend':5000,'spendWindow':'first 3 months',
            'annualFee':350,'offerDeadline':'November 18, 2026'}}
        copy = short_copy(offer)
        for required in ['200,000','$5,000','3 months','$350','November 18, 2026','eligibility']:
            self.assertIn(required,copy)


class TemplateSlotsTest(unittest.TestCase):
    def test_every_topic_mix_fits_the_email_template(self):
        import html, itertools, re
        from weekly_digest import select_highlights, story_slots, thin_issue_warning
        from daily_travel_brief import SECTIONS
        template = (Path(__file__).resolve().parents[1] / 'templates/emailoctopus-weekly.html').read_text()
        blocks = dict(re.findall(r'\{% if WeeklyHighlight(\d) is not empty %\}(.*?)\{% endif %\}', template, re.S))
        self.assertEqual(sorted(blocks), [str(n) for n in range(1, len(SECTIONS) + 2)])
        for n, label in enumerate(SECTIONS.values(), 1):
            self.assertIn(html.escape(label), blocks[str(n)])
        for size in range(1, len(SECTIONS) + 1):
            for topics in itertools.combinations(SECTIONS, size):
                stories = [{'storyId': f'{t}-{n}', 'section': t, 'rank': 100 - n} for t in topics for n in range(5)]
                slots = story_slots(select_highlights({'stories': stories}))
                self.assertTrue(set(slots) <= {int(n) for n in blocks})
                self.assertEqual(thin_issue_warning(list(slots.values())) is None, size == len(SECTIONS))


class StableNewsletterLinksTest(unittest.TestCase):
    def test_frozen_article_order_survives_later_ranking_changes(self):
        import tempfile
        from weekly_digest import freeze_issue, publish_story_links
        import hashlib
        story={'storyId':'original','section':'hotels','rank':80,'title':'Original opening','summary':'A verified fact.',
               'briefUrl':'https://travelpal.now/blog/travel-brief-2026-10-03/#story-'+hashlib.sha256(b'original').hexdigest()[:16]}
        digest={'weekEnding':'2026-10-03','windowStart':'2026-09-27','stories':[story]}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            first=freeze_issue(digest,root/'issues')
            later=freeze_issue({**digest,'stories':[{**story,'storyId':'replacement','title':'Changed ranking'}]},root/'issues')
            self.assertEqual(first,later)
            publish_story_links(later,root/'weekly')
            route=(root/'weekly/2026-10-03/story-1/index.html').read_text()
            self.assertIn(story['briefUrl'],route)
            self.assertIn('http-equiv="refresh"',route)
            self.assertTrue((root/'weekly/2026-10-03/story-1.jpg').exists())
