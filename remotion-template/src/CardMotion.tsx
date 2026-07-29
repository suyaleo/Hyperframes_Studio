import React from "react";
import {
  AbsoluteFill,
  Sequence,
  interpolate,
  useCurrentFrame,
  useVideoConfig,
  spring,
} from "remotion";
import { z } from "zod";

export const cardMotionSchema = z.object({
  title: z.string().optional(),
  aspect_ratio: z.string().optional(),
  secondsPerCard: z.number(),
  cards: z.array(
    z.object({
      id: z.string().optional(),
      kind: z.string().optional(),
      title: z.string().optional(),
      subtitle: z.string().optional(),
      kicker: z.string().optional(),
      bullets: z.array(z.string()).optional(),
      quote: z.string().optional(),
      attribution: z.string().optional(),
      body: z.string().optional(),
      button: z.string().optional(),
      left_label: z.string().optional(),
      right_label: z.string().optional(),
      left_value: z.string().optional(),
      right_value: z.string().optional(),
      unit: z.string().optional(),
    })
  ),
});

export type CardMotionProps = z.infer<typeof cardMotionSchema>;
type Card = CardMotionProps["cards"][number];

const Slide: React.FC<{ card: Card; index: number }> = ({ card, index }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 16, stiffness: 140 } });
  const opacity = interpolate(enter, [0, 1], [0, 1]);
  const y = interpolate(enter, [0, 1], [90, 0]);
  const scale = interpolate(enter, [0, 1], [0.9, 1]);
  const bar = interpolate(frame, [0, 16], [0, 1], { extrapolateRight: "clamp" });
  const kind = card.kind || "headline";

  return (
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(900px 500px at 85% 0%, rgba(241,90,36,0.30), transparent 55%), linear-gradient(160deg,#120b08 0%,#0a0a0b 45%,#0c1018 100%)",
        color: "#f4f1ea",
        fontFamily: 'Pretendard, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif',
        padding: 96,
        justifyContent: "center",
        opacity,
        transform: `translateY(${y}px) scale(${scale})`,
      }}
    >
      <div
        style={{
          position: "absolute",
          left: 0,
          top: 0,
          bottom: 0,
          width: 16,
          background: "linear-gradient(180deg, #ff7a45, #f15a24)",
          transform: `scaleY(${bar})`,
          transformOrigin: "top",
        }}
      />
      <div
        style={{
          fontSize: 26,
          color: "#f15a24",
          letterSpacing: "0.18em",
          fontWeight: 800,
          marginBottom: 22,
        }}
      >
        {(card.kicker || kind || "CARD").toString().toUpperCase()} · REMOTION
      </div>
      {kind === "bullets" ? (
        <>
          <div style={{ fontSize: 56, fontWeight: 800, marginBottom: 28 }}>{card.title}</div>
          <ul style={{ margin: 0, paddingLeft: 34, fontSize: 34, color: "#b8b3a8", lineHeight: 1.45 }}>
            {(card.bullets || []).slice(0, 5).map((b, i) => (
              <li key={i} style={{ marginBottom: 16 }}>{b}</li>
            ))}
          </ul>
        </>
      ) : kind === "quote" ? (
        <>
          <div style={{ fontSize: 54, fontWeight: 700, lineHeight: 1.25 }}>“{card.quote}”</div>
          <div style={{ marginTop: 28, fontSize: 30, color: "#b8b3a8" }}>— {card.attribution}</div>
        </>
      ) : kind === "chart" ? (
        <>
          <div style={{ fontSize: 56, fontWeight: 800, marginBottom: 28 }}>{card.title}</div>
          <div style={{ display: "grid", gap: 18 }}>
            <Row label={card.left_label} value={card.left_value} />
            <Row label={card.right_label} value={card.right_value} hot />
          </div>
          <div style={{ marginTop: 18, color: "#b8b3a8", fontSize: 28 }}>{card.unit}</div>
        </>
      ) : kind === "cta" ? (
        <>
          <div style={{ fontSize: 56, fontWeight: 800 }}>{card.title}</div>
          <div style={{ marginTop: 20, fontSize: 34, color: "#b8b3a8" }}>{card.body}</div>
          <div
            style={{
              marginTop: 36,
              alignSelf: "flex-start",
              padding: "18px 28px",
              borderRadius: 999,
              background: "linear-gradient(180deg,#ff7a45,#f15a24)",
              fontWeight: 700,
              fontSize: 30,
            }}
          >
            {card.button || "더보기"}
          </div>
        </>
      ) : (
        <>
          <div style={{ fontSize: 72, fontWeight: 820, lineHeight: 1.15, letterSpacing: "-0.03em" }}>
            {card.title}
          </div>
          <div style={{ marginTop: 22, fontSize: 34, color: "#b8b3a8" }}>{card.subtitle}</div>
        </>
      )}
      <div style={{ position: "absolute", right: 40, bottom: 36, fontSize: 22, color: "#6a655c" }}>
        REMOTION #{index + 1}
      </div>
    </AbsoluteFill>
  );
};

const Row: React.FC<{ label?: string; value?: string; hot?: boolean }> = ({ label, value, hot }) => (
  <div
    style={{
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      padding: "22px 26px",
      borderRadius: 22,
      border: hot ? "1px solid rgba(241,90,36,0.5)" : "1px solid rgba(244,241,234,0.12)",
      background: "#121214",
      fontSize: 32,
    }}
  >
    <span>{label}</span>
    <b style={{ color: "#f15a24", fontSize: 48 }}>{value}</b>
  </div>
);

export const CardMotion: React.FC<CardMotionProps> = ({ cards, secondsPerCard }) => {
  const { fps } = useVideoConfig();
  const dur = Math.max(1, Math.round((secondsPerCard || 2.5) * fps));
  const list = cards || [];
  return (
    <AbsoluteFill style={{ background: "#0a0a0b" }}>
      {list.map((card, i) => (
        <Sequence key={card.id || String(i)} from={i * dur} durationInFrames={dur}>
          <Slide card={card} index={i} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
};
