/** Agent Companion — observation-plane duty pack from Deck.
 *  Hygiene marker ``agentCompanion``. Auto-clip stays on. No invented scores. */

export const AGENT_COMPANION = "agentCompanion";

export type CompanionClipLast = {
  title: string;
  path: "fast" | "confirm" | "";
  url: string;
  name: string;
  reason: string;
};

export type CompanionCut = {
  stem: string;
  tIn: number | null;
  tOut: number | null;
  title: string;
  text: string;
};

export type AgentCompanion = {
  ok: boolean;
  autoClip: boolean;
  armed: boolean;
  lastClip: CompanionClipLast | null;
  coupling: number;
  redZone: boolean;
  close: boolean;
  late: boolean;
  climax: number | null;
  phase: string;
  matchRate: number | null;
  why: string;
  coach: string;
  cut: CompanionCut | null;
  maySay: string[];
};

export const EMPTY_COMPANION: AgentCompanion = {
  ok: false,
  autoClip: true,
  armed: false,
  lastClip: null,
  coupling: 0,
  redZone: false,
  close: false,
  late: false,
  climax: null,
  phase: "",
  matchRate: null,
  why: "",
  coach: "",
  cut: null,
  maySay: [],
};

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function num(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function parseCompanion(raw: unknown): AgentCompanion {
  const root = rec(raw);
  const bag = rec(root.companion).ok != null ? rec(root.companion) : rec(root);
  if (bag.ok == null && bag.auto_clip == null && bag.clip == null) return { ...EMPTY_COMPANION };
  const clip = rec(bag.clip);
  const gates = rec(clip.gates);
  const last = rec(clip.last);
  const drive = rec(bag.drive);
  const coach = rec(bag.coach);
  const cut = rec(bag.cut);
  const pathRaw = String(last.path || "");
  const path = pathRaw === "fast" || pathRaw === "confirm" ? pathRaw : "";
  const lastClip: CompanionClipLast | null =
    last.title || last.url || last.name
      ? {
          title: String(last.title || ""),
          path,
          url: String(last.url || ""),
          name: String(last.name || ""),
          reason: String(last.reason || ""),
        }
      : null;
  const cutOut: CompanionCut | null =
    cut.text || cut.title || cut.stem
      ? {
          stem: String(cut.stem || ""),
          tIn: num(cut.t_s_in),
          tOut: num(cut.t_s_out),
          title: String(cut.title || ""),
          text: String(cut.text || ""),
        }
      : null;
  const may = Array.isArray(bag.may_say) ? bag.may_say.map(String).filter(Boolean) : [];
  return {
    ok: bag.ok !== false,
    autoClip: bag.auto_clip !== false,
    armed: Boolean(clip.armed),
    lastClip,
    coupling: num(gates.coupling) ?? 0,
    redZone: Boolean(gates.red_zone),
    close: Boolean(gates.close),
    late: Boolean(gates.late),
    climax: num(drive.climax ?? gates.climax),
    phase: String(drive.phase || ""),
    matchRate: num(drive.match_rate),
    why: String(drive.why || ""),
    coach: String(coach.text || ""),
    cut: cutOut,
    maySay: may,
  };
}

export function companionDutyLine(c: AgentCompanion): string {
  if (c.armed) return "CLIP ARMED — ClutchBot will cut this";
  if (c.lastClip?.title) return `AUTO CLIP · ${c.lastClip.path || "hdmi"} · ${c.lastClip.title}`;
  if (c.autoClip) return "AUTO CLIP — watching for clutch (fast ≥0.55 red/late, confirm on lock)";
  return "clip duty off";
}
