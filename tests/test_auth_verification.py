import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-auth-tests-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["SECRET_KEY"] = "oneboard-auth-test-secret"
os.environ["SMTP_HOST"] = "smtp.example.test"
os.environ["SMTP_FROM"] = "ONEBoard <noreply@example.test>"

import app as oneboard


class EmailVerificationTests(unittest.TestCase):
    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()

    def setUp(self):
        oneboard.app.config.update(TESTING=True)
        self.client = oneboard.app.test_client()

    def test_smtp_settings_rejects_an_invalid_port(self):
        with mock.patch.dict(os.environ, {"SMTP_PORT": "not-a-port"}, clear=False):
            with self.assertRaisesRegex(ValueError, "SMTP_PORT must be a valid port number"):
                oneboard.smtp_settings()

    def test_direct_wsgi_import_loads_env_configuration(self):
        from dotenv import dotenv_values
        if not dotenv_values(os.path.join(oneboard.BASE_DIR, ".env")).get("SECRET_KEY"):
            self.skipTest("Requires a local .env with SECRET_KEY")
        environment = os.environ.copy()
        environment.pop("SECRET_KEY", None)
        with tempfile.TemporaryDirectory(prefix="oneboard-wsgi-test-") as directory:
            environment["ONEBOARD_DATA_DIR"] = directory
            result = subprocess.run([
                sys.executable, "-c",
                "from dotenv import dotenv_values; import app; "
                "expected = dotenv_values('.env').get('SECRET_KEY'); "
                "assert not expected or app.app.config['SECRET_KEY'] == expected; "
                "assert app.create_app().config['SECRET_KEY'] == app.app.config['SECRET_KEY']",
            ], cwd=oneboard.BASE_DIR, env=environment, capture_output=True)
        self.assertEqual(result.returncode, 0, "WSGI configuration did not load consistently")

    def test_email_links_use_public_origin_when_request_is_local(self):
        with mock.patch.dict(os.environ, {"ONEBOARD_PUBLIC_URL": "https://board.example.test/"}):
            with oneboard.app.test_request_context(base_url="http://127.0.0.1:5002"):
                for endpoint in ("verify_email", "reset_password", "team_invite_landing"):
                    link = oneboard.email_action_url(endpoint, token="test-token")
                    self.assertTrue(link.startswith("https://board.example.test/"))
                    self.assertTrue(link.endswith("/test-token"))

    def test_email_links_fall_back_to_request_origin(self):
        with mock.patch.dict(os.environ, {"ONEBOARD_PUBLIC_URL": ""}):
            with oneboard.app.test_request_context(base_url="https://board.example.test"):
                self.assertEqual(oneboard.email_action_url("verify_email", token="test-token"),
                                 "https://board.example.test/verify-email/test-token")

    def test_failed_login_preserves_email_for_verification_resend(self):
        response = self.client.post("/login", data={
            "email": "resend@example.test", "password": "wrong-password",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'id="resend_email" value="resend@example.test"', response.data)

    def test_email_requires_complete_authentication_credentials(self):
        with mock.patch.dict(
            os.environ,
            {
                "SMTP_HOST": "smtp.example.test",
                "SMTP_FROM": "ONEBoard <noreply@example.test>",
                "SMTP_USERNAME": "mailer",
                "SMTP_PASSWORD": "",
            },
            clear=False,
        ):
            with self.assertRaisesRegex(ValueError, "SMTP_USERNAME and SMTP_PASSWORD"):
                oneboard.send_email_verification(1, "verify@example.test")

    def test_smtp_verification_failure_is_logged_without_credentials(self):
        smtp_environment = {
            "SMTP_HOST": "smtp.example.test",
            "SMTP_PORT": "587",
            "SMTP_USERNAME": "mailer@example.test",
            "SMTP_PASSWORD": "smtp-test-secret",
            "SMTP_FROM": "ONEBoard <noreply@example.test>",
            "SMTP_USE_TLS": "1",
        }
        with mock.patch.dict(os.environ, smtp_environment):
            with mock.patch("app.smtplib.SMTP") as smtp:
                server = smtp.return_value.__enter__.return_value
                server.login.side_effect = oneboard.smtplib.SMTPAuthenticationError(
                    535, b"Authentication failed"
                )
                with self.assertLogs(oneboard.app.logger, level="ERROR") as captured:
                    response = self.client.post(
                        "/api/auth/register",
                        json={
                            "name": "SMTP Failure",
                            "email": "smtp-failure@example.test",
                            "password": "password123",
                            "confirm_password": "password123",
                        },
                    )

        self.assertEqual(response.status_code, 503)
        self.assertIn("SMTP verification email delivery failed", captured.output[0])
        self.assertIn("Authentication failed", "\n".join(captured.output))
        self.assertNotIn(smtp_environment["SMTP_PASSWORD"], "\n".join(captured.output))

    def test_registration_requires_verification_before_login(self):
        with mock.patch("app.smtplib.SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            response = self.client.post(
                "/api/auth/register",
                json={
                    "name": "Verification Test",
                    "email": "verify@example.test",
                    "password": "password123",
                    "confirm_password": "password123",
                },
            )

            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.get_json()["verification_required"])
            message = server.send_message.call_args.args[0]
            token = re.search(r"/verify-email/([^\s]+)", message.get_content()).group(1)

        login = self.client.post(
            "/api/auth/login",
            json={"email": "verify@example.test", "password": "password123"},
        )
        self.assertEqual(login.status_code, 403)
        self.assertTrue(login.get_json()["verification_required"])

        verified = self.client.get(f"/verify-email/{token}")
        self.assertEqual(verified.status_code, 200)
        self.assertIn(b"email has been verified", verified.data)

        login = self.client.post(
            "/api/auth/login",
            json={"email": "verify@example.test", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200)
        self.assertTrue(login.get_json()["user"]["email_verified"])

    def register_verified_user(self, email, password="password123"):
        with mock.patch("app.smtplib.SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            response = self.client.post(
                "/api/auth/register",
                json={
                    "name": "API Test",
                    "email": email,
                    "password": password,
                    "confirm_password": password,
                },
            )
            self.assertEqual(response.status_code, 200)
            message = server.send_message.call_args.args[0]
            token = re.search(r"/verify-email/([^\s]+)", message.get_content()).group(1)
        verified = self.client.post("/api/auth/verify-email", json={"token": token})
        self.assertEqual(verified.status_code, 200, verified.get_data(as_text=True))
        return verified.get_json()

    def test_api_verify_email_marks_user_verified(self):
        body = self.register_verified_user("api-verify@example.test")

        self.assertTrue(body["verified"])
        login = self.client.post(
            "/api/auth/login",
            json={"email": "api-verify@example.test", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200)

        bad_token = self.client.post("/api/auth/verify-email", json={"token": "bogus"})
        self.assertEqual(bad_token.status_code, 400)

    def test_api_forgot_and_reset_password_flow(self):
        self.register_verified_user("api-reset@example.test")

        with mock.patch("app.smtplib.SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            forgot = self.client.post(
                "/api/auth/forgot-password",
                json={"email": "api-reset@example.test"},
            )
            self.assertEqual(forgot.status_code, 200)
            self.assertNotIn("reset_url", forgot.get_json())
            message = server.send_message.call_args.args[0]
            token = re.search(r"/reset-password/([^\s]+)", message.get_content()).group(1)

            unknown = self.client.post(
                "/api/auth/forgot-password",
                json={"email": "nobody@example.test"},
            )
            self.assertEqual(unknown.status_code, 200)
            self.assertEqual(server.send_message.call_count, 1)

        reset = self.client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "newpass456", "confirm_password": "newpass456"},
        )
        self.assertEqual(reset.status_code, 200, reset.get_data(as_text=True))

        login = self.client.post(
            "/api/auth/login",
            json={"email": "api-reset@example.test", "password": "newpass456"},
        )
        self.assertEqual(login.status_code, 200)

        reused = self.client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "otherpass789", "confirm_password": "otherpass789"},
        )
        self.assertEqual(reused.status_code, 400)

    def test_web_forgot_password_sends_email_without_exposing_link(self):
        self.register_verified_user("web-reset@example.test")
        with mock.patch("app.smtplib.SMTP") as smtp:
            server = smtp.return_value.__enter__.return_value
            response = self.client.post(
                "/forgot-password",
                data={"email": "web-reset@example.test"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(b"/reset-password/", response.data)
            message = server.send_message.call_args.args[0]
            self.assertIn("/reset-password/", message.get_content())

    def test_api_settings_account_updates_profile_and_company(self):
        self.register_verified_user("api-account@example.test")
        login = self.client.post(
            "/api/auth/login",
            json={"email": "api-account@example.test", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200)

        update = self.client.post(
            "/api/settings/account",
            json={
                "name": "New Name",
                "company_name": "Acme",
                "company_email": "hi@acme.test",
                "buffer_api_key": "buffer-key-123",
            },
        )
        self.assertEqual(update.status_code, 200, update.get_data(as_text=True))
        account = update.get_json()["account"]
        self.assertEqual(account["name"], "New Name")
        self.assertEqual(account["company_name"], "Acme")
        self.assertTrue(account["buffer_api_key_configured"])

        email_without_password = self.client.post(
            "/api/settings/account",
            json={"email": "changed@example.test"},
        )
        self.assertEqual(email_without_password.status_code, 401)

        with mock.patch("app.smtplib.SMTP"):
            email_change = self.client.post(
                "/api/settings/account",
                json={"email": "changed@example.test", "current_password": "password123"},
            )
        self.assertEqual(email_change.status_code, 200, email_change.get_data(as_text=True))
        self.assertEqual(email_change.get_json()["account"]["email"], "api-account@example.test")
        self.assertEqual(email_change.get_json()["account"]["pending_email"], "changed@example.test")

        avatar_png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        upload = self.client.post(
            "/api/settings/account",
            data={"avatar": (io.BytesIO(avatar_png), "me.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(upload.status_code, 200, upload.get_data(as_text=True))
        self.assertTrue(upload.get_json()["account"]["avatar_path"].endswith(".png"))


    no_smtp = {"SMTP_HOST": "", "SMTP_FROM": ""}

    def test_register_without_smtp_returns_token(self):
        with mock.patch.dict(os.environ, self.no_smtp, clear=False):
            with mock.patch("app.smtplib.SMTP") as smtp:
                response = self.client.post(
                    "/api/auth/register",
                    json={
                        "name": "Local User",
                        "email": "local-verify@example.test",
                        "password": "password123",
                        "confirm_password": "password123",
                    },
                )
                smtp.assert_not_called()
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        token = response.get_json()["verification_token"]
        self.assertTrue(token)
        verified = self.client.post("/api/auth/verify-email", json={"token": token})
        self.assertEqual(verified.status_code, 200)
        login = self.client.post(
            "/api/auth/login",
            json={"email": "local-verify@example.test", "password": "password123"},
        )
        self.assertEqual(login.status_code, 200)

    def test_resend_without_smtp_returns_token(self):
        with mock.patch.dict(os.environ, self.no_smtp, clear=False):
            self.client.post(
                "/api/auth/register",
                json={
                    "name": "Resend User",
                    "email": "local-resend@example.test",
                    "password": "password123",
                    "confirm_password": "password123",
                },
            )
            response = self.client.post(
                "/api/auth/resend-verification",
                json={"email": "local-resend@example.test"},
            )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.get_json()["verification_token"])

    def test_forgot_without_smtp_returns_token(self):
        with mock.patch.dict(os.environ, self.no_smtp, clear=False):
            registered = self.client.post(
                "/api/auth/register",
                json={
                    "name": "Reset User",
                    "email": "local-reset@example.test",
                    "password": "password123",
                    "confirm_password": "password123",
                },
            )
            self.client.post(
                "/api/auth/verify-email",
                json={"token": registered.get_json()["verification_token"]},
            )
            forgot = self.client.post(
                "/api/auth/forgot-password",
                json={"email": "local-reset@example.test"},
            )
            unknown = self.client.post(
                "/api/auth/forgot-password",
                json={"email": "nobody-local@example.test"},
            )
        self.assertEqual(forgot.status_code, 200)
        token = forgot.get_json()["reset_token"]
        self.assertTrue(token)
        self.assertNotIn("reset_token", unknown.get_json())
        reset = self.client.post(
            "/api/auth/reset-password",
            json={"token": token, "password": "newpass456", "confirm_password": "newpass456"},
        )
        self.assertEqual(reset.status_code, 200, reset.get_data(as_text=True))
        login = self.client.post(
            "/api/auth/login",
            json={"email": "local-reset@example.test", "password": "newpass456"},
        )
        self.assertEqual(login.status_code, 200)


if __name__ == "__main__":
    unittest.main()
