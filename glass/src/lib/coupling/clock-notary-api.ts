import { getDeckOrigin } from "./qoresence-deck";

export type ClockNotaryExport = {
  ok: boolean;
  schema?: string;
  session_id?: string;
  clock_commitment?: string;
  plane?: string;
  error?: string;
  ticks?: unknown[];
  locks?: unknown;
  notary?: { status?: string; reason?: string };
  door?: { live_truth?: string; seal_phrase?: string; chain?: string };
};

export type ClockNotarySeal = {
  ok: boolean;
  status: string;
  reason?: string;
  hint?: string;
  clock_commitment?: string;
  wrap?: Record<string, unknown>;
  discord_card?: string;
  chain?: string;
  locks?: { truth?: { state?: string } };
};

export type ClockNotaryVerify = {
  ok: boolean;
  passed: number;
  total: number;
  clock_commitment?: string;
  checks: { name: string; ok: boolean; detail?: string }[];
  trust?: string;
};

function origin(): string {
  try {
    return getDeckOrigin();
  } catch {
    return "";
  }
}

export async function exportClockEnvelope(sessionId?: string, fixture?: string): Promise<ClockNotaryExport> {
  const params = new URLSearchParams();
  if (sessionId) params.set("session_id", sessionId);
  if (fixture) params.set("fixture", fixture);
  const qs = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${origin()}/api/session/clock-notary${qs}`);
  return res.json();
}

export async function sealClockEnvelope(payload: Record<string, unknown>): Promise<ClockNotarySeal> {
  const res = await fetch(`${origin()}/api/session/clock-notary/seal`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json();
}

export async function verifyClockWrap(wrap: unknown, envelope: unknown): Promise<ClockNotaryVerify> {
  const res = await fetch(`${origin()}/api/session/clock-notary/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ wrap, envelope }),
  });
  return res.json();
}

export async function copyDiscordCard(text: string): Promise<void> {
  if (!text) return;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
  }
}

export function downloadJson(name: string, obj: unknown): void {
  const blob = new Blob([`${JSON.stringify(obj, null, 2)}\n`], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}
