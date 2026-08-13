from __future__ import annotations

import io
import sys
import unittest
from unittest.mock import patch

from bookmark_agent.activity import _print_console


class _Cp949Console:
    encoding = "cp949"

    def __init__(self) -> None:
        self.buffer = io.BytesIO()

    def write(self, value: str) -> int:
        raise UnicodeEncodeError("cp949", value, 0, len(value), "test")

    def flush(self) -> None:
        return None


class ActivityTests(unittest.TestCase):
    def test_unrepresentable_console_text_is_replaced_without_raising(self) -> None:
        console = _Cp949Console()
        with patch.object(sys, "stdout", console):
            _print_console(
                {
                    "timestamp": "2026-01-01T00:00:00Z",
                    "event_type": "processing_failed",
                    "title": "한국어 제목 – 테스트",
                    "message": "실패",
                }
            )
        output = console.buffer.getvalue().decode("cp949")
        self.assertIn("processing_failed", output)
        self.assertIn("?", output)


if __name__ == "__main__":
    unittest.main()
