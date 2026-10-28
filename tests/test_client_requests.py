import io as io_module
import os
import sys
import tempfile
import unittest
from pathlib import Path


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-requests-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-requests-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "requests-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


class ClientRequestsTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-requests-workspace-")
        self.workspace_path = Path(self.workspace.name)
        self.site = self.workspace_path / "request-site"
        self.site.mkdir()
        (self.site / "index.html").write_text(
            "<html><body><h1>Client site</h1></body></html>", encoding="utf-8"
        )

        oneboard.app.config.update(TESTING=True)
        self.owner_id = self._create_user("Owner")
        self.editor_id = self._create_user("Editor")
        self.client = oneboard.app.test_client()
        self.login(self.owner_id)
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})

    def tearDown(self):
        self.workspace.cleanup()

    def _create_user(self, name):
        type(self).user_sequence += 1
        email = f"requests-{name.lower()}-{self.user_sequence}@example.test"
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

    def _create_link(self, label="Homepage review"):
        response = self.client.post("/api/site-manager/request-links", json={"label": label})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["link"]

    def _token_from_url(self, url):
        return url.rstrip("/").rsplit("/", 1)[-1]

    def test_link_portal_and_visibility(self):
        link = self._create_link()
        token = self._token_from_url(link["url"])

        self.logout()
        portal = self.client.get(f"/r/{token}")
        self.assertEqual(portal.status_code, 200, portal.get_data(as_text=True))
        self.assertIn("Client site", self.client.get(f"/r/{token}/preview/index.html").get_data(as_text=True))

        missing = self.client.get("/r/" + "x" * 64)
        self.assertEqual(missing.status_code, 404)

        self.login(self.owner_id)
        revoked = self.client.delete(f"/api/site-manager/request-links/{link['id']}")
        self.assertEqual(revoked.status_code, 200)
        self.logout()
        self.assertEqual(self.client.get(f"/r/{token}").status_code, 404)

    def test_client_creates_request_with_attachment(self):
        link = self._create_link()
        token = self._token_from_url(link["url"])
        self.logout()

        created = self.client.post(
            f"/r/{token}/requests",
            data={
                "client_name": "María",
                "message": "Change this headline to red",
                "page": "index.html",
                "selector": "body > h1",
                "tag": "h1",
                "text": "Client site",
                "attachment": (io_module.BytesIO(PNG_BYTES), "shot.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(created.status_code, 200, created.get_data(as_text=True))
        payload = created.get_json()["request"]
        self.assertEqual(payload["status"], "open")
        self.assertEqual(payload["client_name"], "María")
        self.assertEqual(len(payload["attachments"]), 1)

        thread = self.client.get(f"/r/{token}/requests/{payload['id']}")
        self.assertEqual(thread.status_code, 200)
        self.assertIn("Change this headline", thread.get_data(as_text=True))

        served = self.client.get(f"/r/{token}/attachments/{payload['attachments'][0]['filename']}")
        self.assertEqual(served.status_code, 200)
        self.assertEqual(served.get_data(), PNG_BYTES)

        self.login(self.owner_id)
        listed = self.client.get("/api/site-manager/requests").get_json()
        self.assertEqual(len(listed["requests"]), 1)
        self.assertEqual(listed["requests"][0]["message"], "Change this headline to red")

    def test_review_propose_approve_flow(self):
        link = self._create_link()
        token = self._token_from_url(link["url"])
        self.logout()
        created = self.client.post(
            f"/r/{token}/requests",
            data={"client_name": "María", "message": "Bigger logo", "page": "index.html", "selector": "img"},
            content_type="multipart/form-data",
        )
        request_id = created.get_json()["request"]["id"]

        self.login(self.owner_id)
        review = self.client.post(
            f"/api/site-manager/requests/{request_id}/status",
            json={"status": "in_review"},
        )
        self.assertEqual(review.status_code, 200)
        proposed = self.client.post(
            f"/api/site-manager/requests/{request_id}/status",
            json={"status": "proposed", "proposal": "Logo at 200px, see staging."},
        )
        self.assertEqual(proposed.status_code, 200, proposed.get_data(as_text=True))
        self.assertEqual(proposed.get_json()["request"]["status"], "proposed")

        comment = self.client.post(
            f"/api/site-manager/requests/{request_id}/comments",
            json={"body": "Ready for your review."},
        )
        self.assertEqual(comment.status_code, 200)

        self.logout()
        approved = self.client.post(f"/r/{token}/requests/{request_id}/approve")
        self.assertEqual(approved.status_code, 200, approved.get_data(as_text=True))
        self.assertEqual(approved.get_json()["request"]["status"], "approved")

        client_comment = self.client.post(
            f"/r/{token}/requests/{request_id}/comments",
            data={"client_name": "María", "body": "Looks great!"},
            content_type="multipart/form-data",
        )
        self.assertEqual(client_comment.status_code, 200)

        self.login(self.owner_id)
        thread = self.client.get(f"/api/site-manager/requests/{request_id}").get_json()
        bodies = [item["body"] for item in thread["comments"]]
        self.assertIn("Ready for your review.", bodies)
        self.assertIn("Looks great!", bodies)
        done = self.client.post(
            f"/api/site-manager/requests/{request_id}/status", json={"status": "done"}
        )
        self.assertEqual(done.status_code, 200)

        self.logout()
        rejected = self.client.post(f"/r/{token}/requests/{request_id}/approve")
        self.assertEqual(rejected.status_code, 400)

    def test_link_management_requires_manage(self):
        created = self.client.post("/api/teams", json={"name": "Request Team"})
        team_id = created.get_json()["team"]["id"]
        invite = self.client.post(
            f"/api/teams/{team_id}/invites",
            json={"email": self._email_of(self.editor_id), "role": "editor"},
        ).get_json()
        token = self._token_from_url(invite["invite_link"])
        self.login(self.editor_id)
        self.client.post("/api/teams/invites/accept", json={"token": token})

        self.login(self.owner_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        project_id = next(item["id"] for item in manager["projects"] if item["is_current"])
        self.client.post(f"/api/teams/{team_id}/projects", json={"project_id": project_id})
        link = self._create_link()

        self.login(self.editor_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        team_project = next(item for item in manager["projects"] if item["scope"] == "team")
        self.client.post("/api/site-manager/connect", json={"project_id": team_project["id"]})

        denied = self.client.post("/api/site-manager/request-links", json={"label": "x"})
        self.assertEqual(denied.status_code, 403)
        denied_revoke = self.client.delete(f"/api/site-manager/request-links/{link['id']}")
        self.assertEqual(denied_revoke.status_code, 403)

        listed = self.client.get("/api/site-manager/requests")
        self.assertEqual(listed.status_code, 200)

    def test_agency_pages_render(self):
        self._create_link()
        listed = self.client.get("/site-manager/requests")
        self.assertEqual(listed.status_code, 200, listed.get_data(as_text=True))

    def test_sidebar_shortcuts_and_badges(self):
        dashboard = self.client.get("/dashboard").get_data(as_text=True)
        for href in (
            'href="/site-manager?tab=preview"',
            'href="/site-manager/site"',
            'href="/site-manager/health"',
            'href="/site-manager/requests"',
        ):
            self.assertIn(href, dashboard)
        self.assertNotIn("nav-badge", dashboard)

        link = self._create_link()
        token = self._token_from_url(link["url"])
        self.logout()
        created = self.client.post(
            f"/r/{token}/requests",
            data={"client_name": "María", "message": "Hi", "page": "", "selector": ""},
            content_type="multipart/form-data",
        )
        self.assertEqual(created.status_code, 200)
        self.login(self.owner_id)
        dashboard = self.client.get("/dashboard").get_data(as_text=True)
        self.assertIn('<span class="nav-badge">1</span>', dashboard)

        studio = self.client.get("/site-manager?tab=preview")
        self.assertEqual(studio.status_code, 200)
        self.assertIn('data-active-tab="preview"', studio.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
