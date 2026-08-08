import json
import tempfile
import unittest
from pathlib import Path

from shadowing_app.transcript import TimedWord, parse_json3, words_to_sentences


class TranscriptTests(unittest.TestCase):
    def test_json3_word_offsets_and_buffer(self):
        payload = {
            "events": [{
                "tStartMs": 2500,
                "dDurationMs": 2200,
                "segs": [
                    {"utf8": "Hello ", "tOffsetMs": 200, "acAsrConf": 255},
                    {"utf8": "world.", "tOffsetMs": 900, "acAsrConf": 200},
                ],
            }]
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sample.json3"
            path.write_text(json.dumps(payload), encoding="utf-8")
            sentences = words_to_sentences(parse_json3(path), playback_buffer=1)
        self.assertEqual(sentences[0]["en"], "Hello world.")
        self.assertAlmostEqual(sentences[0]["speechStart"], 2.7)
        self.assertEqual(sentences[0]["playFrom"], 1)

    def test_sentence_boundaries_and_pause(self):
        words = [
            TimedWord("This", 5.2, 5.5), TimedWord("is", 5.5, 5.7),
            TimedWord("one", 5.7, 6.0), TimedWord("sentence", 6.0, 6.5),
            TimedWord(".", 6.5, 6.6), TimedWord("Next", 7.0, 7.3),
            TimedWord("one", 7.3, 7.6), TimedWord("!", 7.6, 7.7),
        ]
        sentences = words_to_sentences(words)
        self.assertEqual([item["en"] for item in sentences], ["This is one sentence.", "Next one!"])
        self.assertEqual(sentences[0]["playFrom"], 4)

    def test_pause_before_lowercase_word_does_not_split_sentence(self):
        words = [
            TimedWord("This", 1.0, 1.2), TimedWord("is", 1.2, 1.3),
            TimedWord("a", 1.3, 1.4), TimedWord("sentence", 1.4, 1.8),
            TimedWord("with", 1.8, 2.0), TimedWord("a", 2.0, 2.1),
            TimedWord("pause", 2.1, 2.4), TimedWord("inside", 3.5, 3.8),
            TimedWord(".", 3.8, 3.9),
        ]
        sentences = words_to_sentences(words)
        self.assertEqual(len(sentences), 1)
        self.assertEqual(sentences[0]["en"], "This is a sentence with a pause inside.")

    def test_long_punctuated_sentence_is_not_split_at_28_words(self):
        tokens = [TimedWord("This", 0.0, 0.1)]
        tokens.extend(TimedWord("word", index / 10, index / 10 + .08) for index in range(1, 35))
        tokens.append(TimedWord(".", 3.5, 3.58))
        sentences = words_to_sentences(tokens)
        self.assertEqual(len(sentences), 1)
        self.assertTrue(sentences[0]["en"].endswith("."))


if __name__ == "__main__":
    unittest.main()
