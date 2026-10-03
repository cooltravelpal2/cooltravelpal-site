import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from listing_thumbnails import add_thumbnails, illustration_for, IllustrationPicker

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
            self.assertRegex(result, r'src="/images/editorial-museums-v[123]\.webp"')
            self.assertIn('AI-generated editorial illustration', result)
            self.assertEqual(result.count('class="listing-thumb"'), 2)
            self.assertNotIn('src="/images/cardpecker-icon.png"', result)
            add_thumbnails(root)
            self.assertEqual(result, listing.read_text())

    def test_subject_mapping(self):
        self.assertEqual(illustration_for('/blog/westin-hotel-review/', ''), 'hotels')
        self.assertEqual(illustration_for('/blog/credit-card-rewards/', ''), 'rewards')
        self.assertEqual(illustration_for('/blog/airport-arrival/', ''), 'airports')
        self.assertEqual(illustration_for('/blog/a-book-review/', ''), 'books')
        self.assertEqual(illustration_for('/blog/cardpecker-1-6-1/', ''), 'technology')

    def test_neighbor_variation_is_balanced_and_reproducible(self):
        def sequence():
            picker = IllustrationPicker()
            return [picker.choose('hotels', f'/blog/hotel-{n}/') for n in range(12)]
        images = sequence()
        self.assertEqual(images, sequence())
        self.assertEqual(len(set(images)), 3)
        for n, image in enumerate(images):
            self.assertNotIn(image, images[max(0, n-2):n])
        self.assertEqual(sorted(images.count(image) for image in set(images)), [4, 4, 4])
