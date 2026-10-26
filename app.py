import base64
import email.message
import os
import difflib
import hashlib
import ipaddress
import json
import mimetypes
import posixpath
import re
import secrets
import shlex
import shutil
import smtplib
import socket
import stat as stat_module
import subprocess
import sqlite3
import ssl
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from functools import wraps

import click
from flask import (
    Flask,
    abort,
    flash,
    g,
    has_request_context,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    send_file,
    send_from_directory,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = os.path.abspath(os.path.dirname(__file__))
RESOURCE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
APP_DATA_DIR = os.environ.get(
    "ONEBOARD_DATA_DIR",
    os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else BASE_DIR,
)
DATABASE = os.path.join(APP_DATA_DIR, "oneboard.db")
BACKUP_DIR = os.path.join(APP_DATA_DIR, "backups")
UPLOAD_DIR = os.path.join(APP_DATA_DIR, "uploads")
AVATAR_DIR = os.path.join(UPLOAD_DIR, "avatars")
COMPANY_LOGO_DIR = os.path.join(UPLOAD_DIR, "company-logos")
REMOTE_WORKSPACE_DIR = os.path.join(APP_DATA_DIR, "remote-sites")
SSH_KEY_DIR = os.path.join(APP_DATA_DIR, "ssh-keys")
REMOTE_SSH_DIR = os.path.join(APP_DATA_DIR, "remote-ssh")
REMOTE_KNOWN_HOSTS_PATH = os.path.join(REMOTE_SSH_DIR, "known_hosts")
MAX_IMAGE_UPLOAD_BYTES = 20 * 1024 * 1024
SITE_RESERVED_COMPONENTS = {".git", ".oneboard", "__pycache__"}
PASSWORD_HASH_METHOD = "pbkdf2:sha256"
SITE_DIRECTORY_ENV_KEYS = ("ONEBOARD_SITE_DIRECTORY", "WEBSITE_DIRECTORY")
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
SEARCH_CONSOLE_API = "https://www.googleapis.com/webmasters/v3"
SEARCH_CONSOLE_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
SUPPORTED_LANGUAGES = {"en", "es"}
DEFAULT_LANGUAGE = "en"
IS_WINDOWS = os.name == "nt"
DEFAULT_AI_PROVIDER = "muse"
AI_PROVIDER_MODELS = {
    "muse": ["muse-image-1.0"],
    "anthropic": ["claude-sonnet-4", "claude-3-5-haiku"],
    "openrouter": ["anthropic/claude-sonnet-4", "google/gemini-2.5-pro"],
    "google": ["gemini-2.5-pro", "gemini-2.5-flash"],
}
MUSE_API_BASE = "https://api.meta.ai/v1"
MUSE_FALLBACK_MODELS = ["muse-image-1.0"]
MUSE_IMAGE_DEFAULT_MODEL = "muse-image-1.0"

EXPECT_PASSWORD_SCRIPT = r"""
set timeout [lindex $argv 0]
set command [lrange $argv 1 end]
log_user 1

if {[gets stdin password_hex] < 0} {
    puts stderr "ONEBOARD_EXPECT_INPUT_ERROR"
    exit 98
}

set password [binary format H* $password_hex]
set password_hex ""
set password_sent 0
spawn -noecho {*}$command
fconfigure $spawn_id -encoding binary -translation binary

expect {
    -nocase -re {password:} {
        if {$password_sent >= 1} {
            puts stderr "ONEBOARD_EXPECT_AUTH_REJECTED"
            close
            catch wait
            exit 77
        }
        incr password_sent
        send -raw -- $password
        send -- "\r"
        set password ""
        exp_continue
    }
    eof {
        set result [wait]
        exit [lindex $result 3]
    }
    timeout {
        puts stderr "ONEBOARD_EXPECT_TIMEOUT"
        close
        catch wait
        exit 124
    }
}
""".strip()

SITE_OPERATION_LOCKS = {}
SITE_OPERATION_LOCKS_GUARD = threading.Lock()

TRANSLATIONS = {
    "en": {
        "nav.dashboard": "Dashboard",
        "nav.seo": "SEO",
        "nav.site_manager": "Site Manager",
        "nav.security_scan": "Security Scan",
        "nav.help": "Help",
        "nav.settings": "Settings",
        "nav.logout": "Sign out",
        "language.en": "English",
        "language.es": "Spanish",
        "auth.login_title": "Sign in",
        "auth.register_title": "Create account",
        "auth.email": "Email",
        "auth.password": "Password",
        "auth.name": "Name",
        "auth.confirm_password": "Confirm password",
        "auth.password_placeholder": "Your password",
        "auth.min_password": "Minimum 8 characters",
        "auth.repeat_password": "Repeat password",
        "auth.sign_in": "Sign in",
        "auth.create_account": "Create account",
        "auth.forgot_password": "Forgot password?",
        "auth.reset_title": "Reset password",
        "auth.reset_instructions": "Enter your account email and ONEBoard will prepare a secure reset link.",
        "auth.reset_password": "Reset password",
        "auth.new_password": "New password",
        "auth.reset_link": "Password reset link",
        "auth.reset_link_note": "Development mode: use this link to complete the reset. Configure email delivery before production use.",
        "auth.no_account": "Don't have an account?",
        "auth.has_account": "Already have an account?",
        "dashboard.kicker": "Google Search Console",
        "dashboard.title": "SEO Analytics",
        "dashboard.integration": "Integration",
        "dashboard.connected_select": "Connected. Select a property to view data.",
        "dashboard.connect_prompt": "Connect the Google account that has access to the Search Console property.",
        "dashboard.disconnect": "Disconnect",
        "dashboard.connect_google": "Connect Google",
        "dashboard.missing_google": "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are missing. They must be configured privately on the server to enable Google connection.",
        "dashboard.property": "Property",
        "dashboard.apply": "Apply",
        "dashboard.top_keywords": "Top keywords",
        "dashboard.traffic_pages": "Pages with traffic",
        "dashboard.no_keywords": "No keywords are available for the selected range.",
        "dashboard.no_pages": "Connect a property to view detected pages.",
        "dashboard.performance": "Performance",
        "dashboard.click_distribution": "Click distribution",
        "dashboard.top_pages_chart": "Top pages by impressions",
        "dashboard.search_health": "Search health",
        "dashboard.search_health_connected": "Search Console is connected and ready for reporting.",
        "dashboard.search_health_waiting": "Connect Search Console to unlock live performance insights.",
        "dashboard.active_property": "Active property",
        "dashboard.reporting_window": "Reporting window",
        "dashboard.data_source": "Data source",
        "dashboard.live_google": "Google Search Console",
        "dashboard.pending_connection": "Pending connection",
        "dashboard.no_chart_data": "No chart data is available yet.",
        "dashboard.date_to": "to",
        "dashboard.seo_opportunities": "SEO opportunities",
        "dashboard.no_seo_opportunities": "Connect Search Console and select a property to generate page ideas.",
        "dashboard.create_page": "Create page",
        "dashboard.idea_source": "Based on Search Console demand",
        "dashboard.expected_page": "Suggested page",
        "metric.clicks": "Clicks",
        "metric.impressions": "Impressions",
        "metric.ctr": "CTR",
        "metric.position": "Position",
        "metric.page": "Page",
        "settings.account": "Account",
        "settings.title": "Settings",
        "settings.profile": "Profile",
        "settings.security": "Security",
        "settings.preferences": "Preferences",
        "settings.company": "Company",
        "settings.company_name": "Company name",
        "settings.company_email": "Company email",
        "settings.company_website": "Company website",
        "settings.company_logo": "Company logo",
        "settings.company_logo_note": "This logo becomes the app logo in the dashboard.",
        "settings.avatar": "Profile photo",
        "settings.avatar_note": "Upload a square image for the best result.",
        "settings.language": "Language",
        "settings.current_password": "Current password",
        "settings.new_password": "New password",
        "settings.confirm_new_password": "Confirm new password",
        "settings.google_note": "Google is managed privately on the server. Use the dashboard connection button to authorize your Search Console account.",
        "settings.muse": "Muse API",
        "settings.muse_note": "Store your Muse API key here so AI website updates and image generation are billed to your own account.",
        "settings.muse_api_key": "Muse API key",
        "settings.muse_api_key_placeholder": "Leave blank to keep the saved key",
        "settings.muse_configured": "API key saved",
        "settings.client_id": "Client ID",
        "settings.client_secret": "Client Secret",
        "settings.redirect_uri": "Redirect URI",
        "settings.configured": "Configured",
        "settings.pending": "Pending",
        "settings.update": "Update settings",
        "site.kicker": "Website operations",
        "site.title": "Site Manager",
        "site.directory": "Website directory",
        "site.directory_note": "Enter the local website directory this account can manage. AI updates, backups, and the terminal stay inside this path.",
        "site.directory_env_note": "The website directory is assigned by the developer for the selected Search Console property.",
        "site.path": "Directory path",
        "site.path_placeholder": "C:\\Sites\\example.com",
        "site.connect": "Connect directory",
        "site.connected": "Connected",
        "site.not_connected": "Not connected",
        "site.last_updated": "Last updated",
        "site.terminal": "Terminal",
        "site.command": "Command",
        "site.command_placeholder": "nano index.html",
        "site.run_command": "Run command",
        "site.codex_update": "Update website",
        "site.codex_prompt": "Message Muse",
        "site.codex_prompt_placeholder": "Ask for the next website change...",
        "site.codex_image": "Suggested image",
        "site.codex_image_note": "Optional. Muse will use this image only for this update request.",
        "site.asset_library": "Asset library",
        "site.asset_upload": "Upload asset",
        "site.asset_empty": "No reusable images have been uploaded yet.",
        "site.use_asset": "Use image",
        "site.selected_asset": "Selected image",
        "site.quick_actions": "Quick actions",
        "site.quick_hero": "Update hero",
        "site.quick_section": "Add section",
        "site.quick_cta": "Improve CTA",
        "site.quick_landing": "Create landing",
        "site.seo_writer": "SEO writer",
        "site.seo_title": "Page title",
        "site.seo_keyword": "Keyword",
        "site.seo_tone": "Tone",
        "site.seo_audience": "Audience",
        "site.seo_cta": "Call to action",
        "site.create_content": "Create content",
        "site.diff": "Diff",
        "site.no_diff": "No text diff was captured for this update.",
        "site.approve": "Approve",
        "site.publish": "Publish",
        "site.restore_files": "Restore files",
        "site.pending": "Pending",
        "site.approved": "Approved",
        "site.published": "Published",
        "site.publish_requires_approval": "Approve this update before publishing it.",
        "site.update_directory_mismatch": "This update belongs to a different website directory.",
        "site.directory_changed": "The selected website directory changed. Refresh Site Manager and try again.",
        "site.operation_in_progress": "Another website operation is already in progress. Wait for it to finish and try again.",
        "site.snapshot_invalid": "The update snapshot is invalid or damaged.",
        "site.restored": "Restored",
        "site.run_codex": "Send",
        "site.codex_empty": "No Muse messages yet.",
        "site.codex_working": "Muse is working...",
        "site.exit_code": "Exit code",
        "site.backups": "Backups",
        "site.create_backup": "Create backup",
        "site.no_backups": "No backups have been created yet.",
        "site.restore": "Restore",
        "site.restore_confirm": "I understand this will replace the current website directory with this backup.",
        "site.filename": "File",
        "site.created": "Created",
        "site.size": "Size",
        "site.files": "Files",
        "site.output": "Output",
        "site.no_output": "Command finished without output.",
        "site.terminal_ready": "Restricted terminal ready. Allowed tool: the platform editor.",
        "site.remote": "Remote deploy",
        "site.tab_studio": "Studio",
        "site.tab_files": "Files",
        "site.tab_remote": "Remote",
        "site.remote_note": "Store the SSH/SFTP target for publishing this local workspace to a remote server.",
        "site.remote_host": "Host",
        "site.remote_port": "Port",
        "site.remote_user": "User",
        "site.remote_path": "Remote path",
        "site.remote_key_path": "SSH key path",
        "site.remote_auth_method": "Auth method",
        "site.remote_auth_key": "SSH key",
        "site.remote_auth_password": "Password",
        "site.remote_password": "SSH password",
        "site.remote_password_placeholder": "Leave blank to keep saved password",
        "site.remote_connect": "Save remote",
        "site.remote_sync": "Sync from remote",
        "site.remote_sync_note": "Install the public key on the server before syncing with SSH key authentication.",
        "site.ssh_key_setup": "SSH key setup",
        "site.ssh_key_note": "Generate a dedicated ONEBoard key, install the public key on your server, then save the remote connection using this key path.",
        "site.ssh_key_generate": "Generate SSH key",
        "site.ssh_key_public": "Public key",
        "site.ssh_key_install_command": "Install command",
        "site.ssh_key_path": "Private key path",
        "site.ssh_key_copy": "Copy",
        "site.ssh_key_help_button": "Help",
        "site.ssh_help_title": "Step-by-step SSH key help",
        "site.ssh_help_intro": "Follow these steps from your own computer. Replace the examples with your real server user and IP address.",
        "site.ssh_help_step_1_title": "1. Create the ONEBoard key",
        "site.ssh_help_step_1_body": "Click Generate SSH key. ONEBoard creates a private key and a public key. Keep the private key secret; the public key is safe to install on the server.",
        "site.ssh_help_step_2_title": "2. Save the remote server details",
        "site.ssh_help_step_2_body": "Enter the server IP or domain, port 22, the SSH user, and the website folder on the server. Example users are ubuntu, deploy, or root, depending on how the server was created.",
        "site.ssh_help_step_3_title": "3. Open a terminal on your computer",
        "site.ssh_help_step_3_body": "Run this test first. It confirms that the server answers before you install the key.",
        "site.ssh_help_step_3_command": "ssh USER@SERVER_IP",
        "site.ssh_help_step_4_title": "4. Install the public key on the server",
        "site.ssh_help_step_4_body": "If the test asks for a password and lets you in, copy the install command below, paste it in your terminal, and press Enter. It adds the ONEBoard public key to the server user's authorized_keys file.",
        "site.ssh_help_step_5_title": "5. Test login with the key",
        "site.ssh_help_step_5_body": "After installing the key, run this command again. If it opens the server without asking for the password, SSH key setup is ready.",
        "site.ssh_help_step_5_command": "ssh -i PRIVATE_KEY_PATH USER@SERVER_IP",
        "site.ssh_help_step_6_title": "6. Save and sync in ONEBoard",
        "site.ssh_help_step_6_body": "Paste the private key path shown above into SSH key path, choose SSH key as the auth method, save the remote connection, then run Sync from remote.",
        "site.ssh_help_replace_title": "What to replace",
        "site.ssh_help_replace_body": "USER is the server username, such as ubuntu. SERVER_IP is the server IP or domain. PRIVATE_KEY_PATH is the private key path shown in ONEBoard.",
        "site.ssh_help_trouble_title": "If something fails",
        "site.ssh_help_trouble_body": "Connection refused means SSH is not running or port 22 is blocked. Permission denied means the key is not installed for that user, or the username is wrong.",
        "site.remote_connected": "Remote configured",
        "site.remote_not_connected": "No remote target",
        "site.remote_directory_mismatch": "Save the remote connection for the current website directory before publishing.",
        "site.remote_test_ready": "Remote SSH connection and website directory are ready.",
        "site.remote_path_missing": "The remote website directory does not exist.",
        "site.remote_path_unreadable": "The remote website directory is not readable by this SSH user.",
        "site.remote_path_unwritable": "The remote website directory is not writable by this SSH user.",
        "site.remote_parent_unwritable": "The SSH user cannot create a safe release beside the remote website directory.",
        "site.remote_path_unsafe": "Choose a specific, absolute remote website directory. System roots, home folders, aliases, and parent references are not allowed.",
        "site.remote_path_changed": "The remote website path resolves somewhere else. Use its canonical directory path before continuing.",
        "site.remote_root_user": "For safety, ONEBoard cannot publish a website through the root SSH account. Use a dedicated deployment user.",
        "site.remote_rsync_missing": "rsync is not installed on the remote server.",
        "site.remote_empty_workspace": "The local website workspace is empty, so publishing was stopped.",
        "site.remote_staging_failed": "The remote release could not be prepared. The active website was not changed.",
        "site.remote_activation_failed": "The staged release could not be activated. The previous remote website was restored.",
        "site.update_history": "Update history",
        "site.no_updates": "No website updates have been recorded yet.",
        "site.files_explorer": "Files",
        "site.current_folder": "Current folder",
        "site.parent_folder": "Parent folder",
        "site.preview": "Preview",
        "site.delete": "Delete",
        "site.delete_confirm": "Delete this file from the connected website directory.",
        "site.preview_unavailable": "Preview is not available for this file type.",
        "site.file_deleted": "File deleted.",
        "site.file_delete_failed": "Could not delete file: {error}",
        "site.file_missing": "File not found.",
        "site.file_outside_workspace": "File path is outside the connected website directory.",
        "site.internal_directory_unsafe": "The website's .oneboard directory is not safe. Remove aliases or symbolic links named .oneboard and try again.",
        "site.unsafe_symlink": "The website contains a symbolic link that points outside its directory: {path}",
        "site.unsupported_entry": "The website contains an unsupported device, socket, or special file: {path}",
        "site.file_delete_directory": "Delete files only from this panel.",
        "site.backup_directory_mismatch": "This backup belongs to a different website directory.",
        "scan.kicker": "Passive analysis",
        "scan.public_domain": "Public domain",
        "scan.title": "Scan any domain",
        "scan.intro": "ONEBoard reviews passive signals: basic DNS, HTTPS response, TLS certificate, security headers, and exposed technology. It does not run attacks or intrusive tests.",
        "scan.domain": "Domain",
        "scan.analyze": "Analyze",
        "scan.score": "Score",
        "scan.grade": "Grade",
        "scan.executed": "Executed",
        "scan.tls": "SSL / TLS",
        "scan.certificate": "Certificate",
        "scan.valid": "Valid",
        "scan.not_validated": "Not validated",
        "scan.issuer": "Issuer",
        "scan.protocol": "Protocol",
        "scan.cipher": "Cipher",
        "scan.expiration": "Expiration",
        "scan.days": "days",
        "scan.not_available": "Not available",
        "scan.hsts": "HSTS",
        "scan.active": "Active",
        "scan.not_detected": "Not detected",
        "scan.resolution": "Resolution",
        "scan.correct": "Correct",
        "scan.no_response": "No response",
        "scan.addresses": "Addresses",
        "scan.security_headers": "HTTP Security Headers",
        "scan.available": "Available",
        "scan.unavailable": "Unavailable",
        "scan.http_to_https": "HTTP to HTTPS",
        "scan.redirects": "Redirects",
        "scan.not_confirmed": "Not confirmed",
        "scan.status": "Status",
        "scan.final_url": "Final URL",
        "scan.tech_stack": "Technology Stack",
        "scan.passive": "Passive",
        "scan.server": "Server",
        "scan.not_exposed": "Not exposed",
        "scan.no_stack_hints": "No clear stack hints were detected in public headers.",
        "scan.recommendations": "Recommendations",
        "scan.external_tools": "External verification tools",
        "scan.history": "Scan history",
        "scan.history_empty": "No security scans have been saved yet.",
        "scan.progress": "Progress",
        "scan.latest_scans": "Latest scans",
        "scan.score_change": "Change",
        "scan.missing_headers": "Missing headers",
        "priority.critical": "critical",
        "priority.high": "high",
        "priority.medium": "medium",
        "priority.low": "low",
        "flash.login_required": "Sign in to continue.",
        "flash.email_password_required": "Enter your email and password.",
        "flash.account_missing": "No account exists with that email.",
        "flash.password_incorrect": "The password is incorrect.",
        "flash.login_success": "Signed in successfully.",
        "flash.account_exists": "An account already exists with that email.",
        "flash.register_success": "Account created. You can now sign in.",
        "flash.reset_email_sent": "If that account exists, a password reset link has been prepared.",
        "flash.reset_token_invalid": "The reset link is invalid or expired.",
        "flash.password_reset_success": "Password updated. You can now sign in.",
        "flash.current_password_required": "Enter your current password to change email or password.",
        "flash.current_password_invalid": "The current password is incorrect.",
        "flash.email_invalid": "Enter a valid email.",
        "flash.password_update_mismatch": "The new passwords do not match.",
        "flash.avatar_invalid": "Upload a PNG, JPG, JPEG, GIF, or WEBP image.",
        "flash.asset_required": "Choose an image to upload.",
        "flash.scan_failed": "The scan could not be completed: {error}",
        "flash.name_required": "Enter the account name.",
        "flash.settings_updated": "Settings updated successfully.",
        "flash.google_credentials_missing": "Google private credentials are missing on the server.",
        "flash.google_denied": "Google did not authorize the connection: {error}.{detail}",
        "flash.google_state_invalid": "The Google connection could not be validated. Try again.",
        "flash.google_code_missing": "Google did not return an authorization code.",
        "flash.search_console_failed": "Search Console could not be connected. {error}",
        "flash.search_console_connected": "Google Search Console connected successfully.",
        "flash.connect_before_site": "Connect Google Search Console before selecting a site.",
        "flash.select_property": "Select a Search Console property.",
        "flash.property_selected": "Property selected successfully.",
        "flash.search_console_disconnected": "Google Search Console was disconnected.",
        "flash.logout_success": "Signed out successfully.",
        "flash.site_path_required": "Enter a website directory path.",
        "flash.site_path_missing": "The directory does not exist.",
        "flash.site_path_not_directory": "The path is not a directory.",
        "flash.site_path_unsafe": "Choose a dedicated website folder, not a system, home, or ONEBoard data directory.",
        "flash.site_connected": "Website directory connected.",
        "flash.site_directory_unmapped": "Connect a website directory first.",
        "flash.seo_page_created": 'SEO page "{title}" for keyword "{keyword}" was created from SEO Opportunities. Review it in Site Manager before publishing.',
        "flash.site_manager_seo_page_created": 'SEO page "{title}" for keyword "{keyword}" was created in Site Manager. Review it before publishing.',
        "flash.seo_fields_required": "Enter a page title and target keyword.",
        "flash.remote_required": "Configure a remote SSH target first.",
        "flash.remote_synced": "Remote website synced into the editable workspace.",
        "flash.remote_sync_failed": "Remote sync failed: {error}",
        "flash.remote_published": "Website published to the remote server.",
        "flash.remote_password_tool_missing": "Password SSH requires the system expect tool. Use an SSH key if expect is unavailable.",
        "flash.remote_password_required": "Enter the SSH password or switch to SSH key authentication.",
        "flash.remote_timeout": "The remote synchronization timed out after 240 seconds.",
        "flash.remote_permission_denied": "The server rejected the SSH login. Install the generated public key in the server user's ~/.ssh/authorized_keys, verify the SSH user, and then run Sync from remote.",
        "flash.ssh_key_generated": "SSH key generated. Copy the public key or install command to your server.",
        "flash.ssh_key_failed": "SSH key setup failed: {error}",
        "flash.site_env_managed": "The website directory is managed by environment variables.",
        "flash.site_required": "Connect a website directory first.",
        "flash.command_required": "Enter a command to run.",
        "flash.codex_prompt_required": "Enter what Muse should change.",
        "flash.codex_auth_missing": "Add your Muse API key in Settings before using AI updates.",
        "flash.codex_failed": "Muse could not complete the website update: {error}",
        "flash.command_timeout": "The command timed out after 30 seconds.",
        "flash.sandbox_unavailable": "The system sandbox is not available, so commands cannot be run safely.",
        "flash.command_outside_workspace": "This command references a path outside the connected directory.",
        "flash.command_not_allowed": "Only the platform editor is allowed in this terminal.",
        "flash.backup_created": "Backup created successfully.",
        "flash.backup_failed": "Backup failed: {error}",
        "flash.restore_confirm_required": "Confirm that you understand the restore will replace the current website directory.",
        "flash.backup_missing": "Backup not found.",
        "flash.restore_complete": "Website restored from backup.",
        "flash.restore_failed": "Restore failed: {error}",
        "scan.error.domain_required": "Enter a domain to scan.",
        "scan.error.domain_too_long": "The domain is too long.",
        "scan.error.no_ip": "Enter a domain, not an IP address.",
        "scan.error.invalid_domain": "Enter a valid domain, for example example.com.",
        "scan.error.dns_failed": "DNS did not resolve the domain: {error}",
        "scan.verdict.strong": "Strong posture for a passive analysis.",
        "scan.verdict.good": "Good foundation, with visible improvements available.",
        "scan.verdict.attention": "Functional configuration, but it needs attention.",
        "scan.verdict.risk": "High risk or insufficient information to validate basic controls.",
    },
    "es": {
        "nav.dashboard": "Dashboard",
        "nav.seo": "SEO",
        "nav.site_manager": "Administrador del sitio",
        "nav.security_scan": "Escaneo de seguridad",
        "nav.help": "Ayuda",
        "nav.settings": "Configuración",
        "nav.logout": "Salir",
        "language.en": "Inglés",
        "language.es": "Español",
        "auth.login_title": "Iniciar sesión",
        "auth.register_title": "Crear cuenta",
        "auth.email": "Correo electrónico",
        "auth.password": "Contraseña",
        "auth.name": "Nombre",
        "auth.confirm_password": "Confirmar contraseña",
        "auth.password_placeholder": "Tu contraseña",
        "auth.min_password": "Mínimo 8 caracteres",
        "auth.repeat_password": "Repite la contraseña",
        "auth.sign_in": "Entrar",
        "auth.create_account": "Crear cuenta",
        "auth.forgot_password": "¿Olvidaste la contraseña?",
        "auth.reset_title": "Recuperar contraseña",
        "auth.reset_instructions": "Escribe el email de la cuenta y ONEBoard preparará un enlace seguro para restablecerla.",
        "auth.reset_password": "Restablecer contraseña",
        "auth.new_password": "Nueva contraseña",
        "auth.reset_link": "Enlace de recuperación",
        "auth.reset_link_note": "Modo desarrollo: usa este enlace para completar la recuperación. Configura envío de email antes de producción.",
        "auth.no_account": "¿No tienes cuenta?",
        "auth.has_account": "¿Ya tienes cuenta?",
        "dashboard.kicker": "Google Search Console",
        "dashboard.title": "Analítica SEO",
        "dashboard.integration": "Integración",
        "dashboard.connected_select": "Conectado. Selecciona una propiedad para ver los datos.",
        "dashboard.connect_prompt": "Conecta la cuenta de Google que tiene acceso a la propiedad de Search Console.",
        "dashboard.disconnect": "Desconectar",
        "dashboard.connect_google": "Conectar Google",
        "dashboard.missing_google": "Faltan GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET. Deben estar configuradas de forma privada en el servidor para activar la conexión con Google.",
        "dashboard.property": "Propiedad",
        "dashboard.apply": "Aplicar",
        "dashboard.top_keywords": "Keywords principales",
        "dashboard.traffic_pages": "Páginas con tráfico",
        "dashboard.no_keywords": "No hay keywords disponibles para el rango consultado.",
        "dashboard.no_pages": "Conecta una propiedad para ver las páginas detectadas.",
        "dashboard.performance": "Rendimiento",
        "dashboard.click_distribution": "Distribucion de clicks",
        "dashboard.top_pages_chart": "Paginas principales por impresiones",
        "dashboard.search_health": "Estado de busqueda",
        "dashboard.search_health_connected": "Search Console esta conectado y listo para reportes.",
        "dashboard.search_health_waiting": "Conecta Search Console para activar metricas en vivo.",
        "dashboard.active_property": "Propiedad activa",
        "dashboard.reporting_window": "Ventana de reporte",
        "dashboard.data_source": "Fuente de datos",
        "dashboard.live_google": "Google Search Console",
        "dashboard.pending_connection": "Conexion pendiente",
        "dashboard.no_chart_data": "Aun no hay datos disponibles para graficar.",
        "dashboard.date_to": "a",
        "dashboard.seo_opportunities": "Oportunidades SEO",
        "dashboard.no_seo_opportunities": "Conecta Search Console y selecciona una propiedad para generar ideas de páginas.",
        "dashboard.create_page": "Crear página",
        "dashboard.idea_source": "Basado en demanda de Search Console",
        "dashboard.expected_page": "Página sugerida",
        "metric.clicks": "Clicks",
        "metric.impressions": "Impresiones",
        "metric.ctr": "CTR",
        "metric.position": "Posición",
        "metric.page": "Página",
        "settings.account": "Cuenta",
        "settings.title": "Configuración",
        "settings.profile": "Perfil",
        "settings.security": "Seguridad",
        "settings.preferences": "Preferencias",
        "settings.company": "Compañía",
        "settings.company_name": "Nombre de la compañía",
        "settings.company_email": "Email de la compañía",
        "settings.company_website": "Website de la compañía",
        "settings.company_logo": "Logo de la compañía",
        "settings.company_logo_note": "Este logo se usará como logo de la app en el dashboard.",
        "settings.avatar": "Foto de perfil",
        "settings.avatar_note": "Sube una imagen cuadrada para mejor resultado.",
        "settings.language": "Idioma",
        "settings.current_password": "Contraseña actual",
        "settings.new_password": "Nueva contraseña",
        "settings.confirm_new_password": "Confirmar nueva contraseña",
        "settings.google_note": "La conexión con Google se gestiona de forma privada en el servidor. Usa el botón de conexión en el dashboard para autorizar tu cuenta de Search Console.",
        "settings.muse": "API de Muse",
        "settings.muse_note": "Guarda aquí tu API key de Muse para que las actualizaciones con IA y la generación de imágenes se facturen a tu propia cuenta.",
        "settings.muse_api_key": "API key de Muse",
        "settings.muse_api_key_placeholder": "Déjalo vacío para mantener la key guardada",
        "settings.muse_configured": "API key guardada",
        "settings.client_id": "Client ID",
        "settings.client_secret": "Client Secret",
        "settings.redirect_uri": "Redirect URI",
        "settings.configured": "Configurado",
        "settings.pending": "Pendiente",
        "settings.update": "Actualizar configuración",
        "site.kicker": "Operaciones del website",
        "site.title": "Administrador del sitio",
        "site.directory": "Directorio del website",
        "site.directory_note": "Ingresa el directorio local del website que esta cuenta puede administrar. Las actualizaciones con IA, backups y la terminal se mantienen dentro de esa ruta.",
        "site.directory_env_note": "El directorio del website es asignado por el desarrollador para la propiedad seleccionada de Search Console.",
        "site.path": "Ruta del directorio",
        "site.path_placeholder": "C:\\Sites\\example.com",
        "site.connect": "Conectar directorio",
        "site.connected": "Conectado",
        "site.not_connected": "No conectado",
        "site.last_updated": "Última actualización",
        "site.terminal": "Terminal",
        "site.command": "Comando",
        "site.command_placeholder": "nano index.html",
        "site.run_command": "Ejecutar comando",
        "site.codex_update": "Actualizar website",
        "site.codex_prompt": "Mensaje para Muse",
        "site.codex_prompt_placeholder": "Pide el próximo cambio del website...",
        "site.codex_image": "Imagen sugerida",
        "site.codex_image_note": "Opcional. Muse usará esta imagen solo para esta actualización.",
        "site.asset_library": "Biblioteca de assets",
        "site.asset_upload": "Subir asset",
        "site.asset_empty": "Todavía no hay imágenes reutilizables.",
        "site.use_asset": "Usar imagen",
        "site.selected_asset": "Imagen seleccionada",
        "site.quick_actions": "Acciones rápidas",
        "site.quick_hero": "Actualizar hero",
        "site.quick_section": "Agregar sección",
        "site.quick_cta": "Mejorar CTA",
        "site.quick_landing": "Crear landing",
        "site.seo_writer": "Redactor SEO",
        "site.seo_title": "Título de página",
        "site.seo_keyword": "Keyword",
        "site.seo_tone": "Tono",
        "site.seo_audience": "Audiencia",
        "site.seo_cta": "Llamado a la acción",
        "site.create_content": "Crear contenido",
        "site.diff": "Diff",
        "site.no_diff": "No se capturó diff de texto para esta actualización.",
        "site.approve": "Aprobar",
        "site.publish": "Publicar",
        "site.restore_files": "Restaurar archivos",
        "site.pending": "Pendiente",
        "site.approved": "Aprobado",
        "site.published": "Publicado",
        "site.publish_requires_approval": "Aprueba esta actualización antes de publicarla.",
        "site.update_directory_mismatch": "Esta actualización pertenece a otro directorio de website.",
        "site.directory_changed": "El directorio del sitio cambió. Actualiza Site Manager e inténtalo de nuevo.",
        "site.operation_in_progress": "Ya hay otra operación del website en curso. Espera a que termine e inténtalo de nuevo.",
        "site.snapshot_invalid": "El snapshot de la actualización es inválido o está dañado.",
        "site.restored": "Restaurado",
        "site.run_codex": "Enviar",
        "site.codex_empty": "Todavía no hay mensajes con Muse.",
        "site.codex_working": "Muse está trabajando...",
        "site.exit_code": "Código de salida",
        "site.backups": "Backups",
        "site.create_backup": "Crear backup",
        "site.no_backups": "Todavía no hay backups creados.",
        "site.restore": "Restaurar",
        "site.restore_confirm": "Entiendo que esto reemplazará el directorio actual del website con este backup.",
        "site.filename": "Archivo",
        "site.created": "Creado",
        "site.size": "Tamaño",
        "site.files": "Archivos",
        "site.output": "Salida",
        "site.no_output": "El comando terminó sin salida.",
        "site.terminal_ready": "Terminal restringida lista. Herramienta permitida: el editor de la plataforma.",
        "site.remote": "Deploy remoto",
        "site.tab_studio": "Studio",
        "site.tab_files": "Archivos",
        "site.tab_remote": "Remoto",
        "site.remote_note": "Guarda el destino SSH/SFTP para publicar este workspace local en un servidor remoto.",
        "site.remote_host": "Host",
        "site.remote_port": "Puerto",
        "site.remote_user": "Usuario",
        "site.remote_path": "Ruta remota",
        "site.remote_key_path": "Ruta de llave SSH",
        "site.remote_auth_method": "Método de acceso",
        "site.remote_auth_key": "Llave SSH",
        "site.remote_auth_password": "Contraseña",
        "site.remote_password": "Contraseña SSH",
        "site.remote_password_placeholder": "Déjalo vacío para mantener la contraseña guardada",
        "site.remote_connect": "Guardar remoto",
        "site.remote_sync": "Sincronizar remoto",
        "site.remote_sync_note": "Instala la llave pública en el servidor antes de sincronizar con autenticación por llave SSH.",
        "site.ssh_key_setup": "Configuración de llave SSH",
        "site.ssh_key_note": "Genera una llave dedicada de ONEBoard, instala la llave pública en tu servidor y luego guarda la conexión remota usando esta ruta.",
        "site.ssh_key_generate": "Generar llave SSH",
        "site.ssh_key_public": "Llave pública",
        "site.ssh_key_install_command": "Comando de instalación",
        "site.ssh_key_path": "Ruta de llave privada",
        "site.ssh_key_copy": "Copiar",
        "site.ssh_key_help_button": "Ayuda",
        "site.ssh_help_title": "Ayuda paso a paso para la llave SSH",
        "site.ssh_help_intro": "Sigue estos pasos desde tu propia computadora. Reemplaza los ejemplos con el usuario real y la IP real de tu servidor.",
        "site.ssh_help_step_1_title": "1. Crea la llave de ONEBoard",
        "site.ssh_help_step_1_body": "Haz clic en Generar llave SSH. ONEBoard crea una llave privada y una llave publica. La llave privada se mantiene en secreto; la llave publica se puede instalar en el servidor.",
        "site.ssh_help_step_2_title": "2. Guarda los datos del servidor remoto",
        "site.ssh_help_step_2_body": "Escribe la IP o dominio del servidor, puerto 22, el usuario SSH y la carpeta del website en el servidor. Usuarios comunes son ubuntu, deploy o root, segun como fue creado el servidor.",
        "site.ssh_help_step_3_title": "3. Abre una terminal en tu computadora",
        "site.ssh_help_step_3_body": "Primero ejecuta esta prueba. Sirve para confirmar que el servidor responde antes de instalar la llave.",
        "site.ssh_help_step_3_command": "ssh USUARIO@IP_DEL_SERVIDOR",
        "site.ssh_help_step_4_title": "4. Instala la llave publica en el servidor",
        "site.ssh_help_step_4_body": "Si la prueba pide contraseña y te deja entrar, copia el comando de instalación de abajo, pégalo en tu terminal y presiona Enter. Ese comando agrega la llave publica de ONEBoard al archivo authorized_keys del usuario del servidor.",
        "site.ssh_help_step_5_title": "5. Prueba el acceso con la llave",
        "site.ssh_help_step_5_body": "Después de instalar la llave, ejecuta este comando otra vez. Si abre el servidor sin pedir contraseña, la configuración SSH ya está lista.",
        "site.ssh_help_step_5_command": "ssh -i RUTA_DE_LLAVE_PRIVADA USUARIO@IP_DEL_SERVIDOR",
        "site.ssh_help_step_6_title": "6. Guarda y sincroniza en ONEBoard",
        "site.ssh_help_step_6_body": "Pega la ruta de llave privada mostrada arriba en Ruta de llave SSH, elige Llave SSH como método de acceso, guarda el remoto y luego ejecuta Sincronizar remoto.",
        "site.ssh_help_replace_title": "Qué reemplazar",
        "site.ssh_help_replace_body": "USUARIO es el usuario del servidor, por ejemplo ubuntu. IP_DEL_SERVIDOR es la IP o dominio del servidor. RUTA_DE_LLAVE_PRIVADA es la ruta de llave privada que muestra ONEBoard.",
        "site.ssh_help_trouble_title": "Si algo falla",
        "site.ssh_help_trouble_body": "Connection refused significa que SSH no está activo o el puerto 22 está bloqueado. Permission denied significa que la llave no está instalada para ese usuario, o que el usuario es incorrecto.",
        "site.remote_connected": "Remoto configurado",
        "site.remote_not_connected": "Sin destino remoto",
        "site.remote_directory_mismatch": "Guarda la conexión remota para el directorio actual antes de publicar.",
        "site.remote_test_ready": "La conexión SSH remota y el directorio del website están listos.",
        "site.remote_path_missing": "El directorio remoto del website no existe.",
        "site.remote_path_unreadable": "El usuario SSH no puede leer el directorio remoto del website.",
        "site.remote_path_unwritable": "El usuario SSH no puede escribir en el directorio remoto del website.",
        "site.remote_parent_unwritable": "El usuario SSH no puede crear una versión segura junto al directorio remoto del website.",
        "site.remote_path_unsafe": "Elige un directorio remoto específico y absoluto. No se permiten raíces del sistema, carpetas home, aliases ni referencias al directorio superior.",
        "site.remote_path_changed": "La ruta remota apunta a otro lugar. Usa la ruta canónica del directorio antes de continuar.",
        "site.remote_root_user": "Por seguridad, ONEBoard no puede publicar usando la cuenta SSH root. Usa un usuario dedicado para despliegues.",
        "site.remote_rsync_missing": "rsync no está instalado en el servidor remoto.",
        "site.remote_empty_workspace": "El workspace local está vacío; la publicación se detuvo.",
        "site.remote_staging_failed": "No se pudo preparar la versión remota. El website activo no fue modificado.",
        "site.remote_activation_failed": "No se pudo activar la versión preparada. Se restauró el website remoto anterior.",
        "site.update_history": "Historial de actualizaciones",
        "site.no_updates": "Todavía no hay actualizaciones registradas.",
        "site.files_explorer": "Archivos",
        "site.current_folder": "Carpeta actual",
        "site.parent_folder": "Carpeta superior",
        "site.preview": "Preview",
        "site.delete": "Eliminar",
        "site.delete_confirm": "Eliminar este archivo del directorio conectado del website.",
        "site.preview_unavailable": "El preview no está disponible para este tipo de archivo.",
        "site.file_deleted": "Archivo eliminado.",
        "site.file_delete_failed": "No se pudo eliminar el archivo: {error}",
        "site.file_missing": "Archivo no encontrado.",
        "site.file_outside_workspace": "La ruta está fuera del directorio conectado del website.",
        "site.internal_directory_unsafe": "La carpeta .oneboard del website no es segura. Elimina aliases o enlaces simbólicos llamados .oneboard e inténtalo de nuevo.",
        "site.unsafe_symlink": "El website contiene un enlace simbólico que apunta fuera de su directorio: {path}",
        "site.unsupported_entry": "El website contiene un dispositivo, socket o archivo especial no permitido: {path}",
        "site.file_delete_directory": "Desde este panel solo se eliminan archivos.",
        "site.backup_directory_mismatch": "Este backup pertenece a otro directorio de website.",
        "scan.kicker": "Análisis pasivo",
        "scan.public_domain": "Dominio público",
        "scan.title": "Escanea cualquier dominio",
        "scan.intro": "ONEBoard revisa señales pasivas: DNS básico, respuesta HTTPS, certificado TLS, cabeceras de seguridad y tecnología expuesta. No ejecuta ataques ni pruebas intrusivas.",
        "scan.domain": "Dominio",
        "scan.analyze": "Analizar",
        "scan.score": "Puntuación",
        "scan.grade": "Grado",
        "scan.executed": "Ejecutado",
        "scan.tls": "SSL / TLS",
        "scan.certificate": "Certificado",
        "scan.valid": "Válido",
        "scan.not_validated": "No validado",
        "scan.issuer": "Emisor",
        "scan.protocol": "Protocolo",
        "scan.cipher": "Cifrado",
        "scan.expiration": "Vencimiento",
        "scan.days": "días",
        "scan.not_available": "No disponible",
        "scan.hsts": "HSTS",
        "scan.active": "Activo",
        "scan.not_detected": "No detectado",
        "scan.resolution": "Resolución",
        "scan.correct": "Correcta",
        "scan.no_response": "Sin respuesta",
        "scan.addresses": "Direcciones",
        "scan.security_headers": "Cabeceras HTTP de seguridad",
        "scan.available": "Disponible",
        "scan.unavailable": "No disponible",
        "scan.http_to_https": "HTTP a HTTPS",
        "scan.redirects": "Redirige",
        "scan.not_confirmed": "No confirmado",
        "scan.status": "Status",
        "scan.final_url": "URL final",
        "scan.tech_stack": "Stack tecnológico",
        "scan.passive": "Pasivo",
        "scan.server": "Servidor",
        "scan.not_exposed": "No expuesto",
        "scan.no_stack_hints": "No se detectaron pistas claras del stack en cabeceras públicas.",
        "scan.recommendations": "Recomendaciones",
        "scan.external_tools": "Herramientas externas de verificación",
        "scan.history": "Historial de escaneos",
        "scan.history_empty": "Aún no hay escaneos de seguridad guardados.",
        "scan.progress": "Progreso",
        "scan.latest_scans": "Últimos escaneos",
        "scan.score_change": "Cambio",
        "scan.missing_headers": "Headers faltantes",
        "priority.critical": "crítica",
        "priority.high": "alta",
        "priority.medium": "media",
        "priority.low": "baja",
        "flash.login_required": "Inicia sesión para continuar.",
        "flash.email_password_required": "Ingresa tu correo y contraseña.",
        "flash.account_missing": "No existe una cuenta con ese correo.",
        "flash.password_incorrect": "La contraseña no es correcta.",
        "flash.login_success": "Sesión iniciada correctamente.",
        "flash.account_exists": "Ya existe una cuenta con ese correo.",
        "flash.register_success": "Cuenta creada. Ahora puedes iniciar sesión.",
        "flash.reset_email_sent": "Si esa cuenta existe, se preparó un enlace para recuperar la contraseña.",
        "flash.reset_token_invalid": "El enlace de recuperación es inválido o expiró.",
        "flash.password_reset_success": "Contraseña actualizada. Ya puedes iniciar sesión.",
        "flash.current_password_required": "Ingresa tu contraseña actual para cambiar email o contraseña.",
        "flash.current_password_invalid": "La contraseña actual es incorrecta.",
        "flash.email_invalid": "Ingresa un email válido.",
        "flash.password_update_mismatch": "Las nuevas contraseñas no coinciden.",
        "flash.avatar_invalid": "Sube una imagen PNG, JPG, JPEG, GIF o WEBP.",
        "flash.asset_required": "Selecciona una imagen para subir.",
        "flash.scan_failed": "No se pudo completar el análisis: {error}",
        "flash.name_required": "Ingresa el nombre de la cuenta.",
        "flash.settings_updated": "Configuración actualizada correctamente.",
        "flash.google_credentials_missing": "Faltan las credenciales privadas de Google en el servidor.",
        "flash.google_denied": "Google no autorizó la conexión: {error}.{detail}",
        "flash.google_state_invalid": "No se pudo validar la conexión con Google. Inténtalo de nuevo.",
        "flash.google_code_missing": "Google no devolvió un código de autorización.",
        "flash.search_console_failed": "No se pudo conectar Search Console. {error}",
        "flash.search_console_connected": "Google Search Console conectado correctamente.",
        "flash.connect_before_site": "Conecta Google Search Console antes de seleccionar un sitio.",
        "flash.select_property": "Selecciona una propiedad de Search Console.",
        "flash.property_selected": "Propiedad seleccionada correctamente.",
        "flash.search_console_disconnected": "Google Search Console fue desconectado.",
        "flash.logout_success": "Sesión cerrada correctamente.",
        "flash.site_path_required": "Ingresa la ruta del directorio del website.",
        "flash.site_path_missing": "El directorio no existe.",
        "flash.site_path_not_directory": "La ruta no es un directorio.",
        "flash.site_path_unsafe": "Selecciona una carpeta dedicada al website, no una carpeta del sistema, de inicio o de datos de ONEBoard.",
        "flash.site_connected": "Directorio del website conectado.",
        "flash.site_directory_unmapped": "Conecta primero un directorio del website.",
        "flash.seo_fields_required": "Ingresa un título de página y una keyword objetivo.",
        "flash.remote_required": "Configura primero un destino SSH remoto.",
        "flash.remote_synced": "Website remoto sincronizado al workspace editable.",
        "flash.remote_sync_failed": "Falló la sincronización remota: {error}",
        "flash.remote_published": "Website publicado en el servidor remoto.",
        "flash.remote_password_tool_missing": "SSH con contraseña requiere la herramienta expect del sistema. Usa una llave SSH si expect no está disponible.",
        "flash.remote_password_required": "Ingresa la contraseña SSH o cambia a autenticación con llave SSH.",
        "flash.remote_timeout": "La sincronización remota excedió el límite de 240 segundos.",
        "flash.remote_permission_denied": "El servidor rechazó el acceso SSH. Instala la llave pública generada en ~/.ssh/authorized_keys del usuario del servidor, verifica el usuario SSH y luego ejecuta Sincronizar remoto.",
        "flash.ssh_key_generated": "Llave SSH generada. Copia la llave pública o el comando de instalación en tu servidor.",
        "flash.ssh_key_failed": "Falló la configuración de llave SSH: {error}",
        "flash.site_env_managed": "El directorio del website se gestiona con variables de entorno.",
        "flash.site_required": "Conecta primero un directorio del website.",
        "flash.command_required": "Ingresa un comando para ejecutar.",
        "flash.codex_prompt_required": "Ingresa qué debe cambiar Muse.",
        "flash.codex_auth_missing": "Agrega tu API key de Muse en Configuración antes de usar las actualizaciones con IA.",
        "flash.codex_failed": "Muse no pudo completar la actualización del website: {error}",
        "flash.command_timeout": "El comando excedió el límite de 30 segundos.",
        "flash.sandbox_unavailable": "El sandbox del sistema no está disponible, así que no se pueden ejecutar comandos de forma segura.",
        "flash.command_outside_workspace": "Este comando referencia una ruta fuera del directorio conectado.",
        "flash.command_not_allowed": "Solo el editor de la plataforma está permitido en esta terminal.",
        "flash.backup_created": "Backup creado correctamente.",
        "flash.backup_failed": "Falló el backup: {error}",
        "flash.restore_confirm_required": "Confirma que entiendes que la restauración reemplazará el directorio actual del website.",
        "flash.backup_missing": "Backup no encontrado.",
        "flash.restore_complete": "Website restaurado desde el backup.",
        "flash.restore_failed": "Falló la restauración: {error}",
        "scan.error.domain_required": "Ingresa un dominio para analizar.",
        "scan.error.domain_too_long": "El dominio es demasiado largo.",
        "scan.error.no_ip": "Ingresa un dominio, no una dirección IP.",
        "scan.error.invalid_domain": "Ingresa un dominio válido, por ejemplo example.com.",
        "scan.error.dns_failed": "DNS no resolvió el dominio: {error}",
        "scan.verdict.strong": "Postura fuerte para un análisis pasivo.",
        "scan.verdict.good": "Buena base, con mejoras visibles.",
        "scan.verdict.attention": "Configuración funcional, pero requiere atención.",
        "scan.verdict.risk": "Riesgo alto o información insuficiente para validar controles básicos.",
    },
}


def current_language():
    if has_request_context():
        return getattr(g, "lang", session.get("lang", DEFAULT_LANGUAGE))
    return DEFAULT_LANGUAGE


def translate(key, **kwargs):
    language = current_language()
    text = TRANSLATIONS.get(language, TRANSLATIONS[DEFAULT_LANGUAGE]).get(
        key,
        TRANSLATIONS[DEFAULT_LANGUAGE].get(key, key),
    )
    return text.format(**kwargs) if kwargs else text


@contextmanager
def site_operation_lock(user_id):
    lock_key = str(user_id)
    with SITE_OPERATION_LOCKS_GUARD:
        lock = SITE_OPERATION_LOCKS.setdefault(lock_key, threading.RLock())
    if not lock.acquire(blocking=False):
        raise ValueError(translate("site.operation_in_progress"))
    try:
        yield
    finally:
        lock.release()


def locked_site_operation(function):
    @wraps(function)
    def wrapped(user_id, *args, **kwargs):
        with site_operation_lock(user_id):
            return function(user_id, *args, **kwargs)

    return wrapped


def language_url(language):
    args = request.args.to_dict(flat=True)
    args["lang"] = language
    return url_for(request.endpoint or "index", **request.view_args or {}, **args)


def create_app():
    app = Flask(
        __name__,
        template_folder=os.path.join(RESOURCE_DIR, "templates"),
        static_folder=os.path.join(RESOURCE_DIR, "static"),
    )
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
    app.config["MAX_CONTENT_LENGTH"] = MAX_IMAGE_UPLOAD_BYTES + (1024 * 1024)
    app.config["NATIVE_SERVICE_TOKEN"] = os.environ.get("ONEBOARD_SERVICE_TOKEN", "")

    @app.before_request
    def load_request_context():
        native_service_token = app.config["NATIVE_SERVICE_TOKEN"]
        if (
            native_service_token
            and request.path.startswith("/api/")
            and request.path != "/api/google-search-console/callback"
            and not secrets.compare_digest(
                request.headers.get("X-ONEBoard-Service-Token", ""),
                native_service_token,
            )
        ):
            return api_error("Unauthorized local service request.", 401)
        g.native_ai_credentials = native_ai_credentials()

        requested_language = request.args.get("lang")
        if requested_language in SUPPORTED_LANGUAGES:
            session["lang"] = requested_language
        g.lang = session.get("lang", DEFAULT_LANGUAGE)

        user_id = session.get("user_id")
        g.user = None

        if user_id is not None:
            g.user = query_db(
                """
                SELECT id, name, email, email_verified, avatar_path, company_name, company_email,
                      company_website, company_logo_path,
                      muse_api_key, muse_models_json, anthropic_api_key, openrouter_api_key, google_api_key,
                      ai_default_provider, ai_default_model,
                      created_at
                FROM users
                WHERE id = ?
                """,
                (user_id,),
                one=True,
            )

    @app.context_processor
    def inject_template_helpers():
        return {
            "current_lang": lambda: current_language(),
            "language_url": language_url,
            "t": translate,
        }

    @app.route("/uploads/avatars/<filename>")
    @login_required
    def uploaded_avatar(filename):
        return send_from_directory(AVATAR_DIR, filename)

    @app.route("/uploads/company-logos/<filename>")
    @login_required
    def uploaded_company_logo(filename):
        return send_from_directory(COMPANY_LOGO_DIR, filename)

    @app.route("/uploads/generated-images/<filename>")
    @login_required
    def uploaded_generated_image(filename):
        safe_name = posixpath.basename(filename or "")
        if not safe_name.startswith(f"user-{g.user['id']}-"):
            abort(404)
        return send_from_directory(generated_image_directory(), safe_name)

    @app.teardown_appcontext
    def close_db(error):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    @app.route("/")
    def index():
        if g.user:
            return redirect(url_for("dashboard"))
        return redirect(url_for("login"))

    @app.route("/login", methods=("GET", "POST"))
    def login():
        if g.user:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            error = None

            user = query_db("SELECT * FROM users WHERE email = ?", (email,), one=True)

            if not email or not password:
                error = translate("flash.email_password_required")
            elif user is None:
                error = translate("flash.account_missing")
            elif not verify_password(user["password_hash"], password):
                error = translate("flash.password_incorrect")
            elif not user["email_verified"]:
                error = "Verify your email before signing in. We can send a new verification link."

            if error is None:
                language = current_language()
                session.clear()
                session["lang"] = language
                session["user_id"] = user["id"]
                flash(translate("flash.login_success"), "success")
                return redirect(url_for("dashboard"))

            flash(error, "danger")

        return render_template("auth/login.html")

    @app.route("/register", methods=("GET", "POST"))
    def register():
        if g.user:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            error = validate_registration(name, email, password, confirm_password)

            if error is None:
                try:
                    execute_db(
                        """
                        INSERT INTO users (name, email, password_hash, email_verified)
                        VALUES (?, ?, ?, 0)
                        """,
                        (name, email, hash_password(password)),
                    )
                except sqlite3.IntegrityError:
                    error = translate("flash.account_exists")
                else:
                    user = query_db("SELECT id, email FROM users WHERE email = ?", (email,), one=True)
                    try:
                        send_email_verification(user["id"], user["email"])
                    except ValueError as delivery_error:
                        execute_db("DELETE FROM users WHERE id = ?", (user["id"],))
                        error = str(delivery_error)
                    else:
                        flash("Check your email to verify your account before signing in.", "success")
                        return redirect(url_for("login"))

            flash(error, "danger")

        return render_template("auth/register.html")

    @app.route("/verify-email/<token>")
    def verify_email(token):
        user_id = consume_email_verification_token(token)
        if not user_id:
            return render_template(
                "auth/email_verification_result.html",
                verified=False,
            )
        execute_db("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))
        return render_template(
            "auth/email_verification_result.html",
            verified=True,
        )

    @app.route("/resend-verification", methods=("POST",))
    def resend_verification():
        email = request.form.get("email", "").strip().lower()
        user = query_db(
            "SELECT id, email, email_verified FROM users WHERE email = ?",
            (email,),
            one=True,
        )
        if user and not user["email_verified"]:
            try:
                send_email_verification(user["id"], user["email"])
            except ValueError as error:
                flash(str(error), "danger")
                return redirect(url_for("login"))
        flash("If that account needs verification, a new link has been sent.", "info")
        return redirect(url_for("login"))

    @app.route("/forgot-password", methods=("GET", "POST"))
    def forgot_password():
        reset_link = None
        if g.user:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user = query_db("SELECT id FROM users WHERE email = ?", (email,), one=True)
            if user:
                token = create_password_reset_token(user["id"])
                reset_link = url_for("reset_password", token=token, _external=True)
            flash(translate("flash.reset_email_sent"), "info")

        return render_template("auth/forgot_password.html", reset_link=reset_link)

    @app.route("/reset-password/<token>", methods=("GET", "POST"))
    def reset_password(token):
        if g.user:
            return redirect(url_for("dashboard"))

        token_row = get_valid_password_reset_token(token)
        if not token_row:
            flash(translate("flash.reset_token_invalid"), "danger")
            return redirect(url_for("forgot_password"))

        if request.method == "POST":
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")
            if not password or len(password) < 8 or password != confirm_password:
                flash(translate("flash.password_incorrect"), "warning")
            else:
                execute_db(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (hash_password(password), token_row["user_id"]),
                )
                mark_password_reset_token_used(token_row["id"])
                flash(translate("flash.password_reset_success"), "success")
                return redirect(url_for("login"))

        return render_template("auth/reset_password.html", token=token)

    @app.route("/dashboard")
    @login_required
    def dashboard():
        gsc = build_search_console_dashboard(g.user["id"])
        return render_template("dashboard.html", gsc=gsc)

    @app.route("/api/session")
    def api_session():
        if not g.user:
            return jsonify({"ok": False, "authenticated": False}), 401
        return jsonify({"ok": True, "authenticated": True, "user": public_user(g.user)})

    @app.route("/api/auth/login", methods=("POST",))
    def api_login():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        user = query_db("SELECT * FROM users WHERE email = ?", (email,), one=True)
        if not email or not password or user is None or not verify_password(user["password_hash"], password):
            return jsonify({"ok": False, "error": translate("flash.password_incorrect")}), 401
        if not user["email_verified"]:
            return jsonify(
                {
                    "ok": False,
                    "error": "Verify your email before signing in.",
                    "verification_required": True,
                }
            ), 403

        language = current_language()
        session.clear()
        session["lang"] = language
        session["user_id"] = user["id"]
        return jsonify({"ok": True, "user": public_user(user)})

    @app.route("/api/auth/register", methods=("POST",))
    def api_register():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip().lower()
        password = data.get("password") or ""
        confirm_password = data.get("confirm_password") or ""
        error = validate_registration(name, email, password, confirm_password)
        if error:
            return api_error(error, 400)
        try:
            execute_db(
                """
                INSERT INTO users (name, email, password_hash, email_verified)
                VALUES (?, ?, ?, 0)
                """,
                (name, email, hash_password(password)),
            )
        except sqlite3.IntegrityError:
            return api_error(translate("flash.account_exists"), 400)

        user = query_db("SELECT * FROM users WHERE email = ?", (email,), one=True)
        try:
            send_email_verification(user["id"], user["email"])
        except ValueError as delivery_error:
            execute_db("DELETE FROM users WHERE id = ?", (user["id"],))
            return api_error(str(delivery_error), 503)
        return jsonify({"ok": True, "verification_required": True, "email": user["email"]})

    @app.route("/api/auth/resend-verification", methods=("POST",))
    def api_resend_verification():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        user = query_db(
            "SELECT id, email, email_verified FROM users WHERE email = ?",
            (email,),
            one=True,
        )
        if user and not user["email_verified"]:
            try:
                send_email_verification(user["id"], user["email"])
            except ValueError as error:
                return api_error(str(error), 503)
        return jsonify({"ok": True})

    @app.route("/api/auth/logout", methods=("POST",))
    @login_required
    def api_logout():
        language = current_language()
        session.clear()
        session["lang"] = language
        return jsonify({"ok": True})

    @app.route("/api/dashboard")
    @login_required
    def api_dashboard():
        return jsonify({"ok": True, "gsc": to_jsonable(build_search_console_dashboard(g.user["id"]))})

    @app.route("/api/google-search-console/connect")
    @login_required
    def api_google_search_console_connect():
        google_credentials = get_google_oauth_credentials()
        if not google_oauth_configured(google_credentials):
            return api_error(translate("flash.google_credentials_missing"), 400)

        state = secrets.token_urlsafe(32)
        code_verifier = secrets.token_urlsafe(64)
        save_google_oauth_state(g.user["id"], state, code_verifier)
        params = {
            "client_id": google_credentials["client_id"],
            "redirect_uri": google_native_redirect_uri(),
            "response_type": "code",
            "scope": SEARCH_CONSOLE_SCOPE,
            "access_type": "offline",
            "prompt": "consent select_account",
            "include_granted_scopes": "true",
            "state": state,
            "code_challenge": base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode("ascii")).digest()
            ).rstrip(b"=").decode("ascii"),
            "code_challenge_method": "S256",
        }
        return jsonify({"ok": True, "auth_url": f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"})

    @app.route("/api/google-search-console/callback")
    def api_google_search_console_callback():
        if request.args.get("error"):
            return google_native_callback_page(False, request.args.get("error_description") or request.args.get("error") or "Google authorization failed.")

        state = request.args.get("state", "")
        code = request.args.get("code", "")
        authorization = consume_google_oauth_state_user_id(state)
        if not authorization:
            return google_native_callback_page(False, translate("flash.google_state_invalid"))
        if not code:
            return google_native_callback_page(False, translate("flash.google_code_missing"))

        try:
            user_id, code_verifier = authorization
            token = exchange_google_code(
                user_id,
                code,
                redirect_uri=google_native_redirect_uri(),
                code_verifier=code_verifier,
            )
            save_google_connection(user_id, token)
        except GoogleApiError as error:
            return google_native_callback_page(False, str(error))

        return google_native_callback_page(True, translate("flash.search_console_connected"))

    @app.route("/api/google-search-console/site", methods=("POST",))
    @login_required
    def api_google_search_console_select_site():
        data = request.get_json(silent=True) or {}
        site_url = (data.get("site_url") or "").strip()
        connection = get_google_connection(g.user["id"])
        if not connection:
            return api_error(translate("flash.connect_before_site"), 400)
        if not site_url:
            return api_error(translate("flash.select_property"), 400)
        execute_db(
            """
            UPDATE google_search_console_connections
            SET selected_site_url = ?
            WHERE user_id = ?
            """,
            (site_url, g.user["id"]),
        )
        return jsonify({"ok": True, "gsc": to_jsonable(build_search_console_dashboard(g.user["id"]))})

    @app.route("/api/google-search-console/disconnect", methods=("POST",))
    @login_required
    def api_google_search_console_disconnect():
        connection = get_google_connection(g.user["id"])
        if connection:
            revoke_google_connection(connection)
        execute_db("DELETE FROM google_search_console_connections WHERE user_id = ?", (g.user["id"],))
        return jsonify({"ok": True, "gsc": to_jsonable(build_search_console_dashboard(g.user["id"]))})

    @app.route("/api/site-manager")
    @login_required
    def api_site_manager():
        return jsonify({"ok": True, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/site-manager/connect", methods=("POST",))
    @login_required
    def api_site_manager_connect():
        data = request_payload()
        try:
            with site_operation_lock(g.user["id"]):
                connect_site_directory(g.user["id"], (data.get("path") or "").strip())
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/site-manager/remote", methods=("POST",))
    @login_required
    def api_site_manager_remote_connect():
        data = request_payload()
        try:
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                save_remote_connection(
                    g.user["id"],
                    (data.get("host") or "").strip(),
                    str(data.get("port") or "").strip(),
                    (data.get("username") or "").strip(),
                    (data.get("remote_path") or "").strip(),
                    (data.get("key_path") or "").strip(),
                    (data.get("auth_method") or "").strip(),
                    data.get("password") or "",
                )
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/site-manager/remote/test", methods=("POST",))
    @login_required
    def api_site_manager_remote_test():
        data = request_payload()
        try:
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                remote = build_remote_connection_candidate(
                    g.user["id"],
                    (data.get("host") or "").strip(),
                    str(data.get("port") or "").strip(),
                    (data.get("username") or "").strip(),
                    (data.get("remote_path") or "").strip(),
                    (data.get("key_path") or "").strip(),
                    (data.get("auth_method") or "").strip(),
                    data.get("password") or "",
                )
                remote_test = test_remote_connection(remote)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify(
            {
                "ok": True,
                "remote_test": remote_test,
                "manager": to_jsonable(build_site_manager(g.user["id"])),
            }
        )

    @app.route("/api/site-manager/ssh-key", methods=("POST",))
    @login_required
    def api_site_manager_generate_ssh_key():
        try:
            ssh_key = generate_user_ssh_key(g.user["id"])
        except ValueError as error:
            return api_error(translate("flash.ssh_key_failed", error=error), 400)
        return jsonify({"ok": True, "ssh_key": ssh_key, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/site-manager/remote/sync", methods=("POST",))
    @login_required
    def api_site_manager_remote_sync():
        try:
            data = request_payload()
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                sync_remote_site_to_workspace(g.user["id"])
        except ValueError as error:
            return api_error(translate("flash.remote_sync_failed", error=error), 400)
        return jsonify({"ok": True, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/site-manager/backup", methods=("POST",))
    @login_required
    def api_site_manager_backup():
        try:
            data = request_payload()
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                create_site_backup(g.user["id"])
        except (ValueError, OSError, zipfile.BadZipFile) as error:
            return api_error(translate("flash.backup_failed", error=error), 400)
        return jsonify({"ok": True, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/site-manager/restore", methods=("POST",))
    @login_required
    def api_site_manager_restore():
        data = request.get_json(silent=True) or {}
        try:
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                restore_site_backup(g.user["id"], str(data.get("backup_id") or "").strip())
        except (ValueError, OSError, zipfile.BadZipFile) as error:
            return api_error(translate("flash.restore_failed", error=error), 400)
        return jsonify({"ok": True, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/site-manager/codex-update", methods=("POST",))
    @login_required
    def api_site_manager_codex_update():
        data = request_payload()
        prompt = (data.get("prompt") or data.get("quick_prompt") or "").strip()
        selected_asset = (data.get("selected_asset") or "").strip()
        provider = (data.get("provider") or "").strip().lower() or None
        model = (data.get("model") or "").strip() or None
        try:
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                if not prompt:
                    raise ValueError(translate("flash.codex_prompt_required"))
                uploaded_asset = save_codex_suggested_image(g.user["id"], request.files.get("suggested_image"))
                image_path = selected_asset or uploaded_asset
                if selected_asset:
                    validate_asset_path(g.user["id"], selected_asset)
                terminal = run_site_codex_update(g.user["id"], prompt, image_path, provider=provider, model=model)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "terminal": terminal, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/seo-suggestions/create", methods=("POST",))
    @login_required
    def api_create_seo_suggestion_page():
        data = request.get_json(silent=True) or {}
        title = (data.get("title") or "").strip()
        keyword = (data.get("keyword") or "").strip()
        if not title or not keyword:
            return api_error(translate("flash.seo_fields_required"), 400)
        try:
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                terminal = run_site_codex_update(
                    g.user["id"],
                    build_seo_page_codex_prompt(title, keyword),
                )
        except ValueError as error:
            return api_error(str(error), 400)
        notification = translate("flash.seo_page_created", title=title, keyword=keyword)
        return jsonify(
            {
                "ok": True,
                "terminal": terminal,
                "manager": to_jsonable(build_site_manager(g.user["id"])),
                "notification": notification,
            }
        )

    @app.route("/api/ai/run", methods=("POST",))
    @login_required
    def api_ai_run():
        data = request_payload()
        task_type = (data.get("task_type") or "assistant").strip().lower()
        provider = (data.get("provider") or "").strip().lower() or None
        model = (data.get("model") or "").strip() or None
        prompt = (data.get("prompt") or data.get("quick_prompt") or "").strip()
        selected_asset = (data.get("selected_asset") or "").strip()

        if not prompt:
            return api_error(translate("flash.codex_prompt_required"), 400)

        if task_type == "website_update":
            try:
                with site_operation_lock(g.user["id"]):
                    validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                    uploaded_asset = save_codex_suggested_image(g.user["id"], request.files.get("suggested_image"))
                    image_path = selected_asset or uploaded_asset
                    if selected_asset:
                        validate_asset_path(g.user["id"], selected_asset)
                    terminal = run_site_codex_update(g.user["id"], prompt, image_path, provider=provider, model=model)
            except ValueError as error:
                return api_error(str(error), 400)

            return jsonify(
                {
                    "ok": True,
                    "task_type": task_type,
                    "provider": terminal.get("provider"),
                    "model": terminal.get("model"),
                    "terminal": terminal,
                    "manager": to_jsonable(build_site_manager(g.user["id"])),
                }
            )

        try:
            run = run_ai_text_task(
                g.user["id"],
                task_type,
                prompt,
                provider=provider,
                model=model,
                context=(data.get("context") or "").strip(),
            )
        except ValueError as error:
            resolved_provider = provider or get_user_ai_policy(g.user["id"])["provider"]
            resolved_model = model or get_user_ai_policy(g.user["id"])["model"]
            save_ai_run(
                g.user["id"],
                resolved_provider,
                resolved_model,
                task_type,
                prompt,
                status="failed",
                error_text=str(error),
            )
            return api_error(str(error), 400)

        return jsonify({"ok": True, "run": run, "runs": to_jsonable(list_ai_runs(g.user["id"]))})

    @app.route("/api/ai/runs")
    @login_required
    def api_ai_runs():
        return jsonify({"ok": True, "runs": to_jsonable(list_ai_runs(g.user["id"]))})

    @app.route("/api/ai/images", methods=("GET",))
    @login_required
    def api_ai_images():
        return jsonify({"ok": True, "images": list_generated_images(g.user["id"])})

    @app.route("/api/ai/images", methods=("POST",))
    @login_required
    def api_ai_images_generate():
        data = request_payload()
        prompt = (data.get("prompt") or data.get("image_prompt") or "").strip()
        model = (data.get("model") or "").strip() or None
        output_format = (data.get("output_format") or "png").strip().lower() or "png"
        if output_format not in ("png", "jpg", "jpeg", "webp"):
            return api_error("Unsupported image format.", 400)
        if not prompt:
            return api_error("Enter an image description.", 400)
        try:
            image = run_muse_image_generation(
                g.user["id"], prompt, model=model, output_format=output_format
            )
        except ValueError as error:
            save_ai_run(
                g.user["id"],
                "muse",
                model or MUSE_IMAGE_DEFAULT_MODEL,
                "image_generation",
                prompt,
                status="failed",
                error_text=str(error),
            )
            return api_error(str(error), 400)
        return jsonify(
            {
                "ok": True,
                "image": {
                    "filename": image["filename"],
                    "url": f"/uploads/generated-images/{image['filename']}",
                    "model": image["model"],
                    "response_id": image["response_id"],
                    "size_bytes": image["size_bytes"],
                },
                "images": list_generated_images(g.user["id"]),
            }
        )

    @app.route("/api/site-manager/assets/upload", methods=("POST",))
    @login_required
    def api_site_manager_asset_upload():
        try:
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], request.form.get("expected_directory_path"))
                upload = request.files.get("asset")
                if not upload or not upload.filename:
                    raise ValueError(translate("flash.asset_required"))
                asset_path = save_codex_suggested_image(g.user["id"], upload)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "asset_path": asset_path, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/site-manager/seo-content", methods=("POST",))
    @login_required
    def api_site_manager_seo_content():
        data = request_payload()
        title = (data.get("title") or "").strip()
        keyword = (data.get("keyword") or "").strip()
        if not title or not keyword:
            return api_error(translate("flash.seo_fields_required"), 400)
        prompt = build_guided_seo_prompt(
            title,
            keyword,
            (data.get("tone") or "").strip(),
            (data.get("audience") or "").strip(),
            (data.get("cta") or "").strip(),
        )
        try:
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                terminal = run_site_codex_update(g.user["id"], prompt)
        except (ValueError, OSError, zipfile.BadZipFile, KeyError, TypeError) as error:
            return api_error(str(error), 400)
        return jsonify(
            {
                "ok": True,
                "terminal": terminal,
                "manager": to_jsonable(build_site_manager(g.user["id"])),
                "notification": translate(
                    "flash.site_manager_seo_page_created",
                    title=title,
                    keyword=keyword,
                ),
            }
        )

    @app.route("/api/site-manager/update/action", methods=("POST",))
    @login_required
    def api_site_manager_update_action():
        data = request.get_json(silent=True) or {}
        update_id = str(data.get("update_id") or "").strip()
        action = (data.get("action") or "").strip()
        try:
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                if action == "approve":
                    set_update_status(g.user["id"], update_id, "approved")
                elif action == "publish":
                    publish_site_to_remote(g.user["id"], update_id)
                elif action == "restore":
                    restore_update_files(g.user["id"], update_id)
                else:
                    raise ValueError("Unknown action.")
        except (ValueError, OSError, zipfile.BadZipFile, KeyError, TypeError) as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/site-manager/files/delete", methods=("POST",))
    @login_required
    def api_site_manager_file_delete():
        data = request.get_json(silent=True) or {}
        file_path = (data.get("path") or "").strip()
        try:
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                delete_site_file(g.user["id"], file_path)
        except ValueError as error:
            return api_error(translate("site.file_delete_failed", error=error), 400)
        return jsonify({"ok": True, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/site-manager/terminal/run", methods=("POST",))
    @login_required
    def api_site_manager_terminal_run():
        data = request_payload()
        try:
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                terminal = run_site_terminal_command(g.user["id"], (data.get("command") or "").strip())
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "terminal": terminal})

    @app.route("/api/security-scan")
    @login_required
    def api_security_scan_history():
        return jsonify({"ok": True, "scan_history": to_jsonable(build_security_scan_history(g.user["id"]))})

    @app.route("/api/security-scan", methods=("POST",))
    @login_required
    def api_security_scan():
        data = request.get_json(silent=True) or {}
        try:
            target = normalize_scan_domain((data.get("domain") or "").strip())
            scan = analyze_domain_security(target)
            save_security_scan_result(g.user["id"], scan)
        except ValueError as error:
            return api_error(str(error), 400)
        except SecurityScanError as error:
            return api_error(translate("flash.scan_failed", error=error), 400)
        return jsonify({"ok": True, "scan": to_jsonable(scan), "scan_history": to_jsonable(build_security_scan_history(g.user["id"]))})

    @app.route("/api/settings")
    @login_required
    def api_settings():
        google_credentials = get_google_oauth_credentials()
        ai_policy = get_user_ai_policy(g.user["id"])
        return jsonify(
            {
                "ok": True,
                "account": public_user(get_user_account(g.user["id"])),
                "ai": {
                    "providers": ai_provider_catalog(),
                    "policy": ai_policy,
                    "credentials": get_user_ai_credentials_status(g.user["id"]),
                },
                "google_config": {
                    "configured": google_oauth_configured(google_credentials),
                    "client_id_configured": bool(google_credentials["client_id"]),
                    "client_secret_configured": bool(google_credentials["client_secret"]),
                    "redirect_uri": google_redirect_uri(),
                },
            }
        )

    @app.route("/api/settings/account", methods=("POST",))
    @login_required
    def api_settings_account():
        data = request.get_json(silent=True) or {}
        user = get_user_account(g.user["id"])
        name = (data.get("name") or user["name"]).strip()
        company_name = (data.get("company_name") or "").strip()
        company_email = (data.get("company_email") or "").strip()
        company_website = (data.get("company_website") or "").strip()
        new_password = data.get("new_password") or ""
        confirm_password = data.get("confirm_password") or ""
        current_password = data.get("current_password") or ""

        if not name:
            return api_error(translate("flash.name_required"), 400)
        if new_password or confirm_password:
            if not verify_password(user["password_hash"], current_password):
                return api_error(translate("flash.current_password_invalid"), 401)
            if len(new_password) < 8 or new_password != confirm_password:
                return api_error(translate("flash.password_update_mismatch"), 400)
            execute_db(
                """
                UPDATE users
                SET name = ?, company_name = ?, company_email = ?, company_website = ?,
                    password_hash = ?
                WHERE id = ?
                """,
                (
                    name,
                    company_name,
                    company_email,
                    company_website,
                    hash_password(new_password),
                    g.user["id"],
                ),
            )
        else:
            execute_db(
                """
                UPDATE users
                SET name = ?, company_name = ?, company_email = ?, company_website = ?
                WHERE id = ?
                """,
                (name, company_name, company_email, company_website, g.user["id"]),
            )
        return jsonify({"ok": True, "account": public_user(get_user_account(g.user["id"]))})

    @app.route("/api/ai/providers")
    @login_required
    def api_ai_providers():
        return jsonify(
            {
                "ok": True,
                "providers": ai_provider_catalog(),
                "policy": get_user_ai_policy(g.user["id"]),
                "credentials": get_user_ai_credentials_status(g.user["id"]),
            }
        )

    @app.route("/api/settings/ai")
    @login_required
    def api_settings_ai():
        return jsonify(
            {
                "ok": True,
                "providers": ai_provider_catalog(),
                "policy": get_user_ai_policy(g.user["id"]),
                "credentials": get_user_ai_credentials_status(g.user["id"]),
            }
        )

    @app.route("/api/settings/ai-credentials", methods=("POST",))
    @login_required
    def api_settings_ai_credentials():
        data = request.get_json(silent=True) or {}
        current_password = data.get("current_password") or ""
        user = get_user_account(g.user["id"])
        if not verify_password(user["password_hash"], current_password):
            return api_error(translate("flash.password_incorrect"), 401)

        updates = []
        values = []
        muse_models = None
        for column, field_name in (
            ("muse_api_key", "muse_api_key"),
            ("anthropic_api_key", "anthropic_api_key"),
            ("openrouter_api_key", "openrouter_api_key"),
            ("google_api_key", "google_api_key"),
        ):
            if field_name in data:
                value = (data.get(field_name) or "").strip()
                if field_name == "muse_api_key" and value:
                    try:
                        muse_models = validate_muse_api_key(value)
                    except ValueError as error:
                        return api_error(str(error), 400)
                updates.append(f"{column} = ?")
                values.append(value)

        if not updates:
            return api_error("No AI credential fields were provided.", 400)

        if app.config["NATIVE_SERVICE_TOKEN"]:
            return jsonify(
                {
                    "ok": True,
                    "account": public_user(get_user_account(g.user["id"])),
                    "credentials": get_user_ai_credentials_status(g.user["id"]),
                }
            )

        values.append(g.user["id"])
        execute_db(
            f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
            tuple(values),
        )
        if muse_models is not None:
            save_muse_models_cache(g.user["id"], muse_models)
        return jsonify(
            {
                "ok": True,
                "account": public_user(get_user_account(g.user["id"])),
                "credentials": get_user_ai_credentials_status(g.user["id"]),
            }
        )

    @app.route("/api/settings/ai-policy", methods=("POST",))
    @login_required
    def api_settings_ai_policy():
        data = request.get_json(silent=True) or {}
        provider = (data.get("provider") or "").strip().lower()
        model = (data.get("model") or "").strip()

        if not provider:
            return api_error("Provider is required.", 400)
        if provider not in AI_PROVIDER_MODELS:
            return api_error(f"Unsupported provider: {provider}", 400)
        allowed_models = provider_models_for_user(g.user["id"], provider)
        if model and model not in allowed_models:
            return api_error(f"Unsupported model '{model}' for provider '{provider}'.", 400)

        effective_model = model or allowed_models[0]
        execute_db(
            "UPDATE users SET ai_default_provider = ?, ai_default_model = ? WHERE id = ?",
            (provider, effective_model, g.user["id"]),
        )
        return jsonify({"ok": True, "policy": get_user_ai_policy(g.user["id"])})

    @app.route("/api/settings/muse-models", methods=("GET",))
    @login_required
    def api_settings_muse_models():
        return jsonify({"ok": True, "models": get_muse_models(g.user["id"])})

    @app.route("/api/settings/muse-models/refresh", methods=("POST",))
    @login_required
    def api_settings_muse_models_refresh():
        try:
            models = refresh_muse_models(g.user["id"])
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "models": models})

    @app.route("/help")
    @login_required
    def help_page():
        return render_template("help.html")

    @app.route("/site-manager")
    @login_required
    def site_manager():
        manager = build_site_manager(g.user["id"])
        return render_template("site_manager.html", manager=manager, terminal=None, command="")

    @app.route("/site-manager/connect", methods=("POST",))
    @login_required
    def site_manager_connect():
        path = request.form.get("path", "").strip()
        try:
            connect_site_directory(g.user["id"], path)
        except ValueError as error:
            flash(str(error), "warning")
            return redirect(url_for("site_manager"))

        flash(translate("flash.site_connected"), "success")
        return redirect(url_for("site_manager"))

    @app.route("/site-manager/remote", methods=("POST",))
    @login_required
    def site_manager_remote_connect():
        try:
            save_remote_connection(
                g.user["id"],
                request.form.get("host", "").strip(),
                request.form.get("port", "").strip(),
                request.form.get("username", "").strip(),
                request.form.get("remote_path", "").strip(),
                request.form.get("key_path", "").strip(),
                request.form.get("auth_method", "").strip(),
                request.form.get("password", ""),
            )
        except ValueError as error:
            flash(str(error), "warning")
        else:
            flash(translate("site.remote_connected"), "success")
        return redirect(url_for("site_manager"))

    @app.route("/site-manager/ssh-key", methods=("POST",))
    @login_required
    def site_manager_generate_ssh_key():
        try:
            generate_user_ssh_key(g.user["id"])
        except ValueError as error:
            flash(translate("flash.ssh_key_failed", error=error), "warning")
        else:
            flash(translate("flash.ssh_key_generated"), "success")
        return redirect(url_for("site_manager"))

    @app.route("/site-manager/remote/sync", methods=("POST",))
    @login_required
    def site_manager_remote_sync():
        try:
            sync_remote_site_to_workspace(g.user["id"])
        except ValueError as error:
            flash(translate("flash.remote_sync_failed", error=error), "warning")
        else:
            flash(translate("flash.remote_synced"), "success")
        return redirect(url_for("site_manager"))

    @app.route("/site-manager/files/delete", methods=("POST",))
    @login_required
    def site_manager_file_delete():
        file_path = request.form.get("path", "").strip()
        try:
            delete_site_file(g.user["id"], file_path)
        except ValueError as error:
            flash(translate("site.file_delete_failed", error=error), "danger")
        else:
            flash(translate("site.file_deleted"), "success")
        parent = os.path.dirname(file_path).replace("\\", "/")
        return redirect(url_for("site_manager", path=parent))

    @app.route("/site-manager/files/raw")
    @login_required
    def site_manager_file_raw():
        file_path = request.args.get("path", "").strip()
        try:
            absolute_path = resolve_site_file(g.user["id"], file_path)
        except ValueError:
            abort(404)
        if not os.path.isfile(absolute_path):
            abort(404)
        return send_file(absolute_path, mimetype=mimetypes.guess_type(absolute_path)[0] or "application/octet-stream")

    @app.route("/site-manager/terminal", methods=("POST",))
    @login_required
    def site_manager_terminal():
        command = request.form.get("command", "").strip()
        manager = build_site_manager(g.user["id"])
        terminal = None

        try:
            terminal = run_site_terminal_command(g.user["id"], command)
        except ValueError as error:
            flash(str(error), "warning")

        return render_template("site_manager.html", manager=manager, terminal=terminal, command=command)

    @app.route("/site-manager/codex-update", methods=("POST",))
    @login_required
    def site_manager_codex_update():
        prompt = request.form.get("prompt", "").strip()
        quick_prompt = request.form.get("quick_prompt", "").strip()
        if quick_prompt and not prompt:
            prompt = quick_prompt
        suggested_image = request.files.get("suggested_image")
        selected_asset = request.form.get("selected_asset", "").strip()
        terminal = None

        try:
            if not prompt:
                raise ValueError(translate("flash.codex_prompt_required"))
            image_path = selected_asset or save_codex_suggested_image(g.user["id"], suggested_image)
            if selected_asset:
                validate_asset_path(g.user["id"], selected_asset)
            terminal = run_site_codex_update(g.user["id"], prompt, image_path)
        except ValueError as error:
            flash(str(error), "warning")

        manager = build_site_manager(g.user["id"])
        return render_template("site_manager.html", manager=manager, terminal=terminal, command="")

    @app.route("/site-manager/assets/upload", methods=("POST",))
    @login_required
    def site_manager_asset_upload():
        try:
            upload = request.files.get("asset")
            if not upload or not upload.filename:
                raise ValueError(translate("flash.asset_required"))
            save_codex_suggested_image(g.user["id"], upload)
        except ValueError as error:
            flash(str(error), "warning")
        return redirect(url_for("site_manager"))

    @app.route("/site-manager/assets/raw")
    @login_required
    def site_manager_asset_raw():
        asset_path = request.args.get("path", "").strip()
        try:
            validate_asset_path(g.user["id"], asset_path)
            absolute_path = resolve_site_file(g.user["id"], asset_path, allow_oneboard=True)
        except ValueError:
            abort(404)
        return send_file(absolute_path, mimetype=mimetypes.guess_type(absolute_path)[0] or "application/octet-stream")

    @app.route("/site-manager/seo-content", methods=("POST",))
    @login_required
    def site_manager_seo_content():
        title = request.form.get("title", "").strip()
        keyword = request.form.get("keyword", "").strip()
        if not title or not keyword:
            flash(translate("flash.seo_fields_required"), "warning")
            return redirect(url_for("site_manager"))
        prompt = build_guided_seo_prompt(
            title,
            keyword,
            request.form.get("tone", "").strip(),
            request.form.get("audience", "").strip(),
            request.form.get("cta", "").strip(),
        )
        try:
            terminal = run_site_codex_update(g.user["id"], prompt)
        except (ValueError, OSError, zipfile.BadZipFile, KeyError, TypeError) as error:
            flash(str(error), "warning")
            terminal = None
        else:
            flash(
                translate(
                    "flash.site_manager_seo_page_created",
                    title=title,
                    keyword=keyword,
                ),
                "success",
            )
        manager = build_site_manager(g.user["id"])
        return render_template("site_manager.html", manager=manager, terminal=terminal, command="")

    @app.route("/site-manager/update/action", methods=("POST",))
    @login_required
    def site_manager_update_action():
        update_id = request.form.get("update_id", "").strip()
        action = request.form.get("action", "").strip()
        try:
            if action == "approve":
                set_update_status(g.user["id"], update_id, "approved")
            elif action == "publish":
                publish_site_to_remote(g.user["id"], update_id)
                flash(translate("flash.remote_published"), "success")
            elif action == "restore":
                restore_update_files(g.user["id"], update_id)
            else:
                raise ValueError("Unknown action.")
        except (ValueError, OSError, zipfile.BadZipFile, KeyError, TypeError) as error:
            flash(str(error), "warning")
        return redirect(url_for("site_manager"))

    @app.route("/seo-suggestions/create", methods=("POST",))
    @login_required
    def create_seo_suggestion_page():
        title = request.form.get("title", "").strip()
        keyword = request.form.get("keyword", "").strip()
        prompt = build_seo_page_codex_prompt(title, keyword)
        try:
            run_site_codex_update(g.user["id"], prompt)
        except ValueError as error:
            flash(str(error), "warning")
        else:
            flash(
                translate("flash.seo_page_created", title=title, keyword=keyword),
                "success",
            )
        return redirect(url_for("site_manager"))

    @app.route("/site-manager/terminal/run", methods=("POST",))
    @login_required
    def site_manager_terminal_run():
        command = request.form.get("command", "").strip()
        try:
            terminal = run_site_terminal_command(g.user["id"], command)
        except ValueError as error:
            return jsonify({"ok": False, "error": str(error)}), 400

        return jsonify({"ok": True, "terminal": terminal})

    @app.route("/site-manager/backup", methods=("POST",))
    @login_required
    def site_manager_backup():
        try:
            create_site_backup(g.user["id"])
        except (ValueError, OSError, zipfile.BadZipFile) as error:
            flash(translate("flash.backup_failed", error=error), "danger")
        else:
            flash(translate("flash.backup_created"), "success")

        return redirect(url_for("site_manager"))

    @app.route("/site-manager/restore", methods=("POST",))
    @login_required
    def site_manager_restore():
        backup_id = request.form.get("backup_id", "").strip()
        confirmed = request.form.get("confirm_restore") == "yes"

        if not confirmed:
            flash(translate("flash.restore_confirm_required"), "warning")
            return redirect(url_for("site_manager"))

        try:
            restore_site_backup(g.user["id"], backup_id)
        except (ValueError, OSError, zipfile.BadZipFile) as error:
            flash(translate("flash.restore_failed", error=error), "danger")
        else:
            flash(translate("flash.restore_complete"), "success")

        return redirect(url_for("site_manager"))

    @app.route("/security-scan", methods=("GET", "POST"))
    @login_required
    def security_scan():
        scan = None
        domain = ""

        if request.method == "POST":
            domain = request.form.get("domain", "").strip()
            try:
                target = normalize_scan_domain(domain)
                scan = analyze_domain_security(target)
                save_security_scan_result(g.user["id"], scan)
                domain = target
            except ValueError as error:
                flash(str(error), "warning")
            except SecurityScanError as error:
                flash(translate("flash.scan_failed", error=error), "danger")

        scan_history = build_security_scan_history(g.user["id"])
        return render_template(
            "security_scan.html",
            scan=scan,
            domain=domain,
            scan_history=scan_history,
        )

    @app.route("/settings", methods=("GET", "POST"))
    @login_required
    def settings():
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            language = request.form.get("language", DEFAULT_LANGUAGE)
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_new_password = request.form.get("confirm_new_password", "")
            company_name = request.form.get("company_name", "").strip()
            company_email = request.form.get("company_email", "").strip().lower()
            company_website = request.form.get("company_website", "").strip()
            muse_api_key = request.form.get("muse_api_key", "").strip()
            avatar = request.files.get("avatar")
            company_logo = request.files.get("company_logo")
            account = get_user_account(g.user["id"])

            if not name:
                flash(translate("flash.name_required"), "warning")
                return redirect(url_for("settings"))
            if not email or "@" not in email:
                flash(translate("flash.email_invalid"), "warning")
                return redirect(url_for("settings"))
            if language in SUPPORTED_LANGUAGES:
                session["lang"] = language

            changing_sensitive_fields = email != account["email"] or bool(new_password)
            if changing_sensitive_fields:
                if not current_password:
                    flash(translate("flash.current_password_required"), "warning")
                    return redirect(url_for("settings"))
                if not verify_password(account["password_hash"], current_password):
                    flash(translate("flash.current_password_invalid"), "danger")
                    return redirect(url_for("settings"))
            if new_password:
                if len(new_password) < 8:
                    flash(translate("auth.min_password"), "warning")
                    return redirect(url_for("settings"))
                if new_password != confirm_new_password:
                    flash(translate("flash.password_update_mismatch"), "warning")
                    return redirect(url_for("settings"))

            avatar_path = account["avatar_path"]
            if avatar and avatar.filename:
                try:
                    avatar_path = save_uploaded_image(
                        g.user["id"],
                        avatar,
                        AVATAR_DIR,
                        "user",
                    )
                except ValueError as error:
                    flash(str(error), "warning")
                    return redirect(url_for("settings"))

            company_logo_path = account["company_logo_path"]
            if company_logo and company_logo.filename:
                try:
                    company_logo_path = save_uploaded_image(
                        g.user["id"],
                        company_logo,
                        COMPANY_LOGO_DIR,
                        "company",
                    )
                except ValueError as error:
                    flash(str(error), "warning")
                    return redirect(url_for("settings"))

            password_hash = hash_password(new_password) if new_password else account["password_hash"]

            try:
                execute_db(
                    """
                    UPDATE users
                    SET name = ?, email = ?, password_hash = ?, avatar_path = ?,
                        company_name = ?, company_email = ?, company_website = ?,
                        company_logo_path = ?,
                        muse_api_key = COALESCE(NULLIF(?, ''), muse_api_key)
                    WHERE id = ?
                    """,
                    (
                        name,
                        email,
                        password_hash,
                        avatar_path,
                        company_name,
                        company_email,
                        company_website,
                        company_logo_path,
                        muse_api_key,
                        g.user["id"],
                    ),
                )
            except sqlite3.IntegrityError:
                flash(translate("flash.account_exists"), "warning")
            else:
                flash(translate("flash.settings_updated"), "success")
            return redirect(url_for("settings"))

        account = get_user_account(g.user["id"])
        google_credentials = get_google_oauth_credentials()
        google_config = {
            "configured": google_oauth_configured(google_credentials),
            "client_id_configured": bool(google_credentials["client_id"]),
            "client_secret_configured": bool(google_credentials["client_secret"]),
            "redirect_uri": google_redirect_uri(),
        }
        return render_template("settings.html", account=account, google_config=google_config)

    @app.route("/integrations/google-search-console/connect")
    @login_required
    def google_search_console_connect():
        google_credentials = get_google_oauth_credentials()
        if not google_oauth_configured(google_credentials):
            flash(
                translate("flash.google_credentials_missing"),
                "warning",
            )
            return redirect(url_for("dashboard"))

        state = secrets.token_urlsafe(32)
        session["google_oauth_state"] = state
        save_google_oauth_state(g.user["id"], state)
        params = {
            "client_id": google_credentials["client_id"],
            "redirect_uri": google_redirect_uri(),
            "response_type": "code",
            "scope": SEARCH_CONSOLE_SCOPE,
            "access_type": "offline",
            "prompt": "consent select_account",
            "include_granted_scopes": "true",
            "state": state,
        }
        return redirect(f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}")

    @app.route("/integrations/google-search-console/callback")
    @login_required
    def google_search_console_callback():
        if request.args.get("error"):
            error = request.args.get("error", "error desconocido")
            description = request.args.get("error_description", "")
            detail = f" Detalle: {description}" if description else ""
            flash(translate("flash.google_denied", error=error, detail=detail), "danger")
            return redirect(url_for("dashboard"))

        state = request.args.get("state", "")
        session_state = session.pop("google_oauth_state", None)
        if state != session_state and not consume_google_oauth_state(g.user["id"], state):
            flash(translate("flash.google_state_invalid"), "danger")
            return redirect(url_for("dashboard"))

        code = request.args.get("code")
        if not code:
            flash(translate("flash.google_code_missing"), "danger")
            return redirect(url_for("dashboard"))

        try:
            token = exchange_google_code(g.user["id"], code)
            save_google_connection(g.user["id"], token)
        except GoogleApiError as error:
            flash(translate("flash.search_console_failed", error=error), "danger")
            return redirect(url_for("dashboard"))

        flash(translate("flash.search_console_connected"), "success")
        return redirect(url_for("dashboard"))

    @app.route("/integrations/google-search-console/site", methods=("POST",))
    @login_required
    def google_search_console_select_site():
        site_url = request.form.get("site_url", "").strip()
        connection = get_google_connection(g.user["id"])
        if not connection:
            flash(translate("flash.connect_before_site"), "warning")
            return redirect(url_for("dashboard"))
        if not site_url:
            flash(translate("flash.select_property"), "warning")
            return redirect(url_for("dashboard"))

        execute_db(
            """
            UPDATE google_search_console_connections
            SET selected_site_url = ?
            WHERE user_id = ?
            """,
            (site_url, g.user["id"]),
        )
        flash(translate("flash.property_selected"), "success")
        return redirect(url_for("dashboard"))

    @app.route("/integrations/google-search-console/disconnect", methods=("POST",))
    @login_required
    def google_search_console_disconnect():
        connection = get_google_connection(g.user["id"])
        try:
            if connection:
                revoke_google_connection(connection)
            execute_db(
                "DELETE FROM google_search_console_connections WHERE user_id = ?",
                (g.user["id"],),
            )
        except GoogleApiError as error:
            flash(translate("flash.search_console_failed", error=error), "danger")
            return redirect(url_for("dashboard"))
        flash(translate("flash.search_console_disconnected"), "info")
        return redirect(url_for("dashboard"))

    @app.route("/logout", methods=("POST",))
    @login_required
    def logout():
        language = current_language()
        session.clear()
        session["lang"] = language
        flash(translate("flash.logout_success"), "info")
        return redirect(url_for("login"))

    @app.cli.command("init-db")
    def init_db_command():
        init_db()
        print("Base de datos inicializada.")

    @app.cli.command("set-site-directory")
    @click.argument("site_url")
    @click.argument("path")
    def set_site_directory_command(site_url, path):
        with app.app_context():
            set_website_project_directory(site_url, path)
        print(f"Mapped {site_url} -> {os.path.abspath(os.path.expanduser(path))}")

    with app.app_context():
        init_db()

    return app


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


def query_db(query, args=(), one=False):
    cursor = get_db().execute(query, args)
    rows = cursor.fetchall()
    cursor.close()
    return (rows[0] if rows else None) if one else rows


def execute_db(query, args=()):
    db = get_db()
    db.execute(query, args)
    db.commit()


def api_error(message, status=400):
    return jsonify({"ok": False, "error": str(message)}), status


def request_payload():
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form


def public_user(user):
    if not user:
        return None
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "email_verified": bool(user["email_verified"]) if "email_verified" in user.keys() else True,
        "avatar_path": user["avatar_path"],
        "company_name": user["company_name"],
        "company_email": user["company_email"],
        "company_website": user["company_website"],
        "company_logo_path": user["company_logo_path"],
        "muse_api_key_configured": bool(user["muse_api_key"]) if "muse_api_key" in user.keys() else False,
        "anthropic_api_key_configured": bool(user["anthropic_api_key"]) if "anthropic_api_key" in user.keys() else False,
        "openrouter_api_key_configured": bool(user["openrouter_api_key"]) if "openrouter_api_key" in user.keys() else False,
        "google_api_key_configured": bool(user["google_api_key"]) if "google_api_key" in user.keys() else False,
        "ai_default_provider": user["ai_default_provider"] if "ai_default_provider" in user.keys() else DEFAULT_AI_PROVIDER,
        "ai_default_model": user["ai_default_model"] if "ai_default_model" in user.keys() else "",
        "created_at": user["created_at"],
    }


def to_jsonable(value):
    if isinstance(value, sqlite3.Row):
        return {key: to_jsonable(value[key]) for key in value.keys()}
    if isinstance(value, dict):
        return {key: to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_jsonable(item) for item in value]
    return value


def init_db():
    db = get_db()
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            email_verified INTEGER NOT NULL DEFAULT 0,
            avatar_path TEXT,
            company_name TEXT,
            company_email TEXT,
            company_website TEXT,
            company_logo_path TEXT,
            muse_api_key TEXT,
            muse_models_json TEXT,
            anthropic_api_key TEXT,
            openrouter_api_key TEXT,
            google_api_key TEXT,
            ai_default_provider TEXT NOT NULL DEFAULT 'muse',
            ai_default_model TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    ensure_column("users", "avatar_path", "TEXT")
    ensure_column("users", "email_verified", "INTEGER NOT NULL DEFAULT 1")
    ensure_column("users", "company_name", "TEXT")
    ensure_column("users", "company_email", "TEXT")
    ensure_column("users", "company_website", "TEXT")
    ensure_column("users", "company_logo_path", "TEXT")
    ensure_column("users", "muse_api_key", "TEXT")
    ensure_column("users", "muse_models_json", "TEXT")
    ensure_column("users", "anthropic_api_key", "TEXT")
    ensure_column("users", "openrouter_api_key", "TEXT")
    ensure_column("users", "google_api_key", "TEXT")
    ensure_column("users", "ai_default_provider", "TEXT NOT NULL DEFAULT 'muse'")
    ensure_column("users", "ai_default_model", "TEXT")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS google_search_console_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            access_token TEXT NOT NULL,
            refresh_token TEXT,
            expires_at INTEGER NOT NULL,
            scope TEXT,
            selected_site_url TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS google_oauth_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            state TEXT NOT NULL UNIQUE,
            code_verifier TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    ensure_column("google_oauth_states", "code_verifier", "TEXT")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS password_reset_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT NOT NULL UNIQUE,
            expires_at INTEGER NOT NULL,
            used_at INTEGER,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS email_verification_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token_hash TEXT NOT NULL UNIQUE,
            expires_at INTEGER NOT NULL,
            used_at INTEGER,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS website_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_url TEXT NOT NULL UNIQUE,
            path TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS website_directories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            path TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS website_backups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            directory_path TEXT NOT NULL,
            filename TEXT NOT NULL,
            backup_path TEXT NOT NULL,
            file_count INTEGER NOT NULL DEFAULT 0,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS website_remote_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            host TEXT NOT NULL,
            port INTEGER NOT NULL DEFAULT 22,
            username TEXT NOT NULL,
            remote_path TEXT NOT NULL,
            key_path TEXT,
            auth_method TEXT NOT NULL DEFAULT 'key',
            password TEXT,
            directory_path TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    ensure_column("website_remote_connections", "auth_method", "TEXT NOT NULL DEFAULT 'key'")
    ensure_column("website_remote_connections", "password", "TEXT")
    ensure_column("website_remote_connections", "directory_path", "TEXT")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS website_update_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            source TEXT NOT NULL,
            summary TEXT NOT NULL,
            exit_code TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            snapshot_path TEXT,
            changed_files TEXT,
            diff_summary TEXT,
            directory_path TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    ensure_column("website_update_history", "status", "TEXT NOT NULL DEFAULT 'pending'")
    ensure_column("website_update_history", "snapshot_path", "TEXT")
    ensure_column("website_update_history", "changed_files", "TEXT")
    ensure_column("website_update_history", "diff_summary", "TEXT")
    ensure_column("website_update_history", "directory_path", "TEXT")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS website_codex_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL UNIQUE,
            session_id TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS website_codex_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            raw_output TEXT,
            exit_code TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS security_scan_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            domain TEXT NOT NULL,
            score INTEGER NOT NULL,
            grade TEXT NOT NULL,
            verdict TEXT,
            https_available INTEGER NOT NULL DEFAULT 0,
            hsts_active INTEGER NOT NULL DEFAULT 0,
            missing_headers_count INTEGER NOT NULL DEFAULT 0,
            details_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            task_type TEXT NOT NULL,
            prompt TEXT NOT NULL,
            response_text TEXT,
            status TEXT NOT NULL DEFAULT 'completed',
            error_text TEXT,
            usage_json TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.commit()


def ensure_column(table, column, definition):
    db = get_db()
    columns = [row["name"] for row in db.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in columns:
        try:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
            db.commit()
        except sqlite3.OperationalError as error:
            if "duplicate column name" not in str(error).lower():
                raise


class GoogleApiError(Exception):
    pass


class SecurityScanError(Exception):
    pass


def google_oauth_configured(credentials):
    return bool(credentials["client_id"] and credentials["client_secret"])


def get_user_account(user_id):
    return query_db(
        """
        SELECT id, name, email, password_hash, email_verified, avatar_path, company_name,
               company_email, company_website, company_logo_path,
               muse_api_key, muse_models_json, anthropic_api_key, openrouter_api_key, google_api_key,
               ai_default_provider, ai_default_model,
               created_at
        FROM users
        WHERE id = ?
        """,
        (user_id,),
        one=True,
    )


def get_google_oauth_credentials():
    return {
        "client_id": os.environ.get("GOOGLE_CLIENT_ID", ""),
        "client_secret": os.environ.get("GOOGLE_CLIENT_SECRET", ""),
    }


def google_redirect_uri():
    configured_uri = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
    if configured_uri:
        return configured_uri
    return url_for("google_search_console_callback", _external=True)


def google_native_redirect_uri():
    port = int(os.environ.get("PORT", "51249"))
    return f"http://127.0.0.1:{port}/api/google-search-console/callback"


def exchange_google_code(user_id, code, redirect_uri=None, code_verifier=None):
    credentials = get_google_oauth_credentials()
    payload = {
        "code": code,
        "client_id": credentials["client_id"],
        "client_secret": credentials["client_secret"],
        "redirect_uri": redirect_uri or google_redirect_uri(),
        "grant_type": "authorization_code",
    }
    if code_verifier:
        payload["code_verifier"] = code_verifier
    return google_token_request(payload, "Could not complete Google authorization.")


def refresh_google_token(connection):
    refresh_token = connection["refresh_token"]
    if not refresh_token:
        raise GoogleApiError("The connection has no refresh token. Disconnect and reconnect Google.")

    credentials = get_google_oauth_credentials()
    payload = {
        "client_id": credentials["client_id"],
        "client_secret": credentials["client_secret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    token = google_token_request(payload, "Could not renew the Google session.")
    expires_at = int(time.time()) + int(token.get("expires_in", 3600)) - 60
    execute_db(
        """
        UPDATE google_search_console_connections
        SET access_token = ?, expires_at = ?, scope = ?, updated_at = CURRENT_TIMESTAMP
        WHERE user_id = ?
        """,
        (
            token["access_token"],
            expires_at,
            token.get("scope", connection["scope"]),
            connection["user_id"],
        ),
    )
    return get_google_connection(connection["user_id"])


def google_token_request(payload, fallback_message):
    try:
        request_data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(
            GOOGLE_TOKEN_URL,
            data=request_data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8")
        raise GoogleApiError(f"{fallback_message} Google response: {detail}") from error
    except urllib.error.URLError as error:
        raise GoogleApiError(f"{fallback_message} Network error: {error.reason}") from error


def save_google_connection(user_id, token):
    refresh_token = token.get("refresh_token")
    if not refresh_token:
        raise GoogleApiError(
            "Google did not return a refresh token. Disconnect the previous connection "
            "and authorize the account again."
        )
    expires_at = int(time.time()) + int(token.get("expires_in", 3600)) - 60
    execute_db(
        """
        INSERT INTO google_search_console_connections (
            user_id, access_token, refresh_token, expires_at, scope, selected_site_url
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            access_token = excluded.access_token,
            refresh_token = excluded.refresh_token,
            expires_at = excluded.expires_at,
            scope = excluded.scope,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            token["access_token"],
            refresh_token,
            expires_at,
            token.get("scope", SEARCH_CONSOLE_SCOPE),
            None,
        ),
    )


def get_google_connection(user_id):
    return query_db(
        """
        SELECT id, user_id, access_token, refresh_token, expires_at, scope, selected_site_url
        FROM google_search_console_connections
        WHERE user_id = ?
        """,
        (user_id,),
        one=True,
    )


def save_google_oauth_state(user_id, state, code_verifier=None):
    now = int(time.time())
    execute_db(
        "DELETE FROM google_oauth_states WHERE created_at < ?",
        (now - 900,),
    )
    execute_db(
        """
        INSERT INTO google_oauth_states (user_id, state, code_verifier, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, state, code_verifier, now),
    )


def consume_google_oauth_state(user_id, state):
    if not state:
        return False

    cutoff = int(time.time()) - 900
    row = query_db(
        """
        SELECT id
        FROM google_oauth_states
        WHERE user_id = ? AND state = ? AND created_at >= ?
        """,
        (user_id, state, cutoff),
        one=True,
    )
    if not row:
        return False

    execute_db("DELETE FROM google_oauth_states WHERE id = ?", (row["id"],))
    return True


def consume_google_oauth_state_user_id(state):
    if not state:
        return None

    cutoff = int(time.time()) - 900
    row = query_db(
        """
        SELECT id, user_id, code_verifier
        FROM google_oauth_states
        WHERE state = ? AND created_at >= ?
        """,
        (state, cutoff),
        one=True,
    )
    if not row:
        return None

    execute_db("DELETE FROM google_oauth_states WHERE id = ?", (row["id"],))
    return row["user_id"], row["code_verifier"]


def google_native_callback_page(ok, message):
    status = 200 if ok else 400
    title = "ONEBoard connected" if ok else "ONEBoard connection failed"
    escaped_message = str(message).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    html = f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      background: linear-gradient(180deg, #fbfbfd 0%, #f4f5f8 58%, #eceef2 100%);
      color: #1d1d1f;
      font-family: -apple-system, BlinkMacSystemFont, "SF Pro Text", sans-serif;
    }}
    main {{
      width: min(460px, calc(100% - 32px));
      padding: 28px;
      border: 1px solid rgba(255,255,255,.72);
      border-radius: 22px;
      background: rgba(255,255,255,.82);
      box-shadow: 0 18px 48px rgba(0,0,0,.055);
    }}
    h1 {{ margin: 0 0 8px; font-size: 1.4rem; }}
    p {{ margin: 0; color: #6e6e73; line-height: 1.45; }}
  </style>
</head>
<body>
  <main>
    <h1>{title}</h1>
    <p>{escaped_message}</p>
  </main>
</body>
</html>
""".strip()
    return html, status, {"Content-Type": "text/html; charset=utf-8"}


def valid_google_connection(user_id):
    connection = get_google_connection(user_id)
    if not connection:
        return None
    credentials = get_google_oauth_credentials()
    if int(connection["expires_at"]) <= int(time.time()) and google_oauth_configured(credentials):
        return refresh_google_token(connection)
    return connection


def google_api_request(connection, path, method="GET", payload=None, retry_on_unauthorized=True):
    url = f"{SEARCH_CONSOLE_API}{path}"
    data = None
    headers = {"Authorization": f"Bearer {connection['access_token']}"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    try:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=25) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8")
        if error.code == 401 and retry_on_unauthorized and connection["refresh_token"]:
            refreshed_connection = refresh_google_token(connection)
            return google_api_request(
                refreshed_connection,
                path,
                method=method,
                payload=payload,
                retry_on_unauthorized=False,
            )
        raise GoogleApiError(f"Google Search Console returned an error: {detail}") from error
    except urllib.error.URLError as error:
        raise GoogleApiError(f"Could not connect to Google Search Console: {error.reason}") from error


def revoke_google_connection(connection):
    token = connection["refresh_token"] or connection["access_token"]
    request_data = urllib.parse.urlencode({"token": token}).encode("utf-8")
    request = urllib.request.Request(
        "https://oauth2.googleapis.com/revoke",
        data=request_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20):
            pass
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8")
        raise GoogleApiError(f"Google could not revoke the connection: {detail}") from error
    except urllib.error.URLError as error:
        raise GoogleApiError(f"Could not revoke the Google connection: {error.reason}") from error


def build_search_console_dashboard(user_id):
    google_credentials = get_google_oauth_credentials()
    dashboard = {
        "configured": google_oauth_configured(google_credentials),
        "connected": False,
        "sites": [],
        "selected_site_url": None,
        "date_range": search_console_date_range(),
        "stats": empty_search_stats(),
        "queries": [],
        "pages": [],
        "query_chart": [],
        "page_chart": [],
        "seo_opportunities": [],
        "error": None,
    }

    connection = get_google_connection(user_id)
    if not connection:
        return dashboard

    dashboard["connected"] = True
    dashboard["selected_site_url"] = connection["selected_site_url"]

    if not dashboard["configured"]:
        dashboard["error"] = translate("dashboard.missing_google")
        return dashboard

    try:
        connection = valid_google_connection(user_id)
        sites_response = google_api_request(connection, "/sites")
        dashboard["sites"] = sites_response.get("siteEntry", [])
        available_site_urls = {
            site.get("siteUrl")
            for site in dashboard["sites"]
            if site.get("siteUrl")
        }
        saved_site_url = connection["selected_site_url"]
        selected_site_url = (
            saved_site_url
            if saved_site_url in available_site_urls
            else first_site_url(dashboard["sites"])
        )
        dashboard["selected_site_url"] = selected_site_url

        if selected_site_url != connection["selected_site_url"]:
            execute_db(
                """
                UPDATE google_search_console_connections
                SET selected_site_url = ?
                WHERE user_id = ?
                """,
                (selected_site_url, user_id),
            )

        if selected_site_url:
            dashboard.update(fetch_search_console_analytics(connection, selected_site_url))
    except GoogleApiError as error:
        dashboard["error"] = str(error)

    return dashboard


def first_site_url(sites):
    for site in sites:
        if site.get("siteUrl") and site.get("permissionLevel") != "siteUnverifiedUser":
            return site["siteUrl"]
    return None


def search_console_date_range():
    end_date = date.today() - timedelta(days=2)
    start_date = end_date - timedelta(days=27)
    return {"start": start_date.isoformat(), "end": end_date.isoformat()}


def fetch_search_console_analytics(connection, site_url):
    date_range = search_console_date_range()
    encoded_site_url = urllib.parse.quote(site_url, safe="")
    base_payload = {
        "startDate": date_range["start"],
        "endDate": date_range["end"],
        "rowLimit": 10,
    }

    totals = google_api_request(
        connection,
        f"/sites/{encoded_site_url}/searchAnalytics/query",
        method="POST",
        payload={**base_payload, "rowLimit": 1},
    )
    queries = google_api_request(
        connection,
        f"/sites/{encoded_site_url}/searchAnalytics/query",
        method="POST",
        payload={**base_payload, "dimensions": ["query"]},
    )
    pages = google_api_request(
        connection,
        f"/sites/{encoded_site_url}/searchAnalytics/query",
        method="POST",
        payload={**base_payload, "dimensions": ["page"]},
    )

    return {
        "stats": format_search_stats(first_row(totals.get("rows", []))),
        "queries": format_search_rows(queries.get("rows", [])),
        "pages": format_search_rows(pages.get("rows", [])),
        "query_chart": format_chart_rows(queries.get("rows", []), "clicks"),
        "page_chart": format_chart_rows(pages.get("rows", []), "impressions"),
        "seo_opportunities": build_seo_opportunities(queries.get("rows", [])),
    }


def first_row(rows):
    return rows[0] if rows else {}


def empty_search_stats():
    return [
        {"label": translate("metric.clicks"), "value": "0"},
        {"label": translate("metric.impressions"), "value": "0"},
        {"label": translate("metric.ctr"), "value": "0%"},
        {"label": translate("metric.position"), "value": "-"},
    ]


def format_search_stats(row):
    clicks = int(row.get("clicks", 0))
    impressions = int(row.get("impressions", 0))
    ctr = row.get("ctr", 0) * 100 if row else 0
    position = row.get("position", 0)
    return [
        {"label": translate("metric.clicks"), "value": f"{clicks:,}"},
        {"label": translate("metric.impressions"), "value": f"{impressions:,}"},
        {"label": translate("metric.ctr"), "value": f"{ctr:.1f}%"},
        {"label": translate("metric.position"), "value": f"{position:.1f}" if position else "-"},
    ]


def format_search_rows(rows):
    formatted_rows = []
    for row in rows:
        key = row.get("keys", [""])[0]
        formatted_rows.append(
            {
                "key": key,
                "clicks": int(row.get("clicks", 0)),
                "impressions": int(row.get("impressions", 0)),
                "ctr": f"{row.get('ctr', 0) * 100:.1f}%",
                "position": f"{row.get('position', 0):.1f}",
            }
        )
    return formatted_rows


def format_chart_rows(rows, metric):
    values = []
    for row in rows[:6]:
        key = row.get("keys", [""])[0]
        value = int(row.get(metric, 0))
        values.append({"label": compact_chart_label(key), "value": value})

    max_value = max((item["value"] for item in values), default=0)
    for item in values:
        item["pct"] = round((item["value"] / max_value) * 100) if max_value else 0
        item["display"] = f"{item['value']:,}"

    return values


def compact_chart_label(value):
    clean_value = value.replace("https://", "").replace("http://", "").strip("/")
    if len(clean_value) <= 34:
        return clean_value or "-"
    return f"{clean_value[:31]}..."


def build_seo_opportunities(rows):
    opportunities = []
    sorted_rows = sorted(
        rows,
        key=lambda row: (row.get("impressions", 0), -row.get("clicks", 0)),
        reverse=True,
    )
    for row in sorted_rows[:4]:
        keyword = row.get("keys", [""])[0].strip()
        if not keyword:
            continue
        impressions = int(row.get("impressions", 0))
        clicks = int(row.get("clicks", 0))
        position = float(row.get("position", 0) or 0)
        title = keyword_to_page_title(keyword)
        opportunities.append(
            {
                "keyword": keyword,
                "title": title,
                "impressions": f"{impressions:,}",
                "clicks": f"{clicks:,}",
                "position": f"{position:.1f}" if position else "-",
            }
        )
    return opportunities


def keyword_to_page_title(keyword):
    words = [word for word in re.split(r"\s+", keyword.strip()) if word]
    title = " ".join(word.capitalize() for word in words)
    return title or keyword


def build_seo_page_codex_prompt(title, keyword):
    return f"""
You are updating this website from inside its root directory only.

Goal:
Create a new SEO landing/content page for the search opportunity:
- Page title: {title}
- Target keyword: {keyword}

Required workflow:
1. Inspect the existing website files first. Identify the current layout, navigation, typography, CSS files, components, footer, and visual style.
2. Reuse the existing design system and assets. Do not introduce a different visual style.
3. Create the new page using the site's existing HTML/CSS patterns. If the site has shared styles, reuse them instead of creating an unrelated page.
4. Add clear, helpful content for the target keyword, with a strong title, concise sections, and internal navigation where appropriate.
5. If there is an existing navigation/menu pattern, add the page link in the appropriate place.
6. Stay strictly inside this website directory.

Return a concise summary of the files changed and the page URL/path created.
""".strip()


def build_site_manager(user_id):
    directory = get_site_directory(user_id)
    current_path = request.args.get("path", "").strip() if has_request_context() else ""
    preview_path = request.args.get("preview", "").strip() if has_request_context() else ""
    selected_asset = request.args.get("asset", "").strip() if has_request_context() else ""
    files = None
    if directory and os.path.isdir(directory["path"]):
        try:
            files = build_site_file_browser(user_id, current_path, preview_path)
        except ValueError:
            files = build_site_file_browser(user_id, "", "")
    return {
        "directory": directory,
        "directory_managed_by_env": False,
        "backups": list_site_backups(user_id),
        "codex_messages": list_codex_messages(user_id),
        "remote_connection": get_remote_connection(user_id),
        "ssh_key": get_user_ssh_key_info(user_id),
        "updates": list_update_history(user_id),
        "files": files,
        "assets": list_site_assets(user_id) if directory and os.path.isdir(directory["path"]) else [],
        "selected_asset": selected_asset,
        "quick_prompts": build_quick_prompts(),
    }


@locked_site_operation
def connect_site_directory(user_id, path):
    if not path:
        raise ValueError(translate("flash.site_path_required"))

    normalized_path = os.path.realpath(os.path.abspath(os.path.expanduser(path)))
    if not os.path.exists(normalized_path):
        raise ValueError(translate("flash.site_path_missing"))
    if not os.path.isdir(normalized_path):
        raise ValueError(translate("flash.site_path_not_directory"))
    app_data_path = os.path.realpath(APP_DATA_DIR)
    home_path = os.path.realpath(os.path.expanduser("~"))
    filesystem_root = os.path.realpath(os.path.abspath(os.sep))
    if (
        normalized_path in {filesystem_root, home_path, app_data_path}
        or path_is_inside(app_data_path, normalized_path)
    ):
        raise ValueError(translate("flash.site_path_unsafe"))

    store_site_directory(user_id, normalized_path)


def store_site_directory(user_id, normalized_path):
    execute_db(
        """
        INSERT INTO website_directories (user_id, path)
        VALUES (?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            path = excluded.path,
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, normalized_path),
    )


def connect_managed_remote_workspace(user_id, workspace_path, remote):
    """Connect only the exact per-user workspace derived for this remote."""
    expected_path = os.path.abspath(remote_workspace_path(user_id, remote))
    candidate_path = os.path.abspath(workspace_path)
    user_root = os.path.abspath(os.path.join(REMOTE_WORKSPACE_DIR, str(user_id)))
    if candidate_path != expected_path or not lexical_path_is_inside(user_root, candidate_path):
        raise ValueError(translate("site.internal_directory_unsafe"))
    if (
        os.path.islink(REMOTE_WORKSPACE_DIR)
        or os.path.islink(user_root)
        or os.path.islink(candidate_path)
        or not os.path.isdir(candidate_path)
    ):
        raise ValueError(translate("site.internal_directory_unsafe"))
    if path_contains_symlink(user_root, candidate_path):
        raise ValueError(translate("site.internal_directory_unsafe"))
    store_site_directory(user_id, os.path.realpath(candidate_path))


def user_ssh_key_path(user_id):
    return os.path.join(SSH_KEY_DIR, str(user_id), "oneboard_ed25519")


def get_user_ssh_key_info(user_id):
    private_path = user_ssh_key_path(user_id)
    public_path = f"{private_path}.pub"
    if not os.path.isfile(private_path) or not os.path.isfile(public_path):
        return {
            "exists": False,
            "private_path": private_path,
            "public_key": "",
            "install_command": "",
        }
    with open(public_path, "r", encoding="utf-8", errors="replace") as file:
        public_key = file.read().strip()
    return {
        "exists": True,
        "private_path": private_path,
        "public_key": public_key,
        "install_command": build_public_key_install_command(user_id, public_key),
    }


def generate_user_ssh_key(user_id):
    ssh_keygen_path = shutil.which("ssh-keygen")
    if not ssh_keygen_path:
        raise ValueError("ssh-keygen is not installed.")

    private_path = user_ssh_key_path(user_id)
    public_path = f"{private_path}.pub"
    os.makedirs(os.path.dirname(private_path), exist_ok=True)

    if os.path.isfile(private_path) and os.path.isfile(public_path):
        return get_user_ssh_key_info(user_id)

    completed = subprocess.run(
        [
            ssh_keygen_path,
            "-t",
            "ed25519",
            "-C",
            f"oneboard-user-{user_id}",
            "-N",
            "",
            "-f",
            private_path,
        ],
        text=True,
        input="",
        capture_output=True,
        timeout=30,
    )
    if completed.returncode != 0:
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        raise ValueError(output or f"ssh-keygen exited with code {completed.returncode}")
    try:
        os.chmod(private_path, 0o600)
        os.chmod(public_path, 0o644)
    except OSError:
        pass
    return get_user_ssh_key_info(user_id)


def build_public_key_install_command(user_id, public_key):
    install_inner = "mkdir -p ~/.ssh && chmod 700 ~/.ssh && printf '%s\\n' " + shlex.quote(public_key) + " >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
    remote = get_remote_connection(user_id)
    if remote and remote["host"] and remote["username"]:
        target = f"{remote['username']}@{remote['host']}"
        port = str(remote["port"] or 22)
        return f"ssh -p {shlex.quote(port)} {shlex.quote(target)} {shlex.quote(install_inner)}"
    return install_inner


def build_remote_connection_candidate(
    user_id,
    host,
    port,
    username,
    remote_path,
    key_path,
    auth_method="key",
    password="",
):
    if not host or not username or not remote_path:
        raise ValueError(translate("site.remote_not_connected"))
    validate_remote_identity(host, username)
    remote_path = validate_remote_website_path(remote_path, username)
    try:
        port = int(port or 22)
    except (TypeError, ValueError) as error:
        raise ValueError(translate("site.remote_port")) from error
    if port < 1 or port > 65535:
        raise ValueError(translate("site.remote_port"))
    if auth_method not in {"key", "password"}:
        raise ValueError(translate("site.remote_not_connected"))
    existing = get_remote_connection_private(user_id)
    same_login = bool(
        existing
        and existing["host"] == host
        and int(existing["port"] or 22) == port
        and existing["username"] == username
    )
    effective_password = password or (
        existing["password"] if auth_method == "password" and same_login else ""
    )
    if auth_method == "password" and not effective_password:
        raise ValueError(translate("flash.remote_password_required"))
    key_path = os.path.abspath(os.path.expanduser(key_path)) if key_path else ""
    if auth_method == "key" and key_path and not os.path.isfile(key_path):
        raise ValueError(translate("site.remote_key_path"))
    return {
        "host": host,
        "port": port,
        "username": username,
        "remote_path": remote_path,
        "key_path": key_path,
        "auth_method": auth_method,
        "password": effective_password if auth_method == "password" else "",
    }


@locked_site_operation
def save_remote_connection(user_id, host, port, username, remote_path, key_path, auth_method="key", password=""):
    existing = get_remote_connection_private(user_id)
    remote = build_remote_connection_candidate(
        user_id,
        host,
        port,
        username,
        remote_path,
        key_path,
        auth_method,
        password,
    )
    same_remote = bool(
        existing
        and existing["host"] == remote["host"]
        and int(existing["port"] or 22) == remote["port"]
        and existing["username"] == remote["username"]
        and existing["remote_path"] == remote["remote_path"]
    )
    directory_path = existing["directory_path"] if same_remote else None

    execute_db(
        """
        INSERT INTO website_remote_connections (
            user_id, host, port, username, remote_path, key_path, auth_method, password, directory_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            host = excluded.host,
            port = excluded.port,
            username = excluded.username,
            remote_path = excluded.remote_path,
            key_path = excluded.key_path,
            auth_method = excluded.auth_method,
            password = excluded.password,
            directory_path = excluded.directory_path,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            remote["host"],
            remote["port"],
            remote["username"],
            remote["remote_path"],
            remote["key_path"],
            remote["auth_method"],
            remote["password"],
            directory_path,
        ),
    )


def get_remote_connection(user_id):
    row = query_db(
        """
        SELECT id, host, port, username, remote_path, key_path, auth_method,
               CASE WHEN password IS NOT NULL AND password != '' THEN 1 ELSE 0 END AS has_password,
               directory_path, created_at, updated_at
        FROM website_remote_connections
        WHERE user_id = ?
        """,
        (user_id,),
        one=True,
    )
    if not row:
        return None
    remote = dict(row)
    directory = get_site_directory(user_id)
    remote["directory_matches"] = bool(
        directory
        and remote.get("directory_path")
        and os.path.realpath(remote["directory_path"]) == os.path.realpath(directory["path"])
    )
    return remote


def get_remote_connection_private(user_id):
    return query_db(
        """
        SELECT id, host, port, username, remote_path, key_path, auth_method, password, directory_path,
               created_at, updated_at
        FROM website_remote_connections
        WHERE user_id = ?
        """,
        (user_id,),
        one=True,
    )


def require_remote_connection(user_id):
    remote = get_remote_connection_private(user_id)
    if not remote:
        raise ValueError(translate("flash.remote_required"))
    return remote


def validate_remote_identity(host, username):
    identity_pattern = re.compile(r"^[A-Za-z0-9._-]+$")
    host_pattern = re.compile(r"^[A-Za-z0-9._:-]+$")
    if (
        not identity_pattern.match(username or "")
        or not host_pattern.match(host or "")
        or username.startswith("-")
        or host.startswith("-")
    ):
        raise ValueError(translate("site.remote_not_connected"))
    if username.casefold() == "root":
        raise ValueError(translate("site.remote_root_user"))


def validate_remote_website_path(remote_path, username):
    """Return a normalized POSIX website path that is safe for sync/deploy."""
    remote_path = str(remote_path or "").strip()
    if (
        not remote_path.startswith("/")
        or "\\" in remote_path
        or "~" in remote_path
        or any(ord(character) < 32 or ord(character) == 127 for character in remote_path)
    ):
        raise ValueError(translate("site.remote_path_unsafe"))

    components = remote_path.split("/")[1:]
    if not components or any(component in {"", ".", ".."} for component in components):
        if len(components) == 1 and components[0] == "":
            raise ValueError(translate("site.remote_path_unsafe"))
        if remote_path.endswith("/") and remote_path.count("/") > 1:
            components = remote_path.rstrip("/").split("/")[1:]
        if not components or any(component in {"", ".", ".."} for component in components):
            raise ValueError(translate("site.remote_path_unsafe"))

    normalized = posixpath.normpath(remote_path)
    if normalized == "/" or normalized != remote_path.rstrip("/"):
        raise ValueError(translate("site.remote_path_unsafe"))

    forbidden_trees = (
        "/bin",
        "/boot",
        "/dev",
        "/etc",
        "/lib",
        "/lib64",
        "/proc",
        "/root",
        "/run",
        "/sbin",
        "/sys",
        "/usr",
    )
    if any(normalized == root or normalized.startswith(root + "/") for root in forbidden_trees):
        raise ValueError(translate("site.remote_path_unsafe"))

    protected_roots = {"/home", "/Users", "/srv", "/var", "/var/www", "/opt", "/tmp"}
    user_homes = {f"/home/{username}", f"/Users/{username}"}
    if normalized in protected_roots or normalized in user_homes or len(components) < 2:
        raise ValueError(translate("site.remote_path_unsafe"))
    return normalized


@locked_site_operation
def sync_remote_site_to_workspace(user_id):
    remote = require_remote_connection(user_id)
    workspace_path = os.path.abspath(remote_workspace_path(user_id, remote))
    user_root = os.path.abspath(os.path.join(REMOTE_WORKSPACE_DIR, str(user_id)))
    os.makedirs(user_root, mode=0o700, exist_ok=True)
    if os.path.islink(REMOTE_WORKSPACE_DIR) or os.path.islink(user_root):
        raise ValueError(translate("site.internal_directory_unsafe"))
    if os.path.lexists(workspace_path) and os.path.islink(workspace_path):
        raise ValueError(translate("site.internal_directory_unsafe"))
    if path_contains_symlink(user_root, workspace_path):
        raise ValueError(translate("site.internal_directory_unsafe"))

    workspace_real_path = os.path.realpath(workspace_path)
    directory = get_site_directory(user_id)
    already_connected = bool(
        directory
        and remote["directory_path"]
        and os.path.realpath(directory["path"]) == workspace_real_path
        and os.path.realpath(remote["directory_path"]) == workspace_real_path
    )

    stage_path = tempfile.mkdtemp(prefix=".oneboard-sync-", dir=user_root)
    rollback_path = ""
    try:
        run_rsync_remote_to_local(remote, stage_path)
        unsupported_entry = find_unsupported_workspace_entry(stage_path)
        if unsupported_entry:
            raise ValueError(translate("site.unsupported_entry", path=unsupported_entry))
        unsafe_symlink = find_unsafe_workspace_symlink(stage_path)
        if unsafe_symlink:
            raise ValueError(translate("site.unsafe_symlink", path=unsafe_symlink))

        if os.path.isdir(workspace_path):
            validate_site_internal_tree(workspace_path)
            private_state = os.path.join(workspace_path, ".oneboard")
            if os.path.isdir(private_state) and not os.path.islink(private_state):
                shutil.copytree(
                    private_state,
                    os.path.join(stage_path, ".oneboard"),
                    symlinks=True,
                    dirs_exist_ok=True,
                )
        validate_site_internal_tree(stage_path)

        if already_connected and managed_workspace_has_content(workspace_path):
            create_site_backup(user_id)

        if os.path.lexists(workspace_path):
            rollback_path = f"{workspace_path}.before-sync-{secrets.token_hex(6)}"
            os.replace(workspace_path, rollback_path)
        try:
            os.replace(stage_path, workspace_path)
            stage_path = ""
        except Exception:
            if rollback_path and not os.path.lexists(workspace_path):
                os.replace(rollback_path, workspace_path)
                rollback_path = ""
            raise

        try:
            connect_managed_remote_workspace(user_id, workspace_path, remote)
            execute_db(
                "UPDATE website_remote_connections SET directory_path = ?, updated_at = CURRENT_TIMESTAMP WHERE user_id = ?",
                (workspace_real_path, user_id),
            )
            record_update_history(
                user_id,
                "remote-sync",
                f"Synced {remote['username']}@{remote['host']}:{remote['remote_path']} into local workspace.",
                "0",
                status="approved",
            )
        except Exception:
            failed_stage = tempfile.mkdtemp(prefix=".oneboard-failed-sync-", dir=user_root)
            os.rmdir(failed_stage)
            os.replace(workspace_path, failed_stage)
            if rollback_path:
                os.replace(rollback_path, workspace_path)
                rollback_path = ""
            stage_path = failed_stage
            raise
    finally:
        for disposable_path in (stage_path, rollback_path):
            if (
                disposable_path
                and os.path.isdir(disposable_path)
                and not os.path.islink(disposable_path)
                and lexical_path_is_inside(user_root, disposable_path)
            ):
                shutil.rmtree(disposable_path, ignore_errors=True)
    return workspace_real_path


def managed_workspace_has_content(workspace_path):
    try:
        with os.scandir(workspace_path) as entries:
            return any(not is_reserved_site_component(entry.name) for entry in entries)
    except FileNotFoundError:
        return False


@locked_site_operation
def publish_site_to_remote(user_id, update_id=None):
    update = None
    if update_id is not None:
        update = require_update_for_current_directory(user_id, update_id)
        if update["status"] != "approved":
            raise ValueError(translate("site.publish_requires_approval"))

    remote = require_remote_connection(user_id)
    directory = require_site_directory(user_id)
    if not remote["directory_path"] or os.path.realpath(remote["directory_path"]) != os.path.realpath(directory["path"]):
        raise ValueError(translate("site.remote_directory_mismatch"))
    validate_site_internal_tree(directory["path"])
    unsupported_entry = find_unsupported_workspace_entry(directory["path"])
    if unsupported_entry:
        raise ValueError(translate("site.unsupported_entry", path=unsupported_entry))
    unsafe_symlink = find_unsafe_workspace_symlink(directory["path"])
    if unsafe_symlink:
        raise ValueError(translate("site.unsafe_symlink", path=unsafe_symlink))
    remote_backup_path = run_rsync_local_to_remote(remote, directory["path"])
    backup_note = (
        f" Previous release retained at {remote_backup_path}."
        if isinstance(remote_backup_path, str) and remote_backup_path
        else ""
    )
    if update:
        set_update_status(user_id, update["id"], "published")
        record_update_history(user_id, "publish", f"Published update #{update['id']} to {remote['username']}@{remote['host']}:{remote['remote_path']}.{backup_note}", "0", status="published")
    else:
        record_update_history(user_id, "publish", f"Published workspace to {remote['username']}@{remote['host']}:{remote['remote_path']}.{backup_note}", "0", status="published")


def remote_workspace_path(user_id, remote):
    fingerprint = hashlib.sha256(
        f"{remote['username']}@{remote['host']}:{remote['port']}:{remote['remote_path']}".encode("utf-8")
    ).hexdigest()[:14]
    safe_host = re.sub(r"[^A-Za-z0-9_.-]+", "-", remote["host"]).strip("-") or "remote"
    return os.path.join(REMOTE_WORKSPACE_DIR, str(user_id), f"{safe_host}-{fingerprint}")


def run_rsync_remote_to_local(remote, workspace_path):
    test_remote_connection(remote)
    source = remote_rsync_location(remote, remote["remote_path"].rstrip("/") + "/")
    destination = os.path.join(workspace_path, "")
    run_rsync(remote, source, destination)


def run_rsync_local_to_remote(remote, workspace_path):
    if not managed_workspace_has_content(workspace_path):
        raise ValueError(translate("site.remote_empty_workspace"))
    test_remote_connection(remote)
    stage_path, backup_path = prepare_remote_release(remote)
    source = os.path.join(workspace_path, "")
    destination = remote_rsync_location(remote, stage_path.rstrip("/") + "/")
    run_rsync(remote, source, destination)
    activate_remote_release(remote, stage_path, backup_path)
    return backup_path


def remote_rsync_location(remote, remote_path):
    host = remote["host"]
    if ":" in host:
        host = f"[{host}]"
    return f"{remote['username']}@{host}:{shlex.quote(remote_path)}"


def remote_release_paths(remote):
    target_path = validate_remote_website_path(remote["remote_path"], remote["username"])
    parent_path = posixpath.dirname(target_path)
    target_fingerprint = hashlib.sha256(target_path.encode("utf-8")).hexdigest()[:12]
    release_token = secrets.token_hex(8)
    timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    stage_path = posixpath.join(parent_path, f".oneboard-stage-{target_fingerprint}-{release_token}")
    backup_path = posixpath.join(
        parent_path,
        f".oneboard-backup-{target_fingerprint}-{timestamp}-{release_token}",
    )
    return target_path, stage_path, backup_path


def prepare_remote_release(remote):
    target_path, stage_path, backup_path = remote_release_paths(remote)
    probe = "; ".join(
        [
            "set -eu",
            f"target={shlex.quote(target_path)}",
            f"stage={shlex.quote(stage_path)}",
            "test -d \"$target\" && test ! -L \"$target\" || { printf '%s\\n' ONEBOARD_REMOTE_PATH_CHANGED; exit 45; }",
            "test ! -e \"$stage\" || { printf '%s\\n' ONEBOARD_REMOTE_STAGE_EXISTS; exit 46; }",
            "mkdir \"$stage\" || { printf '%s\\n' ONEBOARD_REMOTE_STAGE_PREPARE_FAILED; exit 51; }",
            "rsync -rlpt --safe-links \"$target/\" \"$stage/\" || { printf '%s\\n' ONEBOARD_REMOTE_STAGE_PREPARE_FAILED; exit 52; }",
            "printf '%s\\n' ONEBOARD_REMOTE_STAGE_READY",
        ]
    )
    completed = run_remote_shell(remote, probe, timeout=120)
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if completed.returncode != 0 or "ONEBOARD_REMOTE_STAGE_READY" not in output:
        raise ValueError(
            humanize_remote_sync_error(output, completed.returncode)
            or f"remote staging exited with code {completed.returncode}"
        )
    return stage_path, backup_path


def activate_remote_release(remote, stage_path, backup_path):
    target_path = validate_remote_website_path(remote["remote_path"], remote["username"])
    expected_target, expected_stage, expected_backup = remote_release_paths_for_values(
        target_path,
        stage_path,
        backup_path,
    )
    script = "; ".join(
        [
            "set -eu",
            f"target={shlex.quote(expected_target)}",
            f"stage={shlex.quote(expected_stage)}",
            f"backup={shlex.quote(expected_backup)}",
            "rollback_needed=0",
            "rollback_previous() { status=$?; trap - EXIT HUP INT TERM; if test \"$rollback_needed\" = 1 && test ! -e \"$target\" && test -d \"$backup\"; then mv \"$backup\" \"$target\" || true; fi; exit \"$status\"; }",
            "trap rollback_previous EXIT HUP INT TERM",
            "test -d \"$target\" && test ! -L \"$target\" || { printf '%s\\n' ONEBOARD_REMOTE_PATH_CHANGED; exit 45; }",
            "test -d \"$stage\" && test ! -L \"$stage\" || { printf '%s\\n' ONEBOARD_REMOTE_STAGE_MISSING; exit 47; }",
            "test ! -e \"$backup\" || { printf '%s\\n' ONEBOARD_REMOTE_BACKUP_EXISTS; exit 48; }",
            "mv \"$target\" \"$backup\" || { printf '%s\\n' ONEBOARD_REMOTE_BACKUP_FAILED; exit 50; }",
            "rollback_needed=1",
            "mv \"$stage\" \"$target\" || { printf '%s\\n' ONEBOARD_REMOTE_ACTIVATION_FAILED; exit 49; }",
            "rollback_needed=0",
            "trap - EXIT HUP INT TERM",
            "printf '%s\\n' ONEBOARD_REMOTE_RELEASE_ACTIVE",
        ]
    )
    completed = run_remote_shell(remote, script, timeout=90)
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if completed.returncode != 0 or "ONEBOARD_REMOTE_RELEASE_ACTIVE" not in output:
        raise ValueError(
            humanize_remote_sync_error(output, completed.returncode)
            or translate("site.remote_activation_failed")
        )


def remote_release_paths_for_values(target_path, stage_path, backup_path):
    parent_path = posixpath.dirname(target_path)
    target_fingerprint = hashlib.sha256(target_path.encode("utf-8")).hexdigest()[:12]
    stage_prefix = posixpath.join(parent_path, f".oneboard-stage-{target_fingerprint}-")
    backup_prefix = posixpath.join(parent_path, f".oneboard-backup-{target_fingerprint}-")
    if (
        posixpath.dirname(stage_path) != parent_path
        or posixpath.dirname(backup_path) != parent_path
        or not stage_path.startswith(stage_prefix)
        or not backup_path.startswith(backup_prefix)
        or not re.fullmatch(r"[a-f0-9]{16}", stage_path.removeprefix(stage_prefix))
        or not re.fullmatch(r"[0-9]{14}-[a-f0-9]{16}", backup_path.removeprefix(backup_prefix))
    ):
        raise ValueError(translate("site.remote_path_unsafe"))
    return target_path, stage_path, backup_path


def run_rsync(remote, source, destination):
    rsync_path = shutil.which("rsync")
    if not rsync_path:
        raise ValueError("rsync is not installed.")

    ssh_command = build_remote_ssh_command(remote)
    command = [
        rsync_path,
        "-rlptz",
        "--delete",
        "--safe-links",
        "--exclude",
        ".git",
        "--exclude",
        ".oneboard",
        "--exclude",
        "__pycache__",
        "-e",
        ssh_command,
        source,
        destination,
    ]
    completed = run_remote_process(remote, command, timeout=240)
    if completed.returncode != 0:
        output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
        raise ValueError(
            humanize_remote_sync_error(output, completed.returncode)
            or f"rsync exited with code {completed.returncode}"
        )


def humanize_remote_sync_error(output, returncode=None):
    if returncode == 77:
        return translate("flash.remote_permission_denied")
    if returncode == 124:
        return translate("flash.remote_timeout")
    if not output:
        return ""
    normalized = output.lower()
    if "oneboard_remote_path_missing" in normalized:
        return translate("site.remote_path_missing")
    if "oneboard_remote_path_unreadable" in normalized:
        return translate("site.remote_path_unreadable")
    if "oneboard_remote_path_unwritable" in normalized:
        return translate("site.remote_path_unwritable")
    if "oneboard_remote_parent_unwritable" in normalized:
        return translate("site.remote_parent_unwritable")
    if "oneboard_remote_path_changed" in normalized:
        return translate("site.remote_path_changed")
    if "oneboard_remote_root_user" in normalized:
        return translate("site.remote_root_user")
    if "oneboard_remote_rsync_missing" in normalized:
        return translate("site.remote_rsync_missing")
    if "oneboard_remote_stage_prepare_failed" in normalized:
        return translate("site.remote_staging_failed")
    if "oneboard_remote_activation_failed" in normalized or "oneboard_remote_backup_failed" in normalized:
        return translate("site.remote_activation_failed")
    if "oneboard_expect_timeout" in normalized:
        return translate("flash.remote_timeout")
    if "oneboard_expect_auth_rejected" in normalized:
        return translate("flash.remote_permission_denied")
    if "permission denied" in normalized or "publickey" in normalized or "keyboard-interactive" in normalized:
        return translate("flash.remote_permission_denied")
    if "no route to host" in normalized or "connection timed out" in normalized or "could not resolve hostname" in normalized:
        return output
    return output


def ensure_remote_known_hosts_file():
    if os.path.lexists(REMOTE_SSH_DIR) and os.path.islink(REMOTE_SSH_DIR):
        raise ValueError(translate("site.internal_directory_unsafe"))
    os.makedirs(REMOTE_SSH_DIR, mode=0o700, exist_ok=True)
    if not os.path.isdir(REMOTE_SSH_DIR):
        raise ValueError(translate("site.internal_directory_unsafe"))
    try:
        os.chmod(REMOTE_SSH_DIR, 0o700)
    except OSError:
        pass

    if os.path.lexists(REMOTE_KNOWN_HOSTS_PATH):
        if os.path.islink(REMOTE_KNOWN_HOSTS_PATH) or not os.path.isfile(REMOTE_KNOWN_HOSTS_PATH):
            raise ValueError(translate("site.internal_directory_unsafe"))
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(REMOTE_KNOWN_HOSTS_PATH, flags, 0o600)
    except OSError as error:
        raise ValueError(translate("site.internal_directory_unsafe")) from error
    try:
        os.fchmod(descriptor, 0o600)
    finally:
        os.close(descriptor)
    return REMOTE_KNOWN_HOSTS_PATH


def build_remote_ssh_arguments(remote):
    ssh_path = shutil.which("ssh")
    if not ssh_path:
        raise ValueError("ssh is not installed.")
    known_hosts_path = ensure_remote_known_hosts_file()
    if any(ord(character) < 32 or character == '"' for character in known_hosts_path):
        raise ValueError(translate("site.internal_directory_unsafe"))
    quoted_known_hosts_path = f'"{known_hosts_path}"'
    parts = [
        ssh_path,
        "-p",
        str(remote["port"]),
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"UserKnownHostsFile={quoted_known_hosts_path}",
        "-o",
        f"GlobalKnownHostsFile={os.devnull}",
        "-o",
        "ConnectTimeout=15",
        "-o",
        "ConnectionAttempts=1",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=2",
        "-o",
        "ClearAllForwardings=yes",
    ]
    if remote["auth_method"] == "key":
        parts.extend(["-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes"])
        if remote["key_path"]:
            parts.extend(["-i", os.path.expanduser(remote["key_path"])])
    else:
        parts.extend(
            [
                "-o",
                "BatchMode=no",
                "-o",
                "PreferredAuthentications=password,keyboard-interactive",
                "-o",
                "PasswordAuthentication=yes",
                "-o",
                "KbdInteractiveAuthentication=yes",
                "-o",
                "PubkeyAuthentication=no",
                "-o",
                "NumberOfPasswordPrompts=1",
            ]
        )
    return parts


def build_remote_ssh_command(remote):
    return shlex.join(build_remote_ssh_arguments(remote))


def find_system_expect():
    system_expect = "/usr/bin/expect"
    if os.path.isfile(system_expect) and os.access(system_expect, os.X_OK):
        return system_expect
    return shutil.which("expect")


def scrub_remote_secret(value, password):
    value = value or ""
    if not password:
        return value
    password_hex = password.encode("utf-8").hex()
    return value.replace(password, "[redacted]").replace(password_hex, "[redacted]").replace(
        password_hex.upper(), "[redacted]"
    )


def run_remote_process(remote, command, timeout):
    env = os.environ.copy()
    if remote["auth_method"] != "password":
        try:
            return subprocess.run(
                command,
                text=True,
                input="",
                capture_output=True,
                env=env,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as error:
            raise ValueError(translate("flash.remote_timeout")) from error

    password = remote["password"] or ""
    if not password:
        raise ValueError(translate("flash.remote_password_required"))
    expect_path = find_system_expect()
    if not expect_path:
        raise ValueError(translate("flash.remote_password_tool_missing"))

    script_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="oneboard-expect-",
            suffix=".tcl",
            delete=False,
        ) as script_file:
            script_path = script_file.name
            os.fchmod(script_file.fileno(), 0o600)
            script_file.write(EXPECT_PASSWORD_SCRIPT)

        wrapper_command = [expect_path, "-f", script_path, str(int(timeout)), *command]
        completed = subprocess.run(
            wrapper_command,
            text=True,
            input=password.encode("utf-8").hex() + "\n",
            capture_output=True,
            env=env,
            timeout=timeout + 5,
        )
        completed.stdout = scrub_remote_secret(completed.stdout, password)
        completed.stderr = scrub_remote_secret(completed.stderr, password)
        return completed
    except subprocess.TimeoutExpired as error:
        raise ValueError(translate("flash.remote_timeout")) from error
    finally:
        if script_path:
            try:
                os.unlink(script_path)
            except FileNotFoundError:
                pass


def run_remote_shell(remote, script, timeout=60):
    target = f"{remote['username']}@{remote['host']}"
    command = [*build_remote_ssh_arguments(remote), target, script]
    return run_remote_process(remote, command, timeout=timeout)


def test_remote_connection(remote):
    configured_path = validate_remote_website_path(remote["remote_path"], remote["username"])
    probe = "; ".join(
        [
            f"configured={shlex.quote(configured_path)}",
            "test \"$(id -u)\" -ne 0 || { printf '%s\\n' ONEBOARD_REMOTE_ROOT_USER; exit 40; }",
            "test -d \"$configured\" || { printf '%s\\n' ONEBOARD_REMOTE_PATH_MISSING; exit 41; }",
            "test ! -L \"$configured\" || { printf '%s\\n' ONEBOARD_REMOTE_PATH_CHANGED; exit 45; }",
            "test -r \"$configured\" && test -x \"$configured\" || { printf '%s\\n' ONEBOARD_REMOTE_PATH_UNREADABLE; exit 42; }",
            "test -w \"$configured\" || { printf '%s\\n' ONEBOARD_REMOTE_PATH_UNWRITABLE; exit 43; }",
            "canonical=$(cd \"$configured\" 2>/dev/null && pwd -P) || { printf '%s\\n' ONEBOARD_REMOTE_PATH_MISSING; exit 41; }",
            "test \"$canonical\" = \"$configured\" || { printf '%s\\n' ONEBOARD_REMOTE_PATH_CHANGED; exit 45; }",
            "parent=$(dirname \"$configured\")",
            "test -w \"$parent\" && test -x \"$parent\" || { printf '%s\\n' ONEBOARD_REMOTE_PARENT_UNWRITABLE; exit 46; }",
            "command -v rsync >/dev/null 2>&1 || { printf '%s\\n' ONEBOARD_REMOTE_RSYNC_MISSING; exit 44; }",
            "printf '%s\\n' ONEBOARD_REMOTE_READY",
        ]
    )
    completed = run_remote_shell(remote, probe, timeout=30)
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if completed.returncode != 0 or "ONEBOARD_REMOTE_READY" not in output:
        raise ValueError(
            humanize_remote_sync_error(output, completed.returncode)
            or f"ssh exited with code {completed.returncode}"
        )
    message = translate("site.remote_test_ready")
    return {
        "success": True,
        "ok": True,
        "message": message,
        "detail": message,
        "host": remote["host"],
        "port": remote["port"],
        "username": remote["username"],
        "remote_path": configured_path,
        "canonical_path": configured_path,
        "readable": True,
        "writable": True,
        "parent_writable": True,
        "rsync_available": True,
    }


def get_site_directory(user_id):
    return query_db(
        """
        SELECT id, user_id, path, created_at, updated_at
        FROM website_directories
        WHERE user_id = ?
        """,
        (user_id,),
        one=True,
    )


def require_site_directory(user_id):
    directory = get_site_directory(user_id)
    if not directory:
        raise ValueError(translate("flash.site_directory_unmapped"))
    if not os.path.isdir(directory["path"]):
        raise ValueError(translate("flash.site_path_missing"))
    return directory


def validate_expected_site_directory(user_id, expected_path):
    expected_path = str(expected_path or "").strip()
    if not expected_path:
        return
    directory = require_site_directory(user_id)
    expected_real_path = os.path.realpath(os.path.abspath(os.path.expanduser(expected_path)))
    current_real_path = os.path.realpath(directory["path"])
    if expected_real_path != current_real_path:
        raise ValueError(translate("site.directory_changed"))


def configured_site_directory_path():
    for key in SITE_DIRECTORY_ENV_KEYS:
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def normalize_site_url(site_url):
    site_url = site_url.strip()
    if not site_url:
        raise ValueError(translate("flash.select_property"))
    return site_url


def get_website_project(site_url):
    return query_db(
        """
        SELECT id, site_url, path, created_at, updated_at
        FROM website_projects
        WHERE site_url = ?
        """,
        (normalize_site_url(site_url),),
        one=True,
    )


def set_website_project_directory(site_url, path):
    site_url = normalize_site_url(site_url)
    normalized_path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isdir(normalized_path):
        raise ValueError(translate("flash.site_path_missing"))
    execute_db(
        """
        INSERT INTO website_projects (site_url, path)
        VALUES (?, ?)
        ON CONFLICT(site_url) DO UPDATE SET
            path = excluded.path,
            updated_at = CURRENT_TIMESTAMP
        """,
        (site_url, normalized_path),
    )


@locked_site_operation
def run_site_terminal_command(user_id, command):
    if not command:
        raise ValueError(translate("flash.command_required"))

    directory = require_site_directory(user_id)
    started_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    workspace_path = directory["path"]
    command_env = build_site_command_env(workspace_path)
    command_args = sandboxed_tool_command(workspace_path, command)
    timeout = site_command_timeout()
    try:
        completed = subprocess.run(
            command_args,
            cwd=workspace_path,
            env=command_env,
            text=True,
            input="",
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        output = decode_process_output(error.stdout) + decode_process_output(error.stderr)
        return {
            "command": command,
            "cwd": workspace_path,
            "exit_code": "timeout",
            "output": output.strip() or translate("flash.command_timeout"),
            "started_at": started_at,
        }

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    return {
        "command": command,
        "cwd": workspace_path,
        "exit_code": completed.returncode,
        "output": output or translate("site.no_output"),
        "started_at": started_at,
    }


@locked_site_operation
def run_site_codex_update(user_id, prompt, suggested_image_path=None, provider=None, model=None):
    if not prompt:
        raise ValueError(translate("flash.codex_prompt_required"))
    provider, model = resolve_ai_provider_model(user_id, provider=provider, model=model)
    if not get_user_ai_provider_api_key(user_id, provider):
        raise ValueError(f"No API key configured for provider '{provider}'.")
    directory = require_site_directory(user_id)
    workspace_path = os.path.realpath(directory["path"])
    before_manifest = build_workspace_manifest(workspace_path)
    unsafe_symlink = find_unsafe_workspace_symlink(workspace_path, before_manifest)
    if unsafe_symlink:
        raise ValueError(translate("site.unsafe_symlink", path=unsafe_symlink))
    snapshot_path = create_update_snapshot(user_id, workspace_path)
    save_codex_message(user_id, "user", prompt)
    guarded_prompt = build_design_preserving_codex_prompt(prompt, suggested_image_path)
    result = run_site_ai_fallback_update(user_id, workspace_path, guarded_prompt, provider, model)
    history_source = f"ai-direct:{provider}"
    reply = result.get("reply") or result.get("output") or ""
    after_manifest = build_workspace_manifest(workspace_path)
    changed_files = compare_workspace_manifests(before_manifest, after_manifest)
    diff_summary = build_update_diff_summary(workspace_path, snapshot_path, changed_files)
    save_codex_message(user_id, "assistant", reply, result["output"], result["exit_code"])
    unsafe_symlink = find_unsafe_workspace_symlink(workspace_path, after_manifest)
    succeeded = str(result["exit_code"]) == "0" and not unsafe_symlink
    history_exit_code = result["exit_code"] if not unsafe_symlink else "unsafe-symlink"
    summary = reply
    rollback_error = ""
    if not succeeded:
        try:
            restore_workspace_changes(workspace_path, snapshot_path, changed_files)
        except (ValueError, OSError, zipfile.BadZipFile, KeyError, TypeError) as error:
            rollback_error = str(error)
        if unsafe_symlink:
            summary = translate("site.unsafe_symlink", path=unsafe_symlink)
    record_update_history(
        user_id,
        history_source,
        summary,
        history_exit_code,
        status="pending" if succeeded else "failed",
        snapshot_path=snapshot_path,
        changed_files=changed_files,
        diff_summary=diff_summary,
        directory_path=workspace_path,
    )
    if not succeeded:
        detail = (summary or result.get("output") or translate("site.no_output")).strip()
        if rollback_error:
            detail = f"{detail} Automatic rollback also failed: {rollback_error}"
        raise ValueError(translate("flash.codex_failed", error=detail[:800]))
    result["provider"] = provider
    result["model"] = model
    return result


def run_site_ai_fallback_update(user_id, workspace_path, prompt, provider, model):
    site_context = collect_site_edit_context(workspace_path)
    instruction = build_site_direct_edit_instruction(prompt, site_context)
    text, usage, resolved_model = run_ai_provider_prompt(user_id, provider, model, instruction)
    update_plan = parse_site_ai_update_plan(text)
    apply_site_ai_update_plan(workspace_path, update_plan)
    save_ai_run(
        user_id,
        provider,
        resolved_model,
        "website_update",
        instruction,
        response_text=text,
        usage=usage,
    )
    summary = (update_plan.get("summary") or "Website update applied.").strip()
    return {
        "command": f"{provider} direct site update",
        "cwd": workspace_path,
        "exit_code": 0,
        "output": summary,
        "reply": summary,
        "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "usage": usage,
    }


def collect_site_edit_context(workspace_path, max_files=8, max_chars=24000):
    candidates = []
    priority_names = {
        "index.html": 0,
        "home.html": 1,
        "styles.css": 2,
        "style.css": 3,
        "main.css": 4,
        "app.js": 5,
        "main.js": 6,
    }
    for root, dirs, files in os.walk(workspace_path, followlinks=False):
        dirs[:] = [item for item in dirs if not is_reserved_site_component(item) and not os.path.islink(os.path.join(root, item))]
        for file_name in files:
            source_path = os.path.join(root, file_name)
            if is_reserved_site_component(file_name) or os.path.islink(source_path):
                continue
            if not is_text_file(source_path) or not path_is_inside(workspace_path, source_path):
                continue
            relative_path = os.path.relpath(source_path, workspace_path).replace("\\", "/")
            try:
                size = os.path.getsize(source_path)
            except OSError:
                continue
            priority = priority_names.get(file_name.lower(), 50)
            if relative_path.endswith(".html"):
                priority -= 10
            elif relative_path.endswith(".css"):
                priority -= 5
            candidates.append((priority, size, relative_path, source_path))

    selected = []
    consumed = 0
    for _priority, _size, relative_path, source_path in sorted(candidates, key=lambda item: (item[0], item[1], item[2])):
        if len(selected) >= max_files or consumed >= max_chars:
            break
        try:
            with open(source_path, "r", encoding="utf-8", errors="replace") as file:
                content = file.read(min(8000, max_chars - consumed))
        except OSError:
            continue
        if not content.strip():
            continue
        consumed += len(content)
        selected.append({"path": relative_path, "content": content})

    if not selected:
        raise ValueError("No editable text files were found in the connected website directory.")
    return selected


def build_site_direct_edit_instruction(prompt, site_context):
    files_description = []
    for item in site_context:
        files_description.append(
            f"FILE: {item['path']}\n---BEGIN CONTENT---\n{item['content']}\n---END CONTENT---"
        )
    joined_files = "\n\n".join(files_description)
    return f"""
You are editing a customer's website directly. Use only the files provided below as context.

Requirements:
- Preserve the site's current visual identity and structure.
- Change only files that are necessary for the user's request.
- Stay inside the website workspace.
- Return valid JSON only, with no markdown fences.
- JSON schema:
  {{
    "summary": "short explanation of the applied update",
    "files": [
      {{"path": "relative/path.ext", "content": "full new file content"}}
    ]
  }}
- Every file entry must contain the full replacement content for that file.
- Do not include binary files.

User request:
{prompt}

Available files:
{joined_files}
""".strip()


def parse_site_ai_update_plan(text):
    payload = (text or "").strip()
    if payload.startswith("```"):
        lines = payload.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        payload = "\n".join(lines).strip()
    try:
        plan = json.loads(payload)
    except json.JSONDecodeError as error:
        raise ValueError(f"The AI provider returned invalid edit instructions: {error}") from error
    if not isinstance(plan, dict) or not isinstance(plan.get("files"), list):
        raise ValueError("The AI provider did not return a valid file update plan.")
    return plan


def apply_site_ai_update_plan(workspace_path, plan):
    root_path = os.path.realpath(workspace_path)
    seen_paths = set()
    for item in plan.get("files") or []:
        if not isinstance(item, dict):
            raise ValueError("The AI provider returned an invalid file entry.")
        relative_path = str(item.get("path") or "").replace("\\", "/").strip("/")
        content = item.get("content")
        if (
            not relative_path
            or contains_parent_reference(relative_path)
            or relative_path_has_reserved_component(relative_path)
            or not isinstance(content, str)
            or not is_text_file(relative_path)
        ):
            raise ValueError("The AI provider returned an unsafe file update.")
        path_key = relative_path.casefold()
        if path_key in seen_paths:
            raise ValueError("The AI provider returned duplicate file updates.")
        seen_paths.add(path_key)
        target_path = os.path.abspath(os.path.join(root_path, relative_path))
        if not lexical_path_is_inside(root_path, target_path):
            raise ValueError(translate("site.file_outside_workspace"))
        parent_path = os.path.dirname(target_path)
        if not path_is_inside(root_path, parent_path) or path_contains_symlink(root_path, parent_path):
            raise ValueError(translate("site.file_outside_workspace"))
        os.makedirs(parent_path, exist_ok=True)
        with open(target_path, "w", encoding="utf-8", errors="strict") as file:
            file.write(content)
    if not seen_paths:
        raise ValueError("The AI provider did not propose any file changes.")


def build_design_preserving_codex_prompt(prompt, suggested_image_path=None):
    image_instruction = ""
    if suggested_image_path:
        image_instruction = f"""

User-provided image:
- The user uploaded an image for this update at: {suggested_image_path}
- Use this image only if it helps satisfy the user's request.
- If you use it in the public website, copy it into the site's normal public assets/images location and reference that public copy.
- Do not use unrelated generated or stock imagery when this uploaded image is clearly intended for the requested update.
""".rstrip()

    return f"""
You are editing a customer's website. Before changing files, inspect the existing website structure and visual design.

Rules:
- Stay strictly inside the selected website directory.
- Read the existing HTML, CSS, assets, navigation, footer, and component patterns before creating or editing pages.
- Preserve the original visual identity. New pages must look like they belong to the same site.
- Reuse existing CSS/classes/assets whenever possible.
- Do not replace the site with a different theme or unrelated layout.
{image_instruction}

User request:
{prompt}
""".strip()


def build_guided_seo_prompt(title, keyword, tone, audience, cta):
    return f"""
Create or update a website page using this guided SEO brief.

Page title: {title or "Untitled page"}
Target keyword: {keyword or "primary service keyword"}
Tone: {tone or "clear, professional, conversion-focused"}
Audience: {audience or "qualified website visitors"}
Call to action: {cta or "contact the business"}

Requirements:
- Match the existing website design and content structure.
- Write useful, non-generic copy with headings, short sections, and a clear CTA.
- Add or update internal navigation only if the site has an obvious pattern for it.
- Keep all work inside the selected website directory.
""".strip()


def build_quick_prompts():
    return {
        "hero": "Update the homepage hero section with stronger positioning, clearer value proposition, and a more direct call to action. Preserve the existing design system.",
        "section": "Add a new useful content section to the most appropriate page. Match the current layout, spacing, typography, and navigation patterns.",
        "cta": "Improve the primary call to action across the page so it is clearer, more specific, and easier to act on without changing the site's visual identity.",
        "landing": "Create a focused landing page for a core service using the site's existing components, navigation, footer, and CSS patterns.",
    }


def save_codex_message(user_id, role, content, raw_output=None, exit_code=None):
    execute_db(
        """
        INSERT INTO website_codex_messages (user_id, role, content, raw_output, exit_code)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, role, content, raw_output, str(exit_code) if exit_code is not None else None),
    )


def list_codex_messages(user_id):
    return query_db(
        """
        SELECT id, role, content, exit_code, created_at
        FROM website_codex_messages
        WHERE user_id = ?
        ORDER BY id ASC
        """,
        (user_id,),
    )


def record_update_history(
    user_id,
    source,
    summary,
    exit_code=None,
    status="pending",
    snapshot_path=None,
    changed_files=None,
    diff_summary=None,
    directory_path=None,
):
    summary = (summary or translate("site.no_output")).strip()
    changed_files_json = json.dumps(changed_files or [])
    if directory_path is None:
        directory = get_site_directory(user_id)
        directory_path = os.path.realpath(directory["path"]) if directory else None
    execute_db(
        """
        INSERT INTO website_update_history (
            user_id, source, summary, exit_code, status, snapshot_path, changed_files, diff_summary, directory_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            source,
            summary[:1200],
            str(exit_code) if exit_code is not None else None,
            status,
            snapshot_path,
            changed_files_json,
            (diff_summary or "")[:8000],
            directory_path,
        ),
    )


def list_update_history(user_id):
    directory = get_site_directory(user_id)
    if not directory:
        return []
    current_directory = os.path.realpath(directory["path"])
    rows = query_db(
        """
        SELECT id, source, summary, exit_code, status, snapshot_path, changed_files, diff_summary, directory_path, created_at
        FROM website_update_history
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        LIMIT 20
        """,
        (user_id,),
    )
    updates = [format_update_history(row) for row in rows]
    return [
        update
        for update in updates
        if update.get("directory_path")
        and os.path.realpath(update["directory_path"]) == current_directory
    ]


def format_update_history(row):
    item = dict(row)
    try:
        item["files"] = json.loads(item.get("changed_files") or "[]")
    except (TypeError, json.JSONDecodeError):
        item["files"] = []
    item["diff_summary"] = item.get("diff_summary") or ""
    return item


def set_update_status(user_id, update_id, status):
    update = require_update_for_current_directory(user_id, update_id)
    execute_db(
        "UPDATE website_update_history SET status = ? WHERE user_id = ? AND id = ?",
        (status, user_id, update["id"]),
    )


def get_update_history_item(user_id, update_id):
    try:
        update_id = int(update_id)
    except (TypeError, ValueError):
        return None
    row = query_db(
        """
        SELECT id, user_id, source, summary, exit_code, status, snapshot_path, changed_files, diff_summary, directory_path, created_at
        FROM website_update_history
        WHERE user_id = ? AND id = ?
        """,
        (user_id, update_id),
        one=True,
    )
    return format_update_history(row) if row else None


def require_update_for_current_directory(user_id, update_id):
    update = get_update_history_item(user_id, update_id)
    if not update:
        raise ValueError(translate("site.no_updates"))
    directory = require_site_directory(user_id)
    update_directory = update.get("directory_path")
    if not update_directory or os.path.realpath(update_directory) != os.path.realpath(directory["path"]):
        raise ValueError(translate("site.update_directory_mismatch"))
    return update


def create_update_snapshot(user_id, workspace_path):
    workspace_path = os.path.realpath(workspace_path)
    snapshot_dir = os.path.join(BACKUP_DIR, str(user_id), "update-snapshots")
    os.makedirs(snapshot_dir, exist_ok=True)
    filename = f"update-before-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(4)}.zip"
    snapshot_path = os.path.join(snapshot_dir, filename)
    with zipfile.ZipFile(snapshot_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for root, dirs, files in os.walk(workspace_path, followlinks=False):
            dirs[:] = [
                item
                for item in dirs
                if not is_reserved_site_component(item)
                and not os.path.islink(os.path.join(root, item))
            ]
            for file_name in files:
                source_path = os.path.join(root, file_name)
                if os.path.islink(source_path) or not os.path.isfile(source_path):
                    continue
                if not path_is_inside(workspace_path, source_path):
                    continue
                arcname = os.path.relpath(source_path, workspace_path).replace("\\", "/")
                try:
                    archive.write(source_path, arcname)
                except FileNotFoundError:
                    continue
    return snapshot_path


def build_workspace_manifest(workspace_path):
    workspace_path = os.path.realpath(workspace_path)
    manifest = {}
    for root, dirs, files in os.walk(workspace_path, followlinks=False):
        visible_dirs = []
        for item in dirs:
            source_path = os.path.join(root, item)
            if is_reserved_site_component(item):
                continue
            relpath = os.path.relpath(source_path, workspace_path).replace("\\", "/")
            if os.path.islink(source_path):
                try:
                    manifest[relpath] = {"kind": "symlink", "target": os.readlink(source_path)}
                except FileNotFoundError:
                    pass
                continue
            visible_dirs.append(item)
        dirs[:] = visible_dirs
        for file_name in files:
            source_path = os.path.join(root, file_name)
            if is_reserved_site_component(file_name):
                continue
            relpath = os.path.relpath(source_path, workspace_path).replace("\\", "/")
            if os.path.islink(source_path):
                try:
                    manifest[relpath] = {"kind": "symlink", "target": os.readlink(source_path)}
                except FileNotFoundError:
                    pass
                continue
            if not os.path.isfile(source_path) or not path_is_inside(workspace_path, source_path):
                continue
            try:
                manifest[relpath] = {"kind": "file", "digest": file_hash(source_path)}
            except FileNotFoundError:
                continue
    return manifest


def file_hash(path):
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compare_workspace_manifests(before, after):
    changed = []
    for path in sorted(set(before) | set(after)):
        if path not in before:
            item = {"path": path, "change": "created", "kind": after[path]["kind"]}
            if after[path]["kind"] == "symlink":
                item["target"] = after[path]["target"]
            changed.append(item)
        elif path not in after:
            item = {"path": path, "change": "deleted", "before_kind": before[path]["kind"]}
            if before[path]["kind"] == "symlink":
                item["before_target"] = before[path]["target"]
            changed.append(item)
        elif before[path] != after[path]:
            item = {
                "path": path,
                "change": "modified",
                "kind": after[path]["kind"],
                "before_kind": before[path]["kind"],
            }
            if before[path]["kind"] == "symlink":
                item["before_target"] = before[path]["target"]
            if after[path]["kind"] == "symlink":
                item["target"] = after[path]["target"]
            changed.append(item)
    return changed


def find_unsafe_workspace_symlink(workspace_path, manifest=None):
    workspace_path = os.path.realpath(workspace_path)
    manifest = manifest if manifest is not None else build_workspace_manifest(workspace_path)
    for relative_path, item in manifest.items():
        if item.get("kind") != "symlink":
            continue
        if os.path.isabs(item.get("target") or ""):
            return relative_path
        link_path = os.path.abspath(os.path.join(workspace_path, relative_path))
        if not path_is_inside(workspace_path, os.path.realpath(link_path)):
            return relative_path
    return ""


def find_unsupported_workspace_entry(workspace_path):
    workspace_path = os.path.realpath(workspace_path)
    pending_directories = [workspace_path]
    while pending_directories:
        current_path = pending_directories.pop()
        try:
            entries = list(os.scandir(current_path))
        except FileNotFoundError:
            continue
        for entry in entries:
            relative_path = os.path.relpath(entry.path, workspace_path).replace("\\", "/")
            try:
                mode = entry.stat(follow_symlinks=False).st_mode
            except FileNotFoundError:
                continue
            if stat_module.S_ISLNK(mode) or stat_module.S_ISREG(mode):
                continue
            if stat_module.S_ISDIR(mode):
                pending_directories.append(entry.path)
                continue
            return relative_path
    return ""


def build_update_diff_summary(workspace_path, snapshot_path, changed_files):
    if not snapshot_path or not os.path.exists(snapshot_path):
        return ""
    summaries = []
    with zipfile.ZipFile(snapshot_path, "r") as archive:
        names = set(archive.namelist())
        for item in changed_files[:8]:
            path = item["path"]
            current_path = os.path.join(workspace_path, path)
            if (
                not is_text_file(path)
                or item.get("kind") == "symlink"
                or item.get("before_kind") == "symlink"
                or os.path.islink(current_path)
            ):
                continue
            before_lines = []
            if path in names:
                before_text = archive.read(path).decode("utf-8", errors="replace")
                before_lines = before_text.splitlines()
            after_lines = []
            if os.path.exists(current_path) and os.path.isfile(current_path):
                with open(current_path, "r", encoding="utf-8", errors="replace") as file:
                    after_lines = file.read().splitlines()
            diff = "\n".join(
                difflib.unified_diff(
                    before_lines,
                    after_lines,
                    fromfile=f"before/{path}",
                    tofile=f"after/{path}",
                    lineterm="",
                    n=3,
                )
            )
            if diff:
                summaries.append(diff[:2500])
    return "\n\n".join(summaries)


@locked_site_operation
def restore_update_files(user_id, update_id):
    update = require_update_for_current_directory(user_id, update_id)
    if not update or not update["snapshot_path"] or not os.path.exists(update["snapshot_path"]):
        raise ValueError(translate("site.backup_missing"))
    if not isinstance(update.get("files"), list):
        raise ValueError(translate("site.snapshot_invalid"))
    directory = require_site_directory(user_id)
    root_path = os.path.realpath(directory["path"])
    restore_workspace_changes(root_path, update["snapshot_path"], update["files"])
    set_update_status(user_id, update_id, "restored")
    record_update_history(user_id, "restore", f"Restored files from update #{update_id}.", "0", status="restored")


def restore_workspace_changes(root_path, snapshot_path, changed_files):
    root_path = os.path.realpath(root_path)
    if not isinstance(changed_files, list):
        raise ValueError(translate("site.snapshot_invalid"))
    with zipfile.ZipFile(snapshot_path, "r") as archive:
        invalid_member = archive.testzip()
        if invalid_member:
            raise ValueError(translate("site.snapshot_invalid"))
        names = set(archive.namelist())
        operations = []
        operation_paths = set()
        seen_paths = set()
        for item in changed_files:
            if not isinstance(item, dict):
                raise ValueError(translate("site.snapshot_invalid"))
            relpath = str(item.get("path") or "").replace("\\", "/").strip("/")
            change = item.get("change")
            path_key = relpath.casefold()
            if (
                not relpath
                or contains_parent_reference(relpath)
                or relative_path_has_reserved_component(relpath)
                or change not in {"created", "deleted", "modified"}
                or path_key in seen_paths
            ):
                raise ValueError(translate("site.snapshot_invalid"))
            seen_paths.add(path_key)
            target_path = os.path.abspath(os.path.join(root_path, relpath))
            if not lexical_path_is_inside(root_path, target_path):
                raise ValueError(translate("site.file_outside_workspace"))

            before_kind = item.get("before_kind")
            if change != "created":
                before_kind = before_kind or "file"
                if before_kind not in {"file", "symlink"}:
                    raise ValueError(translate("site.snapshot_invalid"))
                if before_kind == "file":
                    if relpath not in names:
                        raise ValueError(translate("site.snapshot_invalid"))
                    info = archive.getinfo(relpath)
                    if ((info.external_attr >> 16) & 0o170000) == 0o120000:
                        raise ValueError(translate("site.snapshot_invalid"))
                else:
                    before_target = item.get("before_target")
                    if not isinstance(before_target, str) or not before_target or "\x00" in before_target:
                        raise ValueError(translate("site.snapshot_invalid"))
            operations.append((relpath, target_path, change, before_kind, item.get("before_target")))
            operation_paths.add(relpath.casefold())

        for relpath, target_path, _change, _before_kind, _before_target in operations:
            current_path = root_path
            for part in relpath.split("/")[:-1]:
                current_path = os.path.join(current_path, part)
                if os.path.islink(current_path):
                    ancestor_path = os.path.relpath(current_path, root_path).replace("\\", "/").casefold()
                    if ancestor_path not in operation_paths:
                        raise ValueError(translate("site.file_outside_workspace"))
                    break

        for _relpath, target_path, _change, _before_kind, _before_target in sorted(
            operations,
            key=lambda operation: operation[0].count("/"),
        ):
            if os.path.islink(target_path) or os.path.isfile(target_path):
                os.unlink(target_path)
            elif os.path.isdir(target_path):
                shutil.rmtree(target_path)

        for relpath, target_path, change, before_kind, before_target in sorted(
            operations,
            key=lambda operation: operation[0].count("/"),
        ):
            if change == "created":
                continue
            os.makedirs(os.path.dirname(target_path), exist_ok=True)
            if (
                path_contains_symlink(root_path, os.path.dirname(target_path))
                or not path_is_inside(root_path, os.path.dirname(target_path))
            ):
                raise ValueError(translate("site.file_outside_workspace"))
            if before_kind == "symlink":
                os.symlink(before_target, target_path)
                continue
            info = archive.getinfo(relpath)
            with archive.open(info) as source, open(target_path, "wb") as target:
                shutil.copyfileobj(source, target)
            mode = (info.external_attr >> 16) & 0o777
            if mode:
                os.chmod(target_path, mode)


def build_site_file_browser(user_id, relative_path="", preview_path=""):
    directory = require_site_directory(user_id)
    root_path = os.path.realpath(directory["path"])
    folder_path = resolve_site_file(user_id, relative_path, allow_root=True)
    if not os.path.isdir(folder_path):
        folder_path = root_path
        relative_path = ""

    entries = []
    for entry in sorted(os.scandir(folder_path), key=lambda item: (not item.is_dir(follow_symlinks=False), item.name.lower())):
        if is_reserved_site_component(entry.name) or entry.is_symlink():
            continue
        item_relative_path = os.path.relpath(entry.path, root_path).replace("\\", "/")
        is_dir = entry.is_dir(follow_symlinks=False)
        size = 0 if is_dir else entry.stat(follow_symlinks=False).st_size
        entries.append(
            {
                "name": entry.name,
                "path": item_relative_path,
                "is_dir": is_dir,
                "size_label": "-" if is_dir else format_bytes(size),
                "modified_at": datetime.fromtimestamp(entry.stat(follow_symlinks=False).st_mtime).strftime("%Y-%m-%d %H:%M"),
                "previewable": not is_dir and is_previewable_file(entry.path),
                "is_image": not is_dir and (mimetypes.guess_type(entry.path)[0] or "").startswith("image/"),
            }
        )

    current_relative_path = os.path.relpath(folder_path, root_path).replace("\\", "/")
    if current_relative_path == ".":
        current_relative_path = ""

    preview = build_site_file_preview(user_id, preview_path) if preview_path else None
    parent_path = os.path.dirname(current_relative_path).replace("\\", "/") if current_relative_path else ""
    return {
        "current_path": current_relative_path,
        "parent_path": parent_path,
        "entries": entries,
        "preview": preview,
    }


def build_site_file_preview(user_id, relative_path):
    absolute_path = resolve_site_file(user_id, relative_path)
    if not os.path.isfile(absolute_path):
        raise ValueError(translate("site.file_missing"))

    mime_type = mimetypes.guess_type(absolute_path)[0] or ""
    preview = {
        "path": relative_path,
        "name": os.path.basename(absolute_path),
        "type": "unsupported",
        "content": "",
        "raw_url": url_for("site_manager_file_raw", path=relative_path) if has_request_context() else "",
    }
    if mime_type.startswith("image/"):
        preview["type"] = "image"
        return preview
    if is_text_file(absolute_path):
        with open(absolute_path, "r", encoding="utf-8", errors="replace") as file:
            preview["content"] = file.read(20000)
        preview["type"] = "text"
        return preview
    return preview


def is_previewable_file(path):
    mime_type = mimetypes.guess_type(path)[0] or ""
    return mime_type.startswith("image/") or is_text_file(path)


def is_text_file(path):
    text_extensions = {
        ".css", ".csv", ".htm", ".html", ".js", ".json", ".md", ".php", ".py",
        ".txt", ".xml", ".yml", ".yaml",
    }
    return os.path.splitext(path)[1].lower() in text_extensions


def list_site_assets(user_id):
    directory = require_site_directory(user_id)
    root_path = os.path.realpath(directory["path"])
    try:
        asset_dir = ensure_site_internal_path(root_path, "user-assets", create=False)
    except ValueError:
        return []
    if not asset_dir:
        return []
    assets = []
    for entry in sorted(os.scandir(asset_dir), key=lambda item: item.stat(follow_symlinks=False).st_mtime, reverse=True):
        if not entry.is_file(follow_symlinks=False) or not is_previewable_file(entry.path):
            continue
        relative_path = os.path.relpath(entry.path, root_path).replace("\\", "/")
        assets.append(
            {
                "name": entry.name,
                "path": relative_path,
                "size_label": format_bytes(entry.stat(follow_symlinks=False).st_size),
                "raw_url": url_for("site_manager_asset_raw", path=relative_path) if has_request_context() else "",
            }
        )
    return assets


def validate_asset_path(user_id, relative_path):
    absolute_path = resolve_site_file(
        user_id,
        relative_path,
        allow_oneboard=relative_path.startswith(".oneboard/user-assets/"),
    )
    mime_type = mimetypes.guess_type(absolute_path)[0] or ""
    if not os.path.isfile(absolute_path) or not mime_type.startswith("image/"):
        raise ValueError(translate("site.file_missing"))
    return absolute_path


def resolve_site_file(user_id, relative_path, allow_root=False, allow_oneboard=False, allow_final_symlink=False):
    directory = require_site_directory(user_id)
    root_path = os.path.realpath(directory["path"])
    relative_path = (relative_path or "").replace("\\", "/").strip("/")
    if contains_parent_reference(relative_path):
        raise ValueError(translate("site.file_outside_workspace"))
    if relative_path_has_reserved_component(relative_path, allow_internal_assets=allow_oneboard):
        raise ValueError(translate("site.file_outside_workspace"))
    absolute_path = os.path.abspath(os.path.join(root_path, relative_path))
    if not lexical_path_is_inside(root_path, absolute_path):
        raise ValueError(translate("site.file_outside_workspace"))
    if absolute_path == root_path and not allow_root:
        raise ValueError(translate("site.file_missing"))
    if not os.path.lexists(absolute_path):
        raise ValueError(translate("site.file_missing"))
    if absolute_path != root_path and path_contains_symlink(root_path, os.path.dirname(absolute_path)):
        raise ValueError(translate("site.file_outside_workspace"))
    if os.path.islink(absolute_path):
        if allow_final_symlink:
            return absolute_path
        raise ValueError(translate("site.file_outside_workspace"))
    if not path_is_inside(root_path, absolute_path):
        raise ValueError(translate("site.file_outside_workspace"))
    return absolute_path


def is_reserved_site_component(name):
    return (name or "").casefold() in SITE_RESERVED_COMPONENTS


def relative_path_has_reserved_component(relative_path, allow_internal_assets=False):
    parts = [part for part in (relative_path or "").replace("\\", "/").split("/") if part]
    folded = [part.casefold() for part in parts]
    if ".git" in folded or "__pycache__" in folded:
        return True
    if ".oneboard" not in folded:
        return False
    return not (
        allow_internal_assets
        and len(parts) >= 3
        and parts[0] == ".oneboard"
        and parts[1] == "user-assets"
        and folded.count(".oneboard") == 1
    )


def ensure_site_internal_path(workspace_path, *components, create=True):
    root_path = os.path.realpath(workspace_path)
    if not os.path.isdir(root_path):
        raise ValueError(translate("flash.site_path_missing"))
    requested_components = (".oneboard", *components)
    current_path = root_path
    for component in requested_components:
        if not component or component in {".", ".."} or "/" in component or "\\" in component:
            raise ValueError(translate("site.internal_directory_unsafe"))
        matches = [entry.name for entry in os.scandir(current_path) if entry.name.casefold() == component.casefold()]
        if matches:
            if len(matches) != 1 or matches[0] != component:
                raise ValueError(translate("site.internal_directory_unsafe"))
            candidate_path = os.path.join(current_path, matches[0])
        else:
            if not create:
                return None
            candidate_path = os.path.join(current_path, component)
            os.mkdir(candidate_path, mode=0o700)
        if os.path.islink(candidate_path) or not os.path.isdir(candidate_path):
            raise ValueError(translate("site.internal_directory_unsafe"))
        if not path_is_inside(root_path, candidate_path):
            raise ValueError(translate("site.internal_directory_unsafe"))
        current_path = candidate_path
    return current_path


def validate_site_internal_tree(workspace_path):
    root_path = os.path.realpath(workspace_path)
    internal_path = ensure_site_internal_path(root_path, create=False)
    if not internal_path:
        return
    for current_path, dirs, files in os.walk(internal_path, followlinks=False):
        if not path_is_inside(root_path, current_path):
            raise ValueError(translate("site.internal_directory_unsafe"))
        for name in (*dirs, *files):
            candidate_path = os.path.join(current_path, name)
            if os.path.islink(candidate_path):
                raise ValueError(translate("site.internal_directory_unsafe"))


def lexical_path_is_inside(root_path, candidate_path):
    root_path = os.path.normcase(os.path.abspath(root_path))
    candidate_path = os.path.normcase(os.path.abspath(candidate_path))
    try:
        return os.path.commonpath([root_path, candidate_path]) == root_path
    except ValueError:
        return False


def path_contains_symlink(root_path, candidate_path):
    root_path = os.path.abspath(root_path)
    candidate_path = os.path.abspath(candidate_path)
    if not lexical_path_is_inside(root_path, candidate_path):
        return True
    relative_path = os.path.relpath(candidate_path, root_path)
    if relative_path == ".":
        return False
    current_path = root_path
    for part in relative_path.split(os.sep):
        current_path = os.path.join(current_path, part)
        if os.path.islink(current_path):
            return True
    return False


def path_is_inside(root_path, candidate_path):
    root_path = os.path.normcase(os.path.realpath(root_path))
    candidate_path = os.path.normcase(os.path.realpath(candidate_path))
    try:
        return os.path.commonpath([root_path, candidate_path]) == root_path
    except ValueError:
        return False


@locked_site_operation
def delete_site_file(user_id, relative_path):
    absolute_path = resolve_site_file(user_id, relative_path, allow_final_symlink=True)
    if os.path.islink(absolute_path):
        os.unlink(absolute_path)
        record_update_history(user_id, "file-delete", f"Deleted symbolic link {relative_path}", "0")
        return
    if os.path.isdir(absolute_path):
        raise ValueError(translate("site.file_delete_directory"))
    os.unlink(absolute_path)
    record_update_history(user_id, "file-delete", f"Deleted {relative_path}", "0")


def ai_provider_catalog():
    providers = []
    for key, models in AI_PROVIDER_MODELS.items():
        providers.append({
            "key": key,
            "label": key.capitalize() if key != "openrouter" else "OpenRouter",
            "models": models,
            "supports_site_updates": provider_supports_site_updates(key),
        })
    return providers


def save_ai_run(user_id, provider, model, task_type, prompt, response_text="", status="completed", error_text="", usage=None):
    execute_db(
        """
        INSERT INTO ai_runs (
            user_id, provider, model, task_type, prompt, response_text, status, error_text, usage_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            provider,
            model,
            task_type,
            (prompt or "")[:8000],
            (response_text or "")[:20000],
            status,
            (error_text or "")[:4000],
            json.dumps(usage or {}),
        ),
    )


def list_ai_runs(user_id, limit=20):
    rows = query_db(
        """
        SELECT id, provider, model, task_type, prompt, response_text, status, error_text, usage_json, created_at
        FROM ai_runs
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, limit),
    )
    items = []
    for row in rows:
        item = dict(row)
        try:
            item["usage"] = json.loads(item.get("usage_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            item["usage"] = {}
        items.append(item)
    return items


def provider_models_for_user(user_id, provider):
    if provider == "muse":
        return get_muse_models(user_id)
    return AI_PROVIDER_MODELS.get(provider, [])


def get_user_ai_policy(user_id):
    row = query_db(
        "SELECT ai_default_provider, ai_default_model FROM users WHERE id = ?",
        (user_id,),
        one=True,
    )
    provider = (row["ai_default_provider"] or DEFAULT_AI_PROVIDER).strip().lower() if row else DEFAULT_AI_PROVIDER
    if provider not in AI_PROVIDER_MODELS:
        provider = DEFAULT_AI_PROVIDER
    allowed_models = provider_models_for_user(user_id, provider)
    model = (row["ai_default_model"] or "").strip() if row else ""
    if model not in allowed_models:
        model = allowed_models[0] if allowed_models else ""
    return {"provider": provider, "model": model}


def resolve_ai_provider_model(user_id, provider=None, model=None):
    policy = get_user_ai_policy(user_id)
    effective_provider = (provider or policy["provider"] or DEFAULT_AI_PROVIDER).strip().lower()
    if effective_provider not in AI_PROVIDER_MODELS:
        raise ValueError(f"Unsupported provider: {effective_provider}")
    allowed_models = provider_models_for_user(user_id, effective_provider)
    effective_model = (model or policy["model"] or "").strip()
    if effective_model and effective_model not in allowed_models:
        raise ValueError(f"Unsupported model '{effective_model}' for provider '{effective_provider}'.")
    if not effective_model:
        if not allowed_models:
            raise ValueError(f"No models available for provider '{effective_provider}'.")
        effective_model = allowed_models[0]
    return effective_provider, effective_model


def get_user_ai_provider_api_key(user_id, provider):
    provider = (provider or "").strip().lower()
    columns = {
        "muse": "muse_api_key",
        "anthropic": "anthropic_api_key",
        "openrouter": "openrouter_api_key",
        "google": "google_api_key",
    }
    column = columns.get(provider)
    if not column:
        return ""
    native_credentials = getattr(g, "native_ai_credentials", {}) if has_request_context() else {}
    if provider in native_credentials:
        return native_credentials[provider]
    row = query_db(
        f"SELECT {column} AS api_key FROM users WHERE id = ?",
        (user_id,),
        one=True,
    )
    return (row["api_key"] or "").strip() if row else ""


def get_user_ai_credentials_status(user_id):
    native_credentials = getattr(g, "native_ai_credentials", {}) if has_request_context() else {}
    if native_credentials:
        return {provider: bool(native_credentials.get(provider)) for provider in AI_PROVIDER_MODELS}
    row = query_db(
        """
        SELECT muse_api_key, anthropic_api_key, openrouter_api_key, google_api_key
        FROM users
        WHERE id = ?
        """,
        (user_id,),
        one=True,
    )
    if not row:
        return {
            "muse": False,
            "anthropic": False,
            "openrouter": False,
            "google": False,
        }
    return {
        "muse": bool((row["muse_api_key"] or "").strip()),
        "anthropic": bool((row["anthropic_api_key"] or "").strip()),
        "openrouter": bool((row["openrouter_api_key"] or "").strip()),
        "google": bool((row["google_api_key"] or "").strip()),
    }


def native_ai_credentials():
    encoded = request.headers.get("X-ONEBoard-AI-Credentials", "")
    if not encoded:
        return {}
    try:
        decoded = base64.b64decode(encoded, validate=True)
        values = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    if not isinstance(values, dict):
        return {}
    return {
        provider: value.strip()
        for provider, value in values.items()
        if provider in AI_PROVIDER_MODELS and isinstance(value, str) and value.strip()
    }


def provider_supports_site_updates(provider):
    return provider in AI_PROVIDER_MODELS


def build_ai_task_prompt(task_type, prompt, context=""):
    task_type = (task_type or "assistant").strip().lower()
    context_block = f"\n\nAdditional context:\n{context.strip()}" if context and context.strip() else ""
    if task_type == "seo_brief":
        return (
            "Create an actionable SEO brief with title ideas, page structure, internal linking ideas, and a concise CTA."
            f"\n\nUser request:\n{prompt.strip()}{context_block}"
        )
    if task_type == "content_brief":
        return (
            "Create a practical website content brief with audience, structure, messaging angles, objections, and CTA guidance."
            f"\n\nUser request:\n{prompt.strip()}{context_block}"
        )
    return f"{prompt.strip()}{context_block}"


def perform_json_request(url, payload, headers=None, timeout=90):
    request_headers = {"Content-Type": "application/json"}
    if headers:
        request_headers.update(headers)
    request_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=request_data, headers=request_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"error": {"message": body.strip() or str(error)}}
        raise ValueError(extract_provider_error_message(parsed, fallback=str(error))) from error
    except urllib.error.URLError as error:
        raise ValueError(str(error.reason) if getattr(error, "reason", None) else str(error)) from error


def extract_provider_error_message(payload, fallback="AI provider request failed."):
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            return error.get("message") or error.get("status") or fallback
        if isinstance(error, str) and error.strip():
            return error.strip()
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return fallback


def parse_anthropic_response(payload):
    parts = []
    for content in payload.get("content", []) or []:
        if isinstance(content, dict) and content.get("type") == "text":
            parts.append(content.get("text") or "")
    usage = payload.get("usage") or {}
    return "\n".join(part for part in parts if part).strip(), usage


def parse_openrouter_response(payload):
    choices = payload.get("choices") or []
    message = choices[0].get("message") if choices and isinstance(choices[0], dict) else {}
    text = message.get("content") if isinstance(message, dict) else ""
    usage = payload.get("usage") or {}
    return (text or "").strip(), usage


def parse_google_response(payload):
    texts = []
    for candidate in payload.get("candidates", []) or []:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content") or {}
        for part in content.get("parts", []) or []:
            if isinstance(part, dict) and part.get("text"):
                texts.append(part["text"])
    usage = payload.get("usageMetadata") or {}
    return "\n".join(texts).strip(), usage


def parse_muse_response(payload):
    text = payload.get("output_text") or ""
    if not text:
        for item in payload.get("output", []) or []:
            if not isinstance(item, dict):
                continue
            for content in item.get("content", []) or []:
                if not isinstance(content, dict):
                    continue
                candidate = content.get("text") or content.get("output_text") or ""
                if candidate:
                    text += candidate
    usage = payload.get("usage") or {}
    return text.strip(), usage


def parse_muse_models(payload):
    models = []
    if isinstance(payload, dict):
        candidates = payload.get("data", [])
        if not isinstance(candidates, list):
            candidates = []
        if not candidates and isinstance(payload.get("models"), list):
            candidates = payload.get("models")
        for entry in candidates:
            if isinstance(entry, dict):
                model_id = entry.get("id") or entry.get("name")
            else:
                model_id = entry
            if isinstance(model_id, str) and model_id.strip() and model_id not in models:
                models.append(model_id.strip())
    return models


def fetch_muse_models(api_key):
    response = perform_get_json_request(
        f"{MUSE_API_BASE}/models",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    return parse_muse_models(response)


def validate_muse_api_key(api_key):
    try:
        models = fetch_muse_models(api_key)
    except ValueError as error:
        detail = str(error).strip()
        raise ValueError(f"Muse API key validation failed: {detail}") from error
    if not models:
        raise ValueError("Muse API key validation failed: no models were returned.")
    return models


def get_muse_models_cache(user_id):
    try:
        row = query_db(
            "SELECT muse_models_json FROM users WHERE id = ?",
            (user_id,),
            one=True,
        )
    except sqlite3.OperationalError:
        return []
    if not row or not row["muse_models_json"]:
        return []
    try:
        cached = json.loads(row["muse_models_json"])
    except (TypeError, ValueError):
        return []
    return [model for model in cached if isinstance(model, str) and model.strip()]


def save_muse_models_cache(user_id, models):
    models = [model for model in (models or []) if isinstance(model, str) and model.strip()]
    if not models:
        return []
    try:
        execute_db(
            "UPDATE users SET muse_models_json = ? WHERE id = ?",
            (json.dumps(models), user_id),
        )
    except sqlite3.OperationalError:
        return []
    return models


def get_muse_models(user_id):
    return get_muse_models_cache(user_id) or list(MUSE_FALLBACK_MODELS)


def refresh_muse_models(user_id):
    api_key = get_user_ai_provider_api_key(user_id, "muse")
    if not api_key:
        raise ValueError("No Muse API key configured.")
    models = fetch_muse_models(api_key)
    if not models:
        raise ValueError("The Muse API did not return any models.")
    return save_muse_models_cache(user_id, models) or list(MUSE_FALLBACK_MODELS)


def muse_model_supports_images(model):
    return "image" in (model or "").lower()


def generated_image_directory():
    directory = os.path.join(UPLOAD_DIR, "generated-images")
    os.makedirs(directory, exist_ok=True)
    return directory


def run_muse_image_generation(user_id, prompt, model=None, output_format="png"):
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Enter an image description.")
    api_key = get_user_ai_provider_api_key(user_id, "muse")
    if not api_key:
        raise ValueError("No Muse API key configured.")
    resolved_model = (model or "").strip() or MUSE_IMAGE_DEFAULT_MODEL
    output_format = (output_format or "png").strip().lower() or "png"
    payload = {
        "input": [
            {
                "content": [{"text": prompt, "type": "input_text"}],
                "role": "user",
                "type": "message",
            },
        ],
        "max_output_tokens": 2048,
        "model": resolved_model,
        "store": True,
        "stream": False,
        "temperature": 0.6,
        "top_p": 0.9,
        "tools": [
            {
                "enable_image_search": True,
                "enable_shell": True,
                "enable_web_search": True,
                "output_format": output_format,
                "reasoning_strength": "high",
                "type": "image_generation",
            },
        ],
    }
    response = perform_json_request(
        f"{MUSE_API_BASE}/responses",
        payload,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=300,
    )
    if response.get("error") or response.get("status") not in (None, "completed"):
        raise ValueError(
            extract_provider_error_message(response, "Image generation failed.")
        )
    image_bytes = None
    for item in response.get("output", []) or []:
        if isinstance(item, dict) and item.get("type") == "image_generation_call" and item.get("result"):
            try:
                image_bytes = base64.b64decode(item["result"])
            except (ValueError, TypeError) as error:
                raise ValueError("The Muse API returned an invalid image.") from error
            break
    if not image_bytes:
        raise ValueError("The Muse API did not return an image.")
    directory = generated_image_directory()
    filename = f"user-{user_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}.{output_format}"
    image_path = os.path.join(directory, filename)
    with open(image_path, "wb") as image_file:
        image_file.write(image_bytes)
    save_ai_run(
        user_id,
        "muse",
        resolved_model,
        "image_generation",
        prompt,
        response_text=response.get("id") or "",
        usage=response.get("usage") or {},
    )
    return {
        "filename": filename,
        "path": image_path,
        "model": resolved_model,
        "response_id": response.get("id") or "",
        "output_format": output_format,
        "size_bytes": len(image_bytes),
    }


def list_generated_images(user_id, limit=50):
    directory = generated_image_directory()
    prefix = f"user-{user_id}-"
    items = []
    try:
        entries = os.listdir(directory)
    except OSError:
        return []
    for filename in entries:
        if not filename.startswith(prefix):
            continue
        image_path = os.path.join(directory, filename)
        try:
            stat = os.stat(image_path)
        except OSError:
            continue
        if not os.path.isfile(image_path):
            continue
        items.append(
            {
                "filename": filename,
                "url": f"/uploads/generated-images/{filename}",
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    items.sort(key=lambda item: item["filename"], reverse=True)
    return items[:limit]


def perform_get_json_request(url, headers=None, timeout=30):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"error": {"message": body.strip() or str(error)}}
        raise ValueError(extract_provider_error_message(parsed, fallback=str(error))) from error
    except urllib.error.URLError as error:
        raise ValueError(str(error.reason) if getattr(error, "reason", None) else str(error)) from error


def run_ai_provider_prompt(user_id, provider, model, prompt):
    provider, model = resolve_ai_provider_model(user_id, provider=provider, model=model)
    api_key = get_user_ai_provider_api_key(user_id, provider)
    if not api_key:
        raise ValueError(f"No API key configured for provider '{provider}'.")

    if provider == "muse":
        payload = {
            "model": model,
            "input": prompt,
            "store": False,
            "stream": False,
        }
        response = perform_json_request(
            f"{MUSE_API_BASE}/responses",
            payload,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        text, usage = parse_muse_response(response)
    elif provider == "anthropic":
        payload = {
            "model": model,
            "max_tokens": 1200,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = perform_json_request(
            "https://api.anthropic.com/v1/messages",
            payload,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        text, usage = parse_anthropic_response(response)
    elif provider == "openrouter":
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = perform_json_request(
            "https://openrouter.ai/api/v1/chat/completions",
            payload,
            headers={
                "Authorization": f"Bearer {api_key}",
                "HTTP-Referer": "https://oneboard.local",
                "X-Title": "ONEBoard",
            },
        )
        text, usage = parse_openrouter_response(response)
    elif provider == "google":
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(model, safe='')}:generateContent?key={urllib.parse.quote(api_key, safe='')}"
        payload = {
            "contents": [
                {
                    "parts": [{"text": prompt}],
                }
            ]
        }
        response = perform_json_request(url, payload)
        text, usage = parse_google_response(response)
    else:
        raise ValueError(f"Unsupported provider: {provider}")

    if not text:
        raise ValueError("The AI provider returned an empty response.")
    return text, usage, model


def run_ai_text_task(user_id, task_type, prompt, provider=None, model=None, context=""):
    provider, model = resolve_ai_provider_model(user_id, provider=provider, model=model)
    final_prompt = build_ai_task_prompt(task_type, prompt, context=context)
    text, usage, resolved_model = run_ai_provider_prompt(user_id, provider, model, final_prompt)

    save_ai_run(user_id, provider, resolved_model, task_type, final_prompt, response_text=text, usage=usage)
    return {
        "provider": provider,
        "model": resolved_model,
        "task_type": task_type,
        "prompt": final_prompt,
        "response_text": text,
        "usage": usage,
    }


def decode_process_output(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def sandboxed_tool_command(workspace_path, command):
    tool_args = parse_allowed_tool_command(command, workspace_path)
    if IS_WINDOWS:
        return tool_args

    sandbox_exec = shutil.which("sandbox-exec")
    if not sandbox_exec:
        raise ValueError(translate("flash.sandbox_unavailable"))

    workspace_path = os.path.realpath(workspace_path)
    profile = build_workspace_sandbox_profile(workspace_path)
    return [sandbox_exec, "-p", profile, *tool_args]


def parse_allowed_tool_command(command, workspace_path):
    try:
        parts = shlex.split(command, posix=not IS_WINDOWS)
    except ValueError as error:
        raise ValueError(str(error)) from error

    if not parts:
        raise ValueError(translate("flash.command_required"))

    tool = os.path.basename(parts[0])
    args = parts[1:]
    if tool in platform_editor_commands():
        return build_platform_editor_command(tool, args)
    raise ValueError(translate("flash.command_not_allowed"))


def platform_editor_commands():
    return {"notepad"} if IS_WINDOWS else {"nano"}


def build_platform_editor_command(tool, args):
    validate_relative_arguments(args)
    editor_path = shutil.which(tool)
    if not editor_path:
        raise ValueError(f"{tool} is not installed.")
    return [editor_path, *args]


def site_command_timeout():
    return 30


def validate_relative_arguments(args):
    for arg in args:
        if not arg or arg.startswith("-"):
            continue
        if is_absolute_like_path(arg) or arg.startswith("~") or contains_parent_reference(arg):
            raise ValueError(translate("flash.command_outside_workspace"))


def is_absolute_like_path(value):
    return (
        os.path.isabs(value)
        or value.startswith(("/", "\\\\"))
        or bool(re.match(r"^[A-Za-z]:[\\/]", value))
    )


def contains_parent_reference(value):
    parts = value.replace("\\", "/").split("/")
    return ".." in parts


def build_site_command_env(workspace_path):
    env_root = ensure_site_internal_path(workspace_path)
    home = ensure_site_internal_path(workspace_path, "home")
    tmp = ensure_site_internal_path(workspace_path, "tmp")
    cache = ensure_site_internal_path(workspace_path, "cache")
    config = ensure_site_internal_path(workspace_path, "config")
    data = ensure_site_internal_path(workspace_path, "data")
    state = ensure_site_internal_path(workspace_path, "state")
    validate_site_internal_tree(workspace_path)

    env = os.environ.copy()
    env.update(
        {
            "HOME": home,
            "TMPDIR": tmp,
            "XDG_CACHE_HOME": cache,
            "XDG_CONFIG_HOME": config,
            "XDG_DATA_HOME": data,
            "XDG_STATE_HOME": state,
            "PWD": workspace_path,
            "ONEBOARD_WORKSPACE": workspace_path,
            "NO_UPDATE_NOTIFIER": "1",
        }
    )
    return env


def build_workspace_sandbox_profile(workspace_path):
    workspace_path = sandbox_literal(workspace_path)
    return f"""
(version 1)
(deny default)
(allow process*)
(allow signal)
(allow network*)
(allow sysctl-read)
(allow mach-lookup)
  (allow file-read*)
  (allow file-write* (subpath "{workspace_path}"))
""".strip()


def validate_workspace_command(command):
    blocked_patterns = [
        r"(^|[\s;&|])/",
        r"(^|[\s;&|])~",
        r"(^|[\s;&|/])\.\.($|[\s;&|/])",
        r"\$\(",
        r"`",
        r"\$\{",
    ]
    if any(re.search(pattern, command) for pattern in blocked_patterns):
        raise ValueError(translate("flash.command_outside_workspace"))


def sandbox_literal(path):
    return path.replace("\\", "\\\\").replace('"', '\\"')


@locked_site_operation
def create_site_backup(user_id):
    directory = require_site_directory(user_id)
    root_path = os.path.realpath(directory["path"])
    user_backup_dir = os.path.join(BACKUP_DIR, str(user_id))
    os.makedirs(user_backup_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    directory_name = os.path.basename(root_path.rstrip(os.sep)) or "website"
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "-", directory_name).strip("-") or "website"
    filename = f"{safe_name}-{timestamp}-{secrets.token_hex(3)}.zip"
    backup_path = os.path.join(user_backup_dir, filename)
    backup_root = os.path.realpath(BACKUP_DIR)

    file_count = 0
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for root, dirs, files in os.walk(root_path, followlinks=False):
            filtered_dirs = []
            for item in dirs:
                candidate = os.path.join(root, item)
                if is_reserved_site_component(item) or os.path.islink(candidate):
                    continue
                candidate_real = os.path.realpath(candidate)
                if path_is_inside(backup_root, candidate_real):
                    continue
                if path_is_inside(root_path, candidate_real):
                    filtered_dirs.append(item)
            dirs[:] = filtered_dirs
            for file_name in files:
                source_path = os.path.join(root, file_name)
                if os.path.islink(source_path) or not os.path.isfile(source_path):
                    continue
                if not path_is_inside(root_path, source_path):
                    continue
                if os.path.realpath(source_path) == os.path.realpath(backup_path):
                    continue
                arcname = os.path.relpath(source_path, root_path).replace("\\", "/")
                try:
                    archive.write(source_path, arcname)
                except FileNotFoundError:
                    continue
                else:
                    file_count += 1

    size_bytes = os.path.getsize(backup_path)
    execute_db(
        """
        INSERT INTO website_backups (
            user_id, directory_path, filename, backup_path, file_count, size_bytes
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, root_path, filename, backup_path, file_count, size_bytes),
    )


def list_site_backups(user_id):
    directory = get_site_directory(user_id)
    if not directory:
        return []
    current_directory = os.path.realpath(directory["path"])
    rows = query_db(
        """
        SELECT id, directory_path, filename, backup_path, file_count, size_bytes, created_at
        FROM website_backups
        WHERE user_id = ?
        ORDER BY created_at DESC, id DESC
        """,
        (user_id,),
    )
    return [
        format_site_backup(row)
        for row in rows
        if os.path.realpath(row["directory_path"]) == current_directory
    ]


def format_site_backup(row):
    backup = dict(row)
    backup["size_label"] = format_bytes(backup["size_bytes"])
    backup["exists"] = os.path.exists(backup["backup_path"])
    return backup


@locked_site_operation
def restore_site_backup(user_id, backup_id):
    directory = require_site_directory(user_id)
    backup = get_site_backup(user_id, backup_id)
    if not backup:
        raise ValueError(translate("flash.backup_missing"))
    if not os.path.exists(backup["backup_path"]):
        raise ValueError(translate("flash.backup_missing"))
    if os.path.realpath(backup["directory_path"]) != os.path.realpath(directory["path"]):
        raise ValueError(translate("site.backup_directory_mismatch"))

    with tempfile.TemporaryDirectory(prefix="oneboard-restore-") as temp_dir:
        with zipfile.ZipFile(backup["backup_path"], "r") as archive:
            safe_extract_zip(archive, temp_dir)

        clear_directory(directory["path"], preserved_names={".git", ".oneboard"})
        copy_directory_contents(temp_dir, directory["path"])


def get_site_backup(user_id, backup_id):
    try:
        backup_id = int(backup_id)
    except (TypeError, ValueError):
        return None

    return query_db(
        """
        SELECT id, directory_path, filename, backup_path, file_count, size_bytes, created_at
        FROM website_backups
        WHERE user_id = ? AND id = ?
        """,
        (user_id, backup_id),
        one=True,
    )


def safe_extract_zip(archive, destination):
    destination = os.path.abspath(destination)
    seen_paths = set()
    for member in archive.infolist():
        member_path = member.filename.replace("\\", "/")
        parts = [part for part in member_path.split("/") if part and part != "."]
        if contains_parent_reference(member_path) or any(is_reserved_site_component(part) for part in parts):
            raise zipfile.BadZipFile("Backup contains a reserved or unsafe path.")
        normalized_member = "/".join(parts)
        if normalized_member in seen_paths:
            raise zipfile.BadZipFile("Backup contains duplicate paths.")
        seen_paths.add(normalized_member)
        target_path = os.path.abspath(os.path.join(destination, normalized_member))
        if not lexical_path_is_inside(destination, target_path):
            raise zipfile.BadZipFile("Backup contains an unsafe path.")
        unix_mode = (member.external_attr >> 16) & 0o170000
        if unix_mode == 0o120000:
            raise zipfile.BadZipFile("Backup contains a symbolic link.")
    invalid_member = archive.testzip()
    if invalid_member:
        raise zipfile.BadZipFile(f"Backup member is damaged: {invalid_member}")
    archive.extractall(destination)


def clear_directory(path, preserved_names=None):
    preserved_names = {name.casefold() for name in (preserved_names or ())}
    for entry in os.scandir(path):
        if entry.name.casefold() in preserved_names:
            continue
        if entry.is_dir(follow_symlinks=False):
            shutil.rmtree(entry.path)
        else:
            os.unlink(entry.path)


def copy_directory_contents(source, destination):
    for entry in os.scandir(source):
        target_path = os.path.join(destination, entry.name)
        if entry.is_dir(follow_symlinks=False):
            shutil.copytree(entry.path, target_path, symlinks=False)
        else:
            shutil.copy2(entry.path, target_path)


def format_bytes(size):
    size = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024


def normalize_scan_domain(value):
    value = value.strip().lower()
    if not value:
        raise ValueError(translate("scan.error.domain_required"))

    parsed = urllib.parse.urlparse(value if "://" in value else f"https://{value}")
    domain = parsed.hostname or value
    domain = domain.strip(".")

    if len(domain) > 253:
        raise ValueError(translate("scan.error.domain_too_long"))

    try:
        ipaddress.ip_address(domain)
        raise ValueError(translate("scan.error.no_ip"))
    except ValueError as error:
        if str(error) == translate("scan.error.no_ip"):
            raise

    domain_pattern = re.compile(
        r"^(?=.{1,253}$)(?!-)[a-z0-9-]{1,63}(?<!-)(\.(?!-)[a-z0-9-]{1,63}(?<!-))+$"
    )
    if not domain_pattern.match(domain):
        raise ValueError(translate("scan.error.invalid_domain"))

    return domain


def analyze_domain_security(domain):
    started_at = time.strftime("%Y-%m-%d %H:%M:%S")
    dns = inspect_dns(domain)
    http = inspect_http(domain)
    tls = inspect_tls(domain)
    tech = detect_technology(http)
    recommendations = build_security_recommendations(tls, http, dns, tech)
    score = compute_security_score(tls, http, dns)

    return {
        "domain": domain,
        "started_at": started_at,
        "score": score,
        "grade": security_grade(score),
        "verdict": security_verdict(score),
        "dns": dns,
        "http": http,
        "tls": tls,
        "tech": tech,
        "recommendations": recommendations,
        "tools": external_security_tools(domain),
    }


def save_security_scan_result(user_id, scan):
    execute_db(
        """
        INSERT INTO security_scan_history (
            user_id, domain, score, grade, verdict, https_available,
            hsts_active, missing_headers_count, details_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            scan["domain"],
            int(scan["score"]),
            scan["grade"],
            scan["verdict"],
            1 if scan["http"].get("https_available") else 0,
            1 if scan["tls"].get("hsts") else 0,
            len(scan["http"].get("missing_headers", [])),
            json.dumps(scan_history_details(scan)),
        ),
    )


def scan_history_details(scan):
    return {
        "security_headers": scan["http"].get("security_headers", []),
        "missing_headers": scan["http"].get("missing_headers", []),
        "tls_status": scan["tls"].get("status"),
        "dns_status": scan["dns"].get("status"),
        "tech_hints": scan["tech"].get("hints", []),
    }


def build_security_scan_history(user_id):
    rows = query_db(
        """
        SELECT id, domain, score, grade, verdict, https_available, hsts_active,
               missing_headers_count, created_at
        FROM security_scan_history
        WHERE user_id = ?
        ORDER BY created_at ASC, id ASC
        LIMIT 120
        """,
        (user_id,),
    )

    previous_by_domain = {}
    history = []
    for row in rows:
        previous_score = previous_by_domain.get(row["domain"])
        change = None if previous_score is None else int(row["score"]) - previous_score
        item = dict(row)
        item["change"] = change
        item["change_label"] = scan_change_label(change)
        item["bar_height"] = max(8, int(row["score"]))
        previous_by_domain[row["domain"]] = int(row["score"])
        history.append(item)

    latest = list(reversed(history[-12:]))
    chart = history[-10:]
    return {
        "latest": latest,
        "chart": chart,
        "total": len(history),
    }


def scan_change_label(change):
    if change is None:
        return "-"
    if change > 0:
        return f"+{change}"
    return str(change)


def inspect_dns(domain):
    addresses = []
    errors = []
    try:
        results = socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM)
        addresses = sorted({row[4][0] for row in results})
    except socket.gaierror as error:
        errors.append(translate("scan.error.dns_failed", error=error))

    return {
        "addresses": addresses,
        "reachable": bool(addresses),
        "errors": errors,
        "status": "ok" if addresses else "error",
    }


def inspect_http(domain):
    result = {
        "url": f"https://{domain}",
        "final_url": None,
        "status": None,
        "headers": {},
        "security_headers": [],
        "missing_headers": [],
        "server": None,
        "powered_by": None,
        "https_available": False,
        "redirects_to_https": False,
        "error": None,
    }

    https_response = fetch_headers(f"https://{domain}")
    if https_response["ok"]:
        result.update(
            {
                "final_url": https_response["final_url"],
                "status": https_response["status"],
                "headers": https_response["headers"],
                "https_available": True,
            }
        )
    else:
        result["error"] = https_response["error"]

    http_response = fetch_headers(f"http://{domain}")
    if http_response["ok"]:
        result["redirects_to_https"] = http_response["final_url"].startswith("https://")

    result["security_headers"] = present_security_headers(result["headers"])
    result["missing_headers"] = missing_security_headers(result["headers"])
    result["server"] = result["headers"].get("server")
    result["powered_by"] = result["headers"].get("x-powered-by")
    return result


def fetch_headers(url):
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(
                url,
                method=method,
                headers={"User-Agent": "ONEBoard Security Analyzer/1.0"},
            )
            with urllib.request.urlopen(req, timeout=12) as response:
                return {
                    "ok": True,
                    "status": response.status,
                    "final_url": response.geturl(),
                    "headers": {key.lower(): value for key, value in response.headers.items()},
                    "error": None,
                }
        except urllib.error.HTTPError as error:
            return {
                "ok": True,
                "status": error.code,
                "final_url": error.geturl(),
                "headers": {key.lower(): value for key, value in error.headers.items()},
                "error": None,
            }
        except (urllib.error.URLError, TimeoutError, ssl.SSLError):
            continue

    return {"ok": False, "status": None, "final_url": None, "headers": {}, "error": "Sin respuesta HTTP."}


def inspect_tls(domain):
    result = {
        "valid": False,
        "issuer": "No disponible",
        "subject": domain,
        "expires": None,
        "days_remaining": None,
        "protocol": "No disponible",
        "cipher": "No disponible",
        "hsts": False,
        "error": None,
        "status": "error",
    }

    try:
        context = ssl.create_default_context()
        with socket.create_connection((domain, 443), timeout=12) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as secure_sock:
                cert = secure_sock.getpeercert()
                result["valid"] = True
                result["protocol"] = secure_sock.version() or "No disponible"
                cipher = secure_sock.cipher()
                result["cipher"] = cipher[0] if cipher else "No disponible"
    except (OSError, ssl.SSLError) as error:
        result["error"] = str(error)
        return result

    not_after = cert.get("notAfter")
    if not_after:
        expires_struct = ssl.cert_time_to_seconds(not_after)
        days_remaining = int((expires_struct - time.time()) / 86400)
        result["expires"] = time.strftime("%Y-%m-%d", time.gmtime(expires_struct))
        result["days_remaining"] = days_remaining

    issuer = dict(value for part in cert.get("issuer", []) for value in part)
    subject = dict(value for part in cert.get("subject", []) for value in part)
    result["issuer"] = issuer.get("organizationName") or issuer.get("commonName") or "No disponible"
    result["subject"] = subject.get("commonName") or domain
    result["hsts"] = "strict-transport-security" in fetch_headers(f"https://{domain}")["headers"]
    result["status"] = "ok" if result["valid"] and (result["days_remaining"] is None or result["days_remaining"] > 14) else "warn"
    return result


def present_security_headers(headers):
    return [header for header in required_security_headers() if header.lower() in headers]


def missing_security_headers(headers):
    return [header for header in required_security_headers() if header.lower() not in headers]


def required_security_headers():
    return [
        "Content-Security-Policy",
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
    ]


def detect_technology(http):
    headers = http["headers"]
    server = headers.get("server") or "No revelado"
    powered_by = headers.get("x-powered-by")
    cookies = " ".join(value.lower() for key, value in headers.items() if key == "set-cookie")
    hints = []

    if "wordpress" in cookies:
        hints.append("WordPress")
    if powered_by:
        hints.append(f"X-Powered-By: {powered_by}")
    if "cloudflare" in server.lower() or "cf-ray" in headers:
        hints.append("Cloudflare")
    if "x-shopify-stage" in headers or "shopify" in server.lower():
        hints.append("Shopify")
    if "x-vercel-id" in headers or "x-vercel-cache" in headers:
        hints.append("Vercel")

    return {
        "server": server,
        "powered_by": powered_by,
        "hints": hints,
        "server_disclosed": bool(http["server"]),
        "powered_by_disclosed": bool(powered_by),
    }


def compute_security_score(tls, http, dns):
    score = 35
    if dns["reachable"]:
        score += 10
    if http["https_available"]:
        score += 15
    if http["redirects_to_https"]:
        score += 8
    if tls["valid"]:
        score += 15
    if tls["protocol"] == "TLSv1.3":
        score += 5
    if tls["hsts"]:
        score += 8
    score += min(len(http["security_headers"]) * 4, 24)
    if http["powered_by"]:
        score -= 5
    if tls["days_remaining"] is not None and tls["days_remaining"] < 14:
        score -= 10
    return max(0, min(100, score))


def security_grade(score):
    if score >= 90:
        return "A+"
    if score >= 80:
        return "A"
    if score >= 70:
        return "B"
    if score >= 60:
        return "C"
    if score >= 50:
        return "D"
    return "F"


def security_verdict(score):
    if score >= 85:
        return translate("scan.verdict.strong")
    if score >= 70:
        return translate("scan.verdict.good")
    if score >= 55:
        return translate("scan.verdict.attention")
    return translate("scan.verdict.risk")


def build_security_recommendations(tls, http, dns, tech):
    recommendations = []
    if not dns["reachable"]:
        recommendations.append(recommendation("critical", "Fix DNS resolution", "The domain did not resolve from ONEBoard's server. Review nameservers and A/AAAA records.", "Corregir resolución DNS", "El dominio no resolvió desde el servidor de ONEBoard. Revisa nameservers y registros A/AAAA."))
    if not http["https_available"]:
        recommendations.append(recommendation("critical", "Enable HTTPS", "A valid HTTPS response could not be reached. Install a TLS certificate and force secure traffic.", "Activar HTTPS", "No se pudo obtener respuesta HTTPS válida. Instala un certificado TLS y fuerza tráfico seguro."))
    if http["https_available"] and not http["redirects_to_https"]:
        recommendations.append(recommendation("high", "Force HTTPS redirects", "HTTP traffic should automatically redirect to the secure version of the site.", "Forzar redirección a HTTPS", "El tráfico HTTP debe redirigir automáticamente a la versión segura del sitio."))
    if tls["valid"] and tls["days_remaining"] is not None and tls["days_remaining"] < 30:
        recommendations.append(recommendation("high", "Renew TLS certificate", f"The certificate expires in {tls['days_remaining']} days.", "Renovar certificado TLS", f"El certificado vence en {tls['days_remaining']} días."))
    if "Strict-Transport-Security" in http["missing_headers"]:
        recommendations.append(recommendation("high", "Add HSTS", "Strict-Transport-Security reduces exposure to downgrade and accidental HTTP access.", "Agregar HSTS", "Strict-Transport-Security reduce exposición a downgrade y acceso accidental por HTTP."))
    if "Content-Security-Policy" in http["missing_headers"]:
        recommendations.append(recommendation("medium", "Define a Content Security Policy", "CSP helps reduce the impact of XSS and unauthorized resource loading.", "Definir Content Security Policy", "CSP ayuda a reducir impacto de XSS y carga de recursos no autorizados."))
    if "X-Content-Type-Options" in http["missing_headers"]:
        recommendations.append(recommendation("medium", "Add X-Content-Type-Options", "Use nosniff to prevent browsers from misinterpreting file types.", "Agregar X-Content-Type-Options", "Usa nosniff para evitar interpretación incorrecta de archivos por el navegador."))
    if tech["powered_by_disclosed"]:
        recommendations.append(recommendation("low", "Hide X-Powered-By", "Avoid unnecessarily revealing backend technology in public headers.", "Ocultar X-Powered-By", "Evita revelar tecnología backend innecesariamente en cabeceras públicas."))
    if not recommendations:
        recommendations.append(recommendation("low", "Keep periodic monitoring", "Basic controls look good in this passive analysis. Repeat the scan after DNS, hosting, or CDN changes.", "Mantener monitoreo periódico", "Los controles básicos se ven bien en este análisis pasivo. Repite el scan tras cambios de DNS, hosting o CDN."))

    return recommendations[:6]


def recommendation(priority, title_en, detail_en, title_es, detail_es):
    spanish = current_language() == "es"
    return {
        "priority": priority,
        "priority_label": translate(f"priority.{priority}"),
        "title": title_es if spanish else title_en,
        "detail": detail_es if spanish else detail_en,
    }


def external_security_tools(domain):
    encoded = urllib.parse.quote(domain)
    return [
        {"name": "Security Headers", "url": f"https://securityheaders.com/?q={encoded}&followRedirects=on", "description": "Public HTTP security header grade." if current_language() == "en" else "Calificación pública de cabeceras HTTP."},
        {"name": "SSL Labs", "url": f"https://www.ssllabs.com/ssltest/analyze.html?d={encoded}", "description": "Deep certificate, protocol, and TLS cipher test." if current_language() == "en" else "Prueba profunda de certificado, protocolos y cifrados TLS."},
        {"name": "VirusTotal", "url": f"https://www.virustotal.com/gui/domain/{encoded}", "description": "Domain reputation across intelligence sources." if current_language() == "en" else "Reputación del dominio en fuentes de inteligencia."},
        {"name": "MX Toolbox", "url": f"https://mxtoolbox.com/SuperTool.aspx?action=dns%3a{encoded}", "description": "DNS, email, and blacklist lookup." if current_language() == "en" else "Consulta DNS, correo y listas negras."},
        {"name": "Mozilla Observatory", "url": f"https://observatory.mozilla.org/analyze/{encoded}", "description": "Additional web security analysis." if current_language() == "en" else "Análisis adicional de seguridad web."},
        {"name": "DNS Checker", "url": f"https://dnschecker.org/server-headers-check.php?query={encoded}", "description": "Headers and propagation from multiple locations." if current_language() == "en" else "Cabeceras y propagación desde varias ubicaciones."},
    ]


def validate_registration(name, email, password, confirm_password):
    if not name:
        return translate("flash.name_required")
    if not email:
        return translate("flash.email_password_required")
    if "@" not in email:
        return "Enter a valid email." if current_language() == "en" else "Ingresa un correo válido."
    if len(password) < 8:
        return "The password must be at least 8 characters." if current_language() == "en" else "La contraseña debe tener al menos 8 caracteres."
    if password != confirm_password:
        return "The passwords do not match." if current_language() == "en" else "Las contraseñas no coinciden."
    return None


def create_password_reset_token(user_id):
    token = secrets.token_urlsafe(48)
    now = int(time.time())
    execute_db(
        """
        INSERT INTO password_reset_tokens (user_id, token, expires_at, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, token, now + 3600, now),
    )
    return token


def get_valid_password_reset_token(token):
    return query_db(
        """
        SELECT id, user_id, token
        FROM password_reset_tokens
        WHERE token = ?
          AND used_at IS NULL
          AND expires_at > ?
        """,
        (token, int(time.time())),
        one=True,
    )


def mark_password_reset_token_used(token_id):
    execute_db(
        "UPDATE password_reset_tokens SET used_at = ? WHERE id = ?",
        (int(time.time()), token_id),
    )


def create_email_verification_token(user_id):
    token = secrets.token_urlsafe(48)
    now = int(time.time())
    execute_db(
        "DELETE FROM email_verification_tokens WHERE user_id = ? AND used_at IS NULL",
        (user_id,),
    )
    execute_db(
        """
        INSERT INTO email_verification_tokens (user_id, token_hash, expires_at, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (user_id, hashlib.sha256(token.encode("utf-8")).hexdigest(), now + 86400, now),
    )
    return token


def consume_email_verification_token(token):
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = query_db(
        """
        SELECT id, user_id
        FROM email_verification_tokens
        WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?
        """,
        (token_hash, int(time.time())),
        one=True,
    )
    if not row:
        return None
    execute_db("UPDATE email_verification_tokens SET used_at = ? WHERE id = ?", (int(time.time()), row["id"]))
    return row["user_id"]


def smtp_settings():
    try:
        port = int(os.environ.get("SMTP_PORT", "587"))
    except ValueError as error:
        raise ValueError("SMTP_PORT must be a valid port number.") from error
    if not 1 <= port <= 65535:
        raise ValueError("SMTP_PORT must be between 1 and 65535.")
    return {
        "host": os.environ.get("SMTP_HOST", "").strip(),
        "port": port,
        "username": os.environ.get("SMTP_USERNAME", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "from_address": os.environ.get("SMTP_FROM", "").strip(),
        "use_tls": os.environ.get("SMTP_USE_TLS", "1").strip().lower() not in {"0", "false", "no"},
    }


def send_email_verification(user_id, recipient):
    settings = smtp_settings()
    if not settings["host"] or not settings["from_address"]:
        raise ValueError("Email verification is not configured. Set SMTP_HOST and SMTP_FROM.")
    if bool(settings["username"]) != bool(settings["password"]):
        raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together.")

    token = create_email_verification_token(user_id)
    verification_url = url_for("verify_email", token=token, _external=True)
    message = email.message.EmailMessage()
    message["Subject"] = "Verify your ONEBoard email address"
    message["From"] = settings["from_address"]
    message["To"] = recipient
    message.set_content(
        "Welcome to ONEBoard.\n\n"
        f"Verify your email address to activate your account:\n{verification_url}\n\n"
        "This link expires in 24 hours. If you did not create this account, ignore this email."
    )
    try:
        with smtplib.SMTP(settings["host"], settings["port"], timeout=20) as server:
            if settings["use_tls"]:
                server.starttls()
            if settings["username"]:
                server.login(settings["username"], settings["password"])
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise ValueError("Unable to send the verification email. Check the SMTP configuration.") from error


def save_uploaded_image(user_id, upload, target_dir, prefix):
    filename = upload.filename or ""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in {"png", "jpg", "jpeg", "gif", "webp"}:
        raise ValueError(translate("flash.avatar_invalid"))
    if not uploaded_image_matches_extension(upload, extension):
        raise ValueError(translate("flash.avatar_invalid"))

    os.makedirs(target_dir, exist_ok=True)
    image_filename = f"{prefix}-{user_id}-{secrets.token_hex(8)}.{extension}"
    image_path = os.path.join(target_dir, image_filename)
    upload.save(image_path)
    return image_filename


def uploaded_image_matches_extension(upload, extension):
    stream = upload.stream
    try:
        stream.seek(0, os.SEEK_END)
        size_bytes = stream.tell()
        stream.seek(0)
        header = stream.read(16)
        stream.seek(0)
    except (AttributeError, OSError):
        return False
    if size_bytes <= 0 or size_bytes > MAX_IMAGE_UPLOAD_BYTES:
        return False
    signatures = {
        "png": header.startswith(b"\x89PNG\r\n\x1a\n"),
        "jpg": header.startswith(b"\xff\xd8\xff"),
        "jpeg": header.startswith(b"\xff\xd8\xff"),
        "gif": header.startswith((b"GIF87a", b"GIF89a")),
        "webp": header.startswith(b"RIFF") and header[8:12] == b"WEBP",
    }
    return signatures.get(extension, False)


def save_codex_suggested_image(user_id, upload):
    if not upload or not upload.filename:
        return None

    directory = require_site_directory(user_id)
    target_dir = ensure_site_internal_path(directory["path"], "user-assets")
    validate_site_internal_tree(directory["path"])
    image_filename = save_uploaded_image(user_id, upload, target_dir, "suggested")
    return os.path.relpath(os.path.join(target_dir, image_filename), directory["path"]).replace("\\", "/")


def hash_password(password):
    return generate_password_hash(password, method=PASSWORD_HASH_METHOD)


def verify_password(password_hash, password):
    try:
        return check_password_hash(password_hash, password)
    except AttributeError:
        return False


def login_required(view):
    @wraps(view)
    def wrapped_view(**kwargs):
        if g.user is None:
            if request.path.startswith("/api/"):
                return api_error(translate("flash.login_required"), 401)
            flash(translate("flash.login_required"), "warning")
            return redirect(url_for("login"))
        return view(**kwargs)

    return wrapped_view


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
