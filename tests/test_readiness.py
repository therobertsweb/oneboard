"""Boundary and failure-path regressions; no live services or production data."""
import json
import os
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-readiness-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["SECRET_KEY"] = "readiness-test-secret"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as oneboard


class ReadinessTests(unittest.TestCase):
    sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()

    def setUp(self):
        type(self).sequence += 1
        self.temp = tempfile.TemporaryDirectory(prefix="oneboard-readiness-site-")
        self.site = Path(self.temp.name) / "site"
        self.site.mkdir()
        (self.site / "index.html").write_text("<html><body>Original</body></html>")
        oneboard.app.config["TESTING"] = True
        with oneboard.app.app_context():
            self.user_id = oneboard.execute_db(
                "INSERT INTO users (name, email, password_hash, email_verified, muse_api_key) VALUES (?, ?, ?, 1, ?)",
                ("Tester", f"ready-{self.sequence}@example.test", oneboard.hash_password("password123"), "fake-key"),
            )
        self.client = oneboard.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id
        self.assertEqual(self.client.post("/api/site-manager/connect", json={"path": str(self.site)}).status_code, 200)

    def tearDown(self):
        self.temp.cleanup()

    def test_json_shape_types_and_malformed_body_return_json_errors(self):
        for payload in ([], [1], "oops", 42, None, {"prompt": {}}, {"prompt": ["x"]}, {"prompt": "x\x00"}, {"publish_now": "false"}):
            response = self.client.post("/api/social/generate", data=json.dumps(payload), content_type="application/json")
            self.assertEqual(response.status_code, 400, payload)
            self.assertFalse(response.get_json()["ok"])
        response = self.client.post("/api/auth/login", data='{broken', content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["ok"])
        self.assertEqual(self.client.get("/api/does-not-exist").get_json()["ok"], False)

    def test_oversized_request_keeps_api_error_envelope(self):
        with mock.patch.dict(oneboard.app.config, {"MAX_CONTENT_LENGTH": 16}):
            response = self.client.post("/api/social/generate", json={"prompt": "x" * 100})
        self.assertEqual(response.status_code, 413)
        self.assertFalse(response.get_json()["ok"])

    def test_cross_origin_mutations_rejected_but_contact_form_still_works(self):
        for origin in ("https://evil.example", "null"):
            response = self.client.post("/api/site-manager/files/delete", json={"path": "index.html"}, headers={"Origin": origin})
            self.assertEqual(response.status_code, 403)
            self.assertTrue((self.site / "index.html").exists())
        with oneboard.app.app_context():
            _record, token = oneboard.create_form_token(self.user_id)
        # Form token values are deliberately public, limited to contact submissions.
        response = self.client.post(f"/forms/{token}/submit", json={"name": "Visitor", "message": "Hello"}, headers={"Origin": "https://client.example"})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))

    def test_entire_edit_plan_is_validated_before_writing(self):
        original = (self.site / "index.html").read_text()
        for bad in ("../escape.html", "/absolute.html", "index.html/child.txt", "index.html", "x\x00.txt"):
            plan = {"files": [{"path": "index.html", "content": "changed"}, {"path": bad, "content": "bad"}]}
            with self.assertRaises((ValueError, OSError)):
                oneboard.apply_site_ai_update_plan(str(self.site), plan)
            self.assertEqual((self.site / "index.html").read_text(), original)
        (self.site / "alias.html").symlink_to(self.site / "index.html")
        with self.assertRaises(ValueError):
            oneboard.apply_site_ai_update_plan(str(self.site), {"files": [{"path": "alias.html", "content": "bad"}]})
        self.assertEqual((self.site / "index.html").read_text(), original)

    def test_write_failure_rolls_back_previous_files_and_records_failed_history(self):
        (self.site / "second.html").write_text("Second original")
        plan = {"summary": "Change two pages", "files": [
            {"path": "index.html", "content": "Changed first"},
            {"path": "second.html", "content": "Changed second"},
        ]}
        original_replace = oneboard.os.replace
        def fail_second(source, destination):
            if str(destination).endswith("second.html"):
                raise OSError("Simulated disk failure")
            return original_replace(source, destination)
        with mock.patch.object(oneboard, "run_ai_provider_prompt", return_value=(json.dumps(plan), {}, "muse-text-1.0")), mock.patch.object(oneboard, "get_muse_models", return_value=["muse-text-1.0"]), mock.patch.object(oneboard.os, "replace", side_effect=fail_second):
            response = self.client.post("/api/site-manager/codex-update", json={"prompt": "Edit two pages"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("Original", (self.site / "index.html").read_text())
        self.assertEqual((self.site / "second.html").read_text(), "Second original")
        with oneboard.app.app_context():
            record = oneboard.query_db("SELECT status, snapshot_path FROM website_update_history WHERE user_id = ? ORDER BY id DESC LIMIT 1", (self.user_id,), one=True)
        self.assertEqual(record["status"], "failed")
        self.assertTrue(Path(record["snapshot_path"]).exists())

    def test_preview_and_public_portal_do_not_expose_application_or_server_files(self):
        for path in ("/site-manager/preview/index.html?picker=1", "/api/site-manager/files/raw?path=index.html"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("sandbox allow-scripts", response.headers["Content-Security-Policy"])
            self.assertNotIn("allow-same-origin", response.headers["Content-Security-Policy"])
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            response.close()
        link = {"workspace_path": str(self.site)}
        for name in (".env", "app.py", "database.sqlite", "secrets.json"):
            (self.site / name).write_text("private")
            self.assertIsNone(oneboard.resolve_link_page(link, name))
        (self.site / "leak.js").symlink_to(self.site / ".env")
        self.assertIsNone(oneboard.resolve_link_page(link, "leak.js"))
        self.assertEqual(oneboard.resolve_link_page(link, "index.html"), str((self.site / "index.html").resolve()))

    def test_preview_selection_is_cleared_after_project_switch(self):
        self.client.post("/api/site-manager/preview/select", json={"page": "index.html", "selector": "body"})
        other = Path(self.temp.name) / "other"
        other.mkdir()
        (other / "index.html").write_text("Other")
        self.client.post("/api/site-manager/connect", json={"path": str(other)})
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        self.assertIsNone(manager["preview_selection"])

    def test_stale_project_guard_covers_calendar_settings_and_html_forms(self):
        other = Path(self.temp.name) / "other"
        other.mkdir()
        for path in ("/api/site-manager/calendar", "/api/site-manager/site", "/api/site-manager/request-links"):
            response = self.client.post(path, json={"expected_directory_path": str(other), "title": "Wrong project"})
            self.assertEqual(response.status_code, 400, path)
        response = self.client.post("/site-manager/files/delete", data={"expected_directory_path": str(other), "path": "index.html"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue((self.site / "index.html").exists())

    def test_shared_directory_lock_rejects_another_user_during_edit(self):
        with oneboard.app.app_context():
            second = oneboard.execute_db("INSERT INTO users (name,email,password_hash,email_verified) VALUES ('Other', ?, 'unused',1)", (f"other-{self.sequence}@example.test",))
            team = oneboard.create_team(self.user_id, "Shared lock test")
            project = oneboard.query_db("SELECT id FROM website_workspaces WHERE user_id = ? AND path = ?",
                                       (self.user_id, str(self.site.resolve())), one=True)
            oneboard.add_team_project(team["id"], self.user_id, project_id=project["id"])
            _, token = oneboard.invite_team_member(team["id"], self.user_id, f"other-{self.sequence}@example.test")
            oneboard.accept_team_invite(token, second)
            oneboard.connect_site_project(second, project_id=project["id"])
        entered = threading.Event()
        release = threading.Event()
        def hold():
            with oneboard.app.app_context(), oneboard.site_operation_lock(self.user_id):
                entered.set()
                release.wait(5)
        thread = threading.Thread(target=hold)
        thread.start()
        try:
            self.assertTrue(entered.wait(2))
            with oneboard.app.app_context(), self.assertRaises(ValueError):
                with oneboard.site_operation_lock(second):
                    self.fail("Concurrent write accepted")
        finally:
            release.set()
            thread.join(2)

    def test_completed_calendar_event_is_not_executed_twice(self):
        response = self.client.post("/api/site-manager/calendar", json={"title": "Launch", "brief": "Update homepage", "kind": "note"})
        event_id = response.get_json()["event"]["id"]
        with mock.patch.object(oneboard, "run_site_codex_update", return_value={"exit_code": 0}) as update:
            first = self.client.post(f"/api/site-manager/calendar/{event_id}/execute", json={})
            second = self.client.post(f"/api/site-manager/calendar/{event_id}/execute", json={})
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(update.call_count, 1)

    def test_main_pages_and_read_apis_render_without_external_services(self):
        pages = ("/dashboard", "/site-manager", "/site-manager/health", "/site-manager/calendar",
                 "/site-manager/inbox", "/site-manager/alerts", "/site-manager/reports",
                 "/site-manager/requests", "/site-manager/site", "/social", "/security-scan",
                 "/notifications", "/teams", "/help", "/settings")
        for path in pages:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])
                self.assertIn("text/html", response.content_type)
                response.close()
        apis = ("/api/session", "/api/dashboard", "/api/site-manager", "/api/site-manager/health",
                "/api/site-manager/intelligence", "/api/site-manager/requests", "/api/site-manager/calendar",
                "/api/site-manager/inbox", "/api/site-manager/alerts", "/api/site-manager/reports",
                "/api/site-manager/site", "/api/teams", "/api/notifications", "/api/settings",
                "/api/security-scan", "/api/social/suggestions")
        for path in apis:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200, response.get_data(as_text=True)[:300])
                self.assertTrue(response.get_json()["ok"])

    def test_monthly_report_excludes_first_day_of_next_month(self):
        self.client.post("/api/site-manager/site", json={"gsc_property": "sc-domain:example.test"})
        with oneboard.app.app_context(), mock.patch.object(oneboard, "fetch_search_console_totals", return_value={}) as totals:
            oneboard.build_site_report(self.user_id, oneboard.get_current_workspace(self.user_id), "2024-02")
        self.assertEqual(totals.call_args.args[2:], ("2024-02-01", "2024-02-29"))


if __name__ == "__main__":
    unittest.main()
