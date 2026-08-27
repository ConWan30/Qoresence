/** Situation harvest — HDMI scorebug + title presence. Digits fail-closed. */

/** Wire contract — must match qoresence.deck.server.SCHEMA_VERSION. */
export const DECK_SCHEMA_VERSION = "qoresence-deck-v0";
let _schemaMissingWarned = false;
let _schemaMismatchWarned = false;

import { parseActuatorReceipts, type ActuatorReceipt } from "./actuators.ts";
import { parseCompanion, type AgentCompanion } from "./companion.ts";
import type { Phrase } from "./engine";

const PHRASES: readonly Phrase[] = ["IDLE", "HUDDLE", "SNAP", "SPRINT", "CUT", "RELEASE"];
const LIVE = new Set<Phrase>(["SNAP", "SPRINT", "CUT", "RELEASE"]);

export type DeckIngest = {
  phrase: Phrase;
  phraseConf: number;
  coupling: number;
  holdEnergy: number;
  pllLock: boolean;
  ticketId: string;
  /** Spine coupling video_clock_ns when present. */
  couplingClockNs: number;
  /** Spine confirm.last_confirm.ticket_id. */
  confirmTicketId: string;
  confirmClockNs: number;
  path: "fast" | "confirm" | "";
  frameSeq: number;
  padConnected: boolean;
  padName: string;
  padHeld: string[];
  bindLagMs: number;
  bindKind: string;
  padR2: number;
  padLeft: number;
  padReports: number;
  padTransport: string;
  padEnergy: number;
  padBinds: number;
  padJitterMs: number;
  padHidSeq: number;
  syncLagMs: number;
  hdmi: "live" | "menu" | "stale";
  videoAgeS: number;
  videoFrames: number;
  videoPushes: number;
  homeScore: number | null;
  awayScore: number | null;
  quarter: number | null;
  down: number | null;
  distance: number | null;
  clock: string;
  boardLocked: boolean;
  climax: number;
  drivePhase: string;
  clipWorth: number;
  winProb: number | null;
  scorePlay: boolean;
  gameTitle: string;
  homeTeam: string;
  awayTeam: string;
  /** True when HOME is the left scorebug. Madden/NFL/CFB default is away-left. */
  homeLeft: boolean;
  fieldPos: string;
  why: string;
  liveSeq: number;
  widgetSeq: number;
  sameSeq: boolean;
  planeDim: boolean;
  paint: boolean;
  /** True when WS carried video live_paint optics (paint/same_seq/has_frame/live_seq). */
  videoOptics: boolean;
  /** ws = /retina; poll = /api/situation (sticky optics apply). */
  via: "ws" | "poll";
  ghostStick: GhostStick;
  companion: AgentCompanion;
  actuators: ActuatorReceipt[];
  /** LAYER A: Observation wire — play-pad observation (may be empty). */
  observation: Observation;
};

export type GhostStick = {
  enabled: boolean;
  paint: boolean;
  lx: number;
  ly: number;
  r2: number;
  l2: number;
  lagMs: number;
  frameSeq: number;
  reason: string;
};

export const EMPTY_GHOST: GhostStick = {
  enabled: false,
  paint: false,
  lx: 0,
  ly: 0,
  r2: 0,
  l2: 0,
  lagMs: 80,
  frameSeq: 0,
  reason: "off",
};

/** LAYER A: Observation wire — play-pad observation aligned to HDMI clock. */
export type Observation = {
  frameSeq: number;
  clockNs: number;
  hidButton: string | null;
  verb: string | null;
  mode: string | null;
  visualPhase: string | null;
  gameProfile: string | null;
  conflict: {
    pictureSheet: string;
    padSheet: string;
    kind: string;
    reason: string | null;
  } | null;
};

export const EMPTY_OBSERVATION: Observation = {
  frameSeq: 0,
  clockNs: 0,
  hidButton: null,
  verb: null,
  mode: null,
  visualPhase: null,
  gameProfile: null,
  conflict: null,
};

function asPhrase(raw: unknown): Phrase {
  const u = String(raw || "IDLE").toUpperCase();
  return (PHRASES as readonly string[]).includes(u) ? (u as Phrase) : "IDLE";
}

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function num(v: unknown, fallback = 0): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function intOrNull(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}

function firstNum(o: Record<string, unknown>, keys: string[]): number | null {
  for (const k of keys) {
    if (o[k] == null || o[k] === "") continue;
    const n = intOrNull(o[k]);
    if (n != null) return n;
  }
  return null;
}

function firstStr(o: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = o[k];
    if (typeof v !== "string") continue;
    const s = v.trim();
    if (s && s !== "true" && s !== "false") return s;
  }
  return "";
}

function firstBool(o: Record<string, unknown>, keys: string[]): boolean | null {
  for (const k of keys) {
    const v = o[k];
    if (v === true || v === false) return v;
    if (v === 1 || v === 0) return Boolean(v);
    if (typeof v === "string") {
      const s = v.trim().toLowerCase();
      if (s === "true" || s === "yes" || s === "on") return true;
      if (s === "false" || s === "no" || s === "off") return false;
    }
  }
  return null;
}

function parsePair(raw: unknown): [number, number] | null {
  const s = String(raw ?? "");
  const m = s.match(/\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\b/);
  if (!m) return null;
  return [Number(m[1]), Number(m[2])];
}

function fmtClock(o: Record<string, unknown>): string {
  if (o.clock != null && String(o.clock) !== "") return String(o.clock);
  const sec = intOrNull(o.game_clock_seconds ?? o.clock_seconds);
  if (sec == null) return "";
  const s = Math.max(0, sec);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export function pickBoard(...bags: Record<string, unknown>[]): {
  home: number | null;
  away: number | null;
  quarter: number | null;
  down: number | null;
  distance: number | null;
  clock: string;
  locked: boolean;
} {
  let home: number | null = null;
  let away: number | null = null;
  let quarter: number | null = null;
  let down: number | null = null;
  let distance: number | null = null;
  let clock = "";
  let locked = false;

  const walk = (o: Record<string, unknown>, forceLocked = false) => {
    if (!o || !Object.keys(o).length) return;
    const h = firstNum(o, ["home_score", "score_home", "homeScore"]);
    const a = firstNum(o, ["away_score", "score_away", "awayScore"]);
    const pair = h != null && a != null ? ([h, a] as const) : parsePair(o.score ?? o.scoreline ?? o.board);
    const thisLocked = forceLocked || Boolean(o.score_vlm_locked || o.scoreboard_locked || o.confirm_ticket_id);
    if (pair) {
      if (thisLocked) {
        home = pair[0];
        away = pair[1];
        locked = true;
      } else if (!locked && home == null) {
        home = pair[0];
        away = pair[1];
      }
    }
    if (thisLocked) locked = true;
    if (quarter == null) quarter = firstNum(o, ["quarter", "period"]);
    if (down == null) down = firstNum(o, ["down"]);
    if (distance == null) distance = firstNum(o, ["yards_to_go", "distance", "togo", "to_go"]);
    if (!clock) clock = fmtClock(o);
  };

  for (const bag of bags) {
    const confirm = rec(bag.confirm);
    walk(rec(confirm.last_confirm), true);
    walk(rec(bag.last_confirm), true);
    walk(bag);
    walk(rec(bag.situation));
    walk(rec(bag.payload));
    walk(rec(bag.visual_context));
    walk(rec(bag.scoreboard));
    walk(rec(confirm.last_fast));
    walk(rec(bag.last_fast));
  }

  return { home, away, quarter, down, distance, clock, locked };
}

function pickClutch(...bags: Record<string, unknown>[]): {
  climax: number;
  phase: string;
  clipWorth: number;
  winProb: number | null;
  scorePlay: boolean;
} {
  let climax = 0;
  let phase = "";
  let clipWorth = 0;
  let winProb: number | null = null;
  let scorePlay = false;
  const n = (v: unknown) => {
    const x = Number(v);
    return Number.isFinite(x) ? x : 0;
  };
  const walk = (o: Record<string, unknown>) => {
    if (!o || !Object.keys(o).length) return;
    const coup = rec(o.coupling);
    const tl = rec(o.timeline);
    const why = rec(tl.why_last);
    const graph = rec(tl.drive_graph).phase ? rec(tl.drive_graph) : rec(o.drive_graph);
    const cl = rec(graph.climax);
    climax = Math.max(climax, n(coup.climax_score), n(o.climax_score), n(why.climax_score), n(cl.score));
    if (!phase) phase = String(graph.phase || o.drive_phase || coup.phase || "");
    clipWorth = Math.max(clipWorth, n(o.clip_worthiness), n(rec(o.situation).clip_worthiness));
    const wp = o.win_prob ?? rec(o.situation).win_prob;
    if (wp != null && winProb == null) {
      const x = Number(wp);
      if (Number.isFinite(x)) winProb = x;
    }
    const kind = String(o.kind || o.type || o.last_event || "").toLowerCase();
    if (/touchdown|score_changed|field_goal|safety|two_point|confirm_score|clutch/.test(kind)) {
      scorePlay = true;
    }
  };
  for (const bag of bags) {
    walk(bag);
    walk(rec(bag.situation));
    walk(rec(bag.payload));
    walk(rec(bag.coupling));
  }
  return { climax, phase, clipWorth, winProb, scorePlay };
}

function teamPair(o: Record<string, unknown>): { home: string; away: string } | null {
  if (!o || !Object.keys(o).length) return null;
  const home = firstStr(o, ["home_team", "homeTeam"]);
  const away = firstStr(o, ["away_team", "awayTeam"]);
  if (home && away) return { home, away };
  return null;
}

function pickIdentity(m: Record<string, unknown>, snap: Record<string, unknown>, sit: Record<string, unknown>): {
  title: string;
  homeTeam: string;
  awayTeam: string;
  homeLeft: boolean;
  fieldPos: string;
} {
  let title = "";
  let homeTeam = "";
  let awayTeam = "";
  let fieldPos = "";
  let homeLeft: boolean | null = null;
  const walkMeta = (o: Record<string, unknown>) => {
    if (!o || !Object.keys(o).length) return;
    if (!title) title = firstStr(o, ["game_title", "title_claim", "game_profile"]);
    if (!fieldPos) fieldPos = firstStr(o, ["field_position", "fieldPos"]);
    if (homeLeft == null) homeLeft = firstBool(o, ["home_left", "homeLeft"]);
  };
  // Spine situation first — do not let a flickering visual_context swap sides.
  const preferred = [sit, rec(snap.situation), rec(m.payload), rec(m.situation), snap, m];
  for (const o of preferred) {
    walkMeta(o);
    if (!homeTeam && !awayTeam) {
      const pair = teamPair(o);
      if (pair) {
        homeTeam = pair.home;
        awayTeam = pair.away;
      }
    }
  }
  if (!homeTeam && !awayTeam) {
    for (const o of [rec(sit.visual_context), rec(snap.visual_context), rec(m.visual_context)]) {
      walkMeta(o);
      const pair = teamPair(o);
      if (pair) {
        homeTeam = pair.home;
        awayTeam = pair.away;
        break;
      }
    }
  } else {
    for (const o of preferred) walkMeta(o);
  }
  return { title, homeTeam, awayTeam, homeLeft: homeLeft === true, fieldPos };
}

function situationOf(m: Record<string, unknown>): Record<string, unknown> {
  const snap =
    m.type === "snapshot"
      ? m
      : rec(m.state).situation
        ? rec(m.state)
        : rec(m.snapshot).situation
          ? rec(m.snapshot)
          : rec(m.state).game_state != null
            ? rec(m.state)
            : rec(m.snapshot);
  if (rec(snap).situation && Object.keys(rec(rec(snap).situation)).length) return rec(rec(snap).situation);
  if (m.situation && typeof m.situation === "object") return rec(m.situation);
  if (m.payload && typeof m.payload === "object" && !Array.isArray(m.payload)) return rec(m.payload);
  if (m.game_state != null || m.home_score != null || m.score_home != null) return m;
  return rec(snap);
}


function assertDeckSchema(m: Record<string, unknown>): boolean {
  const nested = rec(m.state);
  const v = m.schema_version ?? nested.schema_version;
  if (v == null || v === "") {
    if (!_schemaMissingWarned) {
      console.warn("[deck] schema_version missing — soft continue (old build)");
      _schemaMissingWarned = true;
    }
    return true;
  }
  if (String(v) !== DECK_SCHEMA_VERSION) {
    if (!_schemaMismatchWarned) {
      console.error(
        `[deck] schema_version mismatch got=${v} want=${DECK_SCHEMA_VERSION} — HOLD ingest`,
      );
      _schemaMismatchWarned = true;
    }
    return false;
  }
  return true;
}

export function parseDeckMessage(raw: unknown): DeckIngest | null {
  if (!raw || typeof raw !== "object") return null;
  const m = raw as Record<string, unknown>;
  if (!assertDeckSchema(m)) return null;
  const snap =
    m.type === "snapshot"
      ? m
      : rec(m.state).situation || rec(m.state).controller
        ? rec(m.state)
        : rec(m.snapshot).situation || rec(m.snapshot).controller
          ? rec(m.snapshot)
          : m;
  const sit = situationOf(m);
  const ctrl =
    rec(snap.controller).connected != null || rec(snap.controller).phrase
      ? rec(snap.controller)
      : rec(m.controller);
  const video =
    rec(snap.video).has_frame != null || rec(snap.video).age_s != null ? rec(snap.video) : rec(m.video);
  const coup = Object.keys(rec(m.coupling)).length ? rec(m.coupling) : rec(snap.coupling);

  const gs = String(sit.game_state || sit.game_category || "").toLowerCase();
  const age = num(video.age_s, 0.04);
  const hasFrame = Boolean(video.has_frame ?? video.hub_has_frame);
  let hdmi: DeckIngest["hdmi"] = "live";
  if (["menu", "lobby", "hub", "paused", "pause"].includes(gs)) hdmi = "menu";
  else if (hasFrame && age > 0.35) hdmi = "stale";
  else if (!hasFrame && video.age_s != null) hdmi = "stale";

  const board = pickBoard(m, snap, sit, rec(m.confirm), rec(snap.confirm));
  const clutch = pickClutch(m, snap, sit, coup);
  const ident = pickIdentity(m, snap, sit);
  const phrase = asPhrase(ctrl.phrase || coup.phrase);
  const liveSeq = num(video.live_seq ?? video.hub_seq ?? video.seq ?? ctrl.frame_seq, 0);
  const widgetSeq = num(sit.frame_seq ?? ctrl.frame_seq ?? coup.frame_seq, 0);
  // Situation flood often omits video optics — do not demote the board on those.
  const videoOptics =
    video.paint != null ||
    video.same_seq != null ||
    video.has_frame != null ||
    video.hub_has_frame != null ||
    video.live_seq != null ||
    video.hub_seq != null ||
    video.plane_dim != null;
  let planeDim: boolean;
  let sameSeq: boolean;
  let paint: boolean;
  if (!videoOptics) {
    planeDim = false;
    sameSeq = true;
    paint = true;
  } else {
    planeDim = Boolean(video.plane_dim) || hdmi === "menu";
    sameSeq =
      video.same_seq != null
        ? Boolean(video.same_seq)
        : liveSeq === 0 && widgetSeq === 0
          ? true
          : liveSeq > 0 && widgetSeq === liveSeq;
    paint = video.paint != null ? Boolean(video.paint) : hasFrame && !planeDim && sameSeq;
  }
  const widgetsOk = paint && sameSeq && !planeDim;

  const whyBits = [
    ident.title,
    ident.homeTeam && ident.awayTeam ? `${ident.homeTeam}-${ident.awayTeam}` : "",
    board.home != null && board.away != null ? `${board.home}-${board.away}` : "",
    board.quarter != null ? `Q${board.quarter}` : "",
    board.clock,
    ctrl.phrase ? String(ctrl.phrase) : "",
  ].filter(Boolean);

  return {
    phrase,
    phraseConf: num(ctrl.phrase_conf ?? coup.phrase_conf, LIVE.has(phrase) ? 0.8 : 0.4),
    coupling: num(ctrl.coupling ?? coup.coupling),
    holdEnergy: num(ctrl.hold_energy ?? ctrl.input_energy),
    pllLock: Boolean(ctrl.pll_lock ?? coup.pll_lock),
    ticketId: String(ctrl.coupling_ticket_id || coup.coupling_ticket_id || ""),
    couplingClockNs: num(ctrl.video_clock_ns ?? coup.video_clock_ns ?? coup.clock_ns, 0),
    confirmTicketId: (() => {
      const lc = rec(rec(snap.confirm).last_confirm);
      const lc2 = rec(rec(m.confirm).last_confirm);
      return String(lc.ticket_id || lc2.ticket_id || sit.confirm_ticket_id || "");
    })(),
    confirmClockNs: (() => {
      const lc = rec(rec(snap.confirm).last_confirm);
      const lc2 = rec(rec(m.confirm).last_confirm);
      return num(lc.clock_ns ?? lc2.clock_ns, 0);
    })(),
    path: ((): "fast" | "confirm" | "" => {
      const p = String(ctrl.path || coup.path || "").toLowerCase();
      return p === "fast" || p === "confirm" ? p : "";
    })(),
    frameSeq: num(
      rec(rec(snap.confirm).last_confirm).frame_seq ?? ctrl.frame_seq ?? coup.frame_seq,
      0,
    ),
    padConnected: Boolean(ctrl.connected),
    padName: String(ctrl.device || "DualSense"),
    padHeld: Array.isArray(ctrl.buttons) ? ctrl.buttons.map(String).slice(0, 8) : [],
    bindLagMs: num(ctrl.last_bind_ms ?? coup.last_bind_ms),
    bindKind: String(ctrl.last_bind_kind || coup.last_bind_kind || ""),
    padR2: num(ctrl.pad_r2 ?? rec(ctrl.hold).r2),
    padLeft: num(ctrl.pad_left ?? rec(ctrl.hold).left),
    padReports: num(ctrl.reports),
    padTransport: String(ctrl.transport || ""),
    padEnergy: num(ctrl.input_energy ?? ctrl.hold_energy),
    padBinds: num(ctrl.binds),
    padJitterMs: num(ctrl.lag_jitter_ms),
    padHidSeq: num(ctrl.frame_seq),
    syncLagMs: num(
      ctrl.sync_lag_ms ?? ctrl.lag_center_ms ?? coup.lag_center_ms ?? rec(ctrl.lag_band_ms)[0],
      0,
    ),
    hdmi,
    videoAgeS: age,
    videoFrames: num(video.frames ?? video.hub_seq ?? video.live_seq, 0),
    videoPushes: num(video.pushes ?? video.hub_seq ?? video.frames, 0),
    // Locked digits only from spine last_confirm / score_vlm_locked (pickBoard).
    // Unlocked OCR never surfaces when widgets are dark.
    homeScore: board.locked || widgetsOk ? board.home : null,
    awayScore: board.locked || widgetsOk ? board.away : null,
    quarter: board.quarter,
    down: board.down,
    distance: board.distance,
    clock: board.clock,
    boardLocked: board.locked,
    climax: clutch.climax,
    drivePhase: clutch.phase,
    clipWorth: clutch.clipWorth,
    winProb: clutch.winProb,
    scorePlay: clutch.scorePlay,
    gameTitle: ident.title,
    homeTeam: ident.homeTeam,
    awayTeam: ident.awayTeam,
    homeLeft: ident.homeLeft,
    fieldPos: ident.fieldPos,
    why: whyBits.join(" · ") || "deck snapshot",
    liveSeq,
    widgetSeq,
    sameSeq,
    planeDim,
    paint,
    videoOptics,
    via: "ws",
    ghostStick: parseGhostStick(snap.ghost_stick || m.ghost_stick, widgetsOk),
    companion: parseCompanion(snap.companion || m.companion || m),
    actuators: parseActuatorReceipts(snap.actuators || m.actuators),
    observation: parseObservation(snap.observation || m.observation),
  };
}

function parseGhostStick(raw: unknown, widgetsOk: boolean): GhostStick {
  const g = rec(raw);
  const enabled = Boolean(g.enabled);
  const reason = firstStr(g, ["reason"]) || (enabled ? "idle" : "off");
  const paint = enabled && widgetsOk && Boolean(g.paint) && reason === "ok";
  return {
    enabled,
    paint,
    lx: num(g.lx),
    ly: num(g.ly),
    r2: num(g.r2),
    l2: num(g.l2),
    lagMs: num(g.lag_ms ?? g.lagMs, 80),
    frameSeq: num(g.frame_seq ?? g.frameSeq),
    reason: paint ? "ok" : reason,
  };
}

function parseObservation(raw: unknown): Observation {
  if (!raw || typeof raw !== "object") return EMPTY_OBSERVATION;
  const o = rec(raw);
  const conflict = o.conflict && typeof o.conflict === "object" ? rec(o.conflict) : null;
  return {
    frameSeq: num(o.frame_seq ?? o.frameSeq, 0),
    clockNs: num(o.clock_ns ?? o.clockNs, 0),
    hidButton: o.hid_button != null ? String(o.hid_button) : null,
    verb: o.verb != null ? String(o.verb) : null,
    mode: o.mode != null ? String(o.mode) : null,
    visualPhase: o.visual_phase != null ? String(o.visual_phase) : null,
    gameProfile: o.game_profile != null ? String(o.game_profile) : null,
    conflict: conflict
      ? {
          pictureSheet: String(conflict.picture_sheet || ""),
          padSheet: String(conflict.pad_sheet || ""),
          kind: String(conflict.kind || "sheet_mismatch"),
          reason: conflict.reason != null ? String(conflict.reason) : null,
        }
      : null,
  };
}


/** Ordinal down & distance for Lockbug / Down Pill. Unlocked → "— & —". */
export function downDistanceLabel(down: number | null, distance: number | null): string {
  if (down == null) return "— & —";
  const ord =
    down === 1 ? "1st" : down === 2 ? "2nd" : down === 3 ? "3rd" : down === 4 ? "4th" : String(down);
  const dist = distance != null ? String(distance) : "—";
  return `${ord} & ${dist}`;
}

/** Named sides paint left→right as HDMI (away left unless homeLeft). Bare digits stay home–away. */
export function scorebugPair(ing: {
  homeScore: number | null;
  awayScore: number | null;
  homeTeam?: string;
  awayTeam?: string;
  homeLeft?: boolean | null;
  dash?: string;
}): string {
  if (ing.homeScore == null || ing.awayScore == null) return "";
  const dash = ing.dash ?? "-";
  const leftTeam = ing.homeLeft === true ? ing.homeTeam || "" : ing.awayTeam || "";
  const rightTeam = ing.homeLeft === true ? ing.awayTeam || "" : ing.homeTeam || "";
  const named = Boolean(leftTeam && rightTeam);
  const leftScore = named
    ? ing.homeLeft === true
      ? ing.homeScore
      : ing.awayScore
    : ing.homeScore;
  const rightScore = named
    ? ing.homeLeft === true
      ? ing.awayScore
      : ing.homeScore
    : ing.awayScore;
  if (named) {
    return dash === "–"
      ? `${leftTeam} ${leftScore}–${rightScore} ${rightTeam}`
      : `${leftTeam} ${leftScore} - ${rightTeam} ${rightScore}`;
  }
  return dash === "–" ? `${leftScore}–${rightScore}` : `${leftScore}-${rightScore}`;
}

export function situationLine(ing: {
  homeScore: number | null;
  awayScore: number | null;
  quarter: number | null;
  down: number | null;
  distance: number | null;
  clock: string;
  homeTeam?: string;
  awayTeam?: string;
  homeLeft?: boolean | null;
  fieldPos?: string;
  winProb?: number | null;
  gameTitle?: string;
}): string {
  const parts: string[] = [];
  const pair = scorebugPair(ing);
  if (pair) parts.push(pair);
  if (ing.quarter != null) parts.push(`Q${ing.quarter}${ing.clock ? ` ${ing.clock}` : ""}`);
  else if (ing.clock) parts.push(ing.clock);
  if (ing.down != null) {
    const ord = ing.down === 1 ? "1st" : ing.down === 2 ? "2nd" : ing.down === 3 ? "3rd" : ing.down === 4 ? "4th" : String(ing.down);
    const dist = ing.distance != null ? String(ing.distance) : "?";
    const at = ing.fieldPos ? ` @ ${ing.fieldPos}` : "";
    parts.push(`${ord} & ${dist}${at}`);
  }
  if (ing.winProb != null) parts.push(`WP ${Math.round(ing.winProb * 100)}%`);
  if (!parts.length && ing.gameTitle) return ing.gameTitle;
  return parts.join(" · ");
}

export function boardLine(ing: {
  homeScore: number | null;
  awayScore: number | null;
  quarter: number | null;
  down: number | null;
  distance: number | null;
  clock: string;
}): string {
  return situationLine(ing);
}
