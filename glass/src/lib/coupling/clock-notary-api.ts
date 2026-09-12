import { getDeckOrigin } from "@/lib/coupling/hardware";

export type ClockNotaryExport = {
  ok?: boolean;
  error?: string;
  schema?: string;
  session_id?: string;
  plane?: string;
  clock_commitment?: string;
  ticks?: unknown[];
  sidecar_hashes?: Record<string, string>;
  locks?: unknown;
  notary?: { status?: string; reason?: string };
  door?: { live_truth?: string; seal_phrase?: string; chain?: string };
};

export type PresencePackExport = {
  ok?: boolean;
  error?: string;
  manifest?: {
    schema?: string;
    sku?: string;
    plane?: string;
    session_id?: string;
    clock_commitment?: string;
    hash_tail?: string;
    out_edge?: string;
    listing_status?: string;
    chain?: string;
    notary?: string;
    live_truth?: string;
  };
  listing?: {
    schema?: string;
    status?: string;
    sku?: string;
    title?: string;
    blurb?: string;
    clock_commitment?: string;
    hash_tail?: string;
    price?: number | null;
    out_edge?: string;
  };
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

export async function fetchPresencePack(sessionId?: string, fixture?: string): Promise<PresencePackExport> {
  const params = new URLSearchParams();
  if (sessionId) params.set("session_id", sessionId);
  if (fixture) params.set("fixture", fixture);
  const qs = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${origin()}/api/session/presence-pack${qs}`);
  return res.json();
}

export async function downloadPresenceZip(sessionId?: string, fixture?: string): Promise<boolean> {
  const params = new URLSearchParams();
  if (sessionId) params.set("session_id", sessionId);
  if (fixture) params.set("fixture", fixture);
  const qs = params.toString() ? `?${params.toString()}` : "";
  const res = await fetch(`${origin()}/api/session/presence-pack.zip${qs}`);
  const type = res.headers.get("content-type") || "";
  if (!res.ok || type.includes("application/json")) {
    return false;
  }
  const blob = await res.blob();
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "presence-pack.zip";
  a.click();
  URL.revokeObjectURL(a.href);
  return true;
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
