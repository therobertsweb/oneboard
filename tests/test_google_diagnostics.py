import io
import os
import sys
import tempfile
import unittest
import urllib.error
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-gscdiag-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-gscdiag-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "gscdiag-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


MOCK_CREDS = {
    "GOOGLE_CLIENT_ID": "test-client-id",
    "GOOGLE_CLIENT_SECRET": "test-client-secret",
    "GOOGLE_REDIRECT_URI": "",
}


class FakeHttpResponse:
    def __init__(self, body):
        self._body = body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class GoogleDiagnosticsTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        oneboard.app.config.update(TESTING=True)
        self.user_id = self._create_user()
        self.client = oneboard.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def _create_user(self):
        type(self).user_sequence += 1
        email = f"gscdiag-{type(self).user_sequence}@example.test"
        with oneboard.app.app_context():
            oneboard.execute_db(
                "INSERT INTO users (name, email, password_hash, email_verified)"
                " VALUES (?, ?, ?, 1)",
                (
                    f"GSCDiag {type(self).user_sequence}",
                    email,
                    oneboard.hash_password("password123"),
                ),
            )
            row = oneboard.query_db(
                "SELECT id FROM users WHERE email = ?", (email,), one=True
            )
        return row["id"]

    def test_suggested_uris_include_localhost_alternate(self):
        with oneboard.app.test_request_context("/", base_url="http://127.0.0.1:5001"):
            uris = oneboard.suggested_google_redirect_uris()
        self.assertEqual(
            uris[0],
            "http://127.0.0.1:5001/integrations/google-search-console/callback",
        )
        self.assertIn(
            "http://localhost:5001/integrations/google-search-console/callback", uris
        )

    def test_diagnose_detects_mismatch(self):
        body = "<html>Error 400: redirect_uri_mismatch</html>"
        with mock.patch.dict(os.environ, MOCK_CREDS):
            with mock.patch.object(
                oneboard.urllib.request, "urlopen", return_value=FakeHttpResponse(body)
            ):
                result = oneboard.diagnose_google_redirect_uri("http://x/callback")
        self.assertFalse(result["google_accepts"])
        self.assertEqual(result["reason"], "mismatch")

    def test_diagnose_detects_accepted_uri(self):
        body = "<html>Sign in - Google Accounts identifier</html>"
        with mock.patch.dict(os.environ, MOCK_CREDS):
            with mock.patch.object(
                oneboard.urllib.request, "urlopen", return_value=FakeHttpResponse(body)
            ) as urlopen:
                result = oneboard.diagnose_google_redirect_uri("http://x/callback")
        self.assertTrue(result["google_accepts"])
        self.assertEqual(result["reason"], "accepted")
        sent_url = urlopen.call_args.args[0].full_url
        self.assertIn("test-client-id", sent_url)
        self.assertIn("redirect_uri=", sent_url)

    def test_diagnose_without_credentials(self):
        with mock.patch.dict(
            os.environ,
            {"GOOGLE_CLIENT_ID": "", "GOOGLE_CLIENT_SECRET": "", "GOOGLE_REDIRECT_URI": ""},
        ):
            result = oneboard.diagnose_google_redirect_uri("http://x/callback")
        self.assertFalse(result["google_accepts"])
        self.assertEqual(result["reason"], "missing_credentials")

    def test_diagnose_network_error(self):
        with mock.patch.dict(os.environ, MOCK_CREDS):
            with mock.patch.object(
                oneboard.urllib.request,
                "urlopen",
                side_effect=urllib.error.URLError("boom"),
            ):
                result = oneboard.diagnose_google_redirect_uri("http://x/callback")
        self.assertFalse(result["google_accepts"])
        self.assertEqual(result["reason"], "network")

    def test_diagnostics_endpoint_checks_suggested_uris(self):
        body = "<html>Sign in identifier</html>"
        suggested = [
            "http://127.0.0.1:5001/integrations/google-search-console/callback",
            "http://localhost:5001/integrations/google-search-console/callback",
        ]
        with mock.patch.dict(os.environ, MOCK_CREDS):
            with mock.patch.object(
                oneboard, "suggested_google_redirect_uris", return_value=suggested
            ), mock.patch.object(
                oneboard.urllib.request, "urlopen", return_value=FakeHttpResponse(body)
            ):
                response = self.client.get("/api/settings/google/diagnostics")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        checks = response.get_json()["checks"]
        self.assertEqual([item["redirect_uri"] for item in checks], suggested)
        self.assertTrue(all(item["google_accepts"] for item in checks))

    def test_settings_page_shows_uris_and_verify(self):
        fixed = "https://stable.example.com/integrations/google-search-console/callback"
        with mock.patch.dict(os.environ, {**MOCK_CREDS, "GOOGLE_REDIRECT_URI": fixed}):
            response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_data(as_text=True)
        self.assertIn(fixed, body)
        self.assertIn("googleVerifyBtn", body)
        self.assertIn("google-copy-btn", body)
        self.assertIn("api/settings/google/diagnostics", body)


if __name__ == "__main__":
    unittest.main()
