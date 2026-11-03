import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from audit_published import audit_text
import post_to_x
from weekly_sender import deliver, payload
from test_weekly_sender import FakeProvider

PLANTED = {
    'test data': 'Confirmation PHS-DEMO-001 for Joe Doe',
    'developer text': 'Saved to /Users/someone/Desktop/brief.json',
    'email address': 'Questions to someone@gmail.com',
    'phone number': 'Call (206) 555-0142 today',
    'debug value': 'Opens at undefined on [object Object]',
}


class ReleaseAuditTest(unittest.TestCase):
    def test_clean_text_passes_and_each_problem_kind_is_flagged(self):
        self.assertEqual(audit_text('x', 'Park Hyatt Shanghai reopens its pool. Write to support@travelpal.now.'), [])
        for kind, text in PLANTED.items():
            problems = audit_text('x', text)
            self.assertTrue(any(kind in p for p in problems), (kind, problems))

    def test_reviewed_exception_is_keyed_by_file(self):
        line = 'The statewide road-information phone line is 1-800-427-7623.'
        self.assertEqual(audit_text('blog/california-highway-1-big-sur-road-trip/index.html', line), [])
        self.assertTrue(audit_text('blog/other/index.html', line))

    def test_site_is_released_only_after_a_clean_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            site, release = Path(tmp, 'dist'), Path(tmp, '_site')
            site.mkdir()
            (site / 'index.html').write_text('<p>Clean page</p>')
            run = lambda: subprocess.run([sys.executable, str(ROOT / 'scripts/audit_published.py'), str(site), '--release-to', str(release)], capture_output=True, text=True)
            self.assertEqual(run().returncode, 0)
            self.assertTrue((release / 'index.html').exists())
            (site / 'index.html').write_text('<p>' + PLANTED['test data'] + '</p>')
            self.assertEqual(run().returncode, 1)

    def test_deploy_uploads_only_the_audited_copy(self):
        workflow = (ROOT / '.github/workflows/publish-site.yml').read_text()
        self.assertIn('scripts/audit_published.py dist --release-to _site', workflow)
        self.assertIn('upload-pages-artifact@v3\n        with:\n          path: _site\n', workflow)
        self.assertLess(workflow.index('--release-to _site'), workflow.index('upload-pages-artifact'))

    def test_newsletter_with_test_data_is_never_sent(self):
        digest = {'weekEnding': '2026-10-10', 'stories': [{'storyId': 'x', 'section': 'hotels', 'title': PLANTED['test data'], 'summary': 'A supported development.', 'briefUrl': 'https://travelpal.now/blog/x/'}]}
        provider = FakeProvider()
        with self.assertRaises(ValueError):
            deliver(provider, digest, send=True)
        self.assertEqual((provider.updates, provider.queues), ([], []))

    def test_x_post_with_test_data_is_refused_even_in_a_dry_run(self):
        args = ['post_to_x.py', '--slot', 'midday', '--date', '2026-10-10', '--dry-run']
        with mock.patch.object(sys, 'argv', args), mock.patch.dict('os.environ', {'BUFFER_API_KEY': ''}), \
                mock.patch.object(post_to_x, 'choose_brief_text', return_value='Brief: ' + PLANTED['developer text']):
            with self.assertRaises(ValueError):
                post_to_x.main()


if __name__ == '__main__':
    unittest.main()
