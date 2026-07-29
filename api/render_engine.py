from __future__ import annotations

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from api.compose import aspect_spec
from api.settings import OUTPUT_DIR, PROJECTS_DIR

OUT = OUTPUT_DIR
COMP = PROJECTS_DIR


def _which(*names: str) -> str | None:
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def _hyperframes_bin() -> list[str]:
    hf = _which("hyperframes")
    if hf:
        return [hf]
    npx = _which("npx")
    if npx:
        return [npx, "--yes", "hyperframes"]
    raise RuntimeError("hyperframes/npx not available")


def ensure_hyperframes_browser() -> dict[str, Any]:
    cmd = _hyperframes_bin() + ["browser", "ensure"]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return {
        "ok": r.returncode == 0,
        "code": r.returncode,
        "out": ((r.stdout or "") + "\n" + (r.stderr or ""))[-800:],
    }


def render_with_hyperframes(project_id: str, fps: int = 30, aspect_ratio: str | None = None) -> dict[str, Any]:
    proj = json.loads((COMP / project_id / "project.json").read_text(encoding="utf-8"))
    aspect = aspect_ratio or proj.get("aspect_ratio") or "9:16"
    spec = aspect_spec(aspect)
    key = str(spec["key"])
    comp = COMP / project_id / "variants" / key
    html = comp / "index.html"
    if not html.exists():
        raise FileNotFoundError("composition html missing")
    out_mp4 = OUT / f"{project_id}-{key}.mp4"
    if out_mp4.exists():
        try:
            out_mp4.unlink()
        except OSError:
            pass

    # ensure chrome once (cheap if already present)
    ensure_hyperframes_browser()

    # Choose resolution preset matching composition aspect
    if aspect == "16:9":
        res = "landscape"  # 1920x1080
    elif aspect == "1:1":
        res = "square"
    else:
        res = "portrait"  # 1080x1920

    cmd = _hyperframes_bin() + [
        "render",
        str(comp),
        "-o",
        str(out_mp4),
        "-f",
        str(max(1, min(int(fps or 30), 60))),
        "-q",
        "standard",
        "--workers",
        "1",
        "--low-memory-mode",
        "--no-browser-gpu",
        "--resolution",
        res,
        "--quiet",
    ]
    env = os.environ.copy()
    env.setdefault("PRODUCER_LOW_MEMORY_MODE", "1")
    r = subprocess.run(cmd, cwd=str(comp), capture_output=True, text=True, timeout=600, env=env)
    detail = ((r.stdout or "") + "\n" + (r.stderr or ""))[-600:]
    if r.returncode != 0 or not out_mp4.exists():
        raise RuntimeError(detail or "hyperframes failed")
    return {
        "engine": "hyperframes",
        "video_url": f"/output/{project_id}-{key}.mp4",
        "path": str(out_mp4),
        "fps": fps,
        "aspect_ratio": aspect,
        "width": int(spec["width"]),
        "height": int(spec["height"]),
        "detail": detail[-200:],
    }


def render_with_playwright(project_id: str, fps: int = 30, aspect_ratio: str | None = None) -> dict[str, Any]:
    proj = json.loads((COMP / project_id / "project.json").read_text(encoding="utf-8"))
    cards = proj.get("cards") or []
    per = float(proj.get("seconds_per_card") or 3)
    dur = max(per * max(len(cards), 1), 6.0)
    aspect = aspect_ratio or proj.get("aspect_ratio") or "9:16"
    spec = aspect_spec(aspect)
    key = str(spec["key"])
    w, h = int(spec["width"]), int(spec["height"])
    html = COMP / project_id / "variants" / key / "index.html"
    if not html.exists():
        raise FileNotFoundError("composition html missing")

    out_webm = OUT / f"{project_id}-{key}.webm"
    out_mp4 = OUT / f"{project_id}-{key}.mp4"
    for f in (out_webm, out_mp4):
        if f.exists():
            try:
                f.unlink()
            except OSError:
                pass

    async def _run() -> Path:
        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(args=["--no-sandbox", "--disable-dev-shm-usage"])
            context = await browser.new_context(
                viewport={"width": w, "height": h},
                record_video_dir=str(OUT),
                record_video_size={"width": w, "height": h},
            )
            page = await context.new_page()
            await page.goto(html.resolve().as_uri(), wait_until="load")
            await page.wait_for_timeout(int(dur * 1000) + 500)
            video = page.video
            await context.close()
            await browser.close()
            if not video:
                raise RuntimeError("no video object")
            return Path(await video.path())

    vpath = asyncio.run(_run())
    if not vpath.exists():
        raise RuntimeError("playwright video missing")
    if out_webm.exists():
        out_webm.unlink()
    vpath.rename(out_webm)

    ffmpeg = _which("ffmpeg")
    if not ffmpeg:
        return {
            "engine": "playwright-webm",
            "video_url": f"/output/{project_id}-{key}.webm",
            "path": str(out_webm),
            "fps": fps,
            "aspect_ratio": aspect,
        }

    r = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(out_webm),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-an",
            str(out_mp4),
        ],
        capture_output=True,
        text=True,
        timeout=180,
    )
    if r.returncode != 0 or not out_mp4.exists():
        return {
            "engine": "playwright-webm",
            "video_url": f"/output/{project_id}-{key}.webm",
            "path": str(out_webm),
            "ffmpeg_error": (r.stderr or "")[:300],
            "fps": fps,
            "aspect_ratio": aspect,
        }
    try:
        out_webm.unlink()
    except OSError:
        pass
    return {
        "engine": "playwright+ffmpeg",
        "video_url": f"/output/{project_id}-{key}.mp4",
        "path": str(out_mp4),
        "fps": fps,
        "aspect_ratio": aspect,
        "width": w,
        "height": h,
    }


def render_project(
    project_id: str,
    preferred: str = "auto",
    fps: int = 30,
    aspect_ratio: str | None = None,
) -> dict[str, Any]:
    default = (os.environ.get("HYPERFRAMES_DEFAULT_ENGINE") or "hyperframes").strip().lower()
    if preferred in (None, "", "auto"):
        preferred = default

    errors: list[str] = []
    if preferred == "hyperframes":
        order = ["hyperframes", "playwright", "ffmpeg"]
    elif preferred == "remotion":
        order = ["remotion", "hyperframes", "playwright", "ffmpeg"]
    elif preferred == "playwright":
        order = ["playwright", "hyperframes", "ffmpeg"]
    else:
        order = ["hyperframes", "playwright", "ffmpeg"]

    for eng in order:
        try:
            if eng == "playwright":
                return render_with_playwright(project_id, fps=fps, aspect_ratio=aspect_ratio)
            if eng == "hyperframes":
                return render_with_hyperframes(project_id, fps=fps, aspect_ratio=aspect_ratio)
            if eng == "remotion":
                from api.remotion_adapter import render_remotion_style

                return render_remotion_style(project_id, fps=fps, aspect_ratio=aspect_ratio)
            if eng == "ffmpeg":
                proj = json.loads((COMP / project_id / "project.json").read_text(encoding="utf-8"))
                cards = proj.get("cards") or []
                per = float(proj.get("seconds_per_card") or 3)
                dur = max(per * max(len(cards), 1), 6)
                aspect = aspect_ratio or proj.get("aspect_ratio") or "9:16"
                spec = aspect_spec(aspect)
                key = str(spec["key"])
                size = f"{spec['width']}x{spec['height']}"
                out_mp4 = OUT / f"{project_id}-{key}.mp4"
                ffmpeg = _which("ffmpeg")
                if not ffmpeg:
                    raise RuntimeError("ffmpeg missing")
                subprocess.run(
                    [
                        ffmpeg,
                        "-y",
                        "-f",
                        "lavfi",
                        "-i",
                        f"color=c=0x0a0a0b:s={size}:d={dur}",
                        "-vf",
                        "format=yuv420p",
                        "-t",
                        str(dur),
                        str(out_mp4),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=120,
                    check=False,
                )
                if out_mp4.exists():
                    return {
                        "engine": "ffmpeg-slate",
                        "video_url": f"/output/{project_id}-{key}.mp4",
                        "path": str(out_mp4),
                        "aspect_ratio": aspect,
                        "note": "placeholder slate",
                    }
                raise RuntimeError("ffmpeg slate failed")
        except Exception as e:
            errors.append(f"{eng}:{type(e).__name__}:{e}")
            continue
    raise RuntimeError("all render engines failed: " + " | ".join(errors)[:700])
