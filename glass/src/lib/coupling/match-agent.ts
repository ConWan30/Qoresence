/** MatchAgent last_note — fail-closed chrome from Deck poll JSON.
 *  Bind `match_agent` on /health and /api/situation. Empty {} is empty.
 *  Never invent scores. Observation only. DualSense stays on the PS5.
 */

export type MatchAgentPath = "fast" | "confirm";

export type MatchAgentNote = {
  text: string;
  path: MatchAgentPath;
  ticketId: string;
  model: string;
};

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function bagOf(raw: unknown): Record<string, unknown> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) return {};
  const m = rec(raw);
  if (m.match_agent != null) {
    const nested = m.match_agent;
    if (!nested || typeof nested !== "object" || Array.isArray(nested)) return {};
    return rec(nested);
  }
  if (m.ok != null || m.text != null || m.path != null || m.ticket_id != null) return m;
  return {};
}

/** Licensed note only. {} / missing / !ok / !live / hold / empty text → null. */
export function parseMatchAgentNote(raw: unknown): MatchAgentNote | null {
  const bag = bagOf(raw);
  if (!Object.keys(bag).length) return null;
  if (bag.ok !== true) return null;
  if (bag.live !== true) return null;
  const text = String(bag.text ?? "").trim();
  if (!text) return null;
  const ticketId = String(bag.ticket_id ?? bag.ticketId ?? "").trim();
  if (!ticketId) return null;
  const pathRaw = String(bag.path ?? "").toLowerCase();
  if (pathRaw !== "fast" && pathRaw !== "confirm") return null;
  return {
    text: text.slice(0, 280),
    path: pathRaw,
    ticketId,
    model: String(bag.model ?? ""),
  };
}
