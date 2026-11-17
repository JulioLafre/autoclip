import re
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, HttpUrl, field_validator

Platform = Literal["youtube", "tiktok", "instagram"]
Count = Annotated[int, Field(ge=0)]


class ProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    platform: Platform
    username: str = Field(min_length=1, max_length=100)
    days: int = Field(ge=1, le=36500, strict=True)
    limit: int = Field(default=10, ge=1, le=1000, strict=True)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip().removeprefix("@")
        if not value or not re.fullmatch(r"[\w.\-·]+", value):
            raise ValueError("Informe somente o username, handle ou ID do canal, sem URL.")
        return value


class ViralRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "profiles": [
                    {"platform": "youtube", "username": "RockstarGames", "days": 30, "limit": 5},
                    {"platform": "tiktok", "username": "rockstargames", "days": 7, "limit": 10},
                    {"platform": "instagram", "username": "rockstargames", "days": 14, "limit": 5},
                ]
            }
        },
    )

    profiles: list[ProfileRequest] = Field(min_length=1, max_length=100)


class VideoLink(BaseModel):
    id: str = Field(min_length=1)
    platform: Platform
    url: HttpUrl


class Video(VideoLink):
    username: str
    title: str | None = None
    views: Count | None = None
    likes: Count | None = None
    comments: Count | None = None
    published_at: AwareDatetime
    thumbnail: HttpUrl | None = None
    language: str = "unknown"
    language_source: Literal["provider", "text", "unknown"] = "unknown"


class Issue(BaseModel):
    code: str
    message: str


class ProfileResult(BaseModel):
    platform: Platform
    username: str
    days: int
    limit: int
    since: AwareDatetime
    until: AwareDatetime
    status: Literal["complete", "partial", "error"]
    complete: bool
    pages_fetched: int
    matched_videos: int
    videos: list[Video]
    errors: list[Issue] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ViralResponse(BaseModel):
    collected_at: AwareDatetime
    complete: bool
    profiles: list[ProfileResult]
