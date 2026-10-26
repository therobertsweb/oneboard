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


if __name__ == "__main__":
    unittest.main()
