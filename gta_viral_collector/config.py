from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    youtube_api_key: SecretStr | None = None
    youtube_api_base_url: str = "https://www.googleapis.com/youtube/v3"
    scrapecreators_api_key: SecretStr | None = None
    scrapecreators_base_url: str = "https://api.scrapecreators.com"
    tiktok_provider: Literal["scrapecreators", "http"] = "scrapecreators"
    instagram_provider: Literal["scrapecreators", "http"] = "scrapecreators"
    tiktok_api_url: str | None = None
    tiktok_api_key: SecretStr | None = None
    tiktok_api_key_header: str = "Authorization"
    tiktok_api_key_prefix: str = "Bearer "
    instagram_api_url: str | None = None
    instagram_api_key: SecretStr | None = None
    instagram_api_key_header: str = "Authorization"
    instagram_api_key_prefix: str = "Bearer "
    request_timeout_seconds: float = Field(default=30, gt=0)
    max_pages_per_profile: int = Field(default=100, ge=1)
    max_concurrent_profiles: int = Field(default=4, ge=1)
    collection_enabled: bool = True
    creators_file: Path = Path(__file__).resolve().parents[1] / "config/creators.json"
    download_dir: Path = Path(__file__).resolve().parents[1] / "media/entrada"
    collection_state_dir: Path = Path(__file__).resolve().parents[1] / "media/coleta"
    collection_poll_seconds: float = Field(default=5, gt=0)
    download_timeout_seconds: float = Field(default=300, gt=0)
    download_cookies_file: Path | None = None
    ffmpeg_dir: Path | None = None
