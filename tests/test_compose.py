from api import compose
from api.compose import ASPECT_VARIANTS, build_cards_from_issue, project_to_html, save_project


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
    assert "aspect-square" in html
    assert "context-rail" in html
    assert 'id="scene-01-c1"' in html
    assert "performance.now" not in html
    assert "requestAnimationFrame" not in html


def test_all_aspect_variants_have_exact_dimensions_and_art_direction() -> None:
    project = {
        "title": "멀티 비율 프로젝트",
        "seconds_per_card": 3,
        "motion": "zoom",
        "cards": [{"id": "c1", "kind": "headline", "title": "화면비 테스트", "subtitle": "동일한 내용"}],
    }

    for aspect, spec in ASPECT_VARIANTS.items():
        html = project_to_html(project, aspect_ratio=aspect)
        assert f'data-width="{spec["width"]}"' in html
        assert f'data-height="{spec["height"]}"' in html
        assert f'aspect-{spec["key"]}' in html
        assert "fixedPreview" in html
        assert "fitEmbeddedPreview" in html


def test_save_project_builds_three_variants_and_aspect_switch_does_not_rewrite_them(
    tmp_path, monkeypatch
) -> None:
    output = tmp_path / "output"
    compositions = tmp_path / "compositions"
    output.mkdir()
    compositions.mkdir()
    monkeypatch.setattr(compose, "OUT", output)
    monkeypatch.setattr(compose, "COMP", compositions)

    project = save_project(
        {
            "id": "variant-test",
            "title": "화면비 테스트",
            "aspect_ratio": "9:16",
            "seconds_per_card": 2,
            "cards": [{"id": "c1", "kind": "headline", "title": "하나의 스토리보드"}],
        }
    )
    for aspect, spec in ASPECT_VARIANTS.items():
        assert project["variants"][aspect]["width"] == spec["width"]
        assert (output / f"variant-test-{spec['key']}.html").exists()

    portrait = output / "variant-test-portrait.html"
    original = portrait.read_text(encoding="utf-8")
    project["aspect_ratio"] = "1:1"
    switched = save_project(project, preserve_renders=True, refresh_compositions=False)

    assert switched["aspect_ratio"] == "1:1"
    assert switched["preview_url"].endswith("-square.html")
    assert portrait.read_text(encoding="utf-8") == original
