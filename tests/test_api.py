from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from gta_viral_collector.config import Settings
from gta_viral_collector.main import create_app


def settings(**overrides):
    return Settings(_env_file=None, collection_enabled=False, **overrides)


def profile(platform="tiktok", **overrides):
    return {"platform": platform, "username": "creator", "days": 7, "limit": 5, **overrides}


def video(video_id="one", views=10, **overrides):
    return {
        "id": video_id,
        "title": "The best moment of the entire game and how we won the final race",
        "url": f"https://www.tiktok.com/@creator/video/{video_id}",
        "views": views,
        "likes": None,
        "comments": 2,
        "published_at": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "thumbnail": "https://cdn.example.com/cover.jpg",
        "language": "en",
        "is_public": True,
        **overrides,
    }


def http_settings(**overrides):
    return settings(
        tiktok_provider="http",
        tiktok_api_url="https://provider.test/videos",
        tiktok_api_key="test-key",
        **overrides,
    )


def client_for(config, handler):
    return TestClient(create_app(config, transport=httpx.MockTransport(handler)))


def test_collects_all_pages_before_limit_and_filters_deduplicates():
    def handler(request):
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.url.params["username"] == "creator"
        assert "since" in request.url.params and "until" in request.url.params
        if "cursor" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "items": [
                        video("old", 9999, published_at="2000-01-01T00:00:00Z"),
                        video("one", 10),
                        video("private", 99999, is_public=False),
                    ],
                    "has_more": True,
                    "next_cursor": "next",
                },
            )
        assert request.url.params["cursor"] == "next"
        return httpx.Response(
            200,
            json={
                "items": [video("two", 1000), video("one", 10)],
                "has_more": False,
                "next_cursor": None,
            },
        )

    with client_for(http_settings(), handler) as client:
        response = client.post("/api/videos/viral", json={"profiles": [profile(limit=1)]})
    assert response.status_code == 200
    result = response.json()["profiles"][0]
    assert result["status"] == "complete"
    assert result["pages_fetched"] == 2
    assert result["matched_videos"] == 2
    assert [v["id"] for v in result["videos"]] == ["two"]
    assert result["videos"][0]["likes"] is None


def test_english_only_breaks_view_ties_and_unknown_language_is_explicit():
    items = [
        video("other", 100, language="pt"),
        video("english", 100, language="en-US"),
        video("top", 101, language=None, title="GTA 🔥 #gta"),
    ]
    with client_for(
        http_settings(),
        lambda _: httpx.Response(
            200,
            json={
                "items": items,
                "has_more": False,
                "next_cursor": None,
            },
        ),
    ) as client:
        videos = client.post("/api/videos/viral", json={"profiles": [profile()]}).json()[
            "profiles"
        ][0]["videos"]
    assert [v["id"] for v in videos] == ["top", "english", "other"]
    assert videos[0]["language"] == "unknown"
    assert videos[0]["language_source"] == "unknown"
    assert videos[1]["language"] == "en"


@pytest.mark.parametrize(
    "failure,code",
    [
        (httpx.Response(429), "rate_limited"),
        (httpx.Response(403), "provider_forbidden"),
        (httpx.Response(500), "provider_error"),
        (httpx.Response(200, text="not json"), "invalid_provider_response"),
        (httpx.Response(200, json={}), "invalid_provider_response"),
    ],
)
def test_keeps_first_page_on_later_failure_and_isolates_other_profiles(failure, code):
    def handler(request):
        if "cursor" in request.url.params:
            return failure
        return httpx.Response(
            200, json={"items": [video()], "has_more": True, "next_cursor": "two"}
        )

    with client_for(http_settings(), handler) as client:
        body = client.post(
            "/api/videos/viral",
            json={
                "profiles": [
                    profile(),
                    profile("youtube"),
                ]
            },
        ).json()
    assert body["complete"] is False
    first, second = body["profiles"]
    assert first["status"] == "partial" and len(first["videos"]) == 1
    assert first["errors"][0]["code"] == code
    assert second["status"] == "error"
    assert second["errors"][0]["code"] == "not_configured"
    assert second["videos"] == []


def test_timeout_is_an_individual_error_without_fabricated_videos():
    def handler(request):
        raise httpx.ReadTimeout("timeout", request=request)

    with client_for(http_settings(), handler) as client:
        result = client.post("/api/videos/viral", json={"profiles": [profile()]}).json()[
            "profiles"
        ][0]
    assert result["status"] == "error"
    assert result["errors"][0]["code"] == "provider_timeout"
    assert result["videos"] == []


@pytest.mark.parametrize(
    "page_cap,expected_pages,expected_code",
    [
        (10, 2, "pagination_loop"),
        (1, 1, "page_limit_reached"),
    ],
)
def test_infinite_pagination_and_page_budget_are_partial(page_cap, expected_pages, expected_code):
    with client_for(
        http_settings(max_pages_per_profile=page_cap),
        lambda _: httpx.Response(
            200,
            json={"items": [video()], "has_more": True, "next_cursor": "same"},
        ),
    ) as client:
        result = client.post("/api/videos/viral", json={"profiles": [profile()]}).json()[
            "profiles"
        ][0]
    assert result["status"] == "partial"
    assert result["pages_fetched"] == expected_pages
    assert result["errors"][0]["code"] == expected_code


def test_empty_page_with_cursor_does_not_end_collection():
    def handler(request):
        if "cursor" not in request.url.params:
            return httpx.Response(200, json={"items": [], "has_more": True, "next_cursor": "2"})
        return httpx.Response(
            200, json={"items": [video()], "has_more": False, "next_cursor": None}
        )

    with client_for(http_settings(), handler) as client:
        result = client.post("/api/videos/viral", json={"profiles": [profile()]}).json()[
            "profiles"
        ][0]
    assert result["status"] == "complete" and len(result["videos"]) == 1


def test_bad_record_does_not_discard_good_record_and_missing_views_marks_partial():
    with client_for(
        http_settings(),
        lambda _: httpx.Response(
            200,
            json={
                "items": [
                    video("good"),
                    video("bad", published_at="invalid"),
                    video("unknown", None),
                ],
                "has_more": False,
                "next_cursor": None,
            },
        ),
    ) as client:
        result = client.post("/api/videos/viral", json={"profiles": [profile()]}).json()[
            "profiles"
        ][0]
    assert result["status"] == "partial"
    assert [v["id"] for v in result["videos"]] == ["good", "unknown"]
    assert result["videos"][1]["views"] is None
    assert {e["code"] for e in result["errors"]} == {"invalid_video", "missing_views"}


def test_provider_explicitly_incomplete_and_missing_cursor_are_not_complete():
    with client_for(
        http_settings(),
        lambda _: httpx.Response(
            200,
            json={
                "items": [video()],
                "has_more": True,
                "next_cursor": None,
                "complete": False,
            },
        ),
    ) as client:
        result = client.post("/api/videos/viral", json={"profiles": [profile()]}).json()[
            "profiles"
        ][0]
    assert result["status"] == "partial" and len(result["videos"]) == 1
    assert "missing_cursor" in {e["code"] for e in result["errors"]}


def test_empty_feed_is_complete_but_missing_configuration_is_not():
    with client_for(
        http_settings(),
        lambda _: httpx.Response(
            200,
            json={
                "items": [],
                "has_more": False,
                "next_cursor": None,
            },
        ),
    ) as client:
        result = client.post("/api/videos/viral", json={"profiles": [profile()]}).json()
        assert result["complete"] is True
        assert result["profiles"][0]["videos"] == []
        assert client.get("/docs").status_code == 200
        assert "post" in client.get("/openapi.json").json()["paths"]["/api/videos/viral"]


@pytest.mark.parametrize(
    "payload",
    [
        {"profiles": []},
        {"profiles": [profile(days=0)]},
        {"profiles": [profile(limit=0)]},
        {"profiles": [profile(username="@")]},
        {"profiles": [profile(platform="unknown")]},
    ],
)
def test_rejects_invalid_request(payload):
    with client_for(settings(), lambda _: pytest.fail("No HTTP request expected")) as client:
        assert client.post("/api/videos/viral", json=payload).status_code == 422
