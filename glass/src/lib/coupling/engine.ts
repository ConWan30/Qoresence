/** Play-phrase + coupling ticket — port of qoresence.sync.play_phrase / coupling_ticket
 *  and vision.confirm_ticket. Observation plane only. THROW is forbidden. */

export const PHRASES = ["IDLE", "HUDDLE", "SNAP", "SPRINT", "CUT", "RELEASE"] as const;
export type Phrase = (typeof PHRASES)[number];
export const LIVE_PHRASES = new Set<Phrase>(["SNAP", "SPRINT", "CUT", "RELEASE"]);
/** OFF by default — DualSense floors must not chatter Theater labels. */
export const PLAY_PHRASE_ENABLED = false;

export const R2_FLOOR = 0.08;
export const STICK_FLOOR = 0.15;
export const MOTION_FLOOR = 1.2;
export const STALE_VIDEO_S = 0.35;
export const TICKET_TTL_MS = 400;

const MENU = new Set(["menu", "lobby", "hub", "paused", "pause"]);
const PLAY = new Set(["gameplay", "playing", "in_game"]);

const HEAT_RE =
  /controller heat|pad and picture|input spike|pad heat|hands? and picture/i;
const SCORE_PAIR = /\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\b/;

export type GameState = "menu" | "gameplay" | "stale";

export type PhraseSample = {
  gameState: GameState;
  r2: number;
  prevR2: number;
  left: number;
  motion: number;
  r2OnsetEdge: boolean;
  videoAgeS: number;
  holdFresh: boolean;
};

export type PhraseResult = {
  phrase: Phrase;
  confidence: number;
  live: boolean;
};

export type CouplingTicket = {
  ticketId: string;
  clockNs: number;
  frameSeq: number | null;
  phrase: Phrase;
  coupling: number;
  holdEnergy: number;
  imuBodied: boolean;
};

export type ConfirmTicket = {
  ticketId: string;
  clockNs: number;
  homeScore: number;
  awayScore: number;
  frameSeq: number | null;
};

function clamp01(n: number) {
  return Math.max(0, Math.min(1, n));
}

function hash16(raw: string): string {
  let h1 = 0x811c9dc5;
  let h2 = 0x01000193;
  for (let i = 0; i < raw.length; i++) {
    const c = raw.charCodeAt(i);
    h1 ^= c;
    h1 = Math.imul(h1, 16777619);
    h2 = Math.imul(h2 ^ c, 2246822519);
  }
  return (
    (h1 >>> 0).toString(16).padStart(8, "0") +
    (h2 >>> 0).toString(16).padStart(8, "0")
  );
}

function sortedJson(obj: Record<string, unknown>): string {
  const keys = Object.keys(obj).sort();
  const out: Record<string, unknown> = {};
  for (const k of keys) out[k] = obj[k];
  return JSON.stringify(out);
}

export function classifyPhrase(s: PhraseSample): PhraseResult {
  if (!PLAY_PHRASE_ENABLED) return { phrase: "IDLE", confidence: 0, live: false };
  const gst = s.gameState;
  const r2 = Math.max(0, s.r2);
  const prev = Math.max(0, s.prevR2);
  const left = Math.max(0, s.left);
  const motion = Math.max(0, s.motion);
  const age = Math.max(0, s.videoAgeS);
  const onset = s.r2OnsetEdge || (prev < R2_FLOOR && r2 >= R2_FLOOR);
  const release = prev >= R2_FLOOR && r2 < R2_FLOOR;
  const stale = age > STALE_VIDEO_S;
  const menu = MENU.has(gst);
  const play = PLAY.has(gst);

  const pack = (phrase: Phrase, confidence: number): PhraseResult => ({
    phrase,
    confidence,
    live: LIVE_PHRASES.has(phrase),
  });

  if (menu) return pack("IDLE", 0.95);
  if (stale && !onset && !release && r2 < R2_FLOOR) return pack("IDLE", 0.85);
  if (release) return pack("RELEASE", 0.8);
  if (onset && motion >= MOTION_FLOOR) return pack("SNAP", 0.75);
  if (r2 >= R2_FLOOR && s.holdFresh && !stale) return pack("SPRINT", 0.7);
  if (left >= STICK_FLOOR && motion >= MOTION_FLOOR && !stale) return pack("CUT", 0.65);
  if (play && r2 < R2_FLOOR && left < STICK_FLOOR && !onset) return pack("HUDDLE", 0.6);
  if (r2 < R2_FLOOR && left < STICK_FLOOR && !onset && !release) return pack("IDLE", 0.8);
  return pack("IDLE", 0.5);
}

/** @deprecated Spine (Python) is sole mint — Glass must adopt coupling_ticket_id. */
export function mintCouplingTicket(args: {
  clockNs: number;
  frameSeq: number | null;
  phrase: Phrase;
  coupling: number;
  holdEnergy: number;
  imuBodied?: boolean;
  pllLock: boolean;
  videoFresh: boolean;
}): CouplingTicket | null {
  const ph = args.phrase;
  if (!LIVE_PHRASES.has(ph)) return null;
  if (!args.pllLock || !args.videoFresh) return null;
  const payload = {
    v: "QORESENCE-COUPLING-TICKET-v0",
    clock_ns: Math.trunc(args.clockNs),
    frame_seq: args.frameSeq,
    phrase: ph,
    coupling: Math.round(args.coupling * 10000) / 10000,
    hold_energy: Math.round(args.holdEnergy * 10000) / 10000,
    imu_bodied: Boolean(args.imuBodied),
  };
  return {
    ticketId: hash16(sortedJson(payload)),
    clockNs: payload.clock_ns,
    frameSeq: payload.frame_seq,
    phrase: ph,
    coupling: payload.coupling,
    holdEnergy: payload.hold_energy,
    imuBodied: payload.imu_bodied,
  };
}

export function heatSpeech(text: string): boolean {
  return Boolean(text) && HEAT_RE.test(text);
}

export function licenseHeatText(
  text: string,
  ticket: CouplingTicket | null,
): string {
  if (!text) return text;
  if (!heatSpeech(text)) return text;
  if (ticket === null) return "";
  return text;
}

export function whyStripCoupling(ticket: CouplingTicket | null): string {
  if (!ticket) return "couple: none";
  const seq = ticket.frameSeq != null ? ` seq=${ticket.frameSeq}` : "";
  return `couple ${ticket.phrase} ticket=${ticket.ticketId}${seq}`;
}

/** @deprecated Spine (Python) is sole mint — Glass must adopt last_confirm.ticket_id. */
export function mintConfirmTicket(args: {
  clockNs: number;
  homeScore: number;
  awayScore: number;
  frameSeq?: number | null;
}): ConfirmTicket {
  const payload = {
    v: "QORESENCE-CONFIRM-TICKET-v0",
    clock_ns: Math.trunc(args.clockNs),
    home_score: args.homeScore,
    away_score: args.awayScore,
    frame_seq: args.frameSeq ?? null,
  };
  return {
    ticketId: hash16(sortedJson(payload)),
    clockNs: payload.clock_ns,
    homeScore: args.homeScore,
    awayScore: args.awayScore,
    frameSeq: payload.frame_seq,
  };
}

export function licenseScoreText(
  text: string,
  ticket: ConfirmTicket | null,
): string {
  if (!text) return text;
  return text.replace(SCORE_PAIR, (full, a, b) => {
    if (!ticket) return "board";
    const pair = new Set([Number(a), Number(b)]);
    if (pair.has(ticket.homeScore) && pair.has(ticket.awayScore) && pair.size <= 2) {
      return full;
    }
    return "board";
  });
}

export function whyStripConfirm(ticket: ConfirmTicket | null): string {
  if (!ticket) return "confirm: none";
  const seq = ticket.frameSeq != null ? ` seq=${ticket.frameSeq}` : "";
  return `confirm ${ticket.homeScore}-${ticket.awayScore} ticket=${ticket.ticketId}${seq}`;
}

export const SOFT = {
  inputSpike: "Controller heat on a live drive — eyes up.",
  clutchWindow: "Clutch window opening — pad and picture aligned.",
  redZone: "Red-zone energy spike — something's cooking.",
  scoreLine: "Huge 21-14 in the red zone.",
  throwClaim: "THROW — he launched it.",
} as const;

export function isTicketLive(ticket: CouplingTicket | null, nowNs: number): boolean {
  if (!ticket) return false;
  const age = nowNs - ticket.clockNs;
  const ttlNs = TICKET_TTL_MS * 1e6;
  return age >= 0 && age <= ttlNs;
}

export function couplingFromPad(r2: number, left: number, motion: number): number {
  return clamp01(r2 * 0.55 + Math.min(left, 1) * 0.2 + Math.min(motion / 6, 1) * 0.35);
}

export function motionFromPad(r2: number, prevR2: number, left: number, live: boolean): number {
  if (!live) return 0;
  const onset = prevR2 < R2_FLOOR && r2 >= R2_FLOOR ? 4.2 : 0;
  return onset + left * 4.5 + r2 * 0.8;
}

export function nowNs(): number {
  return Math.trunc(performance.now() * 1e6);
}
