import io
import json
import unittest
from urllib.error import HTTPError
from unittest.mock import Mock

from scripts.gcp.health import NoRedirect, check_health


class HealthTests(unittest.TestCase):
    url = "https://engine-example.run.app"
    token = "sensitive-test-token"

    def opener(self, payload, status=200):
        response = io.BytesIO(json.dumps(payload).encode())
        response.status = status
        return Mock(open=Mock(return_value=response))

    def test_checks_exact_service_and_release_with_id_token(self):
        opener = self.opener({"status": "ok", "service": "engine", "version": "abc123"})
        check_health(self.url, "engine", "abc123", self.token, opener=opener)
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, self.url + "/health")
        self.assertEqual(request.get_header("X-serverless-authorization"), "Bearer " + self.token)
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 30)

    def test_rejects_wrong_service_version_status_and_non_json(self):
        for payload in ({"status": "ok", "service": "twin", "version": "abc123"},
                        {"status": "ok", "service": "engine", "version": "dev"},
                        {"status": "error", "service": "engine", "version": "abc123"}, []):
            with self.assertRaises(RuntimeError):
                check_health(self.url, "engine", "abc123", self.token,
                             opener=self.opener(payload))
        with self.assertRaises(RuntimeError):
            check_health(self.url, "engine", "abc123", self.token,
                         opener=self.opener({}, status=503))

    def test_rejects_missing_token_and_foreign_or_insecure_destination(self):
        for url, token in ((self.url, ""), ("http://engine-example.run.app", self.token),
                           ("https://example.com", self.token),
                           ("https://x.evilrun.app", self.token),
                           (self.url + "/unexpected", self.token)):
            with self.assertRaises(ValueError):
                check_health(url, "engine", "abc123", token, opener=Mock())

    def test_redirects_are_not_followed_and_http_errors_never_reveal_token(self):
        handler = NoRedirect()
        self.assertIsNone(handler.redirect_request(None, None, 302, "Found", {}, "https://evil.test"))
        opener = Mock()
        opener.open.side_effect = HTTPError(self.url, 403, self.token, {}, None)
        with self.assertRaises(RuntimeError) as failure:
            check_health(self.url, "engine", "abc123", self.token, opener=opener)
        self.assertIn("403", str(failure.exception))
        self.assertNotIn(self.token, str(failure.exception))


if __name__ == "__main__":
    unittest.main()
