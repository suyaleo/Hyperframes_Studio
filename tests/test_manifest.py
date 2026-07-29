import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_identity_is_internally_consistent() -> None:
    manifest = json.loads((ROOT / "studio.json").read_text(encoding="utf-8"))

    assert manifest["displayName"] == "Hyperframes Studio"
    assert manifest["repository"] == "Hyperframes_Studio"
    assert manifest["slug"] == "hyperframes-studio"
    assert manifest["container"] == "ghcr.io/suyaleo/hyperframes-studio"
    assert manifest["aiProfile"] == manifest["slug"]
    assert manifest["license"] == "Apache-2.0"


def test_release_contract_files_exist() -> None:
    required = {
        "studio.json",
        "LICENSE",
        "NOTICE",
        "THIRD_PARTY_NOTICES.md",
        "TRADEMARKS.md",
        "SECURITY.md",
        ".env.example",
        ".dockerignore",
        "Dockerfile",
        "compose.yaml",
        "pyproject.toml",
        "uv.lock",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
    }

    assert not [path for path in sorted(required) if not (ROOT / path).exists()]


def test_native_and_docker_omlx_addresses_are_separate() -> None:
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "OMLX_BASE_URL=http://127.0.0.1:8000/v1" in env_example
    assert "OMLX_DOCKER_BASE_URL=http://host.docker.internal:8000/v1" in env_example
    assert "OMLX_BASE_URL: ${OMLX_DOCKER_BASE_URL:-http://host.docker.internal:8000/v1}" in compose
