import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-teams-tests-")
TEST_HOME = tempfile.TemporaryDirectory(prefix="oneboard-teams-home-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["HOME"] = TEST_HOME.name
os.environ["SECRET_KEY"] = "teams-test-secret"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app as oneboard


class TeamsTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()
        TEST_HOME.cleanup()

    def setUp(self):
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-teams-workspace-")
        self.workspace_path = Path(self.workspace.name)
        self.site = self.workspace_path / "team-site"
        self.site.mkdir()
        (self.site / "index.html").write_text("team-original", encoding="utf-8")

        oneboard.app.config.update(TESTING=True)
        self.owner_id = self._create_user("Owner")
        self.editor_id = self._create_user("Editor")
        self.viewer_id = self._create_user("Viewer")
        self.client = oneboard.app.test_client()
        self.login(self.owner_id)

    def tearDown(self):
        self.workspace.cleanup()

    def _create_user(self, name):
        type(self).user_sequence += 1
        email = f"{name.lower()}-{self.user_sequence}@example.test"
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

    def _create_team(self, name="Agencia Web"):
        response = self.client.post("/api/teams", json={"name": name})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["team"]

    def _invite(self, team_id, email, role="editor"):
        response = self.client.post(
            f"/api/teams/{team_id}/invites", json={"email": email, "role": role}
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def _accept(self, invite_link):
        token = invite_link.rstrip("/").rsplit("/", 1)[-1]
        response = self.client.post("/api/teams/invites/accept", json={"token": token})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["team"]

    def _team_detail(self, team_id):
        response = self.client.get(f"/api/teams/{team_id}")
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()

    def test_create_team_invite_and_accept(self):
        team = self._create_team()
        self.assertEqual(team["name"], "Agencia Web")
        self.assertEqual(team["my_role"], "owner")

        invite = self._invite(team["id"], self._email_of(self.editor_id), "editor")
        self.assertIn("invite_link", invite)
        self.assertIn("/teams/invites/", invite["invite_link"])

        self.login(self.editor_id)
        joined = self._accept(invite["invite_link"])
        self.assertEqual(joined["id"], team["id"])

        detail = self._team_detail(team["id"])
        emails = {member["email"] for member in detail["members"]}
        self.assertEqual(
            emails, {self._email_of(self.owner_id), self._email_of(self.editor_id)}
        )
        editor = next(m for m in detail["members"] if m["email"] == self._email_of(self.editor_id))
        self.assertEqual(editor["role"], "editor")
        self.assertTrue(editor["permissions"]["edit"])
        self.assertFalse(editor["permissions"]["publish"])

    def test_team_projects_are_shared_with_members(self):
        team = self._create_team()
        invite = self._invite(team["id"], self._email_of(self.editor_id), "editor")
        self.login(self.editor_id)
        self._accept(invite["invite_link"])

        self.login(self.owner_id)
        connected = self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        self.assertEqual(connected.status_code, 200, connected.get_data(as_text=True))
        project_id = next(
            item["id"]
            for item in connected.get_json()["manager"]["projects"]
            if item["path"] == str(self.site.resolve())
        )
        shared = self.client.post(
            f"/api/teams/{team['id']}/projects", json={"project_id": project_id}
        )
        self.assertEqual(shared.status_code, 200, shared.get_data(as_text=True))

        self.login(self.editor_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        team_projects = [item for item in manager["projects"] if item["scope"] == "team"]
        self.assertEqual(len(team_projects), 1)
        self.assertEqual(team_projects[0]["team_name"], "Agencia Web")
        self.assertTrue(team_projects[0]["permissions"]["edit"])

        opened = self.client.post(
            "/api/site-manager/connect", json={"project_id": team_projects[0]["id"]}
        )
        self.assertEqual(opened.status_code, 200, opened.get_data(as_text=True))
        context = opened.get_json()["manager"]["team_context"]
        self.assertEqual(context["team"]["id"], team["id"])
        self.assertEqual(context["role"], "editor")

    def test_viewer_is_read_only_on_team_projects(self):
        team = self._create_team()
        invite = self._invite(team["id"], self._email_of(self.viewer_id), "viewer")
        self.login(self.viewer_id)
        self._accept(invite["invite_link"])

        self.login(self.owner_id)
        connected = self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        project_id = next(
            item["id"]
            for item in connected.get_json()["manager"]["projects"]
            if item["path"] == str(self.site.resolve())
        )
        self.client.post(f"/api/teams/{team['id']}/projects", json={"project_id": project_id})

        self.login(self.viewer_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        team_project = next(item for item in manager["projects"] if item["scope"] == "team")
        opened = self.client.post(
            "/api/site-manager/connect", json={"project_id": team_project["id"]}
        )
        self.assertEqual(opened.status_code, 200, opened.get_data(as_text=True))

        readable = self.client.get(
            "/api/site-manager/files/raw", query_string={"path": "index.html"}
        )
        self.assertEqual(readable.status_code, 200)
        self.assertEqual(readable.get_data(as_text=True), "team-original")

        denied = self.client.post(
            "/api/site-manager/files/delete", json={"path": "index.html"}
        )
        self.assertEqual(denied.status_code, 403, denied.get_data(as_text=True))
        self.assertTrue((self.site / "index.html").exists())

    def test_editor_can_edit_but_not_publish(self):
        team = self._create_team()
        invite = self._invite(team["id"], self._email_of(self.editor_id), "editor")
        self.login(self.editor_id)
        self._accept(invite["invite_link"])

        self.login(self.owner_id)
        connected = self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        project_id = next(
            item["id"]
            for item in connected.get_json()["manager"]["projects"]
            if item["path"] == str(self.site.resolve())
        )
        self.client.post(f"/api/teams/{team['id']}/projects", json={"project_id": project_id})

        self.login(self.editor_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        team_project = next(item for item in manager["projects"] if item["scope"] == "team")
        self.client.post("/api/site-manager/connect", json={"project_id": team_project["id"]})

        (self.site / "draft.txt").write_text("draft", encoding="utf-8")
        deleted = self.client.post(
            "/api/site-manager/files/delete", json={"path": "draft.txt"}
        )
        self.assertEqual(deleted.status_code, 200, deleted.get_data(as_text=True))
        self.assertFalse((self.site / "draft.txt").exists())

        publish = self.client.post(
            "/api/site-manager/remote",
            json={"host": "example.com", "username": "deploy", "remote_path": "/srv/site"},
        )
        self.assertEqual(publish.status_code, 403, publish.get_data(as_text=True))

    def test_custom_permissions_can_grant_publish(self):
        team = self._create_team()
        invite = self._invite(team["id"], self._email_of(self.editor_id), "editor")
        self.login(self.editor_id)
        self._accept(invite["invite_link"])

        self.login(self.owner_id)
        updated = self.client.post(
            f"/api/teams/{team['id']}/members/{self.editor_id}",
            json={"permissions": {"publish": True}},
        )
        self.assertEqual(updated.status_code, 200, updated.get_data(as_text=True))
        member = next(
            item for item in updated.get_json()["members"] if item["id"] == self.editor_id
        )
        self.assertEqual(member["role"], "custom")
        self.assertTrue(member["permissions"]["publish"])
        self.assertTrue(member["permissions"]["edit"])

        detail = self._team_detail(team["id"])
        member = next(item for item in detail["members"] if item["id"] == self.editor_id)
        self.assertTrue(member["permissions"]["publish"])

    def test_chat_and_history_are_shared_on_team_projects(self):
        team = self._create_team()
        invite = self._invite(team["id"], self._email_of(self.editor_id), "editor")
        self.login(self.editor_id)
        self._accept(invite["invite_link"])

        self.login(self.owner_id)
        self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        project_id = next(
            item["id"] for item in manager["projects"] if item["path"] == str(self.site.resolve())
        )
        self.client.post(f"/api/teams/{team['id']}/projects", json={"project_id": project_id})
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.owner_id),
            )
        ai_response = {
            "summary": "Touched by owner.",
            "files": [{"path": "index.html", "content": "<html><body>Team</body></html>"}],
        }
        with mock.patch.object(
            oneboard,
            "run_ai_provider_prompt",
            return_value=(oneboard.json.dumps(ai_response), {"total_tokens": 5}, "muse-text-1.0"),
        ), mock.patch.object(
            oneboard, "get_muse_models", return_value=["muse-text-1.0"]
        ):
            update = self.client.post(
                "/api/site-manager/codex-update", json={"prompt": "Touch team site"}
            )
        self.assertEqual(update.status_code, 200, update.get_data(as_text=True))

        self.login(self.editor_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        team_project = next(item for item in manager["projects"] if item["scope"] == "team")
        opened = self.client.post(
            "/api/site-manager/connect", json={"project_id": team_project["id"]}
        )
        body = opened.get_json()["manager"]
        self.assertEqual(len(body["codex_messages"]), 2)
        self.assertEqual(len(body["updates"]), 1)
        self.assertEqual(body["updates"][0]["summary"], "Touched by owner.")

    def test_non_member_cannot_open_team_project_path(self):
        team = self._create_team()
        self.login(self.owner_id)
        connected = self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        project_id = next(
            item["id"]
            for item in connected.get_json()["manager"]["projects"]
            if item["path"] == str(self.site.resolve())
        )
        self.client.post(f"/api/teams/{team['id']}/projects", json={"project_id": project_id})

        outsider_id = self._create_user("Outsider")
        self.login(outsider_id)
        denied = self.client.post(
            "/api/site-manager/connect", json={"path": str(self.site)}
        )
        self.assertEqual(denied.status_code, 403, denied.get_data(as_text=True))
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        self.assertEqual([item for item in manager["projects"] if item["scope"] == "team"], [])

    def test_removed_member_loses_access(self):
        team = self._create_team()
        invite = self._invite(team["id"], self._email_of(self.editor_id), "editor")
        self.login(self.editor_id)
        self._accept(invite["invite_link"])

        self.login(self.owner_id)
        connected = self.client.post("/api/site-manager/connect", json={"path": str(self.site)})
        project_id = next(
            item["id"]
            for item in connected.get_json()["manager"]["projects"]
            if item["path"] == str(self.site.resolve())
        )
        self.client.post(f"/api/teams/{team['id']}/projects", json={"project_id": project_id})
        removed = self.client.delete(f"/api/teams/{team['id']}/members/{self.editor_id}")
        self.assertEqual(removed.status_code, 200, removed.get_data(as_text=True))

        self.login(self.editor_id)
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        self.assertEqual([item for item in manager["projects"] if item["scope"] == "team"], [])
        denied = self.client.post(
            "/api/site-manager/connect", json={"path": str(self.site)}
        )
        self.assertEqual(denied.status_code, 403, denied.get_data(as_text=True))

    def test_owner_is_protected(self):
        team = self._create_team()
        invite = self._invite(team["id"], self._email_of(self.editor_id), "admin")
        self.login(self.editor_id)
        self._accept(invite["invite_link"])

        self.login(self.editor_id)
        forbidden = self.client.delete(f"/api/teams/{team['id']}/members/{self.owner_id}")
        self.assertEqual(forbidden.status_code, 403, forbidden.get_data(as_text=True))

        self.login(self.owner_id)
        cannot_leave = self.client.post(f"/api/teams/{team['id']}/leave")
        self.assertEqual(cannot_leave.status_code, 400, cannot_leave.get_data(as_text=True))

        transferred = self.client.post(
            f"/api/teams/{team['id']}/transfer", json={"user_id": self.editor_id}
        )
        self.assertEqual(transferred.status_code, 200, transferred.get_data(as_text=True))
        detail = self._team_detail(team["id"])
        roles = {member["id"]: member["role"] for member in detail["members"]}
        self.assertEqual(roles[self.editor_id], "owner")
        self.assertEqual(roles[self.owner_id], "admin")

    def test_teams_pages_render(self):
        team = self._create_team()
        listed = self.client.get("/teams")
        self.assertEqual(listed.status_code, 200, listed.get_data(as_text=True))
        detail = self.client.get(f"/teams/{team['id']}")
        self.assertEqual(detail.status_code, 200, detail.get_data(as_text=True))

        invite = self._invite(team["id"], self._email_of(self.viewer_id), "viewer")
        token = invite["invite_link"].rstrip("/").rsplit("/", 1)[-1]
        self.login(self.viewer_id)
        landing = self.client.get(f"/teams/invites/{token}")
        self.assertEqual(landing.status_code, 200, landing.get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
