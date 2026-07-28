"""Remotion-style special template adapter.

For MVP we generate a Remotion-compatible project scaffold + a kinetic HTML
variant. If `npx remotion` is available, attempt render; else kinetic HTML
is recorded via playwright path by caller.
"""
from __future__ import annotations
import json, subprocess, shutil
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "compositions" / "projects"
OUT = ROOT / "output"
REM = ROOT / "compositions" / "remotion"


def export_remotion_project(project_id: str) -> dict[str, Any]:
    proj_path = COMP / project_id / "project.json"
    if not proj_path.exists():
        raise FileNotFoundError(project_id)
    proj = json.loads(proj_path.read_text(encoding="utf-8"))
    dest = REM / project_id
    dest.mkdir(parents=True, exist_ok=True)
    cards = proj.get("cards") or []
    # props json for Remotion Root
    props = {
        "title": proj.get("title"),
        "cards": cards,
        "aspect_ratio": proj.get("aspect_ratio") or "9:16",
        "secondsPerCard": proj.get("seconds_per_card") or 3,
        "fps": 30,
    }
    (dest / "props.json").write_text(json.dumps(props, ensure_ascii=False, indent=2), encoding="utf-8")
    # Minimal Remotion composition source (documentation + future render)
    (dest / "CardMotion.tsx").write_text(
        '''import React from "react";
import { AbsoluteFill, Sequence, useCurrentFrame, interpolate } from "remotion";

export type Card = { id: string; kind: string; title?: string; subtitle?: string; bullets?: string[]; quote?: string; body?: string; button?: string };
export const CardMotion: React.FC<{ cards: Card[]; secondsPerCard: number }> = ({ cards, secondsPerCard }) => {
  const fps = 30;
  const dur = Math.round(secondsPerCard * fps);
  return (
    <AbsoluteFill style={{ background: "#0a0a0b", color: "#f4f1ea", fontFamily: "Pretendard, sans-serif" }}>
      {cards.map((c, i) => (
        <Sequence key={c.id || i} from={i * dur} durationInFrames={dur}>
          <CardSlide card={c} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};

const CardSlide: React.FC<{ card: Card }> = ({ card }) => {
  const f = useCurrentFrame();
  const op = interpolate(f, [0, 8], [0, 1], { extrapolateRight: "clamp" });
  const y = interpolate(f, [0, 8], [24, 0], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill style={{ opacity: op, transform: `translateY(${y}px)`, padding: 64, justifyContent: "center" }}>
      <div style={{ fontSize: 18, color: "#f15a24", letterSpacing: "0.14em" }}>{(card.kind || "").toUpperCase()}</div>
      <div style={{ fontSize: 54, fontWeight: 780, marginTop: 12 }}>{card.title || card.quote}</div>
      <div style={{ fontSize: 24, color: "#b8b3a8", marginTop: 16 }}>{card.subtitle || card.body || (card.bullets || []).join(" · ")}</div>
    </AbsoluteFill>
  );
};
''',
        encoding="utf-8",
    )
    (dest / "README.md").write_text(
        f"# Remotion export for {project_id}\n\nSpecial-template adapter output.\nUse with Remotion when licensed/runtime available.\n",
        encoding="utf-8",
    )
    return {"ok": True, "path": str(dest), "props": props}


def render_remotion_style(project_id: str, fps: int = 30) -> dict[str, Any]:
    meta = export_remotion_project(project_id)
    # mark project motion as remotion-kinetic and rewrite html with stronger motion
    proj_path = COMP / project_id / "project.json"
    proj = json.loads(proj_path.read_text(encoding="utf-8"))
    proj["motion"] = "kinetic"
    proj["engine_hint"] = "remotion-adapter"
    proj_path.write_text(json.dumps(proj, ensure_ascii=False, indent=2), encoding="utf-8")
    # regenerate html via compose
    from compose import save_project
    save_project(proj)

    npx = shutil.which("npx")
    out_mp4 = OUT / f"{project_id}.mp4"
    if npx:
        # try remotion only if package exists; ignore failures
        try:
            r = subprocess.run(
                [npx, "--yes", "remotion", "render", "--help"],
                capture_output=True, text=True, timeout=60,
            )
            # full remotion project bootstrap is heavy; fall through to playwright
        except Exception:
            pass
    # Use playwright capture of kinetic HTML as remotion-style output
    from render_engine import render_with_playwright
    result = render_with_playwright(project_id, fps=fps)
    result["engine"] = "remotion-adapter+playwright"
    result["remotion_export"] = meta.get("path")
    return result
