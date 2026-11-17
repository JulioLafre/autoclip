import re
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit

import httpx

from gta_viral_collector.models import Platform, VideoLink

HOSTS: dict[str, Platform] = {
    "youtube.com": "youtube",
    "www.youtube.com": "youtube",
    "m.youtube.com": "youtube",
    "youtu.be": "youtube",
    "instagram.com": "instagram",
    "www.instagram.com": "instagram",
    "tiktok.com": "tiktok",
    "www.tiktok.com": "tiktok",
    "m.tiktok.com": "tiktok",
    "vm.tiktok.com": "tiktok",
    "vt.tiktok.com": "tiktok",
}
INSTAGRAM_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
INVALID_LINK = "Informe o link de um vídeo individual do YouTube, Instagram ou TikTok."
UNRESOLVED_LINK = "Não foi possível abrir o link de compartilhamento. Envie o link direto."


def instagram_media_id(shortcode: str) -> str:
    # Public shortcodes encode the numeric media ID as base 64.
    value = 0
    for char in shortcode:
        value = value * 64 + INSTAGRAM_ALPHABET.index(char)
    return str(value)


def parse_link(raw: str) -> VideoLink | tuple[Platform, str]:
    raw = raw.strip()
    if re.search(r"[\s\\\x00-\x1f\x7f]", raw):
        raise ValueError(INVALID_LINK)
    try:
        url = urlsplit(raw)
    except ValueError as exc:
        raise ValueError(INVALID_LINK) from exc
    host = url.netloc.lower()
    platform = HOSTS.get(host)
    if url.scheme not in {"http", "https"} or platform is None:
        raise ValueError(INVALID_LINK)
    path = url.path.rstrip("/")

    if platform == "youtube":
        if host == "youtu.be":
            video_id = path.removeprefix("/")
        elif path == "/watch":
            video_id = parse_qs(url.query).get("v", [""])[0]
        else:
            match = re.fullmatch(r"/(?:shorts|live|embed)/([\w-]+)", path)
            video_id = match[1] if match else ""
        if re.fullmatch(r"[a-zA-Z0-9_-]{11}", video_id):
            return VideoLink(
                platform=platform, id=video_id, url=f"https://www.youtube.com/watch?v={video_id}"
            )
    elif platform == "instagram":
        match = re.fullmatch(r"/(?:(?!share/)[\w.]+/)?(p|reels?|tv)/([a-zA-Z0-9_-]{1,32})", path)
        if match:
            kind, shortcode = match.groups()
            kind = "reel" if kind == "reels" else kind
            return VideoLink(
                platform=platform,
                id=instagram_media_id(shortcode),
                url=f"https://www.instagram.com/{kind}/{shortcode}/",
            )
        if re.fullmatch(r"/share/(?:reel/|p/)?[a-zA-Z0-9_-]+", path):
            return platform, urlunsplit(("https", host, url.path, url.query, ""))
    else:
        if host not in {"vm.tiktok.com", "vt.tiktok.com"}:
            match = re.fullmatch(r"/(@[a-zA-Z0-9_.-]+/video|share/video)/([0-9]{1,32})", path)
            if match:
                return VideoLink(
                    platform=platform, id=match[2], url=f"https://www.tiktok.com{path}"
                )
            is_share = re.fullmatch(r"/t/[a-zA-Z0-9_-]+", path)
        else:
            is_share = re.fullmatch(r"/[a-zA-Z0-9_-]+", path)
        if is_share:
            return platform, urlunsplit(("https", host, url.path, url.query, ""))
    raise ValueError(INVALID_LINK)


async def resolve_link(client: httpx.AsyncClient, link: VideoLink | tuple[Platform, str]):
    if isinstance(link, VideoLink):
        return link
    platform, url = link
    try:
        for _ in range(5):
            async with client.stream("GET", url, follow_redirects=False) as response:
                location = response.headers.get("location")
                if not response.is_redirect or not location:
                    break
            next_link = parse_link(urljoin(url, location))
            if isinstance(next_link, VideoLink):
                if next_link.platform == platform:
                    return next_link
                break
            next_platform, url = next_link
            if next_platform != platform:
                break
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as exc:
        raise ValueError(UNRESOLVED_LINK) from exc
    raise ValueError(UNRESOLVED_LINK)
