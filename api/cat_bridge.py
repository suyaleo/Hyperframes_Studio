"""CAT Artifact Bridge v1 endpoint for deterministic MotionMedia output."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from api.settings import RUNTIME_ROOT, VERSION


PROTOCOL_VERSION = 1
ENGINE_ID = "hyperframes-studio-bridge"
CAPABILITY = "render-motion"
MEDIA_TYPE = "video/mp4"
MODE = "image-motion-v1"
_SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
_SAFE_OUTPUT_PATTERN = re.compile(r"^[0-9a-f]{64}\.mp4$")
_PRESETS = {"push-in", "pan-left", "pan-right"}


class BridgeConflict(ValueError):
    """The caller reused durable identity with conflicting evidence."""


class CatMotionBridge:
    def __init__(self, workspace: Path | None = None) -> None:
        self.root = (workspace or RUNTIME_ROOT).resolve() / "cat-artifact-bridge-v1"
        self.operations_root = self.root / "operations"
        self.outputs_root = self.root / "outputs"
        self.operations_root.mkdir(parents=True, exist_ok=True)
        self.outputs_root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def health(self) -> dict[str, Any]:
        ffmpeg = shutil.which(os.environ.get("CAT_FFMPEG_PATH", "ffmpeg"))
        ffprobe = shutil.which(os.environ.get("CAT_FFPROBE_PATH", "ffprobe"))
        writable = _writable(self.root)
        ready = bool(ffmpeg and ffprobe and writable)
        missing = [name for name, value in (("ffmpeg", ffmpeg), ("ffprobe", ffprobe)) if not value]
        message = "CAT Motion Bridge v1 is ready"
        if not writable:
            message = "CAT Motion Bridge workspace is not writable"
        elif missing:
            message = f"required runtime is unavailable: {', '.join(missing)}"
        return {
            "ok": ready,
            "ready": ready,
            "protocolVersion": PROTOCOL_VERSION,
            "engineId": ENGINE_ID,
            "engineVersion": VERSION,
            "capabilities": [CAPABILITY],
            "outputMediaTypes": [MEDIA_TYPE],
            "mode": "motion-bridge-v1",
            "modes": [MODE],
            "runtime": {
                "ffmpeg": ffmpeg is not None,
                "ffprobe": ffprobe is not None,
            },
            "recovery": {"intent": True, "output": True, "receipt": True},
            "message": message,
        }

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        normalized = _validate_request(request)
        source = _path_from_file_uri(normalized["inputPayloadUris"][0])
        actual_input_hash = _sha256_file(source)
        expected_input_hash = normalized["parameters"]["inputContentHash"]
        if actual_input_hash != expected_input_hash:
            raise BridgeConflict(
                f"input hash mismatch: expected {expected_input_hash}, got {actual_input_hash}"
            )

        key = normalized["idempotencyKey"]
        slug = hashlib.sha256(key.encode("utf-8")).hexdigest()
        fingerprint = _sha256_json(normalized)
        intent_path = self.operations_root / f"{slug}.intent.json"
        receipt_path = self.operations_root / f"{slug}.receipt.json"
        output_path = self.outputs_root / f"{slug}.mp4"
        pending_path = self.outputs_root / f".{slug}.pending.mp4"

        with self._lock:
            if intent_path.is_file():
                intent = _read_json(intent_path)
                if intent.get("requestFingerprint") != fingerprint:
                    raise BridgeConflict("idempotency key was reused with a different request")
            else:
                _write_new_json(
                    intent_path,
                    {
                        "schemaVersion": 1,
                        "requestFingerprint": fingerprint,
                        "request": normalized,
                    },
                )

            if receipt_path.is_file():
                receipt = _read_json(receipt_path)
                _validate_receipt(receipt, normalized, output_path)
                return receipt

            if output_path.is_file():
                _verify_video(output_path, normalized["parameters"])
            else:
                pending_path.unlink(missing_ok=True)
                _render_motion(source, pending_path, normalized["parameters"])
                _verify_video(pending_path, normalized["parameters"])
                pending_path.replace(output_path)

            output_hash = _sha256_file(output_path)
            response = {
                "protocolVersion": PROTOCOL_VERSION,
                "engineId": ENGINE_ID,
                "engineVersion": VERSION,
                "idempotencyKey": key,
                "status": "complete",
                "output": {
                    "mediaType": MEDIA_TYPE,
                    "contentHash": output_hash,
                    "downloadUrl": f"/cat/v1/outputs/{slug}.mp4",
                },
                "provenance": {
                    "mode": MODE,
                    "inputContentHash": actual_input_hash,
                    "motionPreset": normalized["parameters"]["motionPreset"],
                    "durationMs": int(normalized["parameters"]["durationMs"]),
                    "fps": int(normalized["parameters"]["fps"]),
                    "width": 1080,
                    "height": 1920,
                    "renderer": "ffmpeg-zoompan-v1",
                },
            }
            _write_new_json(receipt_path, response)
            return response

    def output_path(self, filename: str) -> Path:
        if not _SAFE_OUTPUT_PATTERN.fullmatch(filename):
            raise FileNotFoundError(filename)
        path = self.outputs_root / filename
        if not path.is_file():
            raise FileNotFoundError(filename)
        return path


def _validate_request(request: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("request body must be an object")
    if request.get("protocolVersion") != PROTOCOL_VERSION:
        raise ValueError(f"protocolVersion must be {PROTOCOL_VERSION}")
    if request.get("engineId") != ENGINE_ID:
        raise ValueError(f"engineId must be {ENGINE_ID}")
    if request.get("capability") != CAPABILITY:
        raise ValueError(f"capability must be {CAPABILITY}")
    key = _required_string(request, "idempotencyKey", 512)
    scene_id = _required_string(request, "sceneId", 512)
    prompt = _required_string(request, "prompt", 20_000)
    parent_artifact_id = _required_string(request, "parentArtifactId", 512)
    raw_uris = request.get("inputPayloadUris")
    if not isinstance(raw_uris, list) or len(raw_uris) != 1 or not isinstance(raw_uris[0], str):
        raise ValueError("inputPayloadUris must contain exactly one local image URI")
    source = _path_from_file_uri(raw_uris[0])
    if not source.is_file() or source.is_symlink():
        raise ValueError("input image must be an existing regular file")
    if source.stat().st_size <= 0 or source.stat().st_size > 128 * 1024 * 1024:
        raise ValueError("input image size is outside the supported range")

    raw_parameters = request.get("parameters") or {}
    if not isinstance(raw_parameters, dict):
        raise ValueError("parameters must be an object")
    mode = _parameter(raw_parameters, "mode", MODE, 64)
    preset = _parameter(raw_parameters, "motionPreset", "push-in", 64)
    if mode != MODE:
        raise ValueError(f"parameters.mode must be {MODE}")
    if preset not in _PRESETS:
        raise ValueError(f"parameters.motionPreset must be one of {sorted(_PRESETS)}")
    duration_ms = _integer_parameter(raw_parameters, "durationMs", 2_000)
    fps = _integer_parameter(raw_parameters, "fps", 30)
    input_hash = _parameter(raw_parameters, "inputContentHash", "", 80).lower()
    if not 1_000 <= duration_ms <= 12_000:
        raise ValueError("parameters.durationMs must be between 1000 and 12000")
    if fps != 30:
        raise ValueError("parameters.fps must be 30 for image-motion-v1")
    if not _SHA256_PATTERN.fullmatch(input_hash):
        raise ValueError("parameters.inputContentHash must be a lowercase SHA-256 digest")
    parameters = {str(key): str(value) for key, value in sorted(raw_parameters.items())}
    parameters.update(
        {
            "mode": mode,
            "motionPreset": preset,
            "durationMs": str(duration_ms),
            "fps": str(fps),
            "inputContentHash": input_hash,
        }
    )
    return {
        "protocolVersion": PROTOCOL_VERSION,
        "engineId": ENGINE_ID,
        "idempotencyKey": key,
        "capability": CAPABILITY,
        "sceneId": scene_id,
        "prompt": prompt,
        "parentArtifactId": parent_artifact_id,
        "inputPayloadUris": [raw_uris[0]],
        "parameters": parameters,
    }


def _render_motion(source: Path, destination: Path, parameters: dict[str, str]) -> None:
    ffmpeg = shutil.which(os.environ.get("CAT_FFMPEG_PATH", "ffmpeg"))
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required for image-motion-v1")
    duration_ms = int(parameters["durationMs"])
    fps = int(parameters["fps"])
    frames = max(1, round(duration_ms * fps / 1_000))
    preset = parameters["motionPreset"]
    if preset == "push-in":
        zoom = f"min(1+on*0.12/{frames},1.12)"
        x = "iw/2-(iw/zoom/2)"
        y = "ih/2-(ih/zoom/2)"
    elif preset == "pan-left":
        zoom = "1.12"
        x = f"(iw-iw/zoom)*(1-on/{frames})"
        y = "ih/2-(ih/zoom/2)"
    else:
        zoom = "1.12"
        x = f"(iw-iw/zoom)*on/{frames}"
        y = "ih/2-(ih/zoom/2)"
    video_filter = (
        "scale=1080:1920:force_original_aspect_ratio=increase,"
        "crop=1080:1920,"
        f"zoompan=z='{zoom}':x='{x}':y='{y}':d=1:s=1080x1920:fps={fps},"
        "format=yuv420p"
    )
    result = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-loop",
            "1",
            "-i",
            str(source),
            "-vf",
            video_filter,
            "-frames:v",
            str(frames),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-movflags",
            "+faststart",
            "-f",
            "mp4",
            str(destination),
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if result.returncode != 0 or not destination.is_file():
        destination.unlink(missing_ok=True)
        detail = (result.stderr or result.stdout or "ffmpeg did not create MotionMedia")[-1_000:]
        raise RuntimeError(detail)


def _verify_video(path: Path, parameters: dict[str, str]) -> None:
    ffprobe = shutil.which(os.environ.get("CAT_FFPROBE_PATH", "ffprobe"))
    if not ffprobe:
        raise RuntimeError("ffprobe is required for image-motion-v1")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,nb_frames:format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise BridgeConflict("MotionMedia output cannot be probed")
    payload = json.loads(result.stdout)
    video = next((stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"), None)
    expected_frames = round(int(parameters["durationMs"]) * int(parameters["fps"]) / 1_000)
    if not video or video.get("codec_name") != "h264":
        raise BridgeConflict("MotionMedia output must contain H.264 video")
    if (video.get("width"), video.get("height"), video.get("pix_fmt")) != (1080, 1920, "yuv420p"):
        raise BridgeConflict("MotionMedia output has unexpected dimensions or pixel format")
    if video.get("avg_frame_rate") != "30/1" or int(video.get("nb_frames") or 0) != expected_frames:
        raise BridgeConflict("MotionMedia output has unexpected frame timing")


def _validate_receipt(receipt: dict[str, Any], request: dict[str, Any], output_path: Path) -> None:
    if receipt.get("idempotencyKey") != request["idempotencyKey"]:
        raise BridgeConflict("receipt idempotency key does not match durable intent")
    output = receipt.get("output") or {}
    if not output_path.is_file() or output.get("contentHash") != _sha256_file(output_path):
        raise BridgeConflict("receipt output is missing or hash-mismatched")
    _verify_video(output_path, request["parameters"])


def _path_from_file_uri(value: str) -> Path:
    parsed = urlparse(value)
    if parsed.scheme.lower() != "file" or parsed.netloc not in {"", "localhost"}:
        raise ValueError("input payload must use a local file URI")
    decoded = unquote(parsed.path)
    if os.name == "nt" and re.match(r"^/[A-Za-z]:", decoded):
        decoded = decoded[1:]
    return Path(decoded).resolve()


def _required_string(value: dict[str, Any], key: str, maximum: int) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str) or not candidate.strip() or len(candidate) > maximum:
        raise ValueError(f"{key} must be a non-empty string up to {maximum} characters")
    return candidate


def _parameter(value: dict[str, Any], key: str, default: str, maximum: int) -> str:
    candidate = value.get(key, default)
    if not isinstance(candidate, (str, int, bool)):
        raise ValueError(f"parameters.{key} must be a scalar")
    result = str(candidate).strip()
    if not result or len(result) > maximum:
        raise ValueError(f"parameters.{key} is outside the supported range")
    return result


def _integer_parameter(value: dict[str, Any], key: str, default: int) -> int:
    candidate = value.get(key, default)
    if isinstance(candidate, bool):
        raise ValueError(f"parameters.{key} must be an integer")
    try:
        return int(candidate)
    except (TypeError, ValueError) as error:
        raise ValueError(f"parameters.{key} must be an integer") from error


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_new_json(path: Path, value: dict[str, Any]) -> None:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2).encode("utf-8")
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except FileExistsError as error:
        raise BridgeConflict(f"durable path already exists: {path.name}") from error


def _writable(path: Path) -> bool:
    probe = path / ".health-write-probe"
    try:
        probe.write_bytes(b"ready")
        probe.unlink()
        return True
    except OSError:
        return False
