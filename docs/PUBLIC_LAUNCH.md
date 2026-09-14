# Public launch runbook

How to run OfferLoop as a real public product — a clean `*.web.app` URL,
sustainable AI costs (bring-your-own-key), and the knobs that control the
free allowance. This builds on the base deployment in
[DEPLOYMENT.md](DEPLOYMENT.md); do that first.

## The cost model (why BYOK)

A public AI product dies on someone else's API bill. OfferLoop's engine
selection makes the economics work per user:

1. **Their own Gemini key** — stored encrypted (Fernet, keyed by
   `OFFERLOOP_KEY_SECRET`), validated live against the Gemini API before
   it's accepted, only ever displayed masked. Unlimited drafts on their
   own free quota.
2. **The operator's key, while the free allowance lasts** —
   `OFFERLOOP_FREE_GENERATIONS` drafts per user (default 30, roughly the
   "first taste"). Auto-drafted nudge follow-ups count against it too.
3. **After that** — generation returns a structured `402 key_required`
   the UI turns into an "add your free key" prompt with a link to
   [Google AI Studio](https://aistudio.google.com/apikey). Import
   extraction and retrieval degrade to regex/lexical instead of blocking.

Every Gemini failure is classified (`key_invalid`, `quota_exhausted`,
`timeout`, `unavailable`) and mapped to an HTTP status and a plain-English
message, so "my key stopped working" and "my quota ran out" are never the
same mystery error.

## 1. Deploy (or redeploy) the service

From the repo root, on the production project:

```bash
PROJECT_ID=<your-project> REGION=asia-south1 \
  GEMINI_API_KEY=<server key from AI Studio> \
  FIREBASE_WEB_CONFIG='<one-line JSON from the Firebase console>' \
  ./infra/deploy.sh
```

Notes:

- `GEMINI_API_KEY` set → the service uses the AI Studio API (no Vertex
  billing needed) and pins flash models that free-tier keys can actually
  serve. Omit it on a billing-enabled project to use Vertex AI with the
  service account instead.
- `OFFERLOOP_KEY_SECRET` is generated on first deploy and **reused on
  every redeploy** (the script reads it back from the running service).
  Rotating it invalidates every stored user key, so don't.
- `FREE_GENERATIONS=<n>` tunes the allowance.

## 2. A clean URL with Firebase Hosting

Cloud Run URLs (`offerloop-…-uc.a.run.app`) are ugly and unmemorable.
Firebase Hosting sits in front of Cloud Run for free and gives you
`<site>.web.app`, plus first-class serving of the `/__/auth` helpers.

```bash
npm install -g firebase-tools
firebase login
firebase hosting:sites:create offerloop --project <your-project>   # or offerloop-app, getofferloop…
firebase target:apply hosting offerloop offerloop --project <your-project>
firebase deploy --only hosting --project <your-project>
```

`firebase.json` (repo root) already rewrites `**` to the `offerloop`
Cloud Run service — edit its `region` if you deployed elsewhere. Site
names are global, so if `offerloop` is taken pick a variant; the URL
becomes `https://<site>.web.app`.

Then point auth at the new domain:

1. Firebase console → Authentication → Settings → **Authorized domains** →
   add `<site>.web.app`. (Only the project's *default* domains are
   pre-authorized; an additional Hosting site's domain must be added, or
   sign-in fails with `auth/unauthorized-domain`.)
2. Update the served web config so the login popup uses the new host:

   ```bash
   gcloud run services update offerloop --region asia-south1 \
     --update-env-vars 'OFFERLOOP_FIREBASE_WEB_CONFIG={"apiKey":"…","authDomain":"<site>.web.app",…}'
   ```

   With `authDomain` on the Hosting domain, the `/__/auth/*` helpers are
   served natively by Hosting — same-origin, no popup warnings, and the
   backend's auth proxy simply never gets hit.

3. (Optional) A fully custom domain: Hosting → **Add custom domain**,
   follow the DNS instructions, then repeat step 2 with that domain.

## 3. Web push notifications (optional, free)

The hourly nudge scan can ping users' browsers the moment follow-ups come
due — the product keeping its promise *outside* the tab.

1. Firebase console → Project settings → **Cloud Messaging** → Web push
   certificates → **Generate key pair**. Copy the public key.
2. Redeploy with it (or `gcloud run services update offerloop
   --update-env-vars OFFERLOOP_FCM_VAPID_KEY=<key>`):

   ```bash
   FCM_VAPID_KEY=<public key> PROJECT_ID=<your-project> ./infra/deploy.sh …
   ```

3. Users flip it on under Profile → Notifications (or the Today page).
   Tokens are stored per profile (max 5 devices), pruned automatically when
   a device unregisters, and only the *scheduled* scan notifies — a user
   clicking "scan" is already looking at the result.

## 4. Verify

```bash
BASE=https://<site>.web.app
curl -s $BASE/api/health          # {"status":"ok","mode":"live"}
curl -s -o /dev/null -w '%{http_code}\n' $BASE/api/applications   # 401 (auth gate)
curl -s $BASE/__/auth/handler -o /dev/null -w '%{http_code}\n'    # 200 (Hosting-served)
```

Then in a browser: sign in, run the onboarding tour, add a key on the
Profile page (watch it validate live), generate a draft, check the
momentum chip ticks up.

## 5. Operating notes

- **Scale-to-zero**: min-instances is 0; a quiet app costs ~nothing.
  The hourly Cloud Scheduler scan is the only guaranteed wake-up.
- **Abuse control**: the free allowance is per Firebase-authenticated
  user, counted server-side (`free_used` on the profile) — a fresh
  incognito window doesn't reset it.
- **Support playbook**: "key not working" → the Profile page re-validates
  on save and shows the Gemini API's reason; "AI exhausted" → 429 with
  the daily-reset explanation; both are structured codes in the logs.
- **Momentum/gamification**: points are awarded server-side only
  (`app/services/engine.py::POINTS`) — the client can't mint them.
