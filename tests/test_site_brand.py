import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-brand-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-brand-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "brand-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class SiteBrandTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-brand-workspace-")
        self.workspace_path = Path(self.workspace.name)
        self.site = self.workspace_path / "brand-site"
        self.site.mkdir()
        (self.site / "index.html").write_text("brand-original", encoding="utf-8")

        oneboard.app.config.update(TESTING=True)
        self.owner_id = self._create_user("Owner")
        self.member_id = self._create_user("Member")
        self.client = oneboard.app.test_client()
        self.login(self.owner_id)

    def tearDown(self):
        self.workspace.cleanup()

    def _create_user(self, name):
        type(self).user_sequence += 1
        email = f"brand-{name.lower()}-{self.user_sequence}@example.test"
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

    def _brand_payload(self):
        return {
            "business_name": "Acme Bakery",
            "tagline": "Fresh bread daily",
            "services": "Bakery, catering",
            "audience": "Local families",
            "tone": "Warm and friendly",
            "colors": {"primary": "#123456", "secondary": "#abcdef", "accent": ""},
            "fonts": {"headings": "Georgia", "body": "Arial"},
            "phone": "555-0100",
            "email": "hello@acme.test",
        }

    def test_site_settings_roundtrip(self):
        connected = self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        self.assertEqual(connected.status_code, 200, connected.get_data(as_text=True))

        saved = self.client.post(
            "/api/site-manager/site",
            json={
                "display_name": "Acme Site",
                "client_name": "Acme Corp",
                "gsc_property": "https://acme.test/",
                "brand": self._brand_payload(),
            },
        )
        self.assertEqual(saved.status_code, 200, saved.get_data(as_text=True))
        settings = saved.get_json()["site"]
        self.assertEqual(settings["display_name"], "Acme Site")
        self.assertEqual(settings["client_name"], "Acme Corp")
        self.assertEqual(settings["gsc_property"], "https://acme.test/")
        self.assertEqual(settings["brand"]["business_name"], "Acme Bakery")
        self.assertEqual(settings["brand"]["colors"]["primary"], "#123456")

        fetched = self.client.get("/api/site-manager/site")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.get_json()["site"]["display_name"], "Acme Site")

        manager = self.client.get("/api/site-manager").get_json()["manager"]
        current = next(item for item in manager["projects"] if item["is_current"])
        self.assertEqual(current["display_name"], "Acme Site")
        self.assertEqual(current["client_name"], "Acme Corp")

    def test_brand_is_used_in_codex_prompt(self):
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        self.client.post("/api/site-manager/site", json={"brand": self._brand_payload()})
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.owner_id),
            )
        ai_response = {
            "summary": "Updated hero.",
            "files": [{"path": "index.html", "content": "<html><body>Hero</body></html>"}],
        }
        with mock.patch.object(
            oneboard,
            "run_ai_provider_prompt",
            return_value=(oneboard.json.dumps(ai_response), {"total_tokens": 5}, "muse-text-1.0"),
        ) as provider, mock.patch.object(
            oneboard, "get_muse_models", return_value=["muse-text-1.0"]
        ):
            response = self.client.post(
                "/api/site-manager/codex-update", json={"prompt": "Update the hero"}
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        sent_prompt = provider.call_args.args[3]
        self.assertIn("Acme Bakery", sent_prompt)
        self.assertIn("#123456", sent_prompt)
        self.assertIn("Warm and friendly", sent_prompt)

    def test_social_generate_includes_brand(self):
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        self.client.post("/api/site-manager/site", json={"brand": self._brand_payload()})
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.owner_id),
            )
        with mock.patch.object(
            oneboard, "run_ai_provider_prompt", return_value=("Post text", {}, "muse-text-1.0")
        ) as provider, mock.patch.object(
            oneboard, "get_muse_models", return_value=["muse-text-1.0"]
        ):
            response = self.client.post("/api/social/generate", json={"prompt": "Write a post"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        sent_prompt = provider.call_args.args[3]
        self.assertIn("Acme Bakery", sent_prompt)
        self.assertIn("Local families", sent_prompt)

    def test_viewer_cannot_edit_site_settings(self):
        created = self.client.post("/api/teams", json={"name": "Brand Team"})
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
        self.client.post("/api/site-manager/site", json={"brand": self._brand_payload()})

        self.login(self.member_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        team_project = next(item for item in manager["projects"] if item["scope"] == "team")
        self.client.post("/api/site-manager/connect", json={"project_id": team_project["id"]})

        fetched = self.client.get("/api/site-manager/site")
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.get_json()["site"]["brand"]["business_name"], "Acme Bakery")

        denied = self.client.post(
            "/api/site-manager/site", json={"display_name": "Hacked"}
        )
        self.assertEqual(denied.status_code, 403, denied.get_data(as_text=True))

        self.login(self.owner_id)
        granted = self.client.post(
            f"/api/teams/{team_id}/members/{self.member_id}", json={"role": "editor"}
        )
        self.assertEqual(granted.status_code, 200)
        self.login(self.member_id)
        allowed = self.client.post(
            "/api/site-manager/site", json={"display_name": "Member Name"}
        )
        self.assertEqual(allowed.status_code, 200, allowed.get_data(as_text=True))

    def test_generated_images_scoped_per_site(self):
        site_b = self.workspace_path / "brand-site-b"
        site_b.mkdir()
        (site_b / "index.html").write_text("b", encoding="utf-8")
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})

        counter = {"n": 0}

        def fake_generate(user_id, prompt, model=None, output_format="png"):
            counter["n"] += 1
            filename = f"user-{user_id}-test{counter['n']}.png"
            with open(os.path.join(oneboard.generated_image_directory(), filename), "wb") as handle:
                handle.write(PNG_BYTES)
            return {
                "filename": filename,
                "model": model or "muse-image-1.0",
                "response_id": f"resp-{counter['n']}",
                "size_bytes": len(PNG_BYTES),
            }

        with mock.patch.object(oneboard, "run_muse_image_generation", side_effect=fake_generate):
            first = self.client.post("/api/ai/images", json={"prompt": "logo for site A"})
            self.assertEqual(first.status_code, 200, first.get_data(as_text=True))
            self.client.post("/api/site-manager/connect", json={"path": str(site_b)})
            second = self.client.post("/api/ai/images", json={"prompt": "logo for site B"})
            self.assertEqual(second.status_code, 200, second.get_data(as_text=True))

        scoped = self.client.get("/api/ai/images", query_string={"scope": "site"})
        self.assertEqual(scoped.status_code, 200)
        scoped_files = [item["filename"] for item in scoped.get_json()["images"]]
        self.assertEqual(scoped_files, [second.get_json()["image"]["filename"]])

        everything = self.client.get("/api/ai/images")
        self.assertEqual(len(everything.get_json()["images"]), 2)

    def test_team_member_can_fetch_site_images(self):
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        filename = f"user-{self.owner_id}-shared1.png"
        with open(os.path.join(oneboard.generated_image_directory(), filename), "wb") as handle:
            handle.write(PNG_BYTES)
        with oneboard.app.app_context():
            workspace = oneboard.get_current_workspace(self.owner_id)
            oneboard.execute_db(
                "INSERT INTO site_images (user_id, workspace_id, filename, prompt) VALUES (?, ?, ?, ?)",
                (self.owner_id, workspace["id"], filename, "shared art"),
            )

        created = self.client.post("/api/teams", json={"name": "Image Team"})
        team_id = created.get_json()["team"]["id"]
        invite = self.client.post(
            f"/api/teams/{team_id}/invites",
            json={"email": self._email_of(self.member_id), "role": "viewer"},
        ).get_json()
        token = invite["invite_link"].rstrip("/").rsplit("/", 1)[-1]
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        project_id = next(item["id"] for item in manager["projects"] if item["is_current"])
        self.client.post(f"/api/teams/{team_id}/projects", json={"project_id": project_id})

        self.login(self.member_id)
        self.client.post("/api/teams/invites/accept", json={"token": token})
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        team_project = next(item for item in manager["projects"] if item["scope"] == "team")
        self.client.post("/api/site-manager/connect", json={"project_id": team_project["id"]})

        shared = self.client.get(f"/uploads/generated-images/{filename}")
        self.assertEqual(shared.status_code, 200)
        self.assertEqual(shared.get_data(), PNG_BYTES)

        personal = f"user-{self.owner_id}-personal9.png"
        with open(os.path.join(oneboard.generated_image_directory(), personal), "wb") as handle:
            handle.write(PNG_BYTES)
        with oneboard.app.app_context():
            oneboard.execute_db(
                "INSERT INTO site_images (user_id, workspace_id, filename, prompt) VALUES (?, ?, ?, ?)",
                (self.owner_id, None, personal, "personal art"),
            )
        forbidden = self.client.get(f"/uploads/generated-images/{personal}")
        self.assertEqual(forbidden.status_code, 404)

    def test_gsc_property_scoped_per_site(self):
        import time as time_module

        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        saved = self.client.post(
            "/api/site-manager/site", json={"gsc_property": "https://site.test/"}
        )
        self.assertEqual(saved.status_code, 200, saved.get_data(as_text=True))

        with oneboard.app.app_context():
            oneboard.execute_db(
                """INSERT INTO google_search_console_connections
                   (user_id, access_token, expires_at, selected_site_url)
                   VALUES (?, ?, ?, ?)""",
                (self.owner_id, "token", int(time_module.time()) + 3600, "https://global.test/"),
            )
        connection = {"selected_site_url": "https://global.test/"}
        sites_response = {
            "siteEntry": [
                {"siteUrl": "https://global.test/", "permissionLevel": "siteOwner"},
                {"siteUrl": "https://site.test/", "permissionLevel": "siteOwner"},
            ]
        }
        with mock.patch.dict(
            os.environ, {"GOOGLE_CLIENT_ID": "x", "GOOGLE_CLIENT_SECRET": "y"}
        ), mock.patch.object(
            oneboard, "valid_google_connection", return_value=connection
        ), mock.patch.object(
            oneboard, "google_api_request", return_value=sites_response
        ), mock.patch.object(
            oneboard, "fetch_search_console_analytics", return_value={}
        ), oneboard.app.app_context():
            dashboard = oneboard.build_search_console_dashboard(self.owner_id)
        self.assertEqual(dashboard["selected_site_url"], "https://site.test/")
        self.assertTrue(dashboard["site_scoped"])
        with oneboard.app.app_context():
            row = oneboard.query_db(
                "SELECT selected_site_url FROM google_search_console_connections WHERE user_id = ?",
                (self.owner_id,),
                one=True,
            )
        self.assertEqual(row["selected_site_url"], "https://global.test/")

    def test_logo_upload_and_serve(self):
        import io as io_module

        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        upload = self.client.post(
            "/api/site-manager/site/logo",
            data={"logo": (io_module.BytesIO(PNG_BYTES), "logo.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(upload.status_code, 200, upload.get_data(as_text=True))
        logo_url = upload.get_json()["site"]["brand"]["logo_url"]
        served = self.client.get(logo_url)
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.get_data(), PNG_BYTES)

        self.login(self.member_id)
        forbidden = self.client.get(logo_url)
        self.assertEqual(forbidden.status_code, 404)

    def test_site_settings_page_renders(self):
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        page = self.client.get("/site-manager/site")
        self.assertEqual(page.status_code, 200, page.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
