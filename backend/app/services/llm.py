"""Gemini intelligence layer.

Ports-and-adapters: the rest of the app talks to the :class:`Intelligence`
interface, which has exactly three capabilities —

- ``extract_postings``: unstructured posting descriptions → structured fields
- ``write_draft``     : application context + voice exemplars → a draft
- ``embed``           : text → vectors for retrieval

``GeminiIntelligence`` implements them with the google-genai SDK. Model
routing sends high-volume structured work to Flash (``gemini-3.7-flash``)
and the highest-stakes artifact — the cover letter — to Pro
(``gemini-3.1-pro-preview``), with a fallback chain so a preview-model
outage degrades to a stable model instead of a failed request.

``TemplateIntelligence`` is a deterministic, zero-network stand-in used in
demo mode and tests. It exercises the exact same code paths (grounding,
exemplar retrieval, report shapes), which is what makes the pipeline
testable end-to-end without credentials.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Protocol

log = logging.getLogger("offerloop.llm")


class GeminiError(RuntimeError):
    """A Gemini failure with a machine-readable code the API/UI can act on.

    codes: key_invalid | quota_exhausted | timeout | unavailable
    """

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def classify_gemini_error(exc: Exception) -> str:
    text = str(exc)
    if "API_KEY_INVALID" in text or "API key not valid" in text:
        return "key_invalid"
    if "RESOURCE_EXHAUSTED" in text or "429" in text or "quota" in text.lower():
        return "quota_exhausted"
    if "timed out" in text.lower() or "timeout" in text.lower() or "deadline" in text.lower():
        return "timeout"
    return "unavailable"


# ---------------------------------------------------------------------------
# Context passed to the writer
# ---------------------------------------------------------------------------


@dataclass
class DraftContext:
    kind: str  # cover_letter | follow_up_email | referral_request | linkedin_message
    role: str
    company: str
    location: str = ""
    job_type: str = ""
    description: str = ""
    skills: list[str] = field(default_factory=list)
    days_since_applied: int = 0
    touch: int = 1
    status: str = "applied"
    profile_name: str = ""
    profile_headline: str = ""
    profile_years: float = 0
    profile_skills: list[str] = field(default_factory=list)
    profile_achievements: str = ""
    tone: str = "warm, direct, confident"
    style_rules: str = ""  # user-set hard constraints, e.g. "never use em dashes"
    exemplars: list[str] = field(default_factory=list)  # past drafts, same type, most relevant first
    instructions: str = ""
    contact_name: str = ""  # recruiter/referrer, when the user recorded one


@dataclass
class WrittenDraft:
    subject: str
    body: str
    model: str


class Intelligence(Protocol):
    name: str

    def extract_postings(self, descriptions: list[str]) -> list[dict]: ...

    def write_draft(self, ctx: DraftContext) -> WrittenDraft: ...

    def prep_pack(self, ctx: DraftContext) -> tuple[dict, str]:
        """Interview prep for one application → (parsed pack, model name)."""
        ...

    def embed(self, texts: list[str]) -> list[list[float]] | None: ...


# ---------------------------------------------------------------------------
# Regex extraction — shared fallback so imports NEVER fail on an LLM outage
# ---------------------------------------------------------------------------

_CITIES = (
    "bengaluru|bangalore|mumbai|pune|hyderabad|chennai|delhi|gurgaon|gurugram|noida|"
    "kolkata|ahmedabad|jaipur|kochi|remote|hybrid|london|singapore|dubai|new york|san francisco"
)


def regex_extract(description: str) -> dict:
    """Best-effort structured extraction from a posting description.

    Handles the evaluation dataset shape, e.g.
    ``"Senior Backend Engineer - Python, Bengaluru"`` and common variants
    like ``"Data Platform Engineer - streaming pipelines"`` or
    ``"SDE II at Meesho (Bengaluru) - Java, AWS"``.
    """
    text = (description or "").strip()
    company = ""
    location = ""

    at_match = re.search(r"\bat\s+([A-Z][\w&.\- ]{1,40}?)(?:\s*[\(,\-]|$)", text)
    if at_match:
        company = at_match.group(1).strip()

    loc_match = re.search(rf"\b({_CITIES})\b", text, re.IGNORECASE)
    if loc_match:
        location = loc_match.group(1).title()

    parts = [p.strip() for p in text.split(" - ", 1)]
    role = parts[0] if parts and parts[0] else "Untitled role"
    role = re.sub(r"\bat\s+[A-Z][\w&.\- ]{1,40}$", "", role).strip() or "Untitled role"

    skills: list[str] = []
    if len(parts) > 1:
        for token in re.split(r"[,;/]", parts[1]):
            token = token.strip()
            if token and not re.fullmatch(rf"(?i){_CITIES}", token) and len(token) <= 40:
                skills.append(token)

    return {"role": role, "company": company, "location": location, "skills": skills[:8]}


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_EXTRACT_SYSTEM = (
    "You are a precise information extraction engine for a job application tracker. "
    "Given raw job posting descriptions, extract structured fields. Return ONLY JSON."
)

_EXTRACT_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "role": {"type": "STRING", "description": "Job title, e.g. 'Senior Backend Engineer'"},
            "company": {"type": "STRING", "description": "Company name if present, else empty string"},
            "location": {"type": "STRING", "description": "City or 'Remote' if present, else empty"},
            "skills": {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Up to 8 skills/technologies"},
        },
        "required": ["role", "company", "location", "skills"],
    },
}

_WRITE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "subject": {"type": "STRING", "description": "Email subject line; empty for a cover letter"},
        "body": {"type": "STRING", "description": "The full text, plain text with paragraph breaks"},
    },
    "required": ["subject", "body"],
}

_PREP_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "questions": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "question": {"type": "STRING"},
                    "why_they_ask": {"type": "STRING", "description": "One sentence on the interviewer's intent"},
                    "how_to_answer": {"type": "STRING", "description": "Angle using the candidate real background"},
                },
                "required": ["question", "why_they_ask", "how_to_answer"],
            },
        },
        "stories": {
            "type": "ARRAY",
            "items": {
                "type": "OBJECT",
                "properties": {
                    "title": {"type": "STRING", "description": "Short memorable label, e.g. 'The latency rescue'"},
                    "outline": {"type": "STRING", "description": "STAR outline from stated proof points only"},
                    "metric": {"type": "STRING", "description": "Number to land from the proof points, or empty"},
                },
                "required": ["title", "outline", "metric"],
            },
        },
        "questions_to_ask": {"type": "ARRAY", "items": {"type": "STRING"}},
    },
    "required": ["questions", "stories", "questions_to_ask"],
}

_PREP_SYSTEM = (
    "You are OfferLoop's interview coach. Build prep material grounded ONLY on the posting "
    "and the candidate's stated profile — never invent experience, employers, or numbers the "
    "candidate did not provide. Sharp, specific, zero filler. Return ONLY JSON."
)


def _prep_prompt(ctx: DraftContext) -> str:
    return "\n".join(
        [
            "TASK: Interview prep pack for this application.",
            "- 6 to 8 likely interview questions for THIS role (mix technical/behavioral as the",
            "  posting suggests), each with why they ask it and how THIS candidate should answer.",
            "- 2 to 3 STAR story outlines built strictly from the candidate's proof points",
            "  (if proof points are thin, coach what to prepare rather than inventing).",
            "- 4 sharp questions the candidate should ask the interviewer, specific to this posting.",
            "",
            "POSTING:",
            f"- Role: {ctx.role}",
            f"- Company: {ctx.company or 'not stated'}",
            f"- Description: {ctx.description[:2000] or 'not provided'}",
            f"- Key skills: {', '.join(ctx.skills) if ctx.skills else 'not stated'}",
            "",
            "CANDIDATE:",
            f"- Headline: {ctx.profile_headline or 'not provided'}",
            f"- Experience: {ctx.profile_years:g} years" if ctx.profile_years else "- Experience: not provided",
            f"- Skills: {', '.join(ctx.profile_skills) if ctx.profile_skills else 'not provided'}",
            f"- Proof points: {ctx.profile_achievements or 'not provided'}",
        ]
    )


_WRITER_SYSTEM = (
    "You are OfferLoop's writing engine: a sharp career coach who writes application "
    "materials that get replies. Rules: be specific, never generic; no clichés "
    "('I am writing to express my interest', 'esteemed organization', 'perfect fit'); "
    "no fabricated facts — only use what the candidate profile and posting provide; "
    "sound like a real person, not a template. Match the candidate's voice from the "
    "writing samples when provided. Return ONLY JSON."
)


_TASKS = {
    "cover_letter": "cover letter (170-230 words, no subject needed).",
    "follow_up_email": "follow-up email (60-120 words) with a subject line.",
    "referral_request": (
        "referral request (70-120 words) with a subject line, addressed to someone who works "
        "at the company. Warm, not needy; make saying yes effortless (offer to send a resume "
        "and a one-line blurb they can forward); name the exact role."
    ),
    "linkedin_message": (
        "LinkedIn direct message to a recruiter or hiring manager. Under 400 characters, "
        "no subject (return an empty subject), no greeting fluff: one specific hook tied to "
        "the role, one credential, one soft ask."
    ),
}


def _writer_prompt(ctx: DraftContext) -> str:
    lines = [
        "TASK: Write a " + _TASKS.get(ctx.kind, _TASKS["follow_up_email"]),
        "",
        "POSTING:",
        f"- Role: {ctx.role}",
        f"- Company: {ctx.company or 'not stated (do not invent one; refer to the role/team instead)'}",
        f"- Location: {ctx.location or 'not stated'}",
        f"- Type: {ctx.job_type or 'not stated'}",
        f"- Description: {ctx.description[:1500] or 'not provided'}",
        f"- Key skills: {', '.join(ctx.skills) if ctx.skills else 'not stated'}",
        "",
        "CANDIDATE:",
        f"- Name: {ctx.profile_name or 'the candidate'}",
        f"- Headline: {ctx.profile_headline or 'not provided'}",
        f"- Experience: {ctx.profile_years:g} years" if ctx.profile_years else "- Experience: not provided",
        f"- Skills: {', '.join(ctx.profile_skills) if ctx.profile_skills else 'not provided'}",
        f"- Proof points: {ctx.profile_achievements or 'not provided'}",
        f"- Preferred tone: {ctx.tone}",
    ]
    if ctx.contact_name and ctx.kind in ("referral_request", "linkedin_message", "follow_up_email"):
        lines.append(f"- Address it to: {ctx.contact_name}")
    if ctx.kind == "follow_up_email":
        lines += [
            "",
            "SITUATION:",
            f"- Applied {ctx.days_since_applied} days ago; current stage: {ctx.status}.",
            f"- This is follow-up touch #{ctx.touch} in the cadence"
            + (" — keep it shorter and lighter than the previous touch." if ctx.touch > 1 else "."),
            "- Goal: polite persistence. Reference the elapsed time, restate one concrete "
            "value point matched to the posting, and end with a clear, low-friction ask.",
        ]
    elif ctx.kind == "cover_letter":
        lines += [
            "",
            "STRUCTURE: hook tied to this specific role -> one or two proof points matched to "
            "the posting's needs -> why this company/team -> confident close with a call to action. "
            "Sign off with the candidate's name.",
        ]
    if ctx.style_rules:
        lines += [
            "",
            "HARD WRITING RULES set by the candidate — follow every one strictly, no exceptions:",
            ctx.style_rules[:600],
        ]
    if ctx.exemplars:
        lines += ["", "CANDIDATE'S PAST WRITING (match this voice, do not copy sentences):"]
        for i, ex in enumerate(ctx.exemplars[:3], 1):
            lines.append(f"--- sample {i} ---\n{ex[:900]}")
    if ctx.instructions:
        lines += ["", f"EXTRA INSTRUCTIONS FROM THE CANDIDATE: {ctx.instructions[:500]}"]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Real Gemini adapter
# ---------------------------------------------------------------------------

_EXTRACT_CHUNK = 40
_EMBED_CHUNK = 96


class GeminiIntelligence:
    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str = "",
        use_vertex: bool = False,
        project: str = "",
        location: str = "global",
        model_flash: str = "gemini-3.7-flash",
        model_pro: str = "gemini-3.1-pro-preview",
        fallbacks: list[str] | None = None,
        model_embed: str = "gemini-embedding-001",
        embed_dim: int = 768,
        timeout_ms: int = 45000,
    ) -> None:
        from google import genai  # deferred so demo mode has zero GCP imports
        from google.genai import types

        # The hard timeout is load-bearing: a model that hangs (observed in
        # the wild on flagship models for free-tier keys) must fail fast so
        # the fallback chain can do its job.
        http_options = types.HttpOptions(timeout=timeout_ms)
        if use_vertex:
            self._client = genai.Client(
                vertexai=True, project=project, location=location, http_options=http_options
            )
        else:
            self._client = genai.Client(api_key=api_key, http_options=http_options)
        self._flash_chain = [model_flash] + [m for m in (fallbacks or []) if "flash" in m and m != model_flash]
        self._pro_chain = [model_pro] + [m for m in (fallbacks or []) if m != model_pro]
        self._model_embed = model_embed
        self._embed_dim = embed_dim

    # -- internals ---------------------------------------------------------
    def _generate_json(self, chain: list[str], system: str, prompt: str, schema: dict, temperature: float):
        from google.genai import types

        last_error: Exception | None = None
        for model in chain:
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction=system,
                        response_mime_type="application/json",
                        response_schema=schema,
                        temperature=temperature,
                    ),
                )
                return json.loads(response.text), model
            except Exception as exc:  # noqa: BLE001 — any model error means "try the next"
                log.warning("model %s failed (%s); falling back", model, exc)
                last_error = exc
        raise GeminiError(
            classify_gemini_error(last_error) if last_error else "unavailable",
            f"all Gemini models failed: {last_error}",
        )

    # -- Intelligence ------------------------------------------------------
    def extract_postings(self, descriptions: list[str]) -> list[dict]:
        results: list[dict] = []
        for start in range(0, len(descriptions), _EXTRACT_CHUNK):
            chunk = descriptions[start : start + _EXTRACT_CHUNK]
            prompt = (
                "Extract fields for each posting below. Return a JSON array "
                "with one object per posting, in order.\n\n"
                + "\n".join(f"{i + 1}. {d[:600]}" for i, d in enumerate(chunk))
            )
            try:
                parsed, _ = self._generate_json(self._flash_chain, _EXTRACT_SYSTEM, prompt, _EXTRACT_SCHEMA, 0.1)
                if not isinstance(parsed, list) or len(parsed) != len(chunk):
                    raise ValueError(f"expected {len(chunk)} items, got {parsed!r:.120}")
                results.extend(
                    {**regex_extract(desc), **{k: v for k, v in item.items() if v}}
                    for desc, item in zip(chunk, parsed, strict=True)
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("extraction batch fell back to regex: %s", exc)
                results.extend(regex_extract(d) for d in chunk)
        return results

    def write_draft(self, ctx: DraftContext) -> WrittenDraft:
        chain = self._pro_chain if ctx.kind == "cover_letter" else self._flash_chain
        parsed, model = self._generate_json(chain, _WRITER_SYSTEM, _writer_prompt(ctx), _WRITE_SCHEMA, 0.7)
        return WrittenDraft(subject=parsed.get("subject", ""), body=parsed.get("body", ""), model=model)

    def prep_pack(self, ctx: DraftContext) -> tuple[dict, str]:
        return self._generate_json(self._flash_chain, _PREP_SYSTEM, _prep_prompt(ctx), _PREP_SCHEMA, 0.5)

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        from google.genai import types

        try:
            vectors: list[list[float]] = []
            for start in range(0, len(texts), _EMBED_CHUNK):
                chunk = [t[:2000] for t in texts[start : start + _EMBED_CHUNK]]
                response = self._client.models.embed_content(
                    model=self._model_embed,
                    contents=chunk,
                    config=types.EmbedContentConfig(output_dimensionality=self._embed_dim),
                )
                vectors.extend(e.values for e in response.embeddings)
            return vectors
        except Exception as exc:  # noqa: BLE001 — retrieval degrades to lexical scoring
            log.warning("embedding unavailable, retrieval will use lexical scoring: %s", exc)
            return None


# ---------------------------------------------------------------------------
# Deterministic template adapter (demo mode + tests)
# ---------------------------------------------------------------------------


class TemplateIntelligence:
    """Credential-free writer. Deterministic, decent prose, instant."""

    name = "template"

    def extract_postings(self, descriptions: list[str]) -> list[dict]:
        return [regex_extract(d) for d in descriptions]

    def write_draft(self, ctx: DraftContext) -> WrittenDraft:
        name = ctx.profile_name or "Your name"
        company = ctx.company or "your team"
        skills = ", ".join(ctx.skills[:3]) if ctx.skills else "this stack"
        mine = ", ".join(ctx.profile_skills[:3]) if ctx.profile_skills else "shipping production systems"

        if ctx.kind == "cover_letter":
            years = f"{ctx.profile_years:g}" if ctx.profile_years else "few"
            focus = "exactly this stack" if mine == skills else mine
            proof = (
                f"A concrete example: {ctx.profile_achievements[0].lower()}{ctx.profile_achievements[1:]}"
                if ctx.profile_achievements
                else "I have shipped systems that people rely on every day"
            )
            body = (
                f"Dear Hiring Manager,\n\n"
                f"The {ctx.role} opening caught my attention because it sits exactly where I do my "
                f"best work: {skills}. Over the last {years} years I've focused on {focus}. {proof}.\n\n"
                f"What draws me to {company} is the chance to own problems end to end rather than a "
                f"slice of them. I move quickly, communicate clearly, and hold a high bar for the "
                f"details that make software feel dependable.\n\n"
                f"I'd welcome a conversation about how I can contribute from week one.\n\n"
                f"Warm regards,\n{name}"
            )
            return WrittenDraft(subject="", body=body, model="template")

        if ctx.kind == "referral_request":
            greeting = f"Hi {ctx.contact_name}," if ctx.contact_name else "Hi,"
            body = (
                f"{greeting}\n\n"
                f"I'm applying for the {ctx.role} role at {company} and I'd really value a referral "
                f"if you're comfortable giving one. My background in {mine} maps closely onto what "
                f"the posting asks for{', especially ' + skills if ctx.skills and skills != mine else ''}.\n\n"
                f"To make it painless: I can send over my resume and a two-line blurb you can forward "
                f"as-is. And if a referral isn't possible, any pointer about the team would already "
                f"help a lot.\n\nThank you either way!\n{name}"
            )
            subject = f"Referral request — {ctx.role}" + (f" at {ctx.company}" if ctx.company else "")
            return WrittenDraft(subject=subject, body=body, model="template")

        if ctx.kind == "linkedin_message":
            greeting = f"Hi {ctx.contact_name.split(' ')[0]} — " if ctx.contact_name else "Hi — "
            body = (
                f"{greeting}I just applied for the {ctx.role} role"
                f"{' at ' + ctx.company if ctx.company else ''} and wanted to reach out directly. "
                f"I've spent {f'{ctx.profile_years:g} years' if ctx.profile_years else 'my career'} "
                f"working with {mine}, which is exactly what the posting calls for. "
                f"Would you be open to a quick chat this week? — {name}"
            )
            return WrittenDraft(subject="", body=body, model="template")

        opener = {
            1: f"I applied for the {ctx.role} position {ctx.days_since_applied} days ago and wanted to check in.",
            2: f"Following up once more on my {ctx.role} application from {ctx.days_since_applied} days ago.",
        }.get(ctx.touch, f"A final note regarding my {ctx.role} application.")
        overlap = f", especially {skills}" if ctx.skills and skills != mine else ""
        body = (
            f"Hi,\n\n{opener} I remain genuinely interested — my background in {mine} lines up "
            f"closely with what the role needs{overlap}.\n\n"
            f"If it's useful, I'm happy to share work samples or make time for a quick call this "
            f"week. Is there anything else you need from my side?\n\nBest,\n{name}"
        )
        subject = f"Following up: {ctx.role} application" + (f" — {ctx.company}" if ctx.company else "")
        return WrittenDraft(subject=subject, body=body, model="template")

    def prep_pack(self, ctx: DraftContext) -> tuple[dict, str]:
        skills = ctx.skills[:3] or ctx.profile_skills[:3] or ["your core stack"]
        company = ctx.company or "the company"
        proof = ctx.profile_achievements.strip()
        questions = [
            {
                "question": f"Walk me through your experience with {skills[0]}.",
                "why_they_ask": "It's the posting's top requirement — they want depth, not name-dropping.",
                "how_to_answer": "Pick one real project: the problem, your decisions, the measurable result.",
            },
            {
                "question": f"Why do you want to work at {company}?",
                "why_they_ask": "They're screening for genuine interest versus a mass application.",
                "how_to_answer": "Tie one concrete detail from the posting to what you want to do next.",
            },
            {
                "question": "Tell me about a time something you shipped went wrong.",
                "why_they_ask": "Ownership and blamelessness under pressure.",
                "how_to_answer": "Failure, your fix, and the guardrail you added so it can't recur.",
            },
            {
                "question": f"How would you approach your first 30 days as a {ctx.role}?",
                "why_they_ask": "They want a self-starter with a plan, not a passenger.",
                "how_to_answer": "Learn the system, ship something small early, earn trust with quick wins.",
            },
            {
                "question": "What's a technical decision you've reversed, and why?",
                "why_they_ask": "Intellectual honesty and judgment beat stubbornness.",
                "how_to_answer": "Show the new information that changed your mind and the outcome.",
            },
            {
                "question": "Where do you want to be in two years?",
                "why_they_ask": "Retention risk and ambition check.",
                "how_to_answer": f"Growth that this {ctx.role} role genuinely feeds into — be specific.",
            },
        ]
        stories = (
            [
                {
                    "title": "Your headline win",
                    "outline": f"Situation and task behind: {proof[:220]}. Action: the two decisions that "
                    "were yours. Result: land the number explicitly.",
                    "metric": proof[:80],
                }
            ]
            if proof
            else [
                {
                    "title": "Prepare one headline win",
                    "outline": "Add a proof point with a number to your Profile — a latency cut, a launch, "
                    "a cost saving — then rebuild this pack. Interviewers remember numbers.",
                    "metric": "",
                }
            ]
        ) + [
            {
                "title": "The conflict you resolved",
                "outline": "A disagreement about approach; how you got to evidence instead of opinion; "
                "what shipped because of it.",
                "metric": "",
            }
        ]
        questions_to_ask = [
            f"What does the first shipped win look like for this {ctx.role} hire?",
            "What separates your best person in this role from a merely good one?",
            f"What's the hardest problem the team is facing with {skills[0]} right now?",
            "How does the team decide what NOT to build?",
        ]
        return {"questions": questions, "stories": stories, "questions_to_ask": questions_to_ask}, "template"

    def embed(self, texts: list[str]) -> list[list[float]] | None:
        return None  # retrieval falls back to lexical scoring


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_intelligence(settings) -> Intelligence:
    if settings.gemini_enabled:
        return GeminiIntelligence(
            api_key=settings.gemini_api_key,
            use_vertex=settings.use_vertex,
            project=settings.gcp_project,
            location=settings.vertex_location,
            model_flash=settings.model_flash,
            model_pro=settings.model_pro,
            fallbacks=[m.strip() for m in settings.model_fallbacks.split(",") if m.strip()],
            model_embed=settings.model_embed,
            embed_dim=settings.embed_dim,
            timeout_ms=settings.gemini_timeout_ms,
        )
    log.info("Gemini credentials absent — using deterministic template writer")
    return TemplateIntelligence()
