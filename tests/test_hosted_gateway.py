from __future__ import annotations

from unittest.mock import Mock, patch
import unittest

from server.hosted_gateway import GatewayRequestError, GatewaySettings, summarize_hosted


class HostedGatewayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = GatewaySettings(
            billing_endpoint="https://billing.example.test",
            upstream_base_url="https://ai.example.test/v1",
            upstream_api_key="upstream-secret",
            default_model="gateway-model",
        )

    @staticmethod
    def response(payload: dict, status: int = 200) -> Mock:
        response = Mock()
        response.ok = status < 400
        response.status_code = status
        response.json.return_value = payload
        return response

    def test_success_checks_entitlement_calls_upstream_then_consumes_credit(self) -> None:
        payload = {"account_id": "acct-1", "request_id": "req-1", "prompt": "Summarize", "source_text": "Source"}
        with patch("server.hosted_gateway.requests.get", return_value=self.response({"plan": "Solo", "hosted_credits": 3})) as get, patch(
            "server.hosted_gateway.requests.post",
            side_effect=[
                self.response({"choices": [{"message": {"content": "A compact summary"}}]}),
                self.response({"ok": True, "consumed": 1, "remaining": 2}),
            ],
        ) as post:
            result = summarize_hosted(payload, "Bearer account-token", self.settings)

        self.assertEqual(result["summary"], "A compact summary")
        get.assert_called_once()
        self.assertEqual(post.call_args_list[0].args[0], "https://ai.example.test/v1/chat/completions")
        self.assertEqual(post.call_args_list[1].args[0], "https://billing.example.test/v1/usage/consume")
        self.assertEqual(post.call_args_list[1].kwargs["headers"]["Idempotency-Key"], "req-1")

    def test_free_account_is_rejected_before_upstream_call(self) -> None:
        payload = {"account_id": "acct-free", "request_id": "req-2", "prompt": "Summarize", "source_text": "Source"}
        with patch("server.hosted_gateway.requests.get", return_value=self.response({"plan": "Free", "hosted_credits": 0})), patch(
            "server.hosted_gateway.requests.post"
        ) as post:
            with self.assertRaises(GatewayRequestError) as context:
                summarize_hosted(payload, "Bearer account-token", self.settings)
        self.assertEqual(context.exception.status, 402)
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
