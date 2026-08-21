/** Pattern B: Qoresence owns the card. This glass is a same-origin viewer
 *  when served from Deck, or it hunts the local Deck origin. */

export const DECK_FALLBACK_ORIGIN = "http://127.0.0.1:8765";

export type DeckProbe = {
  up: boolean;
  label: string;
  origin: string;
};

let liveOrigin = "";

export function getDeckOrigin(): string {
  if (liveOrigin) return liveOrigin;
  if (typeof window !== "undefined" && window.location?.origin && window.location.origin !== "null") {
    return window.location.origin;
  }
  return DECK_FALLBACK_ORIGIN;
}

export function deckMjpegUrl(): string {
  return `${getDeckOrigin()}/video?fps=60&t=${Date.now()}`;
}

export function deckLiveJpgUrl(): string {
  return `${getDeckOrigin()}/live.jpg?t=${Date.now()}`;
}

function candidates(): string[] {
  const out: string[] = [];
  if (typeof window !== "undefined" && window.location?.origin && window.location.origin !== "null") {
    out.push(window.location.origin);
  }
  out.push(DECK_FALLBACK_ORIGIN);
  return [...new Set(out)];
}

export async function probeDeck(): Promise<DeckProbe> {
  for (const origin of candidates()) {
    try {
      const ctrl = new AbortController();
      const timer = window.setTimeout(() => ctrl.abort(), 900);
      const res = await fetch(`${origin}/api/situation`, {
        cache: "no-store",
        mode: "cors",
        signal: ctrl.signal,
      });
      window.clearTimeout(timer);
      if (res.ok) {
        liveOrigin = origin;
        return { up: true, label: "Qoresence LIVE", origin };
      }
    } catch {
      /* try next origin */
    }
  }
  return { up: false, label: "", origin: "" };
}
