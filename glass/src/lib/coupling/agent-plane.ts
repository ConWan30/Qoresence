/** ClutchBot + Agent Society — live from Deck /health and /api/agent. */

import { getDeckOrigin, probeDeck } from "./qoresence-deck";

export type SocietyNote = {
  role: string;
  action: string;
  text: string;
  reason: string;
};

export type AgentPlane = {
  clutchbot: boolean;
  society: boolean;
  a2a: boolean;
  geminiLive: boolean;
  vlmLocked: boolean;
  vlmBoard: string;
  deepseekLive: boolean;
  lastReason: string;
  commits: { text: string; reason: string; path: string }[];
  societyLast: SocietyNote[];
  societyRoles: string[];
  seq: number;
};

export const EMPTY_PLANE: AgentPlane = {
  clutchbot: false,
  society: false,
  a2a: false,
  geminiLive: false,
  vlmLocked: false,
  vlmBoard: "",
  deepseekLive: false,
  lastReason: "",
  commits: [],
  societyLast: [],
  societyRoles: [],
  seq: 0,
};

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" ? (v as Record<string, unknown>) : {};
}

function str(v: unknown): string {
  return v == null ? "" : String(v);
}

async function getJson(url: string): Promise<unknown | null> {
  try {
    const ctrl = new AbortController();
    const t = window.setTimeout(() => ctrl.abort(), 1200);
    const res = await fetch(url, { cache: "no-store", mode: "cors", signal: ctrl.signal });
    window.clearTimeout(t);
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export function parseAgentPlane(parts: {
  health?: unknown;
  agentHealth?: unknown;
  snapshot?: unknown;
}): AgentPlane {
  const health = rec(parts.health);
  const a2a = rec(health.a2a);
  const soc = rec(health.society);
  const agentH = rec(parts.agentHealth);
  const snap = rec(parts.snapshot);
  const coupling = rec(snap.coupling || agentH.coupling);

  const commitsRaw = Array.isArray(a2a.recent_commits) ? a2a.recent_commits : [];
  const commits = commitsRaw
    .map((c) => {
      const r = rec(c);
      const payload = rec(r.payload);
      const text = str(r.text || r.line || r.message || payload.text);
      return { text, reason: str(r.reason || r.path || r.last_reason), path: str(r.path || payload.path) };
    })
    .filter((c) => c.text);

  const lastRaw = Array.isArray(soc.last) ? soc.last : [];
  const societyLast: SocietyNote[] = lastRaw.map((c) => {
    const r = rec(c);
    return {
      role: str(r.role),
      action: str(r.action || "note"),
      text: str(r.text),
      reason: str(r.reason || r.model || "society"),
    };
  });

  const roles = Array.isArray(soc.roles) ? soc.roles.map(str).filter(Boolean) : [];
  const a2aOn = Boolean(a2a.enabled);
  const societyOn = Boolean(soc.enabled && (soc.alive || (soc.ticks != null && Number(soc.ticks) > 0)));
  const clutch =
    a2aOn ||
    Boolean(agentH.running) ||
    Boolean(snap.enabled) ||
    commits.length > 0 ||
    Boolean(coupling.coupling_ticket_id);

  const sit = rec(snap.situation);
  const confirm = rec(snap.confirm);
  const lastConfirm = rec(confirm.last_confirm);
  const vlmLocked = Boolean(
    sit.score_vlm_locked || sit.scoreboard_locked || sit.confirm_ticket_id || lastConfirm.home_score != null,
  );
  const vlmHome = lastConfirm.home_score ?? sit.home_score ?? sit.score_home;
  const vlmAway = lastConfirm.away_score ?? sit.away_score ?? sit.score_away;
  const vlmBoard =
    vlmLocked && vlmHome != null && vlmAway != null ? `${vlmHome}-${vlmAway}` : "";

  return {
    clutchbot: clutch,
    society: societyOn || roles.length > 0,
    a2a: a2aOn,
    geminiLive: Boolean(a2a.gemini_live) || vlmLocked,
    vlmLocked,
    vlmBoard,
    deepseekLive: Boolean(a2a.deepseek_live),
    lastReason: str(a2a.last_reason),
    commits,
    societyLast,
    societyRoles: roles,
    seq: Number(agentH.seq || snap.seq || 0) || 0,
  };
}

export async function fetchAgentPlane(): Promise<AgentPlane | null> {
  const probe = await probeDeck();
  const origin = probe.up ? probe.origin : getDeckOrigin();
  const [health, agentHealth, snapshot] = await Promise.all([
    getJson(`${origin}/health`),
    getJson(`${origin}/api/agent/health`),
    getJson(`${origin}/api/agent/snapshot`),
  ]);
  if (!health && !agentHealth && !snapshot) return null;
  return parseAgentPlane({ health, agentHealth, snapshot });
}
