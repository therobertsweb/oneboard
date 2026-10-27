import base64
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest import mock


TEST_DATA = tempfile.TemporaryDirectory(prefix="oneboard-site-manager-tests-")
os.environ["ONEBOARD_DATA_DIR"] = TEST_DATA.name
os.environ["SECRET_KEY"] = "site-manager-test-secret"

import app as oneboard


class SiteManagerTests(unittest.TestCase):
    user_sequence = 0

    @classmethod
    def tearDownClass(cls):
        TEST_DATA.cleanup()

    def setUp(self):
        type(self).user_sequence += 1
        self.workspace = tempfile.TemporaryDirectory(prefix="oneboard-workspace-")
        self.workspace_path = Path(self.workspace.name)
        self.site = self.workspace_path / "site-a"
        self.site.mkdir()
        (self.site / "index.html").write_text("original", encoding="utf-8")

        oneboard.app.config.update(TESTING=True)
        with oneboard.app.app_context():
            oneboard.execute_db(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (
                    "Site Manager Test",
                    f"site-manager-{self.user_sequence}@example.test",
                    oneboard.hash_password("password123"),
                ),
            )
            self.user_id = oneboard.query_db(
                "SELECT id FROM users WHERE email = ?",
                (f"site-manager-{self.user_sequence}@example.test",),
                one=True,
            )["id"]

        self.client = oneboard.app.test_client()
        with self.client.session_transaction() as session:
            session["user_id"] = self.user_id

    def tearDown(self):
        self.workspace.cleanup()

    def connect(self, path=None):
        response = self.client.post(
            "/api/site-manager/connect",
            json={"path": str(path or self.site)},
        )
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        return response.get_json()["manager"]

    def bind_remote_to_current_site(self):
        with oneboard.app.app_context():
            directory = oneboard.require_site_directory(self.user_id)
            oneboard.execute_db(
                "UPDATE website_remote_connections SET directory_path = ? WHERE user_id = ?",
                (os.path.realpath(directory["path"]), self.user_id),
            )

    def test_connect_uses_canonical_path_and_lists_real_files(self):
        alias = self.workspace_path / "site-alias"
        alias.symlink_to(self.site, target_is_directory=True)
        manager = self.connect(alias)

        self.assertEqual(manager["directory"]["path"], str(self.site.resolve()))
        self.assertEqual([item["name"] for item in manager["files"]["entries"]], ["index.html"])

    def test_connect_rejects_the_oneboard_data_directory(self):
        response = self.client.post(
            "/api/site-manager/connect",
            json={"path": TEST_DATA.name},
        )

        self.assertEqual(response.status_code, 400)

    def test_connect_creates_a_missing_nested_directory(self):
        target = self.workspace_path / "brand" / "new-site"
        manager = self.connect(target)

        self.assertTrue(target.is_dir())
        self.assertEqual(manager["directory"]["path"], str(target.resolve()))

    def test_connect_accepts_quoted_and_escaped_paths(self):
        quoted = self.client.post(
            "/api/site-manager/connect",
            json={"path": f'  "{self.site}"  '},
        )
        self.assertEqual(quoted.status_code, 200, quoted.get_data(as_text=True))

        spaced = self.workspace_path / "my site"
        spaced.mkdir()
        escaped = self.client.post(
            "/api/site-manager/connect",
            json={"path": str(spaced).replace(" ", "\\ ")},
        )
        self.assertEqual(escaped.status_code, 200, escaped.get_data(as_text=True))
        self.assertEqual(
            escaped.get_json()["manager"]["directory"]["path"], str(spaced.resolve())
        )

    def test_connect_still_rejects_home_files_and_filesystem_root(self):
        for bad_path in (
            os.path.expanduser("~"),
            os.path.abspath(os.sep),
            str(self.site / "index.html"),
        ):
            response = self.client.post("/api/site-manager/connect", json={"path": bad_path})
            self.assertEqual(response.status_code, 400, bad_path)

    def test_projects_are_listed_and_switchable(self):
        site_b = self.workspace_path / "site-b"
        site_b.mkdir()
        (site_b / "index.html").write_text("b-original", encoding="utf-8")

        self.connect()
        manager = self.connect(site_b)
        projects = manager["projects"]
        self.assertEqual({item["name"] for item in projects}, {"site-a", "site-b"})
        current = next(item for item in projects if item["is_current"])
        self.assertEqual(current["name"], "site-b")
        self.assertTrue(all(item["exists"] for item in projects))

        manager = self.connect()
        projects = manager["projects"]
        current = next(item for item in projects if item["is_current"])
        self.assertEqual(current["name"], "site-a")

        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE website_workspaces SET last_opened_at = ? WHERE user_id = ? AND path = ?",
                ("2020-01-01 00:00:00", self.user_id, str(self.site.resolve())),
            )
            oneboard.execute_db(
                "UPDATE website_workspaces SET last_opened_at = ? WHERE user_id = ? AND path = ?",
                ("2021-01-01 00:00:00", self.user_id, str(site_b.resolve())),
            )
        ordered = self.client.get("/api/site-manager").get_json()["manager"]["projects"]
        self.assertEqual([item["name"] for item in ordered], ["site-b", "site-a"])

    def test_chat_messages_are_scoped_per_project(self):
        site_b = self.workspace_path / "site-b"
        site_b.mkdir()
        (site_b / "index.html").write_text("b-original", encoding="utf-8")
        self.connect()
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.user_id),
            )
        ai_response = {
            "summary": "Touched site A.",
            "files": [{"path": "index.html", "content": "<html><body>A</body></html>"}],
        }
        with mock.patch.object(
            oneboard,
            "run_ai_provider_prompt",
            return_value=(oneboard.json.dumps(ai_response), {"total_tokens": 5}, "muse-text-1.0"),
        ), mock.patch.object(
            oneboard,
            "get_muse_models",
            return_value=["muse-text-1.0", "muse-image-1.0"],
        ):
            update = self.client.post(
                "/api/site-manager/codex-update",
                json={"prompt": "Touch site A"},
            )
        self.assertEqual(update.status_code, 200, update.get_data(as_text=True))
        self.assertEqual(len(update.get_json()["manager"]["codex_messages"]), 2)

        switched = self.connect(site_b)
        self.assertEqual(switched["codex_messages"], [])

        back = self.connect()
        self.assertEqual(len(back["codex_messages"]), 2)

    def test_legacy_chat_messages_attach_to_current_project(self):
        site_b = self.workspace_path / "site-b"
        site_b.mkdir()
        (site_b / "index.html").write_text("b-original", encoding="utf-8")
        self.connect()
        with oneboard.app.app_context():
            oneboard.execute_db(
                "INSERT INTO website_codex_messages (user_id, role, content) VALUES (?, ?, ?)",
                (self.user_id, "user", "legacy hello"),
            )
        manager = self.client.get("/api/site-manager").get_json()["manager"]
        self.assertEqual(len(manager["codex_messages"]), 1)

        switched = self.connect(site_b)
        self.assertEqual(switched["codex_messages"], [])

    def test_remove_project_disconnects_current(self):
        site_b = self.workspace_path / "site-b"
        site_b.mkdir()
        (site_b / "index.html").write_text("b-original", encoding="utf-8")
        self.connect()
        manager = self.connect(site_b)
        current_id = next(item["id"] for item in manager["projects"] if item["is_current"])

        removed = self.client.post(
            "/api/site-manager/projects/remove",
            json={"project_id": current_id},
        )
        self.assertEqual(removed.status_code, 200, removed.get_data(as_text=True))
        body = removed.get_json()["manager"]
        self.assertIsNone(body["directory"])
        self.assertEqual([item["name"] for item in body["projects"]], ["site-a"])

        bogus = self.client.post(
            "/api/site-manager/projects/remove",
            json={"project_id": 999999},
        )
        self.assertEqual(bogus.status_code, 400)

    def test_browse_directory_lists_subfolders_and_selection_rules(self):
        root = self.workspace_path / "browse-root"
        (root / "alpha").mkdir(parents=True)
        (root / "beta").mkdir(parents=True)
        (root / ".hidden").mkdir(parents=True)
        (root / "file.txt").write_text("not a dir", encoding="utf-8")

        response = self.client.get(
            "/api/site-manager/browse-directory",
            query_string={"path": str(root)},
        )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        listing = response.get_json()["listing"]
        self.assertEqual(listing["current"], os.path.realpath(root))
        self.assertEqual(
            [entry["name"] for entry in listing["entries"]],
            ["alpha", "beta"],
        )
        self.assertTrue(listing["can_select"])
        self.assertEqual(listing["parent"], os.path.realpath(self.workspace_path))

    def test_browse_directory_blocks_app_data_files_and_home_selection(self):
        blocked = self.client.get(
            "/api/site-manager/browse-directory",
            query_string={"path": TEST_DATA.name},
        )
        self.assertEqual(blocked.status_code, 400)

        not_a_dir = self.client.get(
            "/api/site-manager/browse-directory",
            query_string={"path": str(self.site / "index.html")},
        )
        self.assertEqual(not_a_dir.status_code, 400)

        home = self.client.get(
            "/api/site-manager/browse-directory",
            query_string={"path": os.path.expanduser("~")},
        )
        self.assertEqual(home.status_code, 200, home.get_data(as_text=True))
        self.assertFalse(home.get_json()["listing"]["can_select"])

    def test_api_file_raw_serves_workspace_files(self):
        self.connect()

        response = self.client.get(
            "/api/site-manager/files/raw",
            query_string={"path": "index.html"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), "original")

        missing = self.client.get(
            "/api/site-manager/files/raw",
            query_string={"path": "nope.html"},
        )
        self.assertEqual(missing.status_code, 404)

        escape = self.client.get(
            "/api/site-manager/files/raw",
            query_string={"path": "../outside.txt"},
        )
        self.assertEqual(escape.status_code, 404)

    def test_api_asset_raw_serves_uploaded_assets(self):
        self.connect()
        png = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )
        upload = self.client.post(
            "/api/site-manager/assets/upload",
            data={"asset": (io.BytesIO(png), "pic.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(upload.status_code, 200, upload.get_data(as_text=True))
        asset_path = upload.get_json()["asset_path"]

        response = self.client.get(
            "/api/site-manager/assets/raw",
            query_string={"path": asset_path},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(), png)

        bogus = self.client.get(
            "/api/site-manager/assets/raw",
            query_string={"path": ".oneboard/user-assets/nope.png"},
        )
        self.assertEqual(bogus.status_code, 404)

    def test_backup_restore_preserves_internal_state_and_excludes_symlinks(self):
        git_dir = self.site / ".git"
        oneboard_dir = self.site / ".oneboard" / "home"
        git_dir.mkdir()
        oneboard_dir.mkdir(parents=True)
        (git_dir / "config").write_text("git-original", encoding="utf-8")
        (oneboard_dir / "auth.json").write_text("auth-original", encoding="utf-8")
        external = self.workspace_path / "external-secret.txt"
        external.write_text("external-safe", encoding="utf-8")
        external_link = self.site / "external-link.txt"
        external_link.symlink_to(external)
        self.connect()

        response = self.client.post("/api/site-manager/backup", json={})
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        backup_id = response.get_json()["manager"]["backups"][0]["id"]
        with oneboard.app.app_context():
            backup = oneboard.get_site_backup(self.user_id, backup_id)
            with zipfile.ZipFile(backup["backup_path"], "r") as archive:
                self.assertEqual(set(archive.namelist()), {"index.html"})

        (self.site / "index.html").write_text("changed", encoding="utf-8")
        (git_dir / "config").write_text("git-preserved", encoding="utf-8")
        (oneboard_dir / "auth.json").write_text("auth-preserved", encoding="utf-8")
        response = self.client.post("/api/site-manager/restore", json={"backup_id": backup_id})

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual((self.site / "index.html").read_text(encoding="utf-8"), "original")
        self.assertEqual((git_dir / "config").read_text(encoding="utf-8"), "git-preserved")
        self.assertEqual((oneboard_dir / "auth.json").read_text(encoding="utf-8"), "auth-preserved")
        self.assertFalse(os.path.lexists(external_link))
        self.assertEqual(external.read_text(encoding="utf-8"), "external-safe")

    def test_backup_cannot_restore_over_a_different_site(self):
        self.connect()
        response = self.client.post("/api/site-manager/backup", json={})
        backup_id = response.get_json()["manager"]["backups"][0]["id"]

        second_site = self.workspace_path / "site-b"
        second_site.mkdir()
        second_index = second_site / "index.html"
        second_index.write_text("second-site", encoding="utf-8")
        self.connect(second_site)
        response = self.client.post("/api/site-manager/restore", json={"backup_id": backup_id})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(second_index.read_text(encoding="utf-8"), "second-site")

    def test_deleting_symlink_unlinks_it_without_deleting_target(self):
        external = self.workspace_path / "external.txt"
        external.write_text("keep me", encoding="utf-8")
        link = self.site / "linked.txt"
        link.symlink_to(external)
        manager = self.connect()
        self.assertNotIn("linked.txt", [item["name"] for item in manager["files"]["entries"]])

        response = self.client.post("/api/site-manager/files/delete", json={"path": "linked.txt"})

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertFalse(os.path.lexists(link))
        self.assertEqual(external.read_text(encoding="utf-8"), "keep me")

    def test_stale_native_directory_cannot_mutate_the_new_site(self):
        self.connect()
        original_directory = str(self.site.resolve())
        second_site = self.workspace_path / "site-b"
        second_site.mkdir()
        second_index = second_site / "index.html"
        second_index.write_text("second-site", encoding="utf-8")
        self.connect(second_site)

        response = self.client.post(
            "/api/site-manager/files/delete",
            json={"path": "index.html", "expected_directory_path": original_directory},
        )

        self.assertEqual(response.status_code, 400, response.get_data(as_text=True))
        self.assertEqual(second_index.read_text(encoding="utf-8"), "second-site")

    def test_codex_history_remains_bound_to_its_starting_directory(self):
        self.connect()
        second_site = self.workspace_path / "site-b"
        second_site.mkdir()
        (second_site / "index.html").write_text("second-site", encoding="utf-8")

        def finish_after_directory_change(*_args, **_kwargs):
            oneboard.connect_site_directory(self.user_id, str(second_site))
            return {
                "command": "muse direct site update",
                "cwd": str(self.site),
                "exit_code": 0,
                "output": "completed",
                "reply": "completed",
                "started_at": "now",
            }

        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-key", self.user_id),
            )
            with mock.patch.object(
                oneboard,
                "run_site_ai_fallback_update",
                side_effect=finish_after_directory_change,
            ):
                oneboard.run_site_codex_update(self.user_id, "Update the homepage")
            history = oneboard.query_db(
                "SELECT directory_path FROM website_update_history WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (self.user_id,),
                one=True,
            )

        self.assertEqual(history["directory_path"], str(self.site.resolve()))

    def test_site_manager_update_runs_directly_on_muse(self):
        self.connect()
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.user_id),
            )

        ai_response = {
            "summary": "Updated homepage hero copy.",
            "files": [
                {
                    "path": "index.html",
                    "content": "<html><body><h1>New homepage copy</h1></body></html>",
                }
            ],
        }

        with mock.patch.object(
            oneboard,
            "run_ai_provider_prompt",
            return_value=(oneboard.json.dumps(ai_response), {"total_tokens": 42}, "muse-text-1.0"),
        ), mock.patch.object(
            oneboard,
            "get_muse_models",
            return_value=["muse-text-1.0", "muse-image-1.0"],
        ):
            response = self.client.post(
                "/api/site-manager/codex-update",
                json={"prompt": "Update the homepage hero section"},
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn("New homepage copy", (self.site / "index.html").read_text(encoding="utf-8"))
        update = response.get_json()["manager"]["updates"][0]
        self.assertEqual(update["source"], "ai-direct:muse")
        self.assertEqual(update["status"], "pending")

    def test_codex_update_creates_arbitrary_non_html_files(self):
        self.connect()
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.user_id),
            )

        ai_response = {
            "summary": "Created project notes, config, and container file.",
            "files": [
                {"path": "notes/tareas.md", "content": "# Tareas\n\n- Una\n"},
                {"path": "data/config.json", "content": '{"retries": 3}'},
                {"path": "Dockerfile", "content": "FROM python:3.12\n"},
                {"path": "index.html", "content": "<html><body>same</body></html>"},
            ],
        }

        with mock.patch.object(
            oneboard,
            "run_ai_provider_prompt",
            return_value=(oneboard.json.dumps(ai_response), {"total_tokens": 42}, "muse-text-1.0"),
        ), mock.patch.object(
            oneboard,
            "get_muse_models",
            return_value=["muse-text-1.0", "muse-image-1.0"],
        ):
            response = self.client.post(
                "/api/site-manager/codex-update",
                json={"prompt": "Create project notes and config files"},
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertIn("Tareas", (self.site / "notes" / "tareas.md").read_text(encoding="utf-8"))
        self.assertEqual(
            oneboard.json.loads((self.site / "data" / "config.json").read_text(encoding="utf-8")),
            {"retries": 3},
        )
        self.assertIn("FROM python", (self.site / "Dockerfile").read_text(encoding="utf-8"))

    def test_codex_update_works_in_an_empty_workspace(self):
        empty_site = self.workspace_path / "empty-site"
        empty_site.mkdir()
        self.connect(empty_site)
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.user_id),
            )

        ai_response = {
            "summary": "Created the first note.",
            "files": [{"path": "notes.txt", "content": "hello workspace"}],
        }

        with mock.patch.object(
            oneboard,
            "run_ai_provider_prompt",
            return_value=(oneboard.json.dumps(ai_response), {"total_tokens": 7}, "muse-text-1.0"),
        ), mock.patch.object(
            oneboard,
            "get_muse_models",
            return_value=["muse-text-1.0", "muse-image-1.0"],
        ):
            response = self.client.post(
                "/api/site-manager/codex-update",
                json={"prompt": "Create a notes file"},
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual((empty_site / "notes.txt").read_text(encoding="utf-8"), "hello workspace")

    def test_codex_update_still_rejects_unsafe_file_paths(self):
        self.connect()
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-muse-key", self.user_id),
            )

        for unsafe_path in ("../escape.txt", "photo.png", ".git/hooks/x"):
            ai_response = {
                "summary": "Trying something unsafe.",
                "files": [{"path": unsafe_path, "content": "nope"}],
            }
            with mock.patch.object(
                oneboard,
                "run_ai_provider_prompt",
                return_value=(oneboard.json.dumps(ai_response), {"total_tokens": 7}, "muse-text-1.0"),
            ), mock.patch.object(
                oneboard,
                "get_muse_models",
                return_value=["muse-text-1.0", "muse-image-1.0"],
            ):
                response = self.client.post(
                    "/api/site-manager/codex-update",
                    json={"prompt": "Do the unsafe thing"},
                )

            self.assertEqual(response.status_code, 400, unsafe_path)
        self.assertFalse((self.workspace_path / "escape.txt").exists())
        self.assertFalse((self.site / "photo.png").exists())

    def test_seo_page_creation_returns_a_specific_notification(self):
        self.connect()
        with mock.patch.object(
            oneboard,
            "run_site_codex_update",
            return_value={"exit_code": 0, "output": "Created.", "reply": "Created."},
        ):
            response = self.client.post(
                "/api/seo-suggestions/create",
                json={"title": "Local SEO Guide", "keyword": "local seo"},
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(
            response.get_json()["notification"],
            'SEO page "Local SEO Guide" for keyword "local seo" was created from SEO Opportunities. Review it in Site Manager before publishing.',
        )

    def test_site_manager_seo_page_creation_returns_a_specific_notification(self):
        self.connect()
        with self.client.session_transaction() as session:
            session["lang"] = "es"
        with mock.patch.object(
            oneboard,
            "run_site_codex_update",
            return_value={"exit_code": 0, "output": "Created.", "reply": "Created."},
        ):
            response = self.client.post(
                "/api/site-manager/seo-content",
                json={"title": "Local SEO Guide", "keyword": "local seo"},
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(
            response.get_json()["notification"],
            'SEO page "Local SEO Guide" for keyword "local seo" was created in Site Manager. Review it before publishing.',
        )

    def test_asset_upload_rejects_empty_and_fake_images(self):
        self.connect()
        missing = self.client.post("/api/site-manager/assets/upload", data={})
        fake = self.client.post(
            "/api/site-manager/assets/upload",
            data={"asset": (io.BytesIO(b"not an image"), "fake.png")},
            content_type="multipart/form-data",
        )

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(fake.status_code, 400)

        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        valid = self.client.post(
            "/api/site-manager/assets/upload",
            data={"asset": (io.BytesIO(png), "pixel.png")},
            content_type="multipart/form-data",
        )
        self.assertEqual(valid.status_code, 200, valid.get_data(as_text=True))
        self.assertEqual(len(valid.get_json()["manager"]["assets"]), 1)

    def test_oneboard_symlink_cannot_redirect_uploads_or_codex_state(self):
        external = self.workspace_path / "external-state"
        external.mkdir()
        (self.site / ".oneboard").symlink_to(external, target_is_directory=True)
        self.connect()
        png = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )

        response = self.client.post(
            "/api/site-manager/assets/upload",
            data={"asset": (io.BytesIO(png), "pixel.png")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(list(external.iterdir()), [])
        with oneboard.app.app_context():
            with self.assertRaises(ValueError):
                oneboard.build_site_command_env(str(self.site))

    def test_symlink_inside_oneboard_private_tree_is_rejected(self):
        private_home = self.site / ".oneboard" / "home"
        private_home.mkdir(parents=True)
        external_auth = self.workspace_path / "external-auth.json"
        external_auth.write_text("do-not-touch", encoding="utf-8")
        (private_home / "auth.json").symlink_to(external_auth)
        self.connect()

        with oneboard.app.app_context():
            with self.assertRaises(ValueError):
                oneboard.build_site_command_env(str(self.site))
        self.assertEqual(external_auth.read_text(encoding="utf-8"), "do-not-touch")

    def test_reserved_internal_paths_are_case_insensitive(self):
        internal = self.site / ".oneboard" / "home"
        internal.mkdir(parents=True)
        (internal / "auth.json").write_text("secret", encoding="utf-8")
        self.connect()

        with oneboard.app.app_context():
            with self.assertRaises(ValueError):
                oneboard.resolve_site_file(self.user_id, ".ONEBOARD/home/auth.json")

    def test_publish_requires_approved_update_before_rsync(self):
        self.connect()
        with oneboard.app.app_context():
            oneboard.save_remote_connection(
                self.user_id,
                "example.com",
                "22",
                "deploy",
                "/srv/site",
                "",
                "key",
                "",
            )
            oneboard.record_update_history(self.user_id, "codex", "pending change", "0")
            update_id = oneboard.list_update_history(self.user_id)[0]["id"]
        self.bind_remote_to_current_site()

        with mock.patch.object(oneboard, "run_rsync_local_to_remote") as rsync:
            blocked = self.client.post(
                "/api/site-manager/update/action",
                json={"update_id": update_id, "action": "publish"},
            )
            self.assertEqual(blocked.status_code, 400)
            rsync.assert_not_called()

            approved = self.client.post(
                "/api/site-manager/update/action",
                json={"update_id": update_id, "action": "approve"},
            )
            self.assertEqual(approved.status_code, 200, approved.get_data(as_text=True))
            published = self.client.post(
                "/api/site-manager/update/action",
                json={"update_id": update_id, "action": "publish"},
            )
            self.assertEqual(published.status_code, 200, published.get_data(as_text=True))
            rsync.assert_called_once()

            second_site = self.workspace_path / "site-b"
            second_site.mkdir()
            (second_site / "index.html").write_text("second", encoding="utf-8")
            self.connect(second_site)
            with oneboard.app.app_context():
                oneboard.record_update_history(
                    self.user_id,
                    "codex",
                    "second site change",
                    "0",
                    status="approved",
                )
                second_update_id = oneboard.list_update_history(self.user_id)[0]["id"]
            rsync.reset_mock()
            mismatched = self.client.post(
                "/api/site-manager/update/action",
                json={"update_id": second_update_id, "action": "publish"},
            )
            self.assertEqual(mismatched.status_code, 400)
            rsync.assert_not_called()

        with oneboard.app.app_context():
            self.assertEqual(oneboard.get_update_history_item(self.user_id, update_id)["status"], "published")

    def test_publish_rejects_symlink_that_points_outside_site(self):
        self.connect()
        external = self.workspace_path / "external.txt"
        external.write_text("safe", encoding="utf-8")
        (self.site / "leak.txt").symlink_to(external)
        with oneboard.app.app_context():
            oneboard.save_remote_connection(
                self.user_id,
                "example.com",
                "22",
                "deploy",
                "/srv/site",
                "",
                "key",
                "",
            )
            oneboard.record_update_history(self.user_id, "codex", "approved", "0", status="approved")
            update_id = oneboard.list_update_history(self.user_id)[0]["id"]
        self.bind_remote_to_current_site()

        with mock.patch.object(oneboard, "run_rsync_local_to_remote") as rsync:
            response = self.client.post(
                "/api/site-manager/update/action",
                json={"update_id": update_id, "action": "publish"},
            )

        self.assertEqual(response.status_code, 400)
        rsync.assert_not_called()

    def test_publish_rejects_absolute_symlink_even_when_target_is_inside_site(self):
        self.connect()
        target = self.site / "real.txt"
        target.write_text("real", encoding="utf-8")
        (self.site / "absolute-link.txt").symlink_to(target.resolve())
        with oneboard.app.app_context():
            oneboard.save_remote_connection(
                self.user_id,
                "example.com",
                "22",
                "deploy",
                "/srv/site",
                "",
                "key",
                "",
            )
            oneboard.record_update_history(self.user_id, "codex", "approved", "0", status="approved")
            update_id = oneboard.list_update_history(self.user_id)[0]["id"]
        self.bind_remote_to_current_site()

        with mock.patch.object(oneboard, "run_rsync_local_to_remote") as rsync:
            response = self.client.post(
                "/api/site-manager/update/action",
                json={"update_id": update_id, "action": "publish"},
            )

        self.assertEqual(response.status_code, 400)
        rsync.assert_not_called()

    @unittest.skipUnless(hasattr(os, "mkfifo"), "FIFO creation is unavailable")
    def test_publish_rejects_special_files_before_remote_transfer(self):
        self.connect()
        fifo = self.site / "build.pipe"
        os.mkfifo(fifo)
        with oneboard.app.app_context():
            oneboard.save_remote_connection(
                self.user_id,
                "example.com",
                22,
                "deploy",
                "/srv/site",
                "",
                "key",
                "",
            )
            oneboard.record_update_history(
                self.user_id,
                "codex",
                "approved",
                "0",
                status="approved",
            )
            update_id = oneboard.list_update_history(self.user_id)[0]["id"]
        self.bind_remote_to_current_site()

        with mock.patch.object(oneboard, "run_rsync_local_to_remote") as rsync:
            response = self.client.post(
                "/api/site-manager/update/action",
                json={"update_id": update_id, "action": "publish"},
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("special", response.get_json()["error"].lower())
        rsync.assert_not_called()

    def test_failed_codex_update_is_recorded_and_can_be_restored(self):
        self.connect()
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-key", self.user_id),
            )

            def fail_after_change(*_args, **_kwargs):
                (self.site / "index.html").write_text("partial change", encoding="utf-8")
                return {
                    "command": "muse direct site update",
                    "cwd": str(self.site),
                    "exit_code": 1,
                    "output": "Muse failed",
                    "reply": "Muse failed",
                    "started_at": "2026-08-05 00:00:00",
                }

            with mock.patch.object(oneboard, "run_site_ai_fallback_update", side_effect=fail_after_change):
                with self.assertRaises(ValueError):
                    oneboard.run_site_codex_update(self.user_id, "Change the homepage")

            update = oneboard.list_update_history(self.user_id)[0]
            self.assertEqual(update["status"], "failed")
            self.assertEqual((self.site / "index.html").read_text(encoding="utf-8"), "original")
            oneboard.restore_update_files(self.user_id, update["id"])

        self.assertEqual((self.site / "index.html").read_text(encoding="utf-8"), "original")

    def test_codex_created_unsafe_symlink_is_recorded_and_rolled_back(self):
        self.connect()
        external = self.workspace_path / "external.txt"
        external.write_text("safe", encoding="utf-8")
        link = self.site / "leak.txt"
        with oneboard.app.app_context():
            oneboard.execute_db(
                "UPDATE users SET muse_api_key = ? WHERE id = ?",
                ("test-key", self.user_id),
            )

            def create_unsafe_link(*_args, **_kwargs):
                link.symlink_to(external)
                return {
                    "command": "muse direct site update",
                    "cwd": str(self.site),
                    "exit_code": 0,
                    "output": "done",
                    "reply": "done",
                    "started_at": "2026-08-05 00:00:00",
                }

            with mock.patch.object(oneboard, "run_site_ai_fallback_update", side_effect=create_unsafe_link):
                with self.assertRaises(ValueError):
                    oneboard.run_site_codex_update(self.user_id, "Create a link")

            update = oneboard.list_update_history(self.user_id)[0]
            self.assertEqual(update["status"], "failed")
            self.assertEqual(update["files"][0]["kind"], "symlink")
        self.assertFalse(os.path.lexists(link))
        self.assertEqual(external.read_text(encoding="utf-8"), "safe")

    def test_backup_preflight_rejects_reserved_paths_before_mutation(self):
        self.connect()
        extra = self.site / "extra.txt"
        extra.write_text("keep-extra", encoding="utf-8")
        bad_backup = self.workspace_path / "reserved.zip"
        with zipfile.ZipFile(bad_backup, "w") as archive:
            archive.writestr("index.html", "restored")
            archive.writestr(".oneboard/evil.txt", "unsafe")
        with oneboard.app.app_context():
            oneboard.execute_db(
                """
                INSERT INTO website_backups (user_id, directory_path, filename, backup_path, file_count, size_bytes)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (self.user_id, str(self.site.resolve()), "reserved.zip", str(bad_backup), 2, bad_backup.stat().st_size),
            )
            backup_id = oneboard.query_db(
                "SELECT id FROM website_backups WHERE user_id = ? ORDER BY id DESC",
                (self.user_id,),
                one=True,
            )["id"]

        response = self.client.post("/api/site-manager/restore", json={"backup_id": backup_id})

        self.assertEqual(response.status_code, 400)
        self.assertEqual((self.site / "index.html").read_text(encoding="utf-8"), "original")
        self.assertEqual(extra.read_text(encoding="utf-8"), "keep-extra")

    def test_update_restore_validates_every_item_before_mutation(self):
        self.connect()
        snapshot = self.workspace_path / "snapshot.zip"
        with zipfile.ZipFile(snapshot, "w") as archive:
            archive.writestr("index.html", "original")
        (self.site / "index.html").write_text("changed", encoding="utf-8")
        with oneboard.app.app_context():
            oneboard.record_update_history(
                self.user_id,
                "codex",
                "mixed snapshot",
                "0",
                snapshot_path=str(snapshot),
                changed_files=[
                    {"path": "index.html", "change": "modified"},
                    {"path": ".oneboard/evil.txt", "change": "created"},
                ],
            )
            update_id = oneboard.list_update_history(self.user_id)[0]["id"]

        response = self.client.post(
            "/api/site-manager/update/action",
            json={"update_id": update_id, "action": "restore"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual((self.site / "index.html").read_text(encoding="utf-8"), "changed")

    def test_update_restore_handles_file_replaced_by_directory(self):
        original = self.site / "feature"
        original.write_text("original-file", encoding="utf-8")
        with oneboard.app.app_context():
            before = oneboard.build_workspace_manifest(str(self.site))
            snapshot = oneboard.create_update_snapshot(self.user_id, str(self.site))
            original.unlink()
            original.mkdir()
            (original / "child.txt").write_text("new child", encoding="utf-8")
            after = oneboard.build_workspace_manifest(str(self.site))
            changes = oneboard.compare_workspace_manifests(before, after)
            oneboard.restore_workspace_changes(str(self.site), snapshot, changes)

        self.assertTrue(original.is_file())
        self.assertEqual(original.read_text(encoding="utf-8"), "original-file")

    def test_update_restore_handles_directory_replaced_by_symlink(self):
        original_dir = self.site / "content"
        original_dir.mkdir()
        original_file = original_dir / "page.html"
        original_file.write_text("original-page", encoding="utf-8")
        external = self.workspace_path / "external-content"
        external.mkdir()
        with oneboard.app.app_context():
            before = oneboard.build_workspace_manifest(str(self.site))
            snapshot = oneboard.create_update_snapshot(self.user_id, str(self.site))
            original_file.unlink()
            original_dir.rmdir()
            original_dir.symlink_to(external, target_is_directory=True)
            after = oneboard.build_workspace_manifest(str(self.site))
            changes = oneboard.compare_workspace_manifests(before, after)
            oneboard.restore_workspace_changes(str(self.site), snapshot, changes)

        self.assertTrue(original_dir.is_dir())
        self.assertFalse(original_dir.is_symlink())
        self.assertEqual(original_file.read_text(encoding="utf-8"), "original-page")

    def test_corrupt_update_snapshot_returns_json_error(self):
        self.connect()
        bad_snapshot = self.workspace_path / "bad.zip"
        bad_snapshot.write_bytes(b"not a zip")
        with oneboard.app.app_context():
            oneboard.record_update_history(
                self.user_id,
                "codex",
                "bad snapshot",
                "0",
                snapshot_path=str(bad_snapshot),
                changed_files=[{"path": "index.html", "change": "modified"}],
            )
            update_id = oneboard.list_update_history(self.user_id)[0]["id"]

        response = self.client.post(
            "/api/site-manager/update/action",
            json={"update_id": update_id, "action": "restore"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.is_json)
        self.assertFalse(response.get_json()["ok"])

    def test_password_expect_receives_secret_only_through_stdin(self):
        secret = "päss word-'$-unique"
        secret_hex = secret.encode("utf-8").hex()
        script_paths = []
        remote = {
            "host": "example.com",
            "port": 22,
            "username": "deploy",
            "remote_path": "/srv/site",
            "key_path": "",
            "auth_method": "password",
            "password": secret,
        }

        def fake_run(command, **kwargs):
            script_path = command[2]
            script_paths.append(script_path)
            command_text = " ".join(command)
            self.assertNotIn(secret, command_text)
            self.assertNotIn(secret_hex, command_text)
            self.assertEqual(kwargs["input"], f"{secret_hex}\n")
            self.assertFalse(any(secret in str(value) for value in kwargs["env"].values()))
            script = Path(script_path).read_text(encoding="utf-8")
            self.assertNotIn(secret, script)
            self.assertNotIn(secret_hex, script)
            return subprocess.CompletedProcess(command, 0, f"ok {secret}", secret_hex)

        with mock.patch.object(oneboard, "find_system_expect", return_value="/usr/bin/expect"):
            with mock.patch.object(oneboard.subprocess, "run", side_effect=fake_run):
                completed = oneboard.run_remote_process(remote, ["ssh", "deploy@example.com"], 30)

        self.assertEqual(len(script_paths), 1)
        self.assertFalse(os.path.exists(script_paths[0]))
        self.assertNotIn(secret, completed.stdout)
        self.assertNotIn(secret_hex, completed.stderr)

    @unittest.skipUnless(oneboard.find_system_expect(), "system expect is unavailable")
    def test_password_expect_drives_a_real_tty_prompt_without_network(self):
        secret = "local-expect-test-ñ"
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()
        child_code = (
            "import getpass,hashlib,sys; "
            "value=getpass.getpass('Password:'); "
            "sys.exit(0 if hashlib.sha256(value.encode()).hexdigest()==sys.argv[1] else 9)"
        )
        remote = {
            "auth_method": "password",
            "password": secret,
        }

        completed = oneboard.run_remote_process(
            remote,
            [sys.executable, "-c", child_code, digest],
            timeout=10,
        )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertNotIn(secret, completed.stdout)
        self.assertNotIn(secret, completed.stderr)

    def test_remote_test_uses_unsaved_draft_and_checks_the_probe(self):
        manager = self.connect()
        expected_path = manager["directory"]["path"]
        result = {
            "success": True,
            "ok": True,
            "message": "ready",
            "detail": "ready",
            "host": "draft.example.com",
            "port": 2222,
            "username": "deploy",
            "remote_path": "/srv/draft",
            "readable": True,
            "writable": True,
            "rsync_available": True,
        }
        with mock.patch.object(oneboard, "test_remote_connection", return_value=result) as remote_test:
            response = self.client.post(
                "/api/site-manager/remote/test",
                json={
                    "host": "draft.example.com",
                    "port": 2222,
                    "username": "deploy",
                    "remote_path": "/srv/draft",
                    "key_path": "",
                    "auth_method": "key",
                    "password": "",
                    "expected_directory_path": expected_path,
                },
            )

        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        self.assertEqual(response.get_json()["remote_test"], result)
        remote_test.assert_called_once()
        tested_remote = remote_test.call_args.args[0]
        self.assertEqual(tested_remote["host"], "draft.example.com")
        self.assertEqual(tested_remote["port"], 2222)
        with oneboard.app.app_context():
            self.assertIsNone(oneboard.get_remote_connection_private(self.user_id))

    def test_remote_probe_requires_directory_access_and_remote_rsync(self):
        remote = {
            "host": "example.com",
            "port": 22,
            "username": "deploy",
            "remote_path": "/srv/site with spaces",
            "key_path": "",
            "auth_method": "key",
            "password": "",
        }

        def successful_probe(_remote, command, timeout):
            self.assertEqual(timeout, 30)
            self.assertIn("test -d", command[-1])
            self.assertIn("test -r", command[-1])
            self.assertIn("test -w", command[-1])
            self.assertIn("pwd -P", command[-1])
            self.assertIn("ONEBOARD_REMOTE_PARENT_UNWRITABLE", command[-1])
            self.assertIn("ONEBOARD_REMOTE_ROOT_USER", command[-1])
            self.assertIn("command -v rsync", command[-1])
            return subprocess.CompletedProcess(command, 0, "ONEBOARD_REMOTE_READY\n", "")

        with mock.patch.object(oneboard, "build_remote_ssh_arguments", return_value=["ssh"]):
            with mock.patch.object(oneboard, "run_remote_process", side_effect=successful_probe):
                result = oneboard.test_remote_connection(remote)
        self.assertTrue(result["success"])
        self.assertTrue(result["rsync_available"])

        missing = subprocess.CompletedProcess(
            ["ssh"],
            44,
            "ONEBOARD_REMOTE_RSYNC_MISSING\n",
            "",
        )
        with mock.patch.object(oneboard, "build_remote_ssh_arguments", return_value=["ssh"]):
            with mock.patch.object(oneboard, "run_remote_process", return_value=missing):
                with self.assertRaisesRegex(ValueError, "rsync"):
                    oneboard.test_remote_connection(remote)

    def test_private_known_hosts_path_is_quoted_for_openssh(self):
        remote = {
            "host": "example.com",
            "port": 22,
            "username": "deploy",
            "remote_path": "/srv/site",
            "key_path": "",
            "auth_method": "key",
            "password": "",
        }
        known_hosts = "/Users/example/Library/Application Support/ONEBoard/known_hosts"
        with mock.patch.object(oneboard, "ensure_remote_known_hosts_file", return_value=known_hosts):
            with mock.patch.object(oneboard.shutil, "which", return_value="/usr/bin/ssh"):
                arguments = oneboard.build_remote_ssh_arguments(remote)

        self.assertIn(f'UserKnownHostsFile="{known_hosts}"', arguments)
        self.assertIn("IdentitiesOnly=yes", arguments)
        self.assertIn("ClearAllForwardings=yes", arguments)

    def test_rsync_transfer_does_not_request_owner_group_or_special_files(self):
        remote = {
            "host": "example.com",
            "port": 22,
            "username": "deploy",
            "remote_path": "/srv/site",
            "key_path": "",
            "auth_method": "key",
            "password": "",
        }
        completed = subprocess.CompletedProcess(["rsync"], 0, "", "")
        with mock.patch.object(oneboard.shutil, "which", return_value="/usr/bin/rsync"):
            with mock.patch.object(oneboard, "build_remote_ssh_command", return_value="ssh-safe"):
                with mock.patch.object(oneboard, "run_remote_process", return_value=completed) as process:
                    oneboard.run_rsync(remote, "source/", "destination/")

        command = process.call_args.args[1]
        self.assertIn("-rlptz", command)
        self.assertNotIn("-a", command)
        self.assertNotIn("-D", command)
        self.assertNotIn("--devices", command)
        self.assertNotIn("--specials", command)

    def test_saved_password_is_reused_only_for_the_same_login(self):
        with oneboard.app.app_context():
            oneboard.save_remote_connection(
                self.user_id,
                "first.example.com",
                22,
                "deploy",
                "/srv/site",
                "",
                "password",
                "secret-one",
            )
            same_login = oneboard.build_remote_connection_candidate(
                self.user_id,
                "first.example.com",
                22,
                "deploy",
                "/srv/other",
                "",
                "password",
                "",
            )
            self.assertEqual(same_login["password"], "secret-one")
            with self.assertRaises(ValueError):
                oneboard.build_remote_connection_candidate(
                    self.user_id,
                    "second.example.com",
                    22,
                    "deploy",
                    "/srv/site",
                    "",
                    "password",
                    "",
                )

            oneboard.save_remote_connection(
                self.user_id,
                "first.example.com",
                22,
                "deploy",
                "/srv/site",
                "",
                "key",
                "",
            )
            self.assertEqual(oneboard.get_remote_connection_private(self.user_id)["password"], "")

    def test_remote_sync_uses_managed_workspace_and_backs_up_before_resync(self):
        self.connect()
        with oneboard.app.app_context():
            oneboard.save_remote_connection(
                self.user_id,
                "example.com",
                22,
                "deploy",
                "/srv/site",
                "",
                "key",
                "",
            )
            self.assertIsNone(
                oneboard.get_remote_connection_private(self.user_id)["directory_path"]
            )

        sync_count = 0

        def fake_pull(_remote, workspace_path):
            nonlocal sync_count
            sync_count += 1
            Path(workspace_path, "index.html").write_text(
                f"remote-{sync_count}",
                encoding="utf-8",
            )

        with mock.patch.object(oneboard, "run_rsync_remote_to_local", side_effect=fake_pull):
            with oneboard.app.app_context():
                workspace_path = oneboard.sync_remote_site_to_workspace(self.user_id)
                self.assertEqual(oneboard.get_site_directory(self.user_id)["path"], workspace_path)
                self.assertEqual(oneboard.list_site_backups(self.user_id), [])

                Path(workspace_path, "index.html").write_text("edited-before-resync", encoding="utf-8")
                oneboard.sync_remote_site_to_workspace(self.user_id)
                backups = oneboard.list_site_backups(self.user_id)

        self.assertEqual(sync_count, 2)
        self.assertEqual(Path(workspace_path, "index.html").read_text(encoding="utf-8"), "remote-2")
        self.assertEqual(len(backups), 1)
        with zipfile.ZipFile(backups[0]["backup_path"], "r") as archive:
            self.assertEqual(archive.read("index.html").decode("utf-8"), "edited-before-resync")

        rejected = self.client.post("/api/site-manager/connect", json={"path": workspace_path})
        self.assertEqual(rejected.status_code, 400)

    def test_remote_path_validation_rejects_dangerous_targets(self):
        dangerous_paths = (
            "/",
            "relative/site",
            "~/site",
            "/home/deploy",
            "/srv",
            "/etc/nginx/site",
            "/srv/../etc",
            "/srv//site",
            "/srv/site\nother",
        )
        for remote_path in dangerous_paths:
            with self.subTest(remote_path=remote_path):
                with self.assertRaises(ValueError):
                    oneboard.validate_remote_website_path(remote_path, "deploy")

        self.assertEqual(
            oneboard.validate_remote_website_path("/home/deploy/www/site/", "deploy"),
            "/home/deploy/www/site",
        )
        with self.assertRaises(ValueError):
            oneboard.validate_remote_identity("example.com", "root")

    def test_publish_uploads_only_to_a_derived_stage_before_activation(self):
        workspace = self.workspace_path / "publish-workspace"
        workspace.mkdir()
        (workspace / "index.html").write_text("release", encoding="utf-8")
        remote = {
            "host": "example.com",
            "port": 22,
            "username": "deploy",
            "remote_path": "/srv/site",
            "key_path": "",
            "auth_method": "key",
            "password": "",
        }
        stage = "/srv/.oneboard-stage-0123456789ab-0123456789abcdef"
        backup = "/srv/.oneboard-backup-0123456789ab-20260805030000-0123456789abcdef"

        with mock.patch.object(oneboard, "test_remote_connection") as remote_test:
            with mock.patch.object(oneboard, "prepare_remote_release", return_value=(stage, backup)):
                with mock.patch.object(oneboard, "run_rsync") as rsync:
                    with mock.patch.object(oneboard, "activate_remote_release") as activate:
                        result = oneboard.run_rsync_local_to_remote(remote, str(workspace))

        self.assertEqual(result, backup)
        remote_test.assert_called_once_with(remote)
        rsync.assert_called_once()
        destination = rsync.call_args.args[2]
        self.assertIn(stage, destination)
        self.assertNotIn("deploy@example.com:/srv/site/", destination)
        activate.assert_called_once_with(remote, stage, backup)

    def test_remote_release_activation_has_rollback_and_no_recursive_delete(self):
        remote = {
            "host": "example.com",
            "port": 22,
            "username": "deploy",
            "remote_path": "/srv/site",
            "key_path": "",
            "auth_method": "key",
            "password": "",
        }
        target_hash = hashlib.sha256(b"/srv/site").hexdigest()[:12]
        stage = f"/srv/.oneboard-stage-{target_hash}-0123456789abcdef"
        backup = f"/srv/.oneboard-backup-{target_hash}-20260805030000-0123456789abcdef"

        completed = subprocess.CompletedProcess(
            ["ssh"],
            0,
            "ONEBOARD_REMOTE_RELEASE_ACTIVE\n",
            "",
        )
        with mock.patch.object(oneboard, "run_remote_shell", return_value=completed) as remote_shell:
            oneboard.activate_remote_release(remote, stage, backup)

        script = remote_shell.call_args.args[1]
        self.assertIn("trap rollback_previous", script)
        self.assertIn('mv "$backup" "$target"', script)
        self.assertNotIn("rm -rf", script)
        self.assertNotIn("--delete", script)

    def test_failed_first_remote_rename_cannot_activate_or_nest_the_stage(self):
        parent = self.workspace_path / "remote-parent"
        target = parent / "site"
        target.mkdir(parents=True)
        (target / "index.html").write_text("live", encoding="utf-8")
        target_path = target.as_posix()
        target_hash = hashlib.sha256(target_path.encode("utf-8")).hexdigest()[:12]
        stage = parent / f".oneboard-stage-{target_hash}-0123456789abcdef"
        backup = parent / f".oneboard-backup-{target_hash}-20260805030000-0123456789abcdef"
        stage.mkdir()
        (stage / "index.html").write_text("staged", encoding="utf-8")

        fake_bin = self.workspace_path / "fake-bin"
        fake_bin.mkdir()
        fake_mv = fake_bin / "mv"
        fake_mv.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        fake_mv.chmod(0o700)
        remote = {
            "host": "example.com",
            "port": 22,
            "username": "deploy",
            "remote_path": target_path,
            "key_path": "",
            "auth_method": "key",
            "password": "",
        }

        def run_script(_remote, script, timeout):
            self.assertEqual(timeout, 90)
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:/usr/bin:/bin"
            return subprocess.run(
                ["/bin/sh", "-c", script],
                text=True,
                capture_output=True,
                env=environment,
                timeout=10,
            )

        with mock.patch.object(oneboard, "run_remote_shell", side_effect=run_script):
            with self.assertRaises(ValueError):
                oneboard.activate_remote_release(remote, stage.as_posix(), backup.as_posix())

        self.assertEqual((target / "index.html").read_text(encoding="utf-8"), "live")
        self.assertEqual((stage / "index.html").read_text(encoding="utf-8"), "staged")
        self.assertFalse(backup.exists())
        self.assertFalse((target / stage.name).exists())

    def test_failed_second_remote_rename_restores_the_live_target(self):
        parent = self.workspace_path / "rollback-parent"
        target = parent / "site"
        target.mkdir(parents=True)
        (target / "index.html").write_text("live", encoding="utf-8")
        target_path = target.as_posix()
        target_hash = hashlib.sha256(target_path.encode("utf-8")).hexdigest()[:12]
        stage = parent / f".oneboard-stage-{target_hash}-0123456789abcdef"
        backup = parent / f".oneboard-backup-{target_hash}-20260805030000-0123456789abcdef"
        stage.mkdir()
        (stage / "index.html").write_text("staged", encoding="utf-8")

        fake_bin = self.workspace_path / "second-mv-fake-bin"
        fake_bin.mkdir()
        fake_mv = fake_bin / "mv"
        fake_mv.write_text(
            "#!/bin/sh\ncase \"$1\" in *.oneboard-stage-*) exit 1 ;; esac\nexec /bin/mv \"$@\"\n",
            encoding="utf-8",
        )
        fake_mv.chmod(0o700)
        remote = {
            "host": "example.com",
            "port": 22,
            "username": "deploy",
            "remote_path": target_path,
            "key_path": "",
            "auth_method": "key",
            "password": "",
        }

        def run_script(_remote, script, timeout):
            self.assertEqual(timeout, 90)
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:/usr/bin:/bin"
            return subprocess.run(
                ["/bin/sh", "-c", script],
                text=True,
                capture_output=True,
                env=environment,
                timeout=10,
            )

        with mock.patch.object(oneboard, "run_remote_shell", side_effect=run_script):
            with self.assertRaises(ValueError):
                oneboard.activate_remote_release(remote, stage.as_posix(), backup.as_posix())

        self.assertEqual((target / "index.html").read_text(encoding="utf-8"), "live")
        self.assertEqual((stage / "index.html").read_text(encoding="utf-8"), "staged")
        self.assertFalse(backup.exists())

    def test_failed_remote_stage_seed_is_never_reported_ready(self):
        parent = self.workspace_path / "seed-parent"
        target = parent / "site"
        target.mkdir(parents=True)
        (target / "index.html").write_text("live", encoding="utf-8")
        fake_bin = self.workspace_path / "fake-rsync-bin"
        fake_bin.mkdir()
        fake_rsync = fake_bin / "rsync"
        fake_rsync.write_text("#!/bin/sh\nexit 9\n", encoding="utf-8")
        fake_rsync.chmod(0o700)
        remote = {
            "host": "example.com",
            "port": 22,
            "username": "deploy",
            "remote_path": target.as_posix(),
            "key_path": "",
            "auth_method": "key",
            "password": "",
        }
        observed = {}

        def run_script(_remote, script, timeout):
            self.assertEqual(timeout, 120)
            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}:/usr/bin:/bin"
            completed = subprocess.run(
                ["/bin/sh", "-c", script],
                text=True,
                capture_output=True,
                env=environment,
                timeout=10,
            )
            observed["completed"] = completed
            return completed

        with mock.patch.object(oneboard, "run_remote_shell", side_effect=run_script):
            with self.assertRaisesRegex(ValueError, "active website was not changed"):
                oneboard.prepare_remote_release(remote)

        self.assertNotEqual(observed["completed"].returncode, 0)
        self.assertNotIn("ONEBOARD_REMOTE_STAGE_READY", observed["completed"].stdout)
        self.assertEqual((target / "index.html").read_text(encoding="utf-8"), "live")

    @unittest.skipUnless(shutil.which("rsync"), "rsync is unavailable")
    def test_remote_stage_and_activation_swap_release_and_keep_backup(self):
        parent = self.workspace_path / "successful-release"
        target = parent / "site"
        target.mkdir(parents=True)
        (target / "index.html").write_text("live", encoding="utf-8")
        remote = {
            "host": "example.com",
            "port": 22,
            "username": "deploy",
            "remote_path": target.as_posix(),
            "key_path": "",
            "auth_method": "key",
            "password": "",
        }

        def run_script(_remote, script, timeout):
            self.assertIn(timeout, {90, 120})
            return subprocess.run(
                ["/bin/sh", "-c", script],
                text=True,
                capture_output=True,
                env=os.environ.copy(),
                timeout=10,
            )

        with mock.patch.object(oneboard, "run_remote_shell", side_effect=run_script):
            stage_path, backup_path = oneboard.prepare_remote_release(remote)
            Path(stage_path, "index.html").write_text("new release", encoding="utf-8")
            oneboard.activate_remote_release(remote, stage_path, backup_path)

        self.assertEqual((target / "index.html").read_text(encoding="utf-8"), "new release")
        self.assertEqual(Path(backup_path, "index.html").read_text(encoding="utf-8"), "live")
        self.assertFalse(Path(stage_path).exists())

    def test_failed_remote_refresh_leaves_active_local_workspace_unchanged(self):
        with oneboard.app.app_context():
            oneboard.save_remote_connection(
                self.user_id,
                "example.com",
                22,
                "deploy",
                "/srv/site",
                "",
                "key",
                "",
            )

            def first_pull(_remote, destination):
                Path(destination, "index.html").write_text("downloaded", encoding="utf-8")

            with mock.patch.object(oneboard, "run_rsync_remote_to_local", side_effect=first_pull):
                workspace_path = oneboard.sync_remote_site_to_workspace(self.user_id)

            def failed_pull(_remote, destination):
                Path(destination, "index.html").write_text("partial", encoding="utf-8")
                raise ValueError("network interrupted")

            with mock.patch.object(oneboard, "run_rsync_remote_to_local", side_effect=failed_pull):
                with self.assertRaisesRegex(ValueError, "network interrupted"):
                    oneboard.sync_remote_site_to_workspace(self.user_id)

        self.assertEqual(Path(workspace_path, "index.html").read_text(encoding="utf-8"), "downloaded")

    def test_failed_remote_publish_keeps_update_approved(self):
        self.connect()
        with oneboard.app.app_context():
            oneboard.save_remote_connection(
                self.user_id,
                "example.com",
                22,
                "deploy",
                "/srv/site",
                "",
                "key",
                "",
            )
            oneboard.record_update_history(
                self.user_id,
                "codex",
                "approved release",
                "0",
                status="approved",
            )
            update_id = oneboard.list_update_history(self.user_id)[0]["id"]
        self.bind_remote_to_current_site()

        with mock.patch.object(
            oneboard,
            "run_rsync_local_to_remote",
            side_effect=ValueError("activation failed"),
        ):
            response = self.client.post(
                "/api/site-manager/update/action",
                json={"update_id": update_id, "action": "publish"},
            )

        self.assertEqual(response.status_code, 400)
        with oneboard.app.app_context():
            self.assertEqual(oneboard.get_update_history_item(self.user_id, update_id)["status"], "approved")

    def test_concurrent_site_operation_is_rejected_without_mutation(self):
        ready = threading.Event()
        release = threading.Event()

        def hold_operation_lock():
            with oneboard.site_operation_lock(self.user_id):
                ready.set()
                release.wait(5)

        holder = threading.Thread(target=hold_operation_lock, daemon=True)
        holder.start()
        self.assertTrue(ready.wait(2))
        try:
            response = self.client.post(
                "/api/site-manager/connect",
                json={"path": str(self.site)},
            )
        finally:
            release.set()
            holder.join(2)

        self.assertEqual(response.status_code, 400)
        self.assertIn("progress", response.get_json()["error"].lower())
        with oneboard.app.app_context():
            self.assertIsNone(oneboard.get_site_directory(self.user_id))


if __name__ == "__main__":
    unittest.main()
