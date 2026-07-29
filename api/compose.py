from __future__ import annotations

import json
import re
from html import unescape
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


def _clean_text(value: Any, limit: int | None = None) -> str:
    text = unescape(str(value or ""))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbs(?:p)?;?", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if limit and len(text) > limit:
        text = text[: max(1, limit - 1)].rstrip(" ,·-") + "…"
    return text


def issue_title_and_source(issue: dict[str, Any]) -> tuple[str, str]:
    raw_title = _clean_text(issue.get("title")) or "이슈 브리핑"
    feed_source = _clean_text(issue.get("source"))
    title, publisher = raw_title, feed_source
    if " - " in raw_title:
        candidate_title, candidate_source = raw_title.rsplit(" - ", 1)
        if 1 < len(candidate_source) <= 40:
            title, publisher = candidate_title.strip(), candidate_source.strip()
    generic_sources = {"google 뉴스", "google news", "rising", "economy", "it", "politics", "life", "manual"}
    if publisher.lower() in generic_sources:
        publisher = "Issue Feed"
    return _clean_text(title, 86), _clean_text(publisher, 42) or "Issue Feed"


def build_cards_from_issue(
    issue: dict[str, Any],
    template_ids: list[str] | None = None,
    structure: list[str] | None = None,
) -> list[dict[str, Any]]:
    title, publisher = issue_title_and_source(issue)
    summary = _clean_text(issue.get("summary")) or title
    sentences = [_clean_text(part, 74) for part in re.split(r"(?<=[.!?。])\s+|[•·]\s*", summary) if _clean_text(part)]
    bullets = sentences[:4]
    if len(bullets) < 2 and summary != title:
        bullets.insert(0, _clean_text(title, 74))
    if len(bullets) < 2:
        bullets.append(f"{publisher}에서 전한 주요 이슈입니다.")
    category_labels = {
        "rising": "실시간 이슈", "economy": "경제", "it": "테크",
        "politics": "정치", "life": "라이프",
    }
    category = category_labels.get(str(issue.get("category") or "").lower(), _clean_text(issue.get("category")) or "이슈")
    published = _clean_text(issue.get("published"), 44)
    templates = template_ids or ["headline", "bullets", "quote", "cta"]
    cards: list[dict[str, Any]] = []
    for i, tid in enumerate(templates):
        if tid == "headline":
            cards.append(
                {
                    "id": f"c{i+1}",
                    "kind": "headline",
                    "title": title,
                    "subtitle": publisher,
                    "kicker": category,
                }
            )
        elif tid == "bullets":
            cards.append({"id": f"c{i+1}", "kind": "bullets", "title": "핵심 브리핑", "bullets": bullets[:4]})
        elif tid == "chart":
            cards.append(
                {
                    "id": f"c{i+1}",
                    "kind": "chart",
                    "title": "이 이슈의 기준 정보",
                    "left_label": "분류",
                    "right_label": "출처",
                    "left_value": category,
                    "right_value": publisher,
                    "unit": published or "피드에 공개된 정보를 기준으로 구성했습니다.",
                }
            )
        elif tid == "quote":
            cards.append(
                {
                    "id": f"c{i+1}",
                    "kind": "quote",
                    "quote": _clean_text(bullets[0], 110),
                    "attribution": f"출처 요약 · {publisher}",
                }
            )
        elif tid == "cta":
            cards.append(
                {
                    "id": f"c{i+1}",
                    "kind": "cta",
                    "title": "맥락까지 확인하세요",
                    "body": "제목만으로 판단하기 전에 원문에서 배경과 최신 내용을 확인하세요.",
                    "button": "원문 확인",
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
            f'data-card-id="{_esc(c.get("id", ""))}" data-index="{idx + 1:02d}"'
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
                f"<section {common}><blockquote>{_esc(c.get('quote'))}</blockquote>"
                f"<cite>{_esc(c.get('attribution'))}</cite></section>"
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
      background: #090b0e;
      color: #f4f1ea;
      font-family: Pretendard, "Apple SD Gothic Neo", "Noto Sans KR", system-ui, sans-serif;
    }}
    #stage {{
      position: relative;
      width: {w}px;
      height: {h}px;
      overflow: hidden;
      background:
        linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px),
        #090b0e;
      background-size: 64px 64px;
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
    .card::before {{
      content: attr(data-index);
      position: absolute; top: {pad}px; right: {pad}px;
      color: #ff6846; font-size: {f_kicker}px; font-weight: 800;
      letter-spacing: .08em;
    }}
    .card::after {{
      content: "LEO / CARD STUDIO";
      position: absolute; left: {pad}px; bottom: {int(pad * .62)}px;
      color: #68717c; font-size: {int(f_kicker * .58)}px;
      letter-spacing: .20em;
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
      color: #ff6846;
      font-weight: 700;
      margin-bottom: 28px;
      text-transform: uppercase;
    }}
    h1 {{
      font-size: {f_h1}px;
      line-height: 1.18;
      letter-spacing: -.03em;
      margin: 0 0 22px;
      font-weight: 800;
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
      color: #a7afb8;
      font-size: {f_body}px;
      line-height: 1.45;
      word-break: keep-all;
      margin: 0;
    }}
    ul {{ margin: 0; padding: 0; list-style: none; }}
    li {{ margin: 0 0 22px; padding-left: 34px; position: relative; }}
    li::before {{ content:""; position:absolute; left:0; top:.72em; width:14px; height:4px; background:#ff6846; }}
    blockquote {{
      font-size: {f_quote}px;
      line-height: 1.28;
      margin: 0;
      color: #f4f1ea;
      font-weight: 650;
      word-break: keep-all;
    }}
    cite {{ display: block; margin-top: 34px; color:#ff6846; font-style:normal; }}
    .chart {{ display: grid; gap: 1px; margin-top: 12px; background:rgba(244,241,234,.12); }}
    .bar {{
      display: flex; justify-content: space-between; align-items: center;
      padding: 28px 30px;
      background: #11151a;
      font-size: {f_body}px;
    }}
    .bar.hi {{ background:#14191f; }}
    .bar strong {{ max-width:62%; text-align:right; font-size: {int(f_body*1.08)}px; color: #f4f1ea; word-break:keep-all; }}
    .unit {{ margin-top:22px; font-size:{int(f_body*.72)}px; }}
    .cta {{
      margin-top: 32px;
      display: inline-flex;
      padding: 18px 28px;
      border: 2px solid #ff6846;
      color: #ff6846;
      font-weight: 700;
      font-size: {f_body}px;
    }}
    .progress {{ position: absolute; left: {pad}px; right: {pad}px; bottom: {int(pad*.35)}px; height: 4px; background: rgba(255,255,255,.08); }}
    .progress > i {{ display: block; height: 100%; width: 0; background: #ff6846; }}
    /* ===== MOTION PRESETS (must look different) ===== */
    .m-cut.is-on {{ animation: none; }}
    .m-cut .kicker {{ border-left:10px solid #ff6846; padding-left:18px; }}
    #stage.theme-cut {{ background:#090b0e; }}

    .m-zoom.is-on {{ animation: zoomIn .55s cubic-bezier(.2,.8,.2,1) both; }}
    #stage.theme-zoom {{
      background:
        radial-gradient(1200px 700px at 72% 26%, rgba(255,104,70,.14), transparent 50%),
        #090b0e;
    }}
    .m-zoom h1 {{ transform-origin: center; }}

    .m-kinetic.is-on {{ animation: kinIn .5s ease both; }}
    #stage.theme-kinetic {{
      background:
        linear-gradient(145deg, rgba(255,104,70,.12), transparent 42%), #090b0e;
    }}
    .theme-kinetic .kicker {{
      border-left: 8px solid #ff6846; padding-left: 16px; letter-spacing: .24em;
    }}
    .theme-kinetic h1 {{
      text-transform: uppercase;
      letter-spacing: -.04em;
      text-shadow: 0 0 40px rgba(255,104,70,.20);
    }}
    .theme-kinetic h1::after {{
      content:""; display:block; width:42%; height:10px; margin-top:22px;
      background: #ff6846;
    }}

    .m-slide.is-on {{ animation: slideIn .55s cubic-bezier(.2,.8,.2,1) both; }}
    #stage.theme-slide {{
      background:
        linear-gradient(90deg, rgba(255,104,70,.12), transparent 45%), #090b0e;
    }}
    .theme-slide .card {{
      border-left: 14px solid #ff6846;
      padding-left: calc({pad}px + 10px);
    }}

    #stage.theme-remotion {{
      background:
        radial-gradient(900px 500px at 80% 8%, rgba(255,104,70,.16), transparent 55%), #090b0e;
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
