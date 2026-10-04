import sys
import unittest
from copy import deepcopy
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from weekly_sender import deliver, due, payload, Provider

class FakeProvider:
    def __init__(self):
        self.contact = {'id':'private-test-id','status':'subscribed','fields':{}}
        self.updates, self.queues = [], []
        self.fail_queue = False
        self.quota_state = {'period':'2026-09-16','reserved':2,'otherAllowance':2500}
    def contacts(self): return [deepcopy(self.contact)]
    def get(self, contact_id): return deepcopy(self.contact)
    def update(self, contact_id, fields):
        self.updates.append(fields)
        self.contact['fields'].update(fields)
    def quota(self): return deepcopy(self.quota_state)
    def save_quota(self, state): self.quota_state = deepcopy(state)
    def queue(self, contact_id):
        self.queues.append(contact_id)
        if self.fail_queue: raise TimeoutError('ambiguous outcome')

class SenderTest(unittest.TestCase):
    def digest(self):
        return {'weekEnding':'2026-10-10','stories':[{'storyId':'x','section':'hotels','title':'A supported opening','summary':'A supported development.','briefUrl':'https://travelpal.now/blog/example/'}]}
    def test_retry_does_not_duplicate(self):
        p = FakeProvider()
        self.assertEqual(deliver(p,self.digest(),True)['queued'],1)
        self.assertEqual(deliver(p,self.digest(),True)['skipped'],1)
        self.assertEqual(len(p.queues),1)
    def test_uncertain_outcome_is_never_requeued(self):
        p = FakeProvider();p.fail_queue=True
        with self.assertRaises(TimeoutError): deliver(p,self.digest(),True)
        self.assertTrue(p.contact['fields']['WeeklySendState'].endswith(':pending'))
        with self.assertRaises(ValueError): deliver(p,self.digest(),True)
        self.assertEqual(len(p.queues),1)
        later=self.digest();later['weekEnding']='2026-10-17'
        with self.assertRaises(ValueError):deliver(p,later,True)
    def test_dry_run_and_unsubscribed_are_never_queued(self):
        p=FakeProvider();deliver(p,self.digest())
        self.assertEqual(p.updates,[])
        p.contact['status']='unsubscribed';deliver(p,self.digest(),True)
        self.assertEqual(p.queues,[])
    def test_empty_and_overlong_offer_stop_sending(self):
        p=FakeProvider();d=self.digest();d['stories']=[]
        self.assertTrue(deliver(p,d,True)['empty'])
        d=self.digest();d['stories'][0].update(title='Long title '*100,terms={'rewardPoints':200000,'minSpend':5000})
        with self.assertRaises(ValueError):payload(d)
        self.assertEqual(p.queues,[])
    def test_offer_terms_preserved_and_fields_fit_starter(self):
        d=self.digest();d['stories'][0].update(section='cards',terms={'rewardPoints':200000,'minSpend':5000,'spendWindow':'first 3 months','annualFee':350,'offerDeadline':'November 18, 2026'})
        fields=payload(d)
        self.assertEqual(len(fields),6)
        self.assertTrue(all(len(v)<=600 for v in fields.values()))
        for term in ['200,000','$5,000','3 months','$350','November 18, 2026']:
            self.assertIn(term,fields['WeeklyHighlight3'])
    def test_pagination_uses_cursor_not_next_url(self):
        p=Provider('test');calls=[]
        def call(method,path):
            calls.append(path)
            if len(calls)==1:return {'data':[{'id':'a'}],'paging':{'next':{'starting_after':'cursor/+','url':'https://untrusted.invalid'}}}
            return {'data':[{'id':'b'}],'paging':{}}
        p.call=call
        self.assertEqual(len(p.contacts()),2)
        self.assertIn('starting_after=cursor%2F%2B',calls[1])
        self.assertNotIn('untrusted',calls[1])
    def test_capacity_is_reserved_before_queue_and_not_reused_on_timeout(self):
        p=FakeProvider();p.fail_queue=True
        with self.assertRaises(TimeoutError):deliver(p,self.digest(),True)
        self.assertEqual(p.quota_state['reserved'],3)
        p=FakeProvider();p.quota_state['reserved']=7500
        with self.assertRaises(ValueError):deliver(p,self.digest(),True)
        self.assertEqual(p.queues,[])
    def test_schedule(self):
        self.assertTrue(due(datetime(2026,10,10,9)))
        self.assertFalse(due(datetime(2026,10,10,8)))
        self.assertFalse(due(datetime(2026,10,11,9)))
