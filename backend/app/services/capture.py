"""Paste-a-link job capture.

The user pastes a posting URL (or the raw JD text when a site is behind a
login wall — LinkedIn usually is) and gets back structured fields to
confirm in the "log application" form. Capture never creates anything
behind the user's back.

The URL fetch is deliberately paranoid: this is a server-side request to a
user-supplied address, so scheme, host, and resolved IPs are validated
(before the request and again after redirects) to keep it from becoming an
SSRF hole into the metadata service or the VPC.
"""

from __future__ import annotations

import html as html_lib
import ipaddress
import logging
import re
import socket
from urllib.parse import urlparse

from ..models import CapturedPosting
from .llm import Intelligence

log = logging.getLogger("offerloop.capture")

MAX_FETCH_BYTES = 2_000_000
FETCH_TIMEOUT_S = 12.0
MIN_USABLE_CHARS = 80
DESCRIPTION_LIMIT = 5000

_PASTE_HINT = (
    "Couldn't read that page — many job boards (LinkedIn included) hide postings "
    "behind a login. Paste the job description text instead and I'll extract it."
)


class CaptureError(Exception):
    """User-facing capture failure with a helpful message."""


def _assert_public_http_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise CaptureError("Only http(s) links can be captured.")
    if not parsed.hostname:
        raise CaptureError("That doesn't look like a valid link.")
    if parsed.username or parsed.password:
        raise CaptureError("Links with embedded credentials aren't allowed.")
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        raise CaptureError("That host doesn't resolve — check the link.") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise CaptureError("That link points at a private network, which isn't allowed.")


_MAX_REDIRECTS = 3


def _fetch(url: str) -> tuple[str, str]:
    """Fetch a public page → (html, final_url).

    Redirects are followed MANUALLY so every hop is validated *before* it is
    requested — auto-follow would happily GET a redirect into the metadata
    service before any final-URL check could run.
    """
    import httpx

    try:
        current = url
        with httpx.Client(
            follow_redirects=False,
            timeout=FETCH_TIMEOUT_S,
            headers={
                "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) OfferLoop/1.0 job-capture",
                "Accept": "text/html,application/xhtml+xml,text/plain;q=0.9,*/*;q=0.5",
            },
        ) as client:
            for _hop in range(_MAX_REDIRECTS + 1):
                _assert_public_http_url(current)
                with client.stream("GET", current) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        location = response.headers.get("location")
                        if not location:
                            raise CaptureError(_PASTE_HINT)
                        current = str(httpx.URL(current).join(location))
                        continue
                    if response.status_code >= 400:
                        raise CaptureError(_PASTE_HINT)
                    content_type = response.headers.get("content-type", "")
                    if not any(t in content_type for t in ("text/html", "text/plain", "application/xhtml")):
                        raise CaptureError("That link isn't a web page. " + _PASTE_HINT)
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_FETCH_BYTES:
                            break  # enough page to extract from; postings are small
                        chunks.append(chunk)
                    return (
                        b"".join(chunks).decode(response.encoding or "utf-8", errors="replace"),
                        current,
                    )
        raise CaptureError("That link redirects too many times. " + _PASTE_HINT)
    except CaptureError:
        raise
    except Exception as exc:  # noqa: BLE001 — network errors become one friendly hint
        log.info("capture fetch failed for %s: %s", url, exc)
        raise CaptureError(_PASTE_HINT) from exc


_BLOCK_TAGS = r"p|br|li|div|section|article|tr|h[1-6]|ul|ol"


def strip_html(raw: str) -> tuple[str, str]:
    """Very small HTML → text: (title, text). No parser dependency needed —
    posting pages only have to survive well enough for extraction."""
    title_match = re.search(r"<title[^>]*>(.*?)</title>", raw, re.IGNORECASE | re.DOTALL)
    title = html_lib.unescape(title_match.group(1)).strip() if title_match else ""
    text = re.sub(r"(?is)<(script|style|noscript|svg|head|nav|footer)[^>]*>.*?</\1>", " ", raw)
    text = re.sub(rf"(?i)</?(?:{_BLOCK_TAGS})[^>]*>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html_lib.unescape(text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n", text)
    return title, text.strip()


_TITLE_NOISE = re.compile(r"\s*[|\-–—]\s*(LinkedIn|Naukri\.com|Indeed(\.com)?|Glassdoor|Wellfound|hiring).*$", re.I)

_JOB_TYPE_HINTS = [
    ("internship", re.compile(r"\bintern(ship)?\b", re.I)),
    ("contract", re.compile(r"\b(contract|freelance|contractor)\b", re.I)),
    ("part-time", re.compile(r"\bpart[ -]?time\b", re.I)),
    ("full-time", re.compile(r"\bfull[ -]?time\b", re.I)),
]


def capture_posting(intelligence: Intelligence, url: str = "", text: str = "") -> CapturedPosting:
    url = (url or "").strip()
    pasted = (text or "").strip()
    title = ""
    if url and not pasted:
        page, final_url = _fetch(url)
        title, pasted = strip_html(page)
        url = final_url
    if len(pasted) < MIN_USABLE_CHARS:
        raise CaptureError(
            _PASTE_HINT if url else "That's too short to extract from — paste the full job description."
        )

    clean_title = _TITLE_NOISE.sub("", title).strip()
    basis = (f"{clean_title}\n{pasted}" if clean_title else pasted)[:DESCRIPTION_LIMIT]
    fields = intelligence.extract_postings([basis[:4000]])[0]

    job_type = ""
    for label, pattern in _JOB_TYPE_HINTS:
        if pattern.search(basis):
            job_type = label
            break

    role = (fields.get("role") or "").strip()
    if role in ("", "Untitled role") and clean_title:
        role = clean_title[:80]
    return CapturedPosting(
        role=role or "Untitled role",
        company=(fields.get("company") or "").strip(),
        location=(fields.get("location") or "").strip(),
        job_type=job_type,
        skills=fields.get("skills") or [],
        description=pasted[:DESCRIPTION_LIMIT],
        posting_url=url,
    )
