import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from listing_thumbnails import add_thumbnails

class ListingMediaTest(unittest.TestCase):
    def test_photo_credit_fallback_and_repeat_build(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            article = root / 'blog/photo'
            article.mkdir(parents=True)
            (article / 'index.html').write_text('<main><img src="/images/cardpecker-icon.png"><figure><img src="https://thumb.wikimedia.org/photo.jpg" alt="Mountain view"><figcaption>Photo: Example. CC BY-SA 4.0</figcaption></figure></main>')
            listing = root / 'index.html'
            listing.write_text('<a class="story-card" href="/blog/photo/"><h3>Photo story</h3></a><a class="story-card" href="/blog/no-photo/"><span class="badge-cat exp">Museum</span></a><a class="guide-card" href="/apps/">Apps</a>')
            add_thumbnails(root)
            result = listing.read_text()
            self.assertIn('alt="Mountain view"', result)
            self.assertIn('Photo: Example. CC BY-SA 4.0', result)
            self.assertIn('listing-thumb-contain', result)
            self.assertIn('src="/images/listing-experiences.svg"', result)
            self.assertEqual(result.count('class="listing-thumb"'), 2)
            self.assertNotIn('src="/images/cardpecker-icon.png"', result)
            add_thumbnails(root)
            self.assertEqual(result, listing.read_text())
