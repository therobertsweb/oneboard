import os
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-reports-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-reports-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "reports-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


class ReportsTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-reports-workspace-")
        self.site = Path(self.workspace.name) / "reports-site"
        self.site.mkdir()
        (self.site / "index.html").write_text("<html><body>Hi</body></html>", encoding="utf-8")

        oneboard.app.config.update(TESTING=True)
        self.owner_id = self._create_user("Owner")
        self.viewer_id = self._create_user("Viewer")
        self.client = oneboard.app.test_client()
        self.login(self.owner_id)
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})

    def tearDown(self):
        self.workspace.cleanup()

    def _create_user(self, name):
        type(self).user_sequence += 1
        email = f"reports-{name.lower()}-{self.user_sequence}@example.test"
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

    def logout(self):
        with self.client.session_transaction() as session:
            session.clear()

    def test_report_link_and_public_summary(self):
        month = date.today().strftime("%Y-%m")
        with oneboard.app.app_context():
            real = os.path.realpath(str(self.site))
            oneboard.execute_db(
                """INSERT INTO website_update_history
                   (user_id, source, summary, exit_code, status, directory_path, created_at)
                   VALUES (?, 'codex', 'June hero update', '0', 'approved', ?, ?)""",
                (self.owner_id, real, f"{month}-10 12:00:00"),
            )
            workspace = oneboard.get_current_workspace(self.owner_id)
            oneboard.execute_db(
                """INSERT INTO contact_messages
                   (workspace_id, page, name, email, message, status, created_at)
                   VALUES (?, '/contacto', 'Lead', 'l@t.t', 'Hola', 'attended', ?)""",
                (workspace["id"], f"{month}-11 12:00:00"),
            )
            oneboard.execute_db(
                """INSERT INTO site_findings
                   (user_id, directory_path, fingerprint, check_type, severity, page, status,
                    resolved_by, resolved_at, created_at)
                   VALUES (?, ?, 'fp1', 'missing_title', 'warning', 'index.html',
                           'resolved', 'fix', ?, ?)""",
                (self.owner_id, real, f"{month}-12 12:00:00", f"{month}-09 12:00:00"),
            )

        created = self.client.post("/api/site-manager/reports", json={"period": month})
        self.assertEqual(created.status_code, 200, created.get_data(as_text=True))
        link = created.get_json()["link"]
        token = link["url"].rstrip("/").rsplit("/", 1)[-1]

        summary = self.client.get(f"/api/site-manager/reports/{link['id']}").get_json()["report"]
        self.assertEqual(summary["period"], month)
        self.assertEqual(summary["changes_count"], 1)
        self.assertEqual(summary["inquiries_count"], 1)
        self.assertEqual(summary["issues_resolved"], 1)
        self.assertIn("June hero update", summary["changes"][0]["summary"])

        self.logout()
        public = self.client.get(f"/reports/{token}")
        self.assertEqual(public.status_code, 200, public.get_data(as_text=True))
        body = public.get_data(as_text=True)
        self.assertIn("June hero update", body)

        self.login(self.owner_id)
        revoked = self.client.delete(f"/api/site-manager/reports/{link['id']}")
        self.assertEqual(revoked.status_code, 200)
        self.logout()
        self.assertEqual(self.client.get(f"/reports/{token}").status_code, 404)

    def test_visits_from_search_console(self):
        month = date.today().strftime("%Y-%m")
        created = self.client.post("/api/site-manager/reports", json={"period": month})
        link = created.get_json()["link"]
        with mock.patch.object(
            oneboard, "fetch_search_console_totals",
            return_value={"clicks": 120, "impressions": 3400, "ctr": 3.5, "position": 8.2},
        ):
            summary = self.client.get(f"/api/site-manager/reports/{link['id']}").get_json()["report"]
        self.assertEqual(summary["visits"]["clicks"], 120)
        self.assertEqual(summary["visits"]["impressions"], 3400)

    def test_link_management_requires_manage(self):
        created = self.client.post("/api/teams", json={"name": "Reports Team"})
        team_id = created.get_json()["team"]["id"]
        invite = self.client.post(
            f"/api/teams/{team_id}/invites",
            json={"email": self._email_of(self.viewer_id), "role": "viewer"},
        ).get_json()
        token = invite["invite_link"].rstrip("/").rsplit("/", 1)[-1]
        self.login(self.viewer_id)
        self.client.post("/api/teams/invites/accept", json={"token": token})

        self.login(self.owner_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        project_id = next(item["id"] for item in manager["projects"] if item["is_current"])
        self.client.post(f"/api/teams/{team_id}/projects", json={"project_id": project_id})

        self.login(self.viewer_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        team_project = next(item for item in manager["projects"] if item["scope"] == "team")
        self.client.post("/api/site-manager/connect", json={"project_id": team_project["id"]})

        listed = self.client.get("/api/site-manager/reports")
        self.assertEqual(listed.status_code, 200)
        denied = self.client.post(
            "/api/site-manager/reports", json={"period": date.today().strftime("%Y-%m")}
        )
        self.assertEqual(denied.status_code, 403)

    def test_reports_page_renders(self):
        page = self.client.get("/site-manager/reports")
        self.assertEqual(page.status_code, 200, page.get_data(as_text=True))

    def test_public_report_json_format(self):
        month = date.today().strftime("%Y-%m")
        with oneboard.app.app_context():
            real = os.path.realpath(str(self.site))
            oneboard.execute_db(
                """INSERT INTO website_update_history
                   (user_id, source, summary, exit_code, status, directory_path, created_at)
                   VALUES (?, 'codex', 'JSON hero update', '0', 'approved', ?, ?)""",
                (self.owner_id, real, f"{month}-10 12:00:00"),
            )
        created = self.client.post("/api/site-manager/reports", json={"period": month})
        token = created.get_json()["link"]["url"].rstrip("/").rsplit("/", 1)[-1]
        self.logout()
        payload = self.client.get(f"/reports/{token}?format=json")
        self.assertEqual(payload.status_code, 200, payload.get_data(as_text=True))
        report = payload.get_json()["report"]
        self.assertEqual(report["period"], month)
        self.assertIn("JSON hero update", report["changes"][0]["summary"])


if __name__ == "__main__":
    unittest.main()
