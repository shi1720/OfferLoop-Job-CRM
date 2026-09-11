"""Shared FastAPI dependencies. Repo and intelligence are singletons built
at startup (see main.create_app) and stashed on app.state."""

from __future__ import annotations

from fastapi import Request

from .repos.base import Repo
from .services.llm import Intelligence


def get_repo(request: Request) -> Repo:
    return request.app.state.repo


def get_intelligence(request: Request) -> Intelligence:
    return request.app.state.intelligence
