from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.models import Application, Status, StatusChange
from app.repos.memory import MemoryRepo
from app.services.llm import TemplateIntelligence


@pytest.fixture
def settings() -> Settings:
    # _env_file=None keeps tests hermetic: a developer's backend/.env (e.g.
    # a real Gemini key) must never turn the suite into live API calls.
    return Settings(app_mode="demo", demo_seed=False, _env_file=None)


@pytest.fixture
def client(settings) -> TestClient:
    app = create_app(settings)
    with TestClient(app) as test_client:
        test_client.headers["Authorization"] = "Bearer demo"
        test_client.app_state = app.state  # convenient repo access in tests
        yield test_client


@pytest.fixture
def repo() -> MemoryRepo:
    return MemoryRepo()


@pytest.fixture
def intelligence() -> TemplateIntelligence:
    return TemplateIntelligence()


def make_application(uid: str = "u1", **overrides) -> Application:
    defaults = dict(
        uid=uid,
        company="Finlo",
        role="Senior Backend Engineer",
        location="Bengaluru",
        skills=["Python", "FastAPI"],
        description="Senior Backend Engineer at Finlo - Python, FastAPI, PostgreSQL, Bengaluru",
    )
    defaults.update(overrides)
    app = Application(**defaults)
    if not app.status_history:
        app.status_history = [StatusChange(to_status=Status.APPLIED, at=app.applied_at, note="test")]
    return app
