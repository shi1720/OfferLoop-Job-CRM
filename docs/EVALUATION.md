# Evaluator's guide

This maps every requirement in the **AI Job Application Tracker** problem statement to where it
lives in the code, how it's tested, and the fastest way to verify it yourself.

The whole product runs credential-free in demo mode (`make api` or `make docker-run`), so every
check below works on your machine in minutes. In live mode the same code paths run on Firestore,
Firebase Auth, Vertex AI Gemini, and Cloud Scheduler.

All `curl` examples assume demo mode on `http://localhost:8000` with the demo bearer token.
Demo mode still authenticates — a missing or wrong token is a 401, exercising the same rejection
path a bad Firebase token takes in live mode:

```bash
AUTH='Authorization: Bearer demo'
curl -s localhost:8000/api/applications                 # → 401
curl -s -H "$AUTH" localhost:8000/api/applications      # → 200
ol() { curl -s -H "$AUTH" "$@"; }                       # helper used below
```

---

## 1. "Authenticated users log applications: company, role, date, status"

| | |
|---|---|
| Code | [`routers/applications.py`](../backend/app/routers/applications.py), [`auth.py`](../backend/app/auth.py) |
| Tests | `tests/test_applications.py` |

```bash
ol -X POST localhost:8000/api/applications \
   -H 'Content-Type: application/json' \
   -d '{"role":"Senior Backend Engineer","company":"Finlo","location":"Bengaluru"}'
```

Auth: in live mode every request carries a Firebase ID token verified server-side
(`firebase_admin.auth.verify_id_token`); all storage is namespaced by the verified `uid` at the
repository layer, so cross-tenant access is structurally impossible. Firestore client rules are
deny-all ([`infra/firestore.rules`](../infra/firestore.rules)) — the API is the only door.

## 2. "Contextual, tailored cover letters and follow-up email drafts"

| | |
|---|---|
| Code | [`services/generation.py`](../backend/app/services/generation.py), [`services/llm.py`](../backend/app/services/llm.py), [`services/retrieval.py`](../backend/app/services/retrieval.py) |
| Tests | `tests/test_generation.py`, `tests/test_retrieval.py` |

```bash
APP_ID=$(ol localhost:8000/api/applications | python3 -c "import json,sys;print(json.load(sys.stdin)[0]['id'])")
ol -X POST localhost:8000/api/applications/$APP_ID/drafts \
   -H 'Content-Type: application/json' -d '{"type":"cover_letter"}'
```

Note the `grounded_on` field in the response: the ids of the user's own past drafts that were
retrieved (hybrid `gemini-embedding-001` cosine + lexical scoring, sent-drafts boosted) and handed
to Gemini as voice exemplars. Model routing: cover letters → `gemini-3.1-pro-preview`, follow-ups
and extraction → `gemini-3.7-flash`, with a `3.1 Pro → 3.6 Flash → 3.5 Flash-Lite` fallback chain.

## 3. "Persistent state transitions across Applied, Interview, Offer, Reject"

| | |
|---|---|
| Code | `Status` enum + `status_history` in [`models.py`](../backend/app/models.py), transition recording in [`routers/applications.py`](../backend/app/routers/applications.py) |
| Tests | `TestTransitions` in `tests/test_applications.py` |

Every transition appends `{from_status, to_status, at, note}`. The UI renders it as the "Journey"
timeline; analytics computes funnel conversion and time-in-stage from it.

```bash
ol -X PATCH localhost:8000/api/applications/$APP_ID \
   -H 'Content-Type: application/json' \
   -d '{"status":"interview","status_note":"Recruiter call went well"}'
```

## 4. "Automated, scheduled nudges to keep candidates proactive"

| | |
|---|---|
| Code | [`services/nudges.py`](../backend/app/services/nudges.py), Scheduler endpoint in [`routers/tasks.py`](../backend/app/routers/tasks.py), OIDC gate in [`auth.py`](../backend/app/auth.py), job wiring in [`infra/deploy.sh`](../infra/deploy.sh) |
| Tests | `tests/test_nudges.py` (cadence backoff, idempotency, budget caps, staleness semantics) |

Cloud Scheduler POSTs `/api/tasks/nudge-scan` hourly with an OIDC token minted for a dedicated
service account; the API verifies the token and caller. Four deterministic rules:

- **follow_up** — Applied + quiet past the cadence (5 → 7 → 10 days, 3 touches max), with the
  follow-up email **auto-drafted and attached** to the nudge (capped per scan to bound spend)
- **interview_thank_you** — 1 day after moving to Interview
- **offer_response** — 3 days sitting on an Offer
- **reject_feedback** — 2 days after a rejection

Idempotency is structural: deterministic dedupe keys + create-if-absent. Run this twice and watch
the second scan create nothing:

```bash
curl -s -X POST localhost:8000/api/tasks/nudge-scan   # simulates Cloud Scheduler in demo mode
curl -s -X POST localhost:8000/api/tasks/nudge-scan   # → "nudges_created": 0
```

## 5. "Ingest 10+ postings and drafts in the given schemas, efficiently"

| | |
|---|---|
| Code | [`services/ingest.py`](../backend/app/services/ingest.py), endpoint in [`routers/imports.py`](../backend/app/routers/imports.py) |
| Tests | `tests/test_ingest.py` — the largest suite in the repo |

```bash
ol -X POST localhost:8000/api/import \
   -F postings=@data/sample_postings.csv \
   -F drafts=@data/sample_drafts.csv
```

Or in the UI: **Import → Load sample datasets → Run import.** Bring your own files in the same
schemas — the sample CSVs are the schema documentation.

> The demo seed already occupies posting ids 1–12 and draft ids 1–16. Importing your own file
> that reuses those ids will *update* the seeded rows — that's the idempotent upsert-by-id
> semantics working as designed. Use fresh ids to see clean creates.

What the pipeline handles (each item has a dedicated test):

- The problem statement's own example rows, **including the unquoted comma** in
  `Senior Backend Engineer - Python, Bengaluru` — surplus columns are folded back into the
  free-text field
- `<id>`-style angle-bracket headers, header case/spacing variants, UTF-8 BOM, CRLF, `;`/tab
  delimiters, quoted multiline `contents` with escaped quotes
- Multiple date formats; per-row rejection with row numbers and reasons — one bad row never
  fails a file
- **Linking**: drafts attach to postings by `jobId`; orphans are kept *with their jobId
  preserved* and are adopted automatically when the missing posting arrives in a later import
- **Idempotency**: rows carry their CSV id as `external_id`; re-importing — or a duplicated id
  within one file — updates in place, never duplicates
- **Efficiency**: existing rows are indexed once per run (one read, O(1) lookups per row — no
  per-row queries); Gemini Flash structures descriptions in batched calls (~40 rows/call) with a
  regex fallback; embeddings are batched; Firestore writes are batched (450/commit). The report
  returns `duration_ms` measured end to end.
- **Historical learning**: imported drafts become retrieval exemplars, so newly generated letters
  match the user's demonstrated voice (§2). Re-imported drafts whose text changed drop their
  stale embedding for recomputation. Imported history never resets the staleness clock that
  drives nudges — history is history.
- **Date semantics**: an imported posting is treated as an application submitted on its `from`
  date — that date anchors both the follow-up cadence and any "applied N days ago" phrasing in
  generated drafts.

## 6. "Track development over time"

[`services/analytics.py`](../backend/app/services/analytics.py) + the Analytics page: interview
rate, offer rate, median days-to-interview, ghost rate (quiet 21+ days), drafts sent, nudge
action rate, and 8 weeks of momentum. Tests: `tests/test_analytics.py`.

## 7. Robustness & scale posture

- Upload caps (5 MB, 5,000 rows), per-scan generation budget, request-scoped auth
- Naive datetimes in payloads coerced to UTC at the model boundary (can never 500 a request)
- The scheduler endpoint fails **closed** in live mode: OIDC signature, audience (= service
  URL), verified email, and expected service account are all enforced
- Firestore batched writes; per-user namespacing keyed by verified uid
- Model fallback chain + regex extraction fallback: no single Gemini failure breaks a flow
- 105 backend tests + 5 frontend tests run credential-free in CI; the Playwright tour in
  [`e2e/`](../e2e/) click-tests the full UI locally (`make tour`)
