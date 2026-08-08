import unittest

from shadowing_app.youtube import extract_video_id


class YouTubeUrlTests(unittest.TestCase):
    def test_supported_urls(self):
        expected = "_zfN9wnPvU0"
        self.assertEqual(extract_video_id(f"https://www.youtube.com/watch?v={expected}"), expected)
        self.assertEqual(extract_video_id(f"https://youtu.be/{expected}?t=2"), expected)
        self.assertEqual(extract_video_id(f"https://www.youtube.com/shorts/{expected}"), expected)

    def test_rejects_non_youtube_url(self):
        with self.assertRaises(ValueError):
            extract_video_id("https://example.com/watch?v=_zfN9wnPvU0")


if __name__ == "__main__":
    unittest.main()
