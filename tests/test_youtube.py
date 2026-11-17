import httpx
from test_api import client_for, profile, settings


def yt_video(video_id, **overrides):
    return {
        "id": video_id,
        "snippet": {
            "title": "This is the most exciting race we have ever played in the city",
            "publishedAt": "2026-11-15T12:00:00Z",
            "defaultAudioLanguage": "en-US",
            "thumbnails": {"high": {"url": "https://cdn.example.com/yt.jpg"}},
        },
        "statistics": {"viewCount": "100", "likeCount": "5"},
        "status": {"privacyStatus": "public"},
        **overrides,
    }


def test_youtube_uses_uploads_pagination_and_batched_public_statistics():
    def handler(request):
        params = request.url.params
        assert params["key"] == "google-key"
        if request.url.path.endswith("/channels"):
            assert params["forHandle"] == "@creator"
            return httpx.Response(
                200,
                json={
                    "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUcreator"}}}]
                },
            )
        if request.url.path.endswith("/playlistItems"):
            assert params["playlistId"] == "UUcreator"
            video_id = "two" if "pageToken" in params else "one"
            data = {"items": [{"contentDetails": {"videoId": video_id}}]}
            if video_id == "one":
                data["nextPageToken"] = "next"
            return httpx.Response(200, json=data)
        assert request.url.path.endswith("/videos")
        assert "statistics" in params["part"] and "status" in params["part"]
        item = yt_video(params["id"])
        if params["id"] == "two":
            item["statistics"]["viewCount"] = "1000"
        return httpx.Response(200, json={"items": [item]})

    with client_for(settings(youtube_api_key="google-key"), handler) as client:
        result = client.post(
            "/api/videos/viral",
            json={
                "profiles": [
                    profile("youtube", username="@creator", days=3650, limit=1),
                ]
            },
        ).json()["profiles"][0]
    assert result["status"] == "complete"
    assert result["pages_fetched"] == 2
    assert result["videos"][0]["id"] == "two"
    assert result["videos"][0]["url"] == "https://www.youtube.com/watch?v=two"
    assert result["videos"][0]["comments"] is None


def test_youtube_drops_non_public_videos_and_reports_quota_error():
    def handler(request):
        if request.url.path.endswith("/channels"):
            return httpx.Response(
                200,
                json={
                    "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUcreator"}}}]
                },
            )
        if request.url.path.endswith("/playlistItems"):
            if "pageToken" in request.url.params:
                return httpx.Response(
                    403, json={"error": {"errors": [{"reason": "quotaExceeded"}]}}
                )
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"contentDetails": {"videoId": "public"}},
                        {"contentDetails": {"videoId": "unlisted"}},
                    ],
                    "nextPageToken": "next",
                },
            )
        return httpx.Response(
            200,
            json={
                "items": [
                    yt_video("public"),
                    yt_video("unlisted", status={"privacyStatus": "unlisted"}),
                ]
            },
        )

    with client_for(settings(youtube_api_key="key"), handler) as client:
        result = client.post(
            "/api/videos/viral",
            json={
                "profiles": [
                    profile("youtube", days=3650),
                ]
            },
        ).json()["profiles"][0]
    assert [v["id"] for v in result["videos"]] == ["public"]
    assert result["status"] == "partial"
    assert result["errors"][0]["code"] == "quota_exceeded"


def test_youtube_keeps_valid_uploads_when_one_playlist_record_has_no_id():
    def handler(request):
        if request.url.path.endswith("/channels"):
            return httpx.Response(
                200,
                json={
                    "items": [{"contentDetails": {"relatedPlaylists": {"uploads": "UUcreator"}}}]
                },
            )
        if request.url.path.endswith("/playlistItems"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {"contentDetails": {"videoId": "good"}},
                        {},
                    ]
                },
            )
        assert request.url.params["id"] == "good"
        return httpx.Response(200, json={"items": [yt_video("good")]})

    with client_for(settings(youtube_api_key="key"), handler) as client:
        result = client.post(
            "/api/videos/viral",
            json={
                "profiles": [
                    profile("youtube", days=3650),
                ]
            },
        ).json()["profiles"][0]
    assert result["status"] == "partial"
    assert [v["id"] for v in result["videos"]] == ["good"]
    assert result["errors"][0]["code"] == "invalid_video"
