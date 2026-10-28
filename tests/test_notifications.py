import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-notif-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-notif-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "notif-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


class NotificationTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-notif-workspace-")
        self.site = Path(self.workspace.name) / "notif-site"
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
        email = f"notif-{name.lower()}-{self.user_sequence}@example.test"
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

    def _share_with_viewer(self):
        created = self.client.post("/api/teams", json={"name": "Notif Team"})
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

    def _unread(self):
        return self.client.get("/api/notifications").get_json()

    def test_contact_submit_notifies_owner(self):
        token = self.client.post("/api/site-manager/inbox/token").get_json()["token"]
        self.logout()
        self.client.post(
            f"/forms/{token}/submit",
            data={"name": "Juan", "message": "Quiero info", "page": "/contacto"},
        )
        self.login(self.owner_id)
        payload = self._unread()
        self.assertEqual(payload["unread_count"], 1)
        item = payload["notifications"][0]
        self.assertEqual(item["kind"], "inbox")
        self.assertIn("/site-manager/inbox", item["link"])
        self.assertIn("Juan", item["title"])

    def test_request_and_comments_notify_watchers(self):
        self._share_with_viewer()
        link = self.client.post(
            "/api/site-manager/request-links", json={"label": "client"}
        ).get_json()["link"]
        token = link["url"].rstrip("/").rsplit("/", 1)[-1]
        self.logout()
        created = self.client.post(
            f"/r/{token}/requests",
            data={"client_name": "María", "message": "Change headline", "page": "index.html"},
        )
        request_id = created.get_json()["request"]["id"]

        self.login(self.owner_id)
        payload = self._unread()
        self.assertEqual(payload["unread_count"], 1)
        self.assertEqual(payload["notifications"][0]["kind"], "request")
        self.assertIn(f"/site-manager/requests/{request_id}", payload["notifications"][0]["link"])

        self.login(self.viewer_id)
        viewer_payload = self._unread()
        self.assertEqual(viewer_payload["unread_count"], 1)

        # agency comment by owner notifies the teammate, not the author again
        self.login(self.owner_id)
        self.client.post(
            f"/api/site-manager/requests/{request_id}/comments", json={"body": "On it"}
        )
        self.assertEqual(self._unread()["unread_count"], 1)
        self.login(self.viewer_id)
        self.assertEqual(self._unread()["unread_count"], 2)

        # client comment notifies both watchers
        self.logout()
        self.client.post(
            f"/r/{token}/requests/{request_id}/comments",
            data={"author_name": "María", "body": "Thanks!"},
        )
        self.login(self.owner_id)
        self.assertEqual(self._unread()["unread_count"], 2)

    def test_alert_open_notifies_once_until_resolved(self):
        self.client.post(
            "/api/site-manager/alerts/rules",
            json={"kind": "uptime", "target": "https://example.test/"},
        )
        with mock.patch.object(oneboard, "check_site_uptime", return_value=(False, "boom")):
            self.client.post("/api/site-manager/alerts/check")
            self.client.post("/api/site-manager/alerts/check")
        payload = self._unread()
        kinds = [item["kind"] for item in payload["notifications"]]
        self.assertEqual(kinds.count("alert"), 1)
        self.assertIn("/site-manager/alerts", payload["notifications"][0]["link"])

    def test_publish_failure_notifies(self):
        with oneboard.app.app_context():
            oneboard.record_publish_alert(self.owner_id, "ssh: connection refused")
        payload = self._unread()
        self.assertEqual(payload["unread_count"], 1)
        self.assertEqual(payload["notifications"][0]["kind"], "alert")

    def test_read_and_read_all(self):
        token = self.client.post("/api/site-manager/inbox/token").get_json()["token"]
        self.logout()
        self.client.post(f"/forms/{token}/submit", data={"message": "one", "page": "/"})
        self.client.post(f"/forms/{token}/submit", data={"message": "two", "page": "/"})
        self.login(self.owner_id)
        payload = self._unread()
        self.assertEqual(payload["unread_count"], 2)

        first = payload["notifications"][0]["id"]
        read = self.client.post(f"/api/notifications/{first}/read")
        self.assertEqual(read.status_code, 200)
        self.assertEqual(read.get_json()["unread_count"], 1)

        read_all = self.client.post("/api/notifications/read-all")
        self.assertEqual(read_all.status_code, 200)
        self.assertEqual(read_all.get_json()["unread_count"], 0)

        # another user cannot mark it read
        self.login(self.viewer_id)
        denied = self.client.post(f"/api/notifications/{first}/read")
        self.assertEqual(denied.status_code, 404)
        self.assertEqual(self._unread()["unread_count"], 0)

    def test_notifications_page_renders_with_badge(self):
        token = self.client.post("/api/site-manager/inbox/token").get_json()["token"]
        self.logout()
        self.client.post(f"/forms/{token}/submit", data={"message": "hey", "page": "/"})
        self.login(self.owner_id)
        page = self.client.get("/notifications")
        self.assertEqual(page.status_code, 200, page.get_data(as_text=True))
        body = page.get_data(as_text=True)
        self.assertIn("nav-badge", body)


if __name__ == "__main__":
    unittest.main()
