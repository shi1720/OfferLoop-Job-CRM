"""OfferLoop API — application entry point.

One container serves everything: the JSON API under ``/api/*`` and the
built React frontend for every other route (SPA fallback). That single
image is what Cloud Run runs, scaled to zero when nobody is job hunting
at 3 a.m. — and back up the moment Cloud Scheduler fires the nudge scan.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, get_settings
from .routers import analytics, applications, drafts, imports, nudges, tasks

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("offerloop")


def _build_repo(settings: Settings):
    if settings.app_mode == "live":
        from .repos.firestore import FirestoreRepo

        log.info("storage: Firestore (project=%s)", settings.gcp_project or "ADC default")
        return FirestoreRepo(settings.gcp_project, settings.firestore_database)
    from .repos.memory import MemoryRepo

    log.info("storage: in-memory (demo mode)")
    return MemoryRepo()


def _static_dir(settings: Settings) -> Path | None:
    candidates = [Path(settings.static_dir)] if settings.static_dir else []
    candidates += [
        Path(__file__).resolve().parents[2] / "frontend" / "dist",  # repo layout
        Path("/app/static"),  # container layout
    ]
    return next((c for c in candidates if (c / "index.html").is_file()), None)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    if settings.app_mode == "demo" and os.environ.get("K_SERVICE"):
        # Running on Cloud Run but not in live mode — almost certainly a
        # deployment configuration mistake. Shout about it.
        log.error(
            "DEMO MODE ON CLOUD RUN: storage is in-memory and auth is the shared demo "
            "identity. Set OFFERLOOP_APP_MODE=live (see infra/deploy.sh)."
        )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.app_mode == "demo" and settings.demo_seed:
            from .seed import seed_demo

            seed_demo(app.state.repo, app.state.intelligence, settings)
        yield

    app = FastAPI(
        title="OfferLoop",
        description="A sales CRM for your job search — track, draft, follow up, land the offer.",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.state.settings = settings
    # Ensure every Depends(get_settings) sees THIS instance (tests pass their own).
    app.dependency_overrides[get_settings] = lambda: settings
    app.state.repo = _build_repo(settings)

    from .services.llm import build_intelligence

    app.state.intelligence = build_intelligence(settings)
    log.info("intelligence: %s", app.state.intelligence.name)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for router in (applications, drafts, imports, nudges, analytics, tasks):
        app.include_router(router.router)

    if settings.gcp_project:
        # Same-origin proxy for Firebase's hosted auth helper. When the web
        # config's authDomain is set to THIS host, the entire Google sign-in
        # handshake becomes first-party — immune to browsers that block
        # third-party storage (the classic silent-popup-failure). The
        # OAuth client must list https://<this-host>/__/auth/handler as an
        # authorized redirect URI; see docs/DEPLOYMENT.md § Troubleshooting.
        _PROXY_REQUEST_HEADERS = {"accept", "accept-language", "content-type", "user-agent"}
        _PROXY_RESPONSE_HEADERS = {"content-type", "cache-control", "expires", "pragma", "location"}

        @app.api_route("/__/{path:path}", methods=["GET", "POST"], include_in_schema=False)
        async def firebase_auth_proxy(path: str, request: Request):
            upstream = f"https://{settings.gcp_project}.firebaseapp.com/__/{path}"
            if request.url.query:
                upstream += f"?{request.url.query}"
            headers = {
                k: v for k, v in request.headers.items() if k.lower() in _PROXY_REQUEST_HEADERS
            }
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    proxied = await client.request(
                        request.method, upstream, content=await request.body(), headers=headers
                    )
            except httpx.HTTPError as exc:
                log.warning("firebase auth proxy upstream error: %s", exc)
                return Response("Auth helper unavailable", status_code=502)
            return Response(
                proxied.content,
                status_code=proxied.status_code,
                headers={
                    k: v for k, v in proxied.headers.items() if k.lower() in _PROXY_RESPONSE_HEADERS
                },
            )

    static = _static_dir(settings)
    if static:
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/{path:path}", include_in_schema=False)
        def spa(path: str):
            candidate = (static / path).resolve()
            if path and candidate.is_file() and candidate.is_relative_to(static):
                return FileResponse(candidate)
            return FileResponse(static / "index.html")

        log.info("serving frontend from %s", static)
    else:
        log.info("no frontend build found — API-only mode (run `npm run dev` for the UI)")

    return app


app = create_app()
