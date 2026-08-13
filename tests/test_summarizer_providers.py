from __future__ import annotations

from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from bookmark_agent.config import load_config
from bookmark_agent.summarizer import summarize


class _ProviderHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length) or b"{}")
        self.__class__.requests.append({"path": self.path, "headers": dict(self.headers), "body": body})
        if self.path.startswith("/v1/summarize"):
            payload = {"summary": "hosted result"}
        elif self.path.startswith("/api/generate"):
            payload = {"response": "ollama result"}
        elif self.path.startswith("/models/"):
            payload = {"candidates": [{"content": {"parts": [{"text": "gemini result"}]}}]}
        elif self.path.startswith("/messages"):
            payload = {"content": [{"text": "anthropic result"}]}
        else:
            payload = {"choices": [{"message": {"content": "openai result"}}]}
        encoded = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_args: object) -> None:
        return


class SummarizerProviderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _ProviderHandler.requests = []
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _ProviderHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_all_supported_provider_response_shapes(self) -> None:
        base = load_config(Path("config.toml"))
        with tempfile.TemporaryDirectory() as directory:
            base = replace(base, obsidian=replace(base.obsidian, vault_path=Path(directory)))
            port = self.server.server_address[1]
            cases = [
                ("ollama", "qwen2.5:7b", f"http://127.0.0.1:{port}", "", "ollama result"),
                ("openai", "test-model", f"http://127.0.0.1:{port}", "TEST_OPENAI_KEY", "openai result"),
                ("gemini", "test-model", f"http://127.0.0.1:{port}", "TEST_GEMINI_KEY", "gemini result"),
                ("anthropic", "test-model", f"http://127.0.0.1:{port}", "TEST_ANTHROPIC_KEY", "anthropic result"),
            ]
            for provider, model, base_url, api_key_env, expected in cases:
                if api_key_env:
                    import os

                    os.environ[api_key_env] = "test-key"
                config = replace(base, summarizer=replace(base.summarizer, provider=provider, model=model, base_url=base_url, api_key_env=api_key_env, timeout_seconds=5))
                self.assertEqual(summarize(config, "Title", "https://example.com", "Source"), expected)

            import os

            os.environ["TEST_HOSTED_TOKEN"] = "test-token"
            hosted_config = replace(
                base,
                entitlements=replace(base.entitlements, account_id="acct-hosted"),
                summarizer=replace(base.summarizer, provider="hosted", model="hosted-model", base_url=f"http://127.0.0.1:{port}", api_key_env="TEST_HOSTED_TOKEN", timeout_seconds=5),
            )
            self.assertEqual(summarize(hosted_config, "Title", "https://example.com", "Source"), "hosted result")

            paths = [request["path"] for request in _ProviderHandler.requests[-5:]]
            self.assertTrue(paths[0].startswith("/api/generate"))
            self.assertTrue(paths[1].startswith("/chat/completions"))
            self.assertTrue(paths[2].startswith("/models/test-model:generateContent"))
            self.assertTrue(paths[3].startswith("/messages"))
            self.assertTrue(paths[4].startswith("/v1/summarize"))


if __name__ == "__main__":
    unittest.main()
