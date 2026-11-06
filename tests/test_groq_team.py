import unittest

from core.groq_team import TeamRateLimitError, generate_team_stage


class FakeResponse:
    class Item:
        class Message:
            content = "Kısa görev cevabı"
        message = Message()
        finish_reason = "stop"
    choices = [Item()]


class FakeClient:
    def __init__(self):
        self.messages = []
        self.chat = type("Chat", (), {})()
        self.chat.completions = type("Completions", (), {})()
        self.chat.completions.create = self.create

    def create(self, **kwargs):
        self.messages.append(kwargs)
        return FakeResponse()


class TeamBudgetTests(unittest.TestCase):
    def test_team_call_is_short_with_no_implicit_network_source_search(self):
        client = FakeClient()
        answer = generate_team_stage(
            "Aşağıdaki araştırmayı yap", api_key="unit-test-key",
            client_factory=lambda **kw: client)
        self.assertEqual(answer, "Kısa görev cevabı")
        self.assertEqual(len(client.messages), 1)
        payload = client.messages[0]
        self.assertEqual(len(payload["messages"]), 2)
        self.assertLessEqual(payload["max_tokens"], 700)
        self.assertEqual(payload["messages"][1]["content"],
                         "Aşağıdaki araştırmayı yap")
        self.assertIn("kaynak", payload["messages"][0]["content"].casefold())
        self.assertIn("Yapılmamış deneyleri yapılmış gibi anlatma",
                      payload["messages"][0]["content"])

    def test_transient_503_retries_once_then_succeeds(self):
        class Error503(Exception):
            status_code = 503
        client = FakeClient()
        calls = []
        delays = []
        def flaky(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise Error503("temporary outage")
            return FakeResponse()
        client.chat.completions.create = flaky
        result = generate_team_stage(
            "Görev", api_key="private", client_factory=lambda **kw: client,
            sleep=delays.append)
        self.assertEqual(result, "Kısa görev cevabı")
        self.assertEqual(len(calls), 2)
        self.assertEqual(delays, [1])

    def test_provider_429_is_bounded_and_explicit_without_secrets(self):
        class Error429(Exception):
            status_code = 429
        client = FakeClient()
        calls = []
        delays = []
        def reject(**kwargs):
            calls.append(kwargs)
            raise Error429("secret token and organization id")
        client.chat.completions.create = reject
        with self.assertRaises(TeamRateLimitError) as failure:
            generate_team_stage(
                "Görev", api_key="private",
                client_factory=lambda **kw: client, sleep=delays.append)
        self.assertEqual(len(calls), 3)
        self.assertEqual(delays, [1, 2])
        self.assertNotIn("secret", str(failure.exception))
        self.assertIn("kota", str(failure.exception).casefold())

    def test_non_transient_auth_error_is_not_retried(self):
        class Error401(Exception):
            status_code = 401
        client = FakeClient()
        calls = []
        delays = []
        def reject(**kwargs):
            calls.append(kwargs)
            raise Error401("invalid credentials")
        client.chat.completions.create = reject
        with self.assertRaises(Error401):
            generate_team_stage(
                "Görev", api_key="private",
                client_factory=lambda **kw: client, sleep=delays.append)
        self.assertEqual(len(calls), 1)
        self.assertEqual(delays, [])

    def test_short_response_truncation_is_not_silently_hidden(self):
        class ShortResponse:
            class Choice:
                class Message:
                    content = "Ön taslak"
                message = Message()
                finish_reason = "length"
            choices = [Choice()]
        client = FakeClient()
        client.chat.completions.create = lambda **kw: ShortResponse()
        output = generate_team_stage(
            "Görev", api_key="key", client_factory=lambda **kw: client)
        self.assertIn("token sınırında", output)

    def test_blank_and_oversized_prompt_rejected_before_call(self):
        client = FakeClient()
        for text in (" ", "x" * 15000):
            with self.subTest(size=len(text)):
                with self.assertRaises(ValueError):
                    generate_team_stage(text, api_key="key",
                                        client_factory=lambda **kw: client)
        self.assertEqual(client.messages, [])


if __name__ == "__main__":
    unittest.main()
