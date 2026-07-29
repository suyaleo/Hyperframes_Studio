from fastapi.testclient import TestClient

from api import main
from api.omlx import OmlxConfigurationError

CLIENT = TestClient(main.app)
BUNDLE = {
    "id": "123456789abc",
    "query": "근거 기반 테스트",
    "category": "ai",
    "evidence": [
        {
            "id": "ev-known",
            "title": "검증 근거",
            "excerpt": "검증된 설명입니다.",
            "source": "Test Source",
        }
    ],
}


def test_storyboard_endpoint_labels_deterministic_fallback(monkeypatch) -> None:
    monkeypatch.setattr(main, "get_research_bundle", lambda _bundle_id: BUNDLE)
    monkeypatch.setattr(
        main, "generate_storyboard", lambda *_args: (_ for _ in ()).throw(OmlxConfigurationError("키 없음"))
    )
    monkeypatch.setattr(main, "save_project", lambda project: project)

    response = CLIENT.post(
        "/api/storyboards/generate",
        json={
            "research_id": BUNDLE["id"],
            "template_ids": ["headline", "bullets", "cta"],
            "allow_fallback": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["generation"]["mode"] == "deterministic-fallback"
    assert payload["generation"]["warning"] == "키 없음"
    assert payload["project"]["briefing_mode"] == "standard"
    assert len(payload["project"]["cards"]) == 10
    assert payload["project"]["seconds_per_card"] == 4.0
    assert all(card["citations"] == ["ev-known"] for card in payload["project"]["cards"])


def test_storyboard_endpoint_can_require_omlx(monkeypatch) -> None:
    monkeypatch.setattr(main, "get_research_bundle", lambda _bundle_id: BUNDLE)
    monkeypatch.setattr(
        main, "generate_storyboard", lambda *_args: (_ for _ in ()).throw(OmlxConfigurationError("키 없음"))
    )

    response = CLIENT.post(
        "/api/storyboards/generate",
        json={"research_id": BUNDLE["id"], "allow_fallback": False},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "키 없음"
