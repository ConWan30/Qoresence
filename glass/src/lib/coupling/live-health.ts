/** Stage live health — green only when the picture is actually moving.

Never treat a pumping JPEG as live if FrameHub frames/pushes have stopped.
That is the 2026 deadlock lesson: age_s climbing + frozen frames is a
lock cascade, not a dead capture card.
*/
export type LiveHealthTone = "green" | "amber" | "red";

export type LiveHealth = {
  tone: LiveHealthTone;
  label: string;
  reason: string;
};

export type LiveHealthInput = {
  ageS: number;
  frames: number;
  pushes: number;
  prevFrames: number;
  prevPushes: number;
  jpgOk: boolean;
  jpgAgeMs: number;
  stageMode: "live" | "replay";
};

export function scoreLiveHealth(ing: LiveHealthInput): LiveHealth {
  if (ing.stageMode === "replay") {
    return { tone: "amber", label: "REPLAY", reason: "mp4 on stage · LIVE kills player" };
  }
  const moving = ing.frames > ing.prevFrames || ing.pushes > ing.prevPushes;
  const ageOk = ing.ageS >= 0 && ing.ageS < 1;
  if (ageOk && moving) {
    return { tone: "green", label: "LIVE", reason: `age ${ing.ageS.toFixed(2)}s · frames climbing` };
  }
  if (ing.jpgOk && ing.jpgAgeMs < 2500 && !moving) {
    return {
      tone: "amber",
      label: "STALL",
      reason: "JPEG pumping · frames stopped · not the capture card",
    };
  }
  if (ing.ageS >= 5 && !moving) {
    return {
      tone: "red",
      label: "STALL",
      reason: "frames stopped · lock cascade, not the card",
    };
  }
  if (ing.jpgOk && ing.ageS >= 1) {
    return { tone: "amber", label: "LAG", reason: `age ${ing.ageS.toFixed(1)}s · JPEG still arriving` };
  }
  return { tone: "red", label: "WAIT", reason: "no moving HDMI yet" };
}
