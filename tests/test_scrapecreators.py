from datetime import UTC, datetime

import httpx
import pytest
from test_api import client_for, profile, settings


def test_tiktok_maps_real_provider_fields_skips_slideshows_and_follows_max_cursor():
    def handler(request):
        assert request.url.path == "/v3/tiktok/profile/videos"
        assert request.headers["x-api-key"] == "scrape-key"
        assert request.url.params["include_pinned"] == "true"
        item = {
            "aweme_id": "123",
            "desc": "GTA",
            "create_time": int(datetime.now(UTC).timestamp()),
            "image_post_info": None,
            "author": None,
            "status": None,
            "statistics": {"play_count": 0, "digg_count": 8, "comment_count": 3},
            "video": {"cover": {"url_list": ["https://cdn.example.com/tiktok.jpg"]}},
        }
        if "max_cursor" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "aweme_list": [
                        {"aweme_id": "photo", "image_post_info": {"images": [{}]}},
                        item,
                    ],
                    "has_more": 1,
                    "max_cursor": 123456,
                },
            )
        assert request.url.params["max_cursor"] == "123456"
        return httpx.Response(200, json={"success": True, "aweme_list": [], "has_more": 0})

    with client_for(settings(scrapecreators_api_key="scrape-key"), handler) as client:
        result = client.post("/api/videos/viral", json={"profiles": [profile()]}).json()[
            "profiles"
        ][0]
    assert result["status"] == "complete"
    assert len(result["videos"]) == 1
    assert result["videos"][0]["views"] == 0
    assert result["videos"][0]["likes"] == 8
    assert result["videos"][0]["language"] == "unknown"
    assert result["warnings"]


def test_instagram_maps_posts_caption_metrics_and_video_only():
    def handler(request):
        assert request.url.path == "/v2/instagram/user/posts"
        return httpx.Response(
            200,
            json={
                "success": True,
                "status": "ok",
                "user": {
                    "is_private": False,
                },
                "items": [
                    {
                        "id": "123",
                        "code": "ABC",
                        "media_type": 2,
                        "taken_at": int(datetime.now(UTC).timestamp()),
                        "play_count": 200,
                        "caption": {
                            "text": "We won the final race and this is how we did it together"
                        },
                        "like_count": 4,
                        "comment_count": 2,
                        "image_versions2": {
                            "candidates": [{"url": "https://cdn.example.com/ig.jpg"}]
                        },
                    },
                    {"media_type": 1},
                ],
                "more_available": False,
            },
        )

    with client_for(settings(scrapecreators_api_key="key"), handler) as client:
        result = client.post("/api/videos/viral", json={"profiles": [profile("instagram")]}).json()[
            "profiles"
        ][0]
    assert result["status"] == "complete"
    assert len(result["videos"]) == 1
    assert result["videos"][0]["url"] == "https://www.instagram.com/p/ABC/"
    assert result["videos"][0]["views"] == 200
    assert result["videos"][0]["language"] == "en"


def test_provider_success_false_is_error_even_with_http_200():
    with client_for(
        settings(scrapecreators_api_key="key"),
        lambda _: httpx.Response(
            200,
            json={"success": False, "message": "upstream failed"},
        ),
    ) as client:
        result = client.post("/api/videos/viral", json={"profiles": [profile()]}).json()[
            "profiles"
        ][0]
    assert result["status"] == "error"
    assert result["errors"][0]["code"] == "provider_error"
    assert result["videos"] == []


def test_instagram_paginates_past_old_pinned_post_and_rejects_private_profile():
    def handler(request):
        if request.url.params["handle"] == "private":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "user": {"is_private": True},
                    "items": [],
                    "more_available": False,
                },
            )
        post = {
            "id": "old",
            "code": "OLD",
            "media_type": 2,
            "taken_at": 946684800,
            "play_count": 99999,
        }
        if "next_max_id" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "items": [post],
                    "more_available": True,
                    "next_max_id": "page2",
                },
            )
        assert request.url.params["next_max_id"] == "page2"
        post.update(
            id="new", code="NEW", taken_at=int(datetime.now(UTC).timestamp()), play_count=42
        )
        return httpx.Response(200, json={"success": True, "items": [post], "more_available": False})

    with client_for(settings(scrapecreators_api_key="key"), handler) as client:
        first, second = client.post(
            "/api/videos/viral",
            json={
                "profiles": [
                    profile("instagram"),
                    profile("instagram", username="private"),
                ]
            },
        ).json()["profiles"]
    assert first["status"] == "complete" and first["videos"][0]["id"] == "new"
    assert second["status"] == "error" and second["errors"][0]["code"] == "private_profile"


@pytest.mark.parametrize("platform", ["tiktok", "instagram"])
def test_null_identifiers_never_produce_invented_publication_urls(platform):
    now = int(datetime.now(UTC).timestamp())
    payload = (
        {
            "success": True,
            "aweme_list": [
                {"aweme_id": None, "create_time": now, "statistics": {"play_count": 42}}
            ],
            "has_more": 0,
        }
        if platform == "tiktok"
        else {
            "success": True,
            "items": [
                {"id": None, "code": "ABC", "media_type": 2, "taken_at": now, "play_count": 42},
                {"id": "123", "code": None, "media_type": 2, "taken_at": now, "play_count": 42},
            ],
            "more_available": False,
        }
    )
    with client_for(
        settings(scrapecreators_api_key="key"),
        lambda _: httpx.Response(
            200,
            json=payload,
        ),
    ) as client:
        result = client.post("/api/videos/viral", json={"profiles": [profile(platform)]}).json()[
            "profiles"
        ][0]
    assert result["status"] == "partial"
    assert result["videos"] == []
    assert result["errors"][0]["code"] == "invalid_video"
