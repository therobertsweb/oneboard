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

## Dashboard & Search Console

- `GET /api/dashboard` — stats, charts, opportunities.
- `GET /api/google-search-console/connect` — starts OAuth (returns auth URL).
- `GET /api/google-search-console/callback` — OAuth callback.
- `POST /api/google-search-console/site` — `{site_url}` selects property.
- `POST /api/google-search-console/disconnect` — unlinks the account.

## Site manager (file chatbot + workspace)

- `GET /api/site-manager` — full state: directory, projects, files, chat, updates, backups.
- `POST /api/site-manager/connect` — `{path}` connects a local directory (switches projects too; creates the folder if missing).
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

## SEO, AI, images, social

- `POST /api/seo-suggestions/create` — `{title, keyword}` creates the page.
- `POST /api/ai/run` — `{task_type, prompt, provider?, model?, context?}` (`website_update`, `seo_brief`, `content_brief`, `social_post`, `assistant`).
- `GET /api/ai/runs` — AI run history.
- `POST /api/ai/images` — `{prompt, model?, output_format?}` generates an image.
- `GET /api/ai/images` — generated images.
- `GET /api/social/buffer/channels` — connected social channels (needs Buffer key in Settings).
- `GET /api/social/buffer/posts` — post history.
- `POST /api/social/generate` — `{prompt, provider?, model?}` writes post text with AI (no publish).
- `POST /api/social/buffer/posts` — `{channel_id, text?, prompt?, image_url?, draft?}` publishes or drafts; `prompt` generates the text with AI; `image_url` must be a public http(s) address.

## Security scan & settings

- `GET /api/security-scan` / `POST /api/security-scan` (`{domain}`).
- `GET /api/settings` — account + configuration state.
- `POST /api/settings/account` — `{name?, email?, current_password?, new_password?, confirm_password?, company_*?, buffer_api_key?}` + optional multipart `avatar` / `company_logo`.
- `GET /api/ai/providers` / `GET /api/settings/ai` — providers and policy.
- `POST /api/settings/ai-credentials` — `{current_password, muse_api_key?, ...}`.
- `POST /api/settings/ai-policy` — default provider/model.
- `GET /api/settings/muse-models` / `POST /api/settings/muse-models/refresh`.

## Convention

Every new web feature must ship with its `/api/...` equivalent and a test, so the API never falls behind the UI.
