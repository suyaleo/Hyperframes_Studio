import json

from api import omlx


class FakeResponse:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class FakeClient:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def post(self, *_args, **_kwargs) -> FakeResponse:
        return FakeResponse(self.payload)


def test_generate_storyboard_uses_only_known_citations(monkeypatch) -> None:
    storyboard = {
        "title": "근거 기반 영상",
        "summary": "요약",
        "cards": [
            {"kind": "headline", "structure": "hook", "title": "첫 카드", "citations": ["ev-known"]},
            {"kind": "bullets", "title": "둘째 카드", "bullets": ["근거"], "citations": ["ev-known"]},
            {"kind": "cta", "structure": "close", "title": "정리", "citations": ["ev-known", "ev-unknown"]},
        ],
    }
    response = {
        "choices": [{"message": {"content": json.dumps(storyboard, ensure_ascii=False)}}],
        "usage": {"total_tokens": 42},
    }
    monkeypatch.setattr(
        omlx,
        "get_omlx_status",
        lambda: {
            "configured": True,
            "reason": "",
            "model": "gemma-test",
            "base_url": "http://127.0.0.1:8000/v1",
        },
    )
    monkeypatch.setattr(omlx, "_configuration", lambda: ("http://127.0.0.1:8000/v1", "secret", "gemma-test"))
    monkeypatch.setattr(omlx.httpx, "Client", lambda **_kwargs: FakeClient(response))

    result = omlx.generate_storyboard(
        {"query": "테스트", "evidence": [{"id": "ev-known", "title": "근거", "excerpt": "내용"}]},
        ["headline", "bullets", "cta"],
    )

    assert result["mode"] == "omlx"
    assert result["model"] == "gemma-test"
    assert result["cards"][2]["citations"] == ["ev-known"]
    assert [card["id"] for card in result["cards"]] == ["c1", "c2", "c3"]


def test_decode_json_accepts_fenced_output() -> None:
    assert omlx._decode_json('```json\n{"title":"ok"}\n```') == {"title": "ok"}
