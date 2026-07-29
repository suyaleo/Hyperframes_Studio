from api import research


def _candidate(index: int, *, image: bool = False) -> dict:
    return {
        "title": f"근거 {index}",
        "summary": f"검증 가능한 설명 {index}",
        "url": f"https://example.com/{index}",
        "source": f"Source {index}",
        "source_kind": "news",
        "published": "2026-07-29",
        "image_url": f"https://example.com/{index}.jpg" if image else "",
    }


def test_research_bundle_preserves_provenance_and_image_warning() -> None:
    bundle = research.build_research_bundle(
        "AI 영상 제작",
        category="it",
        max_sources=4,
        candidates=[_candidate(1, image=True), _candidate(2)],
    )

    assert bundle["status"] == "complete"
    assert bundle["mode"] == "keyword"
    assert len(bundle["evidence"]) == 2
    assert bundle["evidence"][0]["url"] == "https://example.com/1"
    assert bundle["evidence"][0]["image"]["license_status"] == "unknown"
    assert bundle["providers"][0]["status"] == "ready"
    assert any("라이선스" in warning for warning in bundle["warnings"])


def test_research_bundle_storage_rejects_unsafe_ids(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(research, "RESEARCH_DIR", tmp_path)
    bundle = research.build_research_bundle("테스트", candidates=[_candidate(1), _candidate(2)])

    research.save_research_bundle(bundle)

    assert research.get_research_bundle(bundle["id"])["query"] == "테스트"
    assert research.get_research_bundle("../unsafe") is None
    assert research.list_research_bundles()[0]["evidence_count"] == 2


def test_ai_research_reserves_catalog_evidence(monkeypatch) -> None:
    news = [_candidate(index) for index in range(1, 9)]
    catalog = [
        {
            **_candidate(20 + index),
            "source": "Awesome AI Agents",
            "source_kind": "catalog",
        }
        for index in range(2)
    ]
    monkeypatch.setattr(research, "search_news", lambda *_args, **_kwargs: news)
    monkeypatch.setattr(research, "get_trends", lambda *_args, **_kwargs: {"items": catalog})

    bundle = research.build_research_bundle("AI agents", category="ai", max_sources=6)

    assert len(bundle["evidence"]) == 6
    assert sum(item["source_kind"] == "catalog" for item in bundle["evidence"]) == 2
