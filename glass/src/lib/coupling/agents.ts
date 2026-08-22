/** Agent Society + ClutchBot — Quicksilver phrasing, observation plane only.
 *  Heat requires a live coupling ticket. Score digits require a confirm ticket.
 *  THROW is forbidden. No authorship. */

import type { AgentPlane } from "./agent-plane";
import { companionDutyLine, type AgentCompanion } from "./companion.ts";
import {
  heatSpeech,
  licenseScoreText,
  type ConfirmTicket,
  type Phrase,
} from "./engine";

export type AgentRole =
  | "clutchbot"
  | "gemini"
  | "deepseek"
  | "drive_coach"
  | "spam_warden"
  | "ghost_editor"
  | "pilot_auditor"
  | "prediction_steward";

export type AgentAction = "chat" | "note" | "veto" | "allow" | "quiet";

export type AgentReceipt = {
  role: AgentRole;
  action: AgentAction;
  text: string;
  model: "quicksilver" | "rules";
  policyOk: boolean;
  reason: string;
};

const ROLE_ORDER: AgentRole[] = [
  "clutchbot",
  "gemini",
  "deepseek",
  "drive_coach",
  "spam_warden",
  "ghost_editor",
  "pilot_auditor",
  "prediction_steward",
];

export const ROLE_LABEL: Record<AgentRole, string> = {
  clutchbot: "ClutchBot",
  gemini: "Gemini",
  deepseek: "DeepSeek",
  drive_coach: "Drive coach",
  spam_warden: "Warden",
  ghost_editor: "Ghost editor",
  pilot_auditor: "Auditor",
  prediction_steward: "Steward",
};

const SOCIETY_ROLES: AgentRole[] = [
  "drive_coach",
  "spam_warden",
  "ghost_editor",
  "pilot_auditor",
  "prediction_steward",
];

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

function asAction(raw: string): AgentAction {
  if (raw === "veto" || raw === "chat" || raw === "note" || raw === "allow" || raw === "quiet") return raw;
  if (raw === "advise" || raw === "audit" || raw === "propose_cut") return "note";
  return "note";
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
  const receipts: Record<AgentRole, AgentReceipt> = {
    clutchbot: clutchbot(ctx),
    gemini: gemini(ctx),
    deepseek: deepseek(ctx),
    drive_coach: coach(ctx),
    spam_warden: warden(ctx),
    ghost_editor: ghost(ctx),
    pilot_auditor: quiet("pilot_auditor", "society wait"),
    prediction_steward: quiet("prediction_steward", "society wait"),
  };
  return ROLE_ORDER.map((r) => receipts[r]);
}

export function mergeAgentPlane(
  local: AgentReceipt[],
  plane: AgentPlane | null,
  ticketLive: boolean,
): AgentReceipt[] {
  if (!plane) return local;
  const byRole = Object.fromEntries(local.map((r) => [r.role, r])) as Record<AgentRole, AgentReceipt>;

  if (plane.clutchbot) {
    const commit = plane.commits[0];
    if (commit?.text) {
      byRole.clutchbot = commitHeat("clutchbot", commit.text, ticketLive, "quicksilver");
      if (byRole.clutchbot.action === "chat") {
        byRole.clutchbot = { ...byRole.clutchbot, reason: commit.reason || "a2a commit" };
      }
    } else if (byRole.clutchbot.action === "quiet") {
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
  } else if (plane.geminiLive && byRole.gemini.action === "quiet") {
    byRole.gemini = {
      role: "gemini",
      action: "note",
      text: "Gemini VLM live — waiting for an honest board lock",
      model: "quicksilver",
      policyOk: true,
      reason: "a2a gemini",
    };
  }
  if (plane.deepseekLive && byRole.deepseek.action === "quiet") {
    byRole.deepseek = {
      role: "deepseek",
      action: "note",
      text: "Chat agent live",
      model: "quicksilver",
      policyOk: true,
      reason: "a2a deepseek",
    };
  }

  if (plane.society) {
    for (const note of plane.societyLast) {
      const role = note.role as AgentRole;
      if (!SOCIETY_ROLES.includes(role)) continue;
      const text = note.text;
      if (heatSpeech(text) && !ticketLive) {
        byRole[role] = {
          role,
          action: "veto",
          text: "",
          model: "rules",
          policyOk: false,
          reason: "heat speech requires coupling ticket",
        };
        continue;
      }
      byRole[role] = {
        role,
        action: asAction(note.action),
        text,
        model: /quick|nemo|gemini|deep/i.test(note.reason) ? "quicksilver" : "rules",
        policyOk: true,
        reason: note.reason || "society",
      };
    }
    for (const role of SOCIETY_ROLES) {
      if (byRole[role].action === "quiet") {
        const named = plane.societyRoles.includes(role);
        if (named || plane.society) {
          byRole[role] = {
            role,
            action: "note",
            text: "Society armed",
            model: "rules",
            policyOk: true,
            reason: "agent society live",
          };
        }
      }
    }
  }

  return ROLE_ORDER.map((r) => byRole[r]);
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

function ghost(ctx: AgentContext): AgentReceipt {
  const cut = ctx.companion?.cut;
  if (cut?.title || cut?.text) {
    return {
      role: "ghost_editor",
      action: "note",
      text: cut.text || `propose_cut ${cut.title}`,
      model: "rules",
      policyOk: true,
      reason: "ghost propose_cut — operator exports",
    };
  }
  return quiet("ghost_editor", "society wait");
}

function coach(ctx: AgentContext): AgentReceipt {
  if (ctx.companion?.coach) {
    return {
      role: "drive_coach",
      action: "note",
      text: ctx.companion.coach,
      model: "rules",
      policyOk: true,
      reason: "society drive coach",
    };
  }
  if (!ctx.hdmiLive || ctx.phrase === "IDLE" || (ctx.phrase === "HUDDLE" && !ctx.ticketLive)) {
    return quiet("drive_coach", "no drive");
  }
  const ticketBit = ctx.ticketLive
    ? "Coupling ticket live. Heat is licensed."
    : "Couple: none.";
  const text = `Phrase ${ctx.phrase}. ${ticketBit}`;
  return {
    role: "drive_coach",
    action: "note",
    text,
    model: "rules",
    policyOk: true,
    reason: "observation-plane coach",
  };
}

function warden(ctx: AgentContext): AgentReceipt {
  if (ctx.heatVetoed || (!ctx.ticketLive && ctx.phraseLive && !ctx.pllLock)) {
    return {
      role: "spam_warden",
      action: "veto",
      text: "Heat stripped. Coupling ticket required.",
      model: "rules",
      policyOk: false,
      reason: "heat speech requires coupling ticket",
    };
  }
  if (ctx.ticketLive) {
    return {
      role: "spam_warden",
      action: "allow",
      text: `Ticket ${ctx.ticketId.slice(0, 8)} live.`,
      model: "rules",
      policyOk: true,
      reason: "coupling ticket live",
    };
  }
  return {
    role: "spam_warden",
    action: "allow",
    text: "Quiet. Nothing to license.",
    model: "rules",
    policyOk: true,
    reason: "no heat proposal",
  };
}

export function agentsSignature(list: AgentReceipt[]): string {
  return list.map((a) => `${a.role}:${a.action}:${a.text}`).join("|");
}
