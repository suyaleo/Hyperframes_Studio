from api.trends import AWESOME_AI_AGENTS_REPOSITORY, _catalog_item


def test_awesome_ai_catalog_item_preserves_attribution() -> None:
    item = _catalog_item(
        {
            "project": "Example Agent",
            "project_description": "An evidence-rich example.",
            "project_is_open_source": True,
            "categories": ["AI Agents"],
            "sources": [
                {
                    "source": "github",
                    "source_url": "https://github.com/example/agent",
                    "stars": 123,
                    "stars_last_updated": "2025-07-30T00:00:00Z",
                }
            ],
        }
    )

    assert item is not None
    assert item["source"] == "Awesome AI Agents"
    assert item["source_kind"] == "catalog"
    assert item["source_url"] == AWESOME_AI_AGENTS_REPOSITORY
    assert item["url"] == "https://github.com/example/agent"
    assert item["stars"] == 123
    assert item["open_source"] is True


def test_awesome_ai_catalog_skips_untitled_rows() -> None:
    assert _catalog_item({"project": "", "sources": []}) is None
