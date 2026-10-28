import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-health-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-health-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "health-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


class ActionCenterTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-health-workspace-")
        self.workspace_path = Path(self.workspace.name)
        self.site = self.workspace_path / "health-site"
        (self.site / "img").mkdir(parents=True)
        (self.site / "index.html").write_text(
            "<html><head></head><body>"
            "<h1>Welcome to Acme</h1>"
            "<a href=\"missing.html\">gone</a>"
            "<a href=\"https://example.test/ok\">ext</a>"
            "<img src=\"img/photo.png\">"
            "<form><input type=\"text\" placeholder=\"Your name\"></form>"
            "</body></html>",
            encoding="utf-8",
        )
        try:
            from PIL import Image
        except ImportError:
            (self.site / "img" / "photo.png").write_bytes(os.urandom(600 * 1024))
        else:
            noise = Image.effect_noise((2000, 2000), 128).convert("RGB")
            noise.save(self.site / "img" / "photo.png")
        assert (self.site / "img" / "photo.png").stat().st_size > 500 * 1024

        oneboard.app.config.update(TESTING=True)
        self.owner_id = self._create_user("Owner")
        self.member_id = self._create_user("Member")
        self.client = oneboard.app.test_client()
        self.login(self.owner_id)

    def tearDown(self):
        self.workspace.cleanup()

    def _create_user(self, name):
        type(self).user_sequence += 1
        email = f"health-{name.lower()}-{self.user_sequence}@example.test"
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

    def _scan(self, **kwargs):
        response = self.client.post("/api/site-manager/health/scan", json=kwargs)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["health"]

    def _finding(self, health, check):
        return next(item for item in health["findings"] if item["check"] == check)

    def test_scan_detects_common_issues(self):
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        with mock.patch.object(
            oneboard, "check_external_url", return_value=(True, "")
        ):
            health = self._scan()
        checks = {item["check"] for item in health["findings"]}
        self.assertIn("missing_title", checks)
        self.assertIn("broken_internal_link", checks)
        self.assertIn("heavy_image", checks)
        self.assertIn("missing_alt", checks)
        self.assertIn("form_no_action", checks)
        self.assertIn("form_input_name", checks)
        self.assertNotIn("broken_external_link", checks)

        title = self._finding(health, "missing_title")
        self.assertEqual(title["page"], "index.html")
        self.assertIn("Welcome to Acme", title["proposal"]["title"])

        link = self._finding(health, "broken_internal_link")
        self.assertIn("missing.html", link["detail"])

        image = self._finding(health, "heavy_image")
        self.assertIn("photo.png", image["detail"])

    def test_external_link_check_marks_broken(self):
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})

        def fake_check(url, timeout=6):
            return (False, "HTTP 404")

        with mock.patch.object(oneboard, "check_external_url", side_effect=fake_check):
            health = self._scan()
        checks = {item["check"] for item in health["findings"]}
        self.assertIn("broken_external_link", checks)

        skipped = self._scan(skip_external=True)
        self.assertIn(
            "broken_external_link", {item["check"] for item in skipped["findings"]}
        )

    def test_apply_title_fix(self):
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        with mock.patch.object(oneboard, "check_external_url", return_value=(True, "")):
            health = self._scan()
        finding = self._finding(health, "missing_title")

        applied = self.client.post(
            f"/api/site-manager/health/findings/{finding['id']}/apply",
            json={"title": "Acme Home"},
        )
        self.assertEqual(applied.status_code, 200, applied.get_data(as_text=True))
        self.assertIn("<title>Acme Home</title>", (self.site / "index.html").read_text())

        updated = self.client.get("/api/site-manager/health").get_json()["health"]
        self.assertNotIn("missing_title", {item["check"] for item in updated["findings"]})
        with oneboard.app.app_context():
            history = oneboard.query_db(
                "SELECT source FROM website_update_history WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (self.owner_id,),
                one=True,
            )
        self.assertEqual(history["source"], "action-center")

    def test_apply_unlink_alt_and_input_fixes(self):
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        with mock.patch.object(oneboard, "check_external_url", return_value=(True, "")):
            health = self._scan()

        unlink = self._finding(health, "broken_internal_link")
        response = self.client.post(
            f"/api/site-manager/health/findings/{unlink['id']}/apply", json={}
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        body = (self.site / "index.html").read_text()
        self.assertNotIn("missing.html", body)
        self.assertIn("gone", body)

        alt = self._finding(health, "missing_alt")
        response = self.client.post(
            f"/api/site-manager/health/findings/{alt['id']}/apply",
            json={"alt": "Acme storefront"},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn('alt="Acme storefront"', (self.site / "index.html").read_text())

        named = self._finding(health, "form_input_name")
        response = self.client.post(
            f"/api/site-manager/health/findings/{named['id']}/apply", json={}
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn("name=", (self.site / "index.html").read_text())

    def test_heavy_image_without_pillow_stays_open_with_guidance(self):
        try:
            import PIL  # noqa: F401
        except ImportError:
            pillow_available = False
        else:
            pillow_available = True
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        with mock.patch.object(oneboard, "check_external_url", return_value=(True, "")):
            health = self._scan()
        finding = self._finding(health, "heavy_image")

        if pillow_available:
            before_size = (self.site / "img" / "photo.png").stat().st_size
            applied = self.client.post(
                f"/api/site-manager/health/findings/{finding['id']}/apply", json={}
            )
            self.assertEqual(applied.status_code, 200, applied.get_data(as_text=True))
            self.assertLess(
                (self.site / "img" / "photo.png").stat().st_size, before_size
            )
        else:
            applied = self.client.post(
                f"/api/site-manager/health/findings/{finding['id']}/apply", json={}
            )
            self.assertEqual(applied.status_code, 400, applied.get_data(as_text=True))
            updated = self.client.get("/api/site-manager/health").get_json()["health"]
            self.assertIn("heavy_image", {item["check"] for item in updated["findings"]})

    def test_ignore_and_reopen(self):
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        with mock.patch.object(oneboard, "check_external_url", return_value=(True, "")):
            health = self._scan()
        finding = self._finding(health, "missing_title")

        ignored = self.client.post(
            f"/api/site-manager/health/findings/{finding['id']}/ignore"
        )
        self.assertEqual(ignored.status_code, 200)
        updated = self.client.get("/api/site-manager/health").get_json()["health"]
        self.assertNotIn("missing_title", {item["check"] for item in updated["findings"]})
        self.assertEqual(updated["ignored_count"], 1)

        with mock.patch.object(oneboard, "check_external_url", return_value=(True, "")):
            rescanned = self._scan()
        self.assertNotIn(
            "missing_title", {item["check"] for item in rescanned["findings"]}
        )

        reopened = self.client.post(
            f"/api/site-manager/health/findings/{finding['id']}/reopen"
        )
        self.assertEqual(reopened.status_code, 200)
        updated = self.client.get("/api/site-manager/health").get_json()["health"]
        self.assertIn("missing_title", {item["check"] for item in updated["findings"]})

    def test_viewer_can_scan_but_not_apply(self):
        created = self.client.post("/api/teams", json={"name": "Health Team"})
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
        with mock.patch.object(oneboard, "check_external_url", return_value=(True, "")):
            self._scan()

        self.login(self.member_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        team_project = next(item for item in manager["projects"] if item["scope"] == "team")
        self.client.post("/api/site-manager/connect", json={"project_id": team_project["id"]})

        health = self.client.get("/api/site-manager/health").get_json()["health"]
        self.assertGreater(len(health["findings"]), 0)
        finding = health["findings"][0]
        denied = self.client.post(
            f"/api/site-manager/health/findings/{finding['id']}/apply", json={}
        )
        self.assertEqual(denied.status_code, 403)

        scanned = self.client.post("/api/site-manager/health/scan", json={"skip_external": True})
        self.assertEqual(scanned.status_code, 200)

    def test_health_page_renders(self):
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        page = self.client.get("/site-manager/health")
        self.assertEqual(page.status_code, 200, page.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
