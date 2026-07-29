from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from api.settings import COMPOSITIONS_DIR, OUTPUT_DIR, STATIC_DATA_DIR

OUT = OUTPUT_DIR
DATA = STATIC_DATA_DIR
COMP = COMPOSITIONS_DIR

ASPECT_VARIANTS: dict[str, dict[str, Any]] = {
    "9:16": {"key": "portrait", "width": 1080, "height": 1920, "label": "9:16 세로"},
    "16:9": {"key": "landscape", "width": 1920, "height": 1080, "label": "16:9 가로"},
    "1:1": {"key": "square", "width": 1080, "height": 1080, "label": "1:1 정방형"},
}


def aspect_spec(aspect_ratio: str | None) -> dict[str, Any]:
    return ASPECT_VARIANTS.get(str(aspect_ratio or "9:16"), ASPECT_VARIANTS["9:16"])


def _slug(s: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9가-힣_-]+", "-", s).strip("-")
    return (s[:40] or "card").lower()


def _esc(s: Any) -> str:
    return str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


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
                    "id": f"c{i + 1}",
                    "kind": "headline",
                    "title": title,
                    "subtitle": issue.get("source") or "실시간 이슈",
                    "kicker": "급상승" if issue.get("category") == "rising" else (issue.get("category") or "ISSUE"),
                }
            )
        elif tid == "bullets":
            cards.append({"id": f"c{i + 1}", "kind": "bullets", "title": "핵심 브리핑", "bullets": bullets[:4]})
        elif tid == "chart":
            cards.append(
                {
                    "id": f"c{i + 1}",
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
                    "id": f"c{i + 1}",
                    "kind": "quote",
                    "quote": bullets[0][:90],
                    "attribution": issue.get("source") or "Issue Feed",
                }
            )
        elif tid == "cta":
            cards.append(
                {
                    "id": f"c{i + 1}",
                    "kind": "cta",
                    "title": "정리",
                    "body": "이 이슈의 다음 포인트를 짧게 메모해 두세요.",
                    "button": "전체 브리핑 보기",
                }
            )
        else:
            cards.append({"id": f"c{i + 1}", "kind": "headline", "title": title, "subtitle": summary[:80]})
    struct = structure or ["hook", "body", "body", "close"]
    for i, c in enumerate(cards):
        c["structure"] = struct[i] if i < len(struct) else "body"
    return cards


def project_to_html(project: dict[str, Any], aspect_ratio: str | None = None) -> str:
    """HTML composition for Hyperframes/Playwright render.

    Critical: NO viewport fit-scaling. Stage is exact design pixels so
    headless capture at data-width x data-height is not letterboxed/clipped.
    Card switching is seek-driven via window.__timelines for Hyperframes.
    """
    aspect = aspect_ratio or project.get("aspect_ratio") or "9:16"
    spec = aspect_spec(aspect)
    w, h = int(spec["width"]), int(spec["height"])
    aspect_key = str(spec["key"])

    cards = project.get("cards") or []
    per = float(project.get("seconds_per_card") or 3.0)
    total = max(per * max(len(cards), 1), 6.0)
    motion = project.get("motion") or "zoom"
    title = project.get("title") or "Hyperframes Studio"
    anim = {
        "cut": "cut",
        "zoom": "zoom",
        "kinetic": "kinetic",
        "slide": "slide",
        "remotion": "kinetic",
    }.get(motion, "zoom")

    # Fixed typography in design pixels (render-safe; no cqw/vw).
    if aspect == "16:9":
        f_kicker, f_h1, f_h2, f_body, f_quote, pad = 26, 86, 58, 30, 62, 88
    elif aspect == "1:1":
        f_kicker, f_h1, f_h2, f_body, f_quote, pad = 25, 68, 50, 29, 49, 70
    else:
        f_kicker, f_h1, f_h2, f_body, f_quote, pad = 30, 82, 60, 35, 58, 86

    def card_html(c: dict[str, Any], idx: int) -> str:
        start_t = idx * per
        kind = c.get("kind") or "headline"
        structure = str(c.get("structure") or "body").upper()
        primary_text = str(c.get("title") or c.get("quote") or "")
        length_class = " text-xl" if len(primary_text) > 58 else (" text-long" if len(primary_text) > 36 else "")
        active = " is-on" if idx == 0 else ""
        scene_id = f"scene-{idx + 1:02d}-{_slug(str(c.get('id') or kind))}"
        common = (
            f'id="{scene_id}" class="clip card card-{kind} m-{anim}{length_class}{active}" '
            f'data-start="{start_t:.2f}" data-duration="{per:.2f}" data-track-index="1" '
            f'data-card-id="{_esc(c.get("id", ""))}"'
        )
        rail = (
            '<aside class="context-rail">'
            f'<span class="rail-index">{idx + 1:02d}</span>'
            f'<strong>{_esc(structure)}</strong>'
            f'<span data-layout-allow-occlusion>{_esc(kind.upper())}</span>'
            '<i aria-hidden="true" data-layout-allow-occlusion></i>'
            '</aside>'
        )

        def wrap(content: str) -> str:
            return (
                f'<section {common}><div class="scene-grid">'
                f'<div class="card-content">{content}</div>{rail}</div></section>'
            )

        if kind == "headline":
            return wrap(
                f'<div class="kicker">{_esc(c.get("kicker") or "ISSUE")}</div>'
                f"<h1>{_esc(c.get('title'))}</h1>"
                f'<p class="sub">{_esc(c.get("subtitle"))}</p>'
            )
        if kind == "bullets":
            lis = "".join(f"<li>{_esc(b)}</li>" for b in (c.get("bullets") or [])[:5])
            return wrap(f"<h2>{_esc(c.get('title') or '브리핑')}</h2><ul>{lis}</ul>")
        if kind == "chart":
            left_label = _esc(c.get("left_label"))
            left_value = _esc(c.get("left_value"))
            right_label = _esc(c.get("right_label"))
            right_value = _esc(c.get("right_value"))
            return wrap(
                f"<h2>{_esc(c.get('title') or '비교')}</h2>"
                f'<div class="chart">'
                f'<div class="bar"><span>{left_label}</span><strong>{left_value}</strong></div>'
                f'<div class="bar hi"><span>{right_label}</span><strong>{right_value}</strong></div>'
                f'</div><p class="unit">{_esc(c.get("unit") or "")}</p>'
            )
        if kind == "quote":
            return wrap(
                f"<blockquote>“{_esc(c.get('quote'))}”</blockquote>"
                f"<cite>— {_esc(c.get('attribution'))}</cite>"
            )
        return wrap(
            f"<h2>{_esc(c.get('title'))}</h2><p>{_esc(c.get('body'))}</p>"
            f'<div class="cta">{_esc(c.get("button") or "더보기")}</div>'
        )

    slides = "\n".join(card_html(c, i) for i, c in enumerate(cards))
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width={w}, height={h}, initial-scale=1"/>
  <title>{_esc(title)}</title>
  <style>
    @font-face {{ font-family: "Pretendard"; src: local("Pretendard"); font-display: swap; }}
    @font-face {{ font-family: "Apple SD Gothic Neo"; src: local("Apple SD Gothic Neo"); font-display: swap; }}
    @font-face {{ font-family: "Noto Sans KR"; src: local("Noto Sans KR"); font-display: swap; }}
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
        radial-gradient(900px 520px at 80% 0%, rgba(241,90,36,.20), rgba(241,90,36,0) 55%),
        #0a0a0b;
      /* NEVER scale in render composition */
      transform: none !important;
    }}
    #stage::before {{
      position: absolute;
      inset: 4.8%;
      border: 1px solid rgba(244,241,234,.09);
      content: "";
      pointer-events: none;
    }}
    #stage::after {{
      position: absolute;
      right: 0;
      bottom: 8%;
      width: 34%;
      height: 7px;
      background: #f15a24;
      content: "";
      opacity: .72;
      pointer-events: none;
    }}
    .card {{
      position: absolute; inset: 0;
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
    .scene-grid {{
      display: grid;
      width: 100%;
      height: 100%;
      min-width: 0;
      min-height: 0;
      align-items: center;
      gap: 54px;
    }}
    .card-content {{
      display: flex;
      min-width: 0;
      min-height: 0;
      flex-direction: column;
      justify-content: center;
      overflow: hidden;
    }}
    .context-rail {{
      display: flex;
      min-width: 0;
      align-self: stretch;
      flex-direction: column;
      justify-content: flex-end;
      border-left: 1px solid rgba(244,241,234,.13);
      padding: 30px 0 30px 38px;
      color: #817a71;
      font: 700 18px/1.2 SFMono-Regular, Menlo, monospace;
      letter-spacing: .11em;
    }}
    .context-rail .rail-index {{
      margin-bottom: auto;
      color: rgba(244,241,234,.10);
      font-size: 108px;
      font-weight: 800;
      letter-spacing: -.08em;
    }}
    .context-rail strong {{ color: #f15a24; font-size: 22px; }}
    .context-rail > span:not(.rail-index) {{ margin-top: 12px; }}
    .context-rail i {{ width: 64%; height: 5px; margin-top: 28px; background: #f15a24; }}
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
    .text-long h1 {{ font-size: {int(f_h1 * 0.86)}px; }}
    .text-xl h1 {{ font-size: {int(f_h1 * 0.72)}px; }}
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
    .text-long blockquote {{ font-size: {int(f_quote * 0.88)}px; }}
    .text-xl blockquote {{ font-size: {int(f_quote * 0.76)}px; }}
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
    .bar strong {{ font-size: {int(f_h2 * 0.9)}px; color: #f15a24; }}
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

    /* ===== ASPECT-SPECIFIC ART DIRECTION ===== */
    .aspect-landscape .scene-grid {{ grid-template-columns: minmax(0, 1.55fr) minmax(280px, .45fr); }}
    .aspect-landscape .card-content {{ max-width: 1180px; }}
    .aspect-landscape .card-bullets ul {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 18px 32px;
      padding: 0;
      list-style: none;
      counter-reset: briefing;
    }}
    .aspect-landscape .card-bullets li {{
      position: relative;
      min-height: 88px;
      margin: 0;
      border-top: 1px solid rgba(244,241,234,.14);
      padding: 18px 0 0 54px;
      counter-increment: briefing;
    }}
    .aspect-landscape .card-bullets li::before {{
      position: absolute;
      left: 0;
      color: #f15a24;
      font: 700 18px/1 SFMono-Regular, Menlo, monospace;
      content: counter(briefing, decimal-leading-zero);
    }}
    .aspect-landscape .chart {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}

    .aspect-portrait .scene-grid {{ grid-template-rows: minmax(0, 1fr) 260px; gap: 36px; }}
    .aspect-portrait .context-rail {{
      display: grid;
      grid-template-columns: auto 1fr auto;
      align-items: end;
      align-self: auto;
      border-top: 1px solid rgba(244,241,234,.13);
      border-left: 0;
      padding: 34px 0 0;
    }}
    .aspect-portrait .context-rail .rail-index {{ margin: 0 34px 0 0; font-size: 112px; }}
    .aspect-portrait .context-rail strong {{ align-self: center; }}
    .aspect-portrait .context-rail > span:not(.rail-index) {{ align-self: center; margin: 0; text-align: right; }}
    .aspect-portrait .context-rail i {{ position: absolute; right: {pad}px; bottom: 10.5%; width: 26%; }}

    .aspect-square .scene-grid {{ grid-template-rows: minmax(0, 1fr) 170px; gap: 28px; }}
    .aspect-square .card-content {{ justify-content: flex-start; padding-top: 9%; }}
    .aspect-square .context-rail {{
      display: grid;
      grid-template-columns: auto 1fr auto;
      align-items: end;
      align-self: auto;
      border-top: 1px solid rgba(244,241,234,.13);
      border-left: 0;
      padding: 24px 0 0;
    }}
    .aspect-square .context-rail .rail-index {{ margin: 0 28px 0 0; font-size: 78px; }}
    .aspect-square .context-rail strong {{ align-self: center; }}
    .aspect-square .context-rail > span:not(.rail-index) {{ align-self: center; margin: 0; text-align: right; }}
    .aspect-square .context-rail i {{ position: absolute; right: {pad}px; bottom: 10%; width: 24%; }}
    .aspect-square .card-bullets li {{ margin-bottom: 12px; }}
    .aspect-square .card-quote .card-content {{ justify-content: center; padding-top: 0; }}
    /* ===== MOTION PRESETS (must look different) ===== */
    .m-cut.is-on {{ animation: none; }}
    .m-cut .kicker {{ background:#f15a24; color:#111; padding:8px 14px; border-radius:8px; }}
    .theme-cut #stage {{ background:#0a0a0b; }}

    .m-zoom.is-on {{ animation: none; }}
    .theme-zoom #stage {{
      background:
        radial-gradient(1200px 700px at 50% 40%, rgba(241,90,36,.35), rgba(241,90,36,0) 50%),
        #070708;
    }}
    .m-zoom h1 {{ transform-origin: center; }}

    .m-kinetic.is-on {{ animation: none; }}
    .theme-kinetic #stage {{
      background:
        linear-gradient(135deg, rgba(241,90,36,.25), rgba(241,90,36,0) 40%),
        repeating-linear-gradient(-12deg, rgba(255,255,255,.03) 0 12px, rgba(255,255,255,0) 12px 24px),
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

    .m-slide.is-on {{ animation: none; }}
    .theme-slide #stage {{
      background:
        linear-gradient(90deg, rgba(241,90,36,.22), rgba(241,90,36,0) 45%),
        #0a0a0b;
    }}
    .theme-slide .card {{
      border-left: 14px solid #f15a24;
      padding-left: calc({pad}px + 10px);
    }}

    .theme-remotion #stage {{
      background:
        radial-gradient(900px 500px at 85% 0%, rgba(241,90,36,.30), rgba(241,90,36,0) 55%),
        linear-gradient(160deg,#120b08 0%,#0a0a0b 45%,#0c1018 100%);
    }}
    .theme-remotion .kicker {{ color:#ffb08f; }}
    .theme-remotion .kicker::after {{ content:" · REMOTION"; opacity:.8; }}

    @keyframes zoomIn {{
      from {{ transform: scale(1.18); filter: blur(2px); }}
      to {{ transform: scale(1); filter: none; }}
    }}
    @keyframes slideIn {{
      from {{ transform: translateX(18%); opacity: 0; }}
      to {{ transform: none; opacity: 1; }}
    }}
    @keyframes kinIn {{
      from {{ transform: translateY(40px); letter-spacing: .12em; }}
      to {{ transform: none; letter-spacing: normal; }}
    }}
  </style>
</head>
<body>
  <div id="stage" class="theme-{anim} aspect-{aspect_key}"
       data-composition-id="hyperframes-studio"
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
      const stage = document.getElementById('stage');
      const motion = stage ? stage.dataset.motion || 'zoom' : 'zoom';
      const bar = document.getElementById('bar');
      const params = new URLSearchParams(location.search);
      const requestedCard = Number(params.get('card'));
      const fixedPreview = params.get('preview') === '1' && Number.isFinite(requestedCard);
      const embeddedPreview = fixedPreview || params.get('live') === '1';
      let current = -1;

      function fitEmbeddedPreview() {{
        if (!embeddedPreview || !stage) return;
        const scale = Math.min(window.innerWidth / {w}, window.innerHeight / {h});
        const scaledWidth = {w} * scale;
        const scaledHeight = {h} * scale;
        document.documentElement.style.width = '100vw';
        document.documentElement.style.height = '100vh';
        document.body.style.width = '100vw';
        document.body.style.height = '100vh';
        stage.style.setProperty('transform', `scale(${{scale}})`, 'important');
        stage.style.transformOrigin = 'top left';
        stage.style.marginLeft = `${{Math.max(0, (window.innerWidth - scaledWidth) / 2)}}px`;
        stage.style.marginTop = `${{Math.max(0, (window.innerHeight - scaledHeight) / 2)}}px`;
      }}

      fitEmbeddedPreview();
      if (embeddedPreview) window.addEventListener('resize', fitEmbeddedPreview);

      function showAt(timeSec) {{
        const t = Math.max(0, Math.min(total - 0.0001, Number(timeSec) || 0));
        const idx = cards.length
          ? (fixedPreview
            ? Math.max(0, Math.min(cards.length - 1, requestedCard))
            : Math.min(cards.length - 1, Math.floor(t / per)))
          : 0;
        const local = fixedPreview || motion === 'cut'
          ? 1
          : Math.min(1, Math.max(0, (t - idx * per) / 0.42));
        if (idx !== current) {{
          current = idx;
        }}
        cards.forEach((c, i) => {{
          const incoming = i === idx;
          const outgoing = !fixedPreview && idx > 0 && i === idx - 1 && local < 1;
          c.classList.toggle('is-on', incoming || outgoing);
          if (incoming) {{
            c.style.opacity = String(local);
            if (motion === 'slide') {{
              c.style.transform = `translate3d(${{(1 - local) * 10}}%, 0, 0)`;
            }} else if (motion === 'kinetic') {{
              c.style.transform = `translate3d(${{(1 - local) * 1.6}}%, ${{(1 - local) * 48}}px, 0)`;
            }} else {{
              c.style.transform = `translate3d(0, ${{(1 - local) * 14}}px, 0) scale(${{0.97 + local * 0.03}})`;
            }}
          }} else if (outgoing) {{
            c.style.opacity = String(1 - local);
            if (motion === 'slide') {{
              c.style.transform = `translate3d(${{-local * 5}}%, 0, 0)`;
            }} else if (motion === 'kinetic') {{
              c.style.transform = `translate3d(0, ${{-local * 24}}px, 0)`;
            }} else {{
              c.style.transform = `translate3d(0, ${{-local * 8}}px, 0) scale(${{1 - local * 0.012}})`;
            }}
          }} else {{
            c.style.opacity = '0';
            c.style.transform = 'none';
          }}
        }});
        if (bar) bar.style.width = ((t / total) * 100).toFixed(3) + '%';
      }}

      // initial
      showAt(0);

      // Hyperframes seek API
      window.__timelines = window.__timelines || {{}};
      window.__timelines['hyperframes-studio'] = {{
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

    }})();
  </script>
</body>
</html>"""


def _write_text_atomic(path: Path, content: str) -> None:
    """Replace generated artifacts without exposing a partially-written file."""
    temp = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temp.write_text(content, encoding="utf-8")
    temp.replace(path)


def save_project(
    project: dict[str, Any],
    *,
    preserve_renders: bool = False,
    refresh_compositions: bool = True,
) -> dict[str, Any]:
    pid = project.get("id") or uuid4().hex[:10]
    project["id"] = pid
    project["updated_at"] = datetime.now(UTC).isoformat()
    if not project.get("created_at"):
        project["created_at"] = project["updated_at"]
    active_aspect = str(project.get("aspect_ratio") or "9:16")
    if active_aspect not in ASPECT_VARIANTS:
        active_aspect = "9:16"
    project["aspect_ratio"] = active_aspect
    pdir = COMP / "projects" / pid
    pdir.mkdir(parents=True, exist_ok=True)
    existing_variants = project.get("variants") if isinstance(project.get("variants"), dict) else {}
    legacy_render = project.get("render") if isinstance(project.get("render"), dict) else {}
    variants: dict[str, Any] = {}

    for aspect, spec in ASPECT_VARIANTS.items():
        key = str(spec["key"])
        variant_dir = pdir / "variants" / key
        variant_dir.mkdir(parents=True, exist_ok=True)
        variant_html = variant_dir / "index.html"
        out_html = OUT / f"{pid}-{key}.html"
        if refresh_compositions or not variant_html.exists() or not out_html.exists():
            html = project_to_html(project, aspect_ratio=aspect)
            _write_text_atomic(variant_html, html)
            _write_text_atomic(out_html, html)

        previous = existing_variants.get(aspect) if isinstance(existing_variants.get(aspect), dict) else {}
        if preserve_renders and not previous and aspect == active_aspect and legacy_render.get("video_url"):
            previous = {
                "render_status": "ready",
                "video_url": legacy_render.get("video_url"),
                "render": legacy_render,
            }
        render_status = str(previous.get("render_status") or "pending") if preserve_renders else "pending"
        entry = {
            "aspect_ratio": aspect,
            "key": key,
            "label": spec["label"],
            "width": int(spec["width"]),
            "height": int(spec["height"]),
            "preview_url": f"/output/{pid}-{key}.html",
            "composition_path": f"compositions/projects/{pid}/variants/{key}/index.html",
            "render_status": render_status,
        }
        if preserve_renders:
            for field in ("video_url", "render", "error", "rendered_at"):
                if previous.get(field) is not None:
                    entry[field] = previous[field]
        variants[aspect] = entry

    active = variants[active_aspect]
    legacy_comp = pdir / "index.html"
    legacy_out = OUT / f"{pid}.html"
    if refresh_compositions or not legacy_comp.exists() or not legacy_out.exists():
        active_variant = pdir / "variants" / str(active["key"]) / "index.html"
        active_html = active_variant.read_text(encoding="utf-8")
        _write_text_atomic(legacy_comp, active_html)
        _write_text_atomic(legacy_out, active_html)
    project["variants"] = variants
    project["preview_url"] = active["preview_url"]
    project["composition_path"] = active["composition_path"]
    if active.get("render"):
        project["render"] = active["render"]
    elif not preserve_renders:
        project.pop("render", None)
    _write_text_atomic(pdir / "project.json", json.dumps(project, ensure_ascii=False, indent=2))
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
    project = json.loads(pj.read_text(encoding="utf-8"))
    if not isinstance(project.get("variants"), dict):
        project = save_project(project, preserve_renders=True)
    return project
