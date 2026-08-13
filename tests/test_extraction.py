from __future__ import annotations

from unittest.mock import patch
import unittest

from bookmark_agent.extraction import _download_caption


class CaptionExtractionTests(unittest.TestCase):
    def test_falls_back_to_available_non_preferred_language(self) -> None:
        class Response:
            text = "WEBVTT\n\n00:00.000 --> 00:01.000\nBonjour le monde"

            def raise_for_status(self) -> None:
                return None

        info = {
            "subtitles": {
                "fr": [{"ext": "vtt", "url": "https://captions.example/fr.vtt"}],
            }
        }
        with patch("bookmark_agent.extraction.requests.get", return_value=Response()):
            language, text = _download_caption(info)

        self.assertEqual(language, "fr")
        self.assertEqual(text, "Bonjour le monde")


if __name__ == "__main__":
    unittest.main()
