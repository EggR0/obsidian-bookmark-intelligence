from __future__ import annotations

import io
import sys
import unittest
from unittest.mock import patch

from bookmark_agent.cli import _print_json


class _Cp949Console(io.StringIO):
    encoding = "cp949"

    def write(self, value: str) -> int:
        value.encode(self.encoding)
        return super().write(value)


class CliOutputTests(unittest.TestCase):
    def test_json_output_replaces_unrepresentable_console_characters(self) -> None:
        console = _Cp949Console()
        console.buffer = io.BytesIO()
        with patch.object(sys, "stdout", console):
            _print_json({"title": "👑 한국어"})
        self.assertIn("?", console.buffer.getvalue().decode("cp949"))
