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
