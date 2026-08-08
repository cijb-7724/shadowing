import tempfile
import unittest
from pathlib import Path

from shadowing_app.storage import Store, read_json


class StorageTests(unittest.TestCase):
    def test_publish_updates_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = Store(root, root / ".work")
            lesson = {"id": "abc123xyz", "title": "Example", "sentences": [{"en": "Hello."}]}
            store.save_draft(lesson)
            store.publish(lesson)
            manifest = read_json(root / "data" / "videos.json")
            self.assertEqual(manifest[0]["sentenceCount"], 1)
            self.assertTrue((root / "data" / "videos" / "abc123xyz.json").exists())

    def test_publish_marks_matching_review_job_as_published(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = Store(root, root / ".work")
            store.save_job({
                "id": "job1", "videoId": "abc", "status": "review",
                "createdAt": "2026-01-01T00:00:00+00:00",
            })
            store.publish({"id": "abc", "title": "Test", "sentences": []})
            job = store.job("job1")
            self.assertEqual(job["status"], "published")
            self.assertEqual(job["progress"], 100)


if __name__ == "__main__":
    unittest.main()
