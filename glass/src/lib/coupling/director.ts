/** Instant Highlight Director — next-take brief for the HDMI ring. */

import { shouldClip } from "./clip.ts";
import type { ClutchKind } from "./clutch.ts";
import type { FeedMoment } from "./clutch.ts";

export const CLIP_HOLD_MS = 60_000;

export type DirectorMode = "watch" | "prime" | "armed" | "hold" | "encode";

export type DirectorInput = {
  now: number;
  holdUntil: number;
  clipBusy: boolean;
  companionArmed: boolean;
  redZone: boolean;
  late: boolean;
  close: boolean;
  clutchScore: number;
  clutchKind: ClutchKind;
  clutchLabel: string;
  clutchWhy: string;
  companionWhy: string;
  clipWorth: number;
};

export type DirectorBrief = {
  mode: DirectorMode;
  why: string;
  armHot: boolean;
};

export function autoClipAllowed(holdUntil: number, now: number): boolean {
  return holdUntil <= now;
}

export function directorBrief(ing: DirectorInput): DirectorBrief {
  if (ing.clipBusy) {
    return { mode: "encode", why: "Encoding 30s from the HDMI ring", armHot: false };
  }
  if (ing.holdUntil > ing.now) {
    return { mode: "hold", why: "HOLD — auto-clip silenced", armHot: false };
  }
  if (ing.companionArmed) {
    const extra = ing.companionWhy.trim();
    return {
      mode: "armed",
      why: extra ? `CLIP ARMED — ${extra}` : "CLIP ARMED — clutch will cut this",
      armHot: true,
    };
  }
  const primed =
    shouldClip(ing.clutchKind, ing.clipWorth) ||
    ing.clutchScore >= 0.55 ||
    ing.redZone ||
    ing.late;
  if (primed) {
    return { mode: "prime", why: primeWhy(ing), armHot: true };
  }
  return { mode: "watch", why: "Watching — no take yet", armHot: false };
}

function primeWhy(ing: DirectorInput): string {
  const bits: string[] = [];
  if (ing.redZone) bits.push("Red zone");
  if (ing.late) bits.push("Late clock");
  if (ing.close) bits.push("Close board");
  if (ing.clutchKind === "score_play") bits.push("Score play");
  else if (ing.clutchKind === "climax") bits.push("Climax");
  else if (ing.clutchKind === "window") bits.push("Clutch window");
  if (bits.length) return bits.join(" · ");
  const why = ing.clutchWhy.trim();
  if (why && why !== "no clutch pressure") return why;
  return ing.clutchLabel || "Take primed";
}

export function directorReasons(moments: FeedMoment[]): string[] {
  return moments
    .filter((m) => m.icon === "🎬" || m.path === "fast" || m.path === "confirm" || /clip/i.test(m.title))
    .sort((a, b) => b.at - a.at)
    .slice(0, 3)
    .map((m) => m.title);
}
