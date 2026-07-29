import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_theme_bootstrap_runs_before_stylesheet() -> None:
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")

    assert html.index("hyperframes-studio-theme") < html.index("styles.css")
    assert 'data-theme="dark"' in html
    assert "hyperframes-logo-dark.svg" in html
    assert "hyperframes-logo-light.svg" in html


def test_studio_shell_has_real_work_surfaces() -> None:
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")

    for surface in (
        "studio-toolbar",
        "studio-list",
        "studio-canvas",
        "studio-inspector",
        "studio-timeline",
        "studio-production-panel",
    ):
        assert surface in html
    assert 'href="/app/"' not in html
    assert 'href="/grok/"' not in html


def test_ai_trend_category_is_declared() -> None:
    categories = json.loads((ROOT / "data/categories.json").read_text(encoding="utf-8"))

    assert {item["id"] for item in categories["issue_categories"]} >= {"rising", "ai"}


def test_research_first_controls_are_present() -> None:
    html = (ROOT / "web/index.html").read_text(encoding="utf-8")

    assert 'id="btnResearch"' in html
    assert 'id="btnBuild"' in html
    assert 'id="researchContent"' in html
    assert 'id="summaryGeneration"' in html
    assert 'id="summaryNarration"' in html
    assert "근거 수집부터 카드 생성까지 자동으로 진행합니다" in html
