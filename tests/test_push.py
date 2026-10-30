import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-push-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-push-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "push-test-secret"
os.environ.pop("FIREBASE_SERVICE_ACCOUNT", None)
os.environ.pop("FIREBASE_PROJECT_ID", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


class PushTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-push-workspace-")
        self.site = Path(self.workspace.name) / "push-site"
        self.site.mkdir()
        (self.site / "index.html").write_text("<html><body>Hi</body></html>", encoding="utf-8")

        oneboard.app.config.update(TESTING=True)
        self.owner_id = self._create_user("Owner")
        self.client = oneboard.app.test_client()
        self.login(self.owner_id)
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        with oneboard.app.app_context():
            row = oneboard.query_db(
                "SELECT id FROM website_workspaces WHERE user_id = ? ORDER BY id DESC",
                (self.owner_id,),
                one=True,
            )
        self.workspace_id = row["id"]

    def tearDown(self):
        self.workspace.cleanup()

    def _create_user(self, name):
        type(self).user_sequence += 1
        email = f"push-{name.lower()}-{self.user_sequence}@example.test"
        with oneboard.app.app_context():
            oneboard.execute_db(
                "INSERT INTO users (name, email, password_hash, email_verified) VALUES (?, ?, ?, 1)",
                (f"{name} {self.user_sequence}", email, oneboard.hash_password("password123")),
            )
            row = oneboard.query_db("SELECT id FROM users WHERE email = ?", (email,), one=True)
        return row["id"]

    def login(self, user_id):
        with oneboard.app.app_context():
            email = oneboard.query_db(
                "SELECT email FROM users WHERE id = ?", (user_id,), one=True
            )["email"]
        self.client.post(
            "/api/auth/login", json={"email": email, "password": "password123"}
        )

    def test_register_device_stores_token(self):
        response = self.client.post(
            "/api/notifications/device",
            json={"token": "fcm-token-1", "platform": "macos"},
        )
        self.assertEqual(response.status_code, 200)
        with oneboard.app.app_context():
            self.assertEqual(
                oneboard.user_push_tokens(self.owner_id), ["fcm-token-1"]
            )
        # Same token twice stays a single row.
        response = self.client.post(
            "/api/notifications/device",
            json={"token": "fcm-token-1", "platform": "macos"},
        )
        self.assertEqual(response.status_code, 200)
        with oneboard.app.app_context():
            self.assertEqual(
                oneboard.user_push_tokens(self.owner_id), ["fcm-token-1"]
            )

    def test_register_device_rejects_empty_token(self):
        response = self.client.post(
            "/api/notifications/device", json={"token": "  "}
        )
        self.assertEqual(response.status_code, 400)

    def test_send_without_config_sends_nothing(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("FIREBASE_SERVICE_ACCOUNT", None)
            os.environ.pop("FIREBASE_PROJECT_ID", None)
            with mock.patch.object(
                oneboard.urllib.request, "urlopen"
            ) as urlopen_mock:
                self.assertEqual(
                    oneboard.send_push_message(["t1"], "Hi", "Body"), 0
                )
                urlopen_mock.assert_not_called()

    def test_send_posts_fcm_payload(self):
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"name": "projects/p/messages/m"}'

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["auth"] = request.headers.get("Authorization")
            captured["payload"] = json.loads(request.data.decode())
            return FakeResponse()

        env = {
            "FIREBASE_PROJECT_ID": "demo-project",
            "FIREBASE_SERVICE_ACCOUNT": json.dumps({"client_email": "x@y.iam.gserviceaccount.com"}),
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch.object(
                oneboard, "_fcm_access_token", return_value="access-123"
            ):
                with mock.patch.object(
                    oneboard.urllib.request, "urlopen", side_effect=fake_urlopen
                ):
                    sent = oneboard.send_push_message(
                        ["t1", ""],
                        "Title here",
                        "Detail here",
                        data={"section": "requests", "kind": "request"},
                    )
        self.assertEqual(sent, 1)
        self.assertEqual(
            captured["url"],
            "https://fcm.googleapis.com/v1/projects/demo-project/messages:send",
        )
        self.assertEqual(captured["auth"], "Bearer access-123")
        message = captured["payload"]["message"]
        self.assertEqual(message["token"], "t1")
        self.assertEqual(message["notification"]["title"], "Title here")
        self.assertEqual(message["data"], {"section": "requests", "kind": "request"})
        self.assertEqual(
            message["apns"]["payload"]["aps"], {"sound": "default"}
        )

    def test_notify_sends_push_to_registered_watchers(self):
        self.client.post(
            "/api/notifications/device",
            json={"token": "fcm-token-9", "platform": "macos"},
        )
        with oneboard.app.app_context():
            with mock.patch.object(
                oneboard, "send_push_message", return_value=1
            ) as send_mock:
                sent = oneboard.notify_workspace(
                    self.workspace_id, "request", "New request", "Please review"
                )
        self.assertEqual(sent, 1)
        send_mock.assert_called_once()
        args, kwargs = send_mock.call_args
        self.assertEqual(args[0], ["fcm-token-9"])
        self.assertEqual(args[1], "New request")
        self.assertEqual(
            kwargs["data"], {"section": "requests", "kind": "request"}
        )


if __name__ == "__main__":
    unittest.main()
