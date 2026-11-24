from collections.abc import Iterable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_KEYS = {"spm", "from", "ref", "source", "campaign"}


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(key, value) for key, value in parse_qsl(parts.query) if not key.lower().startswith("utm_") and key.lower() not in TRACKING_KEYS]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))


def score_source(url: str) -> tuple[str, int]:
    domain = (urlsplit(url).hostname or "").lower().removeprefix("www.")
    if domain.endswith((".gov.cn", ".edu.cn", ".gov", ".edu")):
        return "权威机构", 95
    if any(domain == name or domain.endswith("." + name) for name in ("zhaopin.com", "liepin.com", "51job.com", "zhipin.com", "bosszhipin.com")):
        return "招聘平台", 80
    if domain == "github.com" or domain.endswith(".github.com"):
        return "代码托管（未核实）", 65
    if domain:
        return "普通网页", 55
    return "无法识别", 20


def curate_sources(raw_sources: Iterable[Any]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for raw in raw_sources:
        if not isinstance(raw, dict):
            continue
        url = str(raw.get("url") or raw.get("href") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        try:
            parts = urlsplit(url)
            if not parts.hostname or parts.username or parts.password:
                continue
            normalized = normalize_url(url)
        except ValueError:
            continue
        if normalized in unique:
            continue
        tier, score = score_source(normalized)
        unique[normalized] = {
            "url": normalized,
            "title": str(raw.get("title") or raw.get("name") or "")[:300],
            "domain": urlsplit(normalized).netloc.removeprefix("www."),
            "trust_tier": tier,
            "trust_score": score,
        }
    return sorted(unique.values(), key=lambda item: (-item["trust_score"], item["domain"]))

