import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-security-tests-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["SECRET_KEY"] = "security-tests-only"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as ob


class SecurityRegressionTests(unittest.TestCase):
    sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()

    def setUp(self):
        type(self).sequence += 1
        ob.app.config.update(TESTING=True)
        self.files = tempfile.TemporaryDirectory(prefix="oneboard-security-files-")
        self.addCleanup(self.files.cleanup)
        self.root = Path(self.files.name).resolve() / "site"
        self.root.mkdir()
        (self.root / "sub").mkdir()
        (self.root / "sub" / "file.txt").write_text("fixture")
        (self.root / "index.html").write_text("<html><body>Public</body></html>")
        self.owner, self.owner_id, self.owner_email = self.user("owner")
        self.viewer, self.viewer_id, self.viewer_email = self.user("viewer")
        self.stranger, self.stranger_id, self.stranger_email = self.user("stranger")
        self.mail = mock.patch("app.smtplib.SMTP").start()
        self.addCleanup(mock.patch.stopall)
        self.environment = mock.patch.dict(os.environ, {
            "SMTP_HOST": "smtp.example.test", "SMTP_FROM": "test@example.test",
            "SMTP_USERNAME": "", "SMTP_PASSWORD": "",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        with ob.app.app_context():
            ob.connect_site_project(self.owner_id, path=str(self.root))
            self.project_id = ob.query_db("SELECT id FROM website_workspaces WHERE user_id = ? AND path = ?",
                                         (self.owner_id, str(self.root)), one=True)["id"]

    def user(self, name):
        email = f"{name}-{self.sequence}@example.test"
        with ob.app.app_context():
            uid = ob.execute_db("INSERT INTO users (name,email,password_hash,email_verified) VALUES (?,?,?,1)",
                                (name, email, ob.hash_password("password123")))
        client = ob.app.test_client()
        response = client.post("/api/auth/login", json={"email": email, "password": "password123"})
        self.assertEqual(response.status_code, 200)
        return client, uid, email

    def share(self):
        with ob.app.app_context():
            team = ob.create_team(self.owner_id, "Audit team")
            ob.add_team_project(team["id"], self.owner_id, project_id=self.project_id)
            _, token = ob.invite_team_member(team["id"], self.owner_id, self.viewer_email, "viewer")
            ob.accept_team_invite(token, self.viewer_id)
            ob.connect_site_project(self.viewer_id, project_id=self.project_id)
        return team["id"]

    def test_viewer_cannot_use_subfolder_or_parent_to_gain_write_access(self):
        self.share()
        for path in (self.root / "sub", self.root.parent):
            response = self.viewer.post("/api/site-manager/connect", json={"path": str(path)})
            self.assertEqual(response.status_code, 403, response.data)
        denied = self.viewer.post("/api/site-manager/files/delete", json={"path": "sub/file.txt"})
        self.assertEqual(denied.status_code, 403)
        self.assertTrue((self.root / "sub" / "file.txt").exists())
        with self.viewer.get("/api/site-manager/files/raw?path=index.html") as response:
            self.assertEqual(response.status_code, 200)

    def test_other_users_cannot_claim_personal_roots_or_overlapping_paths(self):
        for path in (self.root, self.root / "sub", self.root.parent):
            response = self.stranger.post("/api/site-manager/connect", json={"path": str(path)})
            self.assertEqual(response.status_code, 403, response.data)

    def test_existing_personal_project_can_be_shared_by_path(self):
        with ob.app.app_context():
            team = ob.create_team(self.owner_id, "Share by path")
            project = ob.add_team_project(team["id"], self.owner_id, path=str(self.root))
            self.assertEqual(project["id"], self.project_id)

    def test_preexisting_parent_alias_cannot_read_shared_child(self):
        self.share()
        with ob.app.app_context():
            ob.set_current_site_directory(self.stranger_id, str(self.root.parent))
        response = self.stranger.get("/api/site-manager/files/raw?path=site/index.html")
        self.assertEqual(response.status_code, 403)

    def test_retiring_team_project_disconnects_readers_and_preserves_owner(self):
        team_id = self.share()
        response = self.owner.delete(f"/api/teams/{team_id}/projects/{self.project_id}")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertNotEqual(self.viewer.post("/api/site-manager/files/delete", json={"path": "sub/file.txt"}).status_code, 200)
        self.assertEqual(self.viewer.post("/api/site-manager/connect", json={"path": str(self.root)}).status_code, 403)
        self.assertEqual(self.owner.post("/api/site-manager/connect", json={"project_id": self.project_id}).status_code, 200)
        self.assertTrue((self.root / "sub" / "file.txt").exists())

    def test_deleting_team_preserves_project_ownership(self):
        team_id = self.share()
        response = self.owner.delete(f"/api/teams/{team_id}")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.viewer.post("/api/site-manager/connect", json={"path": str(self.root)}).status_code, 403)
        self.assertEqual(self.owner.post("/api/site-manager/connect", json={"project_id": self.project_id}).status_code, 200)

    def test_legacy_child_alias_does_not_block_owner_or_survive_unshare(self):
        team_id = self.share()
        with ob.app.app_context():
            ob.execute_db("INSERT INTO website_workspaces (user_id,path) VALUES (?,?)", (self.viewer_id, str(self.root / "sub")))
        with self.owner.get("/api/site-manager/files/raw?path=index.html") as response:
            self.assertEqual(response.status_code, 200)
        self.assertEqual(self.owner.delete(f"/api/teams/{team_id}/projects/{self.project_id}").status_code, 200)
        self.assertEqual(self.owner.post("/api/site-manager/connect", json={"project_id": self.project_id}).status_code, 200)
        self.assertEqual(self.viewer.post("/api/site-manager/connect", json={"path": str(self.root / "sub")}).status_code, 403)

    def test_generic_project_removal_also_disconnects_team_readers(self):
        self.share()
        response = self.owner.post("/api/site-manager/projects/remove", json={"project_id": self.project_id})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.viewer.post("/api/site-manager/connect", json={"path": str(self.root)}).status_code, 403)

    def verification_token(self):
        message = self.mail.return_value.__enter__.return_value.send_message.call_args.args[0]
        return re.search(r"/verify-email/([^\s]+)", message.get_content()).group(1)

    def test_pending_email_cannot_claim_invitation_until_verified(self):
        target = f"new-address-{self.sequence}@example.test"
        with ob.app.app_context():
            team = ob.create_team(self.owner_id, "Identity team")
            invite, _ = ob.invite_team_member(team["id"], self.owner_id, target, "admin")
        response = self.stranger.post("/api/settings/account", json={"email": target, "current_password": "password123"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.get_json()["account"]["email"], self.stranger_email)
        self.assertEqual(response.get_json()["account"]["pending_email"], target)
        self.assertEqual(self.stranger.post(f"/api/teams/invites/{invite['id']}/accept").status_code, 403)
        token = self.verification_token()
        verified = ob.app.test_client().post("/api/auth/verify-email", json={"token": token})
        self.assertEqual(verified.status_code, 200, verified.data)
        self.assertEqual(self.stranger.get("/api/session").status_code, 401)
        self.assertEqual(self.stranger.post("/api/auth/login", json={"email": target, "password": "password123"}).status_code, 200)
        self.assertEqual(self.stranger.post(f"/api/teams/invites/{invite['id']}/accept").status_code, 200)

    def test_web_settings_keeps_email_pending(self):
        response = self.owner.post("/settings", data={"name": "Owner", "email": f"pending-web-{self.sequence}@example.test",
                                                     "current_password": "password123"})
        self.assertEqual(response.status_code, 302)
        with ob.app.app_context():
            self.assertEqual(ob.get_user_account(self.owner_id)["email"], self.owner_email)
        self.assertEqual(self.owner.get("/settings").status_code, 200)

    def test_failed_email_change_keeps_existing_identity_and_session(self):
        self.mail.side_effect = OSError("SMTP outage")
        response = self.owner.post("/api/settings/account", json={"email": f"unreachable-{self.sequence}@example.test", "current_password": "password123"})
        self.assertEqual(response.status_code, 400)
        with ob.app.app_context():
            user = ob.get_user_account(self.owner_id)
            self.assertEqual(user["email"], self.owner_email)
            self.assertIsNone(user["pending_email"])
        self.assertEqual(self.owner.get("/api/session").status_code, 200)

    def test_failed_resend_preserves_old_link_and_success_consumes_all_siblings(self):
        with ob.app.app_context():
            first = ob.create_email_verification_token(self.owner_id)
            second = ob.create_email_verification_token(self.owner_id)
            with ob.app.test_request_context():
                self.mail.side_effect = OSError("SMTP outage")
                with self.assertRaises(ValueError):
                    ob.send_email_verification(self.owner_id, self.owner_email)
            self.assertEqual(ob.consume_email_verification_token(first), self.owner_id)
            self.assertIsNone(ob.consume_email_verification_token(second))

    def test_old_email_token_cannot_verify_replacement_pending_email(self):
        with ob.app.app_context():
            old = ob.create_email_verification_token(self.owner_id)
        self.owner.post("/api/settings/account", json={"email": f"replacement-{self.sequence}@example.test", "current_password": "password123"})
        with ob.app.app_context():
            ob.consume_email_verification_token(old)
            self.assertEqual(ob.get_user_account(self.owner_id)["email"], self.owner_email)

    def test_reset_revokes_sessions_other_tokens_and_preview_access(self):
        with ob.app.app_context():
            first = ob.create_password_reset_token(self.owner_id)
            second = ob.create_password_reset_token(self.owner_id)
            preview = ob.create_site_preview_access_token(self.owner_id)
        guest = ob.app.test_client()
        response = guest.post("/api/auth/reset-password", json={"token": first, "password": "newpassword123", "confirm_password": "newpassword123"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.owner.get("/api/session").status_code, 401)
        self.assertEqual(guest.get("/site-manager/preview/index.html", query_string={"preview_token": preview}).status_code, 404)
        for token in (first, second):
            response = guest.post("/api/auth/reset-password", json={"token": token, "password": "otherpassword123", "confirm_password": "otherpassword123"})
            self.assertEqual(response.status_code, 400)
        self.assertEqual(self.owner.post("/api/auth/login", json={"email": self.owner_email, "password": "newpassword123"}).status_code, 200)

    def test_web_reset_also_revokes_existing_session(self):
        with ob.app.app_context():
            token = ob.create_password_reset_token(self.owner_id)
        response = ob.app.test_client().post(f"/reset-password/{token}", data={"password": "newpassword123", "confirm_password": "newpassword123"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.owner.get("/api/session").status_code, 401)

    def test_password_recovery_cancels_pending_identity_change(self):
        self.owner.post("/api/settings/account", json={"email": f"pending-reset-{self.sequence}@example.test", "current_password": "password123"})
        verification = self.verification_token()
        with ob.app.app_context():
            token = ob.create_password_reset_token(self.owner_id)
            self.assertTrue(ob.reset_account_password(token, "newpassword123"))
            self.assertIsNone(ob.consume_email_verification_token(verification))
            self.assertEqual(ob.get_user_account(self.owner_id)["email"], self.owner_email)

    def test_password_change_keeps_initiator_and_revokes_second_session(self):
        second = ob.app.test_client()
        second.post("/api/auth/login", json={"email": self.owner_email, "password": "password123"})
        response = self.owner.post("/api/settings/account", json={"current_password": "password123", "new_password": "newpassword123", "confirm_password": "newpassword123"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(self.owner.get("/api/session").status_code, 200)
        self.assertEqual(second.get("/api/session").status_code, 401)

    def test_preview_only_serves_public_files(self):
        with ob.app.app_context():
            token = ob.create_site_preview_access_token(self.owner_id)
        guest = ob.app.test_client()
        for path in (".env", "database.sqlite", "private.key", ".private.js"):
            (self.root / path).write_text("private fixture")
            response = guest.get(f"/site-manager/preview/{path}", query_string={"preview_token": token})
            self.assertEqual(response.status_code, 404, path)
        with guest.get("/site-manager/preview/index.html", query_string={"preview_token": token}) as response:
            self.assertEqual(response.status_code, 200)
            self.assertIn(b"Public", response.data)

    def test_company_fields_can_be_cleared_without_changing_omitted_fields(self):
        self.owner.post("/api/settings/account", json={"company_name": "Acme", "company_email": "hi@example.test", "company_website": "https://example.test"})
        response = self.owner.post("/api/settings/account", json={"company_name": ""})
        self.assertEqual(response.get_json()["account"]["company_email"], "hi@example.test")
        response = self.owner.post("/api/settings/account", json={"company_email": "", "company_website": ""})
        for key in ("company_name", "company_email", "company_website"):
            self.assertEqual(response.get_json()["account"][key], "")

    def test_workspace_lock_blocks_another_process_and_is_reentrant(self):
        self.share()
        program = """import app
with app.app.app_context():
    try:
        with app.site_operation_lock(%d):
            print('acquired')
    except ValueError:
        print('blocked')
""" % self.viewer_id
        with ob.app.app_context(), ob.site_operation_lock(self.owner_id), ob.site_operation_lock(self.owner_id):
            result = subprocess.run([sys.executable, "-c", program], cwd=ob.BASE_DIR,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), "blocked")
        result = subprocess.run([sys.executable, "-c", program], cwd=ob.BASE_DIR,
                                capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "acquired")


if __name__ == "__main__":
    unittest.main()
