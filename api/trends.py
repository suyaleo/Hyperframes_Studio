from __future__ import annotations

import hashlib
import time
from datetime import UTC, datetime
from html import unescape
from typing import Any
from urllib.parse import quote_plus

import feedparser
import httpx

CACHE: dict[str, Any] = {"ts": 0, "items": []}
TTL = 180  # 3 min
AWESOME_AI_AGENTS_URL = "https://raw.githubusercontent.com/slavakurilyak/awesome-ai-agents/main/awesome-agents.json"
AWESOME_AI_AGENTS_REPOSITORY = "https://github.com/slavakurilyak/awesome-ai-agents"

FEEDS = {
    "rising": [
        "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko",
        "https://www.bbc.com/korean/index.xml",
    ],
    "economy": [
        "https://news.google.com/rss/search?q=%EA%B2%BD%EC%A0%9C&hl=ko&gl=KR&ceid=KR:ko",
    ],
    "it": [
        "https://news.google.com/rss/search?q=AI%20OR%20%EC%B9%B4%EB%93%9C%EB%89%B4%EC%8A%A4&hl=ko&gl=KR&ceid=KR:ko",
        "https://feeds.feedburner.com/TechCrunch",
    ],
    "ai": [
        "https://news.google.com/rss/search?q=AI%20agent%20OR%20generative%20AI&hl=ko&gl=KR&ceid=KR:ko",
        "https://feeds.feedburner.com/TechCrunch",
    ],
    "politics": [
        "https://news.google.com/rss/search?q=%EC%A0%95%EC%B9%98&hl=ko&gl=KR&ceid=KR:ko",
    ],
    "life": [
        "https://news.google.com/rss/search?q=%EB%9D%BC%EC%9D%B4%ED%94%84&hl=ko&gl=KR&ceid=KR:ko",
    ],
}


def _id(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


def _parse_feed(url: str, category: str) -> list[dict[str, Any]]:
    items = []
    try:
        # feedparser can fetch itself; httpx first for control
        with httpx.Client(timeout=12.0, follow_redirects=True) as client:
            r = client.get(url, headers={"User-Agent": "HyperframesStudio/0.1"})
            r.raise_for_status()
            parsed = feedparser.parse(r.text)
    except Exception:
        try:
            parsed = feedparser.parse(url)
        except Exception:
            return []
    for e in (parsed.entries or [])[:12]:
        title = unescape((e.get("title") or "").strip())
        if not title:
            continue
        link = e.get("link") or ""
        summary = (e.get("summary") or e.get("description") or "").strip()
        # strip tags lightly
        if "<" in summary:
            import re

            summary = re.sub(r"<[^>]+>", " ", summary)
            summary = re.sub(r"\s+", " ", summary).strip()
        summary = unescape(summary)
        image_url = ""
        media = e.get("media_content") or e.get("media_thumbnail") or []
        if media and isinstance(media[0], dict):
            image_url = str(media[0].get("url") or "")
        if not image_url:
            for enclosure in e.get("enclosures") or []:
                if str(enclosure.get("type") or "").startswith("image/"):
                    image_url = str(enclosure.get("href") or enclosure.get("url") or "")
                    break
        items.append(
            {
                "id": _id(link or title),
                "title": title[:140],
                "summary": summary[:280],
                "url": link,
                "category": category,
                "source": parsed.feed.get("title") if getattr(parsed, "feed", None) else category,
                "published": e.get("published") or e.get("updated") or "",
                "source_kind": "news",
                "image_url": image_url,
            }
        )
    return items


def _catalog_item(agent: dict[str, Any]) -> dict[str, Any] | None:
    title = str(agent.get("project") or "").strip()
    if not title:
        return None
    sources = agent.get("sources") or []
    github = next((source for source in sources if source.get("source") == "github"), None)
    primary = github or (sources[0] if sources else {})
    stars = github.get("stars") if github else None
    updated = github.get("stars_last_updated") if github else ""
    categories = [str(value) for value in (agent.get("categories") or []) if value]
    return {
        "id": _id(f"awesome-ai-agents:{title}"),
        "title": title[:140],
        "summary": str(agent.get("project_description") or "")[:280],
        "url": str(primary.get("source_url") or AWESOME_AI_AGENTS_REPOSITORY),
        "category": "ai",
        "source": "Awesome AI Agents",
        "source_kind": "catalog",
        "source_url": AWESOME_AI_AGENTS_REPOSITORY,
        "published": str(updated or ""),
        "stars": stars if isinstance(stars, int) else None,
        "open_source": bool(agent.get("project_is_open_source")),
        "tags": categories[:3],
    }


def _fetch_awesome_ai_agents() -> list[dict[str, Any]]:
    try:
        with httpx.Client(timeout=15.0, follow_redirects=True) as client:
            response = client.get(
                AWESOME_AI_AGENTS_URL,
                headers={"User-Agent": "HyperframesStudio/0.1"},
            )
            response.raise_for_status()
            agents = response.json().get("agents") or []
    except Exception:
        return []

    items = [item for agent in agents if (item := _catalog_item(agent))]
    items.sort(key=lambda item: int(item.get("stars") or 0), reverse=True)
    return items[:18]


def search_news(query: str, limit: int = 10) -> list[dict[str, Any]]:
    normalized = " ".join(str(query or "").split()).strip()
    if not normalized:
        return []
    url = f"https://news.google.com/rss/search?q={quote_plus(normalized)}&hl=ko&gl=KR&ceid=KR:ko"
    return _parse_feed(url, "research")[: max(1, min(int(limit), 20))]


def get_trends(category: str = "rising", force: bool = False) -> dict[str, Any]:
    now = time.time()
    key = category or "rising"
    cache_key = f"{key}"
    if not force and CACHE.get("key") == cache_key and now - float(CACHE.get("ts") or 0) < TTL:
        return {"ok": True, "cached": True, "updated_at": CACHE.get("updated_at"), "items": CACHE.get("items") or []}

    urls = FEEDS.get(key) or FEEDS["rising"]
    merged: list[dict[str, Any]] = []
    seen = set()
    for u in urls:
        for it in _parse_feed(u, key):
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            merged.append(it)
    if key == "ai":
        for it in _fetch_awesome_ai_agents():
            if it["id"] in seen:
                continue
            seen.add(it["id"])
            merged.append(it)
    # fallback seed if feeds fail
    if not merged:
        merged = [
            {
                "id": "seed1",
                "title": "AI 규제, 글로벌 빅테크 대응 분주",
                "summary": "미국·EU 규제 논의가 확산되며 기업 대응이 빨라지고 있습니다.",
                "url": "",
                "category": key,
                "source": "seed",
                "published": "",
            },
            {
                "id": "seed2",
                "title": "반도체 공급망 재편 가속",
                "summary": "첨단 공정 투자와 수율 경쟁이 동시에 진행 중입니다.",
                "url": "",
                "category": key,
                "source": "seed",
                "published": "",
            },
            {
                "id": "seed3",
                "title": "숏폼 정보 영상이 뉴스 소비 중심축으로",
                "summary": "짧은 카드형 브리핑 포맷의 수요가 커지고 있습니다.",
                "url": "",
                "category": key,
                "source": "seed",
                "published": "",
            },
        ]
    updated = datetime.now(UTC).isoformat()
    CACHE.update({"ts": now, "key": cache_key, "items": merged[:30], "updated_at": updated})
    return {"ok": True, "cached": False, "updated_at": updated, "items": merged[:30]}
