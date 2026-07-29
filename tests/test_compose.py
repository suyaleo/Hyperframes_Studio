from api.compose import build_cards_from_issue, project_to_html


def test_build_cards_from_issue_preserves_source_context() -> None:
    cards = build_cards_from_issue(
        {
            "title": "테스트 이슈",
            "summary": "첫 번째 근거입니다. 두 번째 근거입니다.",
            "category": "rising",
            "source": "Test Feed",
        },
        template_ids=["headline", "bullets", "quote"],
    )

    assert [card["kind"] for card in cards] == ["headline", "bullets", "quote"]
    assert cards[0]["title"] == "테스트 이슈"
    assert cards[0]["subtitle"] == "Test Feed"
    assert cards[2]["attribution"] == "Test Feed"


def test_project_html_uses_studio_composition_contract() -> None:
    html = project_to_html(
        {
            "title": "테스트 프로젝트",
            "aspect_ratio": "1:1",
            "seconds_per_card": 2,
            "motion": "zoom",
            "cards": [{"id": "c1", "kind": "headline", "title": "제목", "subtitle": "설명"}],
        }
    )

    assert 'data-composition-id="hyperframes-studio"' in html
    assert 'data-width="1080"' in html
    assert 'data-height="1080"' in html
    assert "window.__timelines['hyperframes-studio']" in html
