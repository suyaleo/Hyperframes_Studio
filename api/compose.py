from __future__ import annotations
import json, re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
DATA = ROOT / "data"
COMP = ROOT / "compositions"
OUT.mkdir(exist_ok=True)
(COMP / "projects").mkdir(parents=True, exist_ok=True)

def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9가-힣_-]+", "-", s).strip("-")
    return (s[:40] or "card").lower()

def build_cards_from_issue(issue: dict[str, Any], template_ids: list[str] | None = None, structure: list[str] | None = None) -> list[dict[str, Any]]:
    title = issue.get("title") or "이슈 브리핑"
    summary = issue.get("summary") or "핵심 내용을 짧게 정리합니다."
    bullets = [b.strip() for b in re.split(r"[.!?。]\s+", summary) if b.strip()][:4]
    if len(bullets) < 2:
        bullets = [summary[:80], "시장과 산업 파급 가능성을 주시해야 합니다.", "단기 변동보다 구조 변화가 중요합니다."]
    templates = template_ids or ["headline", "bullets", "quote", "cta"]
    cards = []
    for i, tid in enumerate(templates):
        if tid == "headline":
            cards.append({"id": f"c{i+1}", "kind": "headline", "title": title, "subtitle": issue.get("source") or "실시간 이슈", "kicker": "급상승" if issue.get("category")=="rising" else (issue.get("category") or "ISSUE")})
        elif tid == "bullets":
            cards.append({"id": f"c{i+1}", "kind": "bullets", "title": "핵심 브리핑", "bullets": bullets[:4]})
        elif tid == "chart":
            cards.append({"id": f"c{i+1}", "kind": "chart", "title": "한눈에 보기", "left_label": "이전", "right_label": "현재", "left_value": "62", "right_value": "88", "unit": "관심도"})
        elif tid == "quote":
            cards.append({"id": f"c{i+1}", "kind": "quote", "quote": bullets[0][:90], "attribution": issue.get("source") or "Issue Feed"})
        elif tid == "cta":
            cards.append({"id": f"c{i+1}", "kind": "cta", "title": "정리", "body": "이 이슈의 다음 변수는 정책·공급·수요의 교차점입니다.", "button": "전체 브리핑 보기"})
        else:
            cards.append({"id": f"c{i+1}", "kind": "headline", "title": title, "subtitle": summary[:80]})
    # ensure structure tags
    struct = structure or ["hook", "body", "body", "close"]
    for i, c in enumerate(cards):
        c["structure"] = struct[i] if i < len(struct) else "body"
    return cards

def project_to_html(project: dict[str, Any]) -> str:
    aspect = project.get("aspect_ratio") or "9:16"
    w, h = (1080, 1920) if aspect == "9:16" else ((1920, 1080) if aspect == "16:9" else (1080, 1080))
    cards = project.get("cards") or []
    per = float(project.get("seconds_per_card") or 3.0)
    total = max(per * max(len(cards), 1), 6.0)
    motion = project.get("motion") or "zoom"
    title = project.get("title") or "Leo Card Motion"

    def card_html(c: dict[str, Any], idx: int) -> str:
        start = idx * per
        kind = c.get("kind") or "headline"
        common = f'class="clip card card-{kind}" data-start="{start:.2f}" data-duration="{per:.2f}" data-track-index="1" data-card-id="{c.get("id","")}"'
        if kind == "headline":
            return f'<section {common}><div class="kicker">{_esc(c.get("kicker") or "ISSUE")}</div><h1>{_esc(c.get("title"))}</h1><p class="sub">{_esc(c.get("subtitle"))}</p></section>'
        if kind == "bullets":
            lis = "".join(f"<li>{_esc(b)}</li>" for b in (c.get("bullets") or [])[:5])
            return f'<section {common}><h2>{_esc(c.get("title") or "브리핑")}</h2><ul>{lis}</ul></section>'
        if kind == "chart":
            return f'''<section {common}><h2>{_esc(c.get("title") or "비교")}</h2>
              <div class="chart"><div class="bar"><span>{_esc(c.get("left_label"))}</span><strong>{_esc(c.get("left_value"))}</strong></div>
              <div class="bar hi"><span>{_esc(c.get("right_label"))}</span><strong>{_esc(c.get("right_value"))}</strong></div></div>
              <p class="unit">{_esc(c.get("unit") or "")}</p></section>'''
        if kind == "quote":
            return f'<section {common}><blockquote>“{_esc(c.get("quote"))}”</blockquote><cite>— {_esc(c.get("attribution"))}</cite></section>'
        return f'<section {common}><h2>{_esc(c.get("title"))}</h2><p>{_esc(c.get("body"))}</p><div class="cta">{_esc(c.get("button") or "더보기")}</div></section>'

    slides = "\n".join(card_html(c, i) for i, c in enumerate(cards))
    anim = {
        "cut": "opacity",
        "zoom": "zoom",
        "kinetic": "kinetic",
        "slide": "slide",
    }.get(motion, "zoom")

    return f'''<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>{_esc(title)}</title>
  <style>
    html,body{{margin:0;background:#0a0a0b;color:#f4f1ea;font-family:Pretendard,Apple SD Gothic Neo,Noto Sans KR,sans-serif;overflow:hidden}}
    #stage{{position:relative;width:{w}px;height:{h}px;margin:0 auto;background:radial-gradient(800px 500px at 80% 0%, rgba(241,90,36,.18), transparent 55%),#0a0a0b;overflow:hidden}}
    .card{{position:absolute;inset:0;display:flex;flex-direction:column;justify-content:center;padding:{int(w*0.08)}px;opacity:0;transform:scale(1.04); box-sizing:border-box}}
    .card.active{{opacity:1;transform:none}}
    .kicker{{display:inline-block;font-size:{int(w*0.028)}px;letter-spacing:.14em;color:#f15a24;font-weight:700;margin-bottom:18px;text-transform:uppercase}}
    h1{{font-size:{int(w*0.072)}px;line-height:1.15;letter-spacing:-.03em;margin:0 0 16px;font-weight:780}}
    h2{{font-size:{int(w*0.05)}px;margin:0 0 20px;letter-spacing:-.02em}}
    .sub,p,li,cite{{color:#b8b3a8;font-size:{int(w*0.032)}px;line-height:1.45}}
    ul{{margin:0;padding-left:1.1em}} li{{margin:0 0 12px}}
    blockquote{{font-size:{int(w*0.048)}px;line-height:1.3;margin:0;color:#f4f1ea;font-weight:650}}
    cite{{display:block;margin-top:18px}}
    .chart{{display:grid;gap:14px;margin-top:8px}}
    .bar{{display:flex;justify-content:space-between;align-items:center;padding:16px 18px;border:1px solid rgba(244,241,234,.12);border-radius:16px;background:#121214}}
    .bar.hi{{border-color:rgba(241,90,36,.45);box-shadow:0 0 0 1px rgba(241,90,36,.2)}}
    .bar strong{{font-size:{int(w*0.05)}px;color:#f15a24}}
    .cta{{margin-top:22px;display:inline-flex;padding:14px 22px;border-radius:999px;background:linear-gradient(180deg,#ff7a45,#f15a24);color:#fff;font-weight:700}}
    .progress{{position:absolute;left:0;right:0;bottom:0;height:4px;background:rgba(255,255,255,.08)}}
    .progress>i{{display:block;height:100%;width:0;background:#f15a24}}
    /* motion helpers */
    .m-zoom.active{{animation:zoom {per:.2f}s ease both}}
    .m-slide.active{{animation:slide {per:.2f}s ease both}}
    .m-kinetic.active h1,.m-kinetic.active h2{{animation:kin .7s ease both}}
    @keyframes zoom{{from{{transform:scale(1.08);opacity:0}} 12%{{opacity:1}} to{{transform:scale(1)}}}}
    @keyframes slide{{from{{transform:translateX(40px);opacity:0}} to{{transform:none;opacity:1}}}}
    @keyframes kin{{from{{letter-spacing:.12em;opacity:0}} to{{letter-spacing:-.02em;opacity:1}}}}
  </style>
</head>
<body>
  <div id="stage" data-composition-id="leo-card-motion" data-start="0" data-duration="{total:.2f}" data-fps="30" data-width="{w}" data-height="{h}" data-motion="{anim}">
    {slides}
    <div class="progress"><i id="bar"></i></div>
  </div>
  <script>
    const cards=[...document.querySelectorAll('.card')];
    const per={per:.2f}; const total={total:.2f}; const motion="{anim}";
    cards.forEach(c=>c.classList.add('m-'+motion));
    let t0=performance.now();
    function frame(now){{
      const t=((now-t0)/1000)%total;
      const idx=Math.min(cards.length-1, Math.floor(t/per));
      cards.forEach((c,i)=>c.classList.toggle('active', i===idx));
      const bar=document.getElementById('bar'); if(bar) bar.style.width=((t/total)*100).toFixed(2)+'%';
      requestAnimationFrame(frame);
    }}
    requestAnimationFrame(frame);
    // Hyperframes-friendly paused timeline stub
    window.__timelines = window.__timelines || {{}};
    const api = {{
      paused: true,
      t: 0,
      pause(){{ this.paused = true; }},
      play(){{ this.paused = false; }},
      seek(t){{
        this.t = Math.max(0, Number(t)||0);
        const idx=Math.min(cards.length-1, Math.floor(this.t/per));
        cards.forEach((c,i)=>{{
          const on = i===idx;
          c.classList.toggle('active', on);
          c.style.opacity = on ? '1' : '0';
          c.style.visibility = on ? 'visible' : 'hidden';
        }});
        const bar=document.getElementById('bar'); if(bar) bar.style.width=((this.t/total)*100).toFixed(2)+'%';
      }}
    }};
    window.__timelines['leo-card-motion'] = api;
    // Hyperframes runtime readiness hook
    window.__hf = window.__hf || {{ ready: true }};
    window.__hyperframes = window.__hyperframes || {{ getVariables(){{ return {{}}; }} }};
  </script>
</body>
</html>'''

def _esc(s: Any) -> str:
    return (str(s or "")
            .replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
            .replace('"',"&quot;"))

def save_project(project: dict[str, Any]) -> dict[str, Any]:
    pid = project.get("id") or uuid4().hex[:10]
    project["id"] = pid
    project["updated_at"] = datetime.now(timezone.utc).isoformat()
    if not project.get("created_at"):
        project["created_at"] = project["updated_at"]
    html = project_to_html(project)
    pdir = COMP / "projects" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    (pdir / "index.html").write_text(html, encoding="utf-8")
    # also publish copy under output for static serving
    out_html = OUT / f"{pid}.html"
    out_html.write_text(html, encoding="utf-8")
    project["preview_url"] = f"/output/{pid}.html"
    project["composition_path"] = f"compositions/projects/{pid}/index.html"
    (pdir / "project.json").write_text(json.dumps(project, ensure_ascii=False, indent=2), encoding="utf-8")
    return project

def list_projects() -> list[dict[str, Any]]:
    root = COMP / "projects"
    items = []
    if not root.exists():
        return items
    for d in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        pj = d / "project.json"
        if pj.exists():
            try:
                items.append(json.loads(pj.read_text(encoding="utf-8")))
            except Exception:
                pass
    return items[:50]

def get_project(pid: str) -> dict[str, Any] | None:
    pj = COMP / "projects" / pid / "project.json"
    if not pj.exists():
        return None
    return json.loads(pj.read_text(encoding="utf-8"))
