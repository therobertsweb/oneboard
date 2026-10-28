import os
import socket
import ssl
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-alerts-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-alerts-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "alerts-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


class AlertsTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-alerts-workspace-")
        self.site = Path(self.workspace.name) / "alerts-site"
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
        email = f"alerts-{name.lower()}-{self.user_sequence}@example.test"
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

    def _create_rule(self, kind="uptime", target="https://example.test/", **kwargs):
        payload = {"kind": kind, "target": target, "name": kwargs.pop("name", "")}
        payload.update(kwargs)
        response = self.client.post("/api/site-manager/alerts/rules", json=payload)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["rule"]

    def test_uptime_down_and_recovery(self):
        self._create_rule()

        failure = OSError("unreachable")
        with mock.patch.object(oneboard, "check_site_uptime", return_value=(False, "unreachable")):
            checked = self.client.post("/api/site-manager/alerts/check")
        self.assertEqual(checked.status_code, 200, checked.get_data(as_text=True))
        alerts = checked.get_json()["alerts"]
        open_alerts = [item for item in alerts if item["status"] == "open"]
        self.assertEqual(len(open_alerts), 1)
        self.assertEqual(open_alerts[0]["kind"], "uptime")

        with mock.patch.object(oneboard, "check_site_uptime", return_value=(False, "unreachable")):
            checked = self.client.post("/api/site-manager/alerts/check")
        open_alerts = [item for item in checked.get_json()["alerts"] if item["status"] == "open"]
        self.assertEqual(len(open_alerts), 1)

        with mock.patch.object(oneboard, "check_site_uptime", return_value=(True, "HTTP 200")):
            checked = self.client.post("/api/site-manager/alerts/check")
        open_alerts = [item for item in checked.get_json()["alerts"] if item["status"] == "open"]
        self.assertEqual(open_alerts, [])

    def test_tls_expiry_warning(self):
        soon = datetime.now(timezone.utc) + timedelta(days=5)
        self._create_rule(kind="tls", target="example.test")
        with mock.patch.object(oneboard, "get_tls_expiry", return_value=soon):
            checked = self.client.post("/api/site-manager/alerts/check")
        self.assertEqual(checked.status_code, 200, checked.get_data(as_text=True))
        open_alerts = [item for item in checked.get_json()["alerts"] if item["status"] == "open"]
        self.assertEqual(len(open_alerts), 1)
        self.assertIn("5", open_alerts[0]["detail"])

        later = datetime.now(timezone.utc) + timedelta(days=90)
        with mock.patch.object(oneboard, "get_tls_expiry", return_value=later):
            checked = self.client.post("/api/site-manager/alerts/check")
        open_alerts = [item for item in checked.get_json()["alerts"] if item["status"] == "open"]
        self.assertEqual(open_alerts, [])

    def test_publish_failure_creates_alert(self):
        with oneboard.app.app_context():
            oneboard.record_publish_alert(self.owner_id, "ssh: connection refused")
            workspace = oneboard.get_current_workspace(self.owner_id)
            rows = oneboard.query_db(
                "SELECT kind, status FROM site_alerts WHERE workspace_id = ?",
                (workspace["id"],),
            )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["kind"], "publish")
        self.assertEqual(rows[0]["status"], "open")

    def test_ack_resolve_and_rule_toggle(self):
        rule = self._create_rule()
        with mock.patch.object(oneboard, "check_site_uptime", return_value=(False, "boom")):
            checked = self.client.post("/api/site-manager/alerts/check").get_json()
        alert_id = next(item["id"] for item in checked["alerts"] if item["status"] == "open")

        acked = self.client.post(f"/api/site-manager/alerts/{alert_id}/ack")
        self.assertEqual(acked.status_code, 200)
        self.assertEqual(
            next(item for item in acked.get_json()["alerts"] if item["id"] == alert_id)["status"],
            "acked",
        )
        resolved = self.client.post(f"/api/site-manager/alerts/{alert_id}/resolve")
        self.assertEqual(resolved.status_code, 200)

        disabled = self.client.post(
            f"/api/site-manager/alerts/rules/{rule['id']}", json={"enabled": False}
        )
        self.assertEqual(disabled.status_code, 200)
        with mock.patch.object(oneboard, "check_site_uptime", return_value=(False, "boom")):
            checked = self.client.post("/api/site-manager/alerts/check").get_json()
        self.assertEqual(
            [item for item in checked["alerts"] if item["status"] == "open"], []
        )
        deleted = self.client.delete(f"/api/site-manager/alerts/rules/{rule['id']}")
        self.assertEqual(deleted.status_code, 200)

    def test_viewer_is_read_only(self):
        created = self.client.post("/api/teams", json={"name": "Alerts Team"})
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

        listed = self.client.get("/api/site-manager/alerts")
        self.assertEqual(listed.status_code, 200)
        denied = self.client.post(
            "/api/site-manager/alerts/rules",
            json={"kind": "uptime", "target": "https://x.test/"},
        )
        self.assertEqual(denied.status_code, 403)

    def test_alerts_page_renders(self):
        page = self.client.get("/site-manager/alerts")
        self.assertEqual(page.status_code, 200, page.get_data(as_text=True))

    def test_ack_then_reopen_via_api(self):
        self._create_rule()
        with mock.patch.object(oneboard, "check_site_uptime", return_value=(False, "boom")):
            checked = self.client.post("/api/site-manager/alerts/check").get_json()
        alert_id = next(item["id"] for item in checked["alerts"] if item["status"] == "open")
        self.client.post(f"/api/site-manager/alerts/{alert_id}/ack")
        reopened = self.client.post(f"/api/site-manager/alerts/{alert_id}/reopen")
        self.assertEqual(reopened.status_code, 200, reopened.get_data(as_text=True))
        self.assertEqual(
            next(item for item in reopened.get_json()["alerts"] if item["id"] == alert_id)["status"],
            "open",
        )


if __name__ == "__main__":
    unittest.main()
