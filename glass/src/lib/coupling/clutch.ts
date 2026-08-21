/** Clutch monitor — DriveGraph climax + original Deck moment feed. Observation only. */

import type { Phrase } from "./engine";

export type ClutchKind = "quiet" | "pressure" | "window" | "climax" | "score_play";

export type ClutchSnap = {
  score: number;
  kind: ClutchKind;
  phase: string;
  label: string;
  why: string;
};

export const QUIET_CLUTCH: ClutchSnap = {
  score: 0,
  kind: "quiet",
  phase: "empty",
  label: "watching",
  why: "no clutch pressure",
};

export type ClutchInput = {
  coupling: number;
  climax: number;
  phase: string;
  clipWorth: number;
  winProb: number | null;
  phrase: Phrase;
  ticketLive: boolean;
  quarter: number | null;
  down: number | null;
  distance: number | null;
  clock: string;
  boardLocked: boolean;
  homeScore: number | null;
  awayScore: number | null;
  scorePlay: boolean;
};

function clockSec(clock: string): number | null {
  const m = String(clock || "").match(/^(\d{1,2}):(\d{2})$/);
  if (!m) return null;
  return Number(m[1]) * 60 + Number(m[2]);
}

export function scoreClutch(ing: ClutchInput): ClutchSnap {
  let score = Math.max(0, Math.min(1, ing.climax || 0));
  const bits: string[] = [];
  if (ing.phase && ing.phase !== "empty") bits.push(ing.phase);

  if (ing.boardLocked && ing.homeScore != null && ing.awayScore != null) {
    const margin = Math.abs(ing.homeScore - ing.awayScore);
    const late = (ing.quarter ?? 0) >= 4;
    const sec = clockSec(ing.clock);
    const twoMin = late && sec != null && sec <= 120;
    if (late) {
      score = Math.max(score, 0.22);
      bits.push(`Q${ing.quarter}`);
    }
    if (twoMin) {
      score = Math.max(score, 0.48);
      bits.push(ing.clock);
    }
    if (late && margin <= 8) {
      score += 0.18;
      bits.push(`${ing.homeScore}-${ing.awayScore}`);
    }
    if (ing.down === 3) {
      score += 0.12;
      bits.push(`3rd & ${ing.distance ?? ""}`.trim());
    }
    if (ing.down === 4) {
      score += 0.22;
      bits.push(`4th & ${ing.distance ?? ""}`.trim());
    }
    if (ing.distance != null && ing.distance <= 3 && (ing.down ?? 0) >= 3) score += 0.08;
  }

  if (ing.clipWorth > 0) score = Math.max(score, Math.min(1, ing.clipWorth));
  if (ing.winProb != null && ing.winProb > 0 && ing.winProb < 0.45) score += 0.1;
  score += 0.16 * Math.min(1, Math.max(0, ing.coupling));
  if (ing.phrase === "SNAP" || ing.phrase === "SPRINT" || ing.phrase === "CUT") score += 0.08;
  if (ing.scorePlay) score = Math.max(score, 0.82);
  if (ing.phase === "armed" || ing.phase === "pressure") score = Math.max(score, 0.32);
  if (ing.phase === "open") score = Math.max(score, 0.4);
  score = Math.max(0, Math.min(1, score));

  let kind: ClutchKind = "quiet";
  if (ing.scorePlay || score >= 0.82) kind = "score_play";
  else if (score >= 0.68) kind = "climax";
  else if (score >= 0.45) kind = "window";
  else if (score >= 0.25) kind = "pressure";

  const label =
    kind === "quiet"
      ? "watching"
      : kind === "score_play"
        ? "SCORE PLAY"
        : kind === "climax"
          ? "CLIMAX"
          : kind === "window"
            ? "CLUTCH WINDOW"
            : "PRESSURE";

  return {
    score,
    kind,
    phase: ing.phase || "empty",
    label,
    why: bits.filter(Boolean).join(" · ") || `${ing.phrase} · c ${ing.coupling.toFixed(2)}`,
  };
}

export function clutchAdvanced(prev: ClutchSnap, next: ClutchSnap): boolean {
  if (next.kind === "quiet") return false;
  const rank: Record<ClutchKind, number> = {
    quiet: 0,
    pressure: 1,
    window: 2,
    climax: 3,
    score_play: 4,
  };
  if (rank[next.kind] > rank[prev.kind]) return true;
  if (next.kind === prev.kind && next.score - prev.score >= 0.12) return true;
  if (next.why !== prev.why && next.score >= 0.45) return true;
  return false;
}

export type FeedMoment = {
  key: string;
  title: string;
  path: "fast" | "confirm" | "";
  reason: string;
  clock: string;
  icon: string;
  at: number;
};

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function normTitle(t: string): string {
  return t.toLowerCase().replace(/\s+/g, " ").replace(/[^\w\s\-']/g, "").trim().slice(0, 100);
}

export function parseFeedMoment(raw: unknown): FeedMoment | null {
  if (!raw || typeof raw !== "object") return null;
  const m = raw as Record<string, unknown>;
  const p =
    m.type === "moment" && m.payload && typeof m.payload === "object"
      ? rec(m.payload)
      : rec(m);
  const url = String(p.url || p.media_url || "");
  const action = String(p.action || p.kind || "").toLowerCase();
  const isClip = action === "clip" || Boolean(url && /clip/i.test(url));
  const title = String(p.title || p.message || p.reason || p.text || p.name || (isClip ? "HDMI CLIP" : "")).trim();
  if (!title) return null;
  const pathRaw = String(p.moment_path || p.path || "").toLowerCase();
  const path: FeedMoment["path"] = pathRaw === "confirm" || pathRaw === "fast" ? pathRaw : "";
  const key = url ? `clip:${url}` : isClip ? `clip:${normTitle(title)}` : `chat:${normTitle(title)}`;
  return {
    key,
    title,
    path,
    reason: String(p.reason || p.name || p.action || ""),
    clock: String(p.clock || "now"),
    icon: String(p.icon || (isClip ? "🎬" : path === "fast" ? "⚡" : "●")),
    at: Date.now(),
  };
}

export function parseSnapshotMoments(raw: unknown): FeedMoment[] {
  if (!raw || typeof raw !== "object") return [];
  const m = raw as Record<string, unknown>;
  const snap =
    m.type === "snapshot"
      ? m
      : rec(m.state).moments || rec(m.state).last_moment
        ? rec(m.state)
        : rec(m.snapshot);
  const bag = Object.keys(snap).length ? snap : m;
  const out: FeedMoment[] = [];
  const last = parseFeedMoment(bag.last_moment);
  if (last) out.push(last);
  const list = Array.isArray(bag.moments) ? bag.moments : [];
  for (const item of list) {
    const fm = parseFeedMoment(item);
    if (fm) out.push(fm);
  }
  return out;
}
