from __future__ import annotations

import json
import os
import shutil
import threading
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.briefing import BRIEFING_PRESETS, BriefingMode, get_briefing_preset
from api.compose import (
    ASPECT_VARIANTS,
    build_cards_from_issue,
    get_project,
    list_projects,
    project_to_html,
    save_project,
)
from api.omlx import OmlxError, generate_storyboard, get_omlx_status
from api.research import collect_research, get_research_bundle, list_research_bundles
from api.settings import (
    DEFAULT_PORT,
    DISPLAY_NAME,
    OUTPUT_DIR,
    PROJECTS_DIR,
    SERVICE_SLUG,
    STATIC_DATA_DIR,
    VERSION,
    WEB_DIR,
)
from api.trends import get_trends

WEB = WEB_DIR
OUT = OUTPUT_DIR
DATA = STATIC_DATA_DIR
ASPECT_ORDER = tuple(ASPECT_VARIANTS)
_RENDER_JOBS: dict[str, dict[str, Any]] = {}
_RENDER_JOBS_LOCK = threading.Lock()


def _has_playwright() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except Exception:
        return False


app = FastAPI(title=DISPLAY_NAME, version=VERSION)

app.mount("/static", StaticFiles(directory=str(WEB)), name="static")
app.mount("/output", StaticFiles(directory=str(OUT)), name="output")


class BuildIn(BaseModel):
    issue_id: str | None = None
    title: str | None = None
    summary: str | None = None
    category: str = "rising"
    template_ids: list[str] = Field(default_factory=lambda: ["headline", "bullets", "chart", "quote", "cta"])
    motion: str = "zoom"
    aspect_ratio: str = "9:16"
    seconds_per_card: float = 3.0
    structure: list[str] = Field(default_factory=lambda: ["hook", "body", "body", "body", "close"])


class RenderIn(BaseModel):
    project_id: str | None = None
    fps: int = 30
    engine: str | None = None
    aspect_ratio: str | None = None
    force: bool = False


class AspectIn(BaseModel):
    aspect_ratio: str


class ResearchIn(BaseModel):
    issue_id: str | None = None
    query: str | None = None
    category: str = "rising"
    briefing_mode: BriefingMode = "standard"
    max_sources: int | None = Field(default=None, ge=3, le=24)


class StoryboardIn(BaseModel):
    research_id: str
    template_ids: list[str] = Field(
        default_factory=lambda: ["headline", "bullets", "chart", "quote", "cta"],
        min_length=1,
    )
    briefing_mode: BriefingMode = "standard"
    motion: str = "zoom"
    aspect_ratio: str = "9:16"
    seconds_per_card: float | None = Field(default=None, ge=1.0, le=12.0)
    allow_fallback: bool = True


def _resolve_issue(issue_id: str | None, category: str) -> dict[str, Any] | None:
    trends = get_trends(category=category)
    items = trends.get("items") or []
    if issue_id:
        return next((item for item in items if item.get("id") == issue_id), None)
    return items[0] if items else None


def _fallback_storyboard_cards(bundle: dict[str, Any], target_count: int) -> list[dict[str, Any]]:
    evidence = bundle.get("evidence") or []
    if not evidence:
        return []
    query = str(bundle.get("query") or "Research briefing")
    first = evidence[0]
    cards: list[dict[str, Any]] = [
        {
            "id": "c1",
            "kind": "headline",
            "structure": "hook",
            "kicker": "RESEARCH DRAFT",
            "title": query,
            "subtitle": f"검토 가능한 근거 {len(evidence)}건",
            "citations": [first["id"]],
            "narration": "",
            "visual_query": "",
        }
    ]
    for index in range(max(0, target_count - 2)):
        item = evidence[index % len(evidence)]
        excerpt = str(item.get("excerpt") or "").strip()
        bullets = [part.strip() for part in excerpt.split(".") if part.strip()][:3]
        if not bullets:
            bullets = [str(item.get("title") or "근거 원문을 확인하세요.")]
        cards.append(
            {
                "id": f"c{len(cards) + 1}",
                "kind": "bullets",
                "structure": "body",
                "title": str(item.get("title") or "수집된 근거"),
                "bullets": bullets,
                "citations": [item["id"]],
                "narration": "",
                "visual_query": "",
            }
        )
    cards.append(
        {
            "id": f"c{len(cards) + 1}",
            "kind": "cta",
            "structure": "close",
            "title": "근거를 직접 검토하세요",
            "body": f"수집된 {len(evidence)}개 원문을 확인한 뒤 카드 문구와 나레이션을 확정하세요.",
            "button": "근거 번들 보기",
            "citations": [item["id"] for item in evidence[:2]],
            "narration": "",
            "visual_query": "",
        }
    )
    return cards


@app.get("/", response_class=HTMLResponse)
def index():
    return (WEB / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    timeline_configured = bool(
        (os.environ.get("LT_TIMELINE_URL") or "").strip()
        and (os.environ.get("LT_TIMELINE_TOKEN") or os.environ.get("LT_SINGLE_USER_TOKEN") or "").strip()
    )
    omlx_configured = bool(
        (os.environ.get("OMLX_BASE_URL") or "").strip()
        and (os.environ.get("OMLX_API_KEY") or "").strip()
        and (os.environ.get("OMLX_MODEL") or "").strip()
    )
    return {
        "ok": True,
        "service": SERVICE_SLUG,
        "version": VERSION,
        "engine": "hyperframes-compatible-html",
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "playwright": _has_playwright(),
        "npx": bool(shutil.which("npx")),
        "hyperframes": bool(shutil.which("hyperframes")),
        "omlx_configured": omlx_configured,
        "timeline_configured": timeline_configured,
        "default_engine": os.environ.get("HYPERFRAMES_DEFAULT_ENGINE", "hyperframes"),
        "timestamp": datetime.now(UTC).isoformat(),
    }


@app.get("/api/version")
def version():
    return {"service": SERVICE_SLUG, "version": VERSION}


@app.get("/api/ai/status")
def ai_status():
    return {"ok": True, "omlx": get_omlx_status()}


@app.get("/api/meta")
def meta():
    cats = json.loads((DATA / "categories.json").read_text(encoding="utf-8"))
    briefing_modes = [
        {"id": mode, **preset}
        for mode, preset in BRIEFING_PRESETS.items()
    ]
    return {"ok": True, **cats, "briefing_modes": briefing_modes}


@app.get("/api/trends")
def trends(category: str = "rising", force: bool = False):
    return get_trends(category=category, force=force)


@app.get("/api/research")
def research_list():
    return {"ok": True, "items": list_research_bundles()}


@app.get("/api/research/{research_id}")
def research_get(research_id: str):
    bundle = get_research_bundle(research_id)
    if not bundle:
        raise HTTPException(404, "research bundle not found")
    return {"ok": True, "research": bundle}


@app.post("/api/research")
def research_create(body: ResearchIn):
    selected_issue = _resolve_issue(body.issue_id, body.category) if body.issue_id else None
    query = (body.query or (selected_issue or {}).get("title") or "").strip()
    if not query:
        raise HTTPException(400, "query or issue required")
    try:
        bundle = collect_research(
            query,
            category=body.category,
            selected_issue=selected_issue,
            max_sources=body.max_sources,
            briefing_mode=body.briefing_mode,
        )
    except ValueError as error:
        raise HTTPException(400, str(error)) from error
    return {"ok": True, "research": bundle}


@app.get("/api/projects")
def projects():
    return {"ok": True, "items": list_projects()}


@app.get("/api/projects/{pid}")
def project_get(pid: str):
    p = get_project(pid)
    if not p:
        raise HTTPException(404, "project not found")
    return {"ok": True, "project": p}


def _package_artifact_path(url: str | None, expected_name: str) -> Path | None:
    """Resolve a generated /output artifact without accepting arbitrary paths."""
    name = Path(urlparse(str(url or "")).path).name
    if name != expected_name:
        return None
    candidate = OUT / name
    return candidate if candidate.is_file() else None


@app.get("/api/projects/{pid}/export-package")
def project_export_package(pid: str):
    project = get_project(pid)
    if not project:
        raise HTTPException(404, "project not found")

    variants = project.get("variants") or {}
    missing = [
        aspect
        for aspect in ASPECT_ORDER
        if (variants.get(aspect) or {}).get("render_status") != "ready"
    ]
    if missing:
        raise HTTPException(409, detail=f"render not ready: {', '.join(missing)}")

    root = f"hyperframes-{pid}"
    files: list[dict[str, Any]] = []
    resolved: list[tuple[str, Path, Path]] = []
    for aspect in ASPECT_ORDER:
        variant = variants[aspect]
        key = str(variant.get("key") or ASPECT_VARIANTS[aspect]["key"])
        html_path = _package_artifact_path(variant.get("preview_url"), f"{pid}-{key}.html")
        video_path = _package_artifact_path(variant.get("video_url"), f"{pid}-{key}.mp4")
        if not html_path or not video_path:
            raise HTTPException(409, detail=f"artifact missing: {aspect}")
        html_name = f"html/hyperframes-{key}.html"
        video_name = f"video/hyperframes-{key}.mp4"
        files.append(
            {
                "aspect_ratio": aspect,
                "label": variant.get("label"),
                "width": variant.get("width"),
                "height": variant.get("height"),
                "html": html_name,
                "video": video_name,
                "rendered_at": variant.get("rendered_at"),
            }
        )
        resolved.append((key, html_path, video_path))

    manifest = {
        "schema_version": 1,
        "project_id": pid,
        "title": project.get("title"),
        "exported_at": datetime.now(UTC).isoformat(),
        "duration_seconds": len(project.get("cards") or []) * float(project.get("seconds_per_card") or 3),
        "files": files,
    }
    archive = OUT / f"{pid}-hyperframes-package.zip"
    temporary = OUT / f".{archive.name}.{uuid4().hex}.tmp"
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as package:
        package.writestr(f"{root}/manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        package.writestr(f"{root}/project.json", json.dumps(project, ensure_ascii=False, indent=2))
        package.writestr(
            f"{root}/README.txt",
            "Hyperframes Studio export\n\n"
            "html/ 폴더에는 화면비별 독립 HTML 카드가, video/ 폴더에는 MP4 영상이 있습니다.\n"
            "manifest.json에서 해상도와 파일 매핑을 확인할 수 있습니다.\n",
        )
        research_id = project.get("research_bundle_id")
        research = get_research_bundle(str(research_id)) if research_id else None
        if research:
            package.writestr(f"{root}/research.json", json.dumps(research, ensure_ascii=False, indent=2))
        for key, html_path, video_path in resolved:
            package.write(html_path, f"{root}/html/hyperframes-{key}.html")
            package.write(video_path, f"{root}/video/hyperframes-{key}.mp4")
    temporary.replace(archive)
    return FileResponse(
        archive,
        media_type="application/zip",
        filename=f"hyperframes-{pid}-complete.zip",
    )


@app.post("/api/projects/build")
def project_build(body: BuildIn):
    # resolve issue from trends cache/list
    issue = {
        "title": body.title,
        "summary": body.summary,
        "category": body.category,
        "source": "manual",
        "id": body.issue_id or "manual",
    }
    if body.issue_id or not body.title:
        found = _resolve_issue(body.issue_id, body.category)
        if found:
            issue = found
    if not issue.get("title"):
        raise HTTPException(400, detail="title or issue required")
    cards = build_cards_from_issue(issue, template_ids=body.template_ids, structure=body.structure)
    project = {
        "id": uuid4().hex[:10],
        "title": issue.get("title"),
        "issue": issue,
        "cards": cards,
        "motion": body.motion,
        "aspect_ratio": body.aspect_ratio,
        "seconds_per_card": body.seconds_per_card,
        "status": "draft",
    }
    project = save_project(project)
    return {"ok": True, "project": project}


@app.post("/api/storyboards/generate")
def storyboard_generate(body: StoryboardIn):
    bundle = get_research_bundle(body.research_id)
    if not bundle:
        raise HTTPException(404, "research bundle not found")

    generation_warning = ""
    try:
        generated = generate_storyboard(bundle, body.template_ids, body.briefing_mode)
        cards = generated["cards"]
        title = generated["title"]
        summary = generated["summary"]
    except OmlxError as error:
        if not body.allow_fallback:
            raise HTTPException(503, detail=str(error)) from error
        evidence = bundle.get("evidence") or []
        first = evidence[0] if evidence else {}
        preset = get_briefing_preset(body.briefing_mode)
        cards = _fallback_storyboard_cards(bundle, preset["min_cards"])
        title = str(bundle.get("query") or "Research storyboard")
        summary = str(first.get("excerpt") or "수집된 자료를 바탕으로 만든 검토용 초안입니다.")
        generation_warning = str(error)
        generated = {
            "mode": "deterministic-fallback",
            "model": None,
            "usage": {},
        }

    project = {
        "id": uuid4().hex[:10],
        "title": title,
        "issue": {
            "title": bundle.get("query"),
            "summary": summary,
            "category": bundle.get("category"),
            "source": "Research bundle",
            "id": bundle.get("id"),
        },
        "research_bundle_id": bundle["id"],
        "cards": cards,
        "motion": body.motion,
        "aspect_ratio": body.aspect_ratio,
        "seconds_per_card": body.seconds_per_card or get_briefing_preset(body.briefing_mode)["seconds_per_card"],
        "briefing_mode": body.briefing_mode,
        "status": "draft",
        "generation": {
            "mode": generated["mode"],
            "model": generated.get("model"),
            "usage": generated.get("usage") or {},
            "warning": generation_warning,
            "at": datetime.now(UTC).isoformat(),
        },
    }
    project = save_project(project)
    return {
        "ok": True,
        "project": project,
        "generation": project["generation"],
        "research": bundle,
    }


@app.post("/api/projects/{pid}/save")
def project_save(pid: str, body: dict[str, Any]):
    cur = get_project(pid) or {"id": pid}
    cur.update(body or {})
    cur["id"] = pid
    cur = save_project(cur)
    return {"ok": True, "project": cur}


@app.get("/preview/{pid}", response_class=HTMLResponse)
def preview(pid: str):
    p = get_project(pid)
    if not p:
        raise HTTPException(404, "not found")
    html_path = PROJECTS_DIR / pid / "index.html"
    if html_path.exists():
        return html_path.read_text(encoding="utf-8")
    return project_to_html(p)


def _render_preference(project: dict[str, Any], requested: str | None) -> str:
    if requested:
        return requested
    if project.get("motion") == "remotion" or project.get("engine_hint") == "remotion-adapter":
        return "remotion"
    hint = project.get("engine_hint")
    return str(hint) if hint in {"hyperframes", "playwright", "remotion"} else "auto"


def _set_render_job(pid: str, **patch: Any) -> dict[str, Any]:
    with _RENDER_JOBS_LOCK:
        current = dict(_RENDER_JOBS.get(pid) or {})
        current.update(patch)
        current["project_id"] = pid
        current["updated_at"] = datetime.now(UTC).isoformat()
        _RENDER_JOBS[pid] = current
        return dict(current)


def _render_all_variants(pid: str, order: list[str], engine: str | None, fps: int) -> None:
    from api.render_engine import render_project as _render

    completed = 0
    total = len(order)
    errors: dict[str, str] = {}
    for aspect in order:
        project = get_project(pid)
        if not project:
            _set_render_job(pid, status="error", phase="중단", message="프로젝트를 찾을 수 없습니다.")
            return
        preferred = _render_preference(project, engine)
        variant = project["variants"][aspect]
        variant["render_status"] = "rendering"
        variant.pop("error", None)
        project["variants"][aspect] = variant
        project["status"] = "rendering"
        save_project(project, preserve_renders=True, refresh_compositions=False)
        _set_render_job(
            pid,
            status="running",
            phase=f"{aspect} 렌더",
            current_aspect=aspect,
            completed=completed,
            total=total,
            percent=round(completed / total * 100),
            message=f"{variant['label']} 영상을 {preferred} 엔진으로 렌더하고 있습니다.",
        )
        try:
            result = _render(pid, preferred=preferred, fps=fps, aspect_ratio=aspect)
            project = get_project(pid) or project
            rendered_at = datetime.now(UTC).isoformat()
            project["variants"][aspect].update(
                {
                    "render_status": "ready",
                    "video_url": result["video_url"],
                    "render": {**result, "at": rendered_at},
                    "rendered_at": rendered_at,
                }
            )
            project["variants"][aspect].pop("error", None)
            if project.get("aspect_ratio") == aspect:
                project["render"] = project["variants"][aspect]["render"]
            save_project(project, preserve_renders=True, refresh_compositions=False)
        except Exception as error:
            message = f"{type(error).__name__}: {error}"
            errors[aspect] = message
            project = get_project(pid) or project
            project["variants"][aspect]["render_status"] = "error"
            project["variants"][aspect]["error"] = message[-700:]
            save_project(project, preserve_renders=True, refresh_compositions=False)
        completed += 1

    project = get_project(pid)
    if project:
        ready = sum(1 for variant in project["variants"].values() if variant.get("render_status") == "ready")
        project["status"] = "rendered" if ready else "draft"
        save_project(project, preserve_renders=True, refresh_compositions=False)
    final_status = "success" if not errors else ("partial" if completed > len(errors) else "error")
    _set_render_job(
        pid,
        status=final_status,
        phase="완료" if not errors else "일부 완료",
        current_aspect=None,
        completed=completed,
        total=total,
        percent=100,
        errors=errors,
        message=(
            "세 가지 화면비 렌더가 모두 준비되었습니다."
            if not errors
            else f"{total - len(errors)}/{total}개 화면비 렌더 완료"
        ),
    )


@app.post("/api/projects/{pid}/aspect")
def set_aspect(pid: str, body: AspectIn):
    project = get_project(pid)
    if not project:
        raise HTTPException(404, "project not found")
    if body.aspect_ratio not in ASPECT_VARIANTS:
        raise HTTPException(400, "unsupported aspect ratio")
    project["aspect_ratio"] = body.aspect_ratio
    project = save_project(project, preserve_renders=True, refresh_compositions=False)
    return {"ok": True, "project": project, "variant": project["variants"][body.aspect_ratio]}


@app.post("/api/projects/{pid}/render-all")
def project_render_all(pid: str, body: RenderIn | None = None):
    body = body or RenderIn()
    project = get_project(pid)
    if not project:
        raise HTTPException(404, "project not found")
    with _RENDER_JOBS_LOCK:
        existing = dict(_RENDER_JOBS.get(pid) or {})
    if existing.get("status") == "running":
        return {"ok": True, "started": False, "job": existing, "project": project}
    candidates = [
        aspect
        for aspect in ASPECT_ORDER
        if body.force or project["variants"][aspect].get("render_status") != "ready"
    ]
    if not candidates:
        job = _set_render_job(
            pid,
            status="success",
            phase="완료",
            current_aspect=None,
            completed=len(ASPECT_ORDER),
            total=len(ASPECT_ORDER),
            percent=100,
            errors={},
            message="세 가지 화면비 렌더가 모두 준비되어 있습니다.",
        )
        return {"ok": True, "started": False, "job": job, "project": project}
    requested_first = (
        body.aspect_ratio if body.aspect_ratio in ASPECT_VARIANTS else project.get("aspect_ratio", "9:16")
    )
    first = requested_first if requested_first in candidates else candidates[0]
    order = [first, *(aspect for aspect in candidates if aspect != first)]
    job = _set_render_job(
        pid,
        status="running",
        phase="대기열 준비",
        current_aspect=first,
        completed=0,
        total=len(order),
        percent=0,
        errors={},
        message=f"{first} 화면비부터 렌더를 시작합니다.",
    )
    threading.Thread(
        target=_render_all_variants,
        args=(pid, order, body.engine, max(1, min(int(body.fps or 30), 60))),
        daemon=True,
        name=f"variant-render-{pid}",
    ).start()
    return {"ok": True, "started": True, "job": job, "project": project}


@app.get("/api/projects/{pid}/render-all/status")
def project_render_all_status(pid: str):
    project = get_project(pid)
    if not project:
        raise HTTPException(404, "project not found")
    with _RENDER_JOBS_LOCK:
        job = dict(_RENDER_JOBS.get(pid) or {})
    if not job:
        ready = sum(1 for variant in project["variants"].values() if variant.get("render_status") == "ready")
        job = {
            "project_id": pid,
            "status": "success" if ready == len(ASPECT_ORDER) else "idle",
            "phase": "완료" if ready == len(ASPECT_ORDER) else "대기",
            "completed": ready,
            "total": len(ASPECT_ORDER),
            "percent": round(ready / len(ASPECT_ORDER) * 100),
            "message": f"{ready}/{len(ASPECT_ORDER)}개 화면비 준비",
        }
    return {"ok": True, "job": job, "project": project}


@app.post("/api/projects/{pid}/render")
def project_render(pid: str, body: RenderIn | None = None):
    body = body or RenderIn()
    project = get_project(pid)
    if not project:
        raise HTTPException(404, "project not found")
    aspect = body.aspect_ratio if body.aspect_ratio in ASPECT_VARIANTS else project.get("aspect_ratio", "9:16")
    project = save_project(project, preserve_renders=True)
    try:
        from api.render_engine import render_project as _render

        result = _render(
            pid,
            preferred=_render_preference(project, body.engine),
            fps=int(body.fps or 30),
            aspect_ratio=aspect,
        )
    except Exception as error:
        raise HTTPException(500, detail=f"render failed: {error}") from error
    rendered_at = datetime.now(UTC).isoformat()
    project["variants"][aspect].update(
        {
            "render_status": "ready",
            "video_url": result["video_url"],
            "render": {**result, "at": rendered_at},
            "rendered_at": rendered_at,
        }
    )
    project["status"] = "rendered"
    if project.get("aspect_ratio") == aspect:
        project["render"] = project["variants"][aspect]["render"]
    project = save_project(project, preserve_renders=True)
    return {"ok": True, "project": project, "render": project["variants"][aspect]["render"]}


class CardUpdateIn(BaseModel):
    card_id: str
    patch: dict[str, Any] = Field(default_factory=dict)


class EngineIn(BaseModel):
    engine: str = "auto"  # auto|playwright|hyperframes|remotion


@app.post("/api/projects/{pid}/cards/update")
def update_card(pid: str, body: CardUpdateIn):
    p = get_project(pid)
    if not p:
        raise HTTPException(404, "project not found")
    cards = p.get("cards") or []
    found = False
    for c in cards:
        if str(c.get("id")) == str(body.card_id):
            c.update(body.patch or {})
            found = True
            break
    if not found:
        raise HTTPException(404, "card not found")
    p["cards"] = cards
    p = save_project(p)
    return {"ok": True, "project": p}


@app.post("/api/projects/{pid}/cards/reorder")
def reorder_cards(pid: str, body: dict[str, Any]):
    p = get_project(pid)
    if not p:
        raise HTTPException(404, "project not found")
    order = body.get("order") or []
    by = {str(c.get("id")): c for c in (p.get("cards") or [])}
    new_cards = [by[i] for i in order if i in by]
    # append missing
    for c in p.get("cards") or []:
        if c not in new_cards:
            new_cards.append(c)
    p["cards"] = new_cards
    p = save_project(p)
    return {"ok": True, "project": p}


@app.post("/api/projects/{pid}/engine")
def set_engine(pid: str, body: EngineIn):
    p = get_project(pid)
    if not p:
        raise HTTPException(404, "project not found")
    eng = (body.engine or "auto").lower()
    if eng not in {"auto", "playwright", "hyperframes", "remotion"}:
        raise HTTPException(400, detail="bad engine")
    p["engine_hint"] = "remotion-adapter" if eng == "remotion" else eng
    if eng == "remotion":
        p["motion"] = "kinetic"
        from api.remotion_adapter import export_remotion_project

        export_remotion_project(pid)
    p = save_project(p)
    return {"ok": True, "project": p}


@app.post("/api/projects/{pid}/push-timeline")
def push_timeline(pid: str):
    """Register composition into Leo Timeline as storyboard draft."""
    import httpx

    proj = get_project(pid)
    if not proj:
        raise HTTPException(404, "project not found")
    base = (os.environ.get("LT_TIMELINE_URL") or "").strip().rstrip("/")
    token = (os.environ.get("LT_TIMELINE_TOKEN") or os.environ.get("LT_SINGLE_USER_TOKEN") or "").strip()
    if not base:
        raise HTTPException(503, detail="LT_TIMELINE_URL not set")
    if not token:
        raise HTTPException(503, detail="LT_TIMELINE_TOKEN not set")
    payload = {
        "kind": "storyboard",
        "name": f"Hyperframes Studio · {(proj.get('title') or pid)[:80]}",
        "status": "draft",
        "summary": (proj.get("issue") or {}).get("summary") or proj.get("title") or "",
        "tags": [SERVICE_SLUG, "hyperframes", "storyboard"],
        "data": {
            "source": SERVICE_SLUG,
            "project_id": pid,
            "preview_url": proj.get("preview_url"),
            "cards_app_url": f"/?project={pid}",
            "cards_preview_url": proj.get("preview_url") or f"/output/{pid}.html",
            "cards_video_url": (proj.get("render") or {}).get("video_url"),
            "video_url": (proj.get("render") or {}).get("video_url"),
            "cards": proj.get("cards") or [],
            "aspect_ratio": proj.get("aspect_ratio"),
            "motion": proj.get("motion"),
        },
    }
    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            base + "/api/resources",
            headers={"X-LT-Token": token, "Content-Type": "application/json"},
            json=payload,
        )
        if r.status_code >= 400:
            raise HTTPException(502, detail=r.text[:300])
        data = r.json()
    return {"ok": True, "timeline": data}


@app.get("/favicon.ico")
def favicon():
    return HTMLResponse(status_code=204)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=DEFAULT_PORT, reload=False)
