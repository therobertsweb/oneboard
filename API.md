# ONEBoard API

REST API with full parity: everything the web app does is available here.
Base URL: same host as the web app (e.g. `http://127.0.0.1:5000`).

## Auth (session cookie)

1. `POST /api/auth/register` — `{name, email, password, confirm_password}` → sends verification email.
2. `POST /api/auth/verify-email` — `{token}` → marks email verified.
3. `POST /api/auth/login` — `{email, password}` → sets the session cookie. Keep the cookie jar for all later calls.
4. `POST /api/auth/logout` — closes the session.

Recovery: `POST /api/auth/forgot-password` (`{email}`) sends the reset link by email (1h expiry);
`POST /api/auth/reset-password` (`{token, password, confirm_password}`).
Resend link: `POST /api/auth/resend-verification` (`{email}`).
Session check: `GET /api/session`.

All endpoints below require login except the auth ones above.
Success envelope: `{ok: true, ...}`. Errors: `{ok: false, error}` with HTTP status.

## Context shared between sections

Social generation/publication, local health actions and public security scans accept
`expected_directory_path` in POST payloads. The web UI sends the project that was
open when the page rendered; a mismatch rejects the operation before it runs.
Social suggestions/history also accept it as a query parameter.

`GET /api/site-manager/intelligence` combines current pages, brand, local findings,
calendar, recent edits and the latest security scan linked to the configured domain
and current folder. Studio edits refresh local health; they do not mark the public
security scan as resolved. `GET /security-scan/<id>/repair` prepares a task in Studio
for a matching scan, without changing files until the user sends it.

Social history is scoped to the current folder. Use
`GET /api/social/buffer/posts?scope=unassigned` for older records with no project.
See [the integration review](INTEGRATION_REVIEW.md) for the workflow and boundaries.

## Dashboard & Search Console

- `GET /api/dashboard` — stats, charts, opportunities.
- `GET /api/google-search-console/connect` — starts OAuth (returns auth URL).
- `GET /api/google-search-console/callback` — OAuth callback.
- `POST /api/google-search-console/site` — `{site_url}` selects property.
- `POST /api/google-search-console/disconnect` — unlinks the account.

## Site manager (file chatbot + workspace)

- `GET /api/site-manager` — full state: directory, projects, files, chat, updates, backups.
- `POST /api/site-manager/connect` — `{path}` or `{project_id}` connects a local directory (switches projects too; creates the folder if missing). Team projects open by id for members; other teams' folders are refused.
- `POST /api/site-manager/projects/remove` — `{project_id}` forgets a project (files kept; disconnects if current).
- `GET /api/site-manager/browse-directory?path=` — list subfolders visually.
- `GET /api/site-manager/files/raw?path=` — download a workspace file.
- `POST /api/site-manager/files/delete` — delete a workspace file.
- `POST /api/site-manager/codex-update` — `{prompt, provider?, model?, selected_asset?}` + optional `suggested_image` file. Creates/edits any files.
- `POST /api/site-manager/seo-content` — `{title, keyword, tone?, audience?, cta?}`.
- `POST /api/site-manager/update/action` — `{update_id, action}` where action is `approve`, `publish` or `restore`.
- `POST /api/site-manager/terminal/run` — `{command}` runs an allowed command.
- `POST /api/site-manager/backup` / `POST /api/site-manager/restore` — snapshots.
- `POST /api/site-manager/assets/upload` — multipart `asset` image.
- `GET /api/site-manager/assets/raw?path=` — download an asset.
- `POST /api/site-manager/remote` — `{host, port, username, remote_path, ...}` saves SSH target.
- `POST /api/site-manager/remote/test` — tests the SSH connection.
- `POST /api/site-manager/remote/sync` — syncs with the remote.
- `POST /api/site-manager/ssh-key` — generates the user SSH key.

## Teams & collaboration

- `GET /api/teams` — my teams plus `pending_invites` for my email.
- `POST /api/teams` — `{name, description?}` creates a team (creator becomes owner).
- `GET /api/teams/<id>` — team detail: members, pending invites, shared projects.
- `POST /api/teams/<id>` — `{name?, description?}` renames (needs `manage`).
- `DELETE /api/teams/<id>` — deletes the team (owner only; files on disk are kept).
- `POST /api/teams/<id>/invites` — `{email, role?}` invites (`viewer`/`editor`/`client` need `invite`, `admin` needs `manage`). Returns `invite`, `invite_link` (`/teams/invites/<token>`, 7-day expiry) and `email_sent` (false when SMTP is not configured — share the link manually).
- `DELETE /api/teams/<id>/invites/<invite_id>` — revokes an invitation.
- `POST /api/teams/invites/accept` — `{token}` joins the team (account email must match).
- `POST /api/teams/invites/<invite_id>/accept` — accepts one of my pending invites.
- `POST /api/teams/<id>/members/<user_id>` — `{role?, permissions?}` updates role/granular permissions (needs `manage`; the owner row is locked).
- `DELETE /api/teams/<id>/members/<user_id>` — removes a member (needs `manage`).
- `POST /api/teams/<id>/leave` — leaves the team (owner must transfer first).
- `POST /api/teams/<id>/transfer` — `{user_id}` transfers ownership (owner only).
- `POST /api/teams/<id>/projects` — `{project_id? | path?}` shares a folder with the team (needs `manage`; a folder can only belong to one team).
- `DELETE /api/teams/<id>/projects/<project_id>` — unshares a project (needs `manage`; files kept).

Roles are presets over six granular permissions (`view`, `edit`, `publish`, `invite`, `manage`, `billing`): owner and admin have all of them, editor has `view`+`edit`, viewer and client have `view` only. Editing single permissions switches the role to `custom`. `billing` is reserved for a future billing module.

On team projects, Studio enforces: `view` to open/read, `edit` for files/assistant/terminal/backups, `publish` for remote targets and approve/publish actions. Chat, update history and backups are shared with the whole team (each entry keeps its author). Pages: `/teams`, `/teams/<id>`, `/teams/invites/<token>`.

Trust model: team permissions are enforced at the app layer. ONEBoard runs on a single server account, so treat members as trusted collaborators, like people with access to the same machine.

## Remote connections are per site

Each site keeps its own independent SSH target: saving a connection binds it to the current folder, and switching projects switches the connection shown. On team projects every member configures their own credentials (they are never shared); using them requires the `publish` permission. Databases from older versions are migrated automatically (bound connections keep their site).

## Site record & brand memory

Each project folder keeps its own record: display name, client name, brand memory, logo, Search Console property, generated images, remote target and history. Switching clients is switching projects.

- `GET /api/site-manager/site` — current site record: names, `brand`, `gsc_property`, `images`, `can_edit`.
- `POST /api/site-manager/site` — `{display_name?, client_name?, brand?, gsc_property?}` updates it (needs `edit` on team projects). `brand` accepts `business_name`, `tagline`, `services`, `audience`, `tone`, `colors{primary,secondary,accent}`, `fonts{headings,body}`, `phone`, `email`, `address`, `website`, `notes` (partial updates merge).
- `POST /api/site-manager/site/logo` — multipart `logo` image (needs `edit`). Served at `/uploads/brand-logos/<file>` to people with access to the site.
- `GET /api/ai/images?scope=site` — generated images attached to the current site (default lists all of mine). Images generated while a team site is open are visible to its members.
- Search Console: each site can pin its own `gsc_property`; the dashboard then shows that site's stats (`site_scoped: true`) without changing the account default.

Brand memory is injected automatically into site updates, SEO content, image generation style, and `website_update`/`seo_brief`/`content_brief`/`social_post` AI tasks whenever a site with brand data is open. Page: `/site-manager/site` (linked from Studio's project panel).

## Visual preview, targeted edits & before/after compare

- `GET /site-manager/preview/<path>` — serves the current site as a real website (relative assets resolve). Add `?picker=1` to inject the element picker on HTML pages (needs `view`).
- `POST /api/site-manager/preview/select` — `{page, selector, tag?, text?, html?, image_src?}` stores the picked element for the next assistant update (needs `view`). `DELETE` clears it. The next `codex-update` consumes it and targets that element/section, so users can say "cambia esto" instead of describing the location.
- `GET /api/site-manager/updates/<id>/compare` — per-file `{path, change, kind, before_url, after_url}` where kind is `visual` (pages/images), `text` or `binary` (needs `view`).
- `GET /site-manager/updates/<id>/before/<path>` — serves the pre-change file from the update snapshot, so relative assets render as they were (needs `view`).
- Page `/site-manager/updates/<id>/compare` shows before/after side by side with desktop/mobile widths plus approve/publish/restore actions. Studio has a Preview tab (device toggle, picker, prompt box) and a Compare link on every update.

## Action center

- `POST /api/site-manager/health/scan` — `{skip_external?}` scans the current site for pages without titles, broken internal/external links, heavy images (>500KB), images without alt text, and forms without destination/submit/field names (needs `view`). External links are checked concurrently (HEAD with GET fallback, 6s timeout, max 25 URLs).
- `GET /api/site-manager/health` — open findings with page, detail and editable proposals, ignored list, and last scan (needs `view`).
- `POST /api/site-manager/health/findings/<id>/apply` — applies the fix (needs `edit`): set title, remove link keeping text, add alt text, name form fields, optimize images (requires Pillow, else returns guidance). Every fix snapshots first and records `action-center` history, so it can be reviewed and restored like any update.
- `POST /api/site-manager/health/findings/<id>/ignore|reopen` — manages ignored findings (needs `edit`). Fixed issues auto-resolve on the next scan; ignored ones stay ignored.
- `POST /api/site-manager/health/fix-all` — applies every automatic fix in one snapshot/history entry (needs `edit`); returns `fixed`, `skipped` (forms without destination/submit need AI or manual work) and `skipped_checks`.
- `POST /api/site-manager/health/ai-fix` — `{finding_ids?, provider?, model?}` the AI rewrites the affected pages to fix every open issue, including forms (needs `edit`); snapshots first, re-scans, and returns `fixed` plus `pages`.
- `POST /api/site-manager/health/summary` — `{provider?, model?}` plain-language explanation of the open issues (needs `view`).

Page: `/site-manager/health` (linked from Studio with the open count).

## Client requests & approvals

Shareable review links (`/r/<token>`, no login) let a client annotate the site, file requests with attachments, comment, and approve proposals.

- `POST /api/site-manager/request-links` — `{label?, expires_days?}` creates a link (needs `manage`; the URL is shown once). `DELETE /api/site-manager/request-links/<id>` revokes it.
- `GET /api/site-manager/requests` — links plus requests for the current site (needs `view`).
- `GET /api/site-manager/requests/<id>` — full thread (needs `view`).
- `POST /api/site-manager/requests/<id>/comments` — team comment, JSON or multipart with attachments (needs `edit`).
- `POST /api/site-manager/requests/<id>/status` — `{status, proposal?}` with `open|in_review|proposed|done` (needs `edit`; `proposed` requires text).
- `DELETE /api/site-manager/requests/<id>` — deletes a request with its comments and files (needs `edit`).
- Portal (token in URL, no login): `GET /r/<token>` portal with annotate-and-request form, `POST /r/<token>/requests` (multipart), `GET /r/<token>/requests/<id>` thread, `POST .../comments`, `POST .../approve|reject` (only from `proposed`), `GET /r/<token>/preview/<path>` site files, `GET /r/<token>/attachments/<file>`.
- Attachments: images or PDF up to 10 MB each.

Status flow: `open` → `in_review` → `proposed` → `approved`/`rejected` (client) → `done` (team). Pages: `/site-manager/requests` and `/site-manager/requests/<id>` (linked from Studio with the open count).

## Publish calendar

Scheduled promos, blog posts, price updates and notes with start/end dates. Status is computed: `scheduled` → `active` → `expired`, plus `done`/`cancelled`. Executing an event runs its brief through the site AI update and links the resulting update.

- `GET /api/site-manager/calendar` — events for the current site (needs `view`).
- `POST /api/site-manager/calendar` — `{kind?, title, brief?, page?, starts_on?, ends_on?}` (needs `edit`).
- `POST /api/site-manager/calendar/<id>` — partial update (needs `edit`).
- `POST /api/site-manager/calendar/<id>/cancel` — (needs `edit`).
- `DELETE /api/site-manager/calendar/<id>` — (needs `edit`).
- `POST /api/site-manager/calendar/<id>/execute` — runs the brief as a site update (needs `edit`).

Page: `/site-manager/calendar` (in the sidebar).

## Contact inbox

Each site gets form receiver tokens; any form can POST to the public endpoint (form-encoded or JSON, CORS `*`, 20/hour rate limit per IP+token, revoked tokens get 404, empty messages get 400).

- `POST /api/site-manager/inbox/token` — `{label?}` creates a token (needs `manage`; returns `token` + `submit_url`). `DELETE /api/site-manager/inbox/token/<id>` revokes it.
- `GET /api/site-manager/inbox/snippet` — embeddable HTML form for the latest active token (needs `view`).
- `GET /api/site-manager/inbox` (`?status=new|attended`) — messages plus tokens (needs `view`).
- `POST /api/site-manager/inbox/<id>/attend|reopen` — (needs `edit`).
- `DELETE /api/site-manager/inbox/<id>` — (needs `edit`).
- Public: `POST /forms/<token>/submit` (no login; `OPTIONS` answers the CORS preflight).

Page: `/site-manager/inbox` (in the sidebar with the new-message count).

## Automatic alerts

Uptime checks (HTTP status) and TLS expiry checks (warn below N days), plus automatic publish-failure alerts. Re-checking while an alert is open updates it instead of duplicating; recovery auto-resolves.

- `POST /api/site-manager/alerts/rules` — `{kind: uptime|tls, target, name?, threshold_days?}` (needs `edit`).
- `POST /api/site-manager/alerts/rules/<id>` — `{name?, enabled?, threshold_days?}` (needs `edit`).
- `DELETE /api/site-manager/alerts/rules/<id>` — (needs `edit`).
- `GET /api/site-manager/alerts` — rules plus alerts (needs `view`).
- `POST /api/site-manager/alerts/check` — runs enabled rules now (needs `view`).
- `POST /api/site-manager/alerts/<id>/ack|resolve|reopen` — (needs `edit`).
- CLI for always-on monitoring: `python run.py check-alerts` (run via cron/systemd; prints workspaces checked).

Page: `/site-manager/alerts` (in the sidebar with the open-alert count).

## Shareable reports

Monthly summaries with changes made, Search Console visits, inquiries received, issues resolved and requests completed, with the site/brand logo. Token links are public and printable to PDF.

- `GET /api/site-manager/reports` (`?period=YYYY-MM`) — current-period summary plus links (needs `view`).
- `GET /api/site-manager/reports/<id>` — summary for that link's month (needs `view`).
- `POST /api/site-manager/reports` — `{period, title?}` creates a link (needs `manage`; the URL is shown once).
- `DELETE /api/site-manager/reports/<id>` — revokes the link (needs `manage`).
- Public: `GET /reports/<token>` (no login, 404 once revoked; `?format=json` returns the summary as JSON).

Page: `/site-manager/reports` (in the sidebar).

## Notifications

Event-driven inbox so nobody has to poll each section: contact messages, client requests/comments/decisions and newly opened (or publish-failure) alerts notify the site owner plus every team member with `view` access. Authors don't get notified of their own comments; repeated alert checks don't re-notify until resolved.

- `GET /api/notifications` — latest 100 (unread first) plus `unread_count`.
- `POST /api/notifications/<id>/read` — marks one read (404 for other users' items).
- `POST /api/notifications/read-all` — marks everything read.

Page: `/notifications` (bell in the sidebar with the unread count).

## SEO, AI, images, social

- `POST /api/seo-suggestions/create` — `{title, keyword}` creates the page.
- `POST /api/ai/run` — `{task_type, prompt, provider?, model?, context?}` (`website_update`, `seo_brief`, `content_brief`, `social_post`, `assistant`).
- `GET /api/ai/runs` — AI run history.
- `POST /api/ai/images` — `{prompt, model?, output_format?}` generates an image.
- `GET /api/ai/images` — generated images.
- `GET /api/social/buffer/channels` — connected social channels (needs Buffer key in Settings).
- `GET /api/social/buffer/posts` — post history.
- `POST /api/social/generate` — `{prompt?, provider?, model?}` writes post text with AI (no publish). `prompt` is optional when a site is connected: without it, the post is written from the site's own content (`from_site: true`).
- `GET /api/social/suggestions` — rule-based post ideas derived from the connected site (brand, pages, upcoming events); needs no AI key.
- `POST /api/social/ideas` — `{hint?, provider?, model?}` AI-generated post ideas based on the site's content.
- `GET /api/site-manager/intelligence` — the combined site snapshot every AI feature shares: brand, pages with excerpts, open issues, upcoming events, recent updates.
- `POST /api/social/images/upload` — multipart `image` (png/jpg/gif/webp) from the user.
- `POST /api/social/images/edit` — `{image_url, instruction, model?}` edits the user's own generated/uploaded image with AI.
- `POST /api/social/buffer/posts` — `{channel_id | channel_ids[], text?, prompt?, image_url?, post_type?, draft?, publish_now?}` publishes now, queues, or drafts; `prompt` generates the text with AI; `image_url` must be a public http(s) address; `post_type` is `post` (default), `story`, or `reel` for Facebook/Instagram; multi-channel returns per-channel `results` with `published`/`failed` counts.

## Security scan & settings

- `GET /api/security-scan` / `POST /api/security-scan` (`{domain}`).
- `GET /api/settings` — account + configuration state.
- `POST /api/settings/account` — `{name?, email?, current_password?, new_password?, confirm_password?, company_*?, buffer_api_key?}` + optional multipart `avatar` / `company_logo`.
- `GET /api/ai/providers` / `GET /api/settings/ai` — providers and policy.
- `POST /api/settings/ai-credentials` — `{current_password, muse_api_key?, ...}`.
- `POST /api/settings/ai-policy` — default provider/model.
- `GET /api/settings/muse-models` / `POST /api/settings/muse-models/refresh`.
- `GET /api/settings/google/diagnostics` — asks Google whether each suggested OAuth redirect URI is registered (`google_accepts` + `reason`: `accepted`/`mismatch`/`invalid_client`/`network`/`missing_credentials`). Register mismatched URIs exactly in Google Cloud Console → Credentials → Authorized redirect URIs.

## Convention

Every new web feature must ship with its `/api/...` equivalent and a test, so the API never falls behind the UI.
