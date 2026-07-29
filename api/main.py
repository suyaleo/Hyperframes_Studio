from __future__ import annotations
import os
import json, subprocess, shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from trends import get_trends
from compose import build_cards_from_issue, save_project, list_projects, get_project, project_to_html, issue_title_and_source

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
OUT = ROOT / "output"
DATA = ROOT / "data"
OUT.mkdir(exist_ok=True)

def _has_playwright() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except Exception:
        return False

app = FastAPI(title="Leo Card Studio", version="0.6.0")

app.mount("/static", StaticFiles(directory=str(WEB)), name="static")
app.mount("/output", StaticFiles(directory=str(OUT)), name="output")


class BuildIn(BaseModel):
    issue_id: Optional[str] = None
    title: Optional[str] = None
    summary: Optional[str] = None
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


@app.get("/", response_class=HTMLResponse)
def index():
    return (WEB / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
def health():
    return {
        "ok": True,
        "service": "leo-card-motion",
        "version": "0.6.0",
        "engine": "hyperframes-compatible-html",
        "ffmpeg": bool(shutil.which("ffmpeg")),
        "playwright": _has_playwright(),
        "npx": bool(shutil.which("npx")),
        "hyperframes": bool(shutil.which("hyperframes")),
        "default_engine": os.environ.get("LCM_DEFAULT_ENGINE", "hyperframes"),

        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/meta")
def meta():
    cats = json.loads((DATA / "categories.json").read_text(encoding="utf-8"))
    return {"ok": True, **cats}


@app.get("/api/trends")
def trends(category: str = "rising", force: bool = False):
    return get_trends(category=category, force=force)


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
    issue = {"title": body.title, "summary": body.summary, "category": body.category, "source": "manual", "id": body.issue_id or "manual"}
    if body.issue_id or not body.title:
        tr = get_trends(category=body.category)
        found = None
        if body.issue_id:
            found = next((x for x in tr.get("items") or [] if x.get("id") == body.issue_id), None)
        if not found and (tr.get("items") or []):
            found = tr["items"][0]
        if found:
            issue = found
    if not issue.get("title"):
        raise HTTPException(400, detail="title or issue required")
    cards = build_cards_from_issue(issue, template_ids=body.template_ids, structure=body.structure)
    project_title, _ = issue_title_and_source(issue)
    project = {
        "id": uuid4().hex[:10],
        "title": project_title,
        "issue": issue,
        "cards": cards,
        "motion": body.motion,
        "aspect_ratio": body.aspect_ratio,
        "seconds_per_card": body.seconds_per_card,
        "status": "draft",
    }
    project = save_project(project)
    return {"ok": True, "project": project}


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
    html_path = ROOT / "compositions" / "projects" / pid / "index.html"
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
    preferred = "auto"
    # allow engine override via body.project_id misuse no - use fps only; optional query later
    try:
        from render_engine import render_project as _render
        # if motion is remotion special
        pref = (body.engine if getattr(body, "engine", None) else None) or (
            "remotion" if (p.get("motion") == "remotion" or p.get("engine_hint") == "remotion-adapter")
            else (p.get("engine_hint") if p.get("engine_hint") in {"hyperframes","playwright","remotion"} else "auto")
        )
        result = _render(pid, preferred=pref, fps=int(getattr(body, "fps", None) or 30))
    except Exception as e:
        raise HTTPException(500, detail=f"render failed: {e}")
    p["status"] = "rendered"
    p["render"] = {
        **result,
        "at": datetime.now(timezone.utc).isoformat(),
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
    p["status"] = "draft"
    p["render"] = None
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
    p["status"] = "draft"
    p["render"] = None
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
    p["status"] = "draft"
    p["render"] = None
    if eng == "remotion":
        p["motion"] = "kinetic"
        from remotion_adapter import export_remotion_project
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
    base = (os.environ.get("LT_TIMELINE_URL") or "http://leo-timeline-web:8000").rstrip("/")
    token = (os.environ.get("LT_TIMELINE_TOKEN") or os.environ.get("LT_SINGLE_USER_TOKEN") or "").strip()
    if not token:
        raise HTTPException(503, detail="LT_TIMELINE_TOKEN not set")
    payload = {
        "kind": "storyboard",
        "name": f"CardMotion · {(proj.get('title') or pid)[:80]}",
        "status": "draft",
        "summary": (proj.get("issue") or {}).get("summary") or proj.get("title") or "",
        "tags": ["leo-card-motion", "hyperframes", "storyboard"],
        "data": {
            "source": "leo-card-motion",
            "project_id": pid,
            "preview_url": proj.get("preview_url"),
            "cards_app_url": f"/cards/?project={pid}",
            "cards_preview_url": f"/cards{proj.get('preview_url') or f'/output/{pid}.html'}",
            "cards_video_url": (f"/cards{(proj.get('render') or {}).get('video_url')}" if (proj.get('render') or {}).get('video_url') else None),
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


# ensure imports path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8770, reload=False)
