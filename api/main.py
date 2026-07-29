from __future__ import annotations

import json
import os
import shutil
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from api.compose import build_cards_from_issue, get_project, list_projects, project_to_html, save_project
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


class ResearchIn(BaseModel):
    issue_id: str | None = None
    query: str | None = None
    category: str = "rising"
    max_sources: int = Field(default=8, ge=3, le=12)


class StoryboardIn(BaseModel):
    research_id: str
    template_ids: list[str] = Field(default_factory=lambda: ["headline", "bullets", "chart", "quote", "cta"])
    motion: str = "zoom"
    aspect_ratio: str = "9:16"
    seconds_per_card: float = Field(default=3.0, ge=1.0, le=12.0)
    allow_fallback: bool = True


def _resolve_issue(issue_id: str | None, category: str) -> dict[str, Any] | None:
    trends = get_trends(category=category)
    items = trends.get("items") or []
    if issue_id:
        return next((item for item in items if item.get("id") == issue_id), None)
    return items[0] if items else None


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
    return {"ok": True, **cats}


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
        generated = generate_storyboard(bundle, body.template_ids)
        cards = generated["cards"]
        title = generated["title"]
        summary = generated["summary"]
    except OmlxError as error:
        if not body.allow_fallback:
            raise HTTPException(503, detail=str(error)) from error
        evidence = bundle.get("evidence") or []
        first = evidence[0] if evidence else {}
        fallback_issue = {
            "title": bundle.get("query"),
            "summary": first.get("excerpt") or "수집된 자료를 바탕으로 만든 검토용 초안입니다.",
            "source": first.get("source") or "Research bundle",
            "category": bundle.get("category"),
        }
        cards = build_cards_from_issue(fallback_issue, template_ids=body.template_ids)
        citation = first.get("id")
        for card in cards:
            card["citations"] = [citation] if citation else []
            card["narration"] = ""
            card["visual_query"] = ""
        title = str(bundle.get("query") or "Research storyboard")
        summary = str(fallback_issue["summary"])
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
        "seconds_per_card": body.seconds_per_card,
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


@app.post("/api/projects/{pid}/render")
def project_render(pid: str, body: RenderIn | None = None):
    body = body or RenderIn()
    p = get_project(pid)
    if not p:
        raise HTTPException(404, "project not found")
    # ensure composition exists
    save_project(p)
    # allow engine override via body.project_id misuse no - use fps only; optional query later
    try:
        from api.render_engine import render_project as _render

        # if motion is remotion special
        pref = (body.engine if getattr(body, "engine", None) else None) or (
            "remotion"
            if (p.get("motion") == "remotion" or p.get("engine_hint") == "remotion-adapter")
            else (p.get("engine_hint") if p.get("engine_hint") in {"hyperframes", "playwright", "remotion"} else "auto")
        )
        result = _render(pid, preferred=pref, fps=int(getattr(body, "fps", None) or 30))
    except Exception as e:
        raise HTTPException(500, detail=f"render failed: {e}")
    p["status"] = "rendered"
    p["render"] = {
        **result,
        "at": datetime.now(UTC).isoformat(),
        "preview_url": p.get("preview_url") or f"/output/{pid}.html",
    }
    save_project(p)
    return {"ok": True, "project": p, "render": p["render"]}


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
