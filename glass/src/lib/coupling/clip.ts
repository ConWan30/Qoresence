/** HDMI clip export — Qoresence owns the ring. This glass only requests. */

import type { ClutchKind } from "./clutch";

export type ClipResult = {
  ok: boolean;
  url: string;
  name: string;
  path: string;
  seconds: number;
  error: string;
};

export function shouldClip(kind: ClutchKind, clipWorth: number): boolean {
  if (kind === "score_play" || kind === "climax") return true;
  return clipWorth >= 0.65;
}

export function clipSeconds(kind: ClutchKind): number {
  if (kind === "score_play") return 15;
  if (kind === "climax") return 12;
  return 8;
}

const CLIP_NAME = /^hdmi_clip_[\w.\-]+\.(mp4|avi)$/i;

/** Public /media/clips path from a Deck url, name, or local filesystem path. */
export function clipPublicPath(raw: string): string {
  const s = String(raw || "").trim();
  if (!s) return "";
  if (/^https?:\/\//i.test(s)) {
    try {
      const u = new URL(s);
      return u.pathname.startsWith("/media/clips/") ? u.pathname : "";
    } catch {
      return "";
    }
  }
  if (s.startsWith("/media/clips/")) return s.split("?")[0];
  const name = s.replace(/\\/g, "/").split("/").pop() || "";
  return CLIP_NAME.test(name) ? `/media/clips/${name}` : "";
}

export function clipHref(raw: string, origin?: string): string {
  const path = clipPublicPath(raw);
  if (!path) return "";
  if (/^https?:\/\//i.test(path)) return path;
  const base =
    origin ||
    (typeof window !== "undefined" && window.location?.origin && window.location.origin !== "null"
      ? window.location.origin
      : "http://127.0.0.1:8765");
  return `${base}${path}`;
}

export function momentLooksLikeClip(m: {
  url?: string;
  name?: string;
  icon?: string;
  title?: string;
  key?: string;
}): boolean {
  if (m.url || (m.name && CLIP_NAME.test(m.name))) return true;
  if (m.icon === "🎬") return true;
  if (m.key?.startsWith("clip:")) return true;
  return /clip/i.test(m.title || "");
}

/** Chip href: own file first, else last HDMI clip for clip/clutch rows. */
export function momentPlayHref(
  m: { url?: string; name?: string; icon?: string; title?: string; key?: string },
  lastClipUrl = "",
): string {
  const own = clipHref(m.url || m.name || "");
  if (own) return own;
  if (momentLooksLikeClip(m) || m.key?.startsWith("clutch:")) return clipHref(lastClipUrl);
  return "";
}

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

export function parseClipResult(raw: unknown, seconds: number): ClipResult {
  const d = rec(raw);
  const inner = rec(d.result);
  const bag = Object.keys(inner).length ? { ...d, ...inner } : d;
  const file = String(bag.path || bag.file || bag.clip || "");
  const name = String(bag.name || file.split(/[/\\]/).pop() || "");
  const url = String(bag.url || (name ? `/media/clips/${name}` : ""));
  const ok = bag.ok !== false && Boolean(url || file);
  return {
    ok,
    url,
    name,
    path: file,
    seconds,
    error: ok ? "" : String(bag.error || "clip_unavailable"),
  };
}

export async function requestDeckClip(seconds = 10): Promise<ClipResult> {
  const sec = Math.max(2, Math.min(30, seconds));
  const { getDeckOrigin, probeDeck } = await import("./qoresence-deck");
  const probe = await probeDeck();
  const origin = probe.up ? probe.origin : getDeckOrigin();
  try {
    const res = await fetch(`${origin}/api/agent/clip`, {
      method: "POST",
      mode: "cors",
      cache: "no-store",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ seconds: sec }),
      signal: AbortSignal.timeout(8000),
    });
    const raw = await res.json().catch(() => ({}));
    if (res.status === 429) {
      return { ok: false, url: "", name: "", path: "", seconds: sec, error: "clip_rate_limited" };
    }
    if (!res.ok) {
      const d = rec(raw);
      return {
        ok: false,
        url: "",
        name: "",
        path: "",
        seconds: sec,
        error: String(d.error || `HTTP ${res.status}`),
      };
    }
    return parseClipResult(raw, sec);
  } catch (err) {
    return {
      ok: false,
      url: "",
      name: "",
      path: "",
      seconds: sec,
      error: err instanceof Error ? err.message : "clip failed",
    };
  }
}
