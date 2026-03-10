"""Internal page-content fetcher — NOT a LangChain tool.

Called automatically by ``search_web`` to enrich the top-N organic
results with extracted page text.  Uses `trafilatura
<https://trafilatura.readthedocs.io>`_ for HTML→text extraction.

This module is intentionally **not** exposed as a ``@tool``.  It is an
implementation detail of the search pipeline, eliminating an extra
LLM round-trip that a standalone fetch tool would require.

All HTTP is via ``httpx`` for easy mocking in tests.
"""

from __future__ import annotations

import logging

import httpx
import trafilatura

from atlas.config import get_settings

logger = logging.getLogger(__name__)

# ── In-process cache ─────────────────────────────────────────────────────────

# Keyed by URL → extracted text (or empty string on failure).
_fetch_cache: dict[str, str] = {}


def clear_fetch_cache() -> None:
    """Reset the in-process fetch response cache."""
    _fetch_cache.clear()


# ── Public helper ────────────────────────────────────────────────────────────

# Domains we refuse to fetch (login walls, paywalls, robots.txt issues).
_BLOCKED_DOMAINS: frozenset[str] = frozenset(
    {
        "facebook.com",
        "instagram.com",
        "twitter.com",
        "x.com",
        "linkedin.com",
        "pinterest.com",
        "tiktok.com",
    }
)

# Content-types we accept — only HTML pages.
_ACCEPTED_CONTENT_TYPES: tuple[str, ...] = (
    "text/html",
    "application/xhtml+xml",
)


def _is_blocked(url: str) -> bool:
    """Return True if the URL's domain is on the block list or invalid."""
    try:
        parsed = httpx.URL(url)
        host = parsed.host or ""
        # Require an HTTP(S) scheme.
        if parsed.scheme not in ("http", "https"):
            return True
    except Exception:
        return True
    # Match "facebook.com" and "www.facebook.com" etc.
    for domain in _BLOCKED_DOMAINS:
        if host == domain or host.endswith(f".{domain}"):
            return True
    return False


def fetch_page_content(url: str, max_chars: int | None = None) -> str:
    """Fetch *url* and return extracted main-body text.

    Parameters
    ----------
    url:
        Absolute HTTP(S) URL to fetch.
    max_chars:
        Maximum character length for the returned text.  Defaults to
        ``settings.atlas_fetch_max_chars`` (8 000).

    Returns
    -------
    str
        Extracted page text, truncated to *max_chars*.  Returns an
        empty string on any error (network, timeout, non-HTML, blocked
        domain) — this function **never raises**.
    """
    if max_chars is None:
        max_chars = get_settings().atlas_fetch_max_chars

    # ── Cache check ──────────────────────────────────────────────────
    if url in _fetch_cache:
        return _fetch_cache[url]

    # ── Guard: blocked domains ───────────────────────────────────────
    if _is_blocked(url):
        logger.debug("fetch_page_content: blocked domain — %s", url)
        _fetch_cache[url] = ""
        return ""

    # ── HTTP GET ─────────────────────────────────────────────────────
    try:
        resp = httpx.get(
            url,
            timeout=8,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (compatible; AtlasBot/0.1; "
                    "+https://github.com/atlas-travel)"
                ),
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        resp.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError, httpx.TimeoutException) as exc:
        logger.debug("fetch_page_content: HTTP error for %s — %s", url, exc)
        _fetch_cache[url] = ""
        return ""

    # ── Content-type guard ───────────────────────────────────────────
    ct = resp.headers.get("content-type", "")
    if not any(mime in ct for mime in _ACCEPTED_CONTENT_TYPES):
        logger.debug("fetch_page_content: non-HTML content-type %s — %s", ct, url)
        _fetch_cache[url] = ""
        return ""

    # ── Extract with trafilatura ─────────────────────────────────────
    text = trafilatura.extract(resp.text) or ""
    if len(text) > max_chars:
        text = text[:max_chars] + "…"

    _fetch_cache[url] = text
    return text
