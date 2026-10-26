import base64
import os
import tempfile
import unittest
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-muse-tests-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["SECRET_KEY"] = "muse-test-secret"

import app as oneboard


TINY_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8"
    "z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


class MuseProviderTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()

    def setUp(self):
        type(self).user_sequence += 1
        oneboard.app.config.update(TESTING=True)
        with oneboard.app.app_context():
            try:
                oneboard.execute_db(
                    "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                    (
                        "Muse Test",
                        f"muse-{self.user_sequence}@example.test",
                        oneboard.hash_password("password123"),
                    ),
                )
            except Exception:
                pass
            self.user_id = oneboard.query_db(
                "SELECT id FROM users WHERE email = ?",
                (f"muse-{self.user_sequence}@example.test",),
                one=True,
            )["id"]
        self.client = oneboard.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def test_openai_is_gone_and_muse_is_default(self):
        self.assertEqual(oneboard.DEFAULT_AI_PROVIDER, "muse")
        self.assertNotIn("openai", oneboard.AI_PROVIDER_MODELS)
        self.assertIn("muse", oneboard.AI_PROVIDER_MODELS)
        providers = [item["key"] for item in oneboard.ai_provider_catalog()]
        self.assertIn("muse", providers)
        self.assertNotIn("openai", providers)

    def test_parse_muse_models_accepts_api_shapes(self):
        shapes = [
            {"data": [{"id": "muse-image-1.0"}, {"id": "muse-text-1.0"}]},
            {"models": [{"name": "muse-image-1.0"}]},
            {"data": [{"name": "muse-image-1.0"}]},
        ]
        for payload in shapes:
            models = oneboard.parse_muse_models(payload)
            self.assertIn("muse-image-1.0", models)

    def test_parse_muse_response_extracts_text(self):
        payload = {
            "output_text": "",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": "hello from muse"}],
                }
            ],
            "usage": {"total_tokens": 7},
        }
        text, usage = oneboard.parse_muse_response(payload)
        self.assertEqual(text, "hello from muse")
        self.assertEqual(usage, {"total_tokens": 7})

    def test_muse_image_generation_saves_png(self):
        api_response = {
            "id": "resp-123",
            "status": "completed",
            "output": [
                {"type": "image_generation_call", "result": TINY_PNG_B64},
            ],
        }
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.user_id),
            )
        with mock.patch.object(
            oneboard, "perform_json_request", return_value=api_response
        ) as request:
            with oneboard.app.app_context():
                result = oneboard.run_muse_image_generation(
                    self.user_id, "a fox in a forest"
                )
        self.assertTrue(result["filename"].endswith(".png"))
        self.assertTrue(os.path.isfile(result["path"]))
        with open(result["path"], "rb") as image_file:
            self.assertEqual(image_file.read(), base64.b64decode(TINY_PNG_B64))
        sent_payload = request.call_args.args[1]
        self.assertEqual(sent_payload["model"], "muse-image-1.0")
        self.assertEqual(
            sent_payload["tools"][0]["type"], "image_generation"
        )

    def test_images_endpoints_work_without_network(self):
        response = self.client.get("/api/ai/images")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["images"], [])

        response = self.client.post("/api/ai/images", json={"prompt": ""})
        self.assertEqual(response.status_code, 400)

        response = self.client.post(
            "/api/ai/images", json={"prompt": "a fox in a forest"}
        )
        self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
        self.assertIn("Muse API key", response.get_json()["error"])

    def test_muse_models_endpoint_returns_fallback_without_key(self):
        response = self.client.get("/api/settings/muse-models")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn("muse-image-1.0", response.get_json()["models"])

        response = self.client.post("/api/settings/muse-models/refresh", json={})
        self.assertEqual(response.status_code, 400, response.get_data(as_text=True))

    def test_settings_page_shows_muse_section(self):
        response = self.client.get("/settings")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = response.get_data(as_text=True)
        self.assertIn('name="muse_api_key"', body)
        self.assertNotIn("openai_api_key", body)

    def test_site_update_runs_on_muse_without_codex_cli(self):
        site = tempfile.TemporaryDirectory(prefix="oneboard-muse-site-")
        self.addCleanup(site.cleanup)
        with open(os.path.join(site.name, "index.html"), "w", encoding="utf-8") as handle:
            handle.write("original")
        response = self.client.post(
            "/api/site-manager/connect", json={"path": site.name}
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

        ai_response = {
            "summary": "Updated homepage hero copy.",
            "files": [
                {
                    "path": "index.html",
                    "content": "<html><body><h1>Muse homepage copy</h1></body></html>",
                }
            ],
        }
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.user_id),
            )
        with mock.patch.object(
            oneboard,
            "run_ai_provider_prompt",
            return_value=(oneboard.json.dumps(ai_response), {"total_tokens": 42}, "muse-text-1.0"),
        ):
            with mock.patch.object(
                oneboard,
                "get_muse_models",
                return_value=["muse-text-1.0", "muse-image-1.0"],
            ):
                response = self.client.post(
                    "/api/site-manager/codex-update",
                    json={"prompt": "Update the homepage hero section"},
                )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        with open(os.path.join(site.name, "index.html"), encoding="utf-8") as handle:
            self.assertIn("Muse homepage copy", handle.read())
        update = response.get_json()["manager"]["updates"][0]
        self.assertEqual(update["source"], "ai-direct:muse")
        self.assertEqual(update["status"], "pending")


if __name__ == "__main__":
    unittest.main()
