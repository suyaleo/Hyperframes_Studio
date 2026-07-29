import io
import zipfile

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


def test_complete_export_package_contains_all_aspect_outputs(tmp_path, monkeypatch) -> None:
    project = {
        "id": "export-test",
        "title": "Export test",
        "cards": [{"id": "c1", "kind": "headline", "title": "Test"}],
        "seconds_per_card": 4,
        "variants": {},
    }
    for aspect, spec in main.ASPECT_VARIANTS.items():
        key = spec["key"]
        (tmp_path / f"export-test-{key}.html").write_text(f"<html>{aspect}</html>", encoding="utf-8")
        (tmp_path / f"export-test-{key}.mp4").write_bytes(f"video-{aspect}".encode())
        project["variants"][aspect] = {
            **spec,
            "aspect_ratio": aspect,
            "render_status": "ready",
            "preview_url": f"/output/export-test-{key}.html",
            "video_url": f"/output/export-test-{key}.mp4",
            "rendered_at": "2026-07-30T00:00:00+00:00",
        }

    monkeypatch.setattr(main, "OUT", tmp_path)
    monkeypatch.setattr(main, "get_project", lambda _pid: project)
    monkeypatch.setattr(main, "get_research_bundle", lambda _rid: None)

    response = CLIENT.get("/api/projects/export-test/export-package")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert "hyperframes-export-test-complete.zip" in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "hyperframes-export-test/manifest.json" in names
        assert "hyperframes-export-test/project.json" in names
        assert "hyperframes-export-test/README.txt" in names
        for spec in main.ASPECT_VARIANTS.values():
            assert f"hyperframes-export-test/html/hyperframes-{spec['key']}.html" in names
            assert f"hyperframes-export-test/video/hyperframes-{spec['key']}.mp4" in names


def test_export_package_waits_for_all_variants(monkeypatch) -> None:
    project = {
        "id": "partial-test",
        "variants": {
            aspect: {"render_status": "pending" if aspect == "1:1" else "ready"}
            for aspect in main.ASPECT_VARIANTS
        },
    }
    monkeypatch.setattr(main, "get_project", lambda _pid: project)

    response = CLIENT.get("/api/projects/partial-test/export-package")

    assert response.status_code == 409
    assert "1:1" in response.json()["detail"]
