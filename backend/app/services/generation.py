"""Draft generation — glue between an application, the user's history,
and the Gemini writer.

Every generated draft records *which* past drafts grounded it
(``grounded_on``), so the UI can show the provenance chips and the judges
can see the historical dataset actually flowing into new output.
"""

from __future__ import annotations

from ..models import Application, Draft, DraftType, Profile, utcnow
from ..repos.base import Repo
from .llm import DraftContext, Intelligence
from .retrieval import query_text, rank_exemplars


def generate_draft(
    repo: Repo,
    intelligence: Intelligence,
    app: Application,
    kind: DraftType,
    instructions: str = "",
    touch: int = 1,
) -> Draft:
    profile = repo.get_profile(app.uid) or Profile(uid=app.uid)
    history = repo.list_drafts(app.uid)

    query_embedding = None
    vectors = intelligence.embed([query_text(app)])
    if vectors:
        query_embedding = vectors[0]

    exemplars = rank_exemplars(app, history, kind, query_embedding=query_embedding)
    days = max(0, (utcnow() - app.applied_at).days)

    written = intelligence.write_draft(
        DraftContext(
            kind=kind.value,
            role=app.role,
            company=app.company,
            location=app.location,
            job_type=app.job_type,
            description=app.description,
            skills=app.skills,
            days_since_applied=days,
            touch=touch,
            status=app.status.value,
            profile_name=profile.name,
            profile_headline=profile.headline,
            profile_years=profile.years_experience,
            profile_skills=profile.skills,
            profile_achievements=profile.achievements,
            tone=profile.tone,
            style_rules=profile.style_rules,
            exemplars=[d.contents for d, _ in exemplars],
            instructions=instructions,
        )
    )

    draft = Draft(
        uid=app.uid,
        application_id=app.id,
        type=kind,
        subject=written.subject,
        contents=written.body,
        source="generated",
        model=written.model,
        grounded_on=[d.id for d, _ in exemplars],
    )
    repo.put_draft(draft)

    # Deliberately NOT touching the application's staleness clock here:
    # writing a draft is preparation, not outreach. Only marking a draft
    # "sent" (drafts router) resets the clock that drives the cadence.
    return draft
