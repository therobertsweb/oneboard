import os
import tempfile
import unittest
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-buffer-tests-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["SECRET_KEY"] = "oneboard-buffer-test-secret"

import app as oneboard


ORGS_PAYLOAD = {"data": {"account": {"organizations": [{"id": "org_1", "name": "Acme"}]}}}
CHANNELS_PAYLOAD = {
    "data": {
        "channels": [
            {"id": "ch_1", "name": "Acme X", "service": "twitter"},
            {"id": "ch_2", "name": "Acme IG", "service": "instagram"},
        ]
    }
}
POST_PAYLOAD = {
    "data": {
        "createPost": {
            "post": {"id": "post_9", "text": "Hello", "dueAt": "2026-01-01T10:00:00Z"}
        }
    }
}


def buffer_router(url, payload, headers=None, timeout=30):
    query = (payload or {}).get("query") or ""
    if "GetOrganizations" in query:
        return ORGS_PAYLOAD
    if "GetChannels" in query:
        return CHANNELS_PAYLOAD
    if "CreateBufferPost" in query:
        return POST_PAYLOAD
    raise AssertionError(f"unexpected Buffer query: {query[:80]}")


class BufferTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()

    def setUp(self):
        type(self).user_sequence += 1
        email = f"buffer-{type(self).user_sequence}@example.test"
        oneboard.app.config.update(TESTING=True)
        with oneboard.app.app_context():
            oneboard.execute_db(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                ("Buffer Test", email, oneboard.hash_password("password123")),
            )
            self.user_id = oneboard.query_db(
                "SELECT id FROM users WHERE email = ?",
                (email,),
                one=True,
            )["id"]
        self.client = oneboard.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def set_buffer_key(self, key="test-buffer-key"):
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET buffer_api_key = ? WHERE id = ?",
                (key, self.user_id),
            )

    def test_channels_endpoint_lists_connected_channels(self):
        self.set_buffer_key()
        with mock.patch.object(oneboard, "perform_json_request", side_effect=buffer_router):
            response = self.client.get("/api/social/buffer/channels")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        channels = response.get_json()["channels"]
        self.assertEqual([channel["id"] for channel in channels], ["ch_1", "ch_2"])
        self.assertEqual(channels[0]["organization_id"], "org_1")

    def test_channels_endpoint_requires_an_api_key(self):
        response = self.client.get("/api/social/buffer/channels")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Buffer API key", response.get_json()["error"])

    def test_create_post_queues_text_and_records_history(self):
        self.set_buffer_key()
        with mock.patch.object(oneboard, "perform_json_request", side_effect=buffer_router):
            response = self.client.post(
                "/api/social/buffer/posts",
                json={"channel_id": "ch_1", "text": "Hello social"},
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_json()
        self.assertEqual(body["status"], "queued")
        self.assertEqual(body["post"]["id"], "post_9")
        with oneboard.app.app_context():
            posts = oneboard.list_social_posts(self.user_id)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0]["channel_name"], "Acme X")
        self.assertEqual(posts[0]["status"], "queued")

        history = self.client.get("/api/social/buffer/posts")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.get_json()["posts"]), 1)

    def test_create_post_supports_drafts(self):
        self.set_buffer_key()
        seen_queries = []

        def capture(url, payload, headers=None, timeout=30):
            seen_queries.append((payload or {}).get("query") or "")
            return buffer_router(url, payload, headers, timeout)

        with mock.patch.object(oneboard, "perform_json_request", side_effect=capture):
            response = self.client.post(
                "/api/social/buffer/posts",
                json={"channel_id": "ch_2", "text": "Draft me", "draft": True},
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["status"], "draft")
        mutations = [query for query in seen_queries if "CreateBufferPost" in query]
        self.assertEqual(len(mutations), 1)
        self.assertIn("saveToDraft: true", mutations[0])

    def test_create_post_generates_text_from_a_prompt(self):
        self.set_buffer_key()
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.user_id),
            )
        with mock.patch.object(
            oneboard, "perform_json_request", side_effect=buffer_router
        ), mock.patch.object(
            oneboard,
            "run_ai_provider_prompt",
            return_value=("Generated launch post", {"total_tokens": 12}, "muse-text-1.0"),
        ), mock.patch.object(
            oneboard,
            "get_muse_models",
            return_value=["muse-text-1.0", "muse-image-1.0"],
        ):
            response = self.client.post(
                "/api/social/buffer/posts",
                json={"channel_id": "ch_1", "prompt": "Announce our launch"},
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        with oneboard.app.app_context():
            posts = oneboard.list_social_posts(self.user_id)
        self.assertEqual(posts[0]["text"], "Generated launch post")

    def test_create_post_rejects_unknown_channels_and_buffer_errors(self):
        self.set_buffer_key()
        with mock.patch.object(oneboard, "perform_json_request", side_effect=buffer_router):
            unknown = self.client.post(
                "/api/social/buffer/posts",
                json={"channel_id": "nope", "text": "Hello"},
            )
            missing_text = self.client.post(
                "/api/social/buffer/posts",
                json={"channel_id": "ch_1"},
            )

        self.assertEqual(unknown.status_code, 400)
        self.assertEqual(missing_text.status_code, 400)

        def failing_router(url, payload, headers=None, timeout=30):
            return {"errors": [{"message": "invalid channel"}]}

        with mock.patch.object(oneboard, "perform_json_request", side_effect=failing_router):
            failed = self.client.post(
                "/api/social/buffer/posts",
                json={"channel_id": "ch_1", "text": "Hello"},
            )

        self.assertEqual(failed.status_code, 400)
        self.assertIn("invalid channel", failed.get_data(as_text=True))

    def test_social_page_renders_composer_and_nav(self):
        response = self.client.get("/social")

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_data(as_text=True)
        self.assertIn('id="socialApp"', body)
        self.assertIn('id="socialPreviewText"', body)
        self.assertIn('id="socialAssistBtn"', body)
        self.assertIn('id="socialImageBtn"', body)
        self.assertIn('href="/social"', body)

    def test_social_generate_returns_ai_text(self):
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.user_id),
            )
        with mock.patch.object(
            oneboard,
            "run_ai_provider_prompt",
            return_value=("Launch day is here", {"total_tokens": 9}, "muse-text-1.0"),
        ), mock.patch.object(
            oneboard,
            "get_muse_models",
            return_value=["muse-text-1.0", "muse-image-1.0"],
        ):
            response = self.client.post(
                "/api/social/generate",
                json={"prompt": "Announce launch day"},
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["text"], "Launch day is here")

        missing = self.client.post("/api/social/generate", json={})
        self.assertEqual(missing.status_code, 400)

    def test_create_post_with_image_sends_assets(self):
        self.set_buffer_key()
        seen_queries = []

        def capture(url, payload, headers=None, timeout=30):
            seen_queries.append((payload or {}).get("query") or "")
            return buffer_router(url, payload, headers, timeout)

        with mock.patch.object(oneboard, "perform_json_request", side_effect=capture):
            response = self.client.post(
                "/api/social/buffer/posts",
                json={
                    "channel_id": "ch_1",
                    "text": "Look at this",
                    "image_url": "https://cdn.example.test/pic.png",
                },
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        mutations = [query for query in seen_queries if "CreateBufferPost" in query]
        self.assertEqual(len(mutations), 1)
        self.assertIn("assets:", mutations[0])
        self.assertIn("https://cdn.example.test/pic.png", mutations[0])
        with oneboard.app.app_context():
            posts = oneboard.list_social_posts(self.user_id)
        self.assertEqual(posts[0]["image_url"], "https://cdn.example.test/pic.png")

        bad_url = self.client.post(
            "/api/social/buffer/posts",
            json={"channel_id": "ch_1", "text": "Hi", "image_url": "not-a-url"},
        )
        self.assertEqual(bad_url.status_code, 400)
