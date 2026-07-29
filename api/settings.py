from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = json.loads((ROOT / "studio.json").read_text(encoding="utf-8"))

DISPLAY_NAME: str = MANIFEST["displayName"]
SERVICE_SLUG: str = MANIFEST["slug"]
VERSION: str = MANIFEST["version"]
DEFAULT_PORT: int = MANIFEST["defaultPort"]

RUNTIME_ROOT = Path(os.environ.get("HYPERFRAMES_DATA_DIR") or ROOT).expanduser().resolve()
STATIC_DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
OUTPUT_DIR = RUNTIME_ROOT / "output"
COMPOSITIONS_DIR = RUNTIME_ROOT / "compositions"
PROJECTS_DIR = COMPOSITIONS_DIR / "projects"
REMOTION_EXPORT_DIR = COMPOSITIONS_DIR / "remotion"
REMOTION_TEMPLATE_DIR = ROOT / "remotion-template"


def ensure_runtime_directories() -> None:
    for path in (OUTPUT_DIR, PROJECTS_DIR, REMOTION_EXPORT_DIR):
        path.mkdir(parents=True, exist_ok=True)


ensure_runtime_directories()
