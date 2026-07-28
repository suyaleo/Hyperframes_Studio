from __future__ import annotations
import hashlib, time
from datetime import datetime, timezone
from typing import Any
import feedparser
import httpx

CACHE: dict[str, Any] = {"ts": 0, "items": []}
TTL = 180  # 3 min

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
            r = client.get(url, headers={"User-Agent": "LeoCardMotion/0.1"})
            r.raise_for_status()
            parsed = feedparser.parse(r.text)
    except Exception:
        try:
            parsed = feedparser.parse(url)
        except Exception:
            return []
    for e in (parsed.entries or [])[:12]:
        title = (e.get("title") or "").strip()
        if not title:
            continue
        link = e.get("link") or ""
        summary = (e.get("summary") or e.get("description") or "").strip()
        # strip tags lightly
        if "<" in summary:
            import re
            summary = re.sub(r"<[^>]+>", " ", summary)
            summary = re.sub(r"\s+", " ", summary).strip()
        items.append({
            "id": _id(link or title),
            "title": title[:140],
            "summary": summary[:280],
            "url": link,
            "category": category,
            "source": parsed.feed.get("title") if getattr(parsed, "feed", None) else category,
            "published": e.get("published") or e.get("updated") or "",
        })
    return items

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
    # fallback seed if feeds fail
    if not merged:
        merged = [
            {"id": "seed1", "title": "AI 규제, 글로벌 빅테크 대응 분주", "summary": "미국·EU 규제 논의가 확산되며 기업 대응이 빨라지고 있습니다.", "url": "", "category": key, "source": "seed", "published": ""},
            {"id": "seed2", "title": "반도체 공급망 재편 가속", "summary": "첨단 공정 투자와 수율 경쟁이 동시에 진행 중입니다.", "url": "", "category": key, "source": "seed", "published": ""},
            {"id": "seed3", "title": "숏폼 정보 영상이 뉴스 소비 중심축으로", "summary": "짧은 카드형 브리핑 포맷의 수요가 커지고 있습니다.", "url": "", "category": key, "source": "seed", "published": ""},
        ]
    updated = datetime.now(timezone.utc).isoformat()
    CACHE.update({"ts": now, "key": cache_key, "items": merged[:30], "updated_at": updated})
    return {"ok": True, "cached": False, "updated_at": updated, "items": merged[:30]}
