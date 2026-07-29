"""Real Remotion render adapter for Hyperframes Studio."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from api.settings import OUTPUT_DIR, PROJECTS_DIR, REMOTION_EXPORT_DIR, REMOTION_TEMPLATE_DIR

COMP = PROJECTS_DIR
OUT = OUTPUT_DIR
REM = REMOTION_EXPORT_DIR
TEMPLATE = REMOTION_TEMPLATE_DIR


def export_remotion_project(project_id: str) -> dict[str, Any]:
    proj_path = COMP / project_id / "project.json"
    if not proj_path.exists():
        raise FileNotFoundError(project_id)
    proj = json.loads(proj_path.read_text(encoding="utf-8"))
    dest = REM / project_id
    dest.mkdir(parents=True, exist_ok=True)
    props = {
        "title": proj.get("title") or "Hyperframes Studio",
        "aspect_ratio": proj.get("aspect_ratio") or "9:16",
        "secondsPerCard": float(proj.get("seconds_per_card") or 2.5),
        "cards": proj.get("cards") or [],
    }
    props_path = dest / "input-props.json"
    props_path.write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    (dest / "README.md").write_text(
        f"# Remotion export {project_id}\n\nRendered via remotion-template CardMotion composition.\n",
        encoding="utf-8",
    )
    return {"ok": True, "path": str(dest), "props_path": str(props_path), "props": props}


def _npx() -> str:
    exe = shutil.which("npx")
    if not exe:
        raise RuntimeError("npx not available")
    return exe


def render_remotion_style(project_id: str, fps: int = 30) -> dict[str, Any]:
    meta = export_remotion_project(project_id)
    props_path = Path(meta["props_path"])
    out_mp4 = OUT / f"{project_id}.mp4"
    if out_mp4.exists():
        try:
            out_mp4.unlink()
        except OSError:
            pass

    if not TEMPLATE.exists():
        raise RuntimeError("remotion-template missing")

    # Ensure deps (image build should preinstall; runtime fallback)
    node_modules = TEMPLATE / "node_modules" / "remotion"
    if not node_modules.exists():
        npm = shutil.which("npm") or "npm"
        r = subprocess.run(
            [npm, "install", "--no-fund", "--no-audit"],
            cwd=str(TEMPLATE),
            capture_output=True,
            text=True,
            timeout=900,
        )
        if r.returncode != 0:
            raise RuntimeError("npm install remotion-template failed: " + ((r.stderr or r.stdout or "")[-500:]))

    # Ensure chrome for remotion
    subprocess.run(
        [_npx(), "remotion", "browser", "ensure"],
        cwd=str(TEMPLATE),
        capture_output=True,
        text=True,
        timeout=600,
    )

    cmd = [
        _npx(),
        "remotion",
        "render",
        "src/index.ts",
        "CardMotion",
        str(out_mp4),
        f"--props={props_path}",
        f"--fps={max(1, min(int(fps or 30), 60))}",
        "--log=error",
        "--timeout=120000",
    ]
    env = os.environ.copy()
    env.setdefault("REMOTION_GL", "swangle")
    r = subprocess.run(cmd, cwd=str(TEMPLATE), capture_output=True, text=True, timeout=900, env=env)
    detail = ((r.stdout or "") + "\n" + (r.stderr or ""))[-800:]
    if r.returncode != 0 or not out_mp4.exists():
        raise RuntimeError(detail or "remotion render failed")

    # also refresh HTML composition with remotion theme for preview file
    try:
        from api.compose import get_project, save_project

        proj = get_project(project_id)
        if proj:
            proj["motion"] = "remotion"
            proj["engine_hint"] = "remotion"
            save_project(proj)
    except Exception:
        pass

    return {
        "engine": "remotion",
        "video_url": f"/output/{project_id}.mp4",
        "path": str(out_mp4),
        "fps": fps,
        "remotion_export": meta.get("path"),
        "detail": detail[-200:],
    }
