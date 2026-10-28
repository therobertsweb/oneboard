import os
import sys
import tempfile
import unittest
from pathlib import Path


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-inbox-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-inbox-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "inbox-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


class InboxTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-inbox-workspace-")
        self.site = Path(self.workspace.name) / "inbox-site"
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
        email = f"inbox-{name.lower()}-{self.user_sequence}@example.test"
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

    def test_public_submit_and_attend_flow(self):
        token_row = self.client.post("/api/site-manager/inbox/token").get_json()
        token = token_row["token"]
        self.assertTrue(token_row["submit_url"].endswith(f"/forms/{token}/submit"))

        self.logout()
        submitted = self.client.post(
            f"/forms/{token}/submit",
            data={
                "name": "Juan",
                "email": "juan@example.test",
                "phone": "555-99",
                "message": "Quiero una cotización",
                "page": "/contacto",
            },
        )
        self.assertEqual(submitted.status_code, 200, submitted.get_data(as_text=True))
        self.assertEqual(submitted.headers.get("Access-Control-Allow-Origin"), "*")

        bad_token = self.client.post(f"/forms/{'y' * 64}/submit", data={"message": "x"})
        self.assertEqual(bad_token.status_code, 404)

        empty = self.client.post(f"/forms/{token}/submit", data={"message": "  "})
        self.assertEqual(empty.status_code, 400)

        self.login(self.owner_id)
        inbox = self.client.get("/api/site-manager/inbox").get_json()
        self.assertEqual(len(inbox["messages"]), 1)
        message = inbox["messages"][0]
        self.assertEqual(message["status"], "new")
        self.assertEqual(message["page"], "/contacto")
        self.assertEqual(message["email"], "juan@example.test")

        attended = self.client.post(f"/api/site-manager/inbox/{message['id']}/attend")
        self.assertEqual(attended.status_code, 200)
        self.assertEqual(attended.get_json()["message"]["status"], "attended")

        reopened = self.client.post(f"/api/site-manager/inbox/{message['id']}/reopen")
        self.assertEqual(reopened.status_code, 200)
        self.assertEqual(reopened.get_json()["message"]["status"], "new")

        deleted = self.client.delete(f"/api/site-manager/inbox/{message['id']}")
        self.assertEqual(deleted.status_code, 200)
        inbox = self.client.get("/api/site-manager/inbox").get_json()
        self.assertEqual(inbox["messages"], [])

    def test_json_submit_and_snippet(self):
        token = self.client.post("/api/site-manager/inbox/token").get_json()["token"]
        self.logout()
        submitted = self.client.post(
            f"/forms/{token}/submit",
            json={"name": "Ana", "email": "ana@example.test", "message": "Hola", "page": "/"},
        )
        self.assertEqual(submitted.status_code, 200, submitted.get_data(as_text=True))

        self.login(self.owner_id)
        snippet = self.client.get("/api/site-manager/inbox/snippet").get_json()["snippet"]
        self.assertIn(f"/forms/{token}/submit", snippet)
        self.assertIn('name="message"', snippet)

    def test_viewer_is_read_only(self):
        created = self.client.post("/api/teams", json={"name": "Inbox Team"})
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
        form_token = self.client.post("/api/site-manager/inbox/token").get_json()["token"]
        self.logout()
        self.client.post(
            f"/forms/{form_token}/submit",
            data={"name": "Lead", "message": "Interesado", "page": "/"},
        )

        self.login(self.viewer_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        team_project = next(item for item in manager["projects"] if item["scope"] == "team")
        self.client.post("/api/site-manager/connect", json={"project_id": team_project["id"]})

        listed = self.client.get("/api/site-manager/inbox")
        self.assertEqual(listed.status_code, 200)
        message_id = listed.get_json()["messages"][0]["id"]
        denied = self.client.post(f"/api/site-manager/inbox/{message_id}/attend")
        self.assertEqual(denied.status_code, 403)
        denied_token = self.client.post("/api/site-manager/inbox/token")
        self.assertEqual(denied_token.status_code, 403)

    def test_inbox_page_renders(self):
        page = self.client.get("/site-manager/inbox")
        self.assertEqual(page.status_code, 200, page.get_data(as_text=True))

    def test_token_revoke_via_api(self):
        created = self.client.post("/api/site-manager/inbox/token").get_json()
        token_id = self.client.get("/api/site-manager/inbox").get_json()["tokens"][0]["id"]
        revoked = self.client.delete(f"/api/site-manager/inbox/token/{token_id}")
        self.assertEqual(revoked.status_code, 200, revoked.get_data(as_text=True))
        self.logout()
        self.assertEqual(
            self.client.post(f"/forms/{created['token']}/submit", data={"message": "x"}).status_code,
            404,
        )
        self.login(self.owner_id)
        self.assertEqual(self.client.get("/api/site-manager/inbox/snippet").status_code, 404)


if __name__ == "__main__":
    unittest.main()
