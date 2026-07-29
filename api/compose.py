from __future__ import annotations

import json
import re
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


def _esc(s: Any) -> str:
    return (
        str(s or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_cards_from_issue(
    issue: dict[str, Any],
    template_ids: list[str] | None = None,
    structure: list[str] | None = None,
) -> list[dict[str, Any]]:
    title = issue.get("title") or "이슈 브리핑"
    summary = issue.get("summary") or "핵심 내용을 짧게 정리합니다."
    # strip residual html entities noise
    summary = re.sub(r"&nbsp;?", " ", summary)
    summary = re.sub(r"\s+", " ", summary).strip()
    bullets = [b.strip() for b in re.split(r"[.!?。]\s+", summary) if b.strip()][:4]
    if len(bullets) < 2:
        bullets = [
            summary[:80],
            "관련 동향을 계속 추적해야 합니다.",
            "단기 이슈와 구조 변화를 구분해 보세요.",
        ]
    templates = template_ids or ["headline", "bullets", "quote", "cta"]
    cards: list[dict[str, Any]] = []
    for i, tid in enumerate(templates):
        if tid == "headline":
            cards.append(
                {
                    "id": f"c{i+1}",
                    "kind": "headline",
                    "title": title,
                    "subtitle": issue.get("source") or "실시간 이슈",
                    "kicker": "급상승" if issue.get("category") == "rising" else (issue.get("category") or "ISSUE"),
                }
            )
        elif tid == "bullets":
            cards.append({"id": f"c{i+1}", "kind": "bullets", "title": "핵심 브리핑", "bullets": bullets[:4]})
        elif tid == "chart":
            cards.append(
                {
                    "id": f"c{i+1}",
                    "kind": "chart",
                    "title": "한눈에 보기",
                    "left_label": "이전",
                    "right_label": "현재",
                    "left_value": "62",
                    "right_value": "88",
                    "unit": "관심도",
                }
            )
        elif tid == "quote":
            cards.append(
                {
                    "id": f"c{i+1}",
                    "kind": "quote",
                    "quote": bullets[0][:90],
                    "attribution": issue.get("source") or "Issue Feed",
                }
            )
        elif tid == "cta":
            cards.append(
                {
                    "id": f"c{i+1}",
                    "kind": "cta",
                    "title": "정리",
                    "body": "이 이슈의 다음 포인트를 짧게 메모해 두세요.",
                    "button": "전체 브리핑 보기",
                }
            )
        else:
            cards.append({"id": f"c{i+1}", "kind": "headline", "title": title, "subtitle": summary[:80]})
    struct = structure or ["hook", "body", "body", "close"]
    for i, c in enumerate(cards):
        c["structure"] = struct[i] if i < len(struct) else "body"
    return cards



def project_to_html(project: dict[str, Any]) -> str:
    """HTML composition for Hyperframes/Playwright render.

    Critical: NO viewport fit-scaling. Stage is exact design pixels so
    headless capture at data-width x data-height is not letterboxed/clipped.
    Card switching is seek-driven via window.__timelines for Hyperframes.
    """
    aspect = project.get("aspect_ratio") or "9:16"
    if aspect == "9:16":
        w, h = 1080, 1920
    elif aspect == "16:9":
        w, h = 1920, 1080
    else:
        w, h = 1080, 1080

    cards = project.get("cards") or []
    per = float(project.get("seconds_per_card") or 3.0)
    total = max(per * max(len(cards), 1), 6.0)
    motion = project.get("motion") or "zoom"
    title = project.get("title") or "Leo Card Motion"
    anim = {
        "cut": "cut",
        "zoom": "zoom",
        "kinetic": "kinetic",
        "slide": "slide",
        "remotion": "kinetic",
    }.get(motion, "zoom")

    # Fixed typography in design pixels (render-safe; no cqw/vw)
    if w >= h:  # landscape
        f_kicker, f_h1, f_h2, f_body, f_quote, pad = 28, 72, 56, 34, 52, 96
    else:  # portrait / square
        f_kicker, f_h1, f_h2, f_body, f_quote, pad = 30, 78, 58, 36, 56, 86

    def card_html(c: dict[str, Any], idx: int) -> str:
        start_t = idx * per
        kind = c.get("kind") or "headline"
        active = " is-on" if idx == 0 else ""
        common = (
            f'class="clip card card-{kind} m-{anim}{active}" '
            f'data-start="{start_t:.2f}" data-duration="{per:.2f}" data-track-index="1" '
            f'data-card-id="{_esc(c.get("id", ""))}"'
        )
        if kind == "headline":
            return (
                f"<section {common}>"
                f'<div class="kicker">{_esc(c.get("kicker") or "ISSUE")}</div>'
                f"<h1>{_esc(c.get('title'))}</h1>"
                f'<p class="sub">{_esc(c.get("subtitle"))}</p>'
                f"</section>"
            )
        if kind == "bullets":
            lis = "".join(f"<li>{_esc(b)}</li>" for b in (c.get("bullets") or [])[:5])
            return f"<section {common}><h2>{_esc(c.get('title') or '브리핑')}</h2><ul>{lis}</ul></section>"
        if kind == "chart":
            return (
                f"<section {common}><h2>{_esc(c.get('title') or '비교')}</h2>"
                f'<div class="chart">'
                f'<div class="bar"><span>{_esc(c.get("left_label"))}</span><strong>{_esc(c.get("left_value"))}</strong></div>'
                f'<div class="bar hi"><span>{_esc(c.get("right_label"))}</span><strong>{_esc(c.get("right_value"))}</strong></div>'
                f'</div><p class="unit">{_esc(c.get("unit") or "")}</p></section>'
            )
        if kind == "quote":
            return (
                f"<section {common}><blockquote>“{_esc(c.get('quote'))}”</blockquote>"
                f"<cite>— {_esc(c.get('attribution'))}</cite></section>"
            )
        return (
            f"<section {common}><h2>{_esc(c.get('title'))}</h2><p>{_esc(c.get('body'))}</p>"
            f'<div class="cta">{_esc(c.get("button") or "더보기")}</div></section>'
        )

    slides = "\n".join(card_html(c, i) for i, c in enumerate(cards))
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width={w}, height={h}, initial-scale=1"/>
  <title>{_esc(title)}</title>
  <style>
    html, body {{
      margin: 0; padding: 0;
      width: {w}px; height: {h}px;
      overflow: hidden;
      background: #0a0a0b;
      color: #f4f1ea;
      font-family: Pretendard, "Apple SD Gothic Neo", "Noto Sans KR", system-ui, sans-serif;
    }}
    #stage {{
      position: relative;
      width: {w}px;
      height: {h}px;
      overflow: hidden;
      background:
        radial-gradient(900px 520px at 80% 0%, rgba(241,90,36,.20), transparent 55%),
        #0a0a0b;
      /* NEVER scale in render composition */
      transform: none !important;
    }}
    .card {{
      position: absolute; inset: 0;
      display: flex;
      flex-direction: column;
      justify-content: center;
      box-sizing: border-box;
      padding: {pad}px;
      opacity: 0;
      visibility: hidden;
      pointer-events: none;
    }}
    .card.is-on {{
      opacity: 1;
      visibility: visible;
      pointer-events: auto;
    }}
    .kicker {{
      display: inline-block;
      font-size: {f_kicker}px;
      letter-spacing: .14em;
      color: #f15a24;
      font-weight: 700;
      margin-bottom: 28px;
      text-transform: uppercase;
    }}
    h1 {{
      font-size: {f_h1}px;
      line-height: 1.18;
      letter-spacing: -.03em;
      margin: 0 0 22px;
      font-weight: 780;
      word-break: keep-all;
      max-width: 100%;
    }}
    h2 {{
      font-size: {f_h2}px;
      line-height: 1.2;
      margin: 0 0 28px;
      letter-spacing: -.02em;
      word-break: keep-all;
    }}
    .sub, p, li, cite {{
      color: #b8b3a8;
      font-size: {f_body}px;
      line-height: 1.45;
      word-break: keep-all;
      margin: 0;
    }}
    ul {{ margin: 0; padding-left: 1.15em; }}
    li {{ margin: 0 0 18px; }}
    blockquote {{
      font-size: {f_quote}px;
      line-height: 1.28;
      margin: 0;
      color: #f4f1ea;
      font-weight: 650;
      word-break: keep-all;
    }}
    cite {{ display: block; margin-top: 28px; }}
    .chart {{ display: grid; gap: 18px; margin-top: 8px; }}
    .bar {{
      display: flex; justify-content: space-between; align-items: center;
      padding: 22px 26px;
      border: 1px solid rgba(244,241,234,.12);
      border-radius: 22px;
      background: #121214;
      font-size: {f_body}px;
    }}
    .bar.hi {{ border-color: rgba(241,90,36,.45); box-shadow: 0 0 0 1px rgba(241,90,36,.2); }}
    .bar strong {{ font-size: {int(f_h2*0.9)}px; color: #f15a24; }}
    .cta {{
      margin-top: 32px;
      display: inline-flex;
      padding: 18px 28px;
      border-radius: 999px;
      background: linear-gradient(180deg,#ff7a45,#f15a24);
      color: #fff;
      font-weight: 700;
      font-size: {f_body}px;
    }}
    .progress {{ position: absolute; left: 0; right: 0; bottom: 0; height: 6px; background: rgba(255,255,255,.08); }}
    .progress > i {{ display: block; height: 100%; width: 0; background: #f15a24; }}
    /* ===== MOTION PRESETS (must look different) ===== */
    .m-cut.is-on {{ animation: none; }}
    .m-cut .kicker {{ background:#f15a24; color:#111; padding:8px 14px; border-radius:8px; }}
    .theme-cut #stage {{ background:#0a0a0b; }}

    .m-zoom.is-on {{ animation: zoomIn .55s cubic-bezier(.2,.8,.2,1) both; }}
    .theme-zoom #stage {{
      background:
        radial-gradient(1200px 700px at 50% 40%, rgba(241,90,36,.35), transparent 50%),
        #070708;
    }}
    .m-zoom h1 {{ transform-origin: center; }}

    .m-kinetic.is-on {{ animation: kinIn .5s ease both; }}
    .theme-kinetic #stage {{
      background:
        linear-gradient(135deg, rgba(241,90,36,.25), transparent 40%),
        repeating-linear-gradient(-12deg, rgba(255,255,255,.03) 0 12px, transparent 12px 24px),
        #0a0a0b;
    }}
    .theme-kinetic .kicker {{
      border-left: 8px solid #f15a24; padding-left: 16px; letter-spacing: .28em;
    }}
    .theme-kinetic h1 {{
      text-transform: uppercase;
      letter-spacing: -.04em;
      text-shadow: 0 0 40px rgba(241,90,36,.35);
    }}
    .theme-kinetic h1::after {{
      content:""; display:block; width:42%; height:10px; margin-top:22px;
      background: linear-gradient(90deg,#f15a24,#ffb08f); border-radius:999px;
    }}

    .m-slide.is-on {{ animation: slideIn .55s cubic-bezier(.2,.8,.2,1) both; }}
    .theme-slide #stage {{
      background:
        linear-gradient(90deg, rgba(241,90,36,.22), transparent 45%),
        #0a0a0b;
    }}
    .theme-slide .card {{
      border-left: 14px solid #f15a24;
      padding-left: calc({pad}px + 10px);
    }}

    .theme-remotion #stage {{
      background:
        radial-gradient(900px 500px at 85% 0%, rgba(241,90,36,.30), transparent 55%),
        linear-gradient(160deg,#120b08 0%,#0a0a0b 45%,#0c1018 100%);
    }}
    .theme-remotion .kicker {{ color:#ffb08f; }}
    .theme-remotion .kicker::after {{ content:" · REMOTION"; opacity:.8; }}

    @keyframes zoomIn {{ from {{ transform: scale(1.18); filter: blur(2px); }} to {{ transform: scale(1); filter: none; }} }}
    @keyframes slideIn {{ from {{ transform: translateX(18%); opacity: 0; }} to {{ transform: none; opacity: 1; }} }}
    @keyframes kinIn {{ from {{ transform: translateY(40px); letter-spacing: .12em; }} to {{ transform: none; letter-spacing: normal; }} }}
  </style>
</head>
<body>
  <div id="stage" class="theme-{anim}"
       data-composition-id="leo-card-motion"
       data-start="0"
       data-duration="{total:.2f}"
       data-fps="30"
       data-width="{w}"
       data-height="{h}"
       data-motion="{anim}">
    {slides}
    <div class="progress"><i id="bar"></i></div>
  </div>
  <script>
    (function() {{
      const cards = Array.from(document.querySelectorAll('.card'));
      const per = {per:.2f};
      const total = {total:.2f};
      const bar = document.getElementById('bar');
      let current = -1;

      function showAt(timeSec) {{
        const t = Math.max(0, Math.min(total - 0.0001, Number(timeSec) || 0));
        const idx = cards.length ? Math.min(cards.length - 1, Math.floor(t / per)) : 0;
        if (idx !== current) {{
          current = idx;
          cards.forEach((c, i) => c.classList.toggle('is-on', i === idx));
        }}
        if (bar) bar.style.width = ((t / total) * 100).toFixed(3) + '%';
      }}

      // initial
      showAt(0);

      // Hyperframes seek API
      window.__timelines = window.__timelines || {{}};
      window.__timelines['leo-card-motion'] = {{
        paused: false,
        t: 0,
        pause() {{ this.paused = true; }},
        play() {{ this.paused = false; }},
        seek(t) {{ this.t = Number(t) || 0; showAt(this.t); }},
        progress(t) {{ this.seek(t); }},
      }};

      // Some runtimes call these hooks
      window.__hf = Object.assign(window.__hf || {{}}, {{ ready: true }});
      window.__hyperframes = window.__hyperframes || {{
        getVariables() {{ return {{}}; }},
      }};

      // Fallback wall-clock preview when opened directly in a browser tab
      // (Hyperframes render uses seek(); this keeps standalone HTML usable)
      const params = new URLSearchParams(location.search);
      const forceLive = params.get('live') === '1' || !window.chrome;
      let started = performance.now();
      function tick(now) {{
        // If external seek advanced time recently, don't fight it.
        const tl = window.__timelines['leo-card-motion'];
        if (tl && tl._external) {{
          requestAnimationFrame(tick);
          return;
        }}
        const t = ((now - started) / 1000) % total;
        showAt(t);
        requestAnimationFrame(tick);
      }}
      // Always run live clock; Hyperframes seek() still overrides current class each frame it seeks.
      requestAnimationFrame(tick);

      // Wrap seek to mark external control
      const tl = window.__timelines['leo-card-motion'];
      const rawSeek = tl.seek.bind(tl);
      tl.seek = function(t) {{
        this._external = true;
        rawSeek(t);
      }};
    }})();
  </script>
</body>
</html>"""



def save_project(project: dict[str, Any]) -> dict[str, Any]:
    pid = project.get("id") or uuid4().hex[:10]
    project["id"] = pid
    project["updated_at"] = datetime.now(timezone.utc).isoformat()
    if not project.get("created_at"):
        project["created_at"] = project["updated_at"]
    html = project_to_html(project)
    pdir = COMP / "projects" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "index.html").write_text(html, encoding="utf-8")
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
