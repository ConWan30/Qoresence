/** Signal meter — broadcast-style health read straight from Deck `/health`.
 *
 * Observation only: parses JSON the Deck already serves (state.video,
 * state.local_scorebug, sync_health, lease). Never decodes JPEG, never opens
 * a socket, never invents a value. Missing field = null = rendered as a blank.
 *
 * The tally is LIVE only when the backend says the picture is painting:
 * has_frame + paint + same_seq + !plane_dim + fresh age + frames advancing.
 */

export type TallyState = "live" | "hold" | "stall" | "dark";

export type ScorebugRead = {
  enabled: boolean;
  /** Backend `state`: "sure" (agreed board) or "blank". */
  sure: boolean;
  /** Backend `reason` of the last offer: agreeing | recheck | blank | ok | idle | … */
  reason: string;
  /** Cumulative counters from the reader (not a run length). */
  reads: number | null;
  agreed: number | null;
  lastFrameReason: string | null;
  disagree: number | null;
  readerError: string | null;
};

export type SignalMeter = {
  /** Wall-clock ms of the last /health parse (0 = never). */
  at: number;
  frames: number | null;
  pushes: number | null;
  ageS: number | null;
  hasFrame: boolean;
  paint: boolean;
  paintReason: string;
  sameSeq: boolean | null;
  planeDim: boolean;
  liveSeq: number | null;
  widgetSeq: number | null;
  targetFps: number | null;
  /** Measured capture fps (sync_health.fps_meas) or null when unmeasured. */
  fpsMeas: number | null;
  width: number | null;
  height: number | null;
  /** Capture card the lease names (e.g. "USB3.0 Video"). */
  card: string;
  leaseOk: boolean;
  scorebug: ScorebugRead;
};

export const EMPTY_SCOREBUG: ScorebugRead = {
  enabled: false,
  sure: false,
  reason: "",
  reads: null,
  agreed: null,
  lastFrameReason: null,
  disagree: null,
  readerError: null,
};

export const EMPTY_METER: SignalMeter = {
  at: 0,
  frames: null,
  pushes: null,
  ageS: null,
  hasFrame: false,
  paint: false,
  paintReason: "",
  sameSeq: null,
  planeDim: false,
  liveSeq: null,
  widgetSeq: null,
  targetFps: null,
  fpsMeas: null,
  width: null,
  height: null,
  card: "",
  leaseOk: false,
  scorebug: EMPTY_SCOREBUG,
};

/** Age past which the picture is HOLD (frames still exist, not fresh). */
export const METER_HOLD_AGE_S = 1.0;
/** Age past which the hub is STALL (frames stopped while the Deck is up). */
export const METER_STALL_AGE_S = 5.0;
/** A /health older than this means the Deck itself stopped answering. */
export const METER_STALE_MS = 4000;

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function numOrNull(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function str(v: unknown): string {
  return v == null ? "" : String(v);
}

export function parseScorebugRead(raw: unknown): ScorebugRead {
  const o = rec(raw);
  if (!Object.keys(o).length) return EMPTY_SCOREBUG;
  return {
    enabled: Boolean(o.enabled),
    sure: str(o.state).toLowerCase() === "sure",
    reason: str(o.reason),
    reads: numOrNull(o.reads),
    agreed: numOrNull(o.agreed),
    lastFrameReason: o.last_frame_reason == null ? null : str(o.last_frame_reason),
    disagree: numOrNull(o.cross_check_disagree),
    readerError: o.reader_error == null ? null : str(o.reader_error),
  };
}

export function parseSignalMeter(health: unknown, now = Date.now()): SignalMeter | null {
  const h = rec(health);
  if (!Object.keys(h).length) return null;
  const state = rec(h.state);
  const video = rec(state.video);
  const sync = rec(h.sync_health);
  const lease = rec(h.lease);
  const fpsMeas = numOrNull(sync.fps_meas);
  return {
    at: now,
    frames: numOrNull(video.frames),
    pushes: numOrNull(video.pushes),
    ageS: numOrNull(video.age_s ?? video.hub_age_s),
    hasFrame: Boolean(video.has_frame ?? video.hub_has_frame),
    paint: Boolean(video.paint),
    paintReason: str(video.paint_reason),
    sameSeq: video.same_seq == null ? null : Boolean(video.same_seq),
    planeDim: Boolean(video.plane_dim),
    liveSeq: numOrNull(video.live_seq ?? video.hub_seq),
    widgetSeq: numOrNull(video.widget_seq),
    targetFps: numOrNull(video.target_fps),
    fpsMeas: fpsMeas != null && fpsMeas > 0 ? fpsMeas : null,
    width: numOrNull(video.width) || null,
    height: numOrNull(video.height) || null,
    card: str(lease.device),
    leaseOk: Boolean(lease.ok),
    scorebug: parseScorebugRead(state.local_scorebug ?? h.local_scorebug),
  };
}

/** frames++ since the previous parse. Prefers `pushes` (monotonic) over
 *  `frames` (ClipBuffer fill, which plateaus at capacity). Null when unknown. */
export function framesDelta(prev: SignalMeter, next: SignalMeter): number | null {
  if (!prev.at) return null;
  const a = prev.pushes ?? prev.frames;
  const b = next.pushes ?? next.frames;
  if (a == null || b == null) return null;
  return b - a;
}

/** Tally from backend facts only. Never LIVE on a guess. */
export function tallyState(m: SignalMeter, opts: { now?: number; advancing?: boolean | null } = {}): TallyState {
  const now = opts.now ?? Date.now();
  if (!m.at || now - m.at > METER_STALE_MS) return "dark";
  if (!m.hasFrame || !m.frames) return "dark";
  const age = m.ageS;
  if (age == null) return "dark";
  if (age > METER_STALL_AGE_S || opts.advancing === false) return "stall";
  if (m.paint && m.sameSeq !== false && !m.planeDim && age <= METER_HOLD_AGE_S) return "live";
  return "hold";
}

export const TALLY_LABEL: Record<TallyState, string> = {
  live: "Live",
  hold: "Hold",
  stall: "Stall",
  dark: "Dark",
};

/** Read ticks the backend can actually vouch for (it reports sure/blank + reason, not a run length). */
export function readTicks(sb: ScorebugRead): { lit: number; need: number; label: string; tone: "locked" | "reading" | "recheck" | "dark" } {
  if (!sb.enabled) return { lit: 0, need: 3, label: "reader off", tone: "dark" };
  if (sb.readerError) return { lit: 0, need: 3, label: "reader error", tone: "dark" };
  if (sb.sure) return { lit: 3, need: 3, label: "3/3 agreed", tone: "locked" };
  const r = sb.reason.toLowerCase();
  if (r === "recheck") return { lit: 1, need: 9, label: "recheck ≥1/9", tone: "recheck" };
  if (r === "agreeing") return { lit: 1, need: 3, label: "agreeing ≥1/3", tone: "reading" };
  return { lit: 0, need: 3, label: `0/3 · ${r || "idle"}`, tone: "dark" };
}

export function fmtAge(ageS: number | null): string {
  if (ageS == null) return "—";
  if (ageS < 10) return `${ageS.toFixed(2)}s`;
  if (ageS < 100) return `${ageS.toFixed(1)}s`;
  return `${Math.round(ageS)}s`;
}

export function fmtCount(n: number | null): string {
  if (n == null) return "—";
  return n.toLocaleString("en-US");
}

/**
 * Big centre word on the Lens overlay. "LIVE" only when the /health-driven tally is
 * live (same rule as the tally lamp); with no capture / stale / held picture the slot
 * stays empty — never a LIVE over nothing. Throw, replay and licensed clutch labels
 * keep their existing wording.
 */
export function lensWord(o: {
  tally: TallyState;
  replay: boolean;
  throwAttempt: boolean;
  clutchLabel: string | null;
}): string | null {
  if (o.throwAttempt) return "—";
  if (o.replay) return "REPLAY";
  if (o.clutchLabel) return o.clutchLabel;
  return o.tally === "live" ? "LIVE" : null;
}
