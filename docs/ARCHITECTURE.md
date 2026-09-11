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

- **CI needs no secrets.** All 72 backend tests exercise the real pipeline logic against the
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
