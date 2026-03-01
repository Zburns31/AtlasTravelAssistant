"""Tests for the search tools (``atlas.tools.search``)."""

from __future__ import annotations

import httpx
import pytest

from atlas.tools.search import (
    _get_api_key,
    _serper_request,
    search_places,
    search_web,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

SERPER_SEARCH_RESPONSE = {
    "organic": [
        {
            "title": "Top 10 Temples in Kyoto",
            "link": "https://example.com/kyoto-temples",
            "snippet": "Discover the most beautiful temples in Kyoto...",
            "position": 1,
        },
        {
            "title": "Kyoto Travel Guide 2025",
            "link": "https://example.com/kyoto-guide",
            "snippet": "Everything you need to know about visiting Kyoto...",
            "position": 2,
        },
    ],
    "knowledgeGraph": {
        "title": "Kyoto",
        "type": "City in Japan",
        "description": "Kyoto is a city on the island of Honshu...",
        "website": "https://kyoto.travel/en",
        "imageUrl": "https://example.com/kyoto.jpg",
        "attributes": {"Population": "1.46 million", "Country": "Japan"},
    },
}

SERPER_PLACES_RESPONSE = {
    "places": [
        {
            "title": "Fushimi Inari Taisha",
            "address": "68 Fukakusa Yabunouchicho, Fushimi Ward, Kyoto",
            "latitude": 34.9671,
            "longitude": 135.7727,
            "rating": 4.7,
            "ratingCount": 82000,
            "category": "Shinto shrine",
            "phoneNumber": "+81-75-641-7331",
            "website": "https://inari.jp/en/",
            "cid": "12345678901234567",
        },
        {
            "title": "Kinkaku-ji",
            "address": "1 Kinkakujicho, Kita Ward, Kyoto",
            "latitude": 35.0394,
            "longitude": 135.7292,
            "rating": 4.6,
            "ratingCount": 54000,
            "category": "Buddhist temple",
            "phoneNumber": "+81-75-461-0013",
            "website": "https://www.shokoku-ji.jp/kinkakuji/",
            "cid": "98765432109876543",
        },
    ]
}


def _mock_serper_post(search_json=None, places_json=None):
    """Return a side_effect function that routes by Serper endpoint URL."""

    def _side_effect(url, **kwargs):
        resp = httpx.Response(200, request=httpx.Request("POST", url))
        if "/search" in url:
            resp._content = httpx._content.json_dumps(
                SERPER_SEARCH_RESPONSE if search_json is None else search_json
            )
        elif "/places" in url:
            resp._content = httpx._content.json_dumps(
                SERPER_PLACES_RESPONSE if places_json is None else places_json
            )
        else:
            raise ValueError(f"Unexpected URL: {url}")
        return resp

    return _side_effect


# ── Helper tests ─────────────────────────────────────────────────────────────


class TestGetApiKey:
    def test_raises_when_not_set(self, mocker) -> None:
        mock_settings = mocker.MagicMock()
        mock_settings.serper_api_key = ""
        mocker.patch("atlas.tools.search.get_settings", return_value=mock_settings)
        with pytest.raises(ValueError, match="SERPER_API_KEY is not set"):
            _get_api_key()

    def test_returns_key_when_set(self, mocker) -> None:
        mock_settings = mocker.MagicMock()
        mock_settings.serper_api_key = "test-serper-key"
        mocker.patch("atlas.tools.search.get_settings", return_value=mock_settings)
        assert _get_api_key() == "test-serper-key"


class TestSerperRequest:
    def test_sends_post_with_api_key(self, mocker) -> None:
        mock_settings = mocker.MagicMock()
        mock_settings.serper_api_key = "test-serper-key"
        mocker.patch("atlas.tools.search.get_settings", return_value=mock_settings)
        mock_post = mocker.patch(
            "atlas.tools.search.httpx.post",
            side_effect=_mock_serper_post(),
        )
        _serper_request("https://google.serper.dev/search", {"q": "test"})
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        assert call_kwargs.kwargs["headers"]["X-API-KEY"] == "test-serper-key"
        assert call_kwargs.kwargs["json"] == {"q": "test"}


# ── search_web tests ─────────────────────────────────────────────────────────


class TestSearchWeb:
    def _patch(self, mocker, search_json=None):
        mock_settings = mocker.MagicMock()
        mock_settings.serper_api_key = "test-key"
        mocker.patch("atlas.tools.search.get_settings", return_value=mock_settings)
        return mocker.patch(
            "atlas.tools.search.httpx.post",
            side_effect=_mock_serper_post(search_json=search_json),
        )

    def test_happy_path(self, mocker) -> None:
        self._patch(mocker)
        result = search_web.invoke({"query": "temples in Kyoto"})
        assert result["query"] == "temples in Kyoto"
        assert len(result["results"]) == 2
        assert result["results"][0]["title"] == "Top 10 Temples in Kyoto"
        assert "link" in result["results"][0]
        assert "snippet" in result["results"][0]

    def test_knowledge_graph_included(self, mocker) -> None:
        self._patch(mocker)
        result = search_web.invoke({"query": "Kyoto"})
        assert "knowledgeGraph" in result
        assert result["knowledgeGraph"]["title"] == "Kyoto"
        assert result["knowledgeGraph"]["type"] == "City in Japan"

    def test_no_knowledge_graph(self, mocker) -> None:
        self._patch(mocker, search_json={"organic": []})
        result = search_web.invoke({"query": "obscure query"})
        assert "knowledgeGraph" not in result

    def test_num_results_clamped(self, mocker) -> None:
        mock_post = self._patch(mocker)
        search_web.invoke({"query": "test", "num_results": 50})
        payload = mock_post.call_args.kwargs["json"]
        assert payload["num"] == 10

    def test_missing_api_key_returns_error(self, mocker) -> None:
        mock_settings = mocker.MagicMock()
        mock_settings.serper_api_key = ""
        mocker.patch("atlas.tools.search.get_settings", return_value=mock_settings)
        result = search_web.invoke({"query": "test"})
        assert "error" in result
        assert "SERPER_API_KEY" in result["error"]

    def test_http_error_returns_error(self, mocker) -> None:
        mock_settings = mocker.MagicMock()
        mock_settings.serper_api_key = "test-key"
        mocker.patch("atlas.tools.search.get_settings", return_value=mock_settings)

        def _raise(url, **kw):
            resp = httpx.Response(
                429, request=httpx.Request("POST", url), content=b"Rate limited"
            )
            resp.raise_for_status()

        mocker.patch("atlas.tools.search.httpx.post", side_effect=_raise)
        result = search_web.invoke({"query": "test"})
        assert "error" in result
        assert "Search API" in result["error"]


# ── search_places tests ──────────────────────────────────────────────────────


class TestSearchPlaces:
    def _patch(self, mocker, places_json=None):
        mock_settings = mocker.MagicMock()
        mock_settings.serper_api_key = "test-key"
        mocker.patch("atlas.tools.search.get_settings", return_value=mock_settings)
        return mocker.patch(
            "atlas.tools.search.httpx.post",
            side_effect=_mock_serper_post(places_json=places_json),
        )

    def test_happy_path(self, mocker) -> None:
        self._patch(mocker)
        result = search_places.invoke({"query": "temples in Kyoto"})
        assert result["query"] == "temples in Kyoto"
        assert len(result["places"]) == 2
        place = result["places"][0]
        assert place["title"] == "Fushimi Inari Taisha"
        assert place["latitude"] == pytest.approx(34.9671)
        assert place["longitude"] == pytest.approx(135.7727)
        assert place["rating"] == 4.7
        assert place["review_count"] == 82000
        assert place["category"] == "Shinto shrine"

    def test_includes_website_and_phone(self, mocker) -> None:
        self._patch(mocker)
        result = search_places.invoke({"query": "temples in Kyoto"})
        place = result["places"][0]
        assert place["website"] == "https://inari.jp/en/"
        assert place["phone"] == "+81-75-641-7331"

    def test_empty_results(self, mocker) -> None:
        self._patch(mocker, places_json={"places": []})
        result = search_places.invoke({"query": "nothing here"})
        assert result["places"] == []

    def test_missing_api_key_returns_error(self, mocker) -> None:
        mock_settings = mocker.MagicMock()
        mock_settings.serper_api_key = ""
        mocker.patch("atlas.tools.search.get_settings", return_value=mock_settings)
        result = search_places.invoke({"query": "test"})
        assert "error" in result
        assert "SERPER_API_KEY" in result["error"]

    def test_http_error_returns_error(self, mocker) -> None:
        mock_settings = mocker.MagicMock()
        mock_settings.serper_api_key = "test-key"
        mocker.patch("atlas.tools.search.get_settings", return_value=mock_settings)

        def _raise(url, **kw):
            resp = httpx.Response(
                500, request=httpx.Request("POST", url), content=b"Server Error"
            )
            resp.raise_for_status()

        mocker.patch("atlas.tools.search.httpx.post", side_effect=_raise)
        result = search_places.invoke({"query": "test"})
        assert "error" in result
        assert "Places API" in result["error"]
