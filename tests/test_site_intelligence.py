import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-intelligence-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-intelligence-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "intelligence-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


class SiteIntelligenceTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-intelligence-workspace-")
        self.workspace_path = Path(self.workspace.name)
        self.site = self.workspace_path / "intel-site"
        self.site.mkdir(parents=True)
        (self.site / "index.html").write_text(
            "<html><head></head><body>"
            "<h1>Acme Bakery</h1>"
            "<p>Fresh sourdough bread baked every morning in Oaxaca.</p>"
            "<a href=\"missing.html\">gone</a>"
            "<form><input type=\"text\" placeholder=\"Your name\"></form>"
            "</body></html>",
            encoding="utf-8",
        )
        (self.site / "about.html").write_text(
            "<html><head><title>About Acme Bakery</title></head><body>"
            "<h1>Our story</h1>"
            "<p>Family bakery since 1998. We teach baking workshops every month.</p>"
            "</body></html>",
            encoding="utf-8",
        )
        oneboard.app.config.update(TESTING=True)
        self.owner_id = self._create_user("Owner")
        self.client = oneboard.app.test_client()
        self.login(self.owner_id)

    def tearDown(self):
        self.workspace.cleanup()

    def _create_user(self, name):
        type(self).user_sequence += 1
        email = f"intel-{name.lower()}-{self.user_sequence}@example.test"
        with oneboard.app.app_context():
            oneboard.execute_db(
                "INSERT INTO users (name, email, password_hash, email_verified) VALUES (?, ?, ?, 1)",
                (f"{name} {self.user_sequence}", email, oneboard.hash_password("password123")),
            )
            row = oneboard.query_db("SELECT id FROM users WHERE email = ?", (email,), one=True)
        return row["id"]

    def login(self, user_id):
        with self.client.session_transaction() as session:
            session["user_id"] = user_id

    def _connect(self):
        response = self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def _brand(self):
        response = self.client.post(
            "/api/site-manager/site",
            json={
                "brand": {
                    "business_name": "Acme Bakery",
                    "tagline": "Bread worth waking up for",
                    "services": "Sourdough bread, Baking workshops",
                    "audience": "Local food lovers",
                }
            },
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def _scan(self):
        with mock.patch.object(oneboard, "check_external_url", return_value=(True, "")):
            response = self.client.post("/api/site-manager/health/scan", json={"skip_external": True})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["health"]

    def _set_ai_key(self):
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.owner_id),
            )

    def test_intelligence_combines_brand_pages_and_issues(self):
        self._connect()
        self._brand()
        health = self._scan()
        self.assertGreater(len(health["findings"]), 0)

        response = self.client.get("/api/site-manager/intelligence")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        intelligence = response.get_json()["intelligence"]
        self.assertTrue(intelligence["has_site"])
        self.assertEqual(intelligence["brand"]["business_name"], "Acme Bakery")
        paths = [page["path"] for page in intelligence["pages"]]
        self.assertIn("index.html", paths)
        self.assertIn("about.html", paths)
        index = next(page for page in intelligence["pages"] if page["path"] == "index.html")
        self.assertIn("sourdough", index["excerpt"])
        checks = {issue["check"] for issue in intelligence["open_issues"]}
        self.assertIn("missing_title", checks)

    def test_fix_all_applies_automatic_fixes(self):
        self._connect()
        health = self._scan()
        fixable = {"missing_title", "broken_internal_link", "form_input_name"}
        self.assertTrue(fixable & {item["check"] for item in health["findings"]})

        response = self.client.post("/api/site-manager/health/fix-all", json={})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertGreaterEqual(payload["fixed"], 3)
        self.assertGreaterEqual(payload["skipped"], 1)
        remaining = {item["check"] for item in payload["health"]["findings"]}
        self.assertTrue(remaining <= {"form_no_action", "form_no_submit"})
        updated = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn("<title>", updated)
        self.assertNotIn("missing.html", updated)

    def test_ai_fix_repairs_forms(self):
        self._connect()
        self._set_ai_key()
        health = self._scan()
        form_issue = next(item for item in health["findings"] if item["check"] == "form_no_action")
        fixed_page = (
            "<html><head><title>Acme Bakery</title></head><body>"
            "<h1>Acme Bakery</h1>"
            "<form action=\"/contact\" method=\"post\">"
            "<input type=\"text\" name=\"your_name\" placeholder=\"Your name\">"
            "<button type=\"submit\">Send</button></form>"
            "</body></html>"
        )
        ai_response = {"summary": "Fixed form.", "files": [{"path": "index.html", "content": fixed_page}]}
        with mock.patch.object(
            oneboard, "run_ai_provider_prompt",
            return_value=(json.dumps(ai_response), {}, "muse-text-1.0"),
        ) as provider, mock.patch.object(
            oneboard, "get_muse_models", return_value=["muse-text-1.0"]
        ):
            response = self.client.post(
                "/api/site-manager/health/ai-fix", json={"finding_ids": [form_issue["id"]]}
            )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["fixed"], 1)
        sent_prompt = provider.call_args.args[3]
        self.assertIn("form_no_action", sent_prompt)
        updated = (self.site / "index.html").read_text(encoding="utf-8")
        self.assertIn('action="/contact"', updated)
        self.assertIn("Send</button>", updated)

    def test_health_summary_uses_ai(self):
        self._connect()
        self._set_ai_key()
        self._scan()
        with mock.patch.object(
            oneboard, "run_ai_provider_prompt",
            return_value=("Plain language summary.", {}, "muse-text-1.0"),
        ) as provider, mock.patch.object(
            oneboard, "get_muse_models", return_value=["muse-text-1.0"]
        ):
            response = self.client.post("/api/site-manager/health/summary", json={})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["summary"], "Plain language summary.")
        sent_prompt = provider.call_args.args[3]
        self.assertIn("missing_title", sent_prompt)
        self.assertIn("Acme Bakery", sent_prompt)

    def test_social_suggestions_come_from_site(self):
        self._connect()
        self._brand()
        event = self.client.post(
            "/api/site-manager/calendar",
            json={"kind": "promo", "title": "Weekend sourdough discount", "starts_on": "2026-11-01"},
        )
        self.assertEqual(event.status_code, 200, event.get_data(as_text=True))
        response = self.client.get("/api/social/suggestions")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertTrue(payload["has_site"])
        joined = " ".join(item["prompt"] for item in payload["suggestions"])
        self.assertIn("Sourdough", joined)
        self.assertIn("Weekend sourdough discount", joined)
        self.assertIn("Our story", joined)

    def test_single_page_site_supplies_social_ideas_without_brand(self):
        self._connect()
        (self.site / "about.html").unlink()
        payload = self.client.get("/api/social/suggestions").get_json()
        self.assertIn("sourdough", json.dumps(payload["suggestions"]))

    def _save_security_scan(self, domain="bakery.example"):
        scan = {
            "domain": domain, "score": 70, "grade": "C", "verdict": "Review headers",
            "http": {"https_available": True, "missing_headers": ["X-Content-Type-Options"]},
            "tls": {"hsts": False, "status": "ok"}, "dns": {"status": "ok"},
            "tech": {"hints": []},
            "recommendations": [{"title": "Add X-Content-Type-Options", "detail": "Use nosniff"}],
        }
        with oneboard.app.app_context():
            return oneboard.save_security_scan_result(self.owner_id, scan)

    def test_security_context_is_linked_only_to_matching_project_and_domain(self):
        self._connect()
        self.client.post("/api/site-manager/site", json={"brand": {"website": "https://bakery.example"}})
        scan_id = self._save_security_scan()
        self._save_security_scan("unrelated.example")
        intel = self.client.get("/api/site-manager/intelligence").get_json()["intelligence"]
        self.assertEqual(intel["security_scan"]["id"], scan_id)
        repair = self.client.get(f"/security-scan/{scan_id}/repair")
        self.assertEqual(repair.status_code, 200)
        self.assertIn("Use nosniff", repair.get_data(as_text=True))
        other = self.workspace_path / "other"
        other.mkdir()
        self.client.post("/api/site-manager/connect", json={"path": str(other)})
        self.client.post("/api/site-manager/site", json={"brand": {"website": "https://bakery.example"}})
        intel = self.client.get("/api/site-manager/intelligence").get_json()["intelligence"]
        self.assertIsNone(intel["security_scan"])
        self.assertEqual(self.client.get(f"/security-scan/{scan_id}/repair").status_code, 302)

    def test_social_history_follows_project_and_preserves_unassigned_records(self):
        with oneboard.app.app_context():
            oneboard.record_social_post(self.owner_id, "ch", "channel", "Legacy", "draft")
        self._connect()
        with oneboard.app.app_context():
            oneboard.record_social_post(self.owner_id, "ch", "channel", "Bakery", "draft")
        other = self.workspace_path / "other"
        other.mkdir()
        self.client.post("/api/site-manager/connect", json={"path": str(other)})
        self.assertEqual(self.client.get("/api/social/buffer/posts").get_json()["posts"], [])
        self._connect()
        posts = self.client.get("/api/social/buffer/posts").get_json()["posts"]
        self.assertEqual([post["text"] for post in posts], ["Bakery"])
        legacy = self.client.get("/api/social/buffer/posts?scope=unassigned").get_json()["posts"]
        self.assertEqual([post["text"] for post in legacy], ["Legacy"])
        with oneboard.app.app_context():
            self.assertEqual(oneboard.query_db("SELECT COUNT(*) AS n FROM social_posts WHERE user_id = ?", (self.owner_id,), one=True)["n"], 2)

    def test_security_history_keeps_latest_scans_after_window_is_full(self):
        self._connect()
        for _ in range(121):
            latest_id = self._save_security_scan()
        with oneboard.app.app_context():
            history = oneboard.build_security_scan_history(self.owner_id)
        self.assertEqual(history["total"], 121)
        self.assertEqual(history["latest"][0]["id"], latest_id)

    def test_social_publishing_requires_project_publish_permission(self):
        self._connect()
        viewer_id = self._create_user("Viewer")
        team_id = self.client.post("/api/teams", json={"name": "Bakery team"}).get_json()["team"]["id"]
        with oneboard.app.app_context():
            email = oneboard.query_db("SELECT email FROM users WHERE id = ?", (viewer_id,), one=True)["email"]
            workspace_id = oneboard.get_current_workspace(self.owner_id)["id"]
        invitation = self.client.post(f"/api/teams/{team_id}/invites", json={"email": email, "role": "viewer"}).get_json()
        self.client.post(f"/api/teams/{team_id}/projects", json={"project_id": workspace_id})
        self.login(viewer_id)
        token = invitation["invite_link"].rstrip("/").rsplit("/", 1)[-1]
        self.client.post("/api/teams/invites/accept", json={"token": token})
        response = self.client.post("/api/site-manager/connect", json={"project_id": workspace_id})
        self.assertEqual(response.status_code, 200)
        with mock.patch.object(oneboard, "create_buffer_post") as publish:
            response = self.client.post("/api/social/buffer/posts", json={"channel_id": "ch", "text": "Test"})
            self.assertEqual(response.status_code, 403)
            publish.assert_not_called()

    def test_stale_tabs_cannot_generate_publish_or_repair_another_project(self):
        self._connect()
        other = self.workspace_path / "other"
        other.mkdir()
        self.client.post("/api/site-manager/connect", json={"path": str(other)})
        with mock.patch.object(oneboard, "run_ai_provider_prompt") as ai, mock.patch.object(oneboard, "create_buffer_post") as publish:
            for endpoint in ("/api/social/generate", "/api/social/ideas", "/api/social/buffer/posts",
                             "/api/site-manager/health/scan", "/api/site-manager/health/ai-fix",
                             "/api/site-manager/health/fix-all", "/api/security-scan"):
                response = self.client.post(endpoint, json={"expected_directory_path": str(self.site)})
                self.assertEqual(response.status_code, 400, endpoint)
                self.assertIn("changed", response.get_json()["error"])
            ai.assert_not_called()
            publish.assert_not_called()

    def test_large_site_context_keeps_findings_events_and_page_content(self):
        self._connect()
        self._scan()
        self.client.post("/api/site-manager/calendar", json={"kind": "promo", "title": "Bread festival", "starts_on": "2026-11-01"})
        for index in range(12):
            (self.site / f"long-{index}.html").write_text("<h1>Baking</h1><p>" + "fresh bread " * 300 + "</p>")
        with oneboard.app.app_context():
            context = oneboard.site_intelligence_prompt_block(self.owner_id)
        self.assertLessEqual(len(context), oneboard.INTELLIGENCE_MAX_PROMPT_CHARS)
        self.assertIn("missing_title", context)
        self.assertIn("Bread festival", context)
        self.assertIn("sourdough", context)

    def test_studio_edit_refreshes_health_and_social_and_keeps_security_unverified(self):
        self._connect()
        self._set_ai_key()
        self._scan()
        self.client.post("/api/site-manager/site", json={"brand": {"website": "https://bakery.example"}})
        scan_id = self._save_security_scan()
        plan = {"summary": "Updated homepage", "files": [{"path": "index.html", "content": "<html><head><title>Bakery</title></head><body><h1>Bakery</h1><p>New croissant workshops.</p></body></html>"}]}
        with mock.patch.object(oneboard, "run_ai_provider_prompt", return_value=(json.dumps(plan), {}, "muse-text-1.0")) as provider, mock.patch.object(oneboard, "get_muse_models", return_value=["muse-text-1.0"]):
            response = self.client.post("/api/site-manager/codex-update", json={"prompt": "Update homepage", "expected_directory_path": str(self.site)})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn("X-Content-Type-Options", provider.call_args.args[3])
        intel = self.client.get("/api/site-manager/intelligence").get_json()["intelligence"]
        self.assertNotIn("missing_title", {issue["check"] for issue in intel["open_issues"]})
        self.assertEqual(intel["security_scan"]["id"], scan_id)
        self.assertIn("croissant", json.dumps(self.client.get("/api/social/suggestions").get_json()))
        with oneboard.app.app_context():
            history = oneboard.query_db("SELECT snapshot_path, status FROM website_update_history WHERE user_id = ? ORDER BY id DESC LIMIT 1", (self.owner_id,), one=True)
            self.assertTrue(Path(history["snapshot_path"]).exists())
            self.assertEqual(history["status"], "pending")

    def test_sections_render_shared_project_and_security_navigation(self):
        self._connect()
        self.client.post("/api/site-manager/site", json={"brand": {"website": "https://bakery.example"}})
        self._save_security_scan()
        self._scan()
        for path in ("/social", "/security-scan", "/site-manager/health"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn("workspace-context", response.get_data(as_text=True))
            self.assertIn(str(self.site), response.get_data(as_text=True))
        security = self.client.get("/security-scan").get_data(as_text=True)
        self.assertIn('value="bakery.example"', security)
        self.assertIn("/repair?", security)

    def test_social_generate_without_prompt_uses_site(self):
        self._connect()
        self._brand()
        self._set_ai_key()
        with mock.patch.object(
            oneboard, "run_ai_provider_prompt",
            return_value=("Fresh bread every morning!", {}, "muse-text-1.0"),
        ) as provider, mock.patch.object(
            oneboard, "get_muse_models", return_value=["muse-text-1.0"]
        ):
            response = self.client.post("/api/social/generate", json={})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        payload = response.get_json()
        self.assertEqual(payload["text"], "Fresh bread every morning!")
        self.assertTrue(payload["from_site"])
        sent_prompt = provider.call_args.args[3]
        self.assertIn("Acme Bakery", sent_prompt)
        self.assertIn("sourdough", sent_prompt)

    def test_social_ideas_with_ai(self):
        self._connect()
        self._brand()
        self._set_ai_key()
        ai_text = (
            "1. Morning bake: show the 5am sourdough routine.\n"
            "2. Workshop invite: invite followers to the monthly class.\n"
        )
        with mock.patch.object(
            oneboard, "run_ai_provider_prompt", return_value=(ai_text, {}, "muse-text-1.0")
        ), mock.patch.object(
            oneboard, "get_muse_models", return_value=["muse-text-1.0"]
        ):
            response = self.client.post("/api/social/ideas", json={})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        ideas = response.get_json()["ideas"]
        self.assertEqual(len(ideas), 2)
        self.assertEqual(ideas[0]["title"], "Morning bake")
        self.assertIn("sourdough", ideas[0]["prompt"])


if __name__ == "__main__":
    unittest.main()
