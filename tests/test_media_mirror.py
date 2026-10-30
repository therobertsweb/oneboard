import base64
import io as io_module
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-media-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-media-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "media-test-secret"
os.environ.pop("ONEBOARD_MEDIA_TOKEN", None)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


class MediaMirrorTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-media-workspace-")
        self.site = Path(self.workspace.name) / "media-site"
        self.site.mkdir()
        (self.site / "index.html").write_text("<html><body>Hi</body></html>", encoding="utf-8")

        oneboard.app.config.update(TESTING=True)
        self.owner_id = self._create_user("Owner")
        self.client = oneboard.app.test_client()
        self.login(self.owner_id)
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})

    def tearDown(self):
        self.workspace.cleanup()
        os.environ.pop("ONEBOARD_MEDIA_TOKEN", None)

    def _create_user(self, name):
        type(self).user_sequence += 1
        email = f"media-{name.lower()}-{self.user_sequence}@example.test"
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

    def _upload_library_image(self):
        upload = self.client.post(
            "/api/social/images/upload",
            data={"image": (io_module.BytesIO(PNG_BYTES), "post.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(upload.status_code, 200, upload.get_data(as_text=True))
        return upload.get_json()["image"]["url"]

    def test_public_media_hidden_without_token_env(self):
        response = self.client.post(
            "/api/public-media",
            data={"image": (io_module.BytesIO(PNG_BYTES), "post.png")},
            content_type="multipart/form-data",
            headers={"X-ONEBoard-Media-Token": "anything"},
        )
        self.assertEqual(response.status_code, 404)

    def test_public_media_rejects_wrong_token(self):
        os.environ["ONEBOARD_MEDIA_TOKEN"] = "correct-token"
        response = self.client.post(
            "/api/public-media",
            data={"image": (io_module.BytesIO(PNG_BYTES), "post.png")},
            content_type="multipart/form-data",
            headers={"X-ONEBoard-Media-Token": "wrong-token"},
        )
        self.assertEqual(response.status_code, 401)

    def test_public_media_serves_signed_file(self):
        os.environ["ONEBOARD_MEDIA_TOKEN"] = "correct-token"
        upload = self.client.post(
            "/api/public-media",
            data={"image": (io_module.BytesIO(PNG_BYTES), "post.png")},
            content_type="multipart/form-data",
            headers={"X-ONEBoard-Media-Token": "correct-token"},
        )
        self.assertEqual(upload.status_code, 200, upload.get_data(as_text=True))
        path = upload.get_json()["path"]
        self.assertTrue(path.startswith("/media/"))
        served = self.client.get(path)
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.get_data(), PNG_BYTES)
        tampered = self.client.get(path[:-1] + ("0" if path[-1] != "0" else "1"))
        self.assertEqual(tampered.status_code, 404)

    def test_mirror_requires_media_config(self):
        library_url = self._upload_library_image()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ONEBOARD_MEDIA_URL", None)
            os.environ.pop("ONEBOARD_MEDIA_TOKEN", None)
            response = self.client.post(
                "/api/social/images/mirror", json={"image_url": library_url}
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("media server", response.get_json()["error"].lower())

    def test_mirror_uses_implicit_env_config(self):
        library_url = self._upload_library_image()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"ok": True, "path": "/media/f/sig"}).encode()

        captured = {}

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["token"] = request.headers.get("X-oneboard-media-token")
            return FakeResponse()

        env = {
            "ONEBOARD_MEDIA_URL": "https://media.example.test",
            "ONEBOARD_MEDIA_TOKEN": "env-token",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            with mock.patch.object(
                oneboard.urllib.request, "urlopen", side_effect=fake_urlopen
            ):
                response = self.client.post(
                    "/api/social/images/mirror", json={"image_url": library_url}
                )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(
            response.get_json()["url"], "https://media.example.test/media/f/sig"
        )
        self.assertEqual(captured["token"], "env-token")

    def test_mirror_rejects_foreign_url(self):
        self.client.post(
            "/api/settings/account",
            json={
                "media_server_url": "https://media.example.test",
                "media_server_token": "tok",
            },
        )
        response = self.client.post(
            "/api/social/images/mirror",
            json={"image_url": "https://evil.example/x.png"},
        )
        self.assertEqual(response.status_code, 400)

    def test_mirror_returns_absolute_public_url(self):
        library_url = self._upload_library_image()
        self.client.post(
            "/api/settings/account",
            json={
                "media_server_url": "https://media.example.test/",
                "media_server_token": "tok",
            },
        )
        captured = {}

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"ok": True, "path": "/media/f/sig"}).encode()

        def fake_urlopen(request, timeout=None):
            captured["url"] = request.full_url
            captured["token"] = request.headers.get("X-oneboard-media-token")
            captured["agent"] = request.headers.get("User-agent")
            captured["service_token"] = request.headers.get("X-oneboard-service-token")
            captured["content_type"] = request.headers.get("Content-type")
            captured["body"] = request.data
            return FakeResponse()

        with mock.patch.dict(os.environ, {"ONEBOARD_SERVICE_TOKEN": "svc-1"}):
            with mock.patch.object(
                oneboard.urllib.request, "urlopen", side_effect=fake_urlopen
            ):
                response = self.client.post(
                    "/api/social/images/mirror", json={"image_url": library_url}
                )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(
            response.get_json()["url"], "https://media.example.test/media/f/sig"
        )
        self.assertEqual(
            captured["url"], "https://media.example.test/api/public-media"
        )
        self.assertEqual(captured["token"], "tok")
        self.assertIn("ONEBoard", captured["agent"])
        self.assertEqual(captured["service_token"], "svc-1")
        self.assertIn("multipart/form-data", captured["content_type"])
        self.assertIn(PNG_BYTES, captured["body"])

    def test_settings_exposes_flag_but_never_token(self):
        self.client.post(
            "/api/settings/account",
            json={
                "media_server_url": "https://media.example.test",
                "media_server_token": "super-secret",
            },
        )
        settings = self.client.get("/api/settings")
        account = settings.get_json()["account"]
        self.assertTrue(account["media_server_configured"])
        self.assertEqual(account["media_server_url"], "https://media.example.test")
        self.assertNotIn("super-secret", settings.get_data(as_text=True))
        # Empty token keeps the stored one.
        self.client.post(
            "/api/settings/account",
            json={"media_server_url": "https://media.example.test", "media_server_token": ""},
        )
        settings = self.client.get("/api/settings")
        self.assertTrue(settings.get_json()["account"]["media_server_configured"])


if __name__ == "__main__":
    unittest.main()
