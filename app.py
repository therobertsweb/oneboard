import base64
import email.message
import html
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
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from html.parser import HTMLParser

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
    Response,
    session,
    send_file,
    send_from_directory,
    url_for,
)
from werkzeug.middleware.proxy_fix import ProxyFix
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
    "muse": ["muse-wonder-1.0", "muse-image-1.0"],
    "anthropic": ["claude-sonnet-4", "claude-3-5-haiku"],
    "openrouter": ["anthropic/claude-sonnet-4", "google/gemini-2.5-pro"],
    "google": ["gemini-2.5-pro", "gemini-2.5-flash"],
}
MUSE_API_BASE = "https://api.meta.ai/v1"
MUSE_FALLBACK_MODELS = ["muse-wonder-1.0", "muse-image-1.0"]
MUSE_IMAGE_DEFAULT_MODEL = "muse-image-1.0"
MUSE_TEXT_DEFAULT_MODEL = "muse-wonder-1.0"

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
        "nav.site_manager": "Studio",
        "nav.security_scan": "Security Scan",
        "nav.social": "Social",
        "nav.help": "Help",
        "nav.settings": "Settings",
        "nav.teams": "Teams",
        "nav.preview": "Preview",
        "nav.site": "Site",
        "nav.health": "Pending",
        "nav.requests": "Requests",
        "nav.logout": "Sign out",
        "teams.title": "Teams",
        "teams.kicker": "Collaboration",
        "teams.subtitle": "Work on the same projects with your team and clients.",
        "teams.new_team": "New team",
        "teams.create": "Create team",
        "teams.name": "Team name",
        "teams.name_placeholder": "e.g. Web Agency",
        "teams.description": "Description (optional)",
        "teams.my_teams": "My teams",
        "teams.no_teams": "You are not part of any team yet. Create one or accept an invitation.",
        "teams.members": "Members",
        "teams.projects": "Team projects",
        "teams.no_projects": "No shared projects yet. Share one of your personal projects below.",
        "teams.invites": "Pending invitations",
        "teams.no_invites": "No pending invitations.",
        "teams.invite_member": "Invite member",
        "teams.invite_email": "Email address",
        "teams.invite_role": "Role",
        "teams.send_invite": "Send invitation",
        "teams.copy_link": "Copy link",
        "teams.link_ready": "Share this link with your teammate:",
        "teams.revoke": "Revoke",
        "teams.remove": "Remove",
        "teams.leave": "Leave team",
        "teams.delete_team": "Delete team",
        "teams.confirm_delete": "Delete this team? Shared projects become unshared folders again. Files on disk are kept.",
        "teams.confirm_remove_member": "Remove this member from the team?",
        "teams.confirm_leave": "Leave this team? You will lose access to its shared projects.",
        "teams.transfer": "Transfer ownership",
        "teams.role": "Role",
        "teams.permissions": "Permissions",
        "teams.save_changes": "Save changes",
        "teams.add_project": "Share a project with the team",
        "teams.add_project_note": "Pick one of your personal projects, or paste a folder path, to share it with this team.",
        "teams.project_path": "Folder path",
        "teams.open_project": "Open",
        "teams.remove_project": "Unshare",
        "teams.confirm_remove_project": "Stop sharing this project with the team? Files on disk are kept.",
        "teams.open_in_studio": "Open in Studio",
        "teams.pending_invite": "You have been invited to join",
        "teams.accept_invite": "Accept invitation",
        "teams.accept_own_invite": "Accept",
        "teams.login_to_accept": "Sign in or create an account to accept this invitation.",
        "teams.role_owner": "Owner",
        "teams.role_admin": "Admin",
        "teams.role_editor": "Editor",
        "teams.role_viewer": "Viewer",
        "teams.role_client": "Client",
        "teams.role_custom": "Custom",
        "teams.perm_view": "View",
        "teams.perm_edit": "Edit",
        "teams.perm_publish": "Publish",
        "teams.perm_invite": "Invite",
        "teams.perm_manage": "Manage",
        "teams.perm_billing": "Billing",
        "teams.perm_view_note": "Open and read team projects.",
        "teams.perm_edit_note": "Change files, run the assistant and the terminal.",
        "teams.perm_publish_note": "Approve updates and deploy to remote servers.",
        "teams.perm_invite_note": "Invite new members to the team.",
        "teams.perm_manage_note": "Change roles, remove members and manage shared projects.",
        "teams.perm_billing_note": "Reserved for billing management.",
        "teams.you": "you",
        "teams.personal": "Personal",
        "teams.shared": "Shared",
        "teams.team_project": "Team project",
        "teams.read_only": "Read-only: your role in this team does not allow this action.",
        "teams.expires": "Expires",
        "teams.created": "Created",
        "teams.back_to_teams": "Back to teams",
        "flash.team_created": "Team created.",
        "flash.team_updated": "Team updated.",
        "flash.team_deleted": "Team deleted.",
        "flash.team_not_found": "Team not found.",
        "flash.team_name_required": "Give the team a name.",
        "flash.invite_sent": "Invitation sent.",
        "flash.invite_link_ready": "Email is not configured, so copy the invitation link manually.",
        "flash.invite_revoked": "Invitation revoked.",
        "flash.invite_invalid": "This invitation is invalid or expired.",
        "flash.invite_accepted": "You joined the team.",
        "flash.invite_email_mismatch": "This invitation was sent to another email address.",
        "flash.already_member": "That user is already a member of this team.",
        "flash.member_updated": "Member updated.",
        "flash.member_removed": "Member removed.",
        "flash.team_member_not_found": "Team member not found.",
        "flash.left_team": "You left the team.",
        "flash.owner_transfer_required": "Transfer ownership to another member first.",
        "flash.cannot_modify_owner": "The team owner cannot be modified. Transfer ownership first.",
        "flash.team_permission_denied": "Your team role does not allow this action.",
        "flash.team_project_added": "Project shared with the team.",
        "flash.team_project_removed": "Project unshared from the team.",
        "flash.team_project_elsewhere": "This folder is already shared with another team.",
        "flash.not_team_member": "You are not a member of this team.",
        "flash.ownership_transferred": "Ownership transferred.",
        "flash.team_path_forbidden": "This folder belongs to a team you are not part of.",
        "site.site_settings": "Site settings",
        "site.display_name": "Site name",
        "site.client_name": "Client",
        "site.brand": "Brand memory",
        "site.brand_note": "Saved once per site. The AI uses it for pages, images, and posts.",
        "site.brand_business_name": "Business name",
        "site.brand_tagline": "Tagline",
        "site.brand_services": "Services and products",
        "site.brand_audience": "Audience",
        "site.brand_tone": "Tone of voice",
        "site.brand_colors": "Brand colors",
        "site.brand_color_primary": "Primary",
        "site.brand_color_secondary": "Secondary",
        "site.brand_color_accent": "Accent",
        "site.brand_fonts": "Typography",
        "site.brand_font_headings": "Headings",
        "site.brand_font_body": "Body",
        "site.brand_phone": "Phone",
        "site.brand_email": "Email",
        "site.brand_address": "Address",
        "site.brand_website": "Website",
        "site.brand_notes": "Notes",
        "site.brand_logo": "Logo",
        "site.brand_upload_logo": "Upload logo",
        "site.gsc_property": "Search Console property",
        "site.gsc_property_note": "Stats for this site only. Leave empty to use your default property.",
        "site.gsc_property_global": "Use default property",
        "site.no_gsc": "Connect Search Console to pick a property per site.",
        "site.site_images": "Site images",
        "site.no_site_images": "Images generated while this site is open are kept here.",
        "site.save_site": "Save site settings",
        "site.back_to_studio": "Back to Studio",
        "flash.site_saved": "Site settings saved.",
        "flash.site_brand_invalid": "Brand data is invalid.",
        "flash.logo_saved": "Logo updated.",
        "site.tab_preview": "Preview",
        "site.preview_path": "Page",
        "site.preview_open": "Open",
        "site.preview_desktop": "Desktop",
        "site.preview_mobile": "Mobile",
        "site.preview_select": "Select element",
        "site.preview_selecting": "Click an element…",
        "site.preview_select_hint": "Turn on selection, then click any text, image, or section in the preview.",
        "site.preview_selected": "Selected",
        "site.preview_clear": "Clear",
        "site.preview_prompt_placeholder": "Describe the change, e.g. 'cambia esto a rojo'",
        "site.preview_apply": "Apply change",
        "site.preview_no_selection": "No element selected. Describe the change and the AI will locate it.",
        "site.preview_picker_hint": "Click an element to select it",
        "site.compare": "Compare",
        "site.compare_title": "Before / after",
        "site.before": "Before",
        "site.after": "After",
        "site.compare_empty": "No file changes to compare.",
        "site.compare_added": "New in this update",
        "site.compare_removed": "Removed in this update",
        "flash.selection_cleared": "Selection cleared.",
        "site.health": "Action center",
        "site.health_note": "Issues found on this site, with concrete fixes you can review and apply.",
        "site.scan_now": "Scan now",
        "site.skip_external": "Skip external links (faster)",
        "site.last_scan": "Last scan",
        "site.never_scanned": "Not scanned yet.",
        "site.no_findings": "No open issues. Nice work.",
        "site.where": "Where",
        "site.proposal": "Proposed fix",
        "site.apply_fix": "Apply",
        "site.ignore": "Ignore",
        "site.reopen": "Reopen",
        "site.ignored": "Ignored",
        "site.severity_error": "Error",
        "site.severity_warning": "Warning",
        "site.check_missing_title": "Page without title",
        "site.check_broken_internal_link": "Broken internal link",
        "site.check_broken_external_link": "Broken external link",
        "site.check_heavy_image": "Heavy image",
        "site.check_missing_alt": "Image without alt text",
        "site.check_form_no_action": "Form without destination",
        "site.check_form_no_submit": "Form without submit button",
        "site.check_form_input_name": "Input without name",
        "site.fix_title": "Title",
        "site.fix_alt": "Alt text",
        "site.fix_unlink": "Remove link, keep text",
        "site.fix_input_name": "Field name",
        "site.fix_optimize": "Optimize image",
        "site.guide_form_action": "This form has nowhere to send its data. Point its action to a working receiver.",
        "site.guide_form_submit": "This form has no submit button, so visitors cannot send it. Add one in the page.",
        "site.guide_heavy_no_pillow": "Install Pillow on the server to enable one-click optimization, or compress this image manually.",
        "site.guide_external": "Verify the URL in a browser. If it moved, update it; otherwise remove the link.",
        "site.fix_all": "Fix all",
        "site.fix_all_ai": "Fix all with AI",
        "site.fix_all_note": "Applies every automatic fix at once (titles, alt text, links, field names, images).",
        "site.fix_all_ai_note": "The AI reviews every open issue and rewrites the affected pages, including forms without destination or submit button.",
        "site.explain_ai": "Explain with AI",
        "site.ai_summary": "AI summary",
        "site.ai_fix": "Fix with AI",
        "flash.fixes_applied": "Applied {fixed} automatic fixes ({skipped} need review).",
        "flash.ai_fixes_applied": "The AI fixed {fixed} issues.",
        "flash.no_fixes": "There are no open issues to fix.",
        "flash.scan_done": "Scan finished.",
        "flash.finding_resolved": "Fix applied.",
        "flash.finding_ignored": "Issue ignored.",
        "flash.finding_reopened": "Issue reopened.",
        "flash.finding_not_found": "Issue not found.",
        "flash.fix_value_required": "Enter a value for the fix.",
        "site.requests": "Client requests",
        "req.links": "Review links",
        "req.new_link": "New link",
        "req.label": "Label",
        "req.label_placeholder": "e.g. Homepage review",
        "req.expires": "Expires in (days, empty = never)",
        "req.create_link": "Create link",
        "req.copy_link": "Copy",
        "req.revoke": "Revoke",
        "req.revoked": "Revoked",
        "req.expired": "Expired",
        "req.active": "Active",
        "req.no_links": "No review links yet.",
        "req.requests": "Requests",
        "req.no_requests": "No requests yet. Share a review link with your client.",
        "req.status_open": "Open",
        "req.status_in_review": "In review",
        "req.status_proposed": "Proposed",
        "req.status_approved": "Approved",
        "req.status_rejected": "Rejected",
        "req.status_done": "Done",
        "req.mark_review": "Start review",
        "req.propose": "Send proposal",
        "req.proposal": "Proposal",
        "req.proposal_placeholder": "Describe what you will deliver...",
        "req.mark_done": "Mark done",
        "req.reopen_req": "Reopen",
        "req.comments": "Comments",
        "req.add_comment": "Comment",
        "req.attachments": "Attachments",
        "req.selected_element": "Selected element",
        "req.delete": "Delete request",
        "req.confirm_delete": "Delete this request and its comments?",
        "portal.title": "Review site",
        "portal.new_request": "New request",
        "portal.your_name": "Your name",
        "portal.describe": "Describe the change",
        "portal.annotate": "Point at something",
        "portal.annotate_hint": "Click the preview to point at something (optional).",
        "portal.send": "Send request",
        "portal.my_requests": "Requests",
        "portal.no_requests": "No requests yet.",
        "portal.approve": "Approve proposal",
        "portal.reject": "Request changes",
        "portal.decided_approved": "You approved this proposal.",
        "portal.decided_rejected": "You asked for changes.",
        "portal.proposal_from_team": "Proposal from the team",
        "portal.invalid_link": "This review link is invalid, expired, or revoked.",
        "portal.back": "Back",
        "portal.attach_note": "Images or PDF, up to 10 MB each.",
        "flash.link_created": "Review link created.",
        "flash.link_revoked": "Link revoked.",
        "flash.request_created": "Request sent.",
        "flash.request_updated": "Request updated.",
        "flash.request_deleted": "Request deleted.",
        "flash.request_not_found": "Request not found.",
        "flash.comment_added": "Comment added.",
        "flash.invalid_transition": "That status change is not allowed.",
        "flash.attachment_invalid": "Attachments must be images or PDF up to 10 MB.",
        "site.calendar": "Calendar",
        "cal.new": "New event",
        "cal.title": "Title",
        "cal.kind": "Type",
        "cal.kind_promo": "Promotion",
        "cal.kind_blog": "Blog post",
        "cal.kind_prices": "Price update",
        "cal.kind_note": "Note",
        "cal.brief": "Brief (what should change)",
        "cal.starts_on": "Starts on",
        "cal.ends_on": "Ends (optional)",
        "cal.create": "Schedule",
        "cal.save": "Save",
        "cal.execute": "Implement now with AI",
        "cal.cancel_ev": "Cancel",
        "cal.delete": "Delete",
        "cal.confirm_delete": "Delete this event?",
        "cal.status_scheduled": "Scheduled",
        "cal.status_active": "Active",
        "cal.status_expired": "Expired",
        "cal.status_done": "Done",
        "cal.status_cancelled": "Cancelled",
        "cal.no_events": "No scheduled events.",
        "cal.implemented_in": "Implemented in update",
        "flash.event_created": "Event scheduled.",
        "flash.event_updated": "Event updated.",
        "flash.event_cancelled": "Event cancelled.",
        "flash.event_deleted": "Event deleted.",
        "flash.event_executed": "Change implemented.",
        "flash.event_not_found": "Event not found.",
        "flash.invalid_dates": "The end must be after the start.",
        "site.inbox": "Inbox",
        "inbox.note": "Form inquiries from this site.",
        "inbox.token": "Form receiver",
        "inbox.new_token": "New token",
        "inbox.snippet": "Paste this into your forms",
        "inbox.no_token": "Create a token to start receiving.",
        "inbox.status_new": "New",
        "inbox.status_attended": "Attended",
        "inbox.attend": "Mark attended",
        "inbox.reopen_in": "Reopen",
        "inbox.delete": "Delete",
        "inbox.confirm_delete": "Delete this message?",
        "inbox.no_messages": "No messages yet.",
        "inbox.from": "From",
        "inbox.page": "Page",
        "flash.message_attended": "Marked as attended.",
        "flash.message_reopened": "Message reopened.",
        "flash.message_deleted": "Message deleted.",
        "flash.message_not_found": "Message not found.",
        "flash.token_created": "Token created.",
        "flash.token_revoked": "Token revoked.",
        "site.alerts": "Alerts",
        "alerts.rules": "Rules",
        "alerts.new_rule": "New rule",
        "alerts.name": "Name",
        "alerts.kind": "Type",
        "alerts.kind_uptime": "Uptime",
        "alerts.kind_tls": "TLS certificate",
        "alerts.kind_publish": "Publish failures",
        "alerts.target": "URL or host",
        "alerts.threshold": "Warn when fewer days than",
        "alerts.create": "Create rule",
        "alerts.enable": "Enable",
        "alerts.disable": "Disable",
        "alerts.delete": "Delete",
        "alerts.check_now": "Check now",
        "alerts.list": "Alerts",
        "alerts.no_alerts": "No alerts.",
        "alerts.no_rules": "No rules yet. Publish failures are reported automatically.",
        "alerts.ack": "Acknowledge",
        "alerts.resolve": "Resolve",
        "alerts.status_open": "Open",
        "alerts.status_acked": "Acked",
        "alerts.status_resolved": "Resolved",
        "alerts.continuous_note": "For 24/7 monitoring, run `python run.py check-alerts` on a schedule (cron/systemd) on an always-on machine.",
        "flash.rule_created": "Rule created.",
        "flash.rule_updated": "Rule updated.",
        "flash.rule_deleted": "Rule deleted.",
        "flash.rule_not_found": "Rule not found.",
        "flash.alert_not_found": "Alert not found.",
        "flash.alert_updated": "Alert updated.",
        "flash.check_done": "Check finished.",
        "site.reports": "Reports",
        "rep.new": "New report link",
        "rep.period": "Month",
        "rep.create": "Create link",
        "rep.links": "Shared reports",
        "rep.no_links": "No shared reports.",
        "rep.revoke": "Revoke",
        "rep.changes": "Changes made",
        "rep.visits": "Visits (Search Console)",
        "rep.clicks": "Clicks",
        "rep.impressions": "Impressions",
        "rep.inquiries": "Inquiries received",
        "rep.issues": "Issues resolved",
        "rep.requests_done": "Requests completed",
        "rep.no_gsc": "Connect Search Console for visit stats.",
        "rep.download": "Download / print PDF",
        "rep.summary_for": "Monthly summary",
        "flash.report_created": "Report link created.",
        "flash.report_revoked": "Report revoked.",
        "flash.report_not_found": "Report not found.",
        "nav.inbox": "Inbox",
        "nav.calendar": "Calendar",
        "nav.alerts": "Alerts",
        "nav.reports": "Reports",
        "nav.notifications": "Notifications",
        "notif.title": "Notifications",
        "notif.note": "New messages, requests and alerts across your sites.",
        "notif.empty": "You're all caught up.",
        "notif.mark_read": "Mark read",
        "notif.mark_all": "Mark all read",
        "notif.unread": "Unread",
        "notif.kind_inbox": "Inbox",
        "notif.kind_request": "Request",
        "notif.kind_alert": "Alert",
        "flash.notification_not_found": "Notification not found.",
        "nav.section_main": "Main",
        "nav.section_site": "Site",
        "nav.section_team": "Team",
        "nav.section_system": "System",
        "dashboard.site_stats": "Showing stats for {site}",
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
        "settings.register_note": "Register each URI below exactly (scheme, host, port, and path must match) in Google Cloud Console → Credentials → your OAuth client → Authorized redirect URIs. Then press Verify.",
        "settings.suggested_uris": "URIs to register",
        "settings.copy": "Copy",
        "settings.copied": "Copied.",
        "settings.verify_google": "Verify with Google",
        "settings.verify_ok": "Google accepts this URI. You can connect from the dashboard.",
        "settings.verify_mismatch": "Google does not accept this URI yet. Register it exactly as shown and verify again.",
        "settings.verify_invalid_client": "Google rejected the OAuth client. Check GOOGLE_CLIENT_ID in the server .env file.",
        "settings.verify_network": "Could not reach Google to verify. Check the server connection and try again.",
        "settings.verify_unknown": "Google gave an unexpected answer. Try again.",
        "settings.verify_missing": "Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to the server .env file first.",
        "settings.muse": "Muse API",
        "settings.muse_note": "Store your Muse API key here so project creation and image generation use your own account.",
        "settings.muse_api_key": "Muse API key",
        "settings.muse_api_key_placeholder": "Leave blank to keep the saved key",
        "settings.muse_configured": "API key saved",
        "settings.buffer": "Buffer API",
        "settings.buffer_note": "Store your Buffer API key here to publish social content to your connected channels.",
        "settings.buffer_api_key": "Buffer API key",
        "settings.buffer_api_key_placeholder": "Leave blank to keep the saved key",
        "settings.buffer_configured": "API key saved",
        "social.buffer_key_required": "Add your Buffer API key in Settings to publish social content.",
        "social.channel_required": "Choose one of your Buffer channels for this post.",
        "social.text_required": "Write the post text or describe what to generate.",
        "social.prompt_required": "Describe what the post should say.",
        "social.image_url_invalid": "The image URL must be a complete http(s) address.",
        "social.post_type_invalid": "Choose a valid post type: post, story, or reel.",
        "social.post_type": "Publication type",
        "social.all_channels": "All my channels",
        "social.all_channels_preview": "All channels ({count})",
        "social.partial_ok": "{ok} of {total} channels published.",
        "social.type_post": "Post",
        "social.type_story": "Story",
        "social.type_reel": "Reel",
        "social.edit_instruction_required": "Describe how to edit the image.",
        "social.upload_label": "Or upload your own image",
        "social.upload_button": "Upload image",
        "social.no_file": "No file chosen",
        "social.edit_label": "Edit this image with AI (optional)",
        "social.edit_placeholder": "E.g. make the sky sunset",
        "social.edit_button": "Edit with AI",
        "social.kicker": "Social content",
        "social.title": "Create social posts",
        "social.composer": "Composer",
        "social.preview": "Preview",
        "social.channel": "Channel",
        "social.select_channel": "Select a channel",
        "social.loading_channels": "Loading channels...",
        "social.post_text": "Post text",
        "social.text_placeholder": "Write your post here...",
        "social.assist_label": "Need help writing?",
        "social.assist_placeholder": "E.g. announce our weekend discount",
        "social.assist_button": "Generate with AI",
        "social.working": "Working...",
        "social.image_label": "Post image (optional)",
        "social.image_placeholder": "E.g. a sunny product photo",
        "social.image_button": "Create image",
        "social.remove_image": "Remove image",
        "social.image_attached": "Image attached to this post.",
        "social.localhost_warning": "Note: Buffer can only fetch the image once this app has a public address. Preview works regardless.",
        "social.save_draft": "Save as draft",
        "social.add_queue": "Add to queue",
        "social.publish_now": "Publish now",
        "social.published_now_ok": "Post published.",
        "social.history": "Recent posts",
        "social.no_posts": "No posts yet. Your drafts and queued posts will appear here.",
        "social.key_missing": "Add your Buffer API key to publish.",
        "social.key_missing_link": "Open Settings",
        "social.preview_empty": "Your post preview will appear here.",
        "social.preview_note": "Preview. Each network renders posts slightly differently.",
        "social.published_ok": "Post added to the Buffer queue.",
        "social.draft_ok": "Draft saved in Buffer.",
        "social.suggestions": "Ideas from your site",
        "social.suggestions_note": "Based on your connected website: brand, pages, and upcoming events.",
        "social.suggestions_empty": "Connect a site in Studio to get ideas based on its content.",
        "social.generate_ideas": "Generate ideas with AI",
        "social.use_idea": "Use",
        "social.from_site": "From your site",
        "settings.client_id": "Client ID",
        "settings.client_secret": "Client Secret",
        "settings.redirect_uri": "Redirect URI",
        "settings.configured": "Configured",
        "settings.pending": "Pending",
        "settings.update": "Update settings",
        "site.kicker": "Workspace",
        "site.title": "ONEBoard Studio",
        "site.directory": "Project folder",
        "site.directory_note": "Choose a folder for anything you want to create. If you do not choose one, ONEBoard creates a personal project folder automatically.",
        "site.directory_env_note": "The website directory is assigned by the developer for the selected Search Console property.",
        "site.path": "Directory path",
        "site.path_placeholder": "C:\\Sites\\example.com",
        "site.connect": "Connect directory",
        "site.browse": "Browse",
        "site.select_folder": "Select folder",
        "site.select_folder_hint": "Choose a folder visually",
        "site.browser_title": "Choose a working folder",
        "site.browser_intro": "Open a folder to browse its contents, then choose it as your workspace.",
        "site.browser_up": "Up",
        "site.browser_home": "Home",
        "site.browser_empty": "No subfolders here.",
        "site.browser_cannot_select": "This folder can't be used. Pick a subfolder instead.",
        "site.use_folder": "Use this folder",
        "site.browser_cancel": "Cancel",
        "site.connected": "Connected",
        "site.not_connected": "Not connected",
        "site.last_updated": "Last updated",
        "site.terminal": "Terminal",
        "site.command": "Command",
        "site.command_placeholder": "nano index.html",
        "site.run_command": "Run command",
        "site.ai_studio": "AI Project Studio",
        "site.codex_update": "Create anything",
        "site.codex_prompt": "Message Muse",
        "site.codex_prompt_placeholder": "Describe what you want to create or change...",
        "site.codex_image": "Suggested image",
        "site.codex_image_note": "Optional. Muse will use this image only for this update request.",
        "site.asset_library": "Asset library",
        "site.asset_upload": "Upload asset",
        "site.asset_empty": "No reusable images have been uploaded yet.",
        "site.use_asset": "Use image",
        "site.selected_asset": "Selected image",
        "site.quick_actions": "Quick actions",
        "site.quick_hero": "Workspace README",
        "site.quick_section": "Add file",
        "site.quick_cta": "Review files",
        "site.quick_landing": "New document",
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
        "site.terminal_ready": "Terminal ready. Commands run from your project folder.",
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
        "flash.verification_token_invalid": "The verification link is invalid or expired.",
        "flash.password_reset_success": "Password updated. You can now sign in.",
        "flash.current_password_required": "Enter your current password to change email or password.",
        "flash.current_password_invalid": "The current password is incorrect.",
        "flash.email_invalid": "Enter a valid email.",
        "flash.password_update_mismatch": "The new passwords do not match.",
        "flash.avatar_invalid": "Upload a PNG, JPG, JPEG, JFIF, GIF, or WEBP image.",
        "flash.image_invalid": "The image is invalid or unavailable.",
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
        "flash.search_console_revoke_failed": "Disconnected locally, but Google could not revoke the token: {error}",
        "flash.logout_success": "Signed out successfully.",
        "flash.site_path_required": "Enter a website directory path.",
        "flash.site_path_missing": "The directory does not exist.",
        "flash.site_path_not_directory": "The path is not a directory.",
        "flash.site_path_create_failed": "Could not create the directory. Check the path and permissions.",
        "flash.project_not_found": "Project not found.",
        "site.projects": "Projects",
        "site.projects_note": "Switch between working folders. Each one keeps its own chat, updates, and backups.",
        "site.new_project": "New project",
        "site.open_project": "Open",
        "site.current_project": "Current",
        "site.remove_project": "Remove",
        "site.project_missing": "Folder missing",
        "site.confirm_remove_project": "Remove this project from the list? Files on disk are kept.",
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
        "nav.site_manager": "Studio",
        "nav.security_scan": "Escaneo de seguridad",
        "nav.social": "Redes",
        "nav.help": "Ayuda",
        "nav.settings": "Configuración",
        "nav.teams": "Equipos",
        "nav.preview": "Vista previa",
        "nav.site": "Sitio",
        "nav.health": "Pendientes",
        "nav.requests": "Solicitudes",
        "nav.logout": "Salir",
        "teams.title": "Equipos",
        "teams.kicker": "Colaboración",
        "teams.subtitle": "Trabaja en los mismos proyectos con tu equipo y tus clientes.",
        "teams.new_team": "Nuevo equipo",
        "teams.create": "Crear equipo",
        "teams.name": "Nombre del equipo",
        "teams.name_placeholder": "p. ej. Agencia Web",
        "teams.description": "Descripción (opcional)",
        "teams.my_teams": "Mis equipos",
        "teams.no_teams": "Aún no formas parte de ningún equipo. Crea uno o acepta una invitación.",
        "teams.members": "Miembros",
        "teams.projects": "Proyectos del equipo",
        "teams.no_projects": "Aún no hay proyectos compartidos. Comparte uno de tus proyectos personales abajo.",
        "teams.invites": "Invitaciones pendientes",
        "teams.no_invites": "No hay invitaciones pendientes.",
        "teams.invite_member": "Invitar miembro",
        "teams.invite_email": "Correo electrónico",
        "teams.invite_role": "Rol",
        "teams.send_invite": "Enviar invitación",
        "teams.copy_link": "Copiar enlace",
        "teams.link_ready": "Comparte este enlace con tu compañero:",
        "teams.revoke": "Revocar",
        "teams.remove": "Quitar",
        "teams.leave": "Salir del equipo",
        "teams.delete_team": "Eliminar equipo",
        "teams.confirm_delete": "¿Eliminar este equipo? Los proyectos compartidos volverán a ser carpetas sin compartir. Los archivos se conservan.",
        "teams.confirm_remove_member": "¿Quitar a este miembro del equipo?",
        "teams.confirm_leave": "¿Salir del equipo? Perderás acceso a sus proyectos compartidos.",
        "teams.transfer": "Transferir propiedad",
        "teams.role": "Rol",
        "teams.permissions": "Permisos",
        "teams.save_changes": "Guardar cambios",
        "teams.add_project": "Compartir un proyecto con el equipo",
        "teams.add_project_note": "Elige uno de tus proyectos personales, o pega una ruta de carpeta, para compartirlo con este equipo.",
        "teams.project_path": "Ruta de la carpeta",
        "teams.open_project": "Abrir",
        "teams.remove_project": "Dejar de compartir",
        "teams.confirm_remove_project": "¿Dejar de compartir este proyecto con el equipo? Los archivos se conservan.",
        "teams.open_in_studio": "Abrir en Studio",
        "teams.pending_invite": "Te han invitado a unirte a",
        "teams.accept_invite": "Aceptar invitación",
        "teams.accept_own_invite": "Aceptar",
        "teams.login_to_accept": "Inicia sesión o crea una cuenta para aceptar esta invitación.",
        "teams.role_owner": "Propietario",
        "teams.role_admin": "Administrador",
        "teams.role_editor": "Editor",
        "teams.role_viewer": "Lector",
        "teams.role_client": "Cliente",
        "teams.role_custom": "Personalizado",
        "teams.perm_view": "Ver",
        "teams.perm_edit": "Editar",
        "teams.perm_publish": "Publicar",
        "teams.perm_invite": "Invitar",
        "teams.perm_manage": "Gestionar",
        "teams.perm_billing": "Facturación",
        "teams.perm_view_note": "Abrir y leer los proyectos del equipo.",
        "teams.perm_edit_note": "Cambiar archivos, usar el asistente y la terminal.",
        "teams.perm_publish_note": "Aprobar cambios y desplegar a servidores remotos.",
        "teams.perm_invite_note": "Invitar nuevos miembros al equipo.",
        "teams.perm_manage_note": "Cambiar roles, quitar miembros y gestionar proyectos compartidos.",
        "teams.perm_billing_note": "Reservado para la gestión de facturación.",
        "teams.you": "tú",
        "teams.personal": "Personal",
        "teams.shared": "Compartido",
        "teams.team_project": "Proyecto de equipo",
        "teams.read_only": "Solo lectura: tu rol en este equipo no permite esta acción.",
        "teams.expires": "Expira",
        "teams.created": "Creado",
        "teams.back_to_teams": "Volver a equipos",
        "flash.team_created": "Equipo creado.",
        "flash.team_updated": "Equipo actualizado.",
        "flash.team_deleted": "Equipo eliminado.",
        "flash.team_not_found": "Equipo no encontrado.",
        "flash.team_name_required": "Ponle un nombre al equipo.",
        "flash.invite_sent": "Invitación enviada.",
        "flash.invite_link_ready": "El correo no está configurado, copia el enlace de invitación manualmente.",
        "flash.invite_revoked": "Invitación revocada.",
        "flash.invite_invalid": "Esta invitación no es válida o expiró.",
        "flash.invite_accepted": "Te uniste al equipo.",
        "flash.invite_email_mismatch": "Esta invitación se envió a otra dirección de correo.",
        "flash.already_member": "Ese usuario ya es miembro de este equipo.",
        "flash.member_updated": "Miembro actualizado.",
        "flash.member_removed": "Miembro eliminado.",
        "flash.team_member_not_found": "Miembro del equipo no encontrado.",
        "flash.left_team": "Saliste del equipo.",
        "flash.owner_transfer_required": "Primero transfiere la propiedad a otro miembro.",
        "flash.cannot_modify_owner": "El propietario del equipo no se puede modificar. Transfiere la propiedad primero.",
        "flash.team_permission_denied": "Tu rol en el equipo no permite esta acción.",
        "flash.team_project_added": "Proyecto compartido con el equipo.",
        "flash.team_project_removed": "Proyecto sin compartir del equipo.",
        "flash.team_project_elsewhere": "Esta carpeta ya está compartida con otro equipo.",
        "flash.not_team_member": "No eres miembro de este equipo.",
        "flash.ownership_transferred": "Propiedad transferida.",
        "flash.team_path_forbidden": "Esta carpeta pertenece a un equipo del que no formas parte.",
        "site.site_settings": "Ajustes del sitio",
        "site.display_name": "Nombre del sitio",
        "site.client_name": "Cliente",
        "site.brand": "Memoria de marca",
        "site.brand_note": "Se guarda una vez por sitio. La IA lo usa para páginas, imágenes y publicaciones.",
        "site.brand_business_name": "Nombre del negocio",
        "site.brand_tagline": "Eslogan",
        "site.brand_services": "Servicios y productos",
        "site.brand_audience": "Público",
        "site.brand_tone": "Tono de comunicación",
        "site.brand_colors": "Colores de marca",
        "site.brand_color_primary": "Primario",
        "site.brand_color_secondary": "Secundario",
        "site.brand_color_accent": "Acento",
        "site.brand_fonts": "Tipografías",
        "site.brand_font_headings": "Titulares",
        "site.brand_font_body": "Texto",
        "site.brand_phone": "Teléfono",
        "site.brand_email": "Correo",
        "site.brand_address": "Dirección",
        "site.brand_website": "Sitio web",
        "site.brand_notes": "Notas",
        "site.brand_logo": "Logotipo",
        "site.brand_upload_logo": "Subir logotipo",
        "site.gsc_property": "Propiedad de Search Console",
        "site.gsc_property_note": "Estadísticas solo para este sitio. Déjalo vacío para usar tu propiedad predeterminada.",
        "site.gsc_property_global": "Usar propiedad predeterminada",
        "site.no_gsc": "Conecta Search Console para elegir una propiedad por sitio.",
        "site.site_images": "Imágenes del sitio",
        "site.no_site_images": "Las imágenes generadas con este sitio abierto se guardan aquí.",
        "site.save_site": "Guardar ajustes",
        "site.back_to_studio": "Volver a Studio",
        "flash.site_saved": "Ajustes del sitio guardados.",
        "flash.site_brand_invalid": "Los datos de marca no son válidos.",
        "flash.logo_saved": "Logotipo actualizado.",
        "site.tab_preview": "Vista previa",
        "site.preview_path": "Página",
        "site.preview_open": "Abrir",
        "site.preview_desktop": "Computadora",
        "site.preview_mobile": "Móvil",
        "site.preview_select": "Seleccionar elemento",
        "site.preview_selecting": "Haz clic en un elemento…",
        "site.preview_select_hint": "Activa la selección y haz clic en un texto, imagen o sección de la vista previa.",
        "site.preview_selected": "Seleccionado",
        "site.preview_clear": "Limpiar",
        "site.preview_prompt_placeholder": "Describe el cambio, p. ej. «cambia esto a rojo»",
        "site.preview_apply": "Aplicar cambio",
        "site.preview_no_selection": "Sin elemento seleccionado. Describe el cambio y la IA lo localizará.",
        "site.preview_picker_hint": "Haz clic en un elemento para seleccionarlo",
        "site.compare": "Comparar",
        "site.compare_title": "Antes / después",
        "site.before": "Antes",
        "site.after": "Después",
        "site.compare_empty": "No hay cambios de archivos para comparar.",
        "site.compare_added": "Nuevo en este cambio",
        "site.compare_removed": "Eliminado en este cambio",
        "flash.selection_cleared": "Selección eliminada.",
        "site.health": "Centro de pendientes",
        "site.health_note": "Problemas de este sitio, con soluciones concretas para revisar y aplicar.",
        "site.scan_now": "Analizar ahora",
        "site.skip_external": "Omitir enlaces externos (más rápido)",
        "site.last_scan": "Último análisis",
        "site.never_scanned": "Aún sin analizar.",
        "site.no_findings": "Sin pendientes. Buen trabajo.",
        "site.where": "Dónde",
        "site.proposal": "Solución propuesta",
        "site.apply_fix": "Aplicar",
        "site.ignore": "Ignorar",
        "site.reopen": "Reabrir",
        "site.ignored": "Ignorados",
        "site.severity_error": "Error",
        "site.severity_warning": "Aviso",
        "site.check_missing_title": "Página sin título",
        "site.check_broken_internal_link": "Enlace interno roto",
        "site.check_broken_external_link": "Enlace externo roto",
        "site.check_heavy_image": "Imagen pesada",
        "site.check_missing_alt": "Imagen sin texto alternativo",
        "site.check_form_no_action": "Formulario sin destino",
        "site.check_form_no_submit": "Formulario sin botón de envío",
        "site.check_form_input_name": "Campo sin nombre",
        "site.fix_title": "Título",
        "site.fix_alt": "Texto alternativo",
        "site.fix_unlink": "Quitar enlace, dejar texto",
        "site.fix_input_name": "Nombre del campo",
        "site.fix_optimize": "Optimizar imagen",
        "site.guide_form_action": "Este formulario no tiene a dónde enviar sus datos. Apunta su action a un receptor válido.",
        "site.guide_form_submit": "Este formulario no tiene botón de envío, así que nadie puede enviarlo. Añade uno en la página.",
        "site.guide_heavy_no_pillow": "Instala Pillow en el servidor para optimizar con un clic, o comprime esta imagen manualmente.",
        "site.guide_external": "Verifica la URL en un navegador. Si cambió, actualízala; si no, quita el enlace.",
        "site.fix_all": "Reparar todo",
        "site.fix_all_ai": "Reparar todo con IA",
        "site.fix_all_note": "Aplica todas las correcciones automáticas a la vez (títulos, textos alternativos, enlaces, nombres de campos, imágenes).",
        "site.fix_all_ai_note": "La IA revisa todos los problemas abiertos y reescribe las páginas afectadas, incluyendo formularios sin destino o sin botón de envío.",
        "site.explain_ai": "Explicar con IA",
        "site.ai_summary": "Resumen de la IA",
        "site.ai_fix": "Reparar con IA",
        "flash.fixes_applied": "Se aplicaron {fixed} correcciones automáticas ({skipped} necesitan revisión).",
        "flash.ai_fixes_applied": "La IA corrigió {fixed} problemas.",
        "flash.no_fixes": "No hay problemas abiertos que corregir.",
        "flash.scan_done": "Análisis terminado.",
        "flash.finding_resolved": "Solución aplicada.",
        "flash.finding_ignored": "Pendiente ignorado.",
        "flash.finding_reopened": "Pendiente reabierto.",
        "flash.finding_not_found": "Pendiente no encontrado.",
        "flash.fix_value_required": "Ingresa un valor para la solución.",
        "site.requests": "Solicitudes de clientes",
        "req.links": "Enlaces de revisión",
        "req.new_link": "Nuevo enlace",
        "req.label": "Etiqueta",
        "req.label_placeholder": "p. ej. Revisión inicio",
        "req.expires": "Expira en (días, vacío = nunca)",
        "req.create_link": "Crear enlace",
        "req.copy_link": "Copiar",
        "req.revoke": "Revocar",
        "req.revoked": "Revocado",
        "req.expired": "Expirado",
        "req.active": "Activo",
        "req.no_links": "Aún no hay enlaces de revisión.",
        "req.requests": "Solicitudes",
        "req.no_requests": "Aún no hay solicitudes. Comparte un enlace de revisión con tu cliente.",
        "req.status_open": "Abierta",
        "req.status_in_review": "En revisión",
        "req.status_proposed": "Propuesta",
        "req.status_approved": "Aprobada",
        "req.status_rejected": "Rechazada",
        "req.status_done": "Hecha",
        "req.mark_review": "Empezar revisión",
        "req.propose": "Enviar propuesta",
        "req.proposal": "Propuesta",
        "req.proposal_placeholder": "Describe lo que entregarás...",
        "req.mark_done": "Marcar hecha",
        "req.reopen_req": "Reabrir",
        "req.comments": "Comentarios",
        "req.add_comment": "Comentar",
        "req.attachments": "Adjuntos",
        "req.selected_element": "Elemento seleccionado",
        "req.delete": "Eliminar solicitud",
        "req.confirm_delete": "¿Eliminar esta solicitud y sus comentarios?",
        "portal.title": "Revisar sitio",
        "portal.new_request": "Nueva solicitud",
        "portal.your_name": "Tu nombre",
        "portal.describe": "Describe el cambio",
        "portal.annotate": "Señalar algo",
        "portal.annotate_hint": "Haz clic en la vista para señalar algo (opcional).",
        "portal.send": "Enviar solicitud",
        "portal.my_requests": "Solicitudes",
        "portal.no_requests": "Aún no hay solicitudes.",
        "portal.approve": "Aprobar propuesta",
        "portal.reject": "Pedir cambios",
        "portal.decided_approved": "Aprobaste esta propuesta.",
        "portal.decided_rejected": "Pediste cambios.",
        "portal.proposal_from_team": "Propuesta del equipo",
        "portal.invalid_link": "Este enlace de revisión no es válido, expiró o fue revocado.",
        "portal.back": "Volver",
        "portal.attach_note": "Imágenes o PDF, hasta 10 MB cada uno.",
        "flash.link_created": "Enlace de revisión creado.",
        "flash.link_revoked": "Enlace revocado.",
        "flash.request_created": "Solicitud enviada.",
        "flash.request_updated": "Solicitud actualizada.",
        "flash.request_deleted": "Solicitud eliminada.",
        "flash.request_not_found": "Solicitud no encontrada.",
        "flash.comment_added": "Comentario añadido.",
        "flash.invalid_transition": "Ese cambio de estado no está permitido.",
        "flash.attachment_invalid": "Los adjuntos deben ser imágenes o PDF de hasta 10 MB.",
        "site.calendar": "Calendario",
        "cal.new": "Nuevo evento",
        "cal.title": "Título",
        "cal.kind": "Tipo",
        "cal.kind_promo": "Promoción",
        "cal.kind_blog": "Blog",
        "cal.kind_prices": "Precios",
        "cal.kind_note": "Nota",
        "cal.brief": "Brief (qué debe cambiar)",
        "cal.starts_on": "Empieza",
        "cal.ends_on": "Termina (opcional)",
        "cal.create": "Programar",
        "cal.save": "Guardar",
        "cal.execute": "Implementar ahora con IA",
        "cal.cancel_ev": "Cancelar",
        "cal.delete": "Eliminar",
        "cal.confirm_delete": "¿Eliminar este evento?",
        "cal.status_scheduled": "Programado",
        "cal.status_active": "Activo",
        "cal.status_expired": "Expirado",
        "cal.status_done": "Hecho",
        "cal.status_cancelled": "Cancelado",
        "cal.no_events": "Sin eventos programados.",
        "cal.implemented_in": "Implementado en el cambio",
        "flash.event_created": "Evento programado.",
        "flash.event_updated": "Evento actualizado.",
        "flash.event_cancelled": "Evento cancelado.",
        "flash.event_deleted": "Evento eliminado.",
        "flash.event_executed": "Cambio implementado.",
        "flash.event_not_found": "Evento no encontrado.",
        "flash.invalid_dates": "El fin debe ser posterior al inicio.",
        "site.inbox": "Bandeja",
        "inbox.note": "Consultas de formularios de este sitio.",
        "inbox.token": "Receptor de formularios",
        "inbox.new_token": "Nuevo token",
        "inbox.snippet": "Pega esto en tus formularios",
        "inbox.no_token": "Crea un token para empezar a recibir.",
        "inbox.status_new": "Nueva",
        "inbox.status_attended": "Atendida",
        "inbox.attend": "Marcar atendida",
        "inbox.reopen_in": "Reabrir",
        "inbox.delete": "Eliminar",
        "inbox.confirm_delete": "¿Eliminar este mensaje?",
        "inbox.no_messages": "Aún no hay mensajes.",
        "inbox.from": "De",
        "inbox.page": "Página",
        "flash.message_attended": "Marcada como atendida.",
        "flash.message_reopened": "Mensaje reabierto.",
        "flash.message_deleted": "Mensaje eliminado.",
        "flash.message_not_found": "Mensaje no encontrado.",
        "flash.token_created": "Token creado.",
        "flash.token_revoked": "Token revocado.",
        "site.alerts": "Alertas",
        "alerts.rules": "Reglas",
        "alerts.new_rule": "Nueva regla",
        "alerts.name": "Nombre",
        "alerts.kind": "Tipo",
        "alerts.kind_uptime": "Disponibilidad",
        "alerts.kind_tls": "Certificado TLS",
        "alerts.kind_publish": "Fallos de publicación",
        "alerts.target": "URL o host",
        "alerts.threshold": "Avisar con menos días de",
        "alerts.create": "Crear regla",
        "alerts.enable": "Activar",
        "alerts.disable": "Desactivar",
        "alerts.delete": "Eliminar",
        "alerts.check_now": "Comprobar ahora",
        "alerts.list": "Alertas",
        "alerts.no_alerts": "Sin alertas.",
        "alerts.no_rules": "Sin reglas. Los fallos de publicación se reportan solos.",
        "alerts.ack": "Enterado",
        "alerts.resolve": "Resolver",
        "alerts.status_open": "Abierta",
        "alerts.status_acked": "Vista",
        "alerts.status_resolved": "Resuelta",
        "alerts.continuous_note": "Para monitoreo 24/7, ejecuta `python run.py check-alerts` programado (cron/systemd) en una máquina siempre encendida.",
        "flash.rule_created": "Regla creada.",
        "flash.rule_updated": "Regla actualizada.",
        "flash.rule_deleted": "Regla eliminada.",
        "flash.rule_not_found": "Regla no encontrada.",
        "flash.alert_not_found": "Alerta no encontrada.",
        "flash.alert_updated": "Alerta actualizada.",
        "flash.check_done": "Comprobación terminada.",
        "site.reports": "Informes",
        "rep.new": "Nuevo enlace de informe",
        "rep.period": "Mes",
        "rep.create": "Crear enlace",
        "rep.links": "Informes compartidos",
        "rep.no_links": "Sin informes compartidos.",
        "rep.revoke": "Revocar",
        "rep.changes": "Cambios realizados",
        "rep.visits": "Visitas (Search Console)",
        "rep.clicks": "Clics",
        "rep.impressions": "Impresiones",
        "rep.inquiries": "Consultas recibidas",
        "rep.issues": "Problemas resueltos",
        "rep.requests_done": "Solicitudes completadas",
        "rep.no_gsc": "Conecta Search Console para estadísticas de visitas.",
        "rep.download": "Descargar / imprimir PDF",
        "rep.summary_for": "Resumen mensual",
        "flash.report_created": "Enlace de informe creado.",
        "flash.report_revoked": "Informe revocado.",
        "flash.report_not_found": "Informe no encontrado.",
        "nav.inbox": "Bandeja",
        "nav.calendar": "Calendario",
        "nav.alerts": "Alertas",
        "nav.reports": "Informes",
        "nav.notifications": "Notificaciones",
        "notif.title": "Notificaciones",
        "notif.note": "Mensajes, solicitudes y alertas nuevas de tus sitios.",
        "notif.empty": "Estás al día.",
        "notif.mark_read": "Marcar leída",
        "notif.mark_all": "Marcar todas",
        "notif.unread": "Sin leer",
        "notif.kind_inbox": "Bandeja",
        "notif.kind_request": "Solicitud",
        "notif.kind_alert": "Alerta",
        "flash.notification_not_found": "Notificación no encontrada.",
        "nav.section_main": "Principal",
        "nav.section_site": "Sitio",
        "nav.section_team": "Equipo",
        "nav.section_system": "Sistema",
        "dashboard.site_stats": "Mostrando estadísticas de {site}",
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
        "settings.register_note": "Registra cada URI de abajo de forma exacta (esquema, host, puerto y ruta deben coincidir) en Google Cloud Console → Credenciales → tu cliente OAuth → URIs de redirección autorizados. Luego pulsa Verificar.",
        "settings.suggested_uris": "URIs a registrar",
        "settings.copy": "Copiar",
        "settings.copied": "Copiado.",
        "settings.verify_google": "Verificar con Google",
        "settings.verify_ok": "Google acepta este URI. Ya puedes conectar desde el dashboard.",
        "settings.verify_mismatch": "Google aún no acepta este URI. Regístralo exacto como se muestra y verifica de nuevo.",
        "settings.verify_invalid_client": "Google rechazó el cliente OAuth. Revisa GOOGLE_CLIENT_ID en el .env del servidor.",
        "settings.verify_network": "No se pudo contactar a Google para verificar. Revisa la conexión del servidor e inténtalo de nuevo.",
        "settings.verify_unknown": "Google dio una respuesta inesperada. Inténtalo de nuevo.",
        "settings.verify_missing": "Agrega GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET al .env del servidor primero.",
        "settings.muse": "API de Muse",
        "settings.muse_note": "Guarda aquí tu API key de Muse para que la creación de proyectos y la generación de imágenes usen tu propia cuenta.",
        "settings.muse_api_key": "API key de Muse",
        "settings.muse_api_key_placeholder": "Déjalo vacío para mantener la key guardada",
        "settings.muse_configured": "API key guardada",
        "settings.buffer": "API de Buffer",
        "settings.buffer_note": "Guarda aquí tu API key de Buffer para publicar contenido social en tus canales conectados.",
        "settings.buffer_api_key": "API key de Buffer",
        "settings.buffer_api_key_placeholder": "Déjalo vacío para mantener la key guardada",
        "settings.buffer_configured": "API key guardada",
        "social.buffer_key_required": "Agrega tu API key de Buffer en Ajustes para publicar contenido social.",
        "social.channel_required": "Elige uno de tus canales de Buffer para esta publicación.",
        "social.text_required": "Escribe el texto o describe qué generar.",
        "social.prompt_required": "Describe de qué debe tratar la publicación.",
        "social.image_url_invalid": "La URL de la imagen debe ser una dirección http(s) completa.",
        "social.post_type_invalid": "Elige un tipo válido: post, story o reel.",
        "social.post_type": "Tipo de publicación",
        "social.all_channels": "Todos mis canales",
        "social.all_channels_preview": "Todos los canales ({count})",
        "social.partial_ok": "{ok} de {total} canales publicados.",
        "social.type_post": "Post",
        "social.type_story": "Historia",
        "social.type_reel": "Reel",
        "social.edit_instruction_required": "Describe cómo editar la imagen.",
        "social.upload_label": "O sube tu propia imagen",
        "social.upload_button": "Subir imagen",
        "social.no_file": "Ningún archivo",
        "social.edit_label": "Editar esta imagen con IA (opcional)",
        "social.edit_placeholder": "Ej. pon el cielo al atardecer",
        "social.edit_button": "Editar con IA",
        "social.kicker": "Contenido social",
        "social.title": "Crear publicaciones",
        "social.composer": "Redactor",
        "social.preview": "Vista previa",
        "social.channel": "Canal",
        "social.select_channel": "Elige un canal",
        "social.loading_channels": "Cargando canales...",
        "social.post_text": "Texto de la publicación",
        "social.text_placeholder": "Escribe tu publicación aquí...",
        "social.assist_label": "¿Ayuda para redactar?",
        "social.assist_placeholder": "Ej. anunciar nuestro descuento de fin de semana",
        "social.assist_button": "Generar con IA",
        "social.working": "Trabajando...",
        "social.image_label": "Imagen de la publicación (opcional)",
        "social.image_placeholder": "Ej. foto soleada del producto",
        "social.image_button": "Crear imagen",
        "social.remove_image": "Quitar imagen",
        "social.image_attached": "Imagen adjunta a esta publicación.",
        "social.localhost_warning": "Nota: Buffer solo puede descargar la imagen cuando esta app tenga una dirección pública. La vista previa funciona igual.",
        "social.save_draft": "Guardar borrador",
        "social.add_queue": "Agregar a la cola",
        "social.publish_now": "Publicar ahora",
        "social.published_now_ok": "Publicación enviada.",
        "social.history": "Publicaciones recientes",
        "social.no_posts": "Aún no hay publicaciones. Tus borradores y encolados aparecerán aquí.",
        "social.key_missing": "Agrega tu API key de Buffer para publicar.",
        "social.key_missing_link": "Abrir Ajustes",
        "social.preview_empty": "Tu vista previa aparecerá aquí.",
        "social.preview_note": "Vista previa. Cada red muestra las publicaciones un poco distinto.",
        "social.published_ok": "Publicación agregada a la cola de Buffer.",
        "social.draft_ok": "Borrador guardado en Buffer.",
        "social.suggestions": "Ideas desde tu sitio",
        "social.suggestions_note": "Basadas en tu sitio conectado: marca, páginas y próximos eventos.",
        "social.suggestions_empty": "Conecta un sitio en Studio para obtener ideas basadas en su contenido.",
        "social.generate_ideas": "Generar ideas con IA",
        "social.use_idea": "Usar",
        "social.from_site": "Desde tu sitio",
        "settings.client_id": "Client ID",
        "settings.client_secret": "Client Secret",
        "settings.redirect_uri": "Redirect URI",
        "settings.configured": "Configurado",
        "settings.pending": "Pendiente",
        "settings.update": "Actualizar configuración",
        "site.kicker": "Espacio de trabajo",
        "site.title": "ONEBoard Studio",
        "site.directory": "Carpeta del proyecto",
        "site.directory_note": "Elige una carpeta para crear lo que quieras. Si no eliges ninguna, ONEBoard creará automáticamente una carpeta personal para tus proyectos.",
        "site.directory_env_note": "El directorio del website es asignado por el desarrollador para la propiedad seleccionada de Search Console.",
        "site.path": "Ruta del directorio",
        "site.path_placeholder": "C:\\Sites\\example.com",
        "site.connect": "Conectar directorio",
        "site.browse": "Explorar",
        "site.select_folder": "Seleccionar carpeta",
        "site.select_folder_hint": "Elige una carpeta visualmente",
        "site.browser_title": "Elige una carpeta de trabajo",
        "site.browser_intro": "Abre una carpeta para explorar su contenido y después selecciónala como tu espacio de trabajo.",
        "site.browser_up": "Subir",
        "site.browser_home": "Inicio",
        "site.browser_empty": "No hay subcarpetas aquí.",
        "site.browser_cannot_select": "Esta carpeta no se puede usar. Elige una subcarpeta.",
        "site.use_folder": "Usar esta carpeta",
        "site.browser_cancel": "Cancelar",
        "site.connected": "Conectado",
        "site.not_connected": "No conectado",
        "site.last_updated": "Última actualización",
        "site.terminal": "Terminal",
        "site.command": "Comando",
        "site.command_placeholder": "nano index.html",
        "site.run_command": "Ejecutar comando",
        "site.ai_studio": "Estudio de proyectos con IA",
        "site.codex_update": "Crear cualquier cosa",
        "site.codex_prompt": "Mensaje para Muse",
        "site.codex_prompt_placeholder": "Describe qué quieres crear o cambiar...",
        "site.codex_image": "Imagen sugerida",
        "site.codex_image_note": "Opcional. Muse usará esta imagen solo para esta actualización.",
        "site.asset_library": "Biblioteca de assets",
        "site.asset_upload": "Subir asset",
        "site.asset_empty": "Todavía no hay imágenes reutilizables.",
        "site.use_asset": "Usar imagen",
        "site.selected_asset": "Imagen seleccionada",
        "site.quick_actions": "Acciones rápidas",
        "site.quick_hero": "README del espacio",
        "site.quick_section": "Agregar archivo",
        "site.quick_cta": "Revisar archivos",
        "site.quick_landing": "Nuevo documento",
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
        "site.terminal_ready": "Terminal lista. Los comandos se ejecutan desde la carpeta del proyecto.",
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
        "flash.verification_token_invalid": "El enlace de verificación es inválido o expiró.",
        "flash.password_reset_success": "Contraseña actualizada. Ya puedes iniciar sesión.",
        "flash.current_password_required": "Ingresa tu contraseña actual para cambiar email o contraseña.",
        "flash.current_password_invalid": "La contraseña actual es incorrecta.",
        "flash.email_invalid": "Ingresa un email válido.",
        "flash.password_update_mismatch": "Las nuevas contraseñas no coinciden.",
        "flash.avatar_invalid": "Sube una imagen PNG, JPG, JPEG, JFIF, GIF o WEBP.",
        "flash.image_invalid": "La imagen es inválida o no está disponible.",
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
        "flash.search_console_revoke_failed": "Desconectado localmente, pero Google no pudo revocar el token: {error}",
        "flash.logout_success": "Sesión cerrada correctamente.",
        "flash.site_path_required": "Ingresa la ruta del directorio del website.",
        "flash.site_path_missing": "El directorio no existe.",
        "flash.site_path_not_directory": "La ruta no es un directorio.",
        "flash.site_path_create_failed": "No se pudo crear el directorio. Revisa la ruta y los permisos.",
        "flash.project_not_found": "Proyecto no encontrado.",
        "site.projects": "Proyectos",
        "site.projects_note": "Cambia entre carpetas de trabajo. Cada una conserva su chat, actualizaciones y respaldos.",
        "site.new_project": "Nuevo proyecto",
        "site.open_project": "Abrir",
        "site.current_project": "Actual",
        "site.remove_project": "Quitar",
        "site.project_missing": "Carpeta no encontrada",
        "site.confirm_remove_project": "¿Quitar este proyecto de la lista? Los archivos se conservan.",
        "flash.site_path_unsafe": "Selecciona una carpeta dedicada al website, no una carpeta del sistema, de inicio o de datos de ONEBoard.",
        "flash.site_connected": "Directorio del website conectado.",
        "flash.site_directory_unmapped": "Conecta primero un directorio del website.",
        "flash.seo_page_created": "Página SEO «{title}» para la keyword «{keyword}» creada desde Oportunidades SEO. Revísala en Site Manager antes de publicar.",
        "flash.site_manager_seo_page_created": "Página SEO «{title}» para la keyword «{keyword}» creada en Site Manager. Revísala antes de publicar.",
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
    # Trust one reverse proxy (cloudflared, nginx, ...) so url_for(_external=True)
    # and request.url reflect the public https host. Required for the Google
    # OAuth redirect URI to match the address the browser actually uses.
    # Without this, behind a tunnel the app would send Google a loopback
    # redirect_uri and the connection would fail with redirect_uri_mismatch
    # (or bounce the browser to an unreachable 127.0.0.1 address).
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

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
            "nav_counts": sidebar_badge_counts,
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
        if not site_image_visible_to_user(safe_name, g.user["id"]):
            abort(404)
        return send_from_directory(generated_image_directory(), safe_name)

    @app.route("/uploads/brand-logos/<filename>")
    @login_required
    def uploaded_brand_logo(filename):
        safe_name = posixpath.basename(filename or "")
        if not brand_logo_visible_to_user(safe_name, g.user["id"]):
            abort(404)
        return send_from_directory(brand_logo_directory(), safe_name)

    @app.route("/uploads/social-images/<filename>")
    @login_required
    def uploaded_social_image(filename):
        safe_name = posixpath.basename(filename or "")
        if not safe_name.startswith(f"user-{g.user['id']}-"):
            abort(404)
        return send_from_directory(social_image_directory(), safe_name)

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
        if g.user:
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            user = query_db("SELECT id, email FROM users WHERE email = ?", (email,), one=True)
            if user:
                try:
                    send_password_reset_email(user["id"], user["email"])
                except ValueError as error:
                    flash(str(error), "danger")
                    return redirect(url_for("forgot_password"))
            flash(translate("flash.reset_email_sent"), "info")

        return render_template("auth/forgot_password.html")

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

    @app.route("/api/auth/verify-email", methods=("POST",))
    def api_verify_email():
        data = request.get_json(silent=True) or {}
        token = (data.get("token") or "").strip()
        user_id = consume_email_verification_token(token) if token else None
        if not user_id:
            return api_error(translate("flash.verification_token_invalid"), 400)
        execute_db("UPDATE users SET email_verified = 1 WHERE id = ?", (user_id,))
        return jsonify({"ok": True, "verified": True})

    @app.route("/api/auth/forgot-password", methods=("POST",))
    def api_forgot_password():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        user = query_db("SELECT id, email FROM users WHERE email = ?", (email,), one=True)
        if user:
            try:
                send_password_reset_email(user["id"], user["email"])
            except ValueError as error:
                return api_error(str(error), 503)
        return jsonify({"ok": True})

    @app.route("/api/auth/reset-password", methods=("POST",))
    def api_reset_password():
        data = request.get_json(silent=True) or {}
        token = (data.get("token") or "").strip()
        password = data.get("password") or ""
        confirm_password = data.get("confirm_password") or ""
        token_row = get_valid_password_reset_token(token) if token else None
        if not token_row:
            return api_error(translate("flash.reset_token_invalid"), 400)
        if not password or len(password) < 8 or password != confirm_password:
            return api_error(translate("flash.password_incorrect"), 400)
        execute_db(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (hash_password(password), token_row["user_id"]),
        )
        mark_password_reset_token_used(token_row["id"])
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
        revoke_warning = None
        if connection:
            try:
                revoke_google_connection(connection)
            except GoogleApiError as error:
                # Never leave the user stuck on a dead token: drop the local
                # row even when Google cannot revoke it (already expired,
                # revoked, or unreachable).
                revoke_warning = str(error)
        execute_db("DELETE FROM google_search_console_connections WHERE user_id = ?", (g.user["id"],))
        payload = {"ok": True, "gsc": to_jsonable(build_search_console_dashboard(g.user["id"]))}
        if revoke_warning:
            payload["revoke_warning"] = revoke_warning
        return jsonify(payload)

    @app.route("/api/site-manager")
    @login_required
    def api_site_manager():
        ensure_default_site_directory(g.user["id"])
        return jsonify({"ok": True, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/site-manager/connect", methods=("POST",))
    @login_required
    def api_site_manager_connect():
        data = request_payload()
        try:
            with site_operation_lock(g.user["id"]):
                project_id = data.get("project_id")
                path = data.get("path")
                if project_id not in (None, "") or (path or "").strip():
                    connect_site_project(
                        g.user["id"],
                        project_id=project_id if project_id not in (None, "") else None,
                        path=(path or "").strip() or None,
                    )
                else:
                    ensure_default_site_directory(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/site-manager/browse-directory")
    @login_required
    def api_site_manager_browse_directory():
        try:
            listing = browse_local_directories(request.args.get("path", ""))
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "listing": listing})

    @app.route("/api/site-manager/projects/remove", methods=("POST",))
    @login_required
    def api_site_manager_remove_project():
        data = request_payload()
        try:
            project_id = int(str(data.get("project_id") or "").strip())
        except (TypeError, ValueError):
            return api_error(translate("flash.project_not_found"), 400)
        try:
            with site_operation_lock(g.user["id"]):
                remove_site_project(g.user["id"], project_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "manager": to_jsonable(build_site_manager(g.user["id"]))})

    @app.route("/api/site-manager/files/raw")
    @login_required
    def api_site_manager_file_raw():
        file_path = request.args.get("path", "").strip()
        try:
            require_project_permission(g.user["id"], "view")
            absolute_path = resolve_site_file(g.user["id"], file_path)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError:
            return api_error(translate("flash.site_path_missing"), 404)
        if not os.path.isfile(absolute_path):
            return api_error(translate("flash.site_path_missing"), 404)
        return send_file(absolute_path, mimetype=mimetypes.guess_type(absolute_path)[0] or "application/octet-stream")

    @app.route("/api/site-manager/assets/raw")
    @login_required
    def api_site_manager_asset_raw():
        asset_path = request.args.get("path", "").strip()
        try:
            require_project_permission(g.user["id"], "view")
            validate_asset_path(g.user["id"], asset_path)
            absolute_path = resolve_site_file(g.user["id"], asset_path, allow_oneboard=True)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError:
            return api_error(translate("flash.site_path_missing"), 404)
        return send_file(absolute_path, mimetype=mimetypes.guess_type(absolute_path)[0] or "application/octet-stream")

    @app.route("/api/site-manager/remote", methods=("POST",))
    @login_required
    def api_site_manager_remote_connect():
        data = request_payload()
        try:
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                require_project_permission(g.user["id"], "publish")
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
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
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
                require_project_permission(g.user["id"], "publish")
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
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
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
                require_project_permission(g.user["id"], "publish")
                sync_remote_site_to_workspace(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
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
                require_project_permission(g.user["id"], "edit")
                create_site_backup(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
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
                require_project_permission(g.user["id"], "edit")
                restore_site_backup(g.user["id"], str(data.get("backup_id") or "").strip())
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
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
                require_project_permission(g.user["id"], "edit")
                if not prompt:
                    raise ValueError(translate("flash.codex_prompt_required"))
                uploaded_asset = save_codex_suggested_image(g.user["id"], request.files.get("suggested_image"))
                image_path = selected_asset or uploaded_asset
                if selected_asset:
                    validate_asset_path(g.user["id"], selected_asset)
                selection = session.get(PREVIEW_SELECTION_KEY)
                terminal = run_site_codex_update(g.user["id"], prompt, image_path, provider=provider, model=model, selection=selection)
                session.pop(PREVIEW_SELECTION_KEY, None)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
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
                require_project_permission(g.user["id"], "edit")
                terminal = run_site_codex_update(
                    g.user["id"],
                    build_seo_page_codex_prompt(title, keyword),
                )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
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
        workspace_id = None
        if (request.args.get("scope") or "").strip().lower() == "site":
            workspace = get_current_workspace(g.user["id"])
            if not workspace:
                return jsonify({"ok": True, "images": []})
            workspace_id = workspace["id"]
        return jsonify({"ok": True, "images": list_generated_images(g.user["id"], workspace_id=workspace_id)})

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
        style_suffix = brand_image_style_suffix(current_workspace_brand(g.user["id"]))
        styled_prompt = f"{prompt} {style_suffix}" if style_suffix else prompt
        try:
            image = run_muse_image_generation(
                g.user["id"], styled_prompt, model=model, output_format=output_format
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
        record_generated_image(g.user["id"], image["filename"], prompt)
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

    @app.route("/api/social/buffer/channels")
    @login_required
    def api_social_buffer_channels():
        api_key = get_user_buffer_api_key(g.user["id"])
        if not api_key:
            return api_error(translate("social.buffer_key_required"), 400)
        try:
            channels = list_buffer_channels(api_key)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "channels": channels})

    @app.route("/api/social/buffer/posts")
    @login_required
    def api_social_buffer_history():
        return jsonify({"ok": True, "posts": to_jsonable(list_social_posts(g.user["id"]))})

    @app.route("/api/social/generate", methods=("POST",))
    @login_required
    def api_social_generate():
        data = request.get_json(silent=True) or {}
        prompt = (data.get("prompt") or "").strip()
        provider = (data.get("provider") or "").strip().lower() or None
        model = (data.get("model") or "").strip() or None
        from_site = False
        if not prompt:
            intelligence = build_site_intelligence(g.user["id"])
            if not intelligence.get("has_site"):
                return api_error(translate("social.prompt_required"), 400)
            business = (intelligence.get("brand") or {}).get("business_name") or intelligence.get(
                "site_name"
            )
            prompt = (
                f"Write an engaging post about {business or 'this business'} based on the website context."
            )
            from_site = True
        try:
            run = run_ai_text_task(g.user["id"], "social_post", prompt, provider=provider, model=model)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify(
            {"ok": True, "text": (run["response_text"] or "").strip(), "from_site": from_site}
        )

    @app.route("/api/social/suggestions")
    @login_required
    def api_social_suggestions():
        ensure_default_site_directory(g.user["id"])
        return jsonify({"ok": True, **to_jsonable(build_social_suggestions(g.user["id"]))})

    @app.route("/api/social/ideas", methods=("POST",))
    @login_required
    def api_social_ideas():
        data = request.get_json(silent=True) or {}
        hint = (data.get("hint") or data.get("prompt") or "").strip()
        provider = (data.get("provider") or "").strip().lower() or None
        model = (data.get("model") or "").strip() or None
        try:
            result = generate_social_ideas_with_ai(g.user["id"], hint=hint, provider=provider, model=model)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "ideas": result["ideas"], "provider": result["provider"]})

    @app.route("/api/social/images/upload", methods=("POST",))
    @login_required
    def api_social_image_upload():
        upload = request.files.get("image")
        try:
            if not upload or not (upload.filename or ""):
                raise ValueError(translate("flash.avatar_invalid"))
            saved = save_uploaded_image(g.user["id"], upload, social_image_directory(), "user")
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify(
            {"ok": True, "image": {"filename": saved, "url": f"/uploads/social-images/{saved}"}}
        )

    @app.route("/api/social/images/edit", methods=("POST",))
    @login_required
    def api_social_image_edit():
        data = request.get_json(silent=True) or {}
        model = (data.get("model") or "").strip() or None
        try:
            source_path = resolve_own_social_image(g.user["id"], data.get("image_url"))
        except ValueError as error:
            return api_error(str(error), 400)
        try:
            with open(source_path, "rb") as file:
                source_bytes = file.read(MAX_IMAGE_UPLOAD_BYTES + 1)
        except OSError:
            return api_error(translate("flash.image_invalid"), 400)
        if len(source_bytes) > MAX_IMAGE_UPLOAD_BYTES:
            return api_error(translate("flash.image_invalid"), 400)
        instruction = (data.get("instruction") or "").strip()
        try:
            image = run_muse_image_edit(g.user["id"], source_bytes, instruction, model=model)
        except ValueError as error:
            save_ai_run(
                g.user["id"],
                "muse",
                model or MUSE_IMAGE_DEFAULT_MODEL,
                "image_edit",
                instruction,
                status="failed",
                error_text=str(error),
            )
            return api_error(str(error), 400)
        record_generated_image(g.user["id"], image["filename"], instruction)
        return jsonify(
            {
                "ok": True,
                "image": {
                    "filename": image["filename"],
                    "url": f"/uploads/generated-images/{image['filename']}",
                    "model": image["model"],
                },
            }
        )

    @app.route("/api/social/buffer/posts", methods=("POST",))
    @login_required
    def api_social_buffer_create_post():
        data = request.get_json(silent=True) or {}
        raw_ids = data.get("channel_ids")
        if isinstance(raw_ids, list):
            channel_ids = [str(item or "").strip() for item in raw_ids if str(item or "").strip()]
        else:
            single_id = (data.get("channel_id") or "").strip()
            channel_ids = [single_id] if single_id else []
        # Preserve order, drop duplicates.
        channel_ids = list(dict.fromkeys(channel_ids))
        text = (data.get("text") or "").strip()
        prompt = (data.get("prompt") or "").strip()
        image_url = (data.get("image_url") or "").strip()
        post_type = (data.get("post_type") or "post").strip().lower()
        draft = bool(data.get("draft", False))
        publish_now = bool(data.get("publish_now", False))
        if post_type not in BUFFER_POST_TYPES:
            return api_error(translate("social.post_type_invalid"), 400)
        provider = (data.get("provider") or "").strip().lower() or None
        model = (data.get("model") or "").strip() or None
        api_key = get_user_buffer_api_key(g.user["id"])
        if not api_key:
            return api_error(translate("social.buffer_key_required"), 400)
        if not channel_ids:
            return api_error(translate("social.channel_required"), 400)
        if image_url:
            parsed_url = urllib.parse.urlparse(image_url)
            if parsed_url.scheme not in ("http", "https") or not parsed_url.netloc:
                return api_error(translate("social.image_url_invalid"), 400)
        if not text:
            if not prompt:
                return api_error(translate("social.text_required"), 400)
            try:
                run = run_ai_text_task(g.user["id"], "social_post", prompt, provider=provider, model=model)
            except ValueError as error:
                return api_error(str(error), 400)
            text = (run["response_text"] or "").strip()
            if not text:
                return api_error(translate("social.text_required"), 400)
        try:
            channels = list_buffer_channels(api_key)
        except ValueError as error:
            return api_error(str(error), 400)
        targets = []
        for channel_id in channel_ids:
            channel = next((item for item in channels if item["id"] == channel_id), None)
            if channel is None:
                return api_error(translate("social.channel_required"), 400)
            targets.append(channel)
        if draft:
            status = "draft"
        elif publish_now:
            status = "published"
        else:
            status = "queued"
        results = []
        for channel in targets:
            try:
                post = create_buffer_post(
                    api_key, channel["id"], text, draft=draft, image_url=image_url or None,
                    publish_now=publish_now, post_type=post_type,
                    channel_service=channel.get("service") or "",
                )
            except ValueError as error:
                results.append(
                    {
                        "channel_id": channel["id"],
                        "channel_name": channel["name"],
                        "ok": False,
                        "error": str(error),
                    }
                )
                continue
            record_social_post(
                g.user["id"], channel["id"], channel["name"], text, status, post["id"],
                image_url or None, post_type,
            )
            results.append(
                {
                    "channel_id": channel["id"],
                    "channel_name": channel["name"],
                    "ok": True,
                    "post": post,
                    "status": status,
                }
            )
        succeeded = sum(1 for item in results if item["ok"])
        if not succeeded:
            first_error = results[0]["error"] if results else translate("social.channel_required")
            return api_error(first_error, 400)
        body = {
            "ok": True,
            "results": results,
            "published": succeeded,
            "failed": len(results) - succeeded,
            "posts": to_jsonable(list_social_posts(g.user["id"])),
        }
        if len(results) == 1:
            body["post"] = results[0].get("post")
            body["status"] = status
        return jsonify(body)

    @app.route("/api/site-manager/assets/upload", methods=("POST",))
    @login_required
    def api_site_manager_asset_upload():
        try:
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], request.form.get("expected_directory_path"))
                require_project_permission(g.user["id"], "edit")
                upload = request.files.get("asset")
                if not upload or not upload.filename:
                    raise ValueError(translate("flash.asset_required"))
                asset_path = save_codex_suggested_image(g.user["id"], upload)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
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
            brand_context=current_workspace_brand_text(g.user["id"]),
        )
        try:
            with site_operation_lock(g.user["id"]):
                validate_expected_site_directory(g.user["id"], data.get("expected_directory_path"))
                require_project_permission(g.user["id"], "edit")
                terminal = run_site_codex_update(g.user["id"], prompt)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
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
                    require_project_permission(g.user["id"], "publish")
                    set_update_status(g.user["id"], update_id, "approved")
                elif action == "publish":
                    require_project_permission(g.user["id"], "publish")
                    try:
                        publish_site_to_remote(g.user["id"], update_id)
                    except Exception as error:
                        record_publish_alert(g.user["id"], error)
                        raise
                elif action == "restore":
                    require_project_permission(g.user["id"], "edit")
                    restore_update_files(g.user["id"], update_id)
                else:
                    raise ValueError("Unknown action.")
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
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
                require_project_permission(g.user["id"], "edit")
                delete_site_file(g.user["id"], file_path)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
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
                require_project_permission(g.user["id"], "edit")
                terminal = run_site_terminal_command(g.user["id"], (data.get("command") or "").strip())
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "terminal": terminal})

    @app.route("/site-manager/preview")
    @login_required
    def site_manager_preview_index():
        return redirect(url_for("site_manager_preview_file", filepath="index.html"))

    @app.route("/site-manager/preview/<path:filepath>")
    @login_required
    def site_manager_preview_file(filepath):
        try:
            require_project_permission(g.user["id"], "view")
            return serve_workspace_preview_file(
                g.user["id"], filepath, picker="picker" in request.args
            )
        except TeamAccessDenied:
            abort(403)
        except ValueError:
            abort(404)

    @app.route("/api/site-manager/preview/select", methods=("POST",))
    @login_required
    def api_preview_select():
        data = request_payload()
        try:
            require_project_permission(g.user["id"], "view")
            selection = clean_preview_selection(g.user["id"], data)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        session[PREVIEW_SELECTION_KEY] = selection
        return jsonify({"ok": True, "selection": selection})

    @app.route("/api/site-manager/preview/select", methods=("DELETE",))
    @login_required
    def api_preview_select_clear():
        session.pop(PREVIEW_SELECTION_KEY, None)
        return jsonify({"ok": True, "selection": None})

    @app.route("/api/site-manager/updates/<int:update_id>/compare")
    @login_required
    def api_update_compare(update_id):
        try:
            compare = build_update_compare(g.user["id"], update_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 404)
        return jsonify({"ok": True, **to_jsonable(compare)})

    @app.route("/site-manager/updates/<int:update_id>/before/<path:filepath>")
    @login_required
    def site_manager_update_before_file(update_id, filepath):
        try:
            require_project_permission(g.user["id"], "view")
            update = require_update_for_current_directory(g.user["id"], update_id)
            content = read_snapshot_member(update.get("snapshot_path"), filepath)
        except TeamAccessDenied:
            abort(403)
        except ValueError:
            abort(404)
        if content is None:
            abort(404)
        mime_type = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
        return Response(content, mimetype=mime_type)

    @app.route("/site-manager/updates/<int:update_id>/compare")
    @login_required
    def site_manager_update_compare(update_id):
        try:
            compare = build_update_compare(g.user["id"], update_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("site_manager"))
        return render_template(
            "update_compare.html",
            compare=compare,
            team_context=current_team_context(g.user["id"]),
        )

    @app.route("/api/site-manager/health")
    @login_required
    def api_site_health():
        ensure_default_site_directory(g.user["id"])
        try:
            health = get_site_health(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "health": to_jsonable(health)})

    @app.route("/api/site-manager/health/scan", methods=("POST",))
    @login_required
    def api_site_health_scan():
        ensure_default_site_directory(g.user["id"])
        data = request_payload()
        skip_external = str(data.get("skip_external") or "").strip().lower() in (
            "1", "true", "yes", "on",
        )
        try:
            with site_operation_lock(g.user["id"]):
                health = run_site_health_scan(g.user["id"], skip_external=skip_external)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "health": to_jsonable(health)})

    @app.route("/api/site-manager/health/findings/<int:finding_id>/apply", methods=("POST",))
    @login_required
    def api_site_finding_apply(finding_id):
        data = request_payload()
        try:
            with site_operation_lock(g.user["id"]):
                health = apply_site_finding(g.user["id"], finding_id, data)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify(
            {"ok": True, "health": to_jsonable(health), "manager": to_jsonable(build_site_manager(g.user["id"]))}
        )

    @app.route("/api/site-manager/health/findings/<int:finding_id>/ignore", methods=("POST",))
    @login_required
    def api_site_finding_ignore(finding_id):
        try:
            health = ignore_site_finding(g.user["id"], finding_id, ignored=True)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "health": to_jsonable(health)})

    @app.route("/api/site-manager/health/findings/<int:finding_id>/reopen", methods=("POST",))
    @login_required
    def api_site_finding_reopen(finding_id):
        try:
            health = ignore_site_finding(g.user["id"], finding_id, ignored=False)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "health": to_jsonable(health)})

    @app.route("/api/site-manager/health/fix-all", methods=("POST",))
    @login_required
    def api_site_health_fix_all():
        try:
            with site_operation_lock(g.user["id"]):
                result = apply_all_site_findings(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify(
            {
                "ok": True,
                "health": to_jsonable(result["health"]),
                "fixed": result["fixed"],
                "skipped": result["skipped"],
                "skipped_checks": result["skipped_checks"],
                "manager": to_jsonable(build_site_manager(g.user["id"])),
            }
        )

    @app.route("/api/site-manager/health/ai-fix", methods=("POST",))
    @login_required
    def api_site_health_ai_fix():
        data = request_payload()
        finding_ids = data.get("finding_ids")
        provider = (data.get("provider") or "").strip().lower() or None
        model = (data.get("model") or "").strip() or None
        try:
            with site_operation_lock(g.user["id"]):
                result = run_ai_health_fix(
                    g.user["id"], finding_ids=finding_ids, provider=provider, model=model
                )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify(
            {
                "ok": True,
                "health": to_jsonable(result["health"]),
                "fixed": result["fixed"],
                "pages": result["pages"],
                "provider": result["provider"],
                "manager": to_jsonable(build_site_manager(g.user["id"])),
            }
        )

    @app.route("/api/site-manager/health/summary", methods=("POST",))
    @login_required
    def api_site_health_summary():
        data = request_payload()
        provider = (data.get("provider") or "").strip().lower() or None
        model = (data.get("model") or "").strip() or None
        try:
            result = summarize_health_with_ai(g.user["id"], provider=provider, model=model)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "summary": result["summary"], "provider": result["provider"]})

    @app.route("/api/site-manager/intelligence")
    @login_required
    def api_site_intelligence():
        ensure_default_site_directory(g.user["id"])
        try:
            intelligence = build_site_intelligence(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "intelligence": to_jsonable(intelligence)})

    @app.route("/site-manager/health", methods=("GET", "POST"))
    @login_required
    def site_health():
        ensure_default_site_directory(g.user["id"])
        if request.method == "POST":
            skip_external = request.form.get("skip_external") == "1"
            try:
                with site_operation_lock(g.user["id"]):
                    run_site_health_scan(g.user["id"], skip_external=skip_external)
            except (TeamAccessDenied, ValueError) as error:
                flash(str(error), "warning")
            else:
                flash(translate("flash.scan_done"), "success")
            return redirect(url_for("site_health"))
        try:
            health = get_site_health(g.user["id"])
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("site_manager"))
        return render_template(
            "site_health.html", health=health, team_context=current_team_context(g.user["id"])
        )

    @app.route("/site-manager/health/findings/<int:finding_id>/apply", methods=("POST",))
    @login_required
    def site_finding_apply(finding_id):
        try:
            with site_operation_lock(g.user["id"]):
                apply_site_finding(g.user["id"], finding_id, request.form)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.finding_resolved"), "success")
        return redirect(url_for("site_health"))

    @app.route("/site-manager/health/findings/<int:finding_id>/ignore", methods=("POST",))
    @login_required
    def site_finding_ignore(finding_id):
        try:
            ignore_site_finding(g.user["id"], finding_id, ignored=True)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.finding_ignored"), "success")
        return redirect(url_for("site_health"))

    @app.route("/site-manager/health/findings/<int:finding_id>/reopen", methods=("POST",))
    @login_required
    def site_finding_reopen(finding_id):
        try:
            ignore_site_finding(g.user["id"], finding_id, ignored=False)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.finding_reopened"), "success")
        return redirect(url_for("site_health"))

    @app.route("/site-manager/health/fix-all", methods=("POST",))
    @login_required
    def site_health_fix_all():
        try:
            with site_operation_lock(g.user["id"]):
                result = apply_all_site_findings(g.user["id"])
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(
                translate("flash.fixes_applied", fixed=result["fixed"], skipped=result["skipped"]),
                "success",
            )
        return redirect(url_for("site_health"))

    @app.route("/site-manager/health/ai-fix", methods=("POST",))
    @login_required
    def site_health_ai_fix():
        try:
            with site_operation_lock(g.user["id"]):
                result = run_ai_health_fix(g.user["id"])
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.ai_fixes_applied", fixed=result["fixed"]), "success")
        return redirect(url_for("site_health"))

    @app.route("/api/site-manager/requests")
    @login_required
    def api_workspace_requests():
        ensure_default_site_directory(g.user["id"])
        try:
            links = list_request_links(g.user["id"])
            requests = list_workspace_requests(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "links": to_jsonable(links), "requests": to_jsonable(requests)})

    @app.route("/api/site-manager/request-links", methods=("POST",))
    @login_required
    def api_request_link_create():
        ensure_default_site_directory(g.user["id"])
        data = request_payload()
        try:
            link, token = create_request_link(
                g.user["id"], data.get("label", ""), data.get("expires_days")
            )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        link["url"] = url_for("portal_index", token=token, _external=True)
        return jsonify({"ok": True, "link": to_jsonable(link)})

    @app.route("/api/site-manager/request-links/<int:link_id>", methods=("DELETE",))
    @login_required
    def api_request_link_revoke(link_id):
        try:
            revoke_request_link(g.user["id"], link_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True})

    @app.route("/api/site-manager/requests/<int:request_id>")
    @login_required
    def api_request_thread(request_id):
        try:
            thread = get_agency_request_thread(g.user["id"], request_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 404)
        return jsonify({"ok": True, **to_jsonable(thread)})

    @app.route("/api/site-manager/requests/<int:request_id>/comments", methods=("POST",))
    @login_required
    def api_request_comment_create(request_id):
        data = request_payload()
        files = request.files if request.files else None
        try:
            thread = agency_add_comment(g.user["id"], request_id, data.get("body", ""), files=files)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, **to_jsonable(thread)})

    @app.route("/api/site-manager/requests/<int:request_id>/status", methods=("POST",))
    @login_required
    def api_request_status_update(request_id):
        data = request_payload()
        try:
            thread = agency_set_request_status(
                g.user["id"], request_id, data.get("status"), proposal=data.get("proposal")
            )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "request": to_jsonable(thread)})

    @app.route("/api/site-manager/requests/<int:request_id>", methods=("DELETE",))
    @login_required
    def api_request_delete(request_id):
        try:
            agency_delete_request(g.user["id"], request_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True})

    @app.route("/site-manager/requests/attachments/<filename>")
    @login_required
    def agency_request_attachment(filename):
        try:
            attachment = get_agency_attachment(g.user["id"], filename)
        except (TeamAccessDenied, ValueError):
            abort(404)
        if not attachment:
            abort(404)
        return send_from_directory(
            request_attachment_directory(),
            posixpath.basename(attachment["filename"]),
            mimetype=attachment["mime"] or "application/octet-stream",
        )

    @app.route("/site-manager/requests")
    @login_required
    def agency_requests():
        ensure_default_site_directory(g.user["id"])
        try:
            links = list_request_links(g.user["id"])
            requests = list_workspace_requests(g.user["id"])
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("site_manager"))
        return render_template(
            "requests/list.html",
            links=links,
            requests=requests,
            team_context=current_team_context(g.user["id"]),
        )

    @app.route("/site-manager/request-links", methods=("POST",))
    @login_required
    def agency_request_link_create():
        ensure_default_site_directory(g.user["id"])
        try:
            link, token = create_request_link(
                g.user["id"], request.form.get("label", ""), request.form.get("expires_days") or None
            )
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("agency_requests"))
        flash(f"{translate('flash.link_created')} {url_for('portal_index', token=token, _external=True)}", "success")
        return redirect(url_for("agency_requests"))

    @app.route("/site-manager/request-links/<int:link_id>/revoke", methods=("POST",))
    @login_required
    def agency_request_link_revoke(link_id):
        try:
            revoke_request_link(g.user["id"], link_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.link_revoked"), "success")
        return redirect(url_for("agency_requests"))

    @app.route("/site-manager/requests/<int:request_id>")
    @login_required
    def agency_request_detail(request_id):
        try:
            thread = get_agency_request_thread(g.user["id"], request_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("agency_requests"))
        return render_template(
            "requests/detail.html",
            thread=thread,
            team_context=current_team_context(g.user["id"]),
        )

    @app.route("/site-manager/requests/<int:request_id>/comments", methods=("POST",))
    @login_required
    def agency_request_comment(request_id):
        try:
            agency_add_comment(
                g.user["id"], request_id, request.form.get("body", ""),
                files=request.files if request.files else None,
            )
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.comment_added"), "success")
        return redirect(url_for("agency_request_detail", request_id=request_id))

    @app.route("/site-manager/requests/<int:request_id>/status", methods=("POST",))
    @login_required
    def agency_request_status(request_id):
        try:
            agency_set_request_status(
                g.user["id"], request_id, request.form.get("status"),
                proposal=request.form.get("proposal"),
            )
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.request_updated"), "success")
        return redirect(url_for("agency_request_detail", request_id=request_id))

    @app.route("/site-manager/requests/<int:request_id>/delete", methods=("POST",))
    @login_required
    def agency_request_delete(request_id):
        try:
            agency_delete_request(g.user["id"], request_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("agency_request_detail", request_id=request_id))
        flash(translate("flash.request_deleted"), "success")
        return redirect(url_for("agency_requests"))

    @app.route("/api/site-manager/calendar")
    @login_required
    def api_calendar_list():
        ensure_default_site_directory(g.user["id"])
        try:
            events = list_calendar_events(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "events": to_jsonable(events)})

    @app.route("/api/site-manager/calendar", methods=("POST",))
    @login_required
    def api_calendar_create():
        ensure_default_site_directory(g.user["id"])
        data = request_payload()
        try:
            with site_operation_lock(g.user["id"]):
                event = create_calendar_event(
                    g.user["id"],
                    kind=data.get("kind", "note"),
                    title=data.get("title", ""),
                    brief=data.get("brief", ""),
                    page=data.get("page", ""),
                    starts_on=data.get("starts_on", ""),
                    ends_on=data.get("ends_on", ""),
                )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "event": to_jsonable(event)})

    @app.route("/api/site-manager/calendar/<int:event_id>", methods=("POST",))
    @login_required
    def api_calendar_update(event_id):
        data = request_payload()
        try:
            with site_operation_lock(g.user["id"]):
                event = update_calendar_event(
                    g.user["id"],
                    event_id,
                    kind=data.get("kind"),
                    title=data.get("title"),
                    brief=data.get("brief"),
                    page=data.get("page"),
                    starts_on=data.get("starts_on"),
                    ends_on=data.get("ends_on"),
                )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "event": to_jsonable(event)})

    @app.route("/api/site-manager/calendar/<int:event_id>/cancel", methods=("POST",))
    @login_required
    def api_calendar_cancel(event_id):
        try:
            event = cancel_calendar_event(g.user["id"], event_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "event": to_jsonable(event)})

    @app.route("/api/site-manager/calendar/<int:event_id>", methods=("DELETE",))
    @login_required
    def api_calendar_delete(event_id):
        try:
            delete_calendar_event(g.user["id"], event_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True})

    @app.route("/api/site-manager/calendar/<int:event_id>/execute", methods=("POST",))
    @login_required
    def api_calendar_execute(event_id):
        try:
            with site_operation_lock(g.user["id"]):
                event, terminal = execute_calendar_event(g.user["id"], event_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "event": to_jsonable(event), "terminal": terminal})

    @app.route("/site-manager/calendar")
    @login_required
    def agency_calendar():
        ensure_default_site_directory(g.user["id"])
        try:
            events = list_calendar_events(g.user["id"])
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("site_manager"))
        return render_template(
            "site_calendar.html",
            events=events,
            today=date.today().isoformat(),
            team_context=current_team_context(g.user["id"]),
        )

    @app.route("/site-manager/calendar", methods=("POST",))
    @login_required
    def agency_calendar_create():
        ensure_default_site_directory(g.user["id"])
        try:
            with site_operation_lock(g.user["id"]):
                create_calendar_event(
                    g.user["id"],
                    kind=request.form.get("kind", "note"),
                    title=request.form.get("title", ""),
                    brief=request.form.get("brief", ""),
                    page=request.form.get("page", ""),
                    starts_on=request.form.get("starts_on", ""),
                    ends_on=request.form.get("ends_on", ""),
                )
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.event_created"), "success")
        return redirect(url_for("agency_calendar"))

    @app.route("/site-manager/calendar/<int:event_id>/update", methods=("POST",))
    @login_required
    def agency_calendar_update(event_id):
        try:
            with site_operation_lock(g.user["id"]):
                update_calendar_event(
                    g.user["id"],
                    event_id,
                    kind=request.form.get("kind"),
                    title=request.form.get("title"),
                    brief=request.form.get("brief"),
                    page=request.form.get("page"),
                    starts_on=request.form.get("starts_on"),
                    ends_on=request.form.get("ends_on"),
                )
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.event_updated"), "success")
        return redirect(url_for("agency_calendar"))

    @app.route("/site-manager/calendar/<int:event_id>/cancel", methods=("POST",))
    @login_required
    def agency_calendar_cancel(event_id):
        try:
            cancel_calendar_event(g.user["id"], event_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.event_cancelled"), "success")
        return redirect(url_for("agency_calendar"))

    @app.route("/site-manager/calendar/<int:event_id>/delete", methods=("POST",))
    @login_required
    def agency_calendar_delete(event_id):
        try:
            delete_calendar_event(g.user["id"], event_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.event_deleted"), "success")
        return redirect(url_for("agency_calendar"))

    @app.route("/site-manager/calendar/<int:event_id>/execute", methods=("POST",))
    @login_required
    def agency_calendar_execute(event_id):
        try:
            with site_operation_lock(g.user["id"]):
                execute_calendar_event(g.user["id"], event_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.event_executed"), "success")
        return redirect(url_for("agency_calendar"))

    @app.route("/api/site-manager/inbox")
    @login_required
    def api_inbox_list():
        ensure_default_site_directory(g.user["id"])
        try:
            messages = list_contact_messages(g.user["id"], request.args.get("status"))
            tokens = list_form_tokens(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "messages": to_jsonable(messages), "tokens": to_jsonable(tokens)})

    @app.route("/api/site-manager/inbox/token", methods=("POST",))
    @login_required
    def api_form_token_create():
        ensure_default_site_directory(g.user["id"])
        data = request_payload()
        try:
            _token_row, token = create_form_token(g.user["id"], data.get("label", ""))
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        submit_url = url_for("public_form_submit", token=token, _external=True)
        return jsonify({"ok": True, "token": token, "submit_url": submit_url})

    @app.route("/api/site-manager/inbox/token/<int:token_id>", methods=("DELETE",))
    @login_required
    def api_form_token_revoke(token_id):
        try:
            revoke_form_token(g.user["id"], token_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True})

    @app.route("/api/site-manager/inbox/snippet")
    @login_required
    def api_inbox_snippet():
        ensure_default_site_directory(g.user["id"])
        try:
            token_row = latest_form_token(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        if not token_row:
            return api_error(translate("flash.message_not_found"), 404)
        submit_url = url_for("public_form_submit", token=token_row["token"], _external=True)
        return jsonify({"ok": True, "snippet": build_form_snippet(submit_url)})

    @app.route("/api/site-manager/inbox/<int:message_id>/attend", methods=("POST",))
    @login_required
    def api_inbox_attend(message_id):
        try:
            message = set_contact_message_status(g.user["id"], message_id, "attended")
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "message": to_jsonable(message)})

    @app.route("/api/site-manager/inbox/<int:message_id>/reopen", methods=("POST",))
    @login_required
    def api_inbox_reopen(message_id):
        try:
            message = set_contact_message_status(g.user["id"], message_id, "new")
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "message": to_jsonable(message)})

    @app.route("/api/site-manager/inbox/<int:message_id>", methods=("DELETE",))
    @login_required
    def api_inbox_delete(message_id):
        try:
            delete_contact_message(g.user["id"], message_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True})

    @app.route("/site-manager/inbox")
    @login_required
    def agency_inbox():
        ensure_default_site_directory(g.user["id"])
        status = request.args.get("status", "")
        try:
            messages = list_contact_messages(g.user["id"], status or None)
            tokens = list_form_tokens(g.user["id"])
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("site_manager"))
        return render_template(
            "site_inbox.html",
            messages=messages,
            tokens=tokens,
            status=status,
            team_context=current_team_context(g.user["id"]),
        )

    @app.route("/site-manager/form-tokens", methods=("POST",))
    @login_required
    def agency_form_token_create():
        ensure_default_site_directory(g.user["id"])
        try:
            _token_row, token = create_form_token(g.user["id"], request.form.get("label", ""))
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(f"{translate('flash.token_created')} {url_for('public_form_submit', token=token, _external=True)}", "success")
        return redirect(url_for("agency_inbox"))

    @app.route("/site-manager/form-tokens/<int:token_id>/revoke", methods=("POST",))
    @login_required
    def agency_form_token_revoke(token_id):
        try:
            revoke_form_token(g.user["id"], token_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.token_revoked"), "success")
        return redirect(url_for("agency_inbox"))

    @app.route("/site-manager/inbox/<int:message_id>/attend", methods=("POST",))
    @login_required
    def agency_inbox_attend(message_id):
        try:
            set_contact_message_status(g.user["id"], message_id, "attended")
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.message_attended"), "success")
        return redirect(url_for("agency_inbox"))

    @app.route("/site-manager/inbox/<int:message_id>/reopen", methods=("POST",))
    @login_required
    def agency_inbox_reopen(message_id):
        try:
            set_contact_message_status(g.user["id"], message_id, "new")
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.message_reopened"), "success")
        return redirect(url_for("agency_inbox"))

    @app.route("/site-manager/inbox/<int:message_id>/delete", methods=("POST",))
    @login_required
    def agency_inbox_delete(message_id):
        try:
            delete_contact_message(g.user["id"], message_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.message_deleted"), "success")
        return redirect(url_for("agency_inbox"))

    @app.route("/forms/<token>/submit", methods=("POST", "OPTIONS"))
    def public_form_submit(token):
        if request.method == "OPTIONS":
            response = jsonify({"ok": True})
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "POST, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
            return response
        if request.is_json:
            fields = request.get_json(silent=True) or {}
        else:
            fields = request.form.to_dict()
        try:
            message = submit_contact_message(token, request.remote_addr, fields)
        except FormRateLimited as error:
            response = jsonify({"ok": False, "error": str(error)})
            response.status_code = 429
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response
        except ValueError as error:
            response = jsonify({"ok": False, "error": str(error)})
            response.status_code = 400
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response
        if message is None:
            response = jsonify({"ok": False, "error": translate("flash.message_not_found")})
            response.status_code = 404
            response.headers["Access-Control-Allow-Origin"] = "*"
            return response
        response = jsonify({"ok": True})
        response.headers["Access-Control-Allow-Origin"] = "*"
        return response

    @app.route("/api/site-manager/alerts")
    @login_required
    def api_alerts_list():
        ensure_default_site_directory(g.user["id"])
        try:
            rules = list_alert_rules(g.user["id"])
            alerts = list_site_alerts(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "rules": to_jsonable(rules), "alerts": to_jsonable(alerts)})

    @app.route("/api/site-manager/alerts/rules", methods=("POST",))
    @login_required
    def api_alert_rule_create():
        ensure_default_site_directory(g.user["id"])
        data = request_payload()
        try:
            rule = create_alert_rule(
                g.user["id"],
                kind=data.get("kind", "uptime"),
                target=data.get("target", ""),
                name=data.get("name", ""),
                threshold_days=data.get("threshold_days", 14),
            )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "rule": to_jsonable(rule)})

    @app.route("/api/site-manager/alerts/rules/<int:rule_id>", methods=("POST",))
    @login_required
    def api_alert_rule_update(rule_id):
        data = request_payload()
        try:
            rule = update_alert_rule(
                g.user["id"],
                rule_id,
                name=data.get("name"),
                enabled=data.get("enabled"),
                threshold_days=data.get("threshold_days"),
            )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "rule": to_jsonable(rule)})

    @app.route("/api/site-manager/alerts/rules/<int:rule_id>", methods=("DELETE",))
    @login_required
    def api_alert_rule_delete(rule_id):
        try:
            delete_alert_rule(g.user["id"], rule_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True})

    @app.route("/api/site-manager/alerts/check", methods=("POST",))
    @login_required
    def api_alerts_check():
        ensure_default_site_directory(g.user["id"])
        try:
            result = run_site_alert_checks(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, **to_jsonable(result)})

    @app.route("/api/site-manager/alerts/<int:alert_id>/ack", methods=("POST",))
    @login_required
    def api_alert_ack(alert_id):
        try:
            result = set_site_alert_status(g.user["id"], alert_id, "acked")
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, **to_jsonable(result)})

    @app.route("/api/site-manager/alerts/<int:alert_id>/resolve", methods=("POST",))
    @login_required
    def api_alert_resolve(alert_id):
        try:
            result = set_site_alert_status(g.user["id"], alert_id, "resolved")
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, **to_jsonable(result)})

    @app.route("/api/site-manager/alerts/<int:alert_id>/reopen", methods=("POST",))
    @login_required
    def api_alert_reopen(alert_id):
        try:
            result = set_site_alert_status(g.user["id"], alert_id, "open")
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, **to_jsonable(result)})

    @app.route("/site-manager/alerts")
    @login_required
    def agency_alerts():
        ensure_default_site_directory(g.user["id"])
        try:
            rules = list_alert_rules(g.user["id"])
            alerts = list_site_alerts(g.user["id"])
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("site_manager"))
        return render_template(
            "site_alerts.html",
            rules=rules,
            alerts=alerts,
            team_context=current_team_context(g.user["id"]),
        )

    @app.route("/site-manager/alert-rules", methods=("POST",))
    @login_required
    def agency_alert_rule_create():
        ensure_default_site_directory(g.user["id"])
        try:
            create_alert_rule(
                g.user["id"],
                kind=request.form.get("kind", "uptime"),
                target=request.form.get("target", ""),
                name=request.form.get("name", ""),
                threshold_days=request.form.get("threshold_days", 14),
            )
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.rule_created"), "success")
        return redirect(url_for("agency_alerts"))

    @app.route("/site-manager/alert-rules/<int:rule_id>/update", methods=("POST",))
    @login_required
    def agency_alert_rule_update(rule_id):
        try:
            update_alert_rule(
                g.user["id"],
                rule_id,
                name=request.form.get("name"),
                enabled=request.form.get("enabled"),
                threshold_days=request.form.get("threshold_days"),
            )
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.rule_updated"), "success")
        return redirect(url_for("agency_alerts"))

    @app.route("/site-manager/alert-rules/<int:rule_id>/delete", methods=("POST",))
    @login_required
    def agency_alert_rule_delete(rule_id):
        try:
            delete_alert_rule(g.user["id"], rule_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.rule_deleted"), "success")
        return redirect(url_for("agency_alerts"))

    @app.route("/site-manager/alerts/check", methods=("POST",))
    @login_required
    def agency_alerts_check():
        ensure_default_site_directory(g.user["id"])
        try:
            run_site_alert_checks(g.user["id"])
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.check_done"), "success")
        return redirect(url_for("agency_alerts"))

    @app.route("/site-manager/alerts/<int:alert_id>/status", methods=("POST",))
    @login_required
    def agency_alert_status(alert_id):
        try:
            set_site_alert_status(g.user["id"], alert_id, request.form.get("status"))
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.alert_updated"), "success")
        return redirect(url_for("agency_alerts"))

    @app.route("/api/site-manager/reports")
    @login_required
    def api_reports_list():
        ensure_default_site_directory(g.user["id"])
        period = request.args.get("period") or date.today().isoformat()[:7]
        try:
            workspace = require_current_request_workspace(g.user["id"])
            report = build_site_report(g.user["id"], workspace, period)
            links = list_site_report_links(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "report": to_jsonable(report), "links": to_jsonable(links)})

    @app.route("/api/site-manager/reports", methods=("POST",))
    @login_required
    def api_report_link_create():
        ensure_default_site_directory(g.user["id"])
        data = request_payload()
        try:
            link, token = create_site_report_link(
                g.user["id"], data.get("period") or date.today().isoformat()[:7], data.get("title", "")
            )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        link["url"] = url_for("public_site_report", token=token, _external=True)
        return jsonify({"ok": True, "link": to_jsonable(link)})

    @app.route("/api/site-manager/reports/<int:link_id>")
    @login_required
    def api_report_detail(link_id):
        ensure_default_site_directory(g.user["id"])
        try:
            report = get_site_report(g.user["id"], link_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 404)
        return jsonify({"ok": True, "report": to_jsonable(report)})

    @app.route("/api/site-manager/reports/<int:link_id>", methods=("DELETE",))
    @login_required
    def api_report_link_revoke(link_id):
        try:
            revoke_site_report_link(g.user["id"], link_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True})

    @app.route("/site-manager/reports")
    @login_required
    def agency_reports():
        ensure_default_site_directory(g.user["id"])
        period = request.args.get("period") or date.today().isoformat()[:7]
        try:
            workspace = require_current_request_workspace(g.user["id"])
            report = build_site_report(g.user["id"], workspace, period)
            links = list_site_report_links(g.user["id"])
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("site_manager"))
        return render_template(
            "site_reports.html",
            report=report,
            links=links,
            team_context=current_team_context(g.user["id"]),
        )

    @app.route("/site-manager/reports", methods=("POST",))
    @login_required
    def agency_report_link_create():
        ensure_default_site_directory(g.user["id"])
        try:
            _link, token = create_site_report_link(
                g.user["id"],
                request.form.get("period") or date.today().isoformat()[:7],
                request.form.get("title", ""),
            )
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(f"{translate('flash.report_created')} {url_for('public_site_report', token=token, _external=True)}", "success")
        return redirect(url_for("agency_reports"))

    @app.route("/site-manager/reports/<int:link_id>/revoke", methods=("POST",))
    @login_required
    def agency_report_link_revoke(link_id):
        try:
            revoke_site_report_link(g.user["id"], link_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.report_revoked"), "success")
        return redirect(url_for("agency_reports"))

    @app.route("/reports/<token>")
    def public_site_report(token):
        link = get_site_report_link(token)
        if not link:
            abort(404)
        report = build_public_site_report(link)
        if request.args.get("format") == "json":
            return jsonify({"ok": True, "report": to_jsonable(report)})
        return render_template("public_report.html", report=report)

    @app.route("/api/notifications")
    @login_required
    def api_notifications_list():
        notifications = list_notifications(g.user["id"])
        return jsonify(
            {
                "ok": True,
                "notifications": to_jsonable(notifications),
                "unread_count": count_unread_notifications(g.user["id"]),
            }
        )

    @app.route("/api/notifications/<int:notification_id>/read", methods=("POST",))
    @login_required
    def api_notification_read(notification_id):
        try:
            mark_notification_read(g.user["id"], notification_id)
        except ValueError as error:
            return api_error(str(error), 404)
        return jsonify({"ok": True, "unread_count": count_unread_notifications(g.user["id"])})

    @app.route("/api/notifications/read-all", methods=("POST",))
    @login_required
    def api_notifications_read_all():
        mark_all_notifications_read(g.user["id"])
        return jsonify({"ok": True, "unread_count": 0})

    @app.route("/notifications")
    @login_required
    def notifications_page():
        return render_template(
            "notifications.html",
            notifications=list_notifications(g.user["id"]),
            unread_count=count_unread_notifications(g.user["id"]),
        )

    @app.route("/notifications/<int:notification_id>/read", methods=("POST",))
    @login_required
    def notifications_mark_read(notification_id):
        try:
            mark_notification_read(g.user["id"], notification_id)
        except ValueError as error:
            flash(str(error), "warning")
        return redirect(url_for("notifications_page"))

    @app.route("/notifications/read-all", methods=("POST",))
    @login_required
    def notifications_mark_all_read():
        mark_all_notifications_read(g.user["id"])
        return redirect(url_for("notifications_page"))

    @app.route("/r/<token>")
    def portal_index(token):
        link = get_client_link(token)
        if not link:
            return render_template("portal/invalid.html"), 404
        return render_template(
            "portal/index.html", link=link, token=token, requests=list_link_requests(link)
        )

    @app.route("/r/<token>/preview/<path:filepath>")
    def portal_preview_file(token, filepath):
        link = get_client_link(token)
        if not link:
            abort(404)
        response = serve_link_preview_file(link, filepath, picker="picker" in request.args)
        if response is None:
            abort(404)
        return response

    @app.route("/r/<token>/requests", methods=("POST",))
    def portal_request_create(token):
        link = get_client_link(token)
        if not link:
            return api_error(translate("portal.invalid_link"), 404)
        try:
            thread = create_client_request(link, request.form, request.files)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "request": to_jsonable(thread)})

    @app.route("/r/<token>/requests/<int:request_id>")
    def portal_request_detail(token, request_id):
        link = get_client_link(token)
        if not link:
            return render_template("portal/invalid.html"), 404
        thread = get_portal_request_thread(link, request_id)
        if not thread:
            return render_template("portal/invalid.html"), 404
        return render_template("portal/thread.html", link=link, token=token, thread=thread)

    @app.route("/r/<token>/requests/<int:request_id>/comments", methods=("POST",))
    def portal_comment_create(token, request_id):
        link = get_client_link(token)
        if not link:
            return api_error(translate("portal.invalid_link"), 404)
        try:
            thread = portal_add_comment(
                link, request_id, request.form.get("client_name", ""),
                request.form.get("body", ""), files=request.files if request.files else None,
            )
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "request": to_jsonable(thread)})

    @app.route("/r/<token>/requests/<int:request_id>/approve", methods=("POST",))
    def portal_request_approve(token, request_id):
        link = get_client_link(token)
        if not link:
            return api_error(translate("portal.invalid_link"), 404)
        try:
            thread = portal_decide_request(link, request_id, "approved")
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "request": to_jsonable(thread)})

    @app.route("/r/<token>/requests/<int:request_id>/reject", methods=("POST",))
    def portal_request_reject(token, request_id):
        link = get_client_link(token)
        if not link:
            return api_error(translate("portal.invalid_link"), 404)
        try:
            thread = portal_decide_request(link, request_id, "rejected")
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "request": to_jsonable(thread)})

    @app.route("/r/<token>/attachments/<filename>")
    def portal_attachment(token, filename):
        link = get_client_link(token)
        if not link:
            abort(404)
        attachment = get_portal_attachment(link, filename)
        if not attachment:
            abort(404)
        return send_from_directory(
            request_attachment_directory(),
            posixpath.basename(attachment["filename"]),
            mimetype=attachment["mime"] or "application/octet-stream",
        )

    @app.route("/api/site-manager/site")
    @login_required
    def api_site_settings():
        ensure_default_site_directory(g.user["id"])
        try:
            site = get_site_settings(g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "site": to_jsonable(site)})

    @app.route("/api/site-manager/site", methods=("POST",))
    @login_required
    def api_site_settings_update():
        ensure_default_site_directory(g.user["id"])
        data = request_payload()
        try:
            with site_operation_lock(g.user["id"]):
                site = update_site_settings(
                    g.user["id"],
                    display_name=data.get("display_name"),
                    client_name=data.get("client_name"),
                    brand=data.get("brand"),
                    gsc_property=data.get("gsc_property"),
                )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "site": to_jsonable(site)})

    @app.route("/api/site-manager/site/logo", methods=("POST",))
    @login_required
    def api_site_logo_upload():
        ensure_default_site_directory(g.user["id"])
        try:
            with site_operation_lock(g.user["id"]):
                site = save_site_logo(g.user["id"], request.files.get("logo"))
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "site": to_jsonable(site)})

    @app.route("/site-manager/site", methods=("GET", "POST"))
    @login_required
    def site_settings():
        ensure_default_site_directory(g.user["id"])
        if request.method == "POST":
            form = request.form
            brand = {
                "business_name": form.get("brand_business_name", ""),
                "tagline": form.get("brand_tagline", ""),
                "services": form.get("brand_services", ""),
                "audience": form.get("brand_audience", ""),
                "tone": form.get("brand_tone", ""),
                "colors": {
                    "primary": form.get("brand_color_primary", ""),
                    "secondary": form.get("brand_color_secondary", ""),
                    "accent": form.get("brand_color_accent", ""),
                },
                "fonts": {
                    "headings": form.get("brand_font_headings", ""),
                    "body": form.get("brand_font_body", ""),
                },
                "phone": form.get("brand_phone", ""),
                "email": form.get("brand_email", ""),
                "address": form.get("brand_address", ""),
                "website": form.get("brand_website", ""),
                "notes": form.get("brand_notes", ""),
            }
            try:
                with site_operation_lock(g.user["id"]):
                    update_site_settings(
                        g.user["id"],
                        display_name=form.get("display_name"),
                        client_name=form.get("client_name"),
                        brand=brand,
                        gsc_property=form.get("gsc_property"),
                    )
            except (TeamAccessDenied, ValueError) as error:
                flash(str(error), "warning")
            else:
                flash(translate("flash.site_saved"), "success")
            return redirect(url_for("site_settings"))
        try:
            site = get_site_settings(g.user["id"])
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("site_manager"))
        gsc = build_search_console_dashboard(g.user["id"])
        return render_template("site_settings.html", site=site, gsc=gsc)

    @app.route("/site-manager/site/logo", methods=("POST",))
    @login_required
    def site_logo_upload():
        ensure_default_site_directory(g.user["id"])
        try:
            with site_operation_lock(g.user["id"]):
                save_site_logo(g.user["id"], request.files.get("logo"))
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.logo_saved"), "success")
        return redirect(url_for("site_settings"))

    @app.route("/api/teams")
    @login_required
    def api_teams_list():
        return jsonify(
            {
                "ok": True,
                "teams": to_jsonable(get_user_teams(g.user["id"])),
                "pending_invites": to_jsonable(get_user_pending_invites(g.user["id"])),
            }
        )

    @app.route("/api/teams", methods=("POST",))
    @login_required
    def api_teams_create():
        data = request_payload()
        try:
            team = create_team(
                g.user["id"], data.get("name", ""), data.get("description", "")
            )
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "team": to_jsonable(team)})

    @app.route("/api/teams/<int:team_id>")
    @login_required
    def api_team_detail(team_id):
        try:
            team, membership = require_team_membership(team_id, g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 404)
        return jsonify(
            {
                "ok": True,
                "team": to_jsonable(serialize_team(team, membership)),
                "members": to_jsonable(get_team_members(team["id"])),
                "invites": to_jsonable(get_pending_team_invites(team["id"])),
                "projects": to_jsonable(get_team_projects(team["id"])),
            }
        )

    @app.route("/api/teams/<int:team_id>", methods=("POST",))
    @login_required
    def api_team_update(team_id):
        data = request_payload()
        try:
            team = update_team(
                team_id,
                g.user["id"],
                name=data.get("name"),
                description=data.get("description"),
            )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "team": to_jsonable(team)})

    @app.route("/api/teams/<int:team_id>", methods=("DELETE",))
    @login_required
    def api_team_delete(team_id):
        try:
            delete_team(team_id, g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 404)
        return jsonify({"ok": True})

    @app.route("/api/teams/<int:team_id>/invites", methods=("POST",))
    @login_required
    def api_team_invite_create(team_id):
        data = request_payload()
        try:
            invite, token = invite_team_member(
                team_id, g.user["id"], data.get("email", ""), data.get("role", "editor")
            )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        invite_link = url_for("team_invite_landing", token=token, _external=True)
        email_sent = True
        try:
            team = require_team(team_id)
            send_team_invite_email(team["name"], invite["email"], invite_link)
        except ValueError:
            email_sent = False
        return jsonify(
            {
                "ok": True,
                "invite": to_jsonable(invite),
                "invite_link": invite_link,
                "email_sent": email_sent,
            }
        )

    @app.route("/api/teams/<int:team_id>/invites/<int:invite_id>", methods=("DELETE",))
    @login_required
    def api_team_invite_revoke(team_id, invite_id):
        try:
            revoke_team_invite(team_id, g.user["id"], invite_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True})

    @app.route("/api/teams/invites/accept", methods=("POST",))
    @login_required
    def api_team_invite_accept():
        data = request_payload()
        try:
            team = accept_team_invite((data.get("token") or "").strip(), g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "team": to_jsonable(team)})

    @app.route("/api/teams/invites/<int:invite_id>/accept", methods=("POST",))
    @login_required
    def api_team_invite_accept_by_id(invite_id):
        try:
            team = accept_team_invite_by_id(invite_id, g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "team": to_jsonable(team)})

    @app.route("/api/teams/<int:team_id>/members/<int:user_id>", methods=("POST",))
    @login_required
    def api_team_member_update(team_id, user_id):
        data = request_payload()
        try:
            members = update_team_member(
                team_id,
                g.user["id"],
                user_id,
                role=data.get("role"),
                permissions=data.get("permissions"),
            )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "members": to_jsonable(members)})

    @app.route("/api/teams/<int:team_id>/members/<int:user_id>", methods=("DELETE",))
    @login_required
    def api_team_member_remove(team_id, user_id):
        try:
            members = remove_team_member(team_id, g.user["id"], user_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "members": to_jsonable(members)})

    @app.route("/api/teams/<int:team_id>/leave", methods=("POST",))
    @login_required
    def api_team_leave(team_id):
        try:
            leave_team(team_id, g.user["id"])
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True})

    @app.route("/api/teams/<int:team_id>/transfer", methods=("POST",))
    @login_required
    def api_team_transfer(team_id):
        data = request_payload()
        try:
            members = transfer_team_ownership(team_id, g.user["id"], data.get("user_id"))
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "members": to_jsonable(members)})

    @app.route("/api/teams/<int:team_id>/projects", methods=("POST",))
    @login_required
    def api_team_project_add(team_id):
        data = request_payload()
        try:
            with site_operation_lock(g.user["id"]):
                project = add_team_project(
                    team_id, g.user["id"], project_id=data.get("project_id"), path=data.get("path")
                )
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True, "project": to_jsonable(project)})

    @app.route("/api/teams/<int:team_id>/projects/<int:project_id>", methods=("DELETE",))
    @login_required
    def api_team_project_remove(team_id, project_id):
        try:
            with site_operation_lock(g.user["id"]):
                remove_team_project(team_id, g.user["id"], project_id)
        except TeamAccessDenied as error:
            return api_error(str(error), 403)
        except ValueError as error:
            return api_error(str(error), 400)
        return jsonify({"ok": True})

    @app.route("/teams", methods=("GET", "POST"))
    @login_required
    def teams_list():
        if request.method == "POST":
            try:
                team = create_team(
                    g.user["id"],
                    request.form.get("name", ""),
                    request.form.get("description", ""),
                )
            except ValueError as error:
                flash(str(error), "warning")
                return redirect(url_for("teams_list"))
            flash(translate("flash.team_created"), "success")
            return redirect(url_for("team_detail", team_id=team["id"]))
        return render_template(
            "teams/list.html",
            teams=get_user_teams(g.user["id"]),
            pending_invites=get_user_pending_invites(g.user["id"]),
        )

    @app.route("/teams/<int:team_id>")
    @login_required
    def team_detail(team_id):
        try:
            team, membership = require_team_membership(team_id, g.user["id"])
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("teams_list"))
        personal_projects = [item for item in list_site_projects(g.user["id"]) if item["scope"] == "personal"]
        return render_template(
            "teams/detail.html",
            team=serialize_team(team, membership),
            members=get_team_members(team["id"]),
            invites=get_pending_team_invites(team["id"]),
            projects=get_team_projects(team["id"]),
            personal_projects=personal_projects,
            permissions=TEAM_PERMISSIONS,
            invite_roles=TEAM_INVITE_ROLES,
            member_roles=TEAM_MEMBER_ROLES,
        )

    @app.route("/teams/<int:team_id>/update", methods=("POST",))
    @login_required
    def team_update(team_id):
        try:
            update_team(
                team_id,
                g.user["id"],
                name=request.form.get("name"),
                description=request.form.get("description"),
            )
        except TeamAccessDenied as error:
            flash(str(error), "warning")
        except ValueError as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.team_updated"), "success")
        return redirect(url_for("team_detail", team_id=team_id))

    @app.route("/teams/<int:team_id>/delete", methods=("POST",))
    @login_required
    def team_delete(team_id):
        try:
            delete_team(team_id, g.user["id"])
        except TeamAccessDenied as error:
            flash(str(error), "warning")
            return redirect(url_for("team_detail", team_id=team_id))
        except ValueError as error:
            flash(str(error), "warning")
            return redirect(url_for("teams_list"))
        flash(translate("flash.team_deleted"), "success")
        return redirect(url_for("teams_list"))

    @app.route("/teams/<int:team_id>/invites", methods=("POST",))
    @login_required
    def team_invite_create(team_id):
        try:
            invite, token = invite_team_member(
                team_id, g.user["id"], request.form.get("email", ""), request.form.get("role", "editor")
            )
        except TeamAccessDenied as error:
            flash(str(error), "warning")
            return redirect(url_for("team_detail", team_id=team_id))
        except ValueError as error:
            flash(str(error), "warning")
            return redirect(url_for("team_detail", team_id=team_id))
        invite_link = url_for("team_invite_landing", token=token, _external=True)
        try:
            team = require_team(team_id)
            send_team_invite_email(team["name"], invite["email"], invite_link)
        except ValueError:
            flash(f"{translate('flash.invite_link_ready')} {invite_link}", "info")
        else:
            flash(translate("flash.invite_sent"), "success")
        return redirect(url_for("team_detail", team_id=team_id))

    @app.route("/teams/<int:team_id>/invites/<int:invite_id>/revoke", methods=("POST",))
    @login_required
    def team_invite_revoke(team_id, invite_id):
        try:
            revoke_team_invite(team_id, g.user["id"], invite_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.invite_revoked"), "success")
        return redirect(url_for("team_detail", team_id=team_id))

    @app.route("/teams/invites/<token>")
    def team_invite_landing(token):
        invite = get_valid_team_invite(token)
        if not invite:
            flash(translate("flash.invite_invalid"), "warning")
            return redirect(url_for("teams_list" if g.user else "login"))
        return render_template("teams/invite.html", invite=invite)

    @app.route("/teams/invites/<token>/accept", methods=("POST",))
    @login_required
    def team_invite_accept_token(token):
        try:
            team = accept_team_invite(token, g.user["id"])
        except TeamAccessDenied as error:
            flash(str(error), "warning")
            return redirect(url_for("team_invite_landing", token=token))
        except ValueError as error:
            flash(str(error), "warning")
            return redirect(url_for("teams_list"))
        flash(translate("flash.invite_accepted"), "success")
        return redirect(url_for("team_detail", team_id=team["id"]))

    @app.route("/teams/invites/<int:invite_id>/accept", methods=("POST",))
    @login_required
    def team_invite_accept_id(invite_id):
        try:
            team = accept_team_invite_by_id(invite_id, g.user["id"])
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("teams_list"))
        flash(translate("flash.invite_accepted"), "success")
        return redirect(url_for("team_detail", team_id=team["id"]))

    @app.route("/teams/<int:team_id>/members/<int:user_id>/update", methods=("POST",))
    @login_required
    def team_member_update(team_id, user_id):
        selected = {key for key in TEAM_PERMISSIONS if request.form.get(f"perm_{key}") == "1"}
        selected.add("view")
        permissions = {key: key in selected for key in TEAM_PERMISSIONS}
        try:
            update_team_member(
                team_id, g.user["id"], user_id,
                role=request.form.get("role"), permissions=permissions,
            )
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.member_updated"), "success")
        return redirect(url_for("team_detail", team_id=team_id))

    @app.route("/teams/<int:team_id>/members/<int:user_id>/remove", methods=("POST",))
    @login_required
    def team_member_remove(team_id, user_id):
        try:
            remove_team_member(team_id, g.user["id"], user_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.member_removed"), "success")
        return redirect(url_for("team_detail", team_id=team_id))

    @app.route("/teams/<int:team_id>/leave", methods=("POST",))
    @login_required
    def team_leave(team_id):
        try:
            leave_team(team_id, g.user["id"])
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
            return redirect(url_for("team_detail", team_id=team_id))
        flash(translate("flash.left_team"), "success")
        return redirect(url_for("teams_list"))

    @app.route("/teams/<int:team_id>/transfer", methods=("POST",))
    @login_required
    def team_transfer(team_id):
        try:
            transfer_team_ownership(team_id, g.user["id"], request.form.get("user_id"))
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.ownership_transferred"), "success")
        return redirect(url_for("team_detail", team_id=team_id))

    @app.route("/teams/<int:team_id>/projects", methods=("POST",))
    @login_required
    def team_project_add(team_id):
        try:
            with site_operation_lock(g.user["id"]):
                add_team_project(
                    team_id,
                    g.user["id"],
                    project_id=request.form.get("project_id") or None,
                    path=request.form.get("path") or None,
                )
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.team_project_added"), "success")
        return redirect(url_for("team_detail", team_id=team_id))

    @app.route("/teams/<int:team_id>/projects/<int:project_id>/remove", methods=("POST",))
    @login_required
    def team_project_remove(team_id, project_id):
        try:
            with site_operation_lock(g.user["id"]):
                remove_team_project(team_id, g.user["id"], project_id)
        except (TeamAccessDenied, ValueError) as error:
            flash(str(error), "warning")
        else:
            flash(translate("flash.team_project_removed"), "success")
        return redirect(url_for("team_detail", team_id=team_id))

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
                    "suggested_uris": suggested_google_redirect_uris(),
                },
            }
        )

    @app.route("/api/settings/google/diagnostics")
    @login_required
    def api_settings_google_diagnostics():
        uris = suggested_google_redirect_uris()
        return jsonify(
            {"ok": True, "checks": [diagnose_google_redirect_uri(uri) for uri in uris]}
        )

    @app.route("/api/settings/account", methods=("POST",))
    @login_required
    def api_settings_account():
        data = request_payload()
        user = get_user_account(g.user["id"])
        name = (data.get("name") or user["name"]).strip()
        email = (data.get("email") or user["email"]).strip().lower()
        company_name = (data.get("company_name") or user["company_name"] or "").strip()
        company_email = (data.get("company_email") or user["company_email"] or "").strip()
        company_website = (data.get("company_website") or user["company_website"] or "").strip()
        buffer_api_key = (data.get("buffer_api_key") or "").strip()
        new_password = data.get("new_password") or ""
        confirm_password = data.get("confirm_password") or ""
        current_password = data.get("current_password") or ""

        if not name:
            return api_error(translate("flash.name_required"), 400)
        if not email or "@" not in email:
            return api_error(translate("flash.email_invalid"), 400)
        changing_sensitive_fields = email != user["email"] or bool(new_password)
        if changing_sensitive_fields and not verify_password(user["password_hash"], current_password):
            return api_error(translate("flash.current_password_invalid"), 401)
        if new_password or confirm_password:
            if len(new_password) < 8 or new_password != confirm_password:
                return api_error(translate("flash.password_update_mismatch"), 400)

        avatar_path = user["avatar_path"]
        avatar = request.files.get("avatar")
        if avatar and avatar.filename:
            try:
                avatar_path = save_uploaded_image(g.user["id"], avatar, AVATAR_DIR, "user")
            except ValueError as error:
                return api_error(str(error), 400)

        company_logo_path = user["company_logo_path"]
        company_logo = request.files.get("company_logo")
        if company_logo and company_logo.filename:
            try:
                company_logo_path = save_uploaded_image(
                    g.user["id"], company_logo, COMPANY_LOGO_DIR, "company"
                )
            except ValueError as error:
                return api_error(str(error), 400)

        password_hash = hash_password(new_password) if new_password else user["password_hash"]
        try:
            execute_db(
                """
                UPDATE users
                SET name = ?, email = ?, password_hash = ?, avatar_path = ?,
                    company_name = ?, company_email = ?, company_website = ?,
                    company_logo_path = ?,
                    buffer_api_key = COALESCE(NULLIF(?, ''), buffer_api_key)
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
                    buffer_api_key,
                    g.user["id"],
                ),
            )
        except sqlite3.IntegrityError:
            return api_error(translate("flash.account_exists"), 400)
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

    @app.route("/social")
    @login_required
    def social():
        return render_template(
            "social.html",
            buffer_configured=bool(get_user_buffer_api_key(g.user["id"])),
        )

    @app.route("/help")
    @login_required
    def help_page():
        return render_template("help.html")

    @app.route("/site-manager")
    @login_required
    def site_manager():
        ensure_default_site_directory(g.user["id"])
        manager = build_site_manager(g.user["id"])
        tab = (request.args.get("tab") or "studio").strip().lower()
        if tab not in ("studio", "files", "remote", "preview"):
            tab = "studio"
        return render_template("site_manager.html", manager=manager, terminal=None, command="", tab=tab)

    @app.route("/site-manager/connect", methods=("POST",))
    @login_required
    def site_manager_connect():
        path = request.form.get("path", "").strip()
        project_id = request.form.get("project_id", "").strip()
        try:
            if project_id:
                connect_site_project(g.user["id"], project_id=project_id)
            elif path:
                connect_site_project(g.user["id"], path=path)
            else:
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
            require_project_permission(g.user["id"], "publish")
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
            require_project_permission(g.user["id"], "publish")
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
            require_project_permission(g.user["id"], "edit")
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
            require_project_permission(g.user["id"], "view")
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
            require_project_permission(g.user["id"], "edit")
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
            require_project_permission(g.user["id"], "edit")
            if not prompt:
                raise ValueError(translate("flash.codex_prompt_required"))
            image_path = selected_asset or save_codex_suggested_image(g.user["id"], suggested_image)
            if selected_asset:
                validate_asset_path(g.user["id"], selected_asset)
            selection = session.get(PREVIEW_SELECTION_KEY)
            terminal = run_site_codex_update(g.user["id"], prompt, image_path, selection=selection)
            session.pop(PREVIEW_SELECTION_KEY, None)
        except ValueError as error:
            flash(str(error), "warning")

        manager = build_site_manager(g.user["id"])
        return render_template("site_manager.html", manager=manager, terminal=terminal, command="")

    @app.route("/site-manager/assets/upload", methods=("POST",))
    @login_required
    def site_manager_asset_upload():
        try:
            require_project_permission(g.user["id"], "edit")
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
            require_project_permission(g.user["id"], "view")
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
            brand_context=current_workspace_brand_text(g.user["id"]),
        )
        try:
            require_project_permission(g.user["id"], "edit")
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
                require_project_permission(g.user["id"], "publish")
                set_update_status(g.user["id"], update_id, "approved")
            elif action == "publish":
                require_project_permission(g.user["id"], "publish")
                try:
                    publish_site_to_remote(g.user["id"], update_id)
                except Exception as error:
                    record_publish_alert(g.user["id"], error)
                    raise
                flash(translate("flash.remote_published"), "success")
            elif action == "restore":
                require_project_permission(g.user["id"], "edit")
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
            require_project_permission(g.user["id"], "edit")
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
            require_project_permission(g.user["id"], "edit")
            terminal = run_site_terminal_command(g.user["id"], command)
        except TeamAccessDenied as error:
            return jsonify({"ok": False, "error": str(error)}), 403
        except ValueError as error:
            return jsonify({"ok": False, "error": str(error)}), 400

        return jsonify({"ok": True, "terminal": terminal})

    @app.route("/site-manager/backup", methods=("POST",))
    @login_required
    def site_manager_backup():
        try:
            require_project_permission(g.user["id"], "edit")
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
            require_project_permission(g.user["id"], "edit")
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
            buffer_api_key = request.form.get("buffer_api_key", "").strip()
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
                        muse_api_key = COALESCE(NULLIF(?, ''), muse_api_key),
                        buffer_api_key = COALESCE(NULLIF(?, ''), buffer_api_key)
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
                        buffer_api_key,
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
            "suggested_uris": suggested_google_redirect_uris(),
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
        if connection:
            try:
                revoke_google_connection(connection)
            except GoogleApiError as error:
                # Same as the API route: a dead token must not block the
                # local disconnect. The row is deleted below either way.
                flash(translate("flash.search_console_revoke_failed", error=error), "warning")
        execute_db(
            "DELETE FROM google_search_console_connections WHERE user_id = ?",
            (g.user["id"],),
        )
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
    cursor = db.execute(query, args)
    db.commit()
    return cursor.lastrowid


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
        "buffer_api_key_configured": bool(user["buffer_api_key"]) if "buffer_api_key" in user.keys() else False,
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
            buffer_api_key TEXT,
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
    ensure_column("users", "buffer_api_key", "TEXT")
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
        CREATE TABLE IF NOT EXISTS website_workspaces (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            team_id INTEGER,
            display_name TEXT NOT NULL DEFAULT '',
            client_name TEXT NOT NULL DEFAULT '',
            brand_json TEXT,
            gsc_property TEXT NOT NULL DEFAULT '',
            last_opened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, path),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (team_id) REFERENCES teams (id)
        )
        """
    )
    ensure_column("website_workspaces", "team_id", "INTEGER")
    ensure_column("website_workspaces", "display_name", "TEXT NOT NULL DEFAULT ''")
    ensure_column("website_workspaces", "client_name", "TEXT NOT NULL DEFAULT ''")
    ensure_column("website_workspaces", "brand_json", "TEXT")
    ensure_column("website_workspaces", "gsc_property", "TEXT NOT NULL DEFAULT ''")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS site_scans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            directory_path TEXT NOT NULL,
            started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            finished_at TIMESTAMP,
            files_checked INTEGER NOT NULL DEFAULT 0,
            open_count INTEGER NOT NULL DEFAULT 0,
            skipped_external INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS site_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            directory_path TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            check_type TEXT NOT NULL,
            severity TEXT NOT NULL DEFAULT 'warning',
            page TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '',
            proposal TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'open',
            resolved_by TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            last_seen_at TIMESTAMP,
            last_seen_scan_id INTEGER,
            UNIQUE (directory_path, fingerprint),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS request_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            token_hash TEXT NOT NULL UNIQUE,
            created_by INTEGER,
            expires_at INTEGER,
            revoked INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES website_workspaces (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS client_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            link_id INTEGER,
            page TEXT NOT NULL DEFAULT '',
            selector TEXT NOT NULL DEFAULT '',
            tag TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL DEFAULT '',
            html_excerpt TEXT NOT NULL DEFAULT '',
            image_src TEXT NOT NULL DEFAULT '',
            client_name TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            proposal_text TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES website_workspaces (id),
            FOREIGN KEY (link_id) REFERENCES request_links (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS request_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            side TEXT NOT NULL DEFAULT 'client',
            user_id INTEGER,
            author_name TEXT NOT NULL DEFAULT '',
            body TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (request_id) REFERENCES client_requests (id),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS request_attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            request_id INTEGER NOT NULL,
            comment_id INTEGER,
            filename TEXT NOT NULL UNIQUE,
            original_name TEXT NOT NULL DEFAULT '',
            mime TEXT NOT NULL DEFAULT '',
            size_bytes INTEGER NOT NULL DEFAULT 0,
            side TEXT NOT NULL DEFAULT 'client',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (request_id) REFERENCES client_requests (id),
            FOREIGN KEY (comment_id) REFERENCES request_comments (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS scheduled_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            created_by INTEGER,
            kind TEXT NOT NULL DEFAULT 'note',
            title TEXT NOT NULL DEFAULT '',
            brief TEXT NOT NULL DEFAULT '',
            page TEXT NOT NULL DEFAULT '',
            starts_on TEXT NOT NULL DEFAULT '',
            ends_on TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'scheduled',
            update_id INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES website_workspaces (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS contact_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            page TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            meta TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'new',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES website_workspaces (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS form_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            label TEXT NOT NULL DEFAULT '',
            token TEXT NOT NULL DEFAULT '',
            token_hash TEXT NOT NULL UNIQUE,
            created_by INTEGER,
            revoked INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES website_workspaces (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS alert_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            kind TEXT NOT NULL DEFAULT 'uptime',
            target TEXT NOT NULL DEFAULT '',
            name TEXT NOT NULL DEFAULT '',
            threshold_days INTEGER NOT NULL DEFAULT 14,
            enabled INTEGER NOT NULL DEFAULT 1,
            last_status TEXT NOT NULL DEFAULT '',
            last_detail TEXT NOT NULL DEFAULT '',
            last_checked_at TIMESTAMP,
            created_by INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES website_workspaces (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS site_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            rule_id INTEGER,
            kind TEXT NOT NULL DEFAULT 'uptime',
            severity TEXT NOT NULL DEFAULT 'error',
            title TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            resolved_at TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES website_workspaces (id),
            FOREIGN KEY (rule_id) REFERENCES alert_rules (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS site_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            workspace_id INTEGER NOT NULL,
            period TEXT NOT NULL DEFAULT '',
            title TEXT NOT NULL DEFAULT '',
            token_hash TEXT NOT NULL UNIQUE,
            created_by INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (workspace_id) REFERENCES website_workspaces (id),
            FOREIGN KEY (created_by) REFERENCES users (id)
        )
        """
    )
    ensure_column("form_tokens", "token", "TEXT NOT NULL DEFAULT ''")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            workspace_id INTEGER,
            kind TEXT NOT NULL DEFAULT 'inbox',
            title TEXT NOT NULL DEFAULT '',
            detail TEXT NOT NULL DEFAULT '',
            link TEXT NOT NULL DEFAULT '',
            read INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (workspace_id) REFERENCES website_workspaces (id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS site_images (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            workspace_id INTEGER,
            filename TEXT NOT NULL UNIQUE,
            prompt TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (workspace_id) REFERENCES website_workspaces (id)
        )
        """
    )
    db.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_website_workspaces_team_path
        ON website_workspaces (team_id, path)
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            owner_id INTEGER NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (owner_id) REFERENCES users (id)
        )
        """
    )
    ensure_column("teams", "description", "TEXT NOT NULL DEFAULT ''")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            permissions TEXT,
            invited_by INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (team_id, user_id),
            FOREIGN KEY (team_id) REFERENCES teams (id),
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (invited_by) REFERENCES users (id)
        )
        """
    )
    ensure_column("team_members", "permissions", "TEXT")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS team_invites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_id INTEGER NOT NULL,
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            permissions TEXT,
            token_hash TEXT NOT NULL UNIQUE,
            invited_by INTEGER,
            expires_at INTEGER NOT NULL,
            accepted_at INTEGER,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams (id),
            FOREIGN KEY (invited_by) REFERENCES users (id)
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
            user_id INTEGER NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL DEFAULT 22,
            username TEXT NOT NULL,
            remote_path TEXT NOT NULL,
            key_path TEXT,
            auth_method TEXT NOT NULL DEFAULT 'key',
            password TEXT,
            directory_path TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, directory_path),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    ensure_column("website_remote_connections", "auth_method", "TEXT NOT NULL DEFAULT 'key'")
    ensure_column("website_remote_connections", "password", "TEXT")
    ensure_column("website_remote_connections", "directory_path", "TEXT")
    _migrate_remote_connections_per_site(db)
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
            directory_path TEXT,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    ensure_column("website_codex_messages", "directory_path", "TEXT")
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS social_posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            channel_id TEXT NOT NULL,
            channel_name TEXT NOT NULL DEFAULT '',
            text TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'queued',
            buffer_post_id TEXT,
            image_url TEXT,
            post_type TEXT NOT NULL DEFAULT 'post',
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    ensure_column("social_posts", "image_url", "TEXT")
    ensure_column("social_posts", "post_type", "TEXT NOT NULL DEFAULT 'post'")
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


class TeamAccessDenied(ValueError):
    pass


def _migrate_remote_connections_per_site(db):
    """Rebuild legacy single-connection rows into one row per site.

    Older databases declared ``user_id UNIQUE`` on website_remote_connections,
    so each account could only keep a single remote target. The per-site model
    keys rows by (user_id, directory_path) instead. Bound rows keep their
    site; unbound rows are attached to the user's current directory when there
    is one, and dropped otherwise.
    """
    table = db.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'website_remote_connections'"
    ).fetchone()
    if not table or "UNIQUE (user_id, directory_path)" in (table[0] or ""):
        return
    db.execute("ALTER TABLE website_remote_connections RENAME TO website_remote_connections_legacy")
    db.execute(
        """
        CREATE TABLE website_remote_connections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            host TEXT NOT NULL,
            port INTEGER NOT NULL DEFAULT 22,
            username TEXT NOT NULL,
            remote_path TEXT NOT NULL,
            key_path TEXT,
            auth_method TEXT NOT NULL DEFAULT 'key',
            password TEXT,
            directory_path TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (user_id, directory_path),
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
        """
    )
    columns = [row["name"] for row in db.execute("PRAGMA table_info(website_remote_connections_legacy)").fetchall()]
    legacy_rows = db.execute("SELECT * FROM website_remote_connections_legacy").fetchall()
    for legacy in legacy_rows:
        values = dict(zip(columns, legacy))
        directory_path = values.get("directory_path")
        if not directory_path:
            current = db.execute(
                "SELECT path FROM website_directories WHERE user_id = ?", (values["user_id"],)
            ).fetchone()
            directory_path = current[0] if current else None
        if not directory_path:
            continue
        db.execute(
            """
            INSERT OR IGNORE INTO website_remote_connections (
                user_id, host, port, username, remote_path, key_path,
                auth_method, password, directory_path, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                values["user_id"],
                values["host"],
                values.get("port") or 22,
                values["username"],
                values["remote_path"],
                values.get("key_path"),
                values.get("auth_method") or "key",
                values.get("password"),
                os.path.realpath(directory_path) if os.path.exists(directory_path) else directory_path,
                values.get("created_at"),
                values.get("updated_at"),
            ),
        )
    db.execute("DROP TABLE website_remote_connections_legacy")
    db.commit()


def google_oauth_configured(credentials):
    return bool(credentials["client_id"] and credentials["client_secret"])


def get_user_account(user_id):
    return query_db(
        """
        SELECT id, name, email, password_hash, email_verified, avatar_path, company_name,
               company_email, company_website, company_logo_path,
               muse_api_key, muse_models_json, anthropic_api_key, openrouter_api_key, google_api_key,
               buffer_api_key,
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
    """OAuth callback URL sent to Google.

    Uses GOOGLE_REDIRECT_URI when explicitly configured, otherwise derives it
    from the current public request (scheme + host + callback path). The
    derived value requires ProxyFix above when running behind cloudflared or
    another reverse proxy. Google only accepts URIs registered in the OAuth
    client, so the value shown in Settings must be added to the Google Cloud
    Console "Authorized redirect URIs" list.
    """
    configured_uri = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
    if configured_uri:
        return configured_uri
    if not has_request_context():
        raise GoogleApiError(
            "GOOGLE_REDIRECT_URI is not set and there is no request to derive the callback URL from."
        )
    return url_for("google_search_console_callback", _external=True)


def google_native_redirect_uri():
    port = int(os.environ.get("PORT", "51249"))
    return f"http://127.0.0.1:{port}/api/google-search-console/callback"


GOOGLE_AUTH_DIAG_TIMEOUT = 20
GOOGLE_AUTH_DIAG_USER_AGENT = "Mozilla/5.0 (ONEBoard diagnostics)"


def suggested_google_redirect_uris():
    try:
        current = google_redirect_uri()
    except GoogleApiError:
        return []
    uris = [current]
    try:
        split = urllib.parse.urlsplit(current)
    except ValueError:
        return uris
    host = split.hostname or ""
    if host in ("127.0.0.1", "localhost"):
        port = f":{split.port}" if split.port else ""
        alt_host = "localhost" if host == "127.0.0.1" else "127.0.0.1"
        alt = urllib.parse.urlunsplit((split.scheme, f"{alt_host}{port}", split.path, "", ""))
        if alt not in uris:
            uris.append(alt)
    return uris


def diagnose_google_redirect_uri(redirect_uri):
    """Ask Google whether an OAuth redirect URI is registered.

    Google validates the redirect URI before anything else, so requesting the
    authorization URL reveals `redirect_uri_mismatch` (URI not registered) vs
    the normal sign-in page (URI accepted) without user credentials.
    """
    result = {"redirect_uri": redirect_uri, "google_accepts": False, "reason": "unknown"}
    credentials = get_google_oauth_credentials()
    if not google_oauth_configured(credentials):
        result["reason"] = "missing_credentials"
        return result
    params = {
        "client_id": credentials["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SEARCH_CONSOLE_SCOPE,
        "state": "oneboard-diagnostics",
    }
    req = urllib.request.Request(
        f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}",
        headers={"User-Agent": GOOGLE_AUTH_DIAG_USER_AGENT},
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=GOOGLE_AUTH_DIAG_TIMEOUT) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        try:
            body = error.read().decode("utf-8", errors="replace")
        except (OSError, ValueError):
            body = ""
    except urllib.error.URLError as error:
        result["reason"] = "network"
        result["detail"] = str(error.reason) if getattr(error, "reason", None) else str(error)
        return result
    lowered = body.lower()
    if "redirect_uri_mismatch" in lowered:
        result["reason"] = "mismatch"
    elif "invalid_client" in lowered:
        result["reason"] = "invalid_client"
    elif "identifier" in lowered or "sign in" in lowered:
        result["google_accepts"] = True
        result["reason"] = "accepted"
    return result


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
        "site_scoped": False,
        "site_name": None,
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
        site_property = current_workspace_gsc_property(user_id)
        if site_property and site_property in available_site_urls:
            selected_site_url = site_property
            dashboard["site_scoped"] = True
            workspace = get_current_workspace(user_id)
            if workspace:
                dashboard["site_name"] = workspace["display_name"] or os.path.basename(
                    workspace["path"].rstrip(os.sep)
                ) or workspace["path"]
        else:
            selected_site_url = (
                saved_site_url
                if saved_site_url in available_site_urls
                else first_site_url(dashboard["sites"])
            )
        dashboard["selected_site_url"] = selected_site_url

        if selected_site_url != connection["selected_site_url"] and not dashboard["site_scoped"]:
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
    detach_inaccessible_team_directory(user_id)
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
        "team_context": current_team_context(user_id),
        "preview_selection": session.get(PREVIEW_SELECTION_KEY) if has_request_context() else None,
        "health": get_health_summary(user_id),
        "client_requests": {"open_count": count_open_client_requests(user_id)},
        "projects": list_site_projects(user_id),
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
def validate_site_directory_selection(normalized_path):
    app_data_path = os.path.realpath(APP_DATA_DIR)
    home_path = os.path.realpath(os.path.expanduser("~"))
    filesystem_root = os.path.realpath(os.path.abspath(os.sep))
    if (
        normalized_path in {filesystem_root, home_path, app_data_path}
        or path_is_inside(app_data_path, normalized_path)
    ):
        raise ValueError(translate("flash.site_path_unsafe"))


def clean_manual_directory_path(path):
    cleaned = (path or "").strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in {"'", '"'}:
        cleaned = cleaned[1:-1].strip()
    return cleaned.replace("\\ ", " ")


def connect_site_directory(user_id, path):
    cleaned_path = clean_manual_directory_path(path)
    if not cleaned_path:
        raise ValueError(translate("flash.site_path_required"))

    normalized_path = os.path.realpath(os.path.abspath(os.path.expanduser(cleaned_path)))
    validate_site_directory_selection(normalized_path)
    if not os.path.exists(normalized_path):
        try:
            os.makedirs(normalized_path, exist_ok=True)
        except OSError:
            raise ValueError(translate("flash.site_path_create_failed"))
    if not os.path.isdir(normalized_path):
        raise ValueError(translate("flash.site_path_not_directory"))

    store_site_directory(user_id, normalized_path)


@locked_site_operation
def ensure_default_site_directory(user_id):
    """Give each account a usable project folder when it has not selected one."""
    directory = get_site_directory(user_id)
    if directory and os.path.isdir(directory["path"]):
        return directory
    default_path = os.path.join(
        os.path.expanduser("~"), "ONEBoard Projects", f"project-{user_id}"
    )
    connect_site_directory(user_id, default_path)
    return get_site_directory(user_id)


def browse_local_directories(path):
    start = (path or "").strip() or os.path.expanduser("~")
    normalized_path = os.path.realpath(os.path.abspath(os.path.expanduser(start)))
    if not os.path.exists(normalized_path):
        raise ValueError(translate("flash.site_path_missing"))
    if not os.path.isdir(normalized_path):
        raise ValueError(translate("flash.site_path_not_directory"))
    app_data_path = os.path.realpath(APP_DATA_DIR)
    if normalized_path == app_data_path or path_is_inside(app_data_path, normalized_path):
        raise ValueError(translate("flash.site_path_unsafe"))

    entries = []
    try:
        with os.scandir(normalized_path) as iterator:
            for entry in iterator:
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                    entry_real = os.path.realpath(entry.path)
                    if entry_real == app_data_path or path_is_inside(app_data_path, entry_real):
                        continue
                except OSError:
                    continue
                if entry.name.startswith("."):
                    continue
                entries.append({"name": entry.name, "path": entry_real})
    except OSError as error:
        raise ValueError(translate("flash.site_path_missing")) from error
    entries.sort(key=lambda item: item["name"].casefold())

    filesystem_root = os.path.realpath(os.path.abspath(os.sep))
    try:
        validate_site_directory_selection(normalized_path)
        can_select = True
    except ValueError:
        can_select = False
    return {
        "current": normalized_path,
        "parent": os.path.dirname(normalized_path) if normalized_path != filesystem_root else None,
        "home": os.path.realpath(os.path.expanduser("~")),
        "can_select": can_select,
        "entries": entries,
    }


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
    execute_db(
        """
        INSERT INTO website_workspaces (user_id, path, last_opened_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, path) DO UPDATE SET
            last_opened_at = CURRENT_TIMESTAMP
        """,
        (user_id, normalized_path),
    )


TEAM_PERMISSIONS = ("view", "edit", "publish", "invite", "manage", "billing")

TEAM_ROLE_PRESETS = {
    "owner": {"view": True, "edit": True, "publish": True, "invite": True, "manage": True, "billing": True},
    "admin": {"view": True, "edit": True, "publish": True, "invite": True, "manage": True, "billing": True},
    "editor": {"view": True, "edit": True, "publish": False, "invite": False, "manage": False, "billing": False},
    "viewer": {"view": True, "edit": False, "publish": False, "invite": False, "manage": False, "billing": False},
    "client": {"view": True, "edit": False, "publish": False, "invite": False, "manage": False, "billing": False},
}

TEAM_INVITE_ROLES = ("admin", "editor", "viewer", "client")
TEAM_MEMBER_ROLES = ("admin", "editor", "viewer", "client", "custom")
TEAM_INVITE_TTL_SECONDS = 7 * 24 * 3600


def parse_team_permissions(raw, fallback_role="viewer"):
    permissions = dict(TEAM_ROLE_PRESETS.get(fallback_role, TEAM_ROLE_PRESETS["viewer"]))
    if raw:
        try:
            stored = json.loads(raw)
        except (TypeError, json.JSONDecodeError):
            stored = {}
        if isinstance(stored, dict):
            for key in TEAM_PERMISSIONS:
                if key in stored:
                    permissions[key] = bool(stored[key])
    permissions["view"] = True
    return permissions


def team_permissions_for_role(role):
    return dict(TEAM_ROLE_PRESETS.get(role, TEAM_ROLE_PRESETS["viewer"]))


def get_team(team_id):
    try:
        team_id = int(team_id)
    except (TypeError, ValueError):
        return None
    row = query_db("SELECT * FROM teams WHERE id = ?", (team_id,), one=True)
    return dict(row) if row else None


def get_team_membership(team_id, user_id):
    row = query_db(
        "SELECT * FROM team_members WHERE team_id = ? AND user_id = ?",
        (team_id, user_id),
        one=True,
    )
    if not row:
        return None
    membership = dict(row)
    membership["permissions"] = parse_team_permissions(row["permissions"], row["role"])
    return membership


def require_team(team_id):
    team = get_team(team_id)
    if not team:
        raise ValueError(translate("flash.team_not_found"))
    return team


def require_team_membership(team_id, user_id):
    team = require_team(team_id)
    membership = get_team_membership(team["id"], user_id)
    if not membership:
        raise TeamAccessDenied(translate("flash.not_team_member"))
    return team, membership


def require_team_permission(team_id, user_id, permission):
    team, membership = require_team_membership(team_id, user_id)
    if not membership["permissions"].get(permission):
        raise TeamAccessDenied(translate("flash.team_permission_denied"))
    return team, membership


def get_user_team_ids(user_id):
    rows = query_db("SELECT team_id FROM team_members WHERE user_id = ?", (user_id,))
    return {row["team_id"] for row in rows}


def serialize_team_member(row):
    return {
        "id": row["user_id"],
        "name": row["name"],
        "email": row["email"],
        "role": row["role"],
        "permissions": parse_team_permissions(row["permissions"], row["role"]),
        "created_at": row["created_at"],
    }


def get_team_members(team_id):
    rows = query_db(
        """
        SELECT m.user_id, m.role, m.permissions, m.created_at, u.name, u.email
        FROM team_members m
        JOIN users u ON u.id = m.user_id
        WHERE m.team_id = ?
        ORDER BY m.created_at ASC, m.id ASC
        """,
        (team_id,),
    )
    return [serialize_team_member(row) for row in rows]


def get_pending_team_invites(team_id):
    rows = query_db(
        """
        SELECT i.id, i.email, i.role, i.permissions, i.expires_at, i.created_at,
               u.name AS invited_by_name, t.name AS team_name
        FROM team_invites i
        JOIN teams t ON t.id = i.team_id
        LEFT JOIN users u ON u.id = i.invited_by
        WHERE i.team_id = ? AND i.accepted_at IS NULL AND i.expires_at > ?
        ORDER BY i.created_at DESC, i.id DESC
        """,
        (team_id, int(time.time())),
    )
    invites = []
    for row in rows:
        invite = dict(row)
        invite["permissions"] = parse_team_permissions(row["permissions"], row["role"])
        invite["expires_label"] = datetime.fromtimestamp(row["expires_at"]).strftime("%Y-%m-%d %H:%M")
        invites.append(invite)
    return invites


def get_user_pending_invites(user_id):
    user = query_db("SELECT email FROM users WHERE id = ?", (user_id,), one=True)
    if not user:
        return []
    rows = query_db(
        """
        SELECT i.id, i.team_id, i.email, i.role, i.permissions, i.expires_at, i.created_at,
               t.name AS team_name, t.description AS team_description,
               u.name AS invited_by_name
        FROM team_invites i
        JOIN teams t ON t.id = i.team_id
        LEFT JOIN users u ON u.id = i.invited_by
        WHERE lower(i.email) = lower(?) AND i.accepted_at IS NULL AND i.expires_at > ?
        ORDER BY i.created_at DESC, i.id DESC
        """,
        (user["email"], int(time.time())),
    )
    invites = []
    for row in rows:
        invite = dict(row)
        invite["permissions"] = parse_team_permissions(row["permissions"], row["role"])
        invite["expires_label"] = datetime.fromtimestamp(row["expires_at"]).strftime("%Y-%m-%d %H:%M")
        invites.append(invite)
    return invites


def serialize_team(team, membership=None):
    counts = query_db(
        """
        SELECT
            (SELECT COUNT(*) FROM team_members WHERE team_id = ?) AS member_count,
            (SELECT COUNT(*) FROM website_workspaces WHERE team_id = ?) AS project_count
        """,
        (team["id"], team["id"]),
        one=True,
    )
    payload = {
        "id": team["id"],
        "name": team["name"],
        "description": team.get("description") or "",
        "owner_id": team["owner_id"],
        "member_count": counts["member_count"],
        "project_count": counts["project_count"],
        "created_at": team["created_at"],
        "updated_at": team["updated_at"],
    }
    if membership is not None:
        payload["my_role"] = membership["role"]
        payload["my_permissions"] = membership["permissions"]
    return payload


def get_user_teams(user_id):
    rows = query_db(
        """
        SELECT t.*, m.role AS member_role, m.permissions AS member_permissions
        FROM teams t
        JOIN team_members m ON m.team_id = t.id AND m.user_id = ?
        ORDER BY t.name COLLATE NOCASE ASC, t.id ASC
        """,
        (user_id,),
    )
    teams = []
    for row in rows:
        team = dict(row)
        membership = {
            "role": row["member_role"],
            "permissions": parse_team_permissions(row["member_permissions"], row["member_role"]),
        }
        teams.append(serialize_team(team, membership))
    return teams


def create_team(owner_id, name, description=""):
    name = (name or "").strip()
    if not name:
        raise ValueError(translate("flash.team_name_required"))
    team_id = execute_db(
        "INSERT INTO teams (name, description, owner_id) VALUES (?, ?, ?)",
        (name[:80], (description or "").strip()[:500], owner_id),
    )
    execute_db(
        "INSERT INTO team_members (team_id, user_id, role, permissions, invited_by) VALUES (?, ?, 'owner', ?, ?)",
        (team_id, owner_id, json.dumps(team_permissions_for_role("owner")), owner_id),
    )
    team = require_team(team_id)
    return serialize_team(team, {"role": "owner", "permissions": team_permissions_for_role("owner")})


def update_team(team_id, actor_id, name=None, description=None):
    team, _membership = require_team_permission(team_id, actor_id, "manage")
    updates = {}
    if name is not None:
        name = name.strip()
        if not name:
            raise ValueError(translate("flash.team_name_required"))
        updates["name"] = name[:80]
    if description is not None:
        updates["description"] = description.strip()[:500]
    if updates:
        assignments = ", ".join(f"{column} = ?" for column in updates)
        execute_db(
            f"UPDATE teams SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (*updates.values(), team["id"]),
        )
    return serialize_team(require_team(team["id"]), get_team_membership(team["id"], actor_id))


def delete_team(team_id, actor_id):
    team = require_team(team_id)
    if team["owner_id"] != actor_id:
        raise TeamAccessDenied(translate("flash.team_permission_denied"))
    execute_db("DELETE FROM website_workspaces WHERE team_id = ?", (team["id"],))
    execute_db("DELETE FROM team_invites WHERE team_id = ?", (team["id"],))
    execute_db("DELETE FROM team_members WHERE team_id = ?", (team["id"],))
    execute_db("DELETE FROM teams WHERE id = ?", (team["id"],))


def invite_team_member(team_id, actor_id, email, role="editor"):
    team, membership = require_team_membership(team_id, actor_id)
    role = (role or "editor").strip().lower()
    if role not in TEAM_INVITE_ROLES:
        role = "editor"
    needed = "manage" if role == "admin" else "invite"
    if not membership["permissions"].get(needed):
        raise TeamAccessDenied(translate("flash.team_permission_denied"))
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        raise ValueError(translate("flash.email_password_required"))
    existing_user = query_db("SELECT id FROM users WHERE lower(email) = ?", (email,), one=True)
    if existing_user and get_team_membership(team["id"], existing_user["id"]):
        raise ValueError(translate("flash.already_member"))
    execute_db(
        "DELETE FROM team_invites WHERE team_id = ? AND lower(email) = ? AND accepted_at IS NULL",
        (team["id"], email),
    )
    token = secrets.token_urlsafe(48)
    now = int(time.time())
    invite_id = execute_db(
        """
        INSERT INTO team_invites (team_id, email, role, permissions, token_hash, invited_by, expires_at, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            team["id"],
            email,
            role,
            json.dumps(team_permissions_for_role(role)),
            hashlib.sha256(token.encode("utf-8")).hexdigest(),
            actor_id,
            now + TEAM_INVITE_TTL_SECONDS,
            now,
        ),
    )
    invite = query_db("SELECT * FROM team_invites WHERE id = ?", (invite_id,), one=True)
    payload = dict(invite)
    payload["permissions"] = parse_team_permissions(invite["permissions"], invite["role"])
    return payload, token


def send_team_invite_email(team_name, recipient, invite_link):
    settings = smtp_settings()
    if not settings["host"] or not settings["from_address"]:
        raise ValueError("Email is not configured. Set SMTP_HOST and SMTP_FROM.")
    if bool(settings["username"]) != bool(settings["password"]):
        raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together.")
    message = email.message.EmailMessage()
    message["Subject"] = f"You are invited to join {team_name} on ONEBoard"
    message["From"] = settings["from_address"]
    message["To"] = recipient
    message.set_content(
        f"You have been invited to join the team \"{team_name}\" on ONEBoard.\n\n"
        f"Accept the invitation here:\n{invite_link}\n\n"
        "This link expires in 7 days. If you do not have an account yet, create one with this email address first."
    )
    try:
        with smtplib.SMTP(settings["host"], settings["port"], timeout=20) as server:
            if settings["use_tls"]:
                server.starttls()
            if settings["username"]:
                server.login(settings["username"], settings["password"])
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise ValueError("Unable to send the invitation email. Check the SMTP configuration.") from error


def get_valid_team_invite(token):
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = query_db(
        """
        SELECT i.*, t.name AS team_name
        FROM team_invites i
        JOIN teams t ON t.id = i.team_id
        WHERE i.token_hash = ? AND i.accepted_at IS NULL AND i.expires_at > ?
        """,
        (token_hash, int(time.time())),
        one=True,
    )
    return dict(row) if row else None


def _apply_team_invite(invite, user_id):
    user = query_db("SELECT id, email FROM users WHERE id = ?", (user_id,), one=True)
    if not user:
        raise TeamAccessDenied(translate("flash.login_required"))
    if user["email"].strip().lower() != invite["email"].strip().lower():
        raise TeamAccessDenied(translate("flash.invite_email_mismatch"))
    team = require_team(invite["team_id"])
    membership = get_team_membership(team["id"], user_id)
    if not membership:
        try:
            execute_db(
                "INSERT INTO team_members (team_id, user_id, role, permissions, invited_by) VALUES (?, ?, ?, ?, ?)",
                (
                    team["id"],
                    user_id,
                    invite["role"],
                    invite["permissions"] or json.dumps(team_permissions_for_role(invite["role"])),
                    invite["invited_by"],
                ),
            )
        except sqlite3.IntegrityError:
            pass
        membership = get_team_membership(team["id"], user_id)
    execute_db(
        "UPDATE team_invites SET accepted_at = ? WHERE id = ? AND accepted_at IS NULL",
        (int(time.time()), invite["id"]),
    )
    return serialize_team(team, membership)


def accept_team_invite(token, user_id):
    invite = get_valid_team_invite(token)
    if not invite:
        raise ValueError(translate("flash.invite_invalid"))
    return _apply_team_invite(invite, user_id)


def accept_team_invite_by_id(invite_id, user_id):
    try:
        invite_id = int(invite_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.invite_invalid"))
    row = query_db(
        """
        SELECT i.*, t.name AS team_name
        FROM team_invites i
        JOIN teams t ON t.id = i.team_id
        WHERE i.id = ? AND i.accepted_at IS NULL AND i.expires_at > ?
        """,
        (invite_id, int(time.time())),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.invite_invalid"))
    return _apply_team_invite(dict(row), user_id)


def revoke_team_invite(team_id, actor_id, invite_id):
    _team, membership = require_team_membership(team_id, actor_id)
    if not membership["permissions"].get("invite") and not membership["permissions"].get("manage"):
        raise TeamAccessDenied(translate("flash.team_permission_denied"))
    try:
        invite_id = int(invite_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.invite_invalid"))
    row = query_db(
        "SELECT id FROM team_invites WHERE id = ? AND team_id = ? AND accepted_at IS NULL",
        (invite_id, team_id),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.invite_invalid"))
    execute_db("DELETE FROM team_invites WHERE id = ?", (invite_id,))


def _matching_team_preset(permissions):
    for name, preset in TEAM_ROLE_PRESETS.items():
        if name == "owner":
            continue
        if all(bool(permissions.get(key)) == value for key, value in preset.items()):
            return name
    return "custom"


def update_team_member(team_id, actor_id, target_user_id, role=None, permissions=None):
    team, _membership = require_team_permission(team_id, actor_id, "manage")
    try:
        target_user_id = int(target_user_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.team_member_not_found"))
    target = get_team_membership(team["id"], target_user_id)
    if not target:
        raise ValueError(translate("flash.team_member_not_found"))
    if target["role"] == "owner" or target_user_id == team["owner_id"]:
        raise TeamAccessDenied(translate("flash.cannot_modify_owner"))
    if role is not None:
        role = role.strip().lower()
        if role == "owner":
            raise TeamAccessDenied(translate("flash.cannot_modify_owner"))
        if role not in TEAM_MEMBER_ROLES:
            raise ValueError(translate("flash.team_member_not_found"))
    else:
        role = target["role"]
    merged = dict(team_permissions_for_role(role)) if role != "custom" else dict(target["permissions"])
    if role == "custom":
        merged = dict(target["permissions"])
    if permissions is not None:
        if not isinstance(permissions, dict):
            raise ValueError(translate("flash.team_member_not_found"))
        for key in TEAM_PERMISSIONS:
            if key in permissions:
                merged[key] = bool(permissions[key])
        merged["view"] = True
        role = _matching_team_preset(merged)
    execute_db(
        "UPDATE team_members SET role = ?, permissions = ? WHERE team_id = ? AND user_id = ?",
        (role, json.dumps(merged), team["id"], target_user_id),
    )
    return get_team_members(team["id"])


def remove_team_member(team_id, actor_id, target_user_id):
    team, _membership = require_team_permission(team_id, actor_id, "manage")
    try:
        target_user_id = int(target_user_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.team_member_not_found"))
    target = get_team_membership(team["id"], target_user_id)
    if not target:
        raise ValueError(translate("flash.team_member_not_found"))
    if target["role"] == "owner" or target_user_id == team["owner_id"]:
        raise TeamAccessDenied(translate("flash.cannot_modify_owner"))
    execute_db(
        "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
        (team["id"], target_user_id),
    )
    detach_inaccessible_team_directory(target_user_id)
    return get_team_members(team["id"])


def leave_team(team_id, user_id):
    team, membership = require_team_membership(team_id, user_id)
    if membership["role"] == "owner" or team["owner_id"] == user_id:
        raise ValueError(translate("flash.owner_transfer_required"))
    execute_db(
        "DELETE FROM team_members WHERE team_id = ? AND user_id = ?",
        (team["id"], user_id),
    )
    detach_inaccessible_team_directory(user_id)


def transfer_team_ownership(team_id, actor_id, target_user_id):
    team = require_team(team_id)
    if team["owner_id"] != actor_id:
        raise TeamAccessDenied(translate("flash.team_permission_denied"))
    try:
        target_user_id = int(target_user_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.team_member_not_found"))
    if target_user_id == actor_id:
        raise ValueError(translate("flash.team_member_not_found"))
    target = get_team_membership(team["id"], target_user_id)
    if not target:
        raise ValueError(translate("flash.team_member_not_found"))
    execute_db(
        "UPDATE team_members SET role = 'admin', permissions = ? WHERE team_id = ? AND user_id = ?",
        (json.dumps(team_permissions_for_role("admin")), team["id"], actor_id),
    )
    execute_db(
        "UPDATE team_members SET role = 'owner', permissions = ? WHERE team_id = ? AND user_id = ?",
        (json.dumps(team_permissions_for_role("owner")), team["id"], target_user_id),
    )
    execute_db(
        "UPDATE teams SET owner_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (target_user_id, team["id"]),
    )
    return get_team_members(team["id"])


def find_team_projects_by_path(normalized_path):
    return query_db(
        """
        SELECT w.*, t.name AS team_name
        FROM website_workspaces w
        JOIN teams t ON t.id = w.team_id
        WHERE w.team_id IS NOT NULL AND w.path = ?
        """,
        (normalized_path,),
    )


def current_team_context(user_id):
    """Return the team context for the user's current directory, if any."""
    directory = get_site_directory(user_id)
    if not directory:
        return None
    rows = find_team_projects_by_path(os.path.realpath(directory["path"]))
    if not rows:
        return None
    membership = get_team_membership(rows[0]["team_id"], user_id)
    if not membership or not membership["permissions"].get("view"):
        return None
    team = require_team(rows[0]["team_id"])
    return {
        "team": {"id": team["id"], "name": team["name"]},
        "project_id": rows[0]["id"],
        "role": membership["role"],
        "permissions": membership["permissions"],
    }


def require_project_permission(user_id, permission):
    """Enforce the team permission for the user's current directory.

    Personal folders are always allowed. Folders shared with a team require
    membership plus the given granular permission.
    """
    directory = get_site_directory(user_id)
    if not directory:
        return None
    rows = find_team_projects_by_path(os.path.realpath(directory["path"]))
    if not rows:
        return None
    membership = get_team_membership(rows[0]["team_id"], user_id)
    if not membership or not membership["permissions"].get("view"):
        raise TeamAccessDenied(translate("flash.team_path_forbidden"))
    if not membership["permissions"].get(permission):
        raise TeamAccessDenied(translate("flash.team_permission_denied"))
    return {
        "team_id": rows[0]["team_id"],
        "role": membership["role"],
        "permissions": membership["permissions"],
    }


def team_scope_user_ids(user_id):
    """User ids whose chat/history/backups are visible in the current folder."""
    directory = get_site_directory(user_id)
    if not directory:
        return [user_id]
    rows = find_team_projects_by_path(os.path.realpath(directory["path"]))
    if not rows:
        return [user_id]
    membership = get_team_membership(rows[0]["team_id"], user_id)
    if not membership or not membership["permissions"].get("view"):
        return []
    member_rows = query_db(
        "SELECT user_id FROM team_members WHERE team_id = ?", (rows[0]["team_id"],)
    )
    return [row["user_id"] for row in member_rows] or [user_id]


def detach_inaccessible_team_directory(user_id):
    """Forget the current folder when it is a team project without access."""
    directory = get_site_directory(user_id)
    if not directory:
        return False
    rows = find_team_projects_by_path(os.path.realpath(directory["path"]))
    if not rows:
        return False
    membership = get_team_membership(rows[0]["team_id"], user_id)
    if membership and membership["permissions"].get("view"):
        return False
    execute_db("DELETE FROM website_directories WHERE user_id = ?", (user_id,))
    return True


def set_current_site_directory(user_id, normalized_path):
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


def connect_site_project(user_id, project_id=None, path=None):
    """Open a personal or team project by id, or connect a folder path."""
    if project_id is not None:
        try:
            project_id = int(str(project_id).strip())
        except (TypeError, ValueError):
            raise ValueError(translate("flash.project_not_found"))
        row = query_db(
            """
            SELECT w.*, t.name AS team_name
            FROM website_workspaces w
            LEFT JOIN teams t ON t.id = w.team_id
            WHERE w.id = ?
              AND (
                (w.team_id IS NULL AND w.user_id = ?)
                OR (w.team_id IS NOT NULL AND w.team_id IN (SELECT team_id FROM team_members WHERE user_id = ?))
              )
            """,
            (project_id, user_id, user_id),
            one=True,
        )
        if not row:
            raise ValueError(translate("flash.project_not_found"))
        if row["team_id"] is not None:
            membership = get_team_membership(row["team_id"], user_id)
            if not membership or not membership["permissions"].get("view"):
                raise TeamAccessDenied(translate("flash.team_path_forbidden"))
            normalized_path = os.path.realpath(row["path"])
            validate_site_directory_selection(normalized_path)
            if not os.path.isdir(normalized_path):
                raise ValueError(translate("flash.site_path_missing"))
            set_current_site_directory(user_id, normalized_path)
            execute_db(
                "UPDATE website_workspaces SET last_opened_at = CURRENT_TIMESTAMP WHERE id = ?",
                (row["id"],),
            )
            return
        connect_site_directory(user_id, row["path"])
        return

    cleaned_path = clean_manual_directory_path(path or "")
    if not cleaned_path:
        ensure_default_site_directory(user_id)
        return
    normalized_path = os.path.realpath(os.path.abspath(os.path.expanduser(cleaned_path)))
    validate_site_directory_selection(normalized_path)
    shared = find_team_projects_by_path(normalized_path)
    member_teams = get_user_team_ids(user_id)
    if any(row["team_id"] in member_teams for row in shared):
        membership = get_team_membership(
            next(row["team_id"] for row in shared if row["team_id"] in member_teams), user_id
        )
        if not membership or not membership["permissions"].get("view"):
            raise TeamAccessDenied(translate("flash.team_path_forbidden"))
        if not os.path.isdir(normalized_path):
            raise ValueError(translate("flash.site_path_missing"))
        set_current_site_directory(user_id, normalized_path)
        execute_db(
            "UPDATE website_workspaces SET last_opened_at = CURRENT_TIMESTAMP WHERE team_id IS NOT NULL AND path = ?",
            (normalized_path,),
        )
        return
    if shared:
        raise TeamAccessDenied(translate("flash.team_path_forbidden"))
    connect_site_directory(user_id, cleaned_path)


def add_team_project(team_id, actor_id, project_id=None, path=None):
    _team, _membership = require_team_permission(team_id, actor_id, "manage")
    team_id = int(team_id)
    if project_id is not None:
        try:
            project_id = int(str(project_id).strip())
        except (TypeError, ValueError):
            raise ValueError(translate("flash.project_not_found"))
        row = query_db(
            "SELECT id, path FROM website_workspaces WHERE id = ? AND user_id = ? AND team_id IS NULL",
            (project_id, actor_id),
            one=True,
        )
        if not row:
            raise ValueError(translate("flash.project_not_found"))
        normalized_path = os.path.realpath(row["path"])
        source_id = row["id"]
    else:
        cleaned_path = clean_manual_directory_path(path or "")
        if not cleaned_path:
            raise ValueError(translate("flash.site_path_required"))
        normalized_path = os.path.realpath(os.path.abspath(os.path.expanduser(cleaned_path)))
        source_id = None
    validate_site_directory_selection(normalized_path)
    if not os.path.isdir(normalized_path):
        raise ValueError(translate("flash.site_path_not_directory"))
    shared = find_team_projects_by_path(normalized_path)
    same = next((row for row in shared if row["team_id"] == team_id), None)
    if same:
        execute_db(
            "UPDATE website_workspaces SET last_opened_at = CURRENT_TIMESTAMP WHERE id = ?",
            (same["id"],),
        )
        return format_site_project(same, None, {"scope": "team", "team_id": team_id, "team_name": same["team_name"]})
    if shared:
        raise TeamAccessDenied(translate("flash.team_project_elsewhere"))
    if source_id is not None:
        execute_db(
            "UPDATE website_workspaces SET team_id = ?, last_opened_at = CURRENT_TIMESTAMP WHERE id = ?",
            (team_id, source_id),
        )
        row_id = source_id
    else:
        try:
            row_id = execute_db(
                "INSERT INTO website_workspaces (user_id, path, team_id, last_opened_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
                (actor_id, normalized_path, team_id),
            )
        except sqlite3.IntegrityError as error:
            raise TeamAccessDenied(translate("flash.team_project_elsewhere")) from error
    row = query_db(
        """
        SELECT w.*, t.name AS team_name
        FROM website_workspaces w
        JOIN teams t ON t.id = w.team_id
        WHERE w.id = ?
        """,
        (row_id,),
        one=True,
    )
    return format_site_project(dict(row), None, {"scope": "team", "team_id": team_id, "team_name": row["team_name"]})


def remove_team_project(team_id, actor_id, project_id):
    team, _membership = require_team_permission(team_id, actor_id, "manage")
    try:
        project_id = int(str(project_id).strip())
    except (TypeError, ValueError):
        raise ValueError(translate("flash.project_not_found"))
    row = query_db(
        "SELECT id, path FROM website_workspaces WHERE id = ? AND team_id = ?",
        (project_id, team["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.project_not_found"))
    execute_db("DELETE FROM website_workspaces WHERE id = ?", (project_id,))
    directory = get_site_directory(actor_id)
    if directory and os.path.realpath(directory["path"]) == os.path.realpath(row["path"]):
        execute_db("DELETE FROM website_directories WHERE user_id = ?", (actor_id,))


def get_team_projects(team_id):
    rows = query_db(
        """
        SELECT w.*, t.name AS team_name
        FROM website_workspaces w
        JOIN teams t ON t.id = w.team_id
        WHERE w.team_id = ?
        ORDER BY w.last_opened_at DESC, w.id DESC
        """,
        (team_id,),
    )
    return [format_site_project(dict(row), None, {"scope": "team", "team_id": row["team_id"], "team_name": row["team_name"]}) for row in rows]


def format_site_project(row, current, extra=None):
    path = row["path"]
    name = os.path.basename(path.rstrip(os.sep)) or path
    project = {
        "id": row["id"],
        "path": path,
        "name": name,
        "display_name": row.get("display_name") or name,
        "client_name": row.get("client_name") or "",
        "has_brand": bool(row.get("brand_json")),
        "is_current": current is not None and os.path.realpath(path) == current,
        "exists": os.path.isdir(path),
        "last_opened_at": row["last_opened_at"],
        "scope": "personal",
        "team_id": None,
        "team_name": None,
        "permissions": dict(TEAM_ROLE_PRESETS["owner"]),
    }
    if extra:
        project.update(extra)
    return project


def list_site_projects(user_id):
    directory = get_site_directory(user_id)
    current = os.path.realpath(directory["path"]) if directory else None
    rows = query_db(
        """
        SELECT w.id, w.path, w.last_opened_at, w.team_id, t.name AS team_name,
               w.display_name, w.client_name, w.brand_json,
               m.role AS member_role, m.permissions AS member_permissions
        FROM website_workspaces w
        LEFT JOIN teams t ON t.id = w.team_id
        LEFT JOIN team_members m ON m.team_id = w.team_id AND m.user_id = ?
        WHERE (w.team_id IS NULL AND w.user_id = ?)
           OR (w.team_id IS NOT NULL AND m.user_id IS NOT NULL)
        ORDER BY w.last_opened_at DESC, w.id DESC
        """,
        (user_id, user_id),
    )
    projects = []
    for row in rows:
        if row["team_id"] is not None:
            permissions = parse_team_permissions(row["member_permissions"], row["member_role"])
            if not permissions.get("view"):
                continue
            extra = {
                "scope": "team",
                "team_id": row["team_id"],
                "team_name": row["team_name"],
                "permissions": permissions,
            }
        else:
            extra = None
        projects.append(format_site_project(dict(row), current, extra))
    return projects


def remove_site_project(user_id, project_id):
    row = query_db(
        """
        SELECT w.id, w.path, w.team_id
        FROM website_workspaces w
        LEFT JOIN team_members m ON m.team_id = w.team_id AND m.user_id = ?
        WHERE w.id = ?
          AND ((w.team_id IS NULL AND w.user_id = ?) OR (w.team_id IS NOT NULL AND m.user_id IS NOT NULL))
        """,
        (user_id, project_id, user_id),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.project_not_found"))
    if row["team_id"] is not None:
        _team, membership = require_team_membership(row["team_id"], user_id)
        if not membership["permissions"].get("manage"):
            raise TeamAccessDenied(translate("flash.team_permission_denied"))
        execute_db("DELETE FROM website_workspaces WHERE id = ?", (row["id"],))
    else:
        execute_db(
            "DELETE FROM website_workspaces WHERE id = ? AND user_id = ?",
            (project_id, user_id),
        )
    directory = get_site_directory(user_id)
    if directory and os.path.realpath(directory["path"]) == os.path.realpath(row["path"]):
        execute_db("DELETE FROM website_directories WHERE user_id = ?", (user_id,))


BRAND_TEXT_LIMITS = {
    "business_name": 120,
    "tagline": 200,
    "services": 2000,
    "audience": 1000,
    "tone": 500,
    "phone": 60,
    "email": 120,
    "address": 300,
    "website": 200,
    "notes": 2000,
}
BRAND_COLOR_KEYS = ("primary", "secondary", "accent")
BRAND_FONT_KEYS = ("headings", "body")


def default_site_brand():
    return {
        "business_name": "",
        "tagline": "",
        "services": "",
        "audience": "",
        "tone": "",
        "colors": {key: "" for key in BRAND_COLOR_KEYS},
        "fonts": {key: "" for key in BRAND_FONT_KEYS},
        "phone": "",
        "email": "",
        "address": "",
        "website": "",
        "notes": "",
        "logo": "",
    }


def parse_site_brand(raw):
    brand = default_site_brand()
    if not raw:
        return brand
    try:
        stored = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return brand
    if not isinstance(stored, dict):
        return brand
    for key, limit in BRAND_TEXT_LIMITS.items():
        value = stored.get(key)
        if isinstance(value, str):
            brand[key] = value.strip()[:limit]
    colors = stored.get("colors")
    if isinstance(colors, dict):
        for key in BRAND_COLOR_KEYS:
            if isinstance(colors.get(key), str):
                brand["colors"][key] = colors[key].strip()[:32]
    fonts = stored.get("fonts")
    if isinstance(fonts, dict):
        for key in BRAND_FONT_KEYS:
            if isinstance(fonts.get(key), str):
                brand["fonts"][key] = fonts[key].strip()[:80]
    logo = stored.get("logo")
    if isinstance(logo, str):
        brand["logo"] = logo.strip()[:128]
    return brand


def clean_site_brand_update(payload, existing):
    if not isinstance(payload, dict):
        raise ValueError(translate("flash.site_brand_invalid"))
    brand = parse_site_brand(json.dumps(existing))
    for key, limit in BRAND_TEXT_LIMITS.items():
        if key in payload and payload[key] is not None:
            brand[key] = str(payload[key]).strip()[:limit]
    colors = payload.get("colors")
    if isinstance(colors, dict):
        for key in BRAND_COLOR_KEYS:
            if key in colors and colors[key] is not None:
                brand["colors"][key] = str(colors[key]).strip()[:32]
    fonts = payload.get("fonts")
    if isinstance(fonts, dict):
        for key in BRAND_FONT_KEYS:
            if key in fonts and fonts[key] is not None:
                brand["fonts"][key] = str(fonts[key]).strip()[:80]
    return brand


def serialize_site_brand(brand):
    payload = parse_site_brand(json.dumps(brand))
    logo = payload.get("logo") or ""
    payload["logo_url"] = f"/uploads/brand-logos/{logo}" if logo else ""
    return payload


def brand_prompt_block(brand):
    brand = parse_site_brand(json.dumps(brand or {}))
    lines = []
    business = brand["business_name"]
    if business:
        headline = business
        if brand["tagline"]:
            headline += f" — {brand['tagline']}"
        lines.append(f"- Business: {headline}")
    if brand["services"]:
        lines.append(f"- Services and products: {brand['services']}")
    if brand["audience"]:
        lines.append(f"- Target audience: {brand['audience']}")
    if brand["tone"]:
        lines.append(f"- Tone of voice: {brand['tone']}")
    colors = [f"{key} {brand['colors'][key]}" for key in BRAND_COLOR_KEYS if brand["colors"][key]]
    if colors:
        lines.append(f"- Brand colors: {', '.join(colors)}")
    fonts = [f"{key} {brand['fonts'][key]}" for key in BRAND_FONT_KEYS if brand["fonts"][key]]
    if fonts:
        lines.append(f"- Typography: {', '.join(fonts)}")
    contact = [brand[key] for key in ("phone", "email", "address", "website") if brand[key]]
    if contact:
        lines.append(f"- Contact details: {'; '.join(contact)}")
    if brand["notes"]:
        lines.append(f"- Notes: {brand['notes']}")
    if not lines:
        return ""
    return "Brand context for this website (apply it to copy, pages, and creatives):\n" + "\n".join(lines)


def brand_image_style_suffix(brand):
    brand = parse_site_brand(json.dumps(brand or {}))
    parts = []
    colors = [brand["colors"][key] for key in BRAND_COLOR_KEYS if brand["colors"][key]]
    if colors:
        parts.append(f"brand colors {', '.join(colors)}")
    if brand["tone"]:
        parts.append(f"{brand['tone']} mood")
    if brand["business_name"]:
        parts.append(f"for {brand['business_name']}")
    if not parts:
        return ""
    return "Brand style: " + ", ".join(parts) + "."


def get_workspace_for_path(user_id, real_path):
    return query_db(
        """
        SELECT w.*
        FROM website_workspaces w
        LEFT JOIN team_members m ON m.team_id = w.team_id AND m.user_id = ?
        WHERE w.path = ?
          AND ((w.team_id IS NULL AND w.user_id = ?) OR (w.team_id IS NOT NULL AND m.user_id IS NOT NULL))
        ORDER BY CASE WHEN w.team_id IS NULL THEN 1 ELSE 0 END, w.id ASC
        """,
        (user_id, real_path, user_id),
        one=True,
    )


def get_current_workspace(user_id):
    directory = get_site_directory(user_id)
    if not directory:
        return None
    return get_workspace_for_path(user_id, os.path.realpath(directory["path"]))


def workspace_visible_to_user(workspace_id, user_id):
    try:
        workspace_id = int(workspace_id)
    except (TypeError, ValueError):
        return False
    row = query_db(
        """
        SELECT w.id
        FROM website_workspaces w
        LEFT JOIN team_members m ON m.team_id = w.team_id AND m.user_id = ?
        WHERE w.id = ?
          AND ((w.team_id IS NULL AND w.user_id = ?) OR (w.team_id IS NOT NULL AND m.user_id IS NOT NULL))
        """,
        (user_id, workspace_id, user_id),
        one=True,
    )
    return row is not None


def current_workspace_brand(user_id):
    workspace = get_current_workspace(user_id)
    if not workspace:
        return default_site_brand()
    return parse_site_brand(workspace["brand_json"])


def current_workspace_brand_text(user_id):
    return brand_prompt_block(current_workspace_brand(user_id))


def current_workspace_gsc_property(user_id):
    workspace = get_current_workspace(user_id)
    if not workspace:
        return ""
    return workspace["gsc_property"] or ""


INTELLIGENCE_MAX_PAGES = 10
INTELLIGENCE_MAX_PAGE_CHARS = 1200
INTELLIGENCE_MAX_PROMPT_CHARS = 6000


class _SiteTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.chunks = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip:
            return
        text = (data or "").strip()
        if text:
            self.chunks.append(text)


def extract_visible_page_text(page_text, max_chars=INTELLIGENCE_MAX_PAGE_CHARS):
    extractor = _SiteTextExtractor()
    try:
        extractor.feed(page_text or "")
        extractor.close()
    except (ValueError, TypeError):
        pass
    joined = " ".join(extractor.chunks)
    joined = re.sub(r"\s+", " ", joined).strip()
    if len(joined) > max_chars:
        joined = joined[:max_chars].rsplit(" ", 1)[0]
    return joined


def extract_meta_description(page_text):
    match = re.search(
        r'<meta\s+[^>]*name=["\']description["\'][^>]*content=["\']([^"\']+)["\']',
        page_text or "",
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()[:300]
    match = re.search(
        r'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*name=["\']description["\']',
        page_text or "",
        re.IGNORECASE,
    )
    return match.group(1).strip()[:300] if match else ""


def summarize_site_pages(real_path, max_pages=INTELLIGENCE_MAX_PAGES):
    try:
        manifest = build_workspace_manifest(real_path)
    except (ValueError, OSError):
        return []
    pages = sorted(
        path
        for path, item in manifest.items()
        if item.get("kind") == "file" and posixpath.splitext(path)[1].lower() in (".htm", ".html")
    )

    def _page_priority(path):
        name = posixpath.basename(path).lower()
        if name in ("index.html", "index.htm"):
            return (0, path)
        return (1, path)

    summaries = []
    for relpath in sorted(pages, key=_page_priority)[:max_pages]:
        absolute_path = os.path.join(real_path, *relpath.split("/"))
        try:
            if os.path.getsize(absolute_path) > HEALTH_MAX_PARSE_BYTES:
                continue
            with open(absolute_path, "r", encoding="utf-8", errors="replace") as handle:
                page_text = handle.read()
        except OSError:
            continue
        inspector = inspect_site_page_text(page_text)
        try:
            updated_at = datetime.fromtimestamp(os.path.getmtime(absolute_path)).strftime("%Y-%m-%d")
        except OSError:
            updated_at = ""
        summaries.append(
            {
                "path": relpath,
                "title": (inspector.title or "").strip()[:160],
                "heading": (inspector.h1 or "").strip()[:160],
                "description": extract_meta_description(page_text),
                "excerpt": extract_visible_page_text(page_text),
                "updated": updated_at,
            }
        )
    return summaries


def build_site_intelligence(user_id):
    """Combined context shared by every AI feature: brand, pages, health, calendar.

    This is the glue that makes the whole app work as one: the site analysis,
    the AI assistant, and the social suggestions all read the same snapshot.
    """
    directory = get_site_directory(user_id)
    if not directory:
        return {"has_site": False}
    real_path = os.path.realpath(directory["path"])
    workspace = get_current_workspace(user_id)
    brand = parse_site_brand(workspace["brand_json"]) if workspace else default_site_brand()
    findings = query_db(
        "SELECT check_type, severity, page, detail FROM site_findings"
        " WHERE directory_path = ? AND status = 'open'"
        " ORDER BY CASE WHEN severity = 'error' THEN 0 ELSE 1 END, page ASC LIMIT 25",
        (real_path,),
    )
    try:
        events = [event for event in list_calendar_events(user_id) if event.get("status") in ("scheduled", "active")][:5]
    except (ValueError, sqlite3.OperationalError):
        events = []
    try:
        history = list_update_history(user_id)[:5]
    except (ValueError, sqlite3.OperationalError):
        history = []
    return {
        "has_site": True,
        "site_name": (workspace["display_name"] if workspace else "") or os.path.basename(real_path.rstrip(os.sep)),
        "client_name": workspace["client_name"] if workspace else "",
        "brand": serialize_site_brand(brand),
        "pages": summarize_site_pages(real_path),
        "open_issues": [
            {
                "check": row["check_type"],
                "severity": row["severity"],
                "page": row["page"],
                "detail": (row["detail"] or "")[:160],
            }
            for row in findings
        ],
        "open_issue_count": len(findings),
        "upcoming_events": [
            {"title": event.get("title"), "kind": event.get("kind"), "starts_on": event.get("starts_on")}
            for event in events
        ],
        "recent_updates": [
            {"summary": str(item.get("summary") or "")[:160], "status": item.get("status")}
            for item in history
            if str(item.get("summary") or "").strip()
        ],
    }


def site_intelligence_prompt_block(user_id, max_chars=INTELLIGENCE_MAX_PROMPT_CHARS):
    intelligence = build_site_intelligence(user_id)
    if not intelligence.get("has_site"):
        return ""
    lines = [f"Website under management: {intelligence.get('site_name') or 'connected site'}."]
    brand_text = brand_prompt_block(intelligence.get("brand") or {})
    if brand_text:
        lines.append(brand_text)
    pages = intelligence.get("pages") or []
    if pages:
        lines.append("Site pages (use their real content for copy, posts, and fixes):")
        for page in pages:
            label = page["title"] or page["heading"] or page["path"]
            lines.append(f"- {page['path']}: {label}")
            if page.get("description"):
                lines.append(f"  Meta: {page['description']}")
            if page.get("excerpt"):
                lines.append(f"  Content: {page['excerpt']}")
    issues = intelligence.get("open_issues") or []
    if issues:
        lines.append(f"Open site issues ({len(issues)} shown):")
        for issue in issues[:12]:
            lines.append(f"- [{issue['severity']}] {issue['check']} on {issue['page']}: {issue['detail']}")
    events = intelligence.get("upcoming_events") or []
    if events:
        lines.append("Upcoming calendar events:")
        for event in events:
            lines.append(f"- {event.get('kind')}: {event.get('title')} ({event.get('starts_on') or 'no date'})")
    block = "\n".join(lines)
    if len(block) > max_chars:
        block = block[:max_chars].rsplit("\n", 1)[0]
    return block


def serialize_site_settings(user_id, workspace):
    brand = parse_site_brand(workspace["brand_json"])
    try:
        require_project_permission(user_id, "edit")
        can_edit = True
    except TeamAccessDenied:
        can_edit = False
    return {
        "id": workspace["id"],
        "path": workspace["path"],
        "name": os.path.basename(workspace["path"].rstrip(os.sep)) or workspace["path"],
        "display_name": workspace["display_name"] or "",
        "client_name": workspace["client_name"] or "",
        "scope": "team" if workspace["team_id"] is not None else "personal",
        "team_id": workspace["team_id"],
        "brand": serialize_site_brand(brand),
        "gsc_property": workspace["gsc_property"] or "",
        "images": list_generated_images(user_id, workspace_id=workspace["id"]),
        "can_edit": can_edit,
    }


def get_site_settings(user_id):
    workspace = get_current_workspace(user_id)
    if not workspace:
        raise ValueError(translate("flash.site_directory_unmapped"))
    require_project_permission(user_id, "view")
    return serialize_site_settings(user_id, dict(workspace))


def update_site_settings(user_id, display_name=None, client_name=None, brand=None, gsc_property=None):
    workspace = get_current_workspace(user_id)
    if not workspace:
        raise ValueError(translate("flash.site_directory_unmapped"))
    require_project_permission(user_id, "edit")
    updates = {}
    if display_name is not None:
        updates["display_name"] = str(display_name).strip()[:80]
    if client_name is not None:
        updates["client_name"] = str(client_name).strip()[:80]
    if gsc_property is not None:
        updates["gsc_property"] = str(gsc_property).strip()[:300]
    if brand is not None:
        merged = clean_site_brand_update(brand, parse_site_brand(workspace["brand_json"]))
        updates["brand_json"] = json.dumps(merged)
    if updates:
        assignments = ", ".join(f"{column} = ?" for column in updates)
        execute_db(
            f"UPDATE website_workspaces SET {assignments} WHERE id = ?",
            (*updates.values(), workspace["id"]),
        )
    return get_site_settings(user_id)


def brand_logo_directory():
    directory = os.path.join(UPLOAD_DIR, "brand-logos")
    os.makedirs(directory, exist_ok=True)
    return directory


def save_site_logo(user_id, upload):
    workspace = get_current_workspace(user_id)
    if not workspace:
        raise ValueError(translate("flash.site_directory_unmapped"))
    require_project_permission(user_id, "edit")
    filename = (upload.filename or "") if upload else ""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in {"png", "jpg", "jpeg", "webp", "gif"}:
        raise ValueError(translate("flash.avatar_invalid"))
    if not upload or not uploaded_image_matches_extension(upload, extension):
        raise ValueError(translate("flash.avatar_invalid"))
    directory = brand_logo_directory()
    logo_filename = f"site-{workspace['id']}-{secrets.token_hex(8)}.{extension}"
    upload.save(os.path.join(directory, logo_filename))
    brand = parse_site_brand(workspace["brand_json"])
    previous = brand.get("logo") or ""
    if previous and previous != logo_filename:
        try:
            os.remove(os.path.join(directory, posixpath.basename(previous)))
        except OSError:
            pass
    brand["logo"] = logo_filename
    execute_db(
        "UPDATE website_workspaces SET brand_json = ? WHERE id = ?",
        (json.dumps(brand), workspace["id"]),
    )
    return get_site_settings(user_id)


def brand_logo_visible_to_user(filename, user_id):
    safe_name = posixpath.basename(filename or "")
    if not safe_name.startswith("site-"):
        return False
    try:
        workspace_id = int(safe_name.split("-", 2)[1])
    except (IndexError, TypeError, ValueError):
        return False
    return workspace_visible_to_user(workspace_id, user_id)


def record_generated_image(user_id, filename, prompt=""):
    workspace = get_current_workspace(user_id)
    try:
        execute_db(
            "INSERT INTO site_images (user_id, workspace_id, filename, prompt) VALUES (?, ?, ?, ?)",
            (user_id, workspace["id"] if workspace else None, filename, (prompt or "")[:500]),
        )
    except sqlite3.IntegrityError:
        pass


def site_image_visible_to_user(filename, user_id):
    safe_name = posixpath.basename(filename or "")
    if safe_name.startswith(f"user-{user_id}-"):
        return True
    row = query_db(
        "SELECT workspace_id FROM site_images WHERE filename = ?", (safe_name,), one=True
    )
    if not row or not row["workspace_id"]:
        return False
    return workspace_visible_to_user(row["workspace_id"], user_id)


PREVIEW_SELECTION_KEY = "preview_selection"
PREVIEW_IMAGE_EXTENSIONS = {".gif", ".ico", ".jpeg", ".jpg", ".png", ".svg", ".webp"}


def clean_preview_selection(user_id, payload):
    payload = payload or {}
    page = str(payload.get("page") or "").replace("\\", "/").strip().strip("/")[:300]
    selector = str(payload.get("selector") or "").strip()[:500]
    if not page or not selector:
        raise ValueError(translate("site.file_missing"))
    try:
        absolute_path = resolve_site_file(user_id, page)
    except ValueError:
        raise ValueError(translate("site.file_missing")) from None
    if not os.path.isfile(absolute_path):
        raise ValueError(translate("site.file_missing"))
    return {
        "page": page,
        "selector": selector,
        "tag": str(payload.get("tag") or "").strip()[:40],
        "text": str(payload.get("text") or "").strip()[:500],
        "html": str(payload.get("html") or "").strip()[:2000],
        "image_src": str(payload.get("image_src") or "").strip()[:500],
    }


def selection_prompt_block(selection):
    if not selection:
        return ""
    lines = [
        "Targeted visual change (the user selected this element in the page preview):",
        f"- Page file: {selection.get('page')}",
        f"- Element selector: {selection.get('selector')}",
    ]
    tag = (selection.get("tag") or "").upper()
    text = selection.get("text") or ""
    if tag or text:
        lines.append(f"- Element: <{tag or '?'}> with visible text {text[:200]!r}")
    html_excerpt = selection.get("html") or ""
    if html_excerpt:
        lines.append(f"- Element HTML: {html_excerpt[:1500]}")
    image_src = selection.get("image_src") or ""
    if image_src:
        lines.append(f"- Element image source: {image_src}")
    lines.append(
        f"Apply the user's request to this element or its section. Prefer editing {selection.get('page')}; leave the rest of the site unchanged."
    )
    return "\n".join(lines)


def inject_preview_picker(html_text, page=""):
    hint = translate("site.preview_picker_hint").replace('"', "")
    safe_page = (page or "").replace("\\", "/").strip().strip("/").replace('"', "")
    tag = (
        f'<script id="oneboard-picker" src="/static/js/preview-picker.js"'
        f' data-hint="{hint}" data-page="{safe_page}" data-active="0"></script>'
    )
    if re.search(r"</body\s*>", html_text, re.IGNORECASE):
        return re.sub(r"</body\s*>", f"{tag}</body>", html_text, count=1, flags=re.IGNORECASE)
    return f"{html_text}{tag}"


def serve_workspace_preview_file(user_id, filepath, picker=False):
    absolute_path = resolve_site_file(user_id, filepath or "")
    if not os.path.isfile(absolute_path):
        raise ValueError(translate("site.file_missing"))
    mime_type = mimetypes.guess_type(absolute_path)[0] or "application/octet-stream"
    extension = os.path.splitext(absolute_path)[1].lower()
    if picker and extension in {".htm", ".html"}:
        with open(absolute_path, "r", encoding="utf-8", errors="replace") as handle:
            html_text = handle.read()
        return Response(inject_preview_picker(html_text, filepath), mimetype="text/html")
    return send_file(absolute_path, mimetype=mime_type)


def read_snapshot_member(snapshot_path, filepath):
    if not snapshot_path or not os.path.isfile(snapshot_path):
        return None
    normalized = (filepath or "").replace("\\", "/").strip().strip("/")
    if not normalized or normalized.startswith("/") or contains_parent_reference(normalized):
        return None
    if relative_path_has_reserved_component(normalized):
        return None
    try:
        with zipfile.ZipFile(snapshot_path, "r") as archive:
            try:
                info = archive.getinfo(normalized)
            except KeyError:
                return None
            if info.is_dir() or info.file_size > 10 * 1024 * 1024:
                return None
            return archive.read(normalized)
    except (zipfile.BadZipFile, OSError):
        return None


def compare_file_kind(path):
    extension = os.path.splitext(path or "")[1].lower()
    if extension in {".htm", ".html"} or extension in PREVIEW_IMAGE_EXTENSIONS:
        return "visual"
    if is_text_file(path or ""):
        return "text"
    return "binary"


def build_update_compare(user_id, update_id):
    update = require_update_for_current_directory(user_id, update_id)
    require_project_permission(user_id, "view")
    files = []
    for item in update.get("files") or []:
        path = item.get("path") or ""
        change = item.get("change") or "modified"
        before_url = None
        after_url = None
        if change != "created" and update.get("snapshot_path"):
            before_url = url_for(
                "site_manager_update_before_file", update_id=update["id"], filepath=path
            )
        if change != "deleted":
            after_url = url_for("site_manager_preview_file", filepath=path)
        files.append(
            {
                "path": path,
                "change": change,
                "kind": compare_file_kind(path),
                "before_url": before_url,
                "after_url": after_url,
            }
        )
    return {
        "update": {
            "id": update["id"],
            "source": update.get("source"),
            "summary": update.get("summary"),
            "status": update.get("status"),
            "created_at": update.get("created_at"),
            "author_name": update.get("author_name"),
        },
        "files": files,
    }


HEALTH_MAX_FILES = 300
HEALTH_MAX_EXTERNAL_URLS = 25
HEALTH_EXTERNAL_TIMEOUT = 6
HEALTH_HEAVY_IMAGE_BYTES = 500 * 1024
HEALTH_MAX_PARSE_BYTES = 2 * 1024 * 1024


class _SiteHtmlInspector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = None
        self.h1 = None
        self.links = []
        self.images = []
        self.forms = []
        self._in_title = False
        self._in_h1 = False
        self._title_chunks = []
        self._h1_chunks = []
        self._link_stack = []
        self._form_stack = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "title" and self.title is None:
            self._in_title = True
            self._title_chunks = []
        if tag == "h1" and self.h1 is None:
            self._in_h1 = True
            self._h1_chunks = []
        if tag == "a":
            self._link_stack.append({"href": attributes.get("href", ""), "text": ""})
        if tag == "img":
            self.images.append(
                {
                    "src": attributes.get("src", ""),
                    "alt": attributes.get("alt"),
                    "occurrence": sum(1 for item in self.images if item["src"] == attributes.get("src", "")),
                }
            )
        if tag == "form":
            self._form_stack.append(
                {
                    "action": attributes.get("action", ""),
                    "method": (attributes.get("method", "") or "get").lower(),
                    "inputs": [],
                    "has_submit": False,
                    "index": len(self.forms),
                }
            )
        if tag in ("input", "select", "textarea") and self._form_stack:
            form = self._form_stack[-1]
            field_type = (attributes.get("type", "") or "").lower()
            if tag == "input" and field_type in ("submit", "image"):
                form["has_submit"] = True
                return
            form["inputs"].append(
                {
                    "tag": tag,
                    "type": field_type,
                    "name": attributes.get("name"),
                    "id": attributes.get("id", ""),
                    "placeholder": attributes.get("placeholder", ""),
                }
            )
        if tag == "button" and self._form_stack:
            button_type = (attributes.get("type", "") or "submit").lower()
            if button_type not in ("button", "reset"):
                self._form_stack[-1]["has_submit"] = True

    def handle_endtag(self, tag):
        if tag == "title" and self._in_title:
            self.title = "".join(self._title_chunks).strip()
            self._in_title = False
        if tag == "h1" and self._in_h1:
            self.h1 = "".join(self._h1_chunks).strip()
            self._in_h1 = False
        if tag == "a" and self._link_stack:
            link = self._link_stack.pop()
            link["text"] = link["text"].strip()
            link["occurrence"] = sum(
                1 for item in self.links if item["href"] == link["href"]
            )
            self.links.append(link)
        if tag == "form" and self._form_stack:
            self.forms.append(self._form_stack.pop())

    def handle_data(self, data):
        if self._in_title:
            self._title_chunks.append(data)
        if self._in_h1:
            self._h1_chunks.append(data)
        if self._link_stack:
            self._link_stack[-1]["text"] += data


def finding_fingerprint(*parts):
    joined = "\x00".join(str(part or "") for part in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()


def slugify_field_name(value, fallback):
    slug = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return (slug or fallback)[:40]


def pretty_name_from_filename(path):
    stem = posixpath.splitext(posixpath.basename(path or ""))[0]
    if stem.lower() == "index":
        return "Home"
    words = re.sub(r"[-_]+", " ", stem).strip()
    return words[:60].title() or stem[:60]


def suggest_page_title(page, h1, brand):
    base = (h1 or "").strip()[:100] or pretty_name_from_filename(page)
    business = (brand.get("business_name") or "").strip()
    if business and business.lower() not in base.lower():
        base = f"{base} | {business}"
    return base[:140]


def split_link_reference(href):
    candidate = (href or "").strip()
    if not candidate:
        return ("skip", "")
    lowered = candidate.lower()
    if lowered.startswith(("#", "mailto:", "tel:", "sms:", "javascript:", "data:", "blob:")):
        return ("skip", "")
    if lowered.startswith("//"):
        return ("external", f"https:{candidate}")
    if lowered.startswith(("http://", "https://")):
        return ("external", candidate)
    target = candidate.split("?", 1)[0].split("#", 1)[0].strip()
    if not target:
        return ("skip", "")
    return ("internal", target)


def resolve_internal_reference(page, reference):
    base = posixpath.dirname(page or "")
    return posixpath.normpath(posixpath.join(base, reference.lstrip("/")))


def external_error_detail(error, fallback_code=None):
    if isinstance(error, (TimeoutError, socket.timeout)):
        return "timeout"
    reason = getattr(error, "reason", None)
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(reason, str) and reason:
        return reason[:120]
    if isinstance(error, ssl.SSLError):
        return "TLS error"
    if fallback_code:
        return f"HTTP {fallback_code}"
    text = str(error).strip()
    return (text[:120] if text else "unreachable")


def check_external_url(url, timeout=HEALTH_EXTERNAL_TIMEOUT):
    headers = {"User-Agent": "ONEBoard-health/1.0"}
    try:
        request = urllib.request.Request(url, method="HEAD", headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            return (True, "") if status < 400 else (False, f"HTTP {status}")
    except urllib.error.HTTPError as error:
        if error.code in (403, 405):
            try:
                request = urllib.request.Request(
                    url, headers={**headers, "Range": "bytes=0-0"}
                )
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    status = getattr(response, "status", 200)
                    return (True, "") if status < 400 else (False, f"HTTP {status}")
            except Exception as retry_error:
                return (False, external_error_detail(retry_error, error.code))
        return (False, f"HTTP {error.code}")
    except Exception as error:
        return (False, external_error_detail(error))


def inspect_site_page_text(page_text):
    inspector = _SiteHtmlInspector()
    try:
        inspector.feed(page_text)
        inspector.close()
    except (ValueError, TypeError):
        pass
    while inspector._link_stack:
        link = inspector._link_stack.pop()
        link["occurrence"] = sum(1 for item in inspector.links if item["href"] == link["href"])
        inspector.links.append(link)
    while inspector._form_stack:
        inspector.forms.append(inspector._form_stack.pop())
    return inspector


def collect_site_health_findings(real_path, manifest, brand, skip_external=False):
    files = sorted(path for path, item in manifest.items() if item.get("kind") == "file")
    files = files[:HEALTH_MAX_FILES]
    file_set = set(files)
    collected = []
    externals = []

    for relpath in files:
        extension = posixpath.splitext(relpath)[1].lower()
        if extension not in (".htm", ".html"):
            continue
        absolute_path = os.path.join(real_path, *relpath.split("/"))
        try:
            if os.path.getsize(absolute_path) > HEALTH_MAX_PARSE_BYTES:
                continue
            with open(absolute_path, "r", encoding="utf-8", errors="replace") as handle:
                page_text = handle.read()
        except OSError:
            continue
        inspector = inspect_site_page_text(page_text)
        if not inspector.title:
            collected.append(
                {
                    "check": "missing_title",
                    "severity": "warning",
                    "page": relpath,
                    "detail": relpath,
                    "proposal": {"title": suggest_page_title(relpath, inspector.h1, brand)},
                    "fingerprint": finding_fingerprint("missing_title", relpath),
                }
            )
        for link in inspector.links:
            kind, target = split_link_reference(link["href"])
            if kind == "skip":
                continue
            if kind == "external":
                if not skip_external and len(externals) < HEALTH_MAX_EXTERNAL_URLS:
                    externals.append((relpath, link["occurrence"], target))
                continue
            resolved = resolve_internal_reference(relpath, target)
            if resolved in file_set or posixpath.join(resolved, "index.html") in file_set:
                continue
            collected.append(
                {
                    "check": "broken_internal_link",
                    "severity": "error",
                    "page": relpath,
                    "detail": link["href"][:300],
                    "proposal": {"action": "unlink", "href": link["href"][:300], "occurrence": link["occurrence"]},
                    "fingerprint": finding_fingerprint("broken_internal_link", relpath, link["href"], link["occurrence"]),
                }
            )
        for image in inspector.images:
            src = (image["src"] or "").strip()
            if not src or image.get("alt"):
                continue
            kind, _target = split_link_reference(src)
            if kind == "external":
                continue
            collected.append(
                {
                    "check": "missing_alt",
                    "severity": "warning",
                    "page": relpath,
                    "detail": src[:300],
                    "proposal": {
                        "alt": pretty_name_from_filename(src),
                        "src": src[:300],
                        "occurrence": image["occurrence"],
                    },
                    "fingerprint": finding_fingerprint("missing_alt", relpath, src, image["occurrence"]),
                }
            )
        for form in inspector.forms:
            action = (form["action"] or "").strip()
            if not action or action.startswith("#"):
                collected.append(
                    {
                        "check": "form_no_action",
                        "severity": "error",
                        "page": relpath,
                        "detail": f"form #{form['index'] + 1}",
                        "proposal": {"guidance": "site.guide_form_action"},
                        "fingerprint": finding_fingerprint("form_no_action", relpath, form["index"]),
                    }
                )
            elif split_link_reference(action)[0] == "internal":
                resolved = resolve_internal_reference(relpath, split_link_reference(action)[1])
                if resolved not in file_set:
                    collected.append(
                        {
                            "check": "form_no_action",
                            "severity": "error",
                            "page": relpath,
                            "detail": f"form #{form['index'] + 1} → {action[:200]}",
                            "proposal": {"guidance": "site.guide_form_action"},
                            "fingerprint": finding_fingerprint("form_no_action", relpath, form["index"], action),
                        }
                    )
            if not form["has_submit"]:
                collected.append(
                    {
                        "check": "form_no_submit",
                        "severity": "warning",
                        "page": relpath,
                        "detail": f"form #{form['index'] + 1}",
                        "proposal": {"guidance": "site.guide_form_submit"},
                        "fingerprint": finding_fingerprint("form_no_submit", relpath, form["index"]),
                    }
                )
            nameless_index = 0
            for field in form["inputs"]:
                if field.get("name"):
                    continue
                if field["tag"] == "input" and field["type"] in ("submit", "button", "image", "reset"):
                    continue
                proposal_name = slugify_field_name(
                    field["id"] or field["placeholder"], f"field_{nameless_index + 1}"
                )
                collected.append(
                    {
                        "check": "form_input_name",
                        "severity": "warning",
                        "page": relpath,
                        "detail": (field["id"] or field["placeholder"] or field["tag"])[:120],
                        "proposal": {
                            "name": proposal_name,
                            "occurrence": nameless_index,
                            "form_index": form["index"],
                        },
                        "fingerprint": finding_fingerprint(
                            "form_input_name", relpath, form["index"], nameless_index,
                            field["id"], field["placeholder"],
                        ),
                    }
                )
                nameless_index += 1

    for relpath in files:
        if posixpath.splitext(relpath)[1].lower() not in PREVIEW_IMAGE_EXTENSIONS:
            continue
        absolute_path = os.path.join(real_path, *relpath.split("/"))
        try:
            size_bytes = os.path.getsize(absolute_path)
        except OSError:
            continue
        if size_bytes > HEALTH_HEAVY_IMAGE_BYTES:
            collected.append(
                {
                    "check": "heavy_image",
                    "severity": "warning",
                    "page": relpath,
                    "detail": f"{relpath} ({format_bytes(size_bytes)})",
                    "proposal": {"action": "optimize"},
                    "fingerprint": finding_fingerprint("heavy_image", relpath),
                }
            )

    if externals and not skip_external:
        with ThreadPoolExecutor(max_workers=5) as pool:
            checks = list(pool.map(lambda item: (item, check_external_url(item[2])), externals))
        for (page, occurrence, url), (ok, detail) in checks:
            if ok:
                continue
            collected.append(
                {
                    "check": "broken_external_link",
                    "severity": "warning",
                    "page": page,
                    "detail": f"{url[:300]} ({detail})" if detail else url[:300],
                    "proposal": {"action": "unlink", "href": url[:300], "occurrence": occurrence, "guidance": "site.guide_external"},
                    "fingerprint": finding_fingerprint("broken_external_link", page, url, occurrence),
                }
            )

    return collected, len(files)


def serialize_site_finding(row):
    finding = dict(row)
    finding["check"] = finding.pop("check_type", "")
    try:
        finding["proposal"] = json.loads(row["proposal"] or "{}")
    except (TypeError, json.JSONDecodeError):
        finding["proposal"] = {}
    return finding


def get_site_health(user_id):
    directory = require_site_directory(user_id)
    real_path = os.path.realpath(directory["path"])
    require_project_permission(user_id, "view")
    rows = query_db(
        """
        SELECT * FROM site_findings
        WHERE directory_path = ? AND status = 'open'
        ORDER BY CASE WHEN severity = 'error' THEN 0 ELSE 1 END, page ASC, id ASC
        """,
        (real_path,),
    )
    ignored = query_db(
        "SELECT * FROM site_findings WHERE directory_path = ? AND status = 'ignored' ORDER BY page ASC, id ASC",
        (real_path,),
    )
    last_scan = query_db(
        "SELECT * FROM site_scans WHERE directory_path = ? ORDER BY id DESC LIMIT 1",
        (real_path,),
        one=True,
    )
    try:
        require_project_permission(user_id, "edit")
        can_edit = True
    except TeamAccessDenied:
        can_edit = False
    return {
        "findings": [serialize_site_finding(row) for row in rows],
        "ignored": [serialize_site_finding(row) for row in ignored],
        "ignored_count": len(ignored),
        "open_count": len(rows),
        "last_scan": dict(last_scan) if last_scan else None,
        "can_edit": can_edit,
    }


def sidebar_badge_counts():
    empty = {
        "health_open": 0,
        "requests_open": 0,
        "inbox_new": 0,
        "alerts_open": 0,
        "notifications_unread": 0,
    }
    try:
        if not has_request_context() or g.get("user") is None:
            return dict(empty)
        user_id = g.user["id"]
        return {
            "health_open": get_health_summary(user_id)["open_count"],
            "requests_open": count_open_client_requests(user_id),
            "inbox_new": count_new_contact_messages(user_id),
            "alerts_open": count_open_site_alerts(user_id),
            "notifications_unread": count_unread_notifications(user_id),
        }
    except (sqlite3.OperationalError, ValueError, TypeError, KeyError):
        return dict(empty)


def get_health_summary(user_id):
    directory = get_site_directory(user_id)
    if not directory:
        return {"open_count": 0, "last_scan": None}
    real_path = os.path.realpath(directory["path"])
    open_count = query_db(
        "SELECT COUNT(*) AS total FROM site_findings WHERE directory_path = ? AND status = 'open'",
        (real_path,),
        one=True,
    )["total"]
    last_scan = query_db(
        "SELECT finished_at FROM site_scans WHERE directory_path = ? ORDER BY id DESC LIMIT 1",
        (real_path,),
        one=True,
    )
    return {
        "open_count": open_count,
        "last_scan": last_scan["finished_at"] if last_scan else None,
    }


def run_site_health_scan(user_id, skip_external=False):
    directory = require_site_directory(user_id)
    real_path = os.path.realpath(directory["path"])
    require_project_permission(user_id, "view")
    scan_id = execute_db(
        "INSERT INTO site_scans (user_id, directory_path, skipped_external) VALUES (?, ?, ?)",
        (user_id, real_path, 1 if skip_external else 0),
    )
    manifest = build_workspace_manifest(real_path)
    brand = current_workspace_brand(user_id)
    collected, files_checked = collect_site_health_findings(
        real_path, manifest, brand, skip_external=skip_external
    )
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for finding in collected:
        existing = query_db(
            "SELECT id, status FROM site_findings WHERE directory_path = ? AND fingerprint = ?",
            (real_path, finding["fingerprint"]),
            one=True,
        )
        if existing is None:
            execute_db(
                """
                INSERT INTO site_findings (
                    user_id, directory_path, fingerprint, check_type, severity,
                    page, detail, proposal, status, last_seen_at, last_seen_scan_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?, ?)
                """,
                (
                    user_id,
                    real_path,
                    finding["fingerprint"],
                    finding["check"],
                    finding["severity"],
                    finding["page"],
                    finding["detail"],
                    json.dumps(finding["proposal"]),
                    now,
                    scan_id,
                ),
            )
        elif existing["status"] == "ignored":
            execute_db(
                "UPDATE site_findings SET last_seen_at = ?, last_seen_scan_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (now, scan_id, existing["id"]),
            )
        else:
            execute_db(
                """
                UPDATE site_findings
                SET user_id = ?, check_type = ?, severity = ?, page = ?, detail = ?,
                    proposal = ?, status = 'open', resolved_by = NULL, resolved_at = NULL,
                    last_seen_at = ?, last_seen_scan_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    user_id,
                    finding["check"],
                    finding["severity"],
                    finding["page"],
                    finding["detail"],
                    json.dumps(finding["proposal"]),
                    now,
                    scan_id,
                    existing["id"],
                ),
            )
    execute_db(
        """
        UPDATE site_findings
        SET status = 'resolved', resolved_by = 'scan', resolved_at = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE directory_path = ? AND status = 'open'
          AND (last_seen_scan_id IS NULL OR last_seen_scan_id <> ?)
          AND (? = 0 OR check_type <> 'broken_external_link')
        """,
        (now, real_path, scan_id, 1 if skip_external else 0),
    )
    open_count = query_db(
        "SELECT COUNT(*) AS total FROM site_findings WHERE directory_path = ? AND status = 'open'",
        (real_path,),
        one=True,
    )["total"]
    execute_db(
        "UPDATE site_scans SET finished_at = ?, files_checked = ?, open_count = ? WHERE id = ?",
        (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), files_checked, open_count, scan_id),
    )
    return get_site_health(user_id)


def set_html_title_text(html_text, title):
    title = (title or "").strip()
    if not title:
        raise ValueError(translate("flash.fix_value_required"))
    escaped = html.escape(title[:160], quote=True)
    replacement = f"<title>{escaped}</title>"
    updated, count = re.subn(
        r"<title[^>]*>.*?</title\s*>", replacement, html_text, count=1, flags=re.IGNORECASE | re.DOTALL
    )
    if count:
        return updated
    updated, count = re.subn(
        r"(<head[^>]*>)", rf"\1{replacement}", html_text, count=1, flags=re.IGNORECASE
    )
    if count:
        return updated
    updated, count = re.subn(
        r"(<html[^>]*>)", rf"\1<head>{replacement}</head>", html_text, count=1, flags=re.IGNORECASE
    )
    if count:
        return updated
    return f"<head>{replacement}</head>{html_text}"


def replace_nth_match(html_text, pattern, occurrence, replacement):
    matches = list(re.finditer(pattern, html_text, flags=re.IGNORECASE | re.DOTALL))
    if occurrence < 0 or occurrence >= len(matches):
        raise ValueError(translate("flash.finding_not_found"))
    match = matches[occurrence]
    return html_text[: match.start()] + replacement(match) + html_text[match.end() :]


def unlink_href_occurrence(html_text, href, occurrence):
    pattern = r"<a\b([^>]*?)href=([\"'])" + re.escape(href) + r"\2([^>]*?)>(.*?)</a\s*>"

    def _keep_text(match):
        return match.group(4)

    return replace_nth_match(html_text, pattern, occurrence, _keep_text)


def set_img_alt_occurrence(html_text, src, occurrence, alt):
    escaped = html.escape((alt or "").strip()[:200], quote=True)
    if not escaped:
        raise ValueError(translate("flash.fix_value_required"))
    pattern = r"<img\b[^>]*?src=([\"'])" + re.escape(src) + r"\1[^>]*?>"

    def _add_alt(match):
        tag = match.group(0)
        if re.search(r"\balt\s*=", tag, flags=re.IGNORECASE):
            raise ValueError(translate("flash.finding_not_found"))
        if tag.rstrip().endswith("/>"):
            return tag.rstrip()[:-2].rstrip() + f' alt="{escaped}"/>'
        return tag[:-1].rstrip() + f' alt="{escaped}">'

    return replace_nth_match(html_text, pattern, occurrence, _add_alt)


def set_input_name_occurrence(html_text, occurrence, name):
    name = slugify_field_name(name, "")
    if not name:
        raise ValueError(translate("flash.fix_value_required"))
    candidates = [
        match
        for match in re.finditer(r"<(?:input|select|textarea)\b[^>]*>", html_text, flags=re.IGNORECASE)
        if not re.search(r"\bname\s*=", match.group(0), flags=re.IGNORECASE)
    ]
    if occurrence < 0 or occurrence >= len(candidates):
        raise ValueError(translate("flash.finding_not_found"))
    match = candidates[occurrence]
    tag = match.group(0)
    if tag.rstrip().endswith("/>"):
        fixed = tag.rstrip()[:-2].rstrip() + f' name="{html.escape(name, quote=True)}"/>'
    else:
        fixed = tag[:-1].rstrip() + f' name="{html.escape(name, quote=True)}">'
    return html_text[: match.start()] + fixed + html_text[match.end() :]


def optimize_site_image(absolute_path):
    try:
        from PIL import Image
    except ImportError:
        raise ValueError(translate("site.guide_heavy_no_pillow")) from None
    if os.path.getsize(absolute_path) > 30 * 1024 * 1024:
        raise ValueError(translate("site.guide_heavy_no_pillow"))
    with open(absolute_path, "rb") as handle:
        original_bytes = handle.read()
    try:
        with Image.open(absolute_path) as image:
            image_format = (image.format or "").upper() or posixpath.splitext(absolute_path)[1].upper().lstrip(".")
            if max(image.size) > 1600:
                image.thumbnail((1600, 1600))
            save_kwargs = {}
            if image_format in ("JPEG", "JPG"):
                if image.mode in ("RGBA", "P", "LA"):
                    image = image.convert("RGB")
                save_kwargs = {"quality": 82, "optimize": True}
                image_format = "JPEG"
            elif image_format == "PNG":
                save_kwargs = {"optimize": True}
            elif image_format == "WEBP":
                save_kwargs = {"quality": 82}
            with tempfile.NamedTemporaryFile(delete=False, suffix=".oneboard-opt") as staged:
                staged_path = staged.name
            try:
                image.save(staged_path, image_format or "PNG", **save_kwargs)
                optimized_bytes = open(staged_path, "rb").read()
            finally:
                try:
                    os.remove(staged_path)
                except OSError:
                    pass
    except (OSError, ValueError) as error:
        raise ValueError(translate("site.guide_heavy_no_pillow")) from error
    if len(optimized_bytes) >= len(original_bytes):
        return len(original_bytes), len(original_bytes)
    with open(absolute_path, "wb") as handle:
        handle.write(optimized_bytes)
    return len(original_bytes), len(optimized_bytes)


AUTO_FIXABLE_CHECKS = frozenset(
    {
        "missing_title",
        "broken_internal_link",
        "broken_external_link",
        "missing_alt",
        "form_input_name",
        "heavy_image",
    }
)


def _apply_single_finding_fix(user_id, finding, payload):
    proposal = finding["proposal"]
    check = finding["check"]
    payload = payload or {}
    if check not in AUTO_FIXABLE_CHECKS:
        raise ValueError(translate(proposal.get("guidance") or "site.guide_form_action"))
    absolute_path = resolve_site_file(user_id, finding["page"] or "")
    if not os.path.isfile(absolute_path):
        raise ValueError(translate("flash.finding_not_found"))
    summary = ""
    if check == "missing_title":
        title = str(payload.get("title") or proposal.get("title") or "").strip()
        with open(absolute_path, "r", encoding="utf-8", errors="replace") as handle:
            updated_text = set_html_title_text(handle.read(), title)
        with open(absolute_path, "w", encoding="utf-8") as handle:
            handle.write(updated_text)
        summary = f"Action center: set page title on {finding['page']}"
    elif check in ("broken_internal_link", "broken_external_link"):
        with open(absolute_path, "r", encoding="utf-8", errors="replace") as handle:
            updated_text = unlink_href_occurrence(
                handle.read(), proposal.get("href") or "", int(proposal.get("occurrence") or 0)
            )
        with open(absolute_path, "w", encoding="utf-8") as handle:
            handle.write(updated_text)
        summary = f"Action center: removed broken link on {finding['page']}"
    elif check == "missing_alt":
        alt = str(payload.get("alt") or proposal.get("alt") or "").strip()
        with open(absolute_path, "r", encoding="utf-8", errors="replace") as handle:
            updated_text = set_img_alt_occurrence(
                handle.read(), proposal.get("src") or "", int(proposal.get("occurrence") or 0), alt
            )
        with open(absolute_path, "w", encoding="utf-8") as handle:
            handle.write(updated_text)
        summary = f"Action center: added alt text on {finding['page']}"
    elif check == "form_input_name":
        name = str(payload.get("name") or proposal.get("name") or "").strip()
        with open(absolute_path, "r", encoding="utf-8", errors="replace") as handle:
            updated_text = set_input_name_occurrence(
                handle.read(), int(proposal.get("occurrence") or 0), name
            )
        with open(absolute_path, "w", encoding="utf-8") as handle:
            handle.write(updated_text)
        summary = f"Action center: named form field on {finding['page']}"
    elif check == "heavy_image":
        before_size, after_size = optimize_site_image(absolute_path)
        if after_size >= before_size:
            summary = f"Action center: image already optimal {finding['page']}"
        else:
            summary = f"Action center: optimized image {finding['page']} ({format_bytes(before_size)} → {format_bytes(after_size)})"
    else:
        raise ValueError(translate("flash.finding_not_found"))
    return summary


def _resolve_findings(finding_ids, resolved_by="fix"):
    if not finding_ids:
        return
    placeholders = ", ".join("?" for _ in finding_ids)
    execute_db(
        f"""
        UPDATE site_findings
        SET status = 'resolved', resolved_by = ?, resolved_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP
        WHERE id IN ({placeholders})
        """,
        (resolved_by, *finding_ids),
    )


def _record_action_center_history(user_id, real_path, snapshot_path, before_manifest, summary):
    changed_files = compare_workspace_manifests(
        before_manifest, build_workspace_manifest(real_path)
    )
    record_update_history(
        user_id,
        "action-center",
        summary,
        "0",
        status="approved",
        snapshot_path=snapshot_path,
        changed_files=[{"path": item["path"], "change": item["change"]} for item in changed_files],
        diff_summary="",
        directory_path=real_path,
    )
    return changed_files


def apply_site_finding(user_id, finding_id, payload):
    directory = require_site_directory(user_id)
    real_path = os.path.realpath(directory["path"])
    require_project_permission(user_id, "edit")
    try:
        finding_id = int(finding_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.finding_not_found"))
    row = query_db(
        "SELECT * FROM site_findings WHERE id = ? AND directory_path = ? AND status = 'open'",
        (finding_id, real_path),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.finding_not_found"))
    finding = serialize_site_finding(row)
    snapshot_path = create_update_snapshot(user_id, real_path)
    before_manifest = build_workspace_manifest(real_path)
    summary = _apply_single_finding_fix(user_id, finding, payload)
    _record_action_center_history(user_id, real_path, snapshot_path, before_manifest, summary)
    _resolve_findings([finding["id"]], resolved_by="fix")
    return get_site_health(user_id)


def apply_all_site_findings(user_id):
    directory = require_site_directory(user_id)
    real_path = os.path.realpath(directory["path"])
    require_project_permission(user_id, "edit")
    rows = query_db(
        "SELECT * FROM site_findings WHERE directory_path = ? AND status = 'open'"
        " ORDER BY page ASC, id ASC",
        (real_path,),
    )
    findings = [serialize_site_finding(row) for row in rows]
    if not findings:
        raise ValueError(translate("flash.no_fixes"))
    fixable = [item for item in findings if item["check"] in AUTO_FIXABLE_CHECKS]
    skipped = [item for item in findings if item["check"] not in AUTO_FIXABLE_CHECKS]
    if not fixable:
        raise ValueError(translate("flash.no_fixes"))
    snapshot_path = create_update_snapshot(user_id, real_path)
    before_manifest = build_workspace_manifest(real_path)
    applied_ids = []
    try:
        for finding in fixable:
            _apply_single_finding_fix(user_id, finding, {})
            applied_ids.append(finding["id"])
    except (ValueError, OSError) as error:
        try:
            restore_workspace_changes(
                real_path,
                snapshot_path,
                compare_workspace_manifests(before_manifest, build_workspace_manifest(real_path)),
            )
        except (ValueError, OSError, zipfile.BadZipFile, KeyError, TypeError):
            pass
        raise error
    summary = f"Action center: applied {len(applied_ids)} automatic fixes"
    _record_action_center_history(user_id, real_path, snapshot_path, before_manifest, summary)
    _resolve_findings(applied_ids, resolved_by="fix-all")
    health = get_site_health(user_id)
    return {
        "health": health,
        "fixed": len(applied_ids),
        "skipped": len(skipped),
        "skipped_checks": sorted({item["check"] for item in skipped}),
    }


def summarize_health_with_ai(user_id, provider=None, model=None):
    health = get_site_health(user_id)
    findings = health["findings"]
    if not findings:
        raise ValueError(translate("flash.no_fixes"))
    prompt_lines = ["Open website issues to explain:"]
    for finding in findings[:30]:
        prompt_lines.append(
            f"- [{finding['severity']}] {finding['check']} on {finding['page']}: {finding['detail']}"
        )
    run = run_ai_text_task(
        user_id, "health_summary", "\n".join(prompt_lines), provider=provider, model=model
    )
    return {"summary": (run["response_text"] or "").strip(), "provider": run["provider"]}


def run_ai_health_fix(user_id, finding_ids=None, provider=None, model=None):
    directory = require_site_directory(user_id)
    real_path = os.path.realpath(directory["path"])
    require_project_permission(user_id, "edit")
    provider, model = resolve_ai_provider_model(user_id, provider=provider, model=model)
    if not get_user_ai_provider_api_key(user_id, provider):
        raise ValueError(f"No API key configured for provider '{provider}'.")
    rows = query_db(
        "SELECT * FROM site_findings WHERE directory_path = ? AND status = 'open'"
        " ORDER BY page ASC, id ASC",
        (real_path,),
    )
    findings = [serialize_site_finding(row) for row in rows]
    wanted = set()
    if finding_ids:
        for raw_id in finding_ids:
            try:
                wanted.add(int(raw_id))
            except (TypeError, ValueError):
                continue
        findings = [item for item in findings if item["id"] in wanted]
    if not findings:
        raise ValueError(translate("flash.no_fixes"))
    affected_pages = sorted({item["page"] for item in findings if item["page"]})
    site_context = []
    for relpath in affected_pages:
        try:
            absolute_path = resolve_site_file(user_id, relpath)
        except ValueError:
            continue
        if not os.path.isfile(absolute_path):
            continue
        try:
            if os.path.getsize(absolute_path) > HEALTH_MAX_PARSE_BYTES:
                continue
            with open(absolute_path, "r", encoding="utf-8", errors="replace") as handle:
                content = handle.read()
        except OSError:
            continue
        if "\x00" in content:
            continue
        site_context.append({"path": relpath, "content": content[:12000]})
    issue_lines = [
        f"- [#{item['id']}] [{item['severity']}] {item['check']} on {item['page']}: {item['detail']}"
        f" (suggested fix: {json.dumps(item['proposal'], ensure_ascii=False)})"
        for item in findings
    ]
    fix_prompt = (
        "Fix every website issue listed below by editing the affected files. "
        "For forms without destination, wire them to a sensible receiver or add a working "
        "mailto/form endpoint with a submit button; for forms without submit button, add one. "
        "Keep the design and all other content unchanged.\n\nIssues:\n" + "\n".join(issue_lines)
    )
    instruction = build_site_direct_edit_instruction(
        fix_prompt, site_context, brand_context=current_workspace_brand_text(user_id)
    )
    snapshot_path = create_update_snapshot(user_id, real_path)
    before_manifest = build_workspace_manifest(real_path)
    text, usage, resolved_model = run_ai_provider_prompt(user_id, provider, model, instruction)
    try:
        plan = parse_site_ai_update_plan(text)
        apply_site_ai_update_plan(real_path, plan)
    except ValueError as error:
        try:
            restore_workspace_changes(
                real_path,
                snapshot_path,
                compare_workspace_manifests(before_manifest, build_workspace_manifest(real_path)),
            )
        except (ValueError, OSError, zipfile.BadZipFile, KeyError, TypeError):
            pass
        save_ai_run(
            user_id, provider, resolved_model, "health_fix", instruction,
            response_text=text, status="failed", error_text=str(error), usage=usage,
        )
        raise error
    save_ai_run(
        user_id, provider, resolved_model, "health_fix", instruction,
        response_text=text, usage=usage,
    )
    summary = f"Action center: AI fix ({provider}) — {(plan.get('summary') or 'issues fixed').strip()[:200]}"
    _record_action_center_history(user_id, real_path, snapshot_path, before_manifest, summary)
    target_ids = {item["id"] for item in findings}
    health = run_site_health_scan(user_id, skip_external=True)
    still_open = {
        item["id"] for item in health["findings"] if item["id"] in target_ids
    } | {
        item["id"] for item in health["ignored"] if item["id"] in target_ids
    }
    fixed = len(target_ids - still_open)
    return {"health": health, "fixed": fixed, "pages": affected_pages, "provider": provider}


def ignore_site_finding(user_id, finding_id, ignored=True):
    directory = require_site_directory(user_id)
    real_path = os.path.realpath(directory["path"])
    require_project_permission(user_id, "edit")
    try:
        finding_id = int(finding_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.finding_not_found"))
    row = query_db(
        "SELECT id FROM site_findings WHERE id = ? AND directory_path = ?",
        (finding_id, real_path),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.finding_not_found"))
    execute_db(
        "UPDATE site_findings SET status = ?, resolved_by = NULL, resolved_at = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        ("ignored" if ignored else "open", finding_id),
    )
    return get_site_health(user_id)


REQUEST_STATUSES = ("open", "in_review", "proposed", "approved", "rejected", "done")
REQUEST_ATTACHMENT_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "pdf"}
REQUEST_ATTACHMENT_MAX_BYTES = 10 * 1024 * 1024


def require_current_request_workspace(user_id):
    workspace = get_current_workspace(user_id)
    if not workspace:
        raise ValueError(translate("flash.site_directory_unmapped"))
    return workspace


def serialize_request_link(row):
    link = dict(row)
    now = int(time.time())
    link["revoked"] = bool(link["revoked"])
    link["expired"] = bool(link["expires_at"] and link["expires_at"] <= now)
    link["active"] = not link["revoked"] and not link["expired"]
    return link


def create_request_link(user_id, label="", expires_days=None):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "manage")
    expires_at = None
    if expires_days not in (None, ""):
        try:
            days = int(str(expires_days).strip())
        except (TypeError, ValueError):
            raise ValueError(translate("flash.invalid_transition"))
        if days < 0 or days > 3650:
            raise ValueError(translate("flash.invalid_transition"))
        if days > 0:
            expires_at = int(time.time()) + days * 86400
    token = secrets.token_urlsafe(48)
    link_id = execute_db(
        """
        INSERT INTO request_links (workspace_id, label, token_hash, created_by, expires_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            workspace["id"],
            str(label or "").strip()[:120],
            hashlib.sha256(token.encode("utf-8")).hexdigest(),
            user_id,
            expires_at,
        ),
    )
    row = query_db("SELECT * FROM request_links WHERE id = ?", (link_id,), one=True)
    return serialize_request_link(row), token


def list_request_links(user_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "view")
    rows = query_db(
        "SELECT * FROM request_links WHERE workspace_id = ? ORDER BY id DESC",
        (workspace["id"],),
    )
    return [serialize_request_link(row) for row in rows]


def revoke_request_link(user_id, link_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "manage")
    try:
        link_id = int(link_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.request_not_found"))
    row = query_db(
        "SELECT id FROM request_links WHERE id = ? AND workspace_id = ?",
        (link_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.request_not_found"))
    execute_db("UPDATE request_links SET revoked = 1 WHERE id = ?", (link_id,))


def get_client_link(token):
    if not token:
        return None
    token_hash = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
    row = query_db(
        """
        SELECT l.*, w.path AS workspace_path, w.display_name AS workspace_display_name
        FROM request_links l
        JOIN website_workspaces w ON w.id = l.workspace_id
        WHERE l.token_hash = ?
        """,
        (token_hash,),
        one=True,
    )
    if not row:
        return None
    link = serialize_request_link(row)
    if not link["active"]:
        return None
    return link


def serialize_client_request(row):
    return dict(row)


def serialize_request_comment(row):
    return dict(row)


def serialize_request_attachment(row):
    return dict(row)


def get_request_attachments(request_id):
    rows = query_db(
        "SELECT * FROM request_attachments WHERE request_id = ? ORDER BY id ASC",
        (request_id,),
    )
    return [serialize_request_attachment(row) for row in rows]


def get_request_comments(request_id):
    rows = query_db(
        "SELECT * FROM request_comments WHERE request_id = ? ORDER BY id ASC",
        (request_id,),
    )
    return [serialize_request_comment(row) for row in rows]


def serialize_request_thread(request_row):
    payload = serialize_client_request(request_row)
    payload["comments"] = get_request_comments(request_row["id"])
    payload["attachments"] = get_request_attachments(request_row["id"])
    return payload


def list_workspace_requests(user_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "view")
    rows = query_db(
        """
        SELECT r.*, l.label AS link_label,
               (SELECT COUNT(*) FROM request_comments c WHERE c.request_id = r.id) AS comment_count,
               (SELECT COUNT(*) FROM request_attachments a WHERE a.request_id = r.id) AS attachment_count
        FROM client_requests r
        LEFT JOIN request_links l ON l.id = r.link_id
        WHERE r.workspace_id = ?
        ORDER BY r.updated_at DESC, r.id DESC
        """,
        (workspace["id"],),
    )
    return [dict(row) for row in rows]


def get_agency_request_thread(user_id, request_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "view")
    try:
        request_id = int(request_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.request_not_found"))
    row = query_db(
        "SELECT * FROM client_requests WHERE id = ? AND workspace_id = ?",
        (request_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.request_not_found"))
    return serialize_request_thread(row)


def get_portal_request_thread(link, request_id):
    try:
        request_id = int(request_id)
    except (TypeError, ValueError):
        return None
    row = query_db(
        "SELECT * FROM client_requests WHERE id = ? AND link_id = ? AND workspace_id = ?",
        (request_id, link["id"], link["workspace_id"]),
        one=True,
    )
    if not row:
        return None
    return serialize_request_thread(row)


def list_link_requests(link):
    rows = query_db(
        """
        SELECT r.*,
               (SELECT COUNT(*) FROM request_comments c WHERE c.request_id = r.id) AS comment_count
        FROM client_requests r
        WHERE r.link_id = ? AND r.workspace_id = ?
        ORDER BY r.updated_at DESC, r.id DESC
        """,
        (link["id"], link["workspace_id"]),
    )
    return [dict(row) for row in rows]


def resolve_link_page(link, page):
    candidate = (page or "").replace("\\", "/").strip().strip("/")
    if not candidate or candidate.startswith("/") or contains_parent_reference(candidate):
        return None
    if relative_path_has_reserved_component(candidate):
        return None
    absolute_path = os.path.realpath(os.path.join(link["workspace_path"], *candidate.split("/")))
    root = os.path.realpath(link["workspace_path"])
    if absolute_path != root and not absolute_path.startswith(root + os.sep):
        return None
    if not os.path.isfile(absolute_path):
        return None
    return absolute_path


def serve_link_preview_file(link, filepath, picker=False):
    absolute_path = resolve_link_page(link, filepath or "")
    if absolute_path is None:
        return None
    mime_type = mimetypes.guess_type(absolute_path)[0] or "application/octet-stream"
    extension = os.path.splitext(absolute_path)[1].lower()
    if picker and extension in {".htm", ".html"}:
        with open(absolute_path, "r", encoding="utf-8", errors="replace") as handle:
            html_text = handle.read()
        return Response(inject_preview_picker(html_text, filepath), mimetype="text/html")
    return send_file(absolute_path, mimetype=mime_type)


def create_client_request(link, fields, files):
    message = str(fields.get("message") or "").strip()
    if not message:
        raise ValueError(translate("flash.fix_value_required"))
    page = str(fields.get("page") or "").replace("\\", "/").strip().strip("/")[:300]
    selector = str(fields.get("selector") or "").strip()[:500]
    if page and resolve_link_page(link, page) is None:
        raise ValueError(translate("flash.request_not_found"))
    request_id = execute_db(
        """
        INSERT INTO client_requests (
            workspace_id, link_id, page, selector, tag, text, html_excerpt, image_src,
            client_name, message, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """,
        (
            link["workspace_id"],
            link["id"],
            page,
            selector,
            str(fields.get("tag") or "").strip()[:40],
            str(fields.get("text") or "").strip()[:500],
            str(fields.get("html") or "").strip()[:2000],
            str(fields.get("image_src") or "").strip()[:500],
            str(fields.get("client_name") or "").strip()[:80],
            message[:2000],
        ),
    )
    save_request_attachments(request_id, None, "client", files)
    row = query_db("SELECT * FROM client_requests WHERE id = ?", (request_id,), one=True)
    notify_workspace(
        link["workspace_id"],
        "request",
        f"{row['client_name'] or '?'}: {row['message'][:120]}",
        row["page"] or "",
        f"/site-manager/requests/{request_id}",
    )
    return serialize_request_thread(row)


def add_request_comment_by_id(request_id, side, author_name, body, user_id=None):
    body = str(body or "").strip()
    if not body:
        raise ValueError(translate("flash.fix_value_required"))
    comment_id = execute_db(
        """
        INSERT INTO request_comments (request_id, side, user_id, author_name, body)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            request_id,
            side,
            user_id,
            str(author_name or "").strip()[:80],
            body[:2000],
        ),
    )
    execute_db(
        "UPDATE client_requests SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (request_id,),
    )
    row = query_db("SELECT * FROM request_comments WHERE id = ?", (comment_id,), one=True)
    return serialize_request_comment(row)


def request_attachment_directory():
    directory = os.path.join(UPLOAD_DIR, "request-attachments")
    os.makedirs(directory, exist_ok=True)
    return directory


def save_request_attachments(request_id, comment_id, side, files):
    saved = []
    if not files:
        return saved
    if hasattr(files, "getlist"):
        uploads = files.getlist("attachment") or files.getlist("attachments") or []
    elif isinstance(files, dict):
        uploads = []
        for value in files.values():
            uploads.extend(value if isinstance(value, list) else [value])
    else:
        uploads = list(files)
    directory = request_attachment_directory()
    for upload in uploads:
        filename = (getattr(upload, "filename", "") or "").strip()
        if not filename:
            continue
        extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if extension not in REQUEST_ATTACHMENT_EXTENSIONS:
            raise ValueError(translate("flash.attachment_invalid"))
        if extension != "pdf" and not uploaded_image_matches_extension(upload, extension):
            raise ValueError(translate("flash.attachment_invalid"))
        try:
            upload.stream.seek(0, os.SEEK_END)
            size_bytes = upload.stream.tell()
            upload.stream.seek(0)
        except (AttributeError, OSError):
            size_bytes = 0
        if size_bytes > REQUEST_ATTACHMENT_MAX_BYTES:
            raise ValueError(translate("flash.attachment_invalid"))
        stored = f"req-{request_id}-{secrets.token_hex(8)}.{extension}"
        upload.save(os.path.join(directory, stored))
        try:
            size_bytes = os.path.getsize(os.path.join(directory, stored))
        except OSError:
            size_bytes = 0
        attachment_id = execute_db(
            """
            INSERT INTO request_attachments (
                request_id, comment_id, filename, original_name, mime, size_bytes, side
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                request_id,
                comment_id,
                stored,
                posixpath.basename(filename)[:128],
                mimetypes.guess_type(filename)[0] or "application/octet-stream",
                size_bytes,
                side,
            ),
        )
        row = query_db("SELECT * FROM request_attachments WHERE id = ?", (attachment_id,), one=True)
        saved.append(serialize_request_attachment(row))
    return saved


def remove_request_attachment_files(filenames):
    directory = request_attachment_directory()
    for filename in filenames:
        try:
            os.remove(os.path.join(directory, posixpath.basename(filename or "")))
        except OSError:
            pass


def agency_add_comment(user_id, request_id, body, files=None):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    try:
        request_id = int(request_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.request_not_found"))
    row = query_db(
        "SELECT * FROM client_requests WHERE id = ? AND workspace_id = ?",
        (request_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.request_not_found"))
    user = query_db("SELECT name FROM users WHERE id = ?", (user_id,), one=True)
    comment = add_request_comment_by_id(
        request_id, "team", (user["name"] if user else ""), body, user_id=user_id
    )
    save_request_attachments(request_id, comment["id"], "team", files)
    notify_workspace(
        workspace["id"],
        "request",
        f"{(user['name'] if user else '?')} commented on request #{request_id}",
        str(body or "").strip()[:200],
        f"/site-manager/requests/{request_id}",
        exclude_user_id=user_id,
    )
    return get_agency_request_thread(user_id, request_id)


def agency_set_request_status(user_id, request_id, status, proposal=None):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    status = str(status or "").strip().lower()
    if status not in ("open", "in_review", "proposed", "done"):
        raise ValueError(translate("flash.invalid_transition"))
    try:
        request_id = int(request_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.request_not_found"))
    row = query_db(
        "SELECT * FROM client_requests WHERE id = ? AND workspace_id = ?",
        (request_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.request_not_found"))
    proposal_text = row["proposal_text"] or ""
    if proposal is not None:
        proposal_text = str(proposal or "").strip()[:2000]
    if status == "proposed" and not proposal_text:
        raise ValueError(translate("flash.fix_value_required"))
    execute_db(
        """
        UPDATE client_requests
        SET status = ?, proposal_text = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, proposal_text, request_id),
    )
    return get_agency_request_thread(user_id, request_id)


def agency_delete_request(user_id, request_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    try:
        request_id = int(request_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.request_not_found"))
    row = query_db(
        "SELECT id FROM client_requests WHERE id = ? AND workspace_id = ?",
        (request_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.request_not_found"))
    attachments = query_db(
        "SELECT filename FROM request_attachments WHERE request_id = ?", (request_id,)
    )
    remove_request_attachment_files([item["filename"] for item in attachments])
    execute_db("DELETE FROM request_attachments WHERE request_id = ?", (request_id,))
    execute_db("DELETE FROM request_comments WHERE request_id = ?", (request_id,))
    execute_db("DELETE FROM client_requests WHERE id = ?", (request_id,))


def portal_add_comment(link, request_id, author_name, body, files=None):
    thread = get_portal_request_thread(link, request_id)
    if not thread:
        raise ValueError(translate("flash.request_not_found"))
    comment = add_request_comment_by_id(thread["id"], "client", author_name, body)
    save_request_attachments(thread["id"], comment["id"], "client", files)
    notify_workspace(
        link["workspace_id"],
        "request",
        f"{str(author_name or '?').strip() or '?'} commented on request #{thread['id']}",
        str(body or "").strip()[:200],
        f"/site-manager/requests/{thread['id']}",
    )
    return get_portal_request_thread(link, thread["id"])


def portal_decide_request(link, request_id, decision):
    decision = str(decision or "").strip().lower()
    if decision not in ("approved", "rejected"):
        raise ValueError(translate("flash.invalid_transition"))
    thread = get_portal_request_thread(link, request_id)
    if not thread:
        raise ValueError(translate("flash.request_not_found"))
    if thread["status"] != "proposed":
        raise ValueError(translate("flash.invalid_transition"))
    execute_db(
        "UPDATE client_requests SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (decision, thread["id"]),
    )
    notify_workspace(
        link["workspace_id"],
        "request",
        f"Request #{thread['id']} {decision}",
        thread["message"][:200] if thread.get("message") else "",
        f"/site-manager/requests/{thread['id']}",
    )
    return get_portal_request_thread(link, thread["id"])


def get_portal_attachment(link, filename):
    safe_name = posixpath.basename(filename or "")
    if not safe_name:
        return None
    row = query_db(
        """
        SELECT a.* FROM request_attachments a
        JOIN client_requests r ON r.id = a.request_id
        WHERE a.filename = ? AND r.workspace_id = ?
        """,
        (safe_name, link["workspace_id"]),
        one=True,
    )
    return dict(row) if row else None


def get_agency_attachment(user_id, filename):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "view")
    safe_name = posixpath.basename(filename or "")
    if not safe_name:
        return None
    row = query_db(
        """
        SELECT a.* FROM request_attachments a
        JOIN client_requests r ON r.id = a.request_id
        WHERE a.filename = ? AND r.workspace_id = ?
        """,
        (safe_name, workspace["id"]),
        one=True,
    )
    return dict(row) if row else None


def count_open_client_requests(user_id):
    workspace = get_current_workspace(user_id)
    if not workspace:
        return 0
    row = query_db(
        """
        SELECT COUNT(*) AS total FROM client_requests
        WHERE workspace_id = ? AND status NOT IN ('done', 'approved')
        """,
        (workspace["id"],),
        one=True,
    )
    return row["total"]


CALENDAR_KINDS = ("promo", "blog", "prices", "note")


def clean_calendar_date(value):
    text = str(value or "").strip()[:10]
    if not text:
        return ""
    try:
        datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        raise ValueError(translate("flash.invalid_dates"))
    return text


def serialize_calendar_event(row):
    event = dict(row)
    stored = event.get("status") or "scheduled"
    today = date.today().isoformat()
    starts_on = event.get("starts_on") or ""
    ends_on = event.get("ends_on") or ""
    if stored in ("done", "cancelled"):
        event["status"] = stored
    elif ends_on and ends_on < today:
        event["status"] = "expired"
    elif starts_on and starts_on > today:
        event["status"] = "scheduled"
    else:
        event["status"] = "active"
    return event


def list_calendar_events(user_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "view")
    rows = query_db(
        "SELECT * FROM scheduled_events WHERE workspace_id = ? ORDER BY starts_on ASC, id ASC",
        (workspace["id"],),
    )
    return [serialize_calendar_event(row) for row in rows]


def create_calendar_event(user_id, kind="note", title="", brief="", page="", starts_on="", ends_on=""):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    kind = str(kind or "note").strip().lower()
    if kind not in CALENDAR_KINDS:
        kind = "note"
    title = str(title or "").strip()
    if not title:
        raise ValueError(translate("flash.fix_value_required"))
    starts_on = clean_calendar_date(starts_on) or date.today().isoformat()
    ends_on = clean_calendar_date(ends_on)
    if ends_on and ends_on < starts_on:
        raise ValueError(translate("flash.invalid_dates"))
    event_id = execute_db(
        """
        INSERT INTO scheduled_events (workspace_id, created_by, kind, title, brief, page, starts_on, ends_on, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'scheduled')
        """,
        (
            workspace["id"],
            user_id,
            kind,
            title[:160],
            str(brief or "").strip()[:4000],
            str(page or "").strip()[:300],
            starts_on,
            ends_on,
        ),
    )
    row = query_db("SELECT * FROM scheduled_events WHERE id = ?", (event_id,), one=True)
    return serialize_calendar_event(row)


def update_calendar_event(user_id, event_id, **fields):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    try:
        event_id = int(event_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.event_not_found"))
    row = query_db(
        "SELECT * FROM scheduled_events WHERE id = ? AND workspace_id = ?",
        (event_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.event_not_found"))
    updates = {}
    if "kind" in fields and fields["kind"] is not None:
        kind = str(fields["kind"]).strip().lower()
        updates["kind"] = kind if kind in CALENDAR_KINDS else "note"
    if "title" in fields and fields["title"] is not None:
        title = str(fields["title"]).strip()
        if not title:
            raise ValueError(translate("flash.fix_value_required"))
        updates["title"] = title[:160]
    if "brief" in fields and fields["brief"] is not None:
        updates["brief"] = str(fields["brief"]).strip()[:4000]
    if "page" in fields and fields["page"] is not None:
        updates["page"] = str(fields["page"]).strip()[:300]
    starts_on = clean_calendar_date(fields.get("starts_on", row["starts_on"]))
    ends_on = clean_calendar_date(fields.get("ends_on", row["ends_on"]))
    if "starts_on" in fields or "ends_on" in fields:
        if ends_on and ends_on < (starts_on or ""):
            raise ValueError(translate("flash.invalid_dates"))
        updates["starts_on"] = starts_on or date.today().isoformat()
        updates["ends_on"] = ends_on
    if updates:
        assignments = ", ".join(f"{column} = ?" for column in updates)
        execute_db(
            f"UPDATE scheduled_events SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (*updates.values(), event_id),
        )
    row = query_db("SELECT * FROM scheduled_events WHERE id = ?", (event_id,), one=True)
    return serialize_calendar_event(row)


def cancel_calendar_event(user_id, event_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    try:
        event_id = int(event_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.event_not_found"))
    row = query_db(
        "SELECT * FROM scheduled_events WHERE id = ? AND workspace_id = ?",
        (event_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.event_not_found"))
    execute_db(
        "UPDATE scheduled_events SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (event_id,),
    )
    row = query_db("SELECT * FROM scheduled_events WHERE id = ?", (event_id,), one=True)
    return serialize_calendar_event(row)


def delete_calendar_event(user_id, event_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    try:
        event_id = int(event_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.event_not_found"))
    row = query_db(
        "SELECT id FROM scheduled_events WHERE id = ? AND workspace_id = ?",
        (event_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.event_not_found"))
    execute_db("DELETE FROM scheduled_events WHERE id = ?", (event_id,))


def execute_calendar_event(user_id, event_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    try:
        event_id = int(event_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.event_not_found"))
    row = query_db(
        "SELECT * FROM scheduled_events WHERE id = ? AND workspace_id = ?",
        (event_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.event_not_found"))
    brief = (row["brief"] or "").strip()
    if not brief:
        raise ValueError(translate("flash.fix_value_required"))
    terminal = run_site_codex_update(user_id, f"[{row['kind']}] {row['title']}\n\n{brief}")
    directory = require_site_directory(user_id)
    latest = query_db(
        """
        SELECT id FROM website_update_history
        WHERE user_id = ? AND directory_path = ?
        ORDER BY id DESC LIMIT 1
        """,
        (user_id, os.path.realpath(directory["path"])),
        one=True,
    )
    execute_db(
        "UPDATE scheduled_events SET status = 'done', update_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (latest["id"] if latest else None, event_id),
    )
    row = query_db("SELECT * FROM scheduled_events WHERE id = ?", (event_id,), one=True)
    return serialize_calendar_event(row), terminal


FORM_SUBMIT_LOG = {}
FORM_SUBMIT_GUARD = threading.Lock()
FORM_RATE_LIMIT_COUNT = 20
FORM_RATE_LIMIT_WINDOW = 3600


class FormRateLimited(ValueError):
    pass


def create_form_token(user_id, label=""):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "manage")
    token = secrets.token_urlsafe(32)
    token_id = execute_db(
        "INSERT INTO form_tokens (workspace_id, label, token, token_hash, created_by) VALUES (?, ?, ?, ?, ?)",
        (
            workspace["id"],
            str(label or "").strip()[:120],
            token,
            hashlib.sha256(token.encode("utf-8")).hexdigest(),
            user_id,
        ),
    )
    row = query_db("SELECT * FROM form_tokens WHERE id = ?", (token_id,), one=True)
    return dict(row), token


def list_form_tokens(user_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "view")
    rows = query_db(
        "SELECT * FROM form_tokens WHERE workspace_id = ? ORDER BY id DESC",
        (workspace["id"],),
    )
    return [dict(row) for row in rows]


def latest_form_token(user_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "view")
    row = query_db(
        "SELECT * FROM form_tokens WHERE workspace_id = ? AND revoked = 0 ORDER BY id DESC LIMIT 1",
        (workspace["id"],),
        one=True,
    )
    return dict(row) if row else None


def revoke_form_token(user_id, token_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "manage")
    try:
        token_id = int(token_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.message_not_found"))
    row = query_db(
        "SELECT id FROM form_tokens WHERE id = ? AND workspace_id = ?",
        (token_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.message_not_found"))
    execute_db("UPDATE form_tokens SET revoked = 1 WHERE id = ?", (token_id,))


def get_form_token(token):
    if not token:
        return None
    token_hash = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
    row = query_db(
        """
        SELECT t.*, w.path AS workspace_path
        FROM form_tokens t
        JOIN website_workspaces w ON w.id = t.workspace_id
        WHERE t.token_hash = ? AND t.revoked = 0
        """,
        (token_hash,),
        one=True,
    )
    return dict(row) if row else None


def check_form_rate_limit(key):
    now = time.time()
    with FORM_SUBMIT_GUARD:
        entries = [moment for moment in FORM_SUBMIT_LOG.get(key, []) if now - moment < FORM_RATE_LIMIT_WINDOW]
        if len(entries) >= FORM_RATE_LIMIT_COUNT:
            FORM_SUBMIT_LOG[key] = entries
            return False
        entries.append(now)
        FORM_SUBMIT_LOG[key] = entries
        return True


def submit_contact_message(token, remote_addr, fields):
    form_token = get_form_token(token)
    if not form_token:
        return None
    if not check_form_rate_limit(f"{remote_addr or 'unknown'}:{form_token['id']}"):
        raise FormRateLimited(translate("flash.invalid_transition"))
    message = str(fields.get("message") or "").strip()
    if not message:
        raise ValueError(translate("flash.fix_value_required"))
    message_id = execute_db(
        """
        INSERT INTO contact_messages (workspace_id, page, name, email, phone, message, meta, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'new')
        """,
        (
            form_token["workspace_id"],
            str(fields.get("page") or "")[:300],
            str(fields.get("name") or "").strip()[:120],
            str(fields.get("email") or "").strip()[:160],
            str(fields.get("phone") or "").strip()[:60],
            message[:4000],
            json.dumps({"ip": (remote_addr or "")[:64]}),
        ),
    )
    row = query_db("SELECT * FROM contact_messages WHERE id = ?", (message_id,), one=True)
    sender = (row["name"] or row["email"] or "?").strip()
    notify_workspace(
        form_token["workspace_id"],
        "inbox",
        f"{sender} — {row['page'] or '/'}",
        row["message"][:200],
        "/site-manager/inbox",
    )
    return dict(row)


def list_contact_messages(user_id, status=None):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "view")
    if status in ("new", "attended"):
        rows = query_db(
            "SELECT * FROM contact_messages WHERE workspace_id = ? AND status = ? ORDER BY id DESC",
            (workspace["id"], status),
        )
    else:
        rows = query_db(
            "SELECT * FROM contact_messages WHERE workspace_id = ? ORDER BY id DESC",
            (workspace["id"],),
        )
    return [dict(row) for row in rows]


def set_contact_message_status(user_id, message_id, status):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    if status not in ("new", "attended"):
        raise ValueError(translate("flash.invalid_transition"))
    try:
        message_id = int(message_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.message_not_found"))
    row = query_db(
        "SELECT id FROM contact_messages WHERE id = ? AND workspace_id = ?",
        (message_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.message_not_found"))
    execute_db(
        "UPDATE contact_messages SET status = ? WHERE id = ?", (status, message_id)
    )
    row = query_db("SELECT * FROM contact_messages WHERE id = ?", (message_id,), one=True)
    return dict(row)


def delete_contact_message(user_id, message_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    try:
        message_id = int(message_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.message_not_found"))
    row = query_db(
        "SELECT id FROM contact_messages WHERE id = ? AND workspace_id = ?",
        (message_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.message_not_found"))
    execute_db("DELETE FROM contact_messages WHERE id = ?", (message_id,))


def build_form_snippet(submit_url):
    return f"""<form method="post" action="{submit_url}">
  <input type="text" name="name" placeholder="Name" required>
  <input type="email" name="email" placeholder="Email" required>
  <input type="text" name="phone" placeholder="Phone">
  <input type="hidden" name="page" value="/contact">
  <textarea name="message" placeholder="Message" required></textarea>
  <button type="submit">Send</button>
</form>"""


def count_new_contact_messages(user_id):
    workspace = get_current_workspace(user_id)
    if not workspace:
        return 0
    row = query_db(
        "SELECT COUNT(*) AS total FROM contact_messages WHERE workspace_id = ? AND status = 'new'",
        (workspace["id"],),
        one=True,
    )
    return row["total"]


ALERT_RULE_KINDS = ("uptime", "tls")
ALERT_CHECK_TIMEOUT = 10


def check_site_uptime(url, timeout=ALERT_CHECK_TIMEOUT):
    candidate = str(url or "").strip()
    if not candidate.lower().startswith(("http://", "https://")):
        return (False, "invalid URL")
    try:
        request = urllib.request.Request(candidate, headers={"User-Agent": "ONEBoard-alerts/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = getattr(response, "status", 200)
            return (True, f"HTTP {status}") if status < 400 else (False, f"HTTP {status}")
    except urllib.error.HTTPError as error:
        return (False, f"HTTP {error.code}")
    except Exception as error:
        return (False, external_error_detail(error))


def get_tls_expiry(host, port=443, timeout=ALERT_CHECK_TIMEOUT):
    hostname = str(host or "").strip()
    if "://" in hostname:
        hostname = urllib.parse.urlsplit(hostname).hostname or hostname
    hostname = hostname.split("/")[0].split(":")[0].strip()
    if not hostname:
        raise ValueError("invalid host")
    context = ssl.create_default_context()
    with socket.create_connection((hostname, port), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=hostname) as tls:
            certificate = tls.getpeercert()
    not_after = (certificate or {}).get("notAfter")
    if not not_after:
        raise ValueError("no certificate data")
    return datetime.strptime(not_after, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)


def normalize_alert_target(kind, target):
    target = str(target or "").strip()[:300]
    if kind == "uptime":
        if not target.lower().startswith(("http://", "https://")):
            raise ValueError(translate("flash.fix_value_required"))
        return target
    if "://" in target:
        target = urllib.parse.urlsplit(target).hostname or target
    target = target.split("/")[0].split(":")[0].strip()
    if not target or " " in target:
        raise ValueError(translate("flash.fix_value_required"))
    return target.lower()


def create_alert_rule(user_id, kind="uptime", target="", name="", threshold_days=14):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    kind = str(kind or "uptime").strip().lower()
    if kind not in ALERT_RULE_KINDS:
        kind = "uptime"
    target = normalize_alert_target(kind, target)
    try:
        threshold_days = int(threshold_days)
    except (TypeError, ValueError):
        threshold_days = 14
    threshold_days = max(1, min(threshold_days, 365))
    rule_id = execute_db(
        """
        INSERT INTO alert_rules (workspace_id, kind, target, name, threshold_days, enabled, created_by)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """,
        (workspace["id"], kind, target, str(name or "").strip()[:120], threshold_days, user_id),
    )
    row = query_db("SELECT * FROM alert_rules WHERE id = ?", (rule_id,), one=True)
    return dict(row)


def list_alert_rules(user_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "view")
    rows = query_db(
        "SELECT * FROM alert_rules WHERE workspace_id = ? ORDER BY id ASC",
        (workspace["id"],),
    )
    return [dict(row) for row in rows]


def update_alert_rule(user_id, rule_id, **fields):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    try:
        rule_id = int(rule_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.rule_not_found"))
    row = query_db(
        "SELECT * FROM alert_rules WHERE id = ? AND workspace_id = ?",
        (rule_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.rule_not_found"))
    updates = {}
    if "name" in fields and fields["name"] is not None:
        updates["name"] = str(fields["name"]).strip()[:120]
    if "enabled" in fields and fields["enabled"] is not None:
        raw = fields["enabled"]
        updates["enabled"] = 1 if raw in (True, 1, "1", "true", "yes", "on") else 0
    if "threshold_days" in fields and fields["threshold_days"] is not None:
        try:
            updates["threshold_days"] = max(1, min(int(fields["threshold_days"]), 365))
        except (TypeError, ValueError):
            pass
    if updates:
        assignments = ", ".join(f"{column} = ?" for column in updates)
        execute_db(
            f"UPDATE alert_rules SET {assignments} WHERE id = ?", (*updates.values(), rule_id)
        )
    row = query_db("SELECT * FROM alert_rules WHERE id = ?", (rule_id,), one=True)
    return dict(row)


def delete_alert_rule(user_id, rule_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    try:
        rule_id = int(rule_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.rule_not_found"))
    row = query_db(
        "SELECT id FROM alert_rules WHERE id = ? AND workspace_id = ?",
        (rule_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.rule_not_found"))
    execute_db("UPDATE site_alerts SET rule_id = NULL WHERE rule_id = ?", (rule_id,))
    execute_db("DELETE FROM alert_rules WHERE id = ?", (rule_id,))


def list_site_alerts(user_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "view")
    rows = query_db(
        """
        SELECT a.*, r.name AS rule_name, r.target AS rule_target
        FROM site_alerts a
        LEFT JOIN alert_rules r ON r.id = a.rule_id
        WHERE a.workspace_id = ?
        ORDER BY CASE a.status WHEN 'open' THEN 0 WHEN 'acked' THEN 1 ELSE 2 END,
                 a.updated_at DESC, a.id DESC
        LIMIT 200
        """,
        (workspace["id"],),
    )
    return [dict(row) for row in rows]


def open_workspace_alert(workspace_id, kind, title, detail, rule_id=None, severity="error"):
    if rule_id is not None:
        existing = query_db(
            "SELECT id FROM site_alerts WHERE workspace_id = ? AND rule_id = ? AND status IN ('open', 'acked')",
            (workspace_id, rule_id),
            one=True,
        )
        if existing:
            execute_db(
                """
                UPDATE site_alerts
                SET title = ?, detail = ?, severity = ?, status = 'open',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (title[:200], detail[:500], severity, existing["id"]),
            )
            return existing["id"]
    else:
        existing = query_db(
            "SELECT id FROM site_alerts WHERE workspace_id = ? AND rule_id IS NULL AND kind = ? AND status IN ('open', 'acked')",
            (workspace_id, kind),
            one=True,
        )
        if existing:
            execute_db(
                "UPDATE site_alerts SET title = ?, detail = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (title[:200], detail[:500], existing["id"]),
            )
            return existing["id"]
    alert_id = execute_db(
        """
        INSERT INTO site_alerts (workspace_id, rule_id, kind, severity, title, detail, status)
        VALUES (?, ?, ?, ?, ?, ?, 'open')
        """,
        (workspace_id, rule_id, kind, severity, title[:200], detail[:500]),
    )
    notify_workspace(
        workspace_id, "alert", title[:200], detail[:200], "/site-manager/alerts"
    )
    return alert_id


def resolve_rule_alerts(workspace_id, rule_id):
    execute_db(
        """
        UPDATE site_alerts
        SET status = 'resolved', resolved_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
        WHERE workspace_id = ? AND rule_id = ? AND status IN ('open', 'acked')
        """,
        (workspace_id, rule_id),
    )


def check_alert_rule(workspace_id, rule):
    if rule["kind"] == "uptime":
        ok, detail = check_site_uptime(rule["target"])
        title = f"Site down: {rule['target']}"
    else:
        try:
            expiry = get_tls_expiry(rule["target"])
            days_left = (expiry.date() - datetime.now(timezone.utc).date()).days
            ok = days_left >= (rule["threshold_days"] or 14)
            detail = f"{days_left} days left (expires {expiry.date().isoformat()})"
        except Exception as error:
            ok, detail = False, f"check failed: {external_error_detail(error)}"
        title = f"TLS certificate: {rule['target']}"
    execute_db(
        "UPDATE alert_rules SET last_status = ?, last_detail = ?, last_checked_at = CURRENT_TIMESTAMP WHERE id = ?",
        ("ok" if ok else "failing", detail[:500], rule["id"]),
    )
    if ok:
        resolve_rule_alerts(workspace_id, rule["id"])
    else:
        open_workspace_alert(workspace_id, rule["kind"], title, detail, rule_id=rule["id"])
    return ok


def run_workspace_alert_checks(workspace_id):
    rules = query_db(
        "SELECT * FROM alert_rules WHERE workspace_id = ? AND enabled = 1 ORDER BY id ASC",
        (workspace_id,),
    )
    results = []
    for rule in rules:
        try:
            results.append({"rule_id": rule["id"], "ok": check_alert_rule(workspace_id, dict(rule))})
        except Exception as error:
            results.append({"rule_id": rule["id"], "ok": False, "error": str(error)[:200]})
    return results


def run_site_alert_checks(user_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "view")
    run_workspace_alert_checks(workspace["id"])
    return {"rules": list_alert_rules(user_id), "alerts": list_site_alerts(user_id)}


def run_all_alert_checks():
    rows = query_db(
        "SELECT DISTINCT workspace_id FROM alert_rules WHERE enabled = 1", ()
    )
    checked = 0
    for row in rows:
        run_workspace_alert_checks(row["workspace_id"])
        checked += 1
    return checked


def record_publish_alert(user_id, detail):
    workspace = get_current_workspace(user_id)
    if not workspace:
        return None
    return open_workspace_alert(
        workspace["id"], "publish", "Publish failed", str(detail or "")[:500]
    )


def set_site_alert_status(user_id, alert_id, status):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "edit")
    if status not in ("open", "acked", "resolved"):
        raise ValueError(translate("flash.invalid_transition"))
    try:
        alert_id = int(alert_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.alert_not_found"))
    row = query_db(
        "SELECT id FROM site_alerts WHERE id = ? AND workspace_id = ?",
        (alert_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.alert_not_found"))
    execute_db(
        """
        UPDATE site_alerts
        SET status = ?, resolved_at = CASE WHEN ? = 'resolved' THEN CURRENT_TIMESTAMP ELSE resolved_at END,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (status, status, alert_id),
    )
    return {"rules": list_alert_rules(user_id), "alerts": list_site_alerts(user_id)}


def count_open_site_alerts(user_id):
    workspace = get_current_workspace(user_id)
    if not workspace:
        return 0
    row = query_db(
        "SELECT COUNT(*) AS total FROM site_alerts WHERE workspace_id = ? AND status = 'open'",
        (workspace["id"],),
        one=True,
    )
    return row["total"]


def clean_report_period(value):
    text = str(value or "").strip()[:7]
    try:
        datetime.strptime(text, "%Y-%m")
    except ValueError:
        raise ValueError(translate("flash.fix_value_required"))
    return text


def month_bounds(period):
    year, month = int(period[:4]), int(period[5:7])
    start = f"{period}-01 00:00:00"
    if month == 12:
        end = f"{year + 1}-01-01 00:00:00"
    else:
        end = f"{year}-{month + 1:02d}-01 00:00:00"
    return start, end


def fetch_search_console_totals(connection, site_url, start, end):
    encoded_site_url = urllib.parse.quote(site_url, safe="")
    totals = google_api_request(
        connection,
        f"/sites/{encoded_site_url}/searchAnalytics/query",
        method="POST",
        payload={"startDate": start, "endDate": end, "rowLimit": 1},
    )
    return format_search_stats(first_row(totals.get("rows", [])))


def build_site_report(user_id, workspace, period):
    period = clean_report_period(period)
    start, end = month_bounds(period)
    real_path = os.path.realpath(workspace["path"])
    member_ids = team_scope_user_ids(user_id) or [user_id]
    placeholders = ", ".join("?" for _ in member_ids)
    changes = query_db(
        f"""
        SELECT created_at, source, summary, status
        FROM website_update_history
        WHERE user_id IN ({placeholders}) AND directory_path = ?
          AND created_at >= ? AND created_at < ?
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (*member_ids, real_path, start, end),
    )
    inquiries = query_db(
        """
        SELECT created_at, name, email, page, message, status
        FROM contact_messages
        WHERE workspace_id = ? AND created_at >= ? AND created_at < ?
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (workspace["id"], start, end),
    )
    resolved = query_db(
        """
        SELECT COUNT(*) AS total FROM site_findings
        WHERE directory_path = ? AND status = 'resolved'
          AND resolved_at >= ? AND resolved_at < ?
        """,
        (real_path, start, end),
        one=True,
    )["total"]
    requests_done = query_db(
        """
        SELECT COUNT(*) AS total FROM client_requests
        WHERE workspace_id = ? AND status IN ('done', 'approved')
          AND updated_at >= ? AND updated_at < ?
        """,
        (workspace["id"], start, end),
        one=True,
    )["total"]
    visits = None
    try:
        connection = valid_google_connection(user_id)
    except (GoogleApiError, ValueError):
        connection = None
    site_property = workspace["gsc_property"] or (
        connection["selected_site_url"] if connection else ""
    )
    try:
        visits = fetch_search_console_totals(
            connection, site_property or "", start[:10], end[:10]
        )
    except Exception:
        visits = None
    brand = parse_site_brand(workspace["brand_json"])
    user = query_db(
        "SELECT company_name, company_logo_path FROM users WHERE id = ?", (user_id,), one=True
    )
    return {
        "period": period,
        "site_name": workspace["display_name"] or os.path.basename(workspace["path"].rstrip(os.sep)),
        "client_name": workspace["client_name"] or "",
        "logo_url": f"/uploads/brand-logos/{brand['logo']}" if brand.get("logo") else "",
        "company_name": (user["company_name"] if user else "") or "",
        "company_logo_url": f"/uploads/company-logos/{user['company_logo_path']}" if user and user["company_logo_path"] else "",
        "changes": [dict(row) for row in changes],
        "changes_count": len(changes),
        "visits": visits,
        "inquiries": [dict(row) for row in inquiries],
        "inquiries_count": len(inquiries),
        "issues_resolved": resolved,
        "requests_done": requests_done,
    }


def create_site_report_link(user_id, period, title=""):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "manage")
    period = clean_report_period(period)
    token = secrets.token_urlsafe(32)
    link_id = execute_db(
        "INSERT INTO site_reports (workspace_id, period, title, token_hash, created_by) VALUES (?, ?, ?, ?, ?)",
        (
            workspace["id"],
            period,
            str(title or "").strip()[:160],
            hashlib.sha256(token.encode("utf-8")).hexdigest(),
            user_id,
        ),
    )
    row = query_db("SELECT * FROM site_reports WHERE id = ?", (link_id,), one=True)
    return dict(row), token


def list_site_report_links(user_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "view")
    rows = query_db(
        "SELECT * FROM site_reports WHERE workspace_id = ? ORDER BY period DESC, id DESC",
        (workspace["id"],),
    )
    return [dict(row) for row in rows]


def get_site_report(user_id, link_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "view")
    try:
        link_id = int(link_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.report_not_found"))
    link = query_db(
        "SELECT * FROM site_reports WHERE id = ? AND workspace_id = ?",
        (link_id, workspace["id"]),
        one=True,
    )
    if not link:
        raise ValueError(translate("flash.report_not_found"))
    return build_site_report(user_id, workspace, link["period"])


def revoke_site_report_link(user_id, link_id):
    workspace = require_current_request_workspace(user_id)
    require_project_permission(user_id, "manage")
    try:
        link_id = int(link_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.report_not_found"))
    row = query_db(
        "SELECT id FROM site_reports WHERE id = ? AND workspace_id = ?",
        (link_id, workspace["id"]),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.report_not_found"))
    execute_db("DELETE FROM site_reports WHERE id = ?", (link_id,))


def get_site_report_link(token):
    if not token:
        return None
    token_hash = hashlib.sha256(str(token).encode("utf-8")).hexdigest()
    row = query_db(
        """
        SELECT r.*, w.path AS workspace_path, w.display_name, w.client_name, w.brand_json, w.gsc_property
        FROM site_reports r
        JOIN website_workspaces w ON w.id = r.workspace_id
        WHERE r.token_hash = ?
        """,
        (token_hash,),
        one=True,
    )
    return dict(row) if row else None


def build_public_site_report(link):
    workspace = {
        "id": link["workspace_id"],
        "path": link["workspace_path"],
        "display_name": link["display_name"],
        "client_name": link["client_name"],
        "brand_json": link["brand_json"],
        "gsc_property": link["gsc_property"],
    }
    member_rows = query_db(
        "SELECT user_id FROM team_members WHERE team_id IN (SELECT team_id FROM website_workspaces WHERE id = ?)",
        (workspace["id"],),
    )
    owner = query_db(
        "SELECT user_id FROM website_workspaces WHERE id = ?", (workspace["id"],), one=True
    )
    member_ids = {row["user_id"] for row in member_rows}
    if owner:
        member_ids.add(owner["user_id"])
    member_ids = list(member_ids) or [link["created_by"]]
    period = clean_report_period(link["period"])
    start, end = month_bounds(period)
    real_path = os.path.realpath(workspace["path"])
    placeholders = ", ".join("?" for _ in member_ids)
    changes = query_db(
        f"""
        SELECT created_at, source, summary, status
        FROM website_update_history
        WHERE user_id IN ({placeholders}) AND directory_path = ?
          AND created_at >= ? AND created_at < ?
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (*member_ids, real_path, start, end),
    )
    inquiries = query_db(
        """
        SELECT created_at, name, page, message, status
        FROM contact_messages
        WHERE workspace_id = ? AND created_at >= ? AND created_at < ?
        ORDER BY created_at DESC, id DESC
        LIMIT 100
        """,
        (workspace["id"], start, end),
    )
    resolved = query_db(
        """
        SELECT COUNT(*) AS total FROM site_findings
        WHERE directory_path = ? AND status = 'resolved'
          AND resolved_at >= ? AND resolved_at < ?
        """,
        (real_path, start, end),
        one=True,
    )["total"]
    requests_done = query_db(
        """
        SELECT COUNT(*) AS total FROM client_requests
        WHERE workspace_id = ? AND status IN ('done', 'approved')
          AND updated_at >= ? AND updated_at < ?
        """,
        (workspace["id"], start, end),
        one=True,
    )["total"]
    brand = parse_site_brand(workspace["brand_json"])
    creator = query_db(
        "SELECT company_name FROM users WHERE id = ?", (link["created_by"],), one=True
    )
    return {
        "period": period,
        "title": link["title"] or "",
        "site_name": workspace["display_name"] or os.path.basename(workspace["path"].rstrip(os.sep)),
        "client_name": workspace["client_name"] or "",
        "logo_url": f"/uploads/brand-logos/{brand['logo']}" if brand.get("logo") else "",
        "company_name": (creator["company_name"] if creator else "") or "",
        "changes": [dict(row) for row in changes],
        "changes_count": len(changes),
        "visits": None,
        "inquiries": [dict(row) for row in inquiries],
        "inquiries_count": len(inquiries),
        "issues_resolved": resolved,
        "requests_done": requests_done,
    }


NOTIFICATION_KINDS = ("inbox", "request", "alert")


def workspace_watcher_ids(workspace_id):
    workspace = query_db(
        "SELECT user_id, team_id FROM website_workspaces WHERE id = ?",
        (workspace_id,),
        one=True,
    )
    if not workspace:
        return []
    watchers = {workspace["user_id"]}
    if workspace["team_id"]:
        members = query_db(
            "SELECT user_id, role, permissions FROM team_members WHERE team_id = ?",
            (workspace["team_id"],),
        )
        for member in members:
            if parse_team_permissions(member["permissions"], member["role"]).get("view"):
                watchers.add(member["user_id"])
    return sorted(watchers)


def notify_workspace(workspace_id, kind, title, detail="", link="", exclude_user_id=None):
    if kind not in NOTIFICATION_KINDS:
        kind = "inbox"
    sent = 0
    for watcher_id in workspace_watcher_ids(workspace_id):
        if exclude_user_id is not None and watcher_id == exclude_user_id:
            continue
        execute_db(
            """
            INSERT INTO notifications (user_id, workspace_id, kind, title, detail, link, read)
            VALUES (?, ?, ?, ?, ?, ?, 0)
            """,
            (
                watcher_id,
                workspace_id,
                kind,
                str(title or "")[:200],
                str(detail or "")[:500],
                str(link or "")[:300],
            ),
        )
        sent += 1
    return sent


def list_notifications(user_id, limit=100):
    rows = query_db(
        """
        SELECT n.*, w.display_name AS site_name, w.path AS site_path
        FROM notifications n
        LEFT JOIN website_workspaces w ON w.id = n.workspace_id
        WHERE n.user_id = ?
        ORDER BY n.read ASC, n.id DESC
        LIMIT ?
        """,
        (user_id, max(1, min(int(limit or 100), 200))),
    )
    return [dict(row) for row in rows]


def count_unread_notifications(user_id):
    row = query_db(
        "SELECT COUNT(*) AS total FROM notifications WHERE user_id = ? AND read = 0",
        (user_id,),
        one=True,
    )
    return row["total"]


def mark_notification_read(user_id, notification_id):
    try:
        notification_id = int(notification_id)
    except (TypeError, ValueError):
        raise ValueError(translate("flash.notification_not_found"))
    row = query_db(
        "SELECT id FROM notifications WHERE id = ? AND user_id = ?",
        (notification_id, user_id),
        one=True,
    )
    if not row:
        raise ValueError(translate("flash.notification_not_found"))
    execute_db("UPDATE notifications SET read = 1 WHERE id = ?", (notification_id,))


def mark_all_notifications_read(user_id):
    execute_db("UPDATE notifications SET read = 1 WHERE user_id = ?", (user_id,))


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
    directory = require_site_directory(user_id)
    directory_path = os.path.realpath(directory["path"])
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

    execute_db(
        """
        INSERT INTO website_remote_connections (
            user_id, host, port, username, remote_path, key_path, auth_method, password, directory_path
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id, directory_path) DO UPDATE SET
            host = excluded.host,
            port = excluded.port,
            username = excluded.username,
            remote_path = excluded.remote_path,
            key_path = excluded.key_path,
            auth_method = excluded.auth_method,
            password = excluded.password,
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
    """Return the remote target bound to the user's current site, if any."""
    directory = get_site_directory(user_id)
    if not directory:
        return None
    row = query_db(
        """
        SELECT id, host, port, username, remote_path, key_path, auth_method,
               CASE WHEN password IS NOT NULL AND password != '' THEN 1 ELSE 0 END AS has_password,
               directory_path, created_at, updated_at
        FROM website_remote_connections
        WHERE user_id = ? AND directory_path = ?
        """,
        (user_id, os.path.realpath(directory["path"])),
        one=True,
    )
    if not row:
        return None
    remote = dict(row)
    remote["directory_matches"] = True
    return remote


def get_remote_connection_private(user_id):
    directory = get_site_directory(user_id)
    if not directory:
        return None
    return query_db(
        """
        SELECT id, host, port, username, remote_path, key_path, auth_method, password, directory_path,
               created_at, updated_at
        FROM website_remote_connections
        WHERE user_id = ? AND directory_path = ?
        """,
        (user_id, os.path.realpath(directory["path"])),
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
                "DELETE FROM website_remote_connections WHERE user_id = ? AND directory_path = ? AND id != ?",
                (user_id, workspace_real_path, remote["id"]),
            )
            execute_db(
                "UPDATE website_remote_connections SET directory_path = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (workspace_real_path, remote["id"]),
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
    command_env = os.environ.copy()
    command_env["PWD"] = workspace_path
    completed = subprocess.run(
        command,
        cwd=workspace_path,
        env=command_env,
        shell=True,
        text=True,
        input="",
        capture_output=True,
    )

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    return {
        "command": command,
        "cwd": workspace_path,
        "exit_code": completed.returncode,
        "output": output or translate("site.no_output"),
        "started_at": started_at,
    }


@locked_site_operation
def run_site_codex_update(user_id, prompt, suggested_image_path=None, provider=None, model=None, selection=None):
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
    user_message = prompt
    if selection:
        user_message = (
            f"{prompt}\n\n[Selected in preview: {selection.get('selector')} on {selection.get('page')}]"
        )
    save_codex_message(user_id, "user", user_message, directory_path=workspace_path)
    guarded_prompt = build_workspace_update_prompt(prompt, suggested_image_path)
    result = run_site_ai_fallback_update(
        user_id, workspace_path, guarded_prompt, provider, model, selection=selection
    )
    history_source = f"ai-direct:{provider}"
    reply = result.get("reply") or result.get("output") or ""
    after_manifest = build_workspace_manifest(workspace_path)
    changed_files = compare_workspace_manifests(before_manifest, after_manifest)
    diff_summary = build_update_diff_summary(workspace_path, snapshot_path, changed_files)
    save_codex_message(user_id, "assistant", reply, result["output"], result["exit_code"], workspace_path)
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


def run_site_ai_fallback_update(user_id, workspace_path, prompt, provider, model, selection=None):
    site_context = collect_site_edit_context(workspace_path)
    workspace = get_workspace_for_path(user_id, os.path.realpath(workspace_path))
    brand_context = brand_prompt_block(parse_site_brand(workspace["brand_json"])) if workspace else ""
    instruction = build_site_direct_edit_instruction(
        prompt, site_context, brand_context=brand_context,
        selection_context=selection_prompt_block(selection),
    )
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
    for root, dirs, files in os.walk(workspace_path, followlinks=False):
        dirs[:] = [item for item in dirs if not is_reserved_site_component(item) and not os.path.islink(os.path.join(root, item))]
        for file_name in files:
            source_path = os.path.join(root, file_name)
            if is_reserved_site_component(file_name) or os.path.islink(source_path):
                continue
            if not path_is_inside(workspace_path, source_path):
                continue
            relative_path = os.path.relpath(source_path, workspace_path).replace("\\", "/")
            try:
                size = os.path.getsize(source_path)
            except OSError:
                continue
            if size > 262144:
                continue
            candidates.append((size, relative_path, source_path))

    selected = []
    consumed = 0
    for _size, relative_path, source_path in sorted(candidates, key=lambda item: (item[0], item[1])):
        if len(selected) >= max_files or consumed >= max_chars:
            break
        try:
            with open(source_path, "rb") as file:
                raw = file.read(min(8000, max_chars - consumed))
        except OSError:
            continue
        if b"\x00" in raw:
            continue
        content = raw.decode("utf-8", errors="replace")
        if not content.strip():
            continue
        consumed += len(content)
        selected.append({"path": relative_path, "content": content})

    return selected


def build_site_direct_edit_instruction(prompt, site_context, brand_context="", selection_context=""):
    files_description = []
    for item in site_context:
        files_description.append(
            f"FILE: {item['path']}\n---BEGIN CONTENT---\n{item['content']}\n---END CONTENT---"
        )
    joined_files = "\n\n".join(files_description) or "(The workspace is empty. Create whatever the request needs.)"
    brand_block = f"\n\n{brand_context.strip()}" if brand_context and brand_context.strip() else ""
    selection_block = (
        f"\n\n{selection_context.strip()}" if selection_context and selection_context.strip() else ""
    )
    return f"""
You are a file assistant working inside the user's connected workspace. You can create new files and edit existing ones: documents, notes, code, configs, web pages, or anything else the user asks for.

Requirements:
- Create or update exactly the files the user's request needs. You may create new files, including inside new subfolders.
- Use relative paths inside the workspace only. Never use absolute paths or parent ("..") references.
- Stay inside the workspace.
- Return valid JSON only, with no markdown fences.
- JSON schema:
  {{
    "summary": "short explanation of the applied update",
    "files": [
      {{"path": "relative/path.ext", "content": "full new file content"}}
    ]
  }}
- Every file entry must contain the full replacement content for that file.
- Text content only. Do not include binary files.

User request:
{prompt}

Existing files:
{joined_files}{brand_block}{selection_block}
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
            or is_blocked_update_extension(relative_path)
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


def build_workspace_update_prompt(prompt, suggested_image_path=None):
    image_instruction = ""
    if suggested_image_path:
        image_instruction = f"""

User-provided image:
- The user uploaded an image for this update at: {suggested_image_path}
- Use this image only if it helps satisfy the user's request.
- If you reference it from created files, copy it into the workspace's normal assets/images location and reference that copy.
- Do not use unrelated generated or stock imagery when this uploaded image is clearly intended for the requested update.
""".rstrip()

    return f"""
You are working inside the user's selected directory. You can create new files and edit existing ones: documents, notes, code, configs, web pages, or anything else requested.

Rules:
- Stay strictly inside the selected directory.
- Inspect the existing files first when the request refers to them.
- Create new files or edit existing ones as the request needs, using relative paths.
- Match existing conventions (format, style, structure) when editing files that already exist.
{image_instruction}

User request:
{prompt}
""".strip()


def build_guided_seo_prompt(title, keyword, tone, audience, cta, brand_context=""):
    brand_block = f"\n\n{brand_context.strip()}" if brand_context and brand_context.strip() else ""
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
- Keep all work inside the selected website directory.{brand_block}
""".strip()


def build_quick_prompts():
    return {
        "hero": "Create a README.md file that describes this workspace: what each file is for and how everything is organized.",
        "section": "Add a useful new file to this workspace based on what already exists. Pick the most helpful format for its content.",
        "cta": "Review every file in this workspace and fix small mistakes, typos, and inconsistencies.",
        "landing": "Create a new markdown document with practical content related to this workspace.",
    }


def save_codex_message(user_id, role, content, raw_output=None, exit_code=None, directory_path=None):
    execute_db(
        """
        INSERT INTO website_codex_messages (user_id, role, content, raw_output, exit_code, directory_path)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            role,
            content,
            raw_output,
            str(exit_code) if exit_code is not None else None,
            directory_path,
        ),
    )


def list_codex_messages(user_id):
    directory = get_site_directory(user_id)
    if not directory:
        return []
    current = os.path.realpath(directory["path"])
    execute_db(
        "UPDATE website_codex_messages SET directory_path = ? WHERE user_id = ? AND directory_path IS NULL",
        (current, user_id),
    )
    scope_ids = team_scope_user_ids(user_id)
    if not scope_ids:
        return []
    placeholders = ", ".join("?" for _ in scope_ids)
    rows = query_db(
        f"""
        SELECT m.id, m.role, m.content, m.exit_code, m.created_at,
               u.name AS author_name, u.email AS author_email
        FROM website_codex_messages m
        LEFT JOIN users u ON u.id = m.user_id
        WHERE m.user_id IN ({placeholders}) AND m.directory_path = ?
        ORDER BY m.id ASC
        """,
        (*scope_ids, current),
    )
    return [dict(row) for row in rows]


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
    scope_ids = team_scope_user_ids(user_id)
    if not scope_ids:
        return []
    placeholders = ", ".join("?" for _ in scope_ids)
    rows = query_db(
        f"""
        SELECT h.id, h.source, h.summary, h.exit_code, h.status, h.snapshot_path, h.changed_files,
               h.diff_summary, h.directory_path, h.created_at,
               u.name AS author_name, u.email AS author_email
        FROM website_update_history h
        LEFT JOIN users u ON u.id = h.user_id
        WHERE h.user_id IN ({placeholders})
        ORDER BY h.created_at DESC, h.id DESC
        LIMIT 60
        """,
        tuple(scope_ids),
    )
    updates = [format_update_history(row) for row in rows]
    return [
        update
        for update in updates
        if update.get("directory_path")
        and os.path.realpath(update["directory_path"]) == current_directory
    ][:20]


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
        "UPDATE website_update_history SET status = ? WHERE id = ?",
        (status, update["id"]),
    )


def get_update_history_item(user_id, update_id):
    try:
        update_id = int(update_id)
    except (TypeError, ValueError):
        return None
    scope_ids = team_scope_user_ids(user_id)
    if not scope_ids:
        return None
    placeholders = ", ".join("?" for _ in scope_ids)
    row = query_db(
        f"""
        SELECT h.id, h.user_id, h.source, h.summary, h.exit_code, h.status, h.snapshot_path,
               h.changed_files, h.diff_summary, h.directory_path, h.created_at,
               u.name AS author_name, u.email AS author_email
        FROM website_update_history h
        LEFT JOIN users u ON u.id = h.user_id
        WHERE h.user_id IN ({placeholders}) AND h.id = ?
        """,
        (*scope_ids, update_id),
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
        ".c", ".cfg", ".cpp", ".css", ".csv", ".go", ".h", ".hpp", ".htm",
        ".html", ".ini", ".java", ".js", ".json", ".jsx", ".kt", ".log",
        ".lua", ".md", ".php", ".pl", ".py", ".r", ".rb", ".rs", ".scala",
        ".sh", ".sql", ".swift", ".tex", ".toml", ".ts", ".tsx", ".txt",
        ".vue", ".xml", ".yml", ".yaml",
    }
    return os.path.splitext(path)[1].lower() in text_extensions


def is_blocked_update_extension(path):
    # The chatbot writes text content, so paths with a binary-only extension
    # would produce corrupt files. Everything else (including new or
    # extension-less names such as Dockerfile) is allowed inside the workspace.
    blocked_extensions = {
        ".7z", ".a", ".avi", ".bin", ".bmp", ".bz2", ".db", ".dll", ".doc",
        ".docx", ".dylib", ".exe", ".flac", ".gif", ".gz", ".ico", ".jpeg",
        ".jpg", ".lib", ".mkv", ".mov", ".mp3", ".mp4", ".o", ".obj", ".otf",
        ".pdf", ".png", ".ppt", ".pptx", ".rar", ".so", ".sqlite", ".sqlite3",
        ".tar", ".tgz", ".tiff", ".ttf", ".wav", ".webp", ".woff", ".woff2",
        ".xls", ".xlsx", ".xz", ".zip",
    }
    return os.path.splitext(path)[1].lower() in blocked_extensions


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
    if task_type == "social_post":
        return (
            "Write a single ready-to-publish social media post. Keep it concise, natural, and specific; "
            "avoid hashtags unless they clearly help. Return only the post text, with no quotes or preamble."
            f"\n\nUser request:\n{prompt.strip()}{context_block}"
        )
    if task_type == "social_ideas":
        return (
            "Suggest social media post ideas based on the website context below (brand, pages, events). "
            "Return 5 numbered ideas, one per line, each with a short title, a colon, and a one-sentence angle "
            "that references real content from the site. No preamble, no extra commentary."
            f"\n\nUser request:\n{prompt.strip()}{context_block}"
        )
    if task_type == "health_summary":
        return (
            "Explain these website issues in plain language for a non-technical site owner: "
            "what each issue means, why it matters, and what the fix does. Keep it short, "
            "grouped by page, with no code."
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


def perform_multipart_request(url, fields, files, headers=None, timeout=300):
    boundary = f"----oneboard-{secrets.token_hex(16)}"
    body = bytearray()
    for name, value in (fields or {}).items():
        body += f"--{boundary}\r\n".encode("utf-8")
        body += f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8")
        body += f"{value}\r\n".encode("utf-8")
    for name, (filename, content, content_type) in (files or {}).items():
        body += f"--{boundary}\r\n".encode("utf-8")
        body += (
            f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
        ).encode("utf-8")
        body += f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
        body += content + b"\r\n"
    body += f"--{boundary}--\r\n".encode("utf-8")
    request_headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    if headers:
        request_headers.update(headers)
    req = urllib.request.Request(url, data=bytes(body), headers=request_headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        body_text = error.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body_text)
        except json.JSONDecodeError:
            parsed = {"error": {"message": body_text.strip() or str(error)}}
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
    if not isinstance(payload, dict):
        return "", {}
    error = payload.get("error")
    if isinstance(error, dict):
        raise ValueError(
            error.get("message") or error.get("code") or "Muse API request failed."
        )
    if isinstance(error, str) and error.strip():
        raise ValueError(error.strip())
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
    if not text:
        for choice in payload.get("choices", []) or []:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message") or {}
            content = message.get("content") or ""
            if isinstance(content, str) and content.strip():
                text += content
    usage = payload.get("usage") or {}
    return text.strip(), usage


def describe_empty_provider_response(provider, response):
    if not isinstance(response, dict) or not response:
        return ""
    status = response.get("status") or response.get("state") or ""
    keys = ", ".join(sorted(str(key) for key in response.keys())[:12])
    detail = f" (provider '{provider}'"
    if status:
        detail += f", status '{status}'"
    if keys:
        detail += f", fields: {keys}"
    return detail + ")"


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
    cached = get_muse_models_cache(user_id)
    # Keep text generation available for accounts whose cache was populated
    # before Muse Wonder became the default model.
    return list(dict.fromkeys((cached or []) + MUSE_FALLBACK_MODELS))


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


BUFFER_API_URL = "https://api.buffer.com"


def get_user_buffer_api_key(user_id):
    try:
        row = query_db(
            "SELECT buffer_api_key AS api_key FROM users WHERE id = ?",
            (user_id,),
            one=True,
        )
    except sqlite3.OperationalError:
        return ""
    return (row["api_key"] or "").strip() if row else ""


def buffer_graphql(api_key, query):
    payload = perform_json_request(
        BUFFER_API_URL,
        {"query": query},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30,
    )
    if isinstance(payload, dict) and payload.get("errors"):
        first_error = (payload["errors"] or [{}])[0] or {}
        message = first_error.get("message") if isinstance(first_error, dict) else ""
        raise ValueError(message or "Buffer API request failed.")
    return (payload or {}).get("data") or {}


def list_buffer_organizations(api_key):
    data = buffer_graphql(api_key, "query GetOrganizations { account { organizations { id name } } }")
    organizations = ((data.get("account") or {}).get("organizations")) or []
    return [org for org in organizations if isinstance(org, dict) and org.get("id")]


def validate_buffer_api_key(api_key):
    try:
        organizations = list_buffer_organizations(api_key)
    except ValueError as error:
        raise ValueError(f"Buffer API key validation failed: {error}") from error
    if not organizations:
        raise ValueError("Buffer API key validation failed: no organizations were returned.")
    return organizations


def list_buffer_channels(api_key):
    channels = []
    for organization in list_buffer_organizations(api_key):
        data = buffer_graphql(
            api_key,
            "query GetChannels { channels(input: { organizationId: %s }) { id name service } }"
            % json.dumps(organization["id"]),
        )
        for channel in data.get("channels") or []:
            if not isinstance(channel, dict) or not channel.get("id"):
                continue
            channels.append(
                {
                    "id": channel["id"],
                    "name": channel.get("name") or channel["id"],
                    "service": channel.get("service") or "",
                    "organization_id": organization["id"],
                    "organization_name": organization.get("name") or "",
                }
            )
    return channels


BUFFER_POST_TYPES = ("post", "story", "reel")
BUFFER_TYPED_SERVICES = ("facebook", "instagram")


def create_buffer_post(api_key, channel_id, text, draft=False, image_url=None, publish_now=False,
                       post_type="post", channel_service=""):
    draft_flag = ", saveToDraft: true" if draft else ""
    assets_block = ""
    if image_url:
        assets_block = ", assets: [{ image: { url: %s } }]" % json.dumps(image_url)
    mode_block = "mode: addToQueue"
    if publish_now and not draft:
        # Buffer rejects timestamps that are not in the future, and any "now"
        # is already past when it arrives. +60s is the closest the API allows
        # to an immediate publish.
        due_now = (datetime.now(timezone.utc) + timedelta(seconds=60)).strftime(
            "%Y-%m-%dT%H:%M:%S.000Z"
        )
        mode_block = f"mode: customScheduled, dueAt: {json.dumps(due_now)}"
    metadata_block = ""
    service = (channel_service or "").strip().lower()
    if service in BUFFER_TYPED_SERVICES and post_type in BUFFER_POST_TYPES:
        metadata_block = f", metadata: {{ {service}: {{ type: {post_type} }} }}"
    query = (
        "mutation CreateBufferPost { createPost(input: { text: %s, channelId: %s, "
        "schedulingType: automatic, %s%s%s%s }) { "
        "... on PostActionSuccess { post { id text dueAt } } "
        "... on MutationError { message } } }"
        % (json.dumps(text), json.dumps(channel_id), mode_block, draft_flag, assets_block,
           metadata_block)
    )
    data = buffer_graphql(api_key, query)
    result = data.get("createPost") or {}
    post = result.get("post")
    if not isinstance(post, dict) or not post.get("id"):
        raise ValueError(result.get("message") or "Buffer did not accept the post.")
    return {"id": post["id"], "text": post.get("text") or "", "due_at": post.get("dueAt") or ""}


def record_social_post(user_id, channel_id, channel_name, text, status, buffer_post_id=None,
                      image_url=None, post_type="post"):
    execute_db(
        """
        INSERT INTO social_posts (user_id, channel_id, channel_name, text, status, buffer_post_id,
                                  image_url, post_type)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, channel_id, channel_name, text, status, buffer_post_id, image_url, post_type),
    )


def list_social_posts(user_id, limit=20):
    return query_db(
        """
        SELECT id, channel_id, channel_name, text, status, buffer_post_id, image_url,
               post_type, created_at
        FROM social_posts
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ?
        """,
        (user_id, limit),
    )


def social_image_directory():
    return os.path.join(UPLOAD_DIR, "social-images")


def build_social_suggestions(user_id, max_items=6):
    """Rule-based post ideas derived from the connected site (no AI key needed)."""
    intelligence = build_site_intelligence(user_id)
    if not intelligence.get("has_site"):
        return {"has_site": False, "site_name": "", "suggestions": []}
    brand = intelligence.get("brand") or {}
    business = brand.get("business_name") or intelligence.get("site_name") or ""
    suggestions = []

    def _add(title, prompt):
        if len(suggestions) < max_items and prompt:
            suggestions.append({"title": title[:120], "prompt": prompt[:500]})

    services = (brand.get("services") or "").strip()
    if services:
        first_service = re.split(r"[,;\n]", services)[0].strip()
        _add(
            f"Present: {first_service[:60]}" if first_service else "Present your services",
            f"Announce {business + ': ' if business else ''}{first_service or services[:200]}"
            " and invite people to learn more on our website.",
        )
    for page in (intelligence.get("pages") or [])[1:4]:
        label = page.get("title") or page.get("heading") or ""
        excerpt = (page.get("excerpt") or "")[:220]
        if not label and not excerpt:
            continue
        _add(
            f"Share page: {label[:60] or page['path']}",
            f"Write a post inviting followers to visit the '{label or page['path']}' page"
            + (f" ({excerpt})" if excerpt else "")
            + ".",
        )
    for event in intelligence.get("upcoming_events") or []:
        if not event.get("title"):
            continue
        _add(
            f"Promote: {event['title'][:60]}",
            f"Announce our upcoming {event.get('kind') or 'event'} '{event['title']}'"
            + (f" starting {event['starts_on']}" if event.get("starts_on") else "")
            + ".",
        )
    audience = (brand.get("audience") or "").strip()
    if audience:
        _add(
            "Speak to your audience",
            f"Write a helpful tip for {audience[:160]} related to what {business or 'we'} do.",
        )
    tagline = (brand.get("tagline") or "").strip()
    if tagline:
        _add(
            "Brand message",
            f"Turn this brand message into an engaging post: {tagline[:200]}",
        )
    return {
        "has_site": True,
        "site_name": intelligence.get("site_name") or "",
        "suggestions": suggestions,
    }


def generate_social_ideas_with_ai(user_id, hint="", provider=None, model=None):
    intelligence = build_site_intelligence(user_id)
    if not intelligence.get("has_site"):
        raise ValueError(translate("social.suggestions_empty"))
    prompt = hint.strip() or "Suggest varied post ideas covering our services, pages, and events."
    run = run_ai_text_task(user_id, "social_ideas", prompt, provider=provider, model=model)
    ideas = []
    for line in (run["response_text"] or "").splitlines():
        cleaned = re.sub(r"^\s*(?:\d+[.)\-:]\s*|[-*•]\s*)", "", line).strip()
        if not cleaned:
            continue
        if ":" in cleaned:
            title = cleaned.split(":", 1)[0]
            ideas.append({"title": title.strip()[:120], "prompt": cleaned[:500]})
        else:
            ideas.append({"title": cleaned[:120], "prompt": cleaned[:500]})
        if len(ideas) >= 8:
            break
    return {"ideas": ideas, "provider": run["provider"]}


def resolve_own_social_image(user_id, image_url):
    candidate = (image_url or "").strip()
    if not candidate:
        raise ValueError(translate("flash.image_invalid"))
    path = urllib.parse.urlparse(candidate).path or ""
    directory = None
    if path.startswith("/uploads/generated-images/"):
        directory = generated_image_directory()
    elif path.startswith("/uploads/social-images/"):
        directory = social_image_directory()
    if directory is None:
        raise ValueError(translate("flash.image_invalid"))
    safe_name = posixpath.basename(path)
    prefix = f"user-{user_id}-"
    if not safe_name.startswith(prefix):
        raise ValueError(translate("flash.image_invalid"))
    absolute_path = os.path.realpath(os.path.join(directory, safe_name))
    if os.path.dirname(absolute_path) != os.path.realpath(directory):
        raise ValueError(translate("flash.image_invalid"))
    if not os.path.isfile(absolute_path):
        raise ValueError(translate("flash.image_invalid"))
    return absolute_path


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


def run_muse_image_edit(user_id, image_bytes, instruction, model=None, output_format="png"):
    instruction = (instruction or "").strip()
    if not instruction:
        raise ValueError(translate("social.edit_instruction_required"))
    if not image_bytes:
        raise ValueError(translate("flash.image_invalid"))
    api_key = get_user_ai_provider_api_key(user_id, "muse")
    if not api_key:
        raise ValueError("No Muse API key configured.")
    resolved_model = (model or "").strip() or MUSE_IMAGE_DEFAULT_MODEL
    output_format = (output_format or "png").strip().lower() or "png"
    response = perform_multipart_request(
        f"{MUSE_API_BASE}/images/edits",
        {"prompt": instruction, "model": resolved_model, "response_format": "b64_json"},
        {"image": ("source.png", image_bytes, "image/png")},
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=300,
    )
    if isinstance(response, dict) and response.get("error"):
        raise ValueError(extract_provider_error_message(response, "Image edit failed."))
    edited_bytes = None
    entries = (response.get("data") or []) if isinstance(response, dict) else []
    if entries and isinstance(entries[0], dict):
        payload = entries[0].get("b64_json") or ""
        if payload:
            try:
                edited_bytes = base64.b64decode(payload)
            except (ValueError, TypeError) as error:
                raise ValueError("The Muse API returned an invalid image.") from error
        elif entries[0].get("url"):
            download = urllib.request.Request(entries[0]["url"], method="GET")
            try:
                with urllib.request.urlopen(download, timeout=60) as stream:
                    edited_bytes = stream.read(MAX_IMAGE_UPLOAD_BYTES + 1)
            except (urllib.error.URLError, OSError) as error:
                raise ValueError("The Muse API did not return an image.") from error
            if len(edited_bytes) > MAX_IMAGE_UPLOAD_BYTES:
                raise ValueError("The Muse API returned an oversized image.")
    if not edited_bytes:
        raise ValueError("The Muse API did not return an image.")
    directory = generated_image_directory()
    filename = f"user-{user_id}-{datetime.now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}.{output_format}"
    image_path = os.path.join(directory, filename)
    os.makedirs(directory, exist_ok=True)
    with open(image_path, "wb") as file:
        file.write(edited_bytes)
    save_ai_run(
        user_id,
        "muse",
        resolved_model,
        "image_edit",
        instruction,
        status="completed",
        response_text=filename,
        usage={},
    )
    return {
        "filename": filename,
        "path": image_path,
        "model": resolved_model,
        "response_id": response.get("id") or "" if isinstance(response, dict) else "",
        "output_format": output_format,
        "size_bytes": len(edited_bytes),
    }


def list_generated_images(user_id, limit=50, workspace_id=None):
    directory = generated_image_directory()
    prefix = f"user-{user_id}-"
    try:
        entries = os.listdir(directory)
    except OSError:
        return []
    known = {
        row["filename"]: row
        for row in query_db(
            "SELECT filename, workspace_id, prompt FROM site_images WHERE user_id = ?",
            (user_id,),
        )
    }
    items = []
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
        record = known.get(filename)
        if record is None:
            try:
                execute_db(
                    "INSERT INTO site_images (user_id, workspace_id, filename, prompt) VALUES (?, ?, ?, ?)",
                    (user_id, None, filename, ""),
                )
            except sqlite3.IntegrityError:
                pass
            record = {"workspace_id": None, "prompt": ""}
        if workspace_id is not None and (record["workspace_id"] or None) != workspace_id:
            continue
        items.append(
            {
                "filename": filename,
                "url": f"/uploads/generated-images/{filename}",
                "size_bytes": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "prompt": record["prompt"] or "",
                "workspace_id": record["workspace_id"],
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
        # muse-image is for image generation and may return no text at all.
        # Existing accounts can still have that old model saved as their default.
        if model == MUSE_IMAGE_DEFAULT_MODEL:
            model = MUSE_TEXT_DEFAULT_MODEL
        payload = {
            "model": model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                    ],
                },
            ],
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
        detail = describe_empty_provider_response(provider, response)
        raise ValueError(f"The AI provider returned an empty response.{detail}")
    return text, usage, model


SITE_INTELLIGENCE_TASKS = frozenset(
    {"website_update", "seo_brief", "content_brief", "social_post", "social_ideas", "health_summary"}
)


def run_ai_text_task(user_id, task_type, prompt, provider=None, model=None, context=""):
    provider, model = resolve_ai_provider_model(user_id, provider=provider, model=model)
    final_prompt = build_ai_task_prompt(task_type, prompt, context=context)
    if task_type.strip().lower() in SITE_INTELLIGENCE_TASKS:
        intelligence_text = site_intelligence_prompt_block(user_id)
        if intelligence_text:
            final_prompt = f"{final_prompt}\n\n{intelligence_text}"
        else:
            brand_text = current_workspace_brand_text(user_id)
            if brand_text:
                final_prompt = f"{final_prompt}\n\n{brand_text}"
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
    scope_ids = team_scope_user_ids(user_id)
    if not scope_ids:
        return []
    placeholders = ", ".join("?" for _ in scope_ids)
    rows = query_db(
        f"""
        SELECT b.id, b.directory_path, b.filename, b.backup_path, b.file_count, b.size_bytes,
               b.created_at, u.name AS author_name, u.email AS author_email
        FROM website_backups b
        LEFT JOIN users u ON u.id = b.user_id
        WHERE b.user_id IN ({placeholders})
        ORDER BY b.created_at DESC, b.id DESC
        """,
        tuple(scope_ids),
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

    scope_ids = team_scope_user_ids(user_id)
    if not scope_ids:
        return None
    placeholders = ", ".join("?" for _ in scope_ids)
    return query_db(
        f"""
        SELECT id, directory_path, filename, backup_path, file_count, size_bytes, created_at
        FROM website_backups
        WHERE user_id IN ({placeholders}) AND id = ?
        """,
        (*scope_ids, backup_id),
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


def send_password_reset_email(user_id, recipient):
    settings = smtp_settings()
    if not settings["host"] or not settings["from_address"]:
        raise ValueError("Password reset is not configured. Set SMTP_HOST and SMTP_FROM.")
    if bool(settings["username"]) != bool(settings["password"]):
        raise ValueError("SMTP_USERNAME and SMTP_PASSWORD must be configured together.")

    token = create_password_reset_token(user_id)
    reset_url = url_for("reset_password", token=token, _external=True)
    message = email.message.EmailMessage()
    message["Subject"] = "Reset your ONEBoard password"
    message["From"] = settings["from_address"]
    message["To"] = recipient
    message.set_content(
        "You requested a password reset for your ONEBoard account.\n\n"
        f"Reset your password here:\n{reset_url}\n\n"
        "This link expires in 1 hour. If you did not request this, ignore this email."
    )
    try:
        with smtplib.SMTP(settings["host"], settings["port"], timeout=20) as server:
            if settings["use_tls"]:
                server.starttls()
            if settings["username"]:
                server.login(settings["username"], settings["password"])
            server.send_message(message)
    except (OSError, smtplib.SMTPException) as error:
        raise ValueError("Unable to send the reset email. Check the SMTP configuration.") from error


def save_uploaded_image(user_id, upload, target_dir, prefix):
    filename = upload.filename or ""
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in {"png", "jpg", "jpeg", "jfif", "gif", "webp"}:
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
        "jfif": header.startswith(b"\xff\xd8\xff"),
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
