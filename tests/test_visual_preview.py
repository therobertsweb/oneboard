import os
import re
import sys
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-preview-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-preview-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "preview-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


class VisualPreviewTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-preview-workspace-")
        self.workspace_path = Path(self.workspace.name)
        self.site = self.workspace_path / "preview-site"
        self.site.mkdir()
        (self.site / "index.html").write_text(
            "<html><head><link rel=\"stylesheet\" href=\"style.css\"></head>"
            "<body><h1>Hello shop</h1><p>Welcome</p></body></html>",
            encoding="utf-8",
        )
        (self.site / "style.css").write_text(
            "body { color: red; background: url('/images/background.png'); }",
            encoding="utf-8",
        )

        oneboard.app.config.update(TESTING=True)
        self.owner_id = self._create_user("Owner")
        self.member_id = self._create_user("Member")
        self.client = oneboard.app.test_client()
        self.login(self.owner_id)

    def tearDown(self):
        self.workspace.cleanup()

    def _create_user(self, name):
        type(self).user_sequence += 1
        email = f"preview-{name.lower()}-{self.user_sequence}@example.test"
        with oneboard.app.app_context():
            oneboard.execute_db(
                "INSERT INTO users (name, email, password_hash, email_verified) VALUES (?, ?, ?, 1)",
                (f"{name} {self.user_sequence}", email, oneboard.hash_password("password123")),
            )
            row = oneboard.query_db("SELECT id FROM users WHERE email = ?", (email,), one=True)
        return row["id"]

    def _email_of(self, user_id):
        with oneboard.app.app_context():
            return oneboard.query_db(
                "SELECT email FROM users WHERE id = ?", (user_id,), one=True
            )["email"]

    def login(self, user_id):
        with self.client.session_transaction() as session:
            session["user_id"] = user_id

    def test_preview_serves_workspace_pages(self):
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})

        studio = self.client.get("/site-manager?tab=preview")
        token_match = re.search(
            r'data-preview-token="([^"]+)"', studio.get_data(as_text=True)
        )
        self.assertIsNotNone(token_match)
        preview_token = token_match.group(1)

        page = self.client.get("/site-manager/preview/index.html")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Hello shop", page.get_data(as_text=True))
        self.assertIn("text/html", page.content_type)
        self.assertNotIn("oneboard-picker", page.get_data(as_text=True))

        picker = self.client.get("/site-manager/preview/index.html?picker=1")
        self.assertEqual(picker.status_code, 200)
        self.assertIn("oneboard-picker", picker.get_data(as_text=True))

        css = self.client.get("/site-manager/preview/style.css")
        self.assertEqual(css.status_code, 200)
        self.assertIn("color: red", css.get_data(as_text=True))
        self.assertIn(
            "url('/site-manager/preview/images/background.png')",
            css.get_data(as_text=True),
        )

        background = self.site / "images" / "background.png"
        background.parent.mkdir()
        background.write_bytes(b"preview image")
        public_preview = oneboard.app.test_client()
        preview_query = urllib.parse.urlencode({"preview_token": preview_token})
        public_page = public_preview.get(
            f"/site-manager/preview/index.html?picker=1&{preview_query}"
        )
        self.assertEqual(public_page.status_code, 200)
        self.assertIn("oneboard-picker", public_page.get_data(as_text=True))
        self.assertIn(
            f"/site-manager/preview/style.css?preview_token={preview_token}",
            public_page.get_data(as_text=True),
        )
        public_css = public_preview.get(
            f"/site-manager/preview/style.css?{preview_query}"
        )
        self.assertEqual(public_css.status_code, 200)
        self.assertIn(
            f"/site-manager/preview/images/background.png?preview_token={preview_token}",
            public_css.get_data(as_text=True),
        )
        public_image = public_preview.get(
            f"/site-manager/preview/images/background.png?{preview_query}"
        )
        self.assertEqual(public_image.status_code, 200)
        public_image.close()
        self.assertEqual(
            public_preview.get("/site-manager/preview/style.css").status_code, 404
        )

        root_page = self.site / "root-assets.html"
        root_page.write_text(
            """<html><head><link rel="stylesheet" href="/style.css">
            <style>body { background: url('/images/inline.png'); }</style>
            </head><body style="background: url('/images/attribute.png');"></body></html>""",
            encoding="utf-8",
        )
        root_page_response = self.client.get(
            "/site-manager/preview/root-assets.html?picker=1"
        )
        self.assertEqual(root_page_response.status_code, 200)
        self.assertIn(
            'href="/site-manager/preview/style.css"',
            root_page_response.get_data(as_text=True),
        )
        self.assertIn(
            "url('/site-manager/preview/images/inline.png')",
            root_page_response.get_data(as_text=True),
        )
        self.assertIn(
            "url('/site-manager/preview/images/attribute.png')",
            root_page_response.get_data(as_text=True),
        )

        missing = self.client.get("/site-manager/preview/nope.html")
        self.assertEqual(missing.status_code, 404)

        escape = self.client.get("/site-manager/preview/../outside.html")
        self.assertEqual(escape.status_code, 404)

    def test_preview_without_directory_is_404(self):
        fresh_id = self._create_user("Fresh")
        self.login(fresh_id)
        response = self.client.get("/site-manager/preview/index.html")
        self.assertEqual(response.status_code, 404)

    def test_select_element_and_targeted_update(self):
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.owner_id),
            )
        selected = self.client.post(
            "/api/site-manager/preview/select",
            json={
                "page": "index.html",
                "selector": "body > h1:nth-of-type(1)",
                "tag": "h1",
                "text": "Hello shop",
                "html": "<h1>Hello shop</h1>",
            },
        )
        self.assertEqual(selected.status_code, 200, selected.get_data(as_text=True))
        self.assertEqual(
            selected.get_json()["selection"]["selector"], "body > h1:nth-of-type(1)"
        )

        ai_response = {
            "summary": "Changed hero.",
            "files": [
                {
                    "path": "index.html",
                    "content": "<html><body><h1>Hello red shop</h1></body></html>",
                }
            ],
        }
        with mock.patch.object(
            oneboard,
            "run_ai_provider_prompt",
            return_value=(oneboard.json.dumps(ai_response), {"total_tokens": 5}, "muse-text-1.0"),
        ) as provider, mock.patch.object(
            oneboard, "get_muse_models", return_value=["muse-text-1.0"]
        ):
            response = self.client.post(
                "/api/site-manager/codex-update", json={"prompt": "cambia esto a rojo"}
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        sent_prompt = provider.call_args.args[3]
        self.assertIn("body > h1:nth-of-type(1)", sent_prompt)
        self.assertIn("Hello shop", sent_prompt)
        self.assertIn("index.html", sent_prompt)

        manager = self.client.get("/api/site-manager").get_json()["manager"]
        self.assertIsNone(manager["preview_selection"])

    def test_compare_api_and_before_serve(self):
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.owner_id),
            )
        ai_response = {
            "summary": "Changed hero.",
            "files": [
                {
                    "path": "index.html",
                    "content": "<html><body><h1>After hero</h1></body></html>",
                }
            ],
        }
        with mock.patch.object(
            oneboard,
            "run_ai_provider_prompt",
            return_value=(oneboard.json.dumps(ai_response), {"total_tokens": 5}, "muse-text-1.0"),
        ), mock.patch.object(
            oneboard, "get_muse_models", return_value=["muse-text-1.0"]
        ):
            update = self.client.post(
                "/api/site-manager/codex-update", json={"prompt": "Change hero"}
            )
        self.assertEqual(update.status_code, 200, update.get_data(as_text=True))
        update_id = update.get_json()["manager"]["updates"][0]["id"]

        compare = self.client.get(f"/api/site-manager/updates/{update_id}/compare")
        self.assertEqual(compare.status_code, 200, compare.get_data(as_text=True))
        files = compare.get_json()["files"]
        entry = next(item for item in files if item["path"] == "index.html")
        self.assertEqual(entry["change"], "modified")
        self.assertEqual(entry["kind"], "visual")
        self.assertTrue(entry["before_url"])
        self.assertTrue(entry["after_url"])

        before = self.client.get(entry["before_url"])
        self.assertEqual(before.status_code, 200)
        self.assertIn("Hello shop", before.get_data(as_text=True))
        after = self.client.get(entry["after_url"])
        self.assertEqual(after.status_code, 200)
        self.assertIn("After hero", after.get_data(as_text=True))

        page = self.client.get(f"/site-manager/updates/{update_id}/compare")
        self.assertEqual(page.status_code, 200, page.get_data(as_text=True))

    def test_viewer_can_preview_but_not_apply_picked_change(self):
        created = self.client.post("/api/teams", json={"name": "Preview Team"})
        team_id = created.get_json()["team"]["id"]
        invite = self.client.post(
            f"/api/teams/{team_id}/invites",
            json={"email": self._email_of(self.member_id), "role": "viewer"},
        ).get_json()
        token = invite["invite_link"].rstrip("/").rsplit("/", 1)[-1]
        self.login(self.member_id)
        self.client.post("/api/teams/invites/accept", json={"token": token})

        self.login(self.owner_id)
        connected = self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        project_id = next(
            item["id"]
            for item in connected.get_json()["manager"]["projects"]
            if item["path"] == str(self.site.resolve())
        )
        self.client.post(f"/api/teams/{team_id}/projects", json={"project_id": project_id})

        self.login(self.member_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        team_project = next(item for item in manager["projects"] if item["scope"] == "team")
        self.client.post("/api/site-manager/connect", json={"project_id": team_project["id"]})

        page = self.client.get("/site-manager/preview/index.html")
        self.assertEqual(page.status_code, 200)
        selected = self.client.post(
            "/api/site-manager/preview/select",
            json={"page": "index.html", "selector": "h1", "tag": "h1", "text": "Hello"},
        )
        self.assertEqual(selected.status_code, 200)
        denied = self.client.post(
            "/api/site-manager/codex-update", json={"prompt": "cambia esto"}
        )
        self.assertEqual(denied.status_code, 403)


if __name__ == "__main__":
    unittest.main()
