import { create } from "zustand";
import {
  classifyPhrase,
  couplingFromPad,
  heatSpeech,
  isTicketLive,
  licenseHeatText,
  licenseScoreText,
  mintConfirmTicket,
  mintCouplingTicket,
  motionFromPad,
  nowNs,
  SOFT,
  whyStripConfirm,
  whyStripCoupling,
  type ConfirmTicket,
  type CouplingTicket,
  type GameState,
  type PhraseResult,
  LIVE_PHRASES,
} from "./engine";
import {
  agentsSignature,
  evaluateAgents,
  mergeAgentPlane,
  type AgentReceipt,
} from "./agents";
import { EMPTY_PLANE, type AgentPlane } from "./agent-plane";
import { armCapture as armCaptureDevice, armShare as armShareDevice, getDeckSrc, thawDeck as thawDeckDevice, wakePad as wakePadDevice, sampleCapture, type CaptureStatus, type VideoDevice } from "./hardware";
import { boardLine, situationLine, type DeckIngest } from "./board";
import { clutchAdvanced, scoreClutch, QUIET_CLUTCH, type ClutchSnap, type FeedMoment } from "./clutch";
import { measureLag } from "./sync";
import { qsEnhance, qsProbe } from "./quicksilver";
import { clipSeconds, requestDeckClip, shouldClip } from "./clip";

let qsAt = 0;
let qsKey = "";
let clipAt = 0;

export type HdmiMode = "live" | "menu" | "stale";
export type DrillId = "idle" | "sprint" | "veto" | "score" | null;
export type ViewMode = "deck" | "lens";

export type LogEntry = {
  id: number;
  t: number;
  kind: "phrase" | "ticket" | "heat" | "veto" | "confirm" | "score" | "agent" | "hw" | "clutch";
  line: string;
};

export type TheaterState = {
  r2: number;
  left: number;
  hdmi: HdmiMode;
  pllLock: boolean;
  frameSeq: number;
  phrase: PhraseResult;
  ticket: CouplingTicket | null;
  ticketLive: boolean;
  confirm: ConfirmTicket | null;
  coupling: number;
  motion: number;
  videoAgeS: number;
  heatLine: string;
  heatVetoed: boolean;
  scoreLine: string;
  boardLine: string;
  situation: string;
  gameTitle: string;
  clutch: ClutchSnap;
  moments: FeedMoment[];
  why: string;
  drill: DrillId;
  log: LogEntry[];
  throwAttempt: boolean;
  view: ViewMode;
  agents: AgentReceipt[];
  padConnected: boolean;
  padName: string;
  padHeld: string[];
  r2Frame: number;
  leftFrame: number;
  syncLagMs: number;
  bindKind: string;
  captureStatus: CaptureStatus;
  captureLabel: string;
  captureError: string;
  captureDevices: VideoDevice[];
  deckVideoUrl: string;
  deckLive: boolean;
  deckAt: number;
  agentPlane: AgentPlane;
  qsLive: boolean;
  qsModel: string;
  qsError: string;
  lastClipUrl: string;
  lastClipName: string;
  lastClipError: string;
  framed: boolean;
  setR2: (v: number) => void;
  setLeft: (v: number) => void;
  setHdmi: (m: HdmiMode) => void;
  setPllLock: (v: boolean) => void;
  setView: (v: ViewMode) => void;
  setPad: (p: { connected: boolean; name: string; held: string[] }) => void;
  setFramePad: (p: { r2: number; left: number; lagMs: number }) => void;
  noteFramed: (v: boolean) => void;
  armCapture: (deviceId?: string) => Promise<void>;
  ensureCapture: () => Promise<void>;
  thawDeck: () => void;
  armShare: () => Promise<void>;
  wakePad: () => Promise<void>;
  ingestDeck: (ing: DeckIngest) => void;
  ingestAgentPlane: (plane: AgentPlane) => void;
  ingestMoment: (m: FeedMoment) => void;
  probeQuicksilver: () => Promise<void>;
  requestEnhance: () => Promise<void>;
  requestClip: () => Promise<void>;
  tick: (prevR2: number) => void;
  runDrill: (id: DrillId) => void;
  mintConfirm: () => void;
  clearConfirm: () => void;
  tryThrow: () => void;
};

let logSeq = 0;
const pushLog = (log: LogEntry[], kind: LogEntry["kind"], line: string): LogEntry[] => {
  const entry: LogEntry = { id: ++logSeq, t: Date.now(), kind, line };
  return [entry, ...log].slice(0, 18);
};

function sampleGameState(hdmi: HdmiMode): GameState {
  if (hdmi === "menu") return "menu";
  return "gameplay";
}

function applyArm(
  get: () => TheaterState,
  set: (
    p: Partial<
      Pick<
        TheaterState,
        "captureStatus" | "captureLabel" | "captureError" | "captureDevices" | "deckVideoUrl" | "hdmi" | "pllLock" | "log"
      >
    >,
  ) => void,
  r: { status: CaptureStatus; label: string; error: string; devices?: VideoDevice[] },
) {
  const s = get();
  const log =
    r.status === "live"
      ? pushLog(s.log, "hw", `hdmi ${r.label}`)
      : pushLog(s.log, "veto", r.error || "capture refused");
  set({
    captureStatus: r.status,
    captureLabel: r.label,
    captureError: r.error,
    captureDevices: r.devices ?? s.captureDevices,
    deckVideoUrl: getDeckSrc(),
    hdmi: r.status === "live" ? "live" : s.hdmi,
    pllLock: r.status === "live" && s.padConnected && s.drill === null ? true : s.pllLock,
    log,
  });
}

const EMPTY_AGENTS = evaluateAgents({
  phrase: "HUDDLE",
  phraseLive: false,
  ticketLive: false,
  ticketId: "",
  heatLine: "",
  heatVetoed: false,
  scoreLine: licenseScoreText(SOFT.scoreLine, null),
  confirm: null,
  pllLock: true,
  hdmiLive: true,
});

export const useTheater = create<TheaterState>((set, get) => ({
  r2: 0,
  left: 0,
  hdmi: "live",
  pllLock: true,
  frameSeq: 0,
  phrase: { phrase: "HUDDLE", confidence: 0.6, live: false },
  ticket: null,
  ticketLive: false,
  confirm: null,
  coupling: 0,
  motion: 0,
  videoAgeS: 0,
  heatLine: "",
  heatVetoed: false,
  scoreLine: licenseScoreText(SOFT.scoreLine, null),
  boardLine: "",
  situation: "",
  gameTitle: "",
  clutch: QUIET_CLUTCH,
  moments: [],
  why: "confirm: none · couple: none · phrase=HUDDLE",
  drill: null,
  log: [],
  throwAttempt: false,
  view: "deck",
  agents: EMPTY_AGENTS,
  padConnected: false,
  padName: "",
  padHeld: [],
  r2Frame: 0,
  leftFrame: 0,
  syncLagMs: 80,
  bindKind: "",
  captureStatus: "off",
  captureLabel: "",
  captureError: "",
  captureDevices: [],
  deckVideoUrl: "",
  deckLive: false,
  deckAt: 0,
  agentPlane: EMPTY_PLANE,
  qsLive: false,
  qsModel: "",
  qsError: "",
  lastClipUrl: "",
  lastClipName: "",
  lastClipError: "",
  framed: false,

  setR2: (v) => set({ r2: Math.max(0, Math.min(1, v)), throwAttempt: false }),
  setLeft: (v) => set({ left: Math.max(0, Math.min(1, v)) }),
  setHdmi: (m) => set({ hdmi: m }),
  setPllLock: (v) => set({ pllLock: v }),
  setView: (v) => set({ view: v }),
  setPad: (p) => {
    const s = get();
    const became = p.connected && !s.padConnected;
    const log = became ? pushLog(s.log, "hw", `pad ${p.name || "connected"}`) : s.log;
    set({ padConnected: p.connected, padName: p.name, padHeld: p.held, log });
  },
  setFramePad: (p) => {
    const s = get();
    if (
      Math.abs(p.r2 - s.r2Frame) < 0.02 &&
      Math.abs(p.left - s.leftFrame) < 0.02 &&
      p.lagMs === s.syncLagMs
    ) {
      return;
    }
    set({ r2Frame: p.r2, leftFrame: p.left, syncLagMs: p.lagMs });
  },
  noteFramed: (v) => set({ framed: v }),
  armCapture: async (deviceId) => {
    set({ captureStatus: "arming", captureError: "" });
    const r = await armCaptureDevice(deviceId);
    applyArm(get, set, r);
  },
  ensureCapture: async () => {
    const s = get();
    if (s.captureStatus === "arming") return;
    if (s.captureStatus === "live") return;
    await get().armCapture();
  },
  thawDeck: () => {
    const src = thawDeckDevice();
    if (src) set({ deckVideoUrl: src, captureStatus: "live", hdmi: "live" });
  },
  armShare: async () => {
    set({ captureStatus: "arming", captureError: "" });
    const r = await armShareDevice();
    applyArm(get, set, r);
  },
  wakePad: async () => {
    const p = await wakePadDevice();
    get().setPad({ connected: p.connected, name: p.name, held: p.held });
    if (!p.connected) {
      const log = pushLog(get().log, "veto", "Pad not seen — click this glass, then press R2");
      set({ log });
    }
  },
  ingestDeck: (ing) => {
    const s = get();
    if (s.drill !== null) return;
    const clock = nowNs();
    const phrase: PhraseResult = {
      phrase: ing.phrase,
      confidence: ing.phraseConf,
      live: LIVE_PHRASES.has(ing.phrase),
    };
    let ticket = s.ticket;
    if (ing.ticketId) {
      ticket = {
        ticketId: ing.ticketId,
        clockNs: clock,
        frameSeq: ing.frameSeq || null,
        phrase: ing.phrase,
        coupling: ing.coupling,
        holdEnergy: ing.holdEnergy,
        imuBodied: true,
      };
    } else if (!phrase.live || !ing.pllLock) {
      ticket = null;
    }
    const liveTicket = isTicketLive(ticket, clock) ? ticket : null;
    const clutch = scoreClutch({
      coupling: ing.coupling,
      climax: ing.climax,
      phase: ing.drivePhase,
      clipWorth: ing.clipWorth,
      winProb: ing.winProb,
      phrase: phrase.phrase,
      ticketLive: liveTicket !== null,
      quarter: ing.quarter,
      down: ing.down,
      distance: ing.distance,
      clock: ing.clock,
      boardLocked: ing.boardLocked,
      homeScore: ing.homeScore,
      awayScore: ing.awayScore,
      scorePlay: ing.scorePlay,
    });
    const rawHeat =
      liveTicket && (clutch.kind === "window" || clutch.kind === "climax" || clutch.kind === "score_play")
        ? SOFT.clutchWindow
        : phrase.live
          ? SOFT.inputSpike
          : "";
    const licensed = licenseHeatText(rawHeat, liveTicket);
    const heatVetoed = Boolean(rawHeat) && heatSpeech(rawHeat) && licensed === "";
    let confirm = s.confirm;
    let log = s.log;
    const sit = situationLine({
      homeScore: ing.homeScore,
      awayScore: ing.awayScore,
      quarter: ing.quarter,
      down: ing.down,
      distance: ing.distance,
      clock: ing.clock,
      homeTeam: ing.homeTeam,
      awayTeam: ing.awayTeam,
      fieldPos: ing.fieldPos,
      winProb: ing.winProb,
      gameTitle: ing.gameTitle,
    });
    const board = sit || (ing.boardLocked ? boardLine(ing) : s.boardLine);
    if (ing.boardLocked && ing.homeScore != null && ing.awayScore != null) {
      if (!confirm || confirm.homeScore !== ing.homeScore || confirm.awayScore !== ing.awayScore) {
        confirm = mintConfirmTicket({
          clockNs: clock,
          homeScore: ing.homeScore,
          awayScore: ing.awayScore,
          frameSeq: ing.frameSeq || null,
        });
        log = pushLog(log, "score", board || `${ing.homeScore}-${ing.awayScore}`);
        log = pushLog(log, "confirm", "Gemini VLM board lock");
      }
    }
    const scoreLine = confirm ? whyStripConfirm(confirm) : licenseScoreText(SOFT.scoreLine, confirm);
    const why = ing.why || `${whyStripConfirm(confirm)} · ${whyStripCoupling(liveTicket)} · phrase=${phrase.phrase}`;
    const agents = mergeAgentPlane(evaluateAgents({
      phrase: phrase.phrase,
      phraseLive: phrase.live,
      ticketLive: liveTicket !== null,
      ticketId: liveTicket?.ticketId ?? "",
      heatLine: licensed,
      heatVetoed,
      scoreLine,
      confirm,
      pllLock: ing.pllLock,
      hdmiLive: ing.hdmi === "live",
    }), s.agentPlane, liveTicket !== null);
    if (phrase.phrase !== s.phrase.phrase) log = pushLog(log, "phrase", phrase.phrase);
    if (liveTicket && (!s.ticket || s.ticket.ticketId !== liveTicket.ticketId)) {
      log = pushLog(log, "ticket", `mint ${liveTicket.phrase} ${liveTicket.ticketId}`);
    }
    if (!s.deckLive) log = pushLog(log, "hw", "deck monitor live");
    if (clutchAdvanced(s.clutch, clutch)) {
      log = pushLog(log, "clutch", `${clutch.label} · ${clutch.why}`);
    }
    set({
      deckLive: true,
      deckAt: Date.now(),
      phrase,
      ticket,
      ticketLive: liveTicket !== null,
      coupling: ing.coupling,
      r2: ing.holdEnergy > 0 ? ing.holdEnergy : s.r2,
      pllLock: ing.pllLock,
      hdmi: ing.hdmi,
      videoAgeS: ing.videoAgeS,
      heatLine: licensed,
      heatVetoed,
      scoreLine,
      boardLine: board,
      situation: sit || s.situation,
      gameTitle: ing.gameTitle || s.gameTitle,
      clutch,
      why,
      confirm,
      agents,
      log,
      padConnected: ing.padConnected || s.padConnected,
      padName: ing.padConnected ? ing.padName || "DualSense" : s.padName,
      padHeld: ing.padHeld.length ? ing.padHeld : s.padHeld,
      syncLagMs: measureLag(ing.videoAgeS, ing.bindLagMs) || s.syncLagMs,
      bindKind: ing.bindKind || s.bindKind,
    });
    if (clutchAdvanced(s.clutch, clutch)) {
      get().ingestMoment({
        key: `clutch:${clutch.kind}:${clutch.why}`,
        title: `${clutch.label} · ${clutch.why}`,
        path: liveTicket ? "fast" : ing.boardLocked ? "confirm" : "",
        reason: clutch.phase || clutch.kind,
        clock: ing.clock || "now",
        icon: liveTicket ? "⚡" : "●",
        at: Date.now(),
      });
      void get().requestEnhance();
      if (shouldClip(clutch.kind, ing.clipWorth)) void get().requestClip();
    }
  },
  ingestMoment: (m) => {
    const s = get();
    if (s.moments.some((x) => x.key === m.key)) return;
    if (m.key.startsWith("chat:")) {
      const dup = s.moments.find((x) => x.key === m.key && Date.now() - x.at < 120000);
      if (dup) return;
    }
    set({ moments: [m, ...s.moments].slice(0, 20) });
  },
  probeQuicksilver: async () => {
    try {
      const p = await qsProbe();
      set({ qsLive: p.live, qsModel: p.model, qsError: p.live ? "" : "no Quicksilver key" });
    } catch (err) {
      set({ qsLive: false, qsError: err instanceof Error ? err.message : "qs probe failed" });
    }
  },
  requestEnhance: async () => {
    const s = get();
    if (s.agentPlane.commits[0]?.text) return;
    if (s.clutch.kind === "quiet" && !s.confirm) return;
    const now = Date.now();
    const key = `${s.clutch.kind}:${s.situation}:${s.phrase.phrase}`;
    if (now - qsAt < 8000 || key === qsKey) return;
    qsAt = now;
    qsKey = key;
    const path: "fast" | "confirm" =
      s.confirm && (s.clutch.kind === "score_play" || s.clutch.kind === "climax") ? "confirm" : "fast";
    if (path === "fast" && !s.ticketLive && s.clutch.kind === "quiet") return;
    const situation: Record<string, unknown> = {
      game_title: s.gameTitle || "Madden NFL 27",
      game_state: s.hdmi === "menu" ? "menu" : "gameplay",
      game_category: "football",
      phrase: s.phrase.phrase,
      coupling: s.coupling,
      climax_score: s.clutch.score,
      clutch_kind: s.clutch.kind,
      down: null,
      clock: "",
    };
    if (s.confirm) {
      situation.home_score = s.confirm.homeScore;
      situation.away_score = s.confirm.awayScore;
      situation.score_vlm_locked = true;
    }
    try {
      const out = await qsEnhance({
        data: {
          path,
          eventType: s.clutch.kind === "quiet" ? "score_changed" : s.clutch.kind,
          situation,
          baseMessage: s.heatLine || s.clutch.why || s.clutch.label,
          ticketLive: s.ticketLive,
        },
      });
      if (!out.ok) {
        set({
          qsLive: out.error === "no Quicksilver key" ? false : s.qsLive,
          qsError: out.error,
        });
        return;
      }
      let text = out.text;
      if (heatSpeech(text) && !s.ticketLive) text = "";
      if (s.confirm) text = licenseScoreText(text, s.confirm);
      if (!text) return;
      const agents = s.agents.map((a) =>
        a.role === "clutchbot"
          ? {
              ...a,
              action: "chat" as const,
              text,
              model: "quicksilver" as const,
              policyOk: true,
              reason: out.model,
            }
          : a,
      );
      set({
        agents,
        qsLive: true,
        qsModel: out.model,
        qsError: "",
        heatLine: s.ticketLive && heatSpeech(text) ? text : s.heatLine,
      });
      get().ingestMoment({
        key: `qs:${text.slice(0, 80)}`,
        title: text,
        path,
        reason: out.model,
        clock: "now",
        icon: path === "fast" ? "⚡" : "●",
        at: Date.now(),
      });
    } catch (err) {
      set({ qsError: err instanceof Error ? err.message : "qs enhance failed" });
    }
  },
  requestClip: async () => {
    const s = get();
    const now = Date.now();
    if (now - clipAt < 10000) return;
    clipAt = now;
    const seconds = clipSeconds(s.clutch.kind);
    const out = await requestDeckClip(seconds);
    if (!out.ok) {
      set({ lastClipError: out.error });
      if (out.error === "clip_rate_limited") return;
      get().ingestMoment({
        key: `clip:fail:${out.error}`,
        title: `CLIP wait — ${out.error}`,
        path: s.ticketLive ? "fast" : s.confirm ? "confirm" : "",
        reason: "hdmi ring",
        clock: "now",
        icon: "🎬",
        at: Date.now(),
      });
      return;
    }
    const origin = (await import("./qoresence-deck")).getDeckOrigin();
    const abs = out.url.startsWith("http") ? out.url : `${origin}${out.url.startsWith("/") ? "" : "/"}${out.url}`;
    const agents = get().agents.map((a) =>
      a.role === "ghost_editor"
        ? {
            ...a,
            action: "note" as const,
            text: `Cut candidate · ${out.name || `${out.seconds}s HDMI`}`,
            model: "rules" as const,
            policyOk: true,
            reason: "ghost editor clip",
          }
        : a,
    );
    set({ lastClipUrl: abs, lastClipName: out.name, lastClipError: "", agents });
    get().ingestMoment({
      key: `clip:${abs}`,
      title: `HDMI CLIP ${out.seconds}s`,
      path: s.ticketLive ? "fast" : "confirm",
      reason: out.name,
      clock: "now",
      icon: "🎬",
      at: Date.now(),
    });
  },
  ingestAgentPlane: (plane) => {
    const s = get();
    const agents = mergeAgentPlane(
      evaluateAgents({
        phrase: s.phrase.phrase,
        phraseLive: s.phrase.live,
        ticketLive: s.ticketLive,
        ticketId: s.ticket?.ticketId ?? "",
        heatLine: s.heatLine,
        heatVetoed: s.heatVetoed,
        scoreLine: s.scoreLine,
        confirm: s.confirm,
        pllLock: s.pllLock,
        hdmiLive: s.hdmi === "live",
      }),
      plane,
      s.ticketLive,
    );
    let log = s.log;
    if (plane.clutchbot && !s.agentPlane.clutchbot) log = pushLog(log, "agent", "ClutchBot live");
    if (plane.society && !s.agentPlane.society) log = pushLog(log, "agent", "Agent Society live");
    if (plane.a2a && !s.agentPlane.a2a) log = pushLog(log, "agent", "A2A live");
    set({
      agentPlane: plane,
      agents,
      log,
      qsLive: s.qsLive || plane.a2a || plane.commits.length > 0,
    });
    for (const c of plane.commits) {
      get().ingestMoment({
        key: `chat:${c.text.slice(0, 80)}`,
        title: c.text,
        path: /score|confirm/i.test(c.reason) ? "confirm" : "fast",
        reason: c.reason,
        clock: "now",
        icon: /confirm/i.test(c.reason) ? "●" : "⚡",
        at: Date.now(),
      });
    }
  },

  tick: (prevR2: number) => {
    const s = get();
    if (s.drill === null && s.deckLive && Date.now() - s.deckAt < 3000) return;
    if (s.deckLive && Date.now() - s.deckAt >= 3000) {
      set({ deckLive: false });
    }
    const clock = nowNs();
    const live = s.hdmi === "live";
    const cap = sampleCapture();
    const videoAgeS = s.hdmi === "stale" ? 1.0 : cap.status === "live" ? (cap.fresh ? 0.04 : 1.0) : 0.04;
    const padMotion = motionFromPad(s.r2, prevR2, s.left, live);
    const motion = cap.status === "live" && cap.fresh ? cap.motion + padMotion * 0.2 : padMotion;
    const onset = prevR2 < 0.08 && s.r2 >= 0.08;
    const phrase = classifyPhrase({
      gameState: sampleGameState(s.hdmi),
      r2: s.r2,
      prevR2,
      left: s.left,
      motion,
      r2OnsetEdge: onset,
      videoAgeS,
      holdFresh: s.r2 > 0,
    });
    const coupling = couplingFromPad(s.r2, s.left, motion);
    const videoFresh = videoAgeS <= 0.35;
    const minted = mintCouplingTicket({
      clockNs: clock,
      frameSeq: s.frameSeq + 1,
      phrase: phrase.phrase,
      coupling,
      holdEnergy: s.r2,
      pllLock: s.pllLock,
      videoFresh,
    });

    let ticket = s.ticket;
    let log = s.log;
    if (minted) {
      const changed = !s.ticket || s.ticket.phrase !== minted.phrase;
      ticket = minted;
      if (changed) log = pushLog(log, "ticket", `mint ${minted.phrase} ${minted.ticketId}`);
    } else if (!phrase.live || !s.pllLock || !videoFresh) {
      ticket = null;
    }

    const liveTicket = isTicketLive(ticket, clock) ? ticket : null;
    const clutch = scoreClutch({
      coupling,
      climax: 0,
      phase: "",
      clipWorth: 0,
      winProb: null,
      phrase: phrase.phrase,
      ticketLive: liveTicket !== null,
      quarter: null,
      down: null,
      distance: null,
      clock: "",
      boardLocked: Boolean(s.confirm),
      homeScore: s.confirm?.homeScore ?? null,
      awayScore: s.confirm?.awayScore ?? null,
      scorePlay: false,
    });
    const rawHeat =
      liveTicket && (clutch.kind === "window" || clutch.kind === "climax")
        ? SOFT.clutchWindow
        : phrase.live
          ? SOFT.inputSpike
          : "";
    const licensed = licenseHeatText(rawHeat, liveTicket);
    const heatVetoed = Boolean(rawHeat) && heatSpeech(rawHeat) && licensed === "";
    if (heatVetoed && !s.heatVetoed) {
      log = pushLog(log, "veto", "heat speech vetoed — no live coupling ticket");
    } else if (licensed && licensed !== s.heatLine) {
      log = pushLog(log, "heat", licensed);
    }
    if (phrase.phrase !== s.phrase.phrase) {
      log = pushLog(log, "phrase", phrase.phrase);
    }
    if (clutchAdvanced(s.clutch, clutch)) {
      log = pushLog(log, "clutch", `${clutch.label} · ${clutch.why}`);
    }

    const scoreLine = licenseScoreText(SOFT.scoreLine, s.confirm);
    const why = `${whyStripConfirm(s.confirm)} · ${whyStripCoupling(liveTicket)} · phrase=${phrase.phrase}`;

    const agents = mergeAgentPlane(evaluateAgents({
      phrase: phrase.phrase,
      phraseLive: phrase.live,
      ticketLive: liveTicket !== null,
      ticketId: liveTicket?.ticketId ?? "",
      heatLine: licensed,
      heatVetoed,
      scoreLine,
      confirm: s.confirm,
      pllLock: s.pllLock,
      hdmiLive: live,
    }), s.agentPlane, liveTicket !== null);
    if (agentsSignature(agents) !== agentsSignature(s.agents)) {
      const bot = agents.find((a) => a.role === "clutchbot");
      if (bot && bot.action === "chat" && bot.text && bot.text !== s.heatLine) {
        log = pushLog(log, "agent", `clutchbot ${bot.text}`);
      }
    }

    set({
      frameSeq: s.frameSeq + 1,
      phrase,
      ticket,
      ticketLive: liveTicket !== null,
      coupling,
      motion,
      videoAgeS,
      heatLine: licensed,
      heatVetoed,
      scoreLine,
      clutch,
      why,
      log,
      agents,
    });
  },

  runDrill: (id) => {
    if (id === "idle") {
      set({ drill: id, hdmi: "menu", pllLock: true, r2: 0.9, left: 0, confirm: null, throwAttempt: false });
    } else if (id === "sprint") {
      set({ drill: id, hdmi: "live", pllLock: true, r2: 0.92, left: 0, confirm: null, throwAttempt: false });
    } else if (id === "veto") {
      set({ drill: id, hdmi: "live", pllLock: false, r2: 0.92, left: 0, confirm: null, throwAttempt: false });
    } else if (id === "score") {
      set({ drill: id, hdmi: "live", pllLock: true, r2: 0, left: 0, confirm: null, throwAttempt: false });
    } else {
      set({ drill: null, r2: 0, left: 0 });
    }
  },

  mintConfirm: () => {
    const t = mintConfirmTicket({
      clockNs: nowNs(),
      homeScore: 21,
      awayScore: 14,
      frameSeq: get().frameSeq,
    });
    const log = pushLog(get().log, "confirm", `confirm 21-14 ${t.ticketId}`);
    set({ confirm: t, scoreLine: licenseScoreText(SOFT.scoreLine, t), log });
  },

  clearConfirm: () => {
    set({ confirm: null, scoreLine: licenseScoreText(SOFT.scoreLine, null) });
  },

  tryThrow: () => {
    const log = pushLog(get().log, "veto", "THROW forbidden — authorship, not observation");
    set({ throwAttempt: true, log });
  },
}));
