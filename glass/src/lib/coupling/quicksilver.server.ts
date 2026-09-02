/** Server-only Quicksilver Pro client. Same contract as qoresence.agents.llm_client. */

import { readFileSync, existsSync } from "node:fs";
import { resolve } from "node:path";

export const QS_BASE = "https://api.quicksilverpro.io/v1";
export const QS_CHAT_MODEL = "glm-5.3-flash";
export const QS_FALLBACK = "gpt-4o-mini";
export const QS_SCENE_MODEL = "deepseek-v4-flash";

const KEY_ENV = [
  "QUICKSILVER_API_KEY",
  "QUICKSILVERPRO_API_KEY",
  "QORESENCE_QUICKSILVER_API_KEY",
  "QORESENCE_CLUTCHBOT_LLM_API_KEY",
];

const KEY_FILES = [
  ".secrets/quicksilver_clutchbot.key",
  ".secrets/quicksilver.key",
  "/tmp/qoresence/.secrets/quicksilver_clutchbot.key",
  "/tmp/qoresence/.secrets/quicksilver.key",
];

function resolveKey(): string {
  for (const k of KEY_ENV) {
    const v = process.env[k]?.trim();
    if (v) return v;
  }
  const extra = process.env.QORESENCE_QUICKSILVER_KEY_FILE || process.env.QORESENCE_CLUTCHBOT_LLM_API_KEY_FILE;
  const files = extra ? [extra, ...KEY_FILES] : KEY_FILES;
  for (const f of files) {
    try {
      const p = resolve(f);
      if (!existsSync(p)) continue;
      const v = readFileSync(p, "utf8").trim();
      if (v) return v;
    } catch {
      /* skip */
    }
  }
  return "";
}

export function probeQuicksilver(): { live: boolean; model: string; base: string } {
  return { live: Boolean(resolveKey()), model: QS_CHAT_MODEL, base: QS_BASE };
}

export type EnhanceIn = {
  path: "fast" | "confirm";
  eventType: string;
  situation: Record<string, unknown>;
  baseMessage?: string;
  ticketLive: boolean;
};

export type EnhanceOut = {
  ok: boolean;
  text: string;
  model: string;
  error: string;
};

function systemPrompt(sit: Record<string, unknown>, path: "fast" | "confirm"): string {
  const game = String(sit.game_title || sit.gameTitle || "Madden NFL 27");
  const digits =
    path === "confirm"
      ? "CONFIRM PATH: you may cite score digits only if they appear in SituationState. Never invent a score."
      : "FAST PATH: no scores, no scorelines, no inventing digits.";
  return (
    `You are ClutchBot on the Qoresence observation plane for ${game}. ` +
    "Ground ONLY on the SituationState JSON. Never hallucinate score, quarter, down, or possession. " +
    "Keep chat <140 chars, hype but not cringe, no hashtags. If situation is uncertain, say nothing. " +
    "Never claim authorship or THROW. Never claim to be human. " +
    digits
  );
}

function userPrompt(data: EnhanceIn): string {
  const sit = JSON.stringify(data.situation).slice(0, 2000);
  const parts = [`Situation: ${sit}`, `Trigger event: ${data.eventType}`, `Path: ${data.path}`];
  if (data.baseMessage) parts.push(`Template (rewrite, keep meaning): ${data.baseMessage}`);
  parts.push("Respond with ONE chat line only. No quotes, no prefix.");
  return parts.join("\n");
}

async function postChat(messages: { role: string; content: string }[], model: string, key: string): Promise<{ text: string; error: string; model: string }> {
  const url = `${QS_BASE}/chat/completions`;
  const body = {
    model,
    messages,
    max_tokens: 140,
    temperature: 0.7,
    stream: false,
  };
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${key}`,
        "Content-Type": "application/json",
        Accept: "application/json",
        "User-Agent": "Qoresence-RetinaDeck/1.0",
      },
      body: JSON.stringify(body),
      signal: AbortSignal.timeout(8000),
    });
    const raw = await res.text();
    const reqId = res.headers.get("x-request-id") || "";
    if (res.status === 404 || res.status === 429) {
      if (model !== QS_FALLBACK) return postChat(messages, QS_FALLBACK, key);
    }
    if (!res.ok) {
      return {
        text: "",
        error: `HTTP ${res.status}${reqId ? ` ${reqId}` : ""} ${raw.slice(0, 180)}`,
        model,
      };
    }
    const data = JSON.parse(raw) as { choices?: { message?: { content?: string } }[] };
    const content = data.choices?.[0]?.message?.content;
    const text = typeof content === "string" ? content.trim().replace(/^["']|["']$/g, "") : "";
    if (!text || text.length < 4) return { text: "", error: "empty completion", model };
    return { text: text.slice(0, 140), error: "", model };
  } catch (err) {
    return { text: "", error: err instanceof Error ? err.message : "qs failed", model };
  }
}

const SCORE = /\b\d{1,2}\s*[-–—]\s*\d{1,2}\b/;

export function vetoQsLine(text: string, path: "fast" | "confirm"): string {
  const t = text.trim();
  if (!t) return "";
  if (/throw/i.test(t)) return "";
  if (path === "fast" && SCORE.test(t)) return "";
  return t.slice(0, 140);
}

export async function enhanceClutch(data: EnhanceIn): Promise<EnhanceOut> {
  const key = resolveKey();
  if (!key) return { ok: false, text: "", model: QS_CHAT_MODEL, error: "no Quicksilver key" };
  const messages = [
    { role: "system", content: systemPrompt(data.situation, data.path) },
    { role: "user", content: userPrompt(data) },
  ];
  const out = await postChat(messages, QS_CHAT_MODEL, key);
  if (!out.text) return { ok: false, text: "", model: out.model, error: out.error };
  const clean = vetoQsLine(out.text, data.path);
  if (!clean) return { ok: false, text: "", model: out.model, error: "policy stripped line" };
  return { ok: true, text: clean, model: out.model, error: "" };
}
