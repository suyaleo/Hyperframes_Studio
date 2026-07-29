import React from "react";
import { AbsoluteFill, Sequence, interpolate, useCurrentFrame, useVideoConfig, spring } from "remotion";
import { z } from "zod";

export const cardMotionSchema = z.object({
  title: z.string().optional(),
  aspect_ratio: z.string().optional(),
  secondsPerCard: z.number(),
  cards: z.array(z.object({
    id: z.string().optional(), kind: z.string().optional(), title: z.string().optional(),
    subtitle: z.string().optional(), kicker: z.string().optional(), bullets: z.array(z.string()).optional(),
    quote: z.string().optional(), attribution: z.string().optional(), body: z.string().optional(),
    button: z.string().optional(), left_label: z.string().optional(), right_label: z.string().optional(),
    left_value: z.string().optional(), right_value: z.string().optional(), unit: z.string().optional(),
  })),
});

export type CardMotionProps = z.infer<typeof cardMotionSchema>;
type Card = CardMotionProps["cards"][number];

const palette = { bg: "#090b0e", panel: "#11151a", ink: "#f3f0e9", muted: "#a7afb8", faint: "#68717c", accent: "#ff6846", line: "rgba(243,240,233,.13)" };

const Slide: React.FC<{ card: Card; index: number; total: number }> = ({ card, index, total }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const portrait = height > width;
  const pad = portrait ? 88 : 100;
  const enter = spring({ frame, fps, config: { damping: 18, stiffness: 115, mass: 0.8 } });
  const opacity = interpolate(enter, [0, 1], [0, 1]);
  const y = interpolate(enter, [0, 1], [50, 0]);
  const progress = interpolate(frame, [0, fps * 0.5], [0, (index + 1) / total], { extrapolateRight: "clamp" });
  const kind = card.kind || "headline";
  const bodySize = portrait ? 36 : 31;
  const headingSize = portrait ? 72 : 62;

  return (
    <AbsoluteFill style={{
      backgroundColor: palette.bg,
      backgroundImage: "linear-gradient(rgba(255,255,255,.024) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.024) 1px,transparent 1px)",
      backgroundSize: "64px 64px", color: palette.ink,
      fontFamily: 'Pretendard, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif', padding: pad,
    }}>
      <div style={{ position: "absolute", left: pad, right: pad, top: pad, height: 1, background: palette.line }} />
      <div style={{ position: "absolute", right: pad, top: pad + 22, color: palette.accent, fontSize: 26, fontWeight: 800, letterSpacing: ".12em" }}>
        {String(index + 1).padStart(2, "0")}
      </div>
      <div style={{ marginTop: "auto", marginBottom: "auto", opacity, transform: `translateY(${y}px)` }}>
        <div style={{ color: palette.accent, fontSize: 25, fontWeight: 800, letterSpacing: ".16em", textTransform: "uppercase", marginBottom: 30 }}>
          {card.kicker || ({ bullets: "핵심 브리핑", chart: "팩트 체크", quote: "맥락", cta: "다음 단계" }[kind] || "ISSUE")}
        </div>
        {kind === "bullets" ? (
          <>
            <div style={{ fontSize: headingSize * 0.78, fontWeight: 800, letterSpacing: "-.035em", marginBottom: 34 }}>{card.title}</div>
            <div style={{ display: "grid", gap: 22 }}>
              {(card.bullets || []).slice(0, 4).map((bullet, i) => (
                <div key={i} style={{ display: "grid", gridTemplateColumns: "18px 1fr", gap: 18, alignItems: "start", color: palette.muted, fontSize: bodySize, lineHeight: 1.45 }}>
                  <span style={{ width: 15, height: 4, background: palette.accent, marginTop: bodySize * 0.66 }} />{bullet}
                </div>
              ))}
            </div>
          </>
        ) : kind === "quote" ? (
          <>
            <div style={{ fontSize: headingSize * 0.78, fontWeight: 750, lineHeight: 1.28, letterSpacing: "-.03em" }}>{card.quote}</div>
            <div style={{ marginTop: 34, color: palette.accent, fontSize: bodySize * 0.78 }}>{card.attribution}</div>
          </>
        ) : kind === "chart" ? (
          <>
            <div style={{ fontSize: headingSize * 0.78, fontWeight: 800, letterSpacing: "-.035em", marginBottom: 32 }}>{card.title}</div>
            <div style={{ display: "grid", gap: 1, background: palette.line }}>
              <FactRow label={card.left_label} value={card.left_value} size={bodySize} />
              <FactRow label={card.right_label} value={card.right_value} size={bodySize} />
            </div>
            <div style={{ marginTop: 22, color: palette.muted, fontSize: bodySize * 0.7 }}>{card.unit}</div>
          </>
        ) : kind === "cta" ? (
          <>
            <div style={{ fontSize: headingSize * 0.8, fontWeight: 800, lineHeight: 1.18, letterSpacing: "-.035em" }}>{card.title}</div>
            <div style={{ marginTop: 24, color: palette.muted, fontSize: bodySize, lineHeight: 1.5 }}>{card.body}</div>
            <div style={{ display: "inline-flex", marginTop: 42, padding: "18px 28px", border: `2px solid ${palette.accent}`, color: palette.accent, fontSize: bodySize * 0.82, fontWeight: 750 }}>
              {card.button || "원문 확인"}
            </div>
          </>
        ) : (
          <>
            <div style={{ fontSize: headingSize, fontWeight: 820, lineHeight: 1.16, letterSpacing: "-.045em", wordBreak: "keep-all" }}>{card.title}</div>
            <div style={{ marginTop: 34, paddingTop: 24, borderTop: `1px solid ${palette.line}`, color: palette.muted, fontSize: bodySize }}>{card.subtitle}</div>
          </>
        )}
      </div>
      <div style={{ position: "absolute", left: pad, bottom: pad * 0.62, color: palette.faint, fontSize: 17, letterSpacing: ".2em" }}>LEO / CARD STUDIO</div>
      <div style={{ position: "absolute", left: pad, right: pad, bottom: pad * 0.34, height: 4, background: "rgba(255,255,255,.08)" }}>
        <div style={{ height: "100%", width: `${progress * 100}%`, background: palette.accent }} />
      </div>
    </AbsoluteFill>
  );
};

const FactRow: React.FC<{ label?: string; value?: string; size: number }> = ({ label, value, size }) => (
  <div style={{ display: "grid", gridTemplateColumns: "1fr 1.5fr", alignItems: "center", gap: 20, padding: "29px 30px", background: palette.panel }}>
    <span style={{ color: palette.muted, fontSize: size * 0.76 }}>{label}</span>
    <strong style={{ color: palette.ink, fontSize: size, textAlign: "right", wordBreak: "keep-all" }}>{value}</strong>
  </div>
);

export const CardMotion: React.FC<CardMotionProps> = ({ cards, secondsPerCard }) => {
  const { fps } = useVideoConfig();
  const duration = Math.max(1, Math.round((secondsPerCard || 3) * fps));
  const list = cards || [];
  return (
    <AbsoluteFill style={{ background: palette.bg }}>
      {list.map((card, index) => (
        <Sequence key={card.id || String(index)} from={index * duration} durationInFrames={duration}>
          <Slide card={card} index={index} total={list.length || 1} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
