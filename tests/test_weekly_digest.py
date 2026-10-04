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
        self.assertEqual(len(chosen),6)
        self.assertEqual({s['section'] for s in chosen}, {'hotels','airlines','cards','destinations'})
        self.assertLessEqual(max(sum(s['section']==t for s in chosen) for t in ['hotels','airlines','cards','destinations']),2)
        self.assertLessEqual(len(short_copy(stories[0]).split()),70)
        offer = {'summary':'Do not use this vague bonus teaser.', 'terms':{
            'rewardPoints':200000,'minSpend':5000,'spendWindow':'first 3 months',
            'annualFee':350,'offerDeadline':'November 18, 2026'}}
        copy = short_copy(offer)
        for required in ['200,000','$5,000','3 months','$350','November 18, 2026','eligibility']:
            self.assertIn(required,copy)
