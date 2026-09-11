/** Session Recap export client. Seal/verify live on QorTroller — not Deck glass. */

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

export async function copyText(text: string): Promise<void> {
  if (!text) return;
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
  }
}

/** Hash clipboard only — not Discord notary. */
export const copyDiscordCard = copyText;

export function downloadJson(name: string, obj: unknown): void {
  const blob = new Blob([`${JSON.stringify(obj, null, 2)}\n`], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = name;
  a.click();
  URL.revokeObjectURL(a.href);
}
