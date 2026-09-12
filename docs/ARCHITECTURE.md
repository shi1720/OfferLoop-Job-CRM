# Architecture

OfferLoop is deliberately a **modular monolith in one container**: a FastAPI service that serves
its own React frontend, deployed as a single Cloud Run service that scales to zero. For an MVP
whose traffic is bursty (a scheduler tick, a user session), this beats a microservice split on
cost, latency, and operational surface — while the internal seams keep every future split cheap.

## The three seams

```
routers ──► services ──► adapters
                          ├── Repo:         MemoryRepo | FirestoreRepo
                          ├── Intelligence: TemplateIntelligence | GeminiIntelligence
                          └── Auth:         demo identity | Firebase ID tokens | Scheduler OIDC
```

Selected by `OFFERLOOP_APP_MODE`. Consequences:

- **CI needs no secrets.** All 139 backend tests exercise the real pipeline logic against the
  memory adapter and the deterministic writer.
- **Judges can run the product in one command** with no GCP project.
- **The demo is honest.** Demo mode boots by pushing `data/sample_*.csv` through the same
  ingestion pipeline used in production, then running a real nudge scan.

## Request flow (live mode)

1. React SPA signs in with Firebase Auth (Google); every API call carries the ID token.
2. FastAPI verifies the token with `firebase-admin` and resolves a `uid`.
3. Repositories namespace every read/write under `users/{uid}/…` in Firestore. Isolation is a
   storage-layer property, not a router convention. Client-side Firestore rules are deny-all.

## The nudge engine (the hard requirement done properly)

- **Trigger**: Cloud Scheduler → `POST /api/tasks/nudge-scan`, hourly, with an OIDC token
  (audience = service URL). The endpoint verifies signature *and* caller service account.
- **Rules** (deterministic, user-visible, env-tunable): a 3-touch follow-up cadence with backoff
  (5/7/10 quiet days) for Applied; thank-you after moving to Interview; offer-response after 3
  days; feedback-request after a rejection.
- **Idempotency**: every nudge has a deterministic `dedupe_key`
  (`{app_id}:{rule}:{touch|date}`); `create_nudge_if_absent` is the only write path. In
  Firestore this is a `create()` on a doc whose **id is the dedupe key** — a race between two
  scans resolves at the database, not in application logic.
- **Attached drafts**: a follow-up nudge auto-generates the email (Flash), bounded by
  `max_generated_per_scan` so a scheduled run has a hard spend cap.
- **Clock semantics**: user actions (generating, editing, marking sent) reset an application's
  staleness clock; scheduled auto-drafts and historical imports do not. Getting this wrong makes
  the cadence either spammy or silent — it's tested both ways.

## The ingestion pipeline

`_read_rows` → validate/normalize per row → batched Gemini extraction (regex fallback) →
upsert by `external_id` → link drafts by `jobId` → batch-embed → batched Firestore writes →
auditable `ImportReport` (accepted/updated/rejected-with-reasons/linked/orphaned/embedded/ms).

Two details worth calling out:

- **Spill-column recovery.** The evaluation examples contain unquoted commas inside free-text
  columns. When a row has more fields than the header, the surplus is folded back into the
  designated free-text column (`description`/`contents`) and trailing columns realign.
- **Imported drafts are dated near their application** (the schema has no dates) and never touch
  the staleness clock — so analytics stay honest and the cadence still fires after an import.

## Generation & retrieval (historical learning)

New drafts are grounded three ways: the posting (role, skills, raw description), the user's
profile (facts only — the prompt forbids invented achievements), and **voice exemplars**: the
user's top-3 past drafts of the same type, ranked by
`0.65 · cosine(gemini-embedding-001) + 0.35 · lexical overlap`, with sent drafts boosted (they
represent the user's real voice) and embeddings computed at import time in batches. The response
carries `grounded_on` ids — provenance the UI surfaces as chips.

Model routing: `gemini-3.7-flash` for extraction/follow-ups (volume, latency, cost),
`gemini-3.1-pro-preview` for cover letters (quality), falling back
`3.1 Pro → 3.6 Flash → 3.5 Flash-Lite`; extraction ultimately falls back to regex. An LLM outage
degrades quality, never availability.

## Engine selection & unit economics (BYOK)

`services/engine.py` picks the intelligence for every request, per user, in strict order:
the user's own Gemini key (Fernet-encrypted at rest with `OFFERLOOP_KEY_SECRET`, validated
live against the Gemini API before acceptance, returned only masked) → the server key while
the user's free allowance lasts (`free_used` is counted server-side on the profile, and only
on *success* — a failed generation never burns a credit) → a structured `402 key_required`.
Callers that can degrade (extraction, embeddings) get the template/lexical engine instead of
an error, so imports never block. Gemini failures are classified into a four-code taxonomy
(`key_invalid | quota_exhausted | timeout | unavailable`) mapped to `400/429/504/502` with
human-readable fixes.

The same module owns **momentum**: points are awarded exclusively server-side for real actions
(log 10, send 15, nudge done 20, import 25, first interview 30, first offer 100), with
transition awards keyed to first-time status changes so bouncing a card back and forth can't
farm points.

## The launch feature set

- **Paste-a-link capture** (`services/capture.py`): a server-side fetch of a user-supplied URL
  is an SSRF invitation, so scheme/host/resolved-IPs are validated before the request *and*
  after redirects (metadata service and private ranges refused), responses are size-capped and
  content-type checked, and login-walled boards degrade to a "paste the JD text" hint. The
  extraction itself reuses the import pipeline's engine, so it works keyless via regex.
- **Interview prep packs**: one structured-JSON Gemini call per application (template fallback in
  demo), stored on the application, regenerated on demand, and gated by the same BYOK allowance
  as drafts. Prompts forbid inventing experience — thin proof points get coaching, not fiction.
- **Soft delete + undo**: `delete` stamps `deleted_at`; every listing filters it, scans skip it,
  analytics exclude it, and `restore` brings the application back with drafts and nudges intact.
- **Tracker migration**: Teal/Huntr exports are *application* lists, not postings — detected by
  header shape, stage vocabularies mapped onto the four phases, idempotent by posting URL.
- **Web push** (`services/push.py`): FCM tokens live on the profile (≤5 devices), only the
  *scheduled* scan notifies, dead tokens are pruned on send, and a notification failure can
  never fail a scan.
- **Zero-OAuth integrations**: Gmail compose and Google Calendar template links are pure URL
  builders (`frontend/src/lib/links.ts`) — tested functions, no scopes to review, work on phones.

## Frontend

React 19 + TypeScript + Tailwind 4, single committed dark theme. Kanban via dnd-kit with
optimistic updates (TanStack Query). Charts are hand-rolled to a validated palette: the
categorical trio and the funnel's ordinal ramp both pass the full colorblind-safety/contrast
gate against the app's actual surface (`#151a25`).

## Scale path (what changes at 10× and 100×)

- **10×**: fan the scan out — the scheduler endpoint enqueues one Cloud Task per user
  (`infra` already reserves the queue vars); Cloud Run concurrency absorbs the workers.
- **100×**: move embeddings to Vertex AI Vector Search; split the nudge worker into its own Cloud
  Run service (the `services/` seam is the cut line); BigQuery export for cohort analytics.
- The Repo protocol is the only thing Firestore-shaped; nothing else knows the database exists.
