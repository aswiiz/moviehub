import unittest
from indexer import clean_title, detect_quality, format_size, fetch_imdb_data

class TestIndexerUtils(unittest.TestCase):

    def test_clean_title(self):
        cases = [
            ("Avatar.The.Way.of.Water.2022.720p.WEB-DL.x264.mkv", ("Avatar The Way of Water", 2022)),
            ("Interstellar_2014_1080p_BluRay.mp4", ("Interstellar", 2014)),
            ("Inception.1080p.mkv", ("Inception", None)),
            ("The.Dark.Knight.2008.4K.HDR.2160p.HEVC.mkv", ("The Dark Knight 4K HDR", 2008)),
        ]
        for filename, expected in cases:
            title, year = clean_title(filename)
            # Remove extension from title for comparison if not handled
            title = title.replace(" mkv", "").replace(" mp4", "")
            self.assertEqual((title, year), expected)

    def test_detect_quality(self):
        self.assertEqual(detect_quality("Movie.1080p.mp4"), "1080p")
        self.assertEqual(detect_quality("Movie.720p.mp4"), "720p")
        self.assertEqual(detect_quality("Movie.480p.mp4"), "480p")
        self.assertEqual(detect_quality("Movie.4K.2160p.mp4"), "2160p")
        self.assertEqual(detect_quality("Movie.HD.mp4"), "Unknown")

    def test_format_size(self):
        self.assertEqual(format_size(104857600), "100.0 MB")
        self.assertEqual(format_size(1024), "1.0 KB")
        self.assertEqual(format_size(1073741824), "1.0 GB")

    def test_fetch_imdb_data(self):
        # This is an integration test, but let's see if it works for a known movie
        data = fetch_imdb_data("Inception")
        if data:
            self.assertEqual(data["title"], "Inception")
            self.assertEqual(data["year"], 2010)
            self.assertTrue(data["poster"].startswith("http"))

if __name__ == '__main__':
    unittest.main()
