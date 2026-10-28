import os
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-calendar-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-calendar-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "calendar-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


class CalendarTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-calendar-workspace-")
        self.site = Path(self.workspace.name) / "cal-site"
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
        email = f"cal-{name.lower()}-{self.user_sequence}@example.test"
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

    def test_event_crud_and_status(self):
        today = date.today()
        created = self.client.post(
            "/api/site-manager/calendar",
            json={
                "kind": "promo",
                "title": "Summer sale",
                "brief": "Add a 20% banner on the homepage",
                "starts_on": (today + timedelta(days=1)).isoformat(),
                "ends_on": (today + timedelta(days=8)).isoformat(),
            },
        )
        self.assertEqual(created.status_code, 200, created.get_data(as_text=True))
        event = created.get_json()["event"]
        self.assertEqual(event["status"], "scheduled")
        self.assertEqual(event["kind"], "promo")

        active = self.client.post(
            "/api/site-manager/calendar",
            json={
                "kind": "prices",
                "title": "New rates",
                "starts_on": (today - timedelta(days=1)).isoformat(),
                "ends_on": (today + timedelta(days=1)).isoformat(),
            },
        ).get_json()["event"]
        self.assertEqual(active["status"], "active")

        listed = self.client.get("/api/site-manager/calendar").get_json()["events"]
        self.assertEqual(len(listed), 2)

        updated = self.client.post(
            f"/api/site-manager/calendar/{event['id']}",
            json={"title": "Summer mega sale"},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["event"]["title"], "Summer mega sale")

        cancelled = self.client.post(
            f"/api/site-manager/calendar/{event['id']}/cancel"
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.get_json()["event"]["status"], "cancelled")

        deleted = self.client.delete(f"/api/site-manager/calendar/{event['id']}")
        self.assertEqual(deleted.status_code, 200)
        listed = self.client.get("/api/site-manager/calendar").get_json()["events"]
        self.assertEqual(len(listed), 1)

    def test_execute_event_runs_site_update(self):
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.owner_id),
            )
        today = date.today()
        event = self.client.post(
            "/api/site-manager/calendar",
            json={
                "kind": "blog",
                "title": "Launch post",
                "brief": "Write a launch paragraph on the homepage",
                "starts_on": today.isoformat(),
            },
        ).get_json()["event"]
        ai_response = {
            "summary": "Added launch paragraph.",
            "files": [{"path": "index.html", "content": "<html><body>Launch!</body></html>"}],
        }
        with mock.patch.object(
            oneboard, "run_ai_provider_prompt",
            return_value=(oneboard.json.dumps(ai_response), {}, "muse-text-1.0"),
        ) as provider, mock.patch.object(
            oneboard, "get_muse_models", return_value=["muse-text-1.0"]
        ):
            executed = self.client.post(f"/api/site-manager/calendar/{event['id']}/execute")
        self.assertEqual(executed.status_code, 200, executed.get_data(as_text=True))
        self.assertIn("launch paragraph", provider.call_args.args[3])
        body = executed.get_json()
        self.assertEqual(body["event"]["status"], "done")
        self.assertTrue(body["event"]["update_id"])

    def test_viewer_is_read_only(self):
        created = self.client.post("/api/teams", json={"name": "Cal Team"})
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
        self.client.post(
            "/api/site-manager/calendar",
            json={"kind": "note", "title": "Shared plan", "starts_on": date.today().isoformat()},
        )

        self.login(self.viewer_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        team_project = next(item for item in manager["projects"] if item["scope"] == "team")
        self.client.post("/api/site-manager/connect", json={"project_id": team_project["id"]})

        listed = self.client.get("/api/site-manager/calendar")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.get_json()["events"]), 1)

        denied = self.client.post(
            "/api/site-manager/calendar", json={"kind": "note", "title": "x"}
        )
        self.assertEqual(denied.status_code, 403)

    def test_calendar_page_renders(self):
        page = self.client.get("/site-manager/calendar")
        self.assertEqual(page.status_code, 200, page.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
