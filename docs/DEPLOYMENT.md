# Deploying OfferLoop to Google Cloud

Everything below is scripted in [`infra/deploy.sh`](../infra/deploy.sh); this page explains the
steps so nothing is a black box, plus the one console-side step (Firebase Auth) that can't be
scripted from gcloud.

## What you end up with

| Piece | Service | Cost posture |
|---|---|---|
| App (API + UI) | Cloud Run, 1 container, scale-to-zero, max 3 instances | Free tier covers an MVP |
| Data | Firestore (native mode), per-user namespaces | Free tier: 1 GiB, 50K reads/day |
| Auth | Firebase Authentication, Google sign-in | Free |
| AI | Gemini via Vertex AI (`gemini-3.7-flash`, `gemini-3.1-pro-preview`, `gemini-embedding-001`) | Flash-first routing keeps cost/user in paise |
| Nudges | Cloud Scheduler → OIDC-authenticated POST, hourly | Free tier: 3 jobs |

## Step 1 — Deploy

```bash
gcloud auth login
PROJECT_ID=your-project ./infra/deploy.sh
```

The script is idempotent — safe to rerun. It enables APIs, creates the Firestore database and two
least-privilege service accounts (`offerloop-run` with `datastore.user` + `aiplatform.user`;
`offerloop-scheduler` with nothing but `run.invoker` on the service), builds the container from
source with Cloud Build, deploys, and creates the hourly scheduler job whose OIDC token the API
verifies (audience = service URL, caller = the scheduler SA).

## Step 2 — Firebase Authentication (console, ~2 minutes)

1. [console.firebase.google.com](https://console.firebase.google.com) → **Add project** → select
   the same GCP project.
2. **Build → Authentication → Get started → Sign-in method → Google → Enable.**
3. **Authentication → Settings → Authorized domains** → add your Cloud Run domain
   (e.g. `offerloop-xxxx.a.run.app`).
4. **Project settings → Your apps → Web app** → register, copy the config object.

## Step 3 — Hand the web config to the app

```bash
FIREBASE_WEB_CONFIG='{"apiKey":"...","authDomain":"...","projectId":"..."}' \
PROJECT_ID=your-project ./infra/deploy.sh
```

(Or set `OFFERLOOP_FIREBASE_WEB_CONFIG` on the service in the console.) The backend serves it at
`/api/config`; the frontend initializes Firebase from there — no rebuild needed.

## Step 4 — Verify

```bash
URL=$(gcloud run services describe offerloop --region asia-south1 --format='value(status.url)')
curl $URL/api/health
# {"status":"ok","mode":"live","intelligence":"gemini",...}

gcloud scheduler jobs run offerloop-nudge-scan --location asia-south1   # force a scan
gcloud logging read 'resource.labels.service_name="offerloop"' --limit 20
```

Sign in with Google, log an application, import the sample CSVs, and generate a cover letter —
the response's `model` field tells you which model served it (`gemini-3.1-pro-preview`, or a
fallback from the chain if preview access is limited on your project).

## Alternative: Gemini API key instead of Vertex

For a hackathon sandbox without Vertex access, a [Google AI Studio](https://aistudio.google.com)
key works with zero code changes:

```bash
gcloud run services update offerloop --region asia-south1 \
  --set-env-vars OFFERLOOP_USE_VERTEX=false \
  --set-env-vars OFFERLOOP_GEMINI_API_KEY=YOUR_KEY
```

## Firestore security rules

Clients never talk to Firestore directly, so rules are deny-all
([`infra/firestore.rules`](../infra/firestore.rules)). Deploy them if you ever add the Firebase
JS SDK's Firestore client:

```bash
firebase deploy --only firestore:rules
```

## Troubleshooting: "Sign in with Google bounces back without logging in"

Two causes cover nearly every case. The login page surfaces the exact Firebase error under the
button, so start there.

**1. `auth/unauthorized-domain`** — the Cloud Run host isn't on Firebase's authorized list, or
was typed with a scheme/typo. Firebase console → Authentication → Settings → Authorized
domains → the entry must be the exact bare host, e.g.
`offerloop-359201230061.asia-south1.run.app` (no `https://`, no trailing slash).

**2. No visible error; the popup completes and you land back signed out.** The browser is
blocking third-party storage (Chrome's third-party-cookie phase-out, Safari/Brave shields), which
breaks Firebase's cross-origin popup handshake against `<project>.firebaseapp.com`. The fix is to
make the handshake **first-party**: this service already proxies Firebase's auth helper at
`/__/*`, so switch `authDomain` to the app's own host:

1. GCP console → **APIs & Services → Credentials** → under *OAuth 2.0 Client IDs* open the web
   client auto-created by Firebase → add
   - Authorized JavaScript origin: `https://<your-run-host>`
   - Authorized redirect URI: `https://<your-run-host>/__/auth/handler`
   → Save (takes effect within a few minutes).
2. Point the web config's `authDomain` at your own host:

```bash
gcloud run services update offerloop --region asia-south1 \
  --update-env-vars '^##^OFFERLOOP_FIREBASE_WEB_CONFIG={"apiKey":"YOUR_KEY","authDomain":"<your-run-host>","projectId":"YOUR_PROJECT"}'
```

Hard-refresh the app (Ctrl+Shift+R) and sign in again — the whole flow now stays on one origin.

## Rollback / teardown

```bash
gcloud run services delete offerloop --region asia-south1
gcloud scheduler jobs delete offerloop-nudge-scan --location asia-south1
```
