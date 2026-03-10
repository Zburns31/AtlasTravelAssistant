"""Tests for the page-content fetcher (``atlas.tools.fetch``)."""

from __future__ import annotations

import httpx
import pytest

from atlas.tools.fetch import (
    _is_blocked,
    clear_fetch_cache,
    fetch_page_content,
)


# ── Auto-clear cache between tests ──────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_fetch_cache()
    yield
    clear_fetch_cache()


# ── Helpers ──────────────────────────────────────────────────────────────

SAMPLE_HTML = """\
<html>
<head><title>Kyoto Travel Guide</title></head>
<body>
<article>
<h1>Kyoto Travel Guide 2025</h1>
<p>Kyoto is one of the most beautiful cities in Japan, known for its
classical Buddhist temples, stunning gardens, imperial palaces, and
traditional wooden houses. The city was the capital of Japan for over
a thousand years.</p>
<p>Must-visit temples include Kinkaku-ji (Golden Pavilion), Fushimi
Inari Taisha with its iconic torii gates, and Kiyomizu-dera with its
spectacular wooden stage.</p>
</article>
</body>
</html>
"""

EXTRACTED_TEXT_FRAGMENT = "Kyoto is one of the most beautiful cities"


def _mock_html_response(url: str, html: str = SAMPLE_HTML, status: int = 200):
    """Build a fake ``httpx.Response`` with HTML content."""
    return httpx.Response(
        status,
        request=httpx.Request("GET", url),
        content=html.encode(),
        headers={"content-type": "text/html; charset=utf-8"},
    )


def _mock_non_html_response(url: str):
    return httpx.Response(
        200,
        request=httpx.Request("GET", url),
        content=b"%PDF-1.4 binary content",
        headers={"content-type": "application/pdf"},
    )


# ── Domain blocking ─────────────────────────────────────────────────────


class TestIsBlocked:
    def test_blocked_domain(self):
        assert _is_blocked("https://www.facebook.com/some-page") is True

    def test_blocked_subdomain(self):
        assert _is_blocked("https://m.twitter.com/user") is True

    def test_allowed_domain(self):
        assert _is_blocked("https://www.lonelyplanet.com/kyoto") is False

    def test_invalid_url(self):
        assert _is_blocked("not-a-url") is True


# ── fetch_page_content ───────────────────────────────────────────────────


class TestFetchPageContent:
    def _patch(
        self, mocker, url="https://example.com/guide", html=SAMPLE_HTML, status=200
    ):
        """Patch httpx.get and settings, return the mock."""
        mock_settings = mocker.MagicMock()
        mock_settings.atlas_fetch_max_chars = 8000
        mocker.patch("atlas.tools.fetch.get_settings", return_value=mock_settings)
        mock_get = mocker.patch(
            "atlas.tools.fetch.httpx.get",
            return_value=_mock_html_response(url, html, status),
        )
        return mock_get

    def test_happy_path(self, mocker):
        """Extracts readable text from a valid HTML page."""
        self._patch(mocker)
        text = fetch_page_content("https://example.com/guide")
        assert len(text) > 0
        assert EXTRACTED_TEXT_FRAGMENT in text

    def test_truncates_to_max_chars(self, mocker):
        """Long content is truncated with an ellipsis."""
        self._patch(mocker)
        text = fetch_page_content("https://example.com/guide", max_chars=50)
        assert len(text) <= 52  # 50 + "…"
        assert text.endswith("…")

    def test_non_html_returns_empty(self, mocker):
        """Non-HTML content types are rejected gracefully."""
        mock_settings = mocker.MagicMock()
        mock_settings.atlas_fetch_max_chars = 8000
        mocker.patch("atlas.tools.fetch.get_settings", return_value=mock_settings)
        mocker.patch(
            "atlas.tools.fetch.httpx.get",
            return_value=_mock_non_html_response("https://example.com/doc.pdf"),
        )
        text = fetch_page_content("https://example.com/doc.pdf")
        assert text == ""

    def test_http_error_returns_empty(self, mocker):
        """HTTP errors are caught and return empty string."""
        mock_settings = mocker.MagicMock()
        mock_settings.atlas_fetch_max_chars = 8000
        mocker.patch("atlas.tools.fetch.get_settings", return_value=mock_settings)

        def _raise(url, **kw):
            resp = httpx.Response(404, request=httpx.Request("GET", url))
            resp.raise_for_status()

        mocker.patch("atlas.tools.fetch.httpx.get", side_effect=_raise)
        text = fetch_page_content("https://example.com/missing")
        assert text == ""

    def test_timeout_returns_empty(self, mocker):
        """Network timeouts are caught and return empty string."""
        mock_settings = mocker.MagicMock()
        mock_settings.atlas_fetch_max_chars = 8000
        mocker.patch("atlas.tools.fetch.get_settings", return_value=mock_settings)
        mocker.patch(
            "atlas.tools.fetch.httpx.get",
            side_effect=httpx.TimeoutException("timed out"),
        )
        text = fetch_page_content("https://example.com/slow")
        assert text == ""

    def test_blocked_domain_returns_empty(self, mocker):
        """Blocked domains are never fetched."""
        mock_settings = mocker.MagicMock()
        mock_settings.atlas_fetch_max_chars = 8000
        mocker.patch("atlas.tools.fetch.get_settings", return_value=mock_settings)
        mock_get = mocker.patch("atlas.tools.fetch.httpx.get")
        text = fetch_page_content("https://www.facebook.com/page")
        assert text == ""
        mock_get.assert_not_called()

    def test_cache_hit_skips_http(self, mocker):
        """Second call for the same URL is served from cache."""
        mock_get = self._patch(mocker)
        fetch_page_content("https://example.com/guide")
        fetch_page_content("https://example.com/guide")
        assert mock_get.call_count == 1

    def test_cache_clear_forces_refetch(self, mocker):
        """After clearing the cache, the same URL hits HTTP again."""
        mock_get = self._patch(mocker)
        fetch_page_content("https://example.com/guide")
        clear_fetch_cache()
        fetch_page_content("https://example.com/guide")
        assert mock_get.call_count == 2

    def test_trafilatura_returns_none(self, mocker):
        """If trafilatura can't extract text, return empty string."""
        self._patch(mocker, html="<html><body></body></html>")
        mocker.patch("atlas.tools.fetch.trafilatura.extract", return_value=None)
        text = fetch_page_content("https://example.com/empty")
        assert text == ""
