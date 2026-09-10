/** X Glass Timeline VOD — Create≠Post. Lobe default OFF. No free-text caption. */

import { getDeckOrigin } from "./qoresence-deck";

export type XGlassStatus = {
  enabled: boolean;
  grant: boolean;
  ready: boolean;
  last_reason: string;
  oauth_present?: boolean;
  draft?: {
    clip_name: string;
    media_url?: string;
    digit_silent?: boolean;
    caption_mode?: string;
    caption?: string;
  } | null;
};

export type CaptionMode = "auto" | "silent";

export type XGlassArmReason =
  | "ok"
  | "lobe_off"
  | "not_replay"
  | "no_mp4"
  | "digit_silent"
  | "busy"
  | "hold";

const CLIP_NAME = /^hdmi_clip_[\w.\-]+\.mp4$/i;

export function isFoundryMp4Name(name: string): boolean {
  return CLIP_NAME.test(String(name || "").trim());
}

export function parseXGlassStatus(raw: unknown): XGlassStatus {
  const bag = rec(raw);
  const x = rec(bag.x_glass || bag);
  return {
    enabled: Boolean(x.enabled),
    grant: Boolean(x.grant),
    ready: Boolean(x.ready),
    last_reason: String(x.last_reason || (x.enabled ? "idle" : "lobe_off")),
    oauth_present: x.oauth_present == null ? undefined : Boolean(x.oauth_present),
    draft: x.draft && typeof x.draft === "object" ? (x.draft as XGlassStatus["draft"]) : null,
  };
}

export function pickCaptionMode(boardLocked: boolean): CaptionMode {
  return boardLocked ? "auto" : "silent";
}

export function armPostReason(args: {
  stageMode: string;
  clipName: string;
  enabled: boolean;
  boardLocked: boolean;
  busy?: boolean;
}): XGlassArmReason {
  if (args.busy) return "busy";
  if (!args.enabled) return "lobe_off";
  if (args.stageMode !== "replay") return "not_replay";
  if (!isFoundryMp4Name(args.clipName)) return "no_mp4";
  // pickBoard-locked is the client hint for HOLD copy; server still digit-silences.
  if (!args.boardLocked) return "digit_silent";
  return "ok";
}

export function holdLabel(reason: XGlassArmReason, apiReason?: string): string {
  const r = (apiReason || reason || "").toLowerCase();
  if (r === "lobe_off" || reason === "lobe_off") return "HOLD · --x-glass";
  if (r === "digit_silent" || reason === "digit_silent") return "HOLD · digit silent";
  if (r === "no_mp4" || reason === "no_mp4") return "HOLD · no mp4";
  if (r === "not_replay" || reason === "not_replay") return "HOLD · replay";
  if (r === "no_grant") return "HOLD · no grant";
  if (r === "create_required") return "HOLD · create first";
  if (r === "oauth_missing") return "HOLD · oauth";
  if (r === "rate_limited") return "HOLD · rate";
  if (reason === "busy") return "Posting…";
  if (r && r !== "ok" && r !== "idle") return `HOLD · ${r}`;
  return "HOLD";
}

export type XGlassActionResult = {
  ok: boolean;
  action?: string;
  receipt_id?: string;
  caption?: string;
  clip_name?: string;
  tweet_id?: string;
  error?: string;
  reason?: string;
  status: number;
};

function failReason(body: Record<string, unknown>, status: number): string {
  const err = String(body.error || body.reason || "");
  if (err) return err;
  if (status === 404) return "no_mp4";
  if (status === 429) return "rate_limited";
  if (status === 503) return "oauth_missing";
  if (status === 403) return "lobe_off";
  return "hold";
}

export async function fetchXGlassStatus(origin?: string): Promise<XGlassStatus> {
  const base = origin || getDeckOrigin();
  try {
    const res = await fetch(`${base}/api/x-glass`, { cache: "no-store" });
    const json = await res.json().catch(() => ({}));
    return parseXGlassStatus(json);
  } catch {
    return { enabled: false, grant: false, ready: false, last_reason: "lobe_off", draft: null };
  }
}

export async function createXGlassDraft(args: {
  clipName: string;
  clipPath?: string;
  captionMode: CaptionMode;
  origin?: string;
}): Promise<XGlassActionResult> {
  const base = args.origin || getDeckOrigin();
  const body: Record<string, string> = {
    clip_name: args.clipName,
    caption_mode: args.captionMode,
  };
  if (args.clipPath) body.clip_path = args.clipPath;
  const res = await fetch(`${base}/api/x-glass/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = rec(await res.json().catch(() => ({})));
  return {
    ok: Boolean(json.ok) && res.ok,
    action: String(json.action || "create"),
    receipt_id: json.receipt_id != null ? String(json.receipt_id) : undefined,
    caption: json.caption != null ? String(json.caption) : undefined,
    clip_name: json.clip_name != null ? String(json.clip_name) : args.clipName,
    error: failReason(json, res.status),
    reason: failReason(json, res.status),
    status: res.status,
  };
}

export async function postXGlassVod(args: {
  clipName: string;
  clipPath?: string;
  captionMode: CaptionMode;
  origin?: string;
}): Promise<XGlassActionResult> {
  const base = args.origin || getDeckOrigin();
  const body: Record<string, string> = {
    clip_name: args.clipName,
    caption_mode: args.captionMode,
  };
  if (args.clipPath) body.clip_path = args.clipPath;
  const res = await fetch(`${base}/api/x-glass/post`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = rec(await res.json().catch(() => ({})));
  return {
    ok: Boolean(json.ok) && res.ok,
    action: String(json.action || "post"),
    receipt_id: json.receipt_id != null ? String(json.receipt_id) : undefined,
    caption: json.caption != null ? String(json.caption) : undefined,
    clip_name: json.clip_name != null ? String(json.clip_name) : args.clipName,
    tweet_id: json.tweet_id != null ? String(json.tweet_id) : undefined,
    error: failReason(json, res.status),
    reason: failReason(json, res.status),
    status: res.status,
  };
}

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}
