"""Exemplar retrieval — the "historical learning" half of the pipeline.

When OfferLoop writes a new cover letter or follow-up, it first retrieves
the user's most relevant past drafts of the same type and hands them to
Gemini as voice exemplars. Scoring is hybrid:

- cosine similarity over Gemini embeddings when they exist (live mode
  computes them at import time, batched), and
- lexical overlap between the target role/skills and the draft text,
  which needs no credentials and keeps demo mode fully functional.

Sent drafts outrank unsent ones (they represent the user's real voice),
and recency breaks ties.
"""

from __future__ import annotations

import math
import re

from ..models import Application, Draft, DraftStatus, DraftType

_WORD = re.compile(r"[a-z0-9+#]{2,}")
_STOP = {
    "the", "and", "for", "with", "you", "your", "our", "are", "this", "that", "from",
    "have", "has", "was", "will", "would", "about", "into", "over", "than", "then",
    "dear", "hiring", "manager", "regards", "best", "warm", "team", "role", "position",
}


def tokens(text: str) -> set[str]:
    return {w for w in _WORD.findall(text.lower()) if w not in _STOP}


def lexical_overlap(query: set[str], text: str) -> float:
    if not query:
        return 0.0
    doc = tokens(text)
    if not doc:
        return 0.0
    return len(query & doc) / math.sqrt(len(query) * len(doc))


def cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


def query_text(app: Application) -> str:
    return " ".join([app.role, app.company, " ".join(app.skills), app.description[:400]])


def rank_exemplars(
    target: Application,
    candidates: list[Draft],
    kind: DraftType,
    query_embedding: list[float] | None = None,
    k: int = 3,
) -> list[tuple[Draft, float]]:
    """Return the top-k past drafts to use as voice exemplars, with scores."""
    query = tokens(query_text(target))
    scored: list[tuple[Draft, float]] = []
    for draft in candidates:
        if draft.type != kind or draft.application_id == target.id:
            continue
        lex = lexical_overlap(query, draft.contents)
        emb = cosine(query_embedding or [], draft.embedding or [])
        score = 0.65 * emb + 0.35 * lex if emb > 0 else lex
        if draft.status == DraftStatus.SENT:
            score += 0.15  # the user's real, sent voice beats an unsent draft
        scored.append((draft, score))
    scored.sort(key=lambda pair: (pair[1], pair[0].created_at), reverse=True)
    return scored[:k]
