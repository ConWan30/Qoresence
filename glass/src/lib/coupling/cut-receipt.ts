/** Cut Receipt (<stem>.cut.json) view helpers — Qoresence decides; glass only shows and asks. */

export type CutAnswers = {
  kind?: string | null;
  kind_confidence?: number | null;
  suspended?: number | null;
  hides_play?: number | null;
};

export type CutSpan = {
  id: string;
  t0_s: number;
  t1_s: number;
  kinds?: string[];
  decision?: "cut" | "suggest" | "keep";
  reason?: string;
  user?: "cut" | "keep" | null;
  answers?: CutAnswers | null;
  evidence?: { still_s?: number; options_press_before_s?: number | null };
};

export type CutReceipt = {
  referee?: string;
  model?: string | null;
  excision?: string;
  source_duration_s?: number;
  edited_duration_s?: number;
  spans?: CutSpan[];
  time_map?: [number, number, number][];
  render?: { state?: string; path?: string | null };
};

export type DeadKind = "pause" | "menu" | "loading";
export type DeadSpan = [number, number, DeadKind];

export const DEAD_KINDS: DeadKind[] = ["pause", "menu", "loading"];
export const DEAD_LABEL: Record<DeadKind, string> = {
  pause: "Pause",
  menu: "Menu",
  loading: "Loading",
};
const KIND_LABEL: Record<string, string> = {
  pause: "Paused",
  select_plate: "Play select",
  menu: "Menu",
  loading: "Loading",
  still: "Frozen picture",
};

export function clipStem(href: string): string {
  const name = String(href || "").split("?")[0].split("/").pop() || "";
  return /^hdmi_clip_[\w-]+\.mp4$/i.test(name) ? name.replace(/\.mp4$/i, "") : "";
}

export function receiptUrl(href: string): string {
  const stem = clipStem(href);
  return stem ? `/media/clips/${stem}.cut.json` : "";
}

export function cutReady(r: CutReceipt | null): boolean {
  return Boolean(r && r.render && r.render.state === "done" && r.render.path);
}

export function cutRenderUrl(href: string, r: CutReceipt | null): string {
  if (!cutReady(r) || !clipStem(href)) return "";
  const path = String(r!.render!.path);
  return /^hdmi_clip_[\w-]+\.cut\.mp4$/i.test(path) ? `/media/clips/${path}` : "";
}

export function cutEffective(s: CutSpan): "cut" | "keep" {
  if (s.user === "cut" || s.user === "keep") return s.user;
  return s.decision === "cut" ? "cut" : "keep";
}

export function spanState(s: CutSpan): "removed" | "suggested" | "kept" {
  if (cutEffective(s) === "cut") return "removed";
  return s.decision === "suggest" && !s.user ? "suggested" : "kept";
}

export function spanTitle(s: CutSpan): string {
  const label = (s.kinds || []).map((k) => KIND_LABEL[k] || k).join("+") || "Span";
  return `${label} ${s.t0_s.toFixed(1)}–${s.t1_s.toFixed(1)}s · ${spanState(s)}`;
}

export function spanWhy(s: CutSpan): string {
  const a = s.answers || {};
  const ev = s.evidence || {};
  const bits: string[] = [];
  if (a.kind) {
    bits.push(`Jev ${a.kind}${a.kind_confidence != null ? " " + a.kind_confidence.toFixed(2) : ""}`);
  }
  if (a.suspended != null) bits.push(`suspended ${a.suspended.toFixed(2)}`);
  if (ev.still_s) bits.push(`still ${ev.still_s.toFixed(1)}s`);
  if (ev.options_press_before_s != null) bits.push(`Options −${ev.options_press_before_s.toFixed(1)}s`);
  bits.push(s.user ? `you: ${s.user}` : String(s.reason || ""));
  return bits.filter(Boolean).join(" · ");
}

export function refereeNote(r: CutReceipt): string {
  if (r.excision === "aborted_too_much") return "kept all: cut would remove too much";
  if (r.render?.state === "pending") return "rendering…";
  if (r.referee === "jev") return `judged by ${r.model || "Jev"}`;
  if (r.referee === "offline_triple_proof") return "offline: proven pauses only";
  return "";
}

/** Edited-player seconds → source seconds (identity when the original is playing). */
export function toSourceT(r: CutReceipt | null, t: number, edited: boolean): number {
  if (!edited || !r?.time_map) return t;
  for (const [e0, s0, len] of r.time_map) {
    if (t >= e0 && t <= e0 + len) return s0 + (t - e0);
  }
  return t;
}

/** Source seconds → edited-player seconds; removed time snaps to the next kept range. */
export function toPlayerT(r: CutReceipt | null, t: number, edited: boolean): number {
  if (!edited || !r?.time_map) return t;
  for (const [e0, s0, len] of r.time_map) {
    if (t < s0) return e0;
    if (t <= s0 + len) return e0 + (t - s0);
  }
  return t;
}

export type StripPiece = { kind: "keep" | "cut" | "suggest"; frac: number };

export function stripPieces(r: CutReceipt): StripPiece[] {
  const total = Math.max(Number(r.source_duration_s || 0), 0.001);
  const out: StripPiece[] = [];
  const push = (kind: StripPiece["kind"], t0: number, t1: number) => {
    if (t1 > t0) out.push({ kind, frac: (t1 - t0) / total });
  };
  let cursor = 0;
  for (const s of [...(r.spans || [])].sort((a, b) => a.t0_s - b.t0_s)) {
    push("keep", cursor, s.t0_s);
    const kind = cutEffective(s) === "cut" ? "cut" : s.decision === "suggest" ? "suggest" : "keep";
    push(kind, Math.max(cursor, s.t0_s), s.t1_s);
    cursor = Math.max(cursor, s.t1_s);
  }
  push("keep", cursor, total);
  return out;
}

export function addDeadSpan(
  dead: DeadSpan[],
  start: number | null,
  end: number,
  kind: DeadKind,
): { dead: DeadSpan[]; error: string } {
  if (start == null) return { dead, error: "mark start first" };
  if (end < start + 0.2) return { dead, error: "end must be after start" };
  const round = (x: number) => Math.round(x * 1000) / 1000;
  const next: DeadSpan[] = [...dead, [round(start), round(end), kind]];
  next.sort((a, b) => a[0] - b[0]);
  return { dead: next, error: "" };
}

export type GateStatus = {
  verdict?: string;
  failures?: string[];
  gaps?: string[];
  min_clips?: number;
  summary?: { football_clips_with_dead?: number; over_cut_s?: number };
};

export function gateLine(g: GateStatus | null): string {
  if (!g || !g.verdict) return "";
  const s = g.summary || {};
  const why = (g.failures || [])[0] || (g.gaps || [])[0] || "";
  return (
    `Pilot gate: ${g.verdict} · ${s.football_clips_with_dead || 0}/${g.min_clips || 20} clips` +
    ` · over-cut ${s.over_cut_s || 0}s${why ? " · " + why : ""}`
  );
}
