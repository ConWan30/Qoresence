/** Stage live health — green when HDMI is current.

Never treat a pumping JPEG as live if FrameHub age has climbed and
frames/pushes have stopped. That is the 2026 deadlock lesson.

Do not compare counters at React render rate. A JPEG age tick or board
ingest often re-renders with the same frames/pushes; that is not a stall.
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
  /** ms since frames/pushes last increased. Large / omitted = no hold. */
  climbAgeMs?: number;
  jpgOk: boolean;
  jpgAgeMs: number;
  stageMode: "live" | "replay";
};

/** Keep LIVE through snapshot gaps. Real stalls last longer than one paint. */
export const CLIMB_HOLD_MS = 1600;

export function scoreLiveHealth(ing: LiveHealthInput): LiveHealth {
  if (ing.stageMode === "replay") {
    return { tone: "amber", label: "REPLAY", reason: "mp4 on stage · LIVE kills player" };
  }
  const climbed = ing.frames > ing.prevFrames || ing.pushes > ing.prevPushes;
  const climbAge = ing.climbAgeMs ?? 99999;
  const moving = climbed || (climbAge >= 0 && climbAge < CLIMB_HOLD_MS);
  const ageOk = ing.ageS >= 0 && ing.ageS < 1.25;
  const jpgFresh = ing.jpgOk && ing.jpgAgeMs < 1200;

  // Fresh hub age is LIVE even if this paint saw the same counters.
  if (ageOk) {
    return { tone: "green", label: "LIVE", reason: `age ${ing.ageS.toFixed(2)}s · HDMI fresh` };
  }
  if (moving && jpgFresh) {
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
