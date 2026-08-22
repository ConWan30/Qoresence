/** Live Deck monitor — /retina WS + /api/situation poll. Observation only. */

import { fetchAgentPlane, parseAgentPlane, type AgentPlane } from "./agent-plane";
import { parseDeckMessage, type DeckIngest } from "./board";
import { parseFeedMoment, parseSnapshotMoments, type FeedMoment } from "./clutch";
import { getDeckOrigin, probeDeck } from "./qoresence-deck";

export type { DeckIngest } from "./board";
export { boardLine, parseDeckMessage, pickBoard, situationLine } from "./board";
export type { FeedMoment } from "./clutch";

export function startDeckMonitor(
  onSnap: (ing: DeckIngest) => void,
  onPlane?: (plane: AgentPlane) => void,
  onMoment?: (m: FeedMoment) => void,
): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let poll = 0;
  let retry = 0;

  const readJson = async (url: string) => {
    const ctrl = new AbortController();
    const t = window.setTimeout(() => ctrl.abort(), 5000);
    try {
      const res = await fetch(url, { cache: "no-store", mode: "cors", signal: ctrl.signal });
      if (!res.ok) return null;
      return (await res.json()) as unknown;
    } catch {
      return null;
    } finally {
      window.clearTimeout(t);
    }
  };

  const ingestRaw = (raw: unknown) => {
    const rec = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : null;
    if (rec?.type === "moment") {
      const fm = parseFeedMoment(rec);
      if (fm) onMoment?.(fm);
      return;
    }
    const ing = parseDeckMessage(raw);
    if (ing) onSnap(ing);
    for (const fm of parseSnapshotMoments(raw)) onMoment?.(fm);
  };

  const connectWs = () => {
    if (closed) return;
    const origin = getDeckOrigin();
    const url = origin.replace(/^http/, "ws") + "/retina";
    try {
      ws = new WebSocket(url);
      ws.onmessage = (ev) => {
        try {
          ingestRaw(JSON.parse(String(ev.data)));
        } catch {
          /* ignore bad frames */
        }
      };
      ws.onclose = () => {
        ws = null;
        if (!closed) {
          retry = window.setTimeout(connectWs, 1200);
        }
      };
      ws.onerror = () => {
        try {
          ws?.close();
        } catch {
          /* ignore */
        }
      };
    } catch {
      retry = window.setTimeout(connectWs, 1200);
    }
  };

  const tickPoll = async () => {
    const probe = await probeDeck();
    if (!probe.up) return;
    const [body, snap, events, planeBody] = await Promise.all([
      readJson(`${probe.origin}/api/situation`),
      readJson(`${probe.origin}/api/agent/snapshot`),
      readJson(`${probe.origin}/api/agent/events?limit=12`),
      readJson(`${probe.origin}/api/agent/plane`),
    ]);
    if (body) ingestRaw(body);
    if (snap) ingestRaw(snap);
    const evBag = events && typeof events === "object" ? (events as Record<string, unknown>) : null;
    const list = evBag && Array.isArray(evBag.events) ? evBag.events : [];
    for (const ev of list) {
      const fm = parseFeedMoment(ev);
      if (fm) onMoment?.(fm);
    }
    if (onPlane) {
      const plane = planeBody
        ? parseAgentPlane({ health: planeBody, agentHealth: planeBody, snapshot: snap || planeBody })
        : await fetchAgentPlane();
      if (plane) onPlane(plane);
    }
  };

  void tickPoll();
  connectWs();
  poll = window.setInterval(() => void tickPoll(), 1000);

  return () => {
    closed = true;
    window.clearInterval(poll);
    window.clearTimeout(retry);
    try {
      ws?.close();
    } catch {
      /* ignore */
    }
  };
}
