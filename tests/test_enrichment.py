import unittest
from unittest.mock import patch

from shadowing_app.enrichment import _candidate_terms, _ensure_candidate_vocab, _request_translation_resilient


class EnrichmentTests(unittest.TestCase):
    def test_frequency_candidates_find_uncommon_words(self):
        try:
            import wordfreq  # noqa: F401
        except ImportError:
            self.skipTest("wordfreq is optional")
        candidates = _candidate_terms("The evidence remains inconclusive.")
        self.assertIn("inconclusive", candidates)
        self.assertNotIn("evidence", candidates)

    @patch("shadowing_app.enrichment._candidate_terms", return_value=["inconclusive"])
    @patch("shadowing_app.enrichment._request_candidate_glosses")
    def test_required_candidate_is_added(self, request_glosses, _candidate_terms_mock):
        request_glosses.return_value = [{
            "sentenceId": 1,
            "term": "inconclusive",
            "meaning": "結論が出ていない",
            "level": "B2",
            "note": "文脈上の意味",
        }]
        sentences = [{"id": 1, "en": "The evidence is inconclusive.", "vocab": [], "needsReview": False}]
        _ensure_candidate_vocab(sentences, "http://localhost", "model")
        self.assertEqual(sentences[0]["vocab"][0]["term"], "inconclusive")
        self.assertEqual(sentences[0]["vocab"][0]["meaning"], "結論が出ていない")

    def test_missing_translation_is_retried_separately(self):
        sentences = [{"id": 1, "en": "One."}, {"id": 2, "en": "Two."}]
        with patch("shadowing_app.enrichment._request_batch") as request:
            request.side_effect = [
                [{"id": 1, "jp": "一。"}],
                [{"id": 2, "jp": "二。"}],
            ]
            generated = _request_translation_resilient("http://localhost", "model", sentences)
        self.assertEqual({item["id"] for item in generated}, {1, 2})
        self.assertEqual(request.call_count, 2)


if __name__ == "__main__":
    unittest.main()
