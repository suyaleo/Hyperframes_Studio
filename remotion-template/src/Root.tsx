import React from "react";
import { Composition } from "remotion";
import { CardMotion, type CardMotionProps, cardMotionSchema } from "./CardMotion";

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="CardMotion"
        component={CardMotion}
        durationInFrames={300}
        fps={30}
        width={1080}
        height={1920}
        schema={cardMotionSchema}
        defaultProps={{
          title: "Hyperframes Studio",
          aspect_ratio: "9:16",
          secondsPerCard: 2.5,
          cards: [
            { id: "c1", kind: "headline", title: "Sample", subtitle: "Remotion", kicker: "LIVE" },
          ],
        }}
        calculateMetadata={({ props }) => {
          const typedProps = props as CardMotionProps;
          const fps = 30;
          const spc = Number(typedProps.secondsPerCard) || 2.5;
          const n = Math.max((typedProps.cards || []).length, 1);
          const aspect = typedProps.aspect_ratio || "9:16";
          const size =
            aspect === "16:9"
              ? { width: 1920, height: 1080 }
              : aspect === "1:1"
                ? { width: 1080, height: 1080 }
                : { width: 1080, height: 1920 };
          return {
            durationInFrames: Math.max(1, Math.round(spc * fps * n)),
            fps,
            ...size,
          };
        }}
      />
    </>
  );
};
