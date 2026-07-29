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
    last_request: dict | None = None

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> None:
        return None

    def post(self, *_args, **_kwargs) -> FakeResponse:
        FakeClient.last_request = _kwargs
        return FakeResponse(self.payload)


def test_generate_storyboard_uses_only_known_citations(monkeypatch) -> None:
    storyboard = {
        "title": "근거 기반 영상",
        "summary": "요약",
        "cards": [
            {"kind": "headline", "structure": "hook", "title": "첫 카드", "citations": ["ev-known"]},
            {"kind": "bullets", "title": "둘째 카드", "bullets": ["근거"], "citations": ["ev-known"]},
            {"kind": "bullets", "title": "셋째 카드", "bullets": ["근거"], "citations": ["ev-known"]},
            {"kind": "bullets", "title": "넷째 카드", "bullets": ["근거"], "citations": ["ev-known"]},
            {"kind": "bullets", "title": "다섯째 카드", "bullets": ["근거"], "citations": ["ev-known"]},
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
        "short",
    )

    assert result["mode"] == "omlx"
    assert result["model"] == "gemma-test"
    assert result["cards"][-1]["citations"] == ["ev-known"]
    assert [card["id"] for card in result["cards"]] == [f"c{index}" for index in range(1, 7)]
    schema = FakeClient.last_request["json"]["response_format"]["json_schema"]["schema"]
    assert schema["properties"]["cards"]["minItems"] == 6
    assert schema["properties"]["cards"]["maxItems"] == 8
    assert FakeClient.last_request["json"]["max_tokens"] == 4200


def test_decode_json_accepts_fenced_output() -> None:
    assert omlx._decode_json('```json\n{"title":"ok"}\n```') == {"title": "ok"}
