/** HDMI plinth clutch lamp — chrome only, never the JPEG. */

import type { ClutchKind } from "./clutch.ts";

export type ClutchPulse = "off" | "near" | "hot";

const PULSE_RANK: Record<ClutchPulse, number> = { off: 0, near: 1, hot: 2 };

export function hotterPulse(a: ClutchPulse, b: ClutchPulse): ClutchPulse {
  return PULSE_RANK[a] >= PULSE_RANK[b] ? a : b;
}

export function clutchPulse(ing: {
  kind: ClutchKind;
  score: number;
  armed: boolean;
  companionPhase?: string;
  companionClimax?: number | null;
}): ClutchPulse {
  const peak = Math.max(ing.score, Number(ing.companionClimax) || 0);
  const phase = String(ing.companionPhase || "").toLowerCase();
  if (ing.armed || ing.kind === "climax" || ing.kind === "score_play" || peak >= 0.7) {
    return "hot";
  }
  if (
    ing.kind === "pressure" ||
    ing.kind === "window" ||
    peak >= 0.42 ||
    phase === "pressure" ||
    phase === "armed" ||
    phase === "open" ||
    phase === "climax"
  ) {
    return "near";
  }
  return "off";
}
