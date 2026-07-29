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
  const { fps, width, height } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 16, stiffness: 140 } });
  const opacity = interpolate(enter, [0, 1], [0, 1]);
  const y = interpolate(enter, [0, 1], [90, 0]);
  const scale = interpolate(enter, [0, 1], [0.9, 1]);
  const bar = interpolate(frame, [0, 16], [0, 1], { extrapolateRight: "clamp" });
  const kind = card.kind || "headline";
  const landscape = width > height;
  const square = width === height;
  const padding = landscape ? 88 : square ? 70 : 86;
  const titleSize = landscape ? 86 : square ? 68 : 82;
  const headingSize = landscape ? 58 : square ? 50 : 60;
  const bodySize = landscape ? 30 : square ? 29 : 35;
  const quoteSize = landscape ? 62 : square ? 49 : 58;

  const content = kind === "bullets" ? (
    <>
      <div style={{ fontSize: headingSize, fontWeight: 800, marginBottom: 28 }}>{card.title}</div>
      <ul
        style={{
          display: landscape ? "grid" : "block",
          gridTemplateColumns: landscape ? "1fr 1fr" : undefined,
          columnGap: landscape ? 34 : undefined,
          margin: 0,
          paddingLeft: landscape ? 0 : 34,
          listStyle: landscape ? "none" : undefined,
          fontSize: bodySize,
          color: "#c4bdb3",
          lineHeight: 1.45,
        }}
      >
        {(card.bullets || []).slice(0, 5).map((bullet, bulletIndex) => (
          <li
            key={bulletIndex}
            style={{
              minHeight: landscape ? 86 : undefined,
              marginBottom: 16,
              borderTop: landscape ? "1px solid rgba(244,241,234,0.14)" : undefined,
              paddingTop: landscape ? 16 : undefined,
            }}
          >
            {bullet}
          </li>
        ))}
      </ul>
    </>
  ) : kind === "quote" ? (
    <>
      <div style={{ fontSize: quoteSize, fontWeight: 700, lineHeight: 1.25 }}>“{card.quote}”</div>
      <div style={{ marginTop: 28, fontSize: bodySize, color: "#c4bdb3" }}>— {card.attribution}</div>
    </>
  ) : kind === "chart" ? (
    <>
      <div style={{ fontSize: headingSize, fontWeight: 800, marginBottom: 28 }}>{card.title}</div>
      <div style={{ display: "grid", gridTemplateColumns: landscape ? "1fr 1fr" : "1fr", gap: 18 }}>
        <Row label={card.left_label} value={card.left_value} bodySize={bodySize} valueSize={headingSize} />
        <Row label={card.right_label} value={card.right_value} bodySize={bodySize} valueSize={headingSize} hot />
      </div>
      <div style={{ marginTop: 18, color: "#c4bdb3", fontSize: bodySize }}>{card.unit}</div>
    </>
  ) : kind === "cta" ? (
    <>
      <div style={{ fontSize: headingSize, fontWeight: 800 }}>{card.title}</div>
      <div style={{ marginTop: 20, fontSize: bodySize, color: "#c4bdb3", lineHeight: 1.45 }}>{card.body}</div>
      <div
        style={{
          marginTop: 36,
          alignSelf: "flex-start",
          padding: "18px 28px",
          borderRadius: 999,
          background: "linear-gradient(180deg,#ff8a57,#f15a24)",
          fontWeight: 700,
          fontSize: bodySize,
        }}
      >
        {card.button || "더보기"}
      </div>
    </>
  ) : (
    <>
      <div style={{ fontSize: titleSize, fontWeight: 820, lineHeight: 1.15, letterSpacing: "-0.03em" }}>
        {card.title}
      </div>
      <div style={{ marginTop: 22, fontSize: bodySize, color: "#c4bdb3", lineHeight: 1.45 }}>{card.subtitle}</div>
    </>
  );

  return (
    <AbsoluteFill
      style={{
        background:
          "radial-gradient(900px 500px at 85% 0%, rgba(241,90,36,0.30), transparent 55%), linear-gradient(160deg,#120b08 0%,#0a0a0b 45%,#0c1018 100%)",
        color: "#f4f1ea",
        fontFamily: 'Pretendard, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif',
        padding,
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
      <div
        style={{
          display: "grid",
          gridTemplateColumns: landscape ? "minmax(0, 1.55fr) minmax(260px, 0.45fr)" : "1fr",
          gridTemplateRows: landscape ? "1fr" : square ? "minmax(0, 1fr) 150px" : "minmax(0, 1fr) 240px",
          gap: landscape ? 54 : 32,
          minHeight: 0,
          flex: 1,
        }}
      >
        <div style={{ display: "flex", minWidth: 0, flexDirection: "column", justifyContent: "center", overflow: "hidden" }}>
          {content}
        </div>
        <div
          style={{
            display: "flex",
            flexDirection: landscape ? "column" : "row",
            alignItems: landscape ? "stretch" : "flex-end",
            justifyContent: "space-between",
            borderLeft: landscape ? "1px solid rgba(244,241,234,0.14)" : undefined,
            borderTop: landscape ? undefined : "1px solid rgba(244,241,234,0.14)",
            padding: landscape ? "28px 0 28px 36px" : "24px 0 0",
            color: "#817a71",
            fontFamily: "SFMono-Regular, Menlo, monospace",
            fontSize: 18,
            fontWeight: 700,
          }}
        >
          <span style={{ color: "rgba(244,241,234,0.12)", fontSize: landscape ? 104 : square ? 72 : 96, lineHeight: 0.9 }}>
            {String(index + 1).padStart(2, "0")}
          </span>
          <span style={{ color: "#f15a24", letterSpacing: "0.12em" }}>{kind.toUpperCase()}</span>
        </div>
      </div>
      <div style={{ position: "absolute", right: 40, bottom: 36, fontSize: 22, color: "#6a655c" }}>
        REMOTION #{index + 1}
      </div>
    </AbsoluteFill>
  );
};

const Row: React.FC<{ label?: string; value?: string; hot?: boolean; bodySize: number; valueSize: number }> = ({
  label,
  value,
  hot,
  bodySize,
  valueSize,
}) => (
  <div
    style={{
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      padding: "22px 26px",
      borderRadius: 22,
      border: hot ? "1px solid rgba(241,90,36,0.5)" : "1px solid rgba(244,241,234,0.12)",
      background: "#121214",
      fontSize: bodySize,
    }}
  >
    <span>{label}</span>
    <b style={{ color: "#f15a24", fontSize: valueSize }}>{value}</b>
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
