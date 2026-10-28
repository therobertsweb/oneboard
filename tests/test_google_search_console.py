import os
import sys
import tempfile
import unittest
import urllib.parse
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-gsc-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-gsc-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "gsc-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


PUBLIC_HOST = "seem-stream-teachers-generated.trycloudflare.com"
PUBLIC_CALLBACK = (
    f"https://{PUBLIC_HOST}/integrations/google-search-console/callback"
)
MOCK_CREDS = {
    "GOOGLE_CLIENT_ID": "test-client-id",
    "GOOGLE_CLIENT_SECRET": "test-client-secret",
    "GOOGLE_REDIRECT_URI": "",
}


class GoogleSearchConsoleTests(unittest.TestCase):
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
        email = f"gsc-{type(self).user_sequence}@example.test"
        with oneboard.app.app_context():
            oneboard.execute_db(
                "INSERT INTO users (name, email, password_hash, email_verified)"
                " VALUES (?, ?, ?, 1)",
                (f"GSC {type(self).user_sequence}", email, oneboard.hash_password("password123")),
            )
            row = oneboard.query_db(
                "SELECT id FROM users WHERE email = ?", (email,), one=True
            )
        return row["id"]

    def _insert_connection(self):
        with oneboard.app.app_context():
            oneboard.execute_db(
                """INSERT INTO google_search_console_connections
                   (user_id, access_token, refresh_token, expires_at)
                   VALUES (?, ?, ?, ?)""",
                (self.user_id, "access-token", "refresh-token", 9_999_999_999),
            )

    def _connection_row(self):
        with oneboard.app.app_context():
            return oneboard.query_db(
                "SELECT * FROM google_search_console_connections WHERE user_id = ?",
                (self.user_id,),
                one=True,
            )

    def test_env_redirect_uri_override_wins(self):
        fixed = "https://stable.example.com/integrations/google-search-console/callback"
        with mock.patch.dict(os.environ, {"GOOGLE_REDIRECT_URI": fixed}):
            with oneboard.app.test_request_context("/"):
                self.assertEqual(oneboard.google_redirect_uri(), fixed)

    def test_connect_uses_public_host_behind_proxy(self):
        """Behind cloudflared the Google redirect_uri must be the public https URL."""
        with mock.patch.dict(os.environ, MOCK_CREDS):
            response = self.client.get(
                "/integrations/google-search-console/connect",
                headers={
                    "X-Forwarded-Proto": "https",
                    "X-Forwarded-Host": PUBLIC_HOST,
                },
            )
        self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
        location = response.headers["Location"]
        self.assertIn("accounts.google.com", location)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(location).query)
        self.assertEqual(query["redirect_uri"], [PUBLIC_CALLBACK])

    def test_exchange_uses_same_dynamic_redirect_uri(self):
        """Connect and token exchange must send the identical redirect_uri."""
        captured = {}
        with mock.patch.dict(os.environ, MOCK_CREDS):
            with oneboard.app.test_request_context(
                "/integrations/google-search-console/callback",
                base_url=f"https://{PUBLIC_HOST}",
            ):
                with mock.patch.object(
                    oneboard, "google_token_request", return_value={"ok": True}
                ) as token_request:
                    oneboard.exchange_google_code(self.user_id, "auth-code")
        captured = token_request.call_args[0][0]
        self.assertEqual(captured["redirect_uri"], PUBLIC_CALLBACK)

    def test_web_disconnect_deletes_row_when_revoke_fails(self):
        self._insert_connection()
        with mock.patch.object(
            oneboard,
            "revoke_google_connection",
            side_effect=oneboard.GoogleApiError("invalid_token"),
        ):
            response = self.client.post(
                "/integrations/google-search-console/disconnect",
                follow_redirects=True,
            )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(self._connection_row())
        body = response.get_data(as_text=True)
        self.assertIn("was disconnected", body)
        self.assertIn("could not revoke the token", body)

    def test_api_disconnect_returns_ok_when_revoke_fails(self):
        self._insert_connection()
        with mock.patch.object(
            oneboard,
            "revoke_google_connection",
            side_effect=oneboard.GoogleApiError("invalid_token"),
        ), mock.patch.dict(os.environ, MOCK_CREDS):
            response = self.client.post("/api/google-search-console/disconnect")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["ok"])
        self.assertIn("revoke_warning", payload)
        self.assertIsNone(self._connection_row())

    def test_callback_success_stores_connection_and_dashboard_connects(self):
        """Once Google accepts the redirect URI, callback stores the connection."""
        with mock.patch.dict(os.environ, MOCK_CREDS):
            response = self.client.get("/integrations/google-search-console/connect")
            self.assertEqual(response.status_code, 302, response.get_data(as_text=True))
            with self.client.session_transaction() as session:
                state = session.get("google_oauth_state")
            self.assertTrue(state)
            token = {
                "access_token": "ya29.test-access",
                "refresh_token": "refresh.test",
                "expires_in": 3600,
                "scope": oneboard.SEARCH_CONSOLE_SCOPE,
            }
            with mock.patch.object(
                oneboard, "exchange_google_code", return_value=token
            ) as exchange:
                callback = self.client.get(
                    "/integrations/google-search-console/callback"
                    f"?code=auth-code&state={state}",
                    follow_redirects=False,
                )
            self.assertEqual(callback.status_code, 302, callback.get_data(as_text=True))
            exchange.assert_called_once_with(self.user_id, "auth-code")
            row = self._connection_row()
            self.assertIsNotNone(row)
            self.assertEqual(row["refresh_token"], "refresh.test")
            sites = {
                "siteEntry": [
                    {"siteUrl": "https://example.com/", "permissionLevel": "siteOwner"}
                ]
            }
            with mock.patch.object(
                oneboard, "google_api_request", return_value=sites
            ), mock.patch.object(
                oneboard, "fetch_search_console_analytics", return_value={}
            ):
                dashboard = self.client.get("/api/dashboard")
            self.assertEqual(dashboard.status_code, 200, dashboard.get_data(as_text=True))
            gsc = dashboard.get_json()["gsc"]
            self.assertTrue(gsc["connected"])
            self.assertEqual(gsc["selected_site_url"], "https://example.com/")


if __name__ == "__main__":
    unittest.main()
