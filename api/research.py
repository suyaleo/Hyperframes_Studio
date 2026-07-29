from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from api.briefing import BriefingMode, get_briefing_preset
from api.settings import RESEARCH_DIR
from api.trends import get_trends, search_news

SAFE_ID = re.compile(r"^[a-f0-9]{12}$")
QUERY_TOKEN = re.compile(r"[0-9A-Za-z가-힣]+")


def _clean(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split()).strip()[:limit]


def _evidence_id(item: dict[str, Any]) -> str:
    identity = _clean(item.get("url") or item.get("title"), 1000)
    return f"ev-{hashlib.sha1(identity.encode('utf-8')).hexdigest()[:10]}"


def _query_variants(query: str, category: str, breadth: int) -> list[str]:
    original = _clean(query, 220)
    without_source = re.sub(r"\s+[-–—|]\s+[^-–—|]{2,40}$", "", original).strip()
    tokens = QUERY_TOKEN.findall(without_source)
    compact = " ".join(tokens[: min(6, len(tokens))])
    variants = [original, without_source]
    if category == "ai":
        topic_tokens = [
            token
            for token in tokens
            if token.casefold() not in {"ai", "agent", "agents", "에이전트", "인공지능"}
        ][:3]
        variants.extend(
            [
                "AI 에이전트 OR 생성형 AI 최신 동향",
                " ".join([*topic_tokens, "AI 에이전트"]).strip(),
            ]
        )
    variants.append(compact)
    unique: list[str] = []
    for variant in variants:
        if variant and variant.casefold() not in {value.casefold() for value in unique}:
            unique.append(variant)
    return unique[:breadth]


def _expanded_news_search(query: str, category: str, limit: int, breadth: int) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    per_query = max(8, min(limit, 16))
    for variant in _query_variants(query, category, breadth):
        for item in search_news(variant, limit=per_query):
            identity = _clean(item.get("url") or item.get("title"), 1000)
            if not identity or identity in seen:
                continue
            seen.add(identity)
            merged.append(item)
    return merged


def evidence_from_item(item: dict[str, Any], retrieved_at: str) -> dict[str, Any] | None:
    title = _clean(item.get("title"), 180)
    if not title:
        return None
    url = _clean(item.get("url"), 1000)
    source_url = _clean(item.get("source_url") or url, 1000)
    image_url = _clean(item.get("image_url"), 1000)
    return {
        "id": _evidence_id(item),
        "title": title,
        "url": url,
        "source": _clean(item.get("source") or "Unknown source", 120),
        "source_kind": _clean(item.get("source_kind") or "news", 40),
        "source_url": source_url,
        "published_at": _clean(item.get("published"), 100),
        "retrieved_at": retrieved_at,
        "excerpt": _clean(item.get("summary"), 700),
        "image": {
            "url": image_url,
            "license_status": "unknown" if image_url else "not-provided",
        },
        "metadata": {
            "stars": item.get("stars") if isinstance(item.get("stars"), int) else None,
            "open_source": item.get("open_source") if isinstance(item.get("open_source"), bool) else None,
            "tags": [_clean(tag, 60) for tag in (item.get("tags") or [])[:5]],
        },
    }


def build_research_bundle(
    query: str,
    *,
    category: str = "rising",
    selected_issue: dict[str, Any] | None = None,
    max_sources: int | None = None,
    briefing_mode: BriefingMode = "standard",
    candidates: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    normalized_query = _clean(query or (selected_issue or {}).get("title"), 220)
    if not normalized_query:
        raise ValueError("research query is required")
    retrieved_at = datetime.now(UTC).isoformat()
    preset = get_briefing_preset(briefing_mode)
    requested_sources = max_sources if max_sources is not None else preset["max_sources"]
    limit = max(3, min(int(requested_sources), 24))
    items: list[dict[str, Any]] = []
    search_breadth = {"short": 1, "standard": 3, "deep": 4}[briefing_mode]
    if selected_issue:
        items.append(selected_issue)
    if candidates is not None:
        items.extend(candidates)
    elif category == "ai":
        news_items = _expanded_news_search(normalized_query, category, limit + 2, search_breadth)
        catalog_items = [item for item in (get_trends("ai").get("items") or []) if item.get("source_kind") == "catalog"]
        reserved = min(2, len(catalog_items))
        news_slots = max(1, limit - len(items) - reserved)
        items.extend(news_items[:news_slots])
        items.extend(catalog_items[:reserved])
        items.extend(news_items[news_slots:])
    else:
        items.extend(_expanded_news_search(normalized_query, category, limit + 2, search_breadth))

    evidence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        record = evidence_from_item(item, retrieved_at)
        if not record or record["id"] in seen:
            continue
        seen.add(record["id"])
        evidence.append(record)
        if len(evidence) >= limit:
            break

    providers: dict[str, dict[str, Any]] = {}
    for record in evidence:
        name = record["source"]
        current = providers.setdefault(
            name,
            {
                "name": name,
                "kind": record["source_kind"],
                "status": "ready",
                "items": 0,
            },
        )
        current["items"] += 1

    warnings: list[str] = []
    if len(evidence) < 2:
        warnings.append("독립된 근거가 충분하지 않습니다. 생성 전에 출처를 추가로 확인하세요.")
    if any(record["image"]["url"] and record["image"]["license_status"] == "unknown" for record in evidence):
        warnings.append("이미지 후보의 재사용 라이선스가 확인되지 않았습니다.")

    bundle_id = hashlib.sha1(f"{normalized_query}:{retrieved_at}".encode()).hexdigest()[:12]
    return {
        "id": bundle_id,
        "query": normalized_query,
        "category": category,
        "mode": "issue" if selected_issue else "keyword",
        "briefing_mode": briefing_mode,
        "requested_sources": limit,
        "status": "complete" if len(evidence) >= 2 else "partial",
        "created_at": retrieved_at,
        "evidence": evidence,
        "providers": list(providers.values()),
        "warnings": warnings,
    }


def save_research_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    bundle_id = str(bundle.get("id") or "")
    if not SAFE_ID.fullmatch(bundle_id):
        raise ValueError("invalid research bundle id")
    path = RESEARCH_DIR / f"{bundle_id}.json"
    path.write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding="utf-8")
    return bundle


def collect_research(
    query: str,
    *,
    category: str = "rising",
    selected_issue: dict[str, Any] | None = None,
    max_sources: int | None = None,
    briefing_mode: BriefingMode = "standard",
) -> dict[str, Any]:
    bundle = build_research_bundle(
        query,
        category=category,
        selected_issue=selected_issue,
        max_sources=max_sources,
        briefing_mode=briefing_mode,
    )
    return save_research_bundle(bundle)


def get_research_bundle(bundle_id: str) -> dict[str, Any] | None:
    if not SAFE_ID.fullmatch(str(bundle_id or "")):
        return None
    path = RESEARCH_DIR / f"{bundle_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_research_bundles() -> list[dict[str, Any]]:
    bundles: list[dict[str, Any]] = []
    for path in sorted(RESEARCH_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True):
        try:
            bundle = json.loads(path.read_text(encoding="utf-8"))
            bundles.append(
                {
                    "id": bundle.get("id"),
                    "query": bundle.get("query"),
                    "status": bundle.get("status"),
                    "created_at": bundle.get("created_at"),
                    "evidence_count": len(bundle.get("evidence") or []),
                }
            )
        except (OSError, json.JSONDecodeError):
            continue
    return bundles[:50]
