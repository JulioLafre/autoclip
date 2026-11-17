import re
from functools import lru_cache

from langdetect import DetectorFactory, LangDetectException, detect_langs

DetectorFactory.seed = 0


@lru_cache(maxsize=4096)
def estimate_language(text: str | None, provider_language: str | None = None) -> tuple[str, str]:
    """Metadata has priority; uncertain, short or hashtag-only text stays unknown."""
    if provider_language:
        code = provider_language.strip().lower().replace("_", "-").split("-")[0]
        if re.fullmatch(r"[a-z]{2,3}", code) and code not in {"und", "unk", "zxx", "mul"}:
            return code, "provider"
    clean = re.sub(r"https?://\S+|[#@]\S+", " ", text or "")
    if len(re.findall(r"[^\W\d_]", clean)) < 25:
        return "unknown", "unknown"
    try:
        candidates = detect_langs(clean)
    except LangDetectException:
        return "unknown", "unknown"
    if candidates and candidates[0].prob >= 0.90:
        return candidates[0].lang, "text"
    return "unknown", "unknown"
