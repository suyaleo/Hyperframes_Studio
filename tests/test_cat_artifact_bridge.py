from __future__ import annotations

import base64
import hashlib
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api import cat_bridge, main


PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def request_for(source: Path, *, key: str = "operation-motion-1") -> dict[str, object]:
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    return {
        "protocolVersion": 1,
        "engineId": "hyperframes-studio-bridge",
        "idempotencyKey": key,
        "capability": "render-motion",
        "sceneId": "scene-1",
        "prompt": "선택 장면을 실제 9:16 모션으로 렌더",
        "parentArtifactId": "artifact-image-1",
        "inputPayloadUris": [source.resolve().as_uri()],
        "parameters": {
            "mode": "image-motion-v1",
            "motionPreset": "push-in",
            "durationMs": "1000",
            "fps": "30",
            "inputContentHash": f"sha256:{digest}",
        },
    }


def test_bridge_is_idempotent_and_rejects_hash_or_request_conflicts(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(PNG_1X1)
    bridge = cat_bridge.CatMotionBridge(tmp_path / "workspace")

    monkeypatch.setattr(cat_bridge, "_render_motion", lambda _source, destination, _parameters: destination.write_bytes(b"mp4"))
    monkeypatch.setattr(cat_bridge, "_verify_video", lambda _path, _parameters: None)

    first = bridge.execute(request_for(source))
    repeated = bridge.execute(request_for(source))
    assert repeated == first
    assert first["output"]["mediaType"] == "video/mp4"
    assert bridge.output_path(first["output"]["downloadUrl"].rsplit("/", 1)[-1]).read_bytes() == b"mp4"

    conflict = request_for(source)
    conflict["parameters"]["motionPreset"] = "pan-left"  # type: ignore[index]
    with pytest.raises(cat_bridge.BridgeConflict, match="different request"):
        bridge.execute(conflict)

    mismatch = request_for(source, key="operation-motion-hash-mismatch")
    mismatch["parameters"]["inputContentHash"] = "sha256:" + "0" * 64  # type: ignore[index]
    with pytest.raises(cat_bridge.BridgeConflict, match="input hash mismatch"):
        bridge.execute(mismatch)


def test_http_contract_exposes_health_errors_and_owned_download(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(PNG_1X1)
    bridge = cat_bridge.CatMotionBridge(tmp_path / "workspace")
    monkeypatch.setattr(main, "CAT_BRIDGE", bridge)
    monkeypatch.setattr(cat_bridge, "_render_motion", lambda _source, destination, _parameters: destination.write_bytes(b"mp4"))
    monkeypatch.setattr(cat_bridge, "_verify_video", lambda _path, _parameters: None)
    monkeypatch.setattr(bridge, "health", lambda: {"ok": True, "ready": True, "protocolVersion": 1, "engineId": cat_bridge.ENGINE_ID, "engineVersion": "0.1.0"})
    client = TestClient(main.app)

    assert client.get("/cat/v1/health").json()["ready"] is True
    response = client.post("/cat/v1/artifacts", json=request_for(source))
    assert response.status_code == 200
    download = client.get(response.json()["output"]["downloadUrl"])
    assert download.status_code == 200
    assert download.content == b"mp4"

    invalid = request_for(source, key="operation-invalid")
    invalid["capability"] = "generate-depth-map"
    rejected = client.post("/cat/v1/artifacts", json=invalid)
    assert rejected.status_code == 400
    assert "error" in rejected.json()


def test_restart_recovers_output_without_receipt_and_rejects_tamper(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(PNG_1X1)
    workspace = tmp_path / "workspace"
    bridge = cat_bridge.CatMotionBridge(workspace)
    renders: list[Path] = []

    def render(_source: Path, destination: Path, _parameters: dict[str, str]) -> None:
        renders.append(destination)
        destination.write_bytes(b"verified-mp4")

    monkeypatch.setattr(cat_bridge, "_render_motion", render)
    monkeypatch.setattr(cat_bridge, "_verify_video", lambda _path, _parameters: None)
    request = request_for(source, key="operation-restart-recovery")
    first = bridge.execute(request)
    slug = first["output"]["downloadUrl"].rsplit("/", 1)[-1].removesuffix(".mp4")
    (bridge.operations_root / f"{slug}.receipt.json").unlink()

    restarted = cat_bridge.CatMotionBridge(workspace)
    recovered = restarted.execute(request)
    assert recovered["output"]["contentHash"] == first["output"]["contentHash"]
    assert len(renders) == 1

    restarted.output_path(f"{slug}.mp4").write_bytes(b"tampered")
    with pytest.raises(cat_bridge.BridgeConflict, match="hash-mismatched"):
        cat_bridge.CatMotionBridge(workspace).execute(request)


def test_interrupted_pending_output_is_retried_under_one_intent(tmp_path, monkeypatch) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(PNG_1X1)
    workspace = tmp_path / "workspace"
    bridge = cat_bridge.CatMotionBridge(workspace)
    attempts = 0

    def interrupted_then_complete(
        _source: Path,
        destination: Path,
        _parameters: dict[str, str],
    ) -> None:
        nonlocal attempts
        attempts += 1
        destination.write_bytes(b"partial" if attempts == 1 else b"complete-mp4")
        if attempts == 1:
            raise RuntimeError("simulated bridge interruption")

    monkeypatch.setattr(cat_bridge, "_render_motion", interrupted_then_complete)
    monkeypatch.setattr(cat_bridge, "_verify_video", lambda _path, _parameters: None)
    request = request_for(source, key="operation-interrupted-pending")
    with pytest.raises(RuntimeError, match="simulated bridge interruption"):
        bridge.execute(request)

    recovered = cat_bridge.CatMotionBridge(workspace).execute(request)
    output = cat_bridge.CatMotionBridge(workspace).output_path(
        recovered["output"]["downloadUrl"].rsplit("/", 1)[-1]
    )
    assert output.read_bytes() == b"complete-mp4"
    assert attempts == 2
    assert len(list(bridge.operations_root.glob("*.intent.json"))) == 1
    assert len(list(bridge.operations_root.glob("*.receipt.json"))) == 1


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg is required")
def test_real_bridge_output_is_verified_h264_motion(tmp_path) -> None:
    source = tmp_path / "source.png"
    source.write_bytes(PNG_1X1)
    bridge = cat_bridge.CatMotionBridge(tmp_path / "workspace")

    result = bridge.execute(request_for(source, key="operation-real-motion"))
    output = bridge.output_path(result["output"]["downloadUrl"].rsplit("/", 1)[-1])
    probe = subprocess.run(
        [
            shutil.which("ffprobe") or "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_name,width,height,pix_fmt,avg_frame_rate,nb_frames",
            "-of",
            "json",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert '"codec_name": "h264"' in probe
    assert '"width": 1080' in probe
    assert '"height": 1920' in probe
    assert '"nb_frames": "30"' in probe
