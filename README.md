<div align="center">

# ◎ OfferLoop

### A sales CRM for your job search

**Sales teams never forget to follow up. Now you won't either.**

Built end-to-end on Google Cloud for **Code Kitchen Season 01** · Track: *AI Job Application Tracker*

[![CI](https://github.com/shi1720/OfferLoop-Job-CRM/actions/workflows/ci.yml/badge.svg)](https://github.com/shi1720/OfferLoop-Job-CRM/actions/workflows/ci.yml)
[![Gemini](https://img.shields.io/badge/Gemini-3.7%20Flash%20%2B%203.1%20Pro-4285F4)](backend/app/services/llm.py)
[![Cloud Run](https://img.shields.io/badge/deploy-Cloud%20Run-blue)](infra/deploy.sh)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

### **[▶ Live demo — offerloop on Cloud Run](https://offerloop-g7qf54ykpa-uc.a.run.app)**

*Deployed on the Code Kitchen sandbox (us-central1). Sign in with Google, then **Import → Load
sample datasets → Run import** to fill your workspace through the evaluation pipeline.*

<img src="docs/screenshots/02-pipeline.png" alt="OfferLoop pipeline board" width="820" />

</div>

---

## The problem

Three out of four candidates report being ghosted after an interview ([Greenhouse candidate
experience survey](https://www.greenhouse.com/blog/candidate-experience-report)) — and that's the
applications that got a reply at all. Not because candidates aren't good, but because nobody
*works* their applications. They apply, they wait, they lose track in a spreadsheet.

Sales teams solved this exact problem decades ago: a pipeline with stages, automated cadences,
and follow-ups that go out on schedule, every time. **OfferLoop gives job seekers that same
engine.**

## What it does

| | |
|---|---|
| **Today view** | The landing page is a to-do list, not a dashboard: follow-ups due with drafts attached, interviews coming up with calendar links, applications going quiet, and a weekly goal you set. The daily ritual that keeps a search alive. |
| **Paste-a-link capture** | Paste any posting URL — or the whole job description — and Gemini extracts role, company, location and skills into a prefilled card you confirm. Seconds from "saw a job" to "in the pipeline". |
| **Pipeline board** | Drag applications through Applied → Interview → Offer / Reject. Every transition is recorded with a timestamped, annotated history. Delete is soft — an Undo toast restores everything, drafts included. |
| **AI outreach that sounds like you** | Four draft types — cover letters (Gemini **3.1 Pro**), follow-up emails, referral requests, and LinkedIn DMs (**3.7 Flash**) — grounded on the posting, your profile, *and your own past drafts*, retrieved by hybrid semantic + lexical search. Every draft shows its provenance and opens **prefilled in Gmail**, addressed to the recruiter contact on the card. |
| **Interview prep packs** | One click per application: likely questions for that exact posting with answer angles, STAR story outlines built strictly from your own proof points, and sharp questions to ask back. |
| **Scheduled nudges** | **Cloud Scheduler** scans every pipeline hourly. Quiet applications trigger a 3-touch follow-up cadence (5 → 7 → 10 days) with the follow-up email *already drafted and attached*. Interviews trigger thank-you nudges; offers and rejections get their own rules. Idempotent by construction — a rerun never double-nudges. |
| **Bulk CSV ingestion** | Drop postings (`id, from, to, type, description`) and drafts (`id, jobId, type, contents, status`). Gemini Flash structures free-text descriptions in batched calls, drafts link to postings by `jobId`, orphans are kept and flagged, bad rows are rejected individually with reasons, and re-imports update instead of duplicating. |
| **Funnel analytics** | Interview rate, offer rate, median days-to-interview, ghost rate, weekly momentum — your search measured like a sales funnel. |
| **Momentum + guided onboarding** | A seven-step spotlight tour on first sign-in, an activation checklist computed from real data, and server-side momentum points for real actions (log +10, send +15, first interview +30, first offer +100) with levels from Starter to Legend. Gamification that rewards *doing the work*, not opening the app. |
| **Web push nudges** | The hourly Cloud Scheduler scan can ping your browser via Firebase Cloud Messaging the moment follow-ups come due — the cadence works even when the tab is closed. |
| **Your data, no lock-in** | One-click CSV export of everything, delete-my-account that actually deletes, and one-upload migration from **Teal or Huntr** — their exports are detected by shape and mapped onto your pipeline, statuses included. |
| **Bring your own key** | Every user gets a free AI-draft allowance on the server key, then plugs in their own free Gemini key — validated live, stored Fernet-encrypted, only ever shown masked. Key errors come back as structured codes (`key_invalid`, `quota_exhausted`…) with plain-English fixes, so the product's AI bill scales with its users instead of its operator. |

<div align="center">
<img src="docs/screenshots/10-today.png" alt="Today view: due follow-ups, interviews, weekly goal" width="820" />
<img src="docs/screenshots/05-nudges.png" alt="Nudge inbox with auto-drafted follow-ups" width="820" />
</div>

Fully responsive — the board becomes swipeable stage columns on a phone, with the whole app behind
a slide-over menu.

## Architecture

One container. One Cloud Run service. Scales to zero when nobody is job hunting at 3 a.m. — and
wakes the moment Cloud Scheduler fires.

```mermaid
flowchart LR
    subgraph client [Browser]
        UI[React SPA<br/>Vite + Tailwind]
    end

    subgraph run [Cloud Run — one container]
        API[FastAPI<br/>REST + static serving]
        ING[CSV ingestion pipeline]
        NUD[Nudge cadence engine]
        GEN[Draft generator<br/>+ exemplar retrieval]
    end

    subgraph gcp [Google Cloud]
        AUTH[Firebase Auth<br/>Google sign-in]
        FS[(Firestore<br/>per-user namespaces)]
        GEM[Vertex AI<br/>Gemini 3.7 Flash · 3.1 Pro<br/>gemini-embedding-001]
        SCHED[Cloud Scheduler<br/>hourly, OIDC-signed]
    end

    UI -- "ID token" --> AUTH
    UI -- "Bearer token" --> API
    API -- verify --> AUTH
    API --> ING & NUD & GEN
    ING & NUD & GEN <--> FS
    ING & GEN --> GEM
    SCHED -- "POST /api/tasks/nudge-scan" --> NUD
```

**Design decisions that matter:**

- **Adapter seams everywhere.** Storage (`Firestore ⇄ in-memory`), intelligence
  (`Gemini ⇄ deterministic templates`), and auth (`Firebase ⇄ demo identity`) are swappable via
  one env var. That's why the entire product — including the evaluation pipeline — runs and is
  tested in CI with zero credentials, then switches to full GCP with `OFFERLOOP_APP_MODE=live`.
- **Model routing with a fallback chain.** High-volume structured work (posting extraction,
  follow-ups) goes to `gemini-3.7-flash`; the highest-stakes artifact — the cover letter — goes to
  `gemini-3.1-pro-preview`. Every call degrades along
  `3.1 Pro → 3.6 Flash → 3.5 Flash-Lite` instead of failing, and extraction falls back to regex so a
  model outage can never break an import.
- **Idempotency as structure, not discipline.** Nudges are keyed by deterministic dedupe keys and
  the store refuses duplicates; CSV rows carry their external id so re-imports update in place.
  Scheduler retries and judge re-runs are harmless by design.
- **The demo seed *is* the evaluation pipeline.** Demo mode boots by ingesting
  [`data/sample_postings.csv`](data/sample_postings.csv) and
  [`data/sample_drafts.csv`](data/sample_drafts.csv) through the exact same importer the
  evaluators will exercise. No hand-planted fixtures.
- **Unit economics are a design constraint.** The engine for any request is chosen per user —
  their own encrypted Gemini key, else the server key while a free allowance lasts, else a
  structured `402 key_required` that the UI turns into a one-minute "get a free key" flow.
  Generation blocks politely; extraction and retrieval degrade to regex/lexical and never do
  ([`app/services/engine.py`](backend/app/services/engine.py)).

## Try it in 60 seconds (no GCP account needed)

```bash
git clone https://github.com/shi1720/OfferLoop-Job-CRM.git && cd OfferLoop-Job-CRM
make install     # backend venv + frontend npm install
make build       # production frontend bundle
make api         # http://localhost:8000 — demo workspace, seeded via the CSV pipeline
```

Or with Docker — exactly what Cloud Run runs:

```bash
make docker && make docker-run    # http://localhost:8080
```

Click **Enter OfferLoop** and you're inside a seeded workspace: 12 imported postings, 16
historical drafts, and a live nudge inbox. Then go to **Import** and hit **Load sample datasets →
Run import** to watch the evaluation pipeline run end to end — and hit it again to see
idempotency in action.

> Demo mode keeps everything in memory (restart = fresh seed) and uses a deterministic writer,
> so it needs zero credentials. Live mode is the same code on Firestore + Gemini, flipped by
> one env var.

## Deploying to Google Cloud

```bash
PROJECT_ID=your-project ./infra/deploy.sh
```

The script enables APIs, creates Firestore, sets up least-privilege service accounts, deploys to
Cloud Run from source, and wires the hourly Cloud Scheduler job (OIDC-authenticated). Full
runbook with the Firebase Auth step: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md). Running it as a
public product — a clean `*.web.app` URL via Firebase Hosting, the bring-your-own-key cost model,
and the free-allowance knobs: [docs/PUBLIC_LAUNCH.md](docs/PUBLIC_LAUNCH.md).

## For evaluators

**[docs/EVALUATION.md](docs/EVALUATION.md)** maps every requirement in the problem statement to
the code, tests, and the exact `curl`/UI path to verify it — including how to run your own CSV
datasets through the pipeline.

## Testing

```bash
make test    # 140 backend tests (pytest) + 10 frontend tests (vitest)
make lint    # ruff + tsc --noEmit
make tour    # Playwright end-to-end tour of the full UI (needs `make api` running)
```

The importer is tested against the messy realities of the evaluation schema: unquoted commas
inside descriptions (as in the problem statement's own examples), `<id>`-style angle-bracket
headers, UTF-8 BOM, CRLF, multiline quoted contents, mixed date formats, messy type labels
(`follow-up`, `Thank You`, `fulltime`), duplicate ids within one file, per-row failures,
idempotent re-imports, and orphan adoption when a posting arrives after its drafts. The nudge
engine is tested for cadence backoff, dedupe idempotency, budget caps, and the staleness-clock
semantics. The BYOK layer is tested for encryption round-trips, secret rotation, engine-selection
order, allowance accounting (a failed generation never burns a credit), the Gemini error taxonomy's
HTTP mapping, and momentum award rules (first-time-only transitions can't be farmed). The
Playwright tour in [`e2e/`](e2e/) click-tests every page — onboarding tour included — against the
running stack and regenerates the screenshots above.

## Project structure

```
backend/
  app/
    main.py            FastAPI app factory + SPA serving
    config.py          every knob, env-driven
    auth.py            Firebase ID-token verify · demo identity · Scheduler OIDC gate
    models.py          domain models mirroring the evaluation schemas
    repos/             Repo protocol · MemoryRepo · FirestoreRepo (batched writes)
    services/
      llm.py           Gemini adapter (routing, fallbacks, batching) + template fallback
      engine.py        per-user engine selection · BYOK encryption · momentum
      ingest.py        the CSV pipeline
      nudges.py        the cadence engine
      retrieval.py     hybrid exemplar retrieval (embeddings + lexical)
      generation.py    grounded draft generation with provenance
      analytics.py     funnel math
    routers/           applications · drafts · imports · nudges · analytics · tasks
  tests/               140 tests
frontend/
  src/                 React 19 + TypeScript + Tailwind 4 (validated dataviz palette)
e2e/                   Playwright tour: click-tests every page, regenerates screenshots
data/                  sample datasets in the evaluation schema
infra/                 deploy.sh · Cloud Scheduler wiring · Firestore rules · env reference
docs/                  architecture · deployment · evaluation guide · screenshots
```

## Commercial viability

Job-search CRMs like Teal and Huntr already have paying users in the US; the "cadence" mechanic —
borrowed from sales tools like Outreach — is the wedge none of the spreadsheet-replacement tools
have. India makes the problem *worse* and the opportunity bigger: mass-apply culture on Naukri
and LinkedIn means more pipelines, more silence, more ghosting. The roadmap follows the market:
one-click import from Naukri/LinkedIn, nudges delivered on WhatsApp, a ₹99/month premium tier —
and, because Indian B2C rarely pays alone, **placement-cell and bootcamp licensing as the B2B2C
channel** (a college buys OfferLoop for 2,000 final-year students and gets the recruiter-facing
funnel analytics).

The infrastructure is the business model's friend: scale-to-zero Cloud Run + Firestore free tier
+ Flash-first model routing puts the marginal cost of a free user near zero.

## Credits

Built by **[Shivam Gupta](https://github.com/shi1720)** for Code Kitchen Season 01, with Claude
(Anthropic) as pair programmer. Product concept, architecture direction, testing and iteration:
Shivam.

## License

[MIT](LICENSE)
