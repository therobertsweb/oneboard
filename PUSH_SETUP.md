# Push notifications setup (owner steps)

The app code is ready: the backend registers devices (`push_devices` table),
sends via FCM when a notification is created, and the Mac app registers its
token on login and opens the right section on tap. Real delivery needs three
things only the owner can provide.

## 1. APNs key in Firebase Console (requires Apple Developer, $99/year)

1. At [Apple Developer](https://developer.apple.com/account/resources/authkeys/list),
   create a **Key** with **Apple Push Notifications service (APNs)** enabled.
   Download the `.p8` file once, and note the **Key ID** and **Team ID**.
2. In [Firebase Console](https://console.firebase.google.com) → project
   `oneboard-27024` → **Project settings → Cloud Messaging** → **Apple app
   configuration** → upload the `.p8` with its Key ID and Team ID.

Without this, Firebase cannot reach any Apple device and tokens stay
unusable; the app reports "push is waiting for APNs".

## 2. Service account for the local backend (sending)

1. Firebase Console → **Project settings → Service accounts** →
   **Generate new private key** (JSON).
2. Save it OUTSIDE the repo, e.g. `~/.oneboard/firebase-service-account.json`.
3. Point the service at it before launch (local runs and the bundled app
   both read the environment / bundled `.env`):

```sh
export FIREBASE_PROJECT_ID=oneboard-27024
export FIREBASE_SERVICE_ACCOUNT=$HOME/.oneboard/firebase-service-account.json
```

The bundled `.env` already ships inside the app with mode 600; add the two
lines there for the packaged app. Sending is best-effort: without these
values the app works normally, it just never calls FCM.

## 3. Signed build with push entitlement

Ad-hoc signatures cannot carry `aps-environment`, so the default build has
no push. With a Developer identity:

```sh
export ONEBOARD_SIGN_IDENTITY="Apple Development: Your Name (TEAMID)"
bash oneboard_MacOS/scripts/build-flutter-macos.sh
```

The script signs the top-level bundle with
`macos/Runner/Release.push.entitlements`. For distribution also assign a
provisioning profile with the Push capability in Xcode (the workspace opens
after every build).

## 4. Console prerequisites (verify once)

- **Authentication → Sign-in method**: Email/Password **enabled**
  (the app signs into Firebase with the same credentials as local login).
- **Firestore**: database created; rules from `oneboard_MacOS/firestore.rules`
  deployed.
- **Storage is NOT needed**: social images are hosted on your own media
  server (see `MEDIA_SETUP.md`), so the Firebase Storage paywall does not
  apply.

## 5. Verify end to end

1. Sign in on the Mac, accept the notification permission prompt.
2. Trigger an event (e.g. a new contact message on the connected site).
3. A macOS notification arrives; clicking it opens the matching section.
