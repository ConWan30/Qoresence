/** ClutchBot + A2A on glass. Actuators, not Society coworkers.
 *  Heat requires a live coupling ticket. Score digits require a confirm ticket.
 *  THROW is forbidden. No authorship. */

import type { AgentPlane } from "./agent-plane";
import { companionDutyLine, type AgentCompanion } from "./companion.ts";
import {
  heatSpeech,
  licenseScoreText,
  type ConfirmTicket,
  type Phrase,
} from "./engine.ts";

export type AgentRole =
  | "clutchbot"
  | "gemini"
  | "deepseek"
  | "drive_coach"
  | "spam_warden"
  | "ghost_editor"
  | "pilot_auditor"
  | "prediction_steward"
  | "sync_warden"; // leftover names only — no Society persona chips

export type AgentAction = "chat" | "note" | "veto" | "allow" | "quiet";

export type AgentReceipt = {
  role: AgentRole;
  action: AgentAction;
  text: string;
  model: "quicksilver" | "rules";
  policyOk: boolean;
  reason: string;
};

const ROLE_ORDER: AgentRole[] = ["clutchbot", "gemini", "deepseek"];

export const ROLE_LABEL: Record<AgentRole, string> = {
  clutchbot: "ClutchBot",
  gemini: "Gemini",
  deepseek: "DeepSeek",
  drive_coach: "Drive coach",
  spam_warden: "Warden",
  ghost_editor: "Ghost editor",
  pilot_auditor: "Auditor",
  prediction_steward: "Steward",
  sync_warden: "Sync warden",
};

function quiet(role: AgentRole, reason: string): AgentReceipt {
  return {
    role,
    action: "quiet",
    text: "",
    model: "rules",
    policyOk: true,
    reason,
  };
}

/** Phase 1: hide persona rows. Show the last real receipt only. */
export function visibleAgentReceipts(agents: AgentReceipt[]): AgentReceipt[] {
  for (let i = agents.length - 1; i >= 0; i--) {
    const a = agents[i];
    if (a.action === "quiet") continue;
    if (a.action === "note" && /society (armed|wait|live)/i.test(`${a.text} ${a.reason}`)) {
      continue;
    }
    if (!a.text && a.action !== "veto" && a.action !== "chat") continue;
    return [a];
  }
  return [];
}

function commitHeat(
  role: AgentRole,
  text: string,
  ticketLive: boolean,
  model: "quicksilver" | "rules" = "rules",
): AgentReceipt {
  if (heatSpeech(text) && !ticketLive) {
    return {
      role,
      action: "veto",
      text: "",
      model: "rules",
      policyOk: false,
      reason: "heat speech requires coupling ticket",
    };
  }
  return {
    role,
    action: "chat",
    text,
    model,
    policyOk: true,
    reason: model === "quicksilver" ? "a2a soft commit" : "template until Quicksilver",
  };
}

export type AgentContext = {
  phrase: Phrase;
  phraseLive: boolean;
  ticketLive: boolean;
  ticketId: string;
  heatLine: string;
  heatVetoed: boolean;
  scoreLine: string;
  confirm: ConfirmTicket | null;
  pllLock: boolean;
  hdmiLive: boolean;
  companion?: AgentCompanion | null;
};

export function evaluateAgents(ctx: AgentContext): AgentReceipt[] {
  const receipts: Partial<Record<AgentRole, AgentReceipt>> = {
    clutchbot: clutchbot(ctx),
    gemini: gemini(ctx),
    deepseek: deepseek(ctx),
  };
  return ROLE_ORDER.map((r) => receipts[r]!);
}

export function mergeAgentPlane(
  local: AgentReceipt[],
  plane: AgentPlane | null,
  ticketLive: boolean,
): AgentReceipt[] {
  if (!plane) return local;
  const byRole = Object.fromEntries(local.map((r) => [r.role, r])) as Partial<
    Record<AgentRole, AgentReceipt>
  >;

  if (plane.clutchbot) {
    const commit = plane.commits[0];
    if (commit?.text) {
      byRole.clutchbot = commitHeat("clutchbot", commit.text, ticketLive, "quicksilver");
      if (byRole.clutchbot?.action === "chat") {
        byRole.clutchbot = { ...byRole.clutchbot, reason: commit.reason || "a2a commit" };
      }
    } else if (byRole.clutchbot?.action === "quiet") {
      byRole.clutchbot = {
        role: "clutchbot",
        action: "note",
        text: "ClutchBot armed — waiting for a licensed Quicksilver line",
        model: "rules",
        policyOk: true,
        reason: plane.a2a ? `a2a live${plane.lastReason ? ` · ${plane.lastReason}` : ""}` : "deck feed live",
      };
    }
  }

  if (plane.vlmLocked) {
    byRole.gemini = {
      role: "gemini",
      action: "note",
      text: plane.vlmBoard
        ? `Board lock ${plane.vlmBoard} — primary scorebug only.`
        : "Scoreboard VLM locked.",
      model: "quicksilver",
      policyOk: true,
      reason: "gemini-3.5-flash-lite scoreboard VLM",
    };
  } else if (plane.geminiLive && byRole.gemini?.action === "quiet") {
    byRole.gemini = {
      role: "gemini",
      action: "note",
      text: "Gemini VLM live — waiting for an honest board lock",
      model: "quicksilver",
      policyOk: true,
      reason: "a2a gemini",
    };
  }
  if (plane.deepseekLive && byRole.deepseek?.action === "quiet") {
    byRole.deepseek = {
      role: "deepseek",
      action: "note",
      text: "Chat agent live",
      model: "quicksilver",
      policyOk: true,
      reason: "a2a deepseek",
    };
  }

  return ROLE_ORDER.map((r) => byRole[r]).filter((r): r is AgentReceipt => Boolean(r));
}

function clutchbot(ctx: AgentContext): AgentReceipt {
  if (ctx.heatVetoed) {
    return {
      role: "clutchbot",
      action: "veto",
      text: "",
      model: "rules",
      policyOk: false,
      reason: "heat speech requires coupling ticket",
    };
  }
  if (ctx.heatLine) {
    return {
      role: "clutchbot",
      action: "chat",
      text: ctx.heatLine,
      model: "rules",
      policyOk: true,
      reason: "heat licensed template",
    };
  }
  if (ctx.confirm) {
    const line = licenseScoreText(ctx.scoreLine, ctx.confirm);
    if (line && !/board/i.test(line)) {
      return {
        role: "clutchbot",
        action: "chat",
        text: line,
        model: "rules",
        policyOk: true,
        reason: "confirm ticket digits",
      };
    }
  }
  const duty = ctx.companion ? companionDutyLine(ctx.companion) : "";
  if (ctx.companion?.armed) {
    return {
      role: "clutchbot",
      action: "note",
      text: duty,
      model: "rules",
      policyOk: true,
      reason: "auto-clip armed",
    };
  }
  if (ctx.companion?.lastClip?.title) {
    return {
      role: "clutchbot",
      action: "note",
      text: duty,
      model: "rules",
      policyOk: true,
      reason: "auto-clip last",
    };
  }
  if (ctx.companion?.autoClip !== false) {
    return {
      role: "clutchbot",
      action: "note",
      text: duty || "AUTO CLIP — watching for clutch",
      model: "rules",
      policyOk: true,
      reason: "auto-clip duty",
    };
  }
  return quiet("clutchbot", "invisible when boring");
}

function gemini(ctx: AgentContext): AgentReceipt {
  if (!ctx.hdmiLive || !ctx.phraseLive || !ctx.ticketLive) {
    return quiet("gemini", "scene idle");
  }
  return commitHeat(
    "gemini",
    `Pad and picture aligned — ${ctx.phrase}.`,
    ctx.ticketLive,
  );
}

function deepseek(ctx: AgentContext): AgentReceipt {
  if (ctx.heatVetoed) {
    return {
      role: "deepseek",
      action: "veto",
      text: "",
      model: "rules",
      policyOk: false,
      reason: "heat speech requires coupling ticket",
    };
  }
  if (!ctx.ticketLive || !ctx.phraseLive) {
    return quiet("deepseek", "no live coupling ticket");
  }
  const lines: Record<string, string> = {
    SNAP: "Snap window — pad and picture aligned.",
    SPRINT: "Controller heat on a live drive — eyes up.",
    CUT: "Cut on the hash — hands and picture together.",
    RELEASE: "Release — input spike fading.",
  };
  const text = lines[ctx.phrase];
  if (!text) return quiet("deepseek", "phrase not live");
  return commitHeat("deepseek", text, ctx.ticketLive);
}

export function agentsSignature(list: AgentReceipt[]): string {
  return list.map((a) => `${a.role}:${a.action}:${a.text}`).join("|");
}
