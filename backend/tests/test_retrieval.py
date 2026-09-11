"""Exemplar ranking: relevant, sent, recent — in that order of force."""

from __future__ import annotations

from app.models import Draft, DraftStatus, DraftType
from app.services.retrieval import cosine, lexical_overlap, rank_exemplars, tokens
from tests.conftest import make_application


def _draft(text: str, status=DraftStatus.DRAFT, kind=DraftType.COVER_LETTER, app_id="other", embedding=None):
    return Draft(
        uid="u1", application_id=app_id, type=kind, contents=text, status=status, embedding=embedding
    )


class TestScoring:
    def test_cosine_basics(self):
        assert cosine([1, 0], [1, 0]) == 1.0
        assert cosine([1, 0], [0, 1]) == 0.0
        assert cosine([], [1, 2]) == 0.0
        assert cosine([1, 2], [1, 2, 3]) == 0.0  # dimension mismatch is safe

    def test_lexical_overlap_favors_shared_vocabulary(self):
        query = tokens("python kafka backend engineer")
        relevant = lexical_overlap(query, "Four years of python and kafka pipeline work")
        irrelevant = lexical_overlap(query, "Watercolor painting and pottery")
        assert relevant > irrelevant >= 0.0


class TestRanking:
    def test_relevant_draft_outranks_irrelevant(self):
        target = make_application(role="Backend Engineer", skills=["Python", "Kafka"])
        drafts = [
            _draft("A letter about python kafka and backend systems."),
            _draft("A letter about frontend animation in CSS."),
        ]
        ranked = rank_exemplars(target, drafts, DraftType.COVER_LETTER)
        assert ranked[0][0].contents.startswith("A letter about python")

    def test_sent_beats_unsent_at_equal_relevance(self):
        target = make_application(role="Backend Engineer", skills=["Python"])
        same = "A letter about python backend work."
        drafts = [_draft(same), _draft(same, status=DraftStatus.SENT)]
        ranked = rank_exemplars(target, drafts, DraftType.COVER_LETTER)
        assert ranked[0][0].status == DraftStatus.SENT

    def test_embeddings_dominate_when_present(self):
        target = make_application(role="Backend Engineer", skills=["Python"])
        drafts = [
            _draft("python backend letter", embedding=[0.0, 1.0]),  # lexical hit, embedding miss
            _draft("totally different words", embedding=[1.0, 0.0]),  # embedding hit
        ]
        ranked = rank_exemplars(target, drafts, DraftType.COVER_LETTER, query_embedding=[1.0, 0.0])
        assert ranked[0][0].contents == "totally different words"

    def test_own_application_draft_excluded(self):
        target = make_application(role="Backend Engineer")
        drafts = [_draft("python letter", app_id=target.id)]
        assert rank_exemplars(target, drafts, DraftType.COVER_LETTER) == []

    def test_top_k_limit(self):
        target = make_application(role="Backend Engineer", skills=["Python"])
        drafts = [_draft(f"python letter number {i}") for i in range(10)]
        assert len(rank_exemplars(target, drafts, DraftType.COVER_LETTER, k=3)) == 3
