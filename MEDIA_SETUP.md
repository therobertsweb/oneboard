# Media server setup (Buffer images without Firebase Storage)

Social images are hosted on your own server instead of Firebase Storage,
so there is no Storage paywall and no per-file cost. Firebase stays only
for the free parts: sign-in, push notifications, and cached data.

How it works:

1. The Mac app keeps a private copy of every social image in its local
   library (`/uploads/social-images/`, `/uploads/generated-images/`).
2. Before publishing, the local backend forwards the bytes to your server
   (`POST /api/public-media`, guarded by a shared token).
3. Your server stores them under `public-media/` and serves them publicly
   at signed, unguessable URLs (`/media/<file>/<signature>`).
4. Buffer downloads the public copy. The token never leaves your machines.

## 1. Server: deploy this code and set the token

On `museboard.theroberts.io`, update to this version of `app.py` (it contains
`/api/public-media` and `/media/...`), then set one secret and restart:

```sh
export ONEBOARD_MEDIA_TOKEN=$(python3 -c 'import secrets; print(secrets.token_hex(24))')
# persist it in the server's own .env / service environment, then restart
```

Without `ONEBOARD_MEDIA_TOKEN` the upload endpoint answers 404 as if it did
not exist. Uploads are validated (png/jpg/gif/webp, magic bytes, ≤ 20 MB).

Storage used: `UPLOAD_DIR/public-media/` next to the other uploads. There is
no quota in the app; your disk is the limit. Delete old files directly when
you no longer need them (Buffer keeps its own copy after fetching).

## 2. Mac app: nothing to enter (implicit)

The URL and token travel inside the app's own bundled `.env` (mode 600,
never committed to git), so the user never sees or types them. Per-user
values in Settings remain supported as an override, but there is no
visible field for them.

## 3. Verify

1. In Social, attach or generate any image: the composer must show
   "Buffer downloads the public copy from your media server."
2. Save a Buffer **draft** and check the draft carries the image.
3. If it fails, the error tells you which side is wrong:
   - "Set your media server URL and token" → step 2 missing.
   - "rejected the image" → wrong token, or server not updated/restarted.
   - "could not be reached" → wrong URL, or server down.

Note: uploads identify as `ONEBoard/1.0` so Cloudflare bot checks pass.
If your Cloudflare dashboard shows 1010/403 blocks on `/api/public-media`,
add a firewall exception for that path (it is already token-guarded).
