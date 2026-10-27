import io
import os
import re
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

        email_change = self.client.post(
            "/api/settings/account",
            json={"email": "changed@example.test", "current_password": "password123"},
        )
        self.assertEqual(email_change.status_code, 200, email_change.get_data(as_text=True))
        self.assertEqual(email_change.get_json()["account"]["email"], "changed@example.test")

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


if __name__ == "__main__":
    unittest.main()
