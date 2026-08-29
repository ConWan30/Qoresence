/** Live Deck monitor — /retina WS + /api/situation poll. Observation only. */

import { fetchAgentPlane, parseAgentPlane, type AgentPlane } from "./agent-plane";
import { parseDeckMessage, type DeckIngest } from "./board";
import { parseHdmiClipList } from "./clip";
import { parseFeedMoment, parseSnapshotMoments, type FeedMoment } from "./clutch";
import { parseMatchAgentNote } from "./match-agent";
import { parseStemProgram, type StemProgram } from "./stem";
import { getDeckOrigin, probeDeck } from "./qoresence-deck";
import { useTheater } from "./store";

export type { DeckIngest } from "./board";
export { boardLine, parseDeckMessage, pickBoard, situationLine } from "./board";
export type { FeedMoment } from "./clutch";

/** While WS is fresh, poll must not own paint/sameSeq/planeDim or wipe the board. */
const WS_OPTICS_HOLD_MS = 2000;

export function startDeckMonitor(
  onSnap: (ing: DeckIngest) => void,
  onPlane?: (plane: AgentPlane) => void,
  onMoment?: (m: FeedMoment) => void,
  onStem?: (p: StemProgram) => void,
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

  const ingestRaw = (raw: unknown, via: "ws" | "poll") => {
    const rec = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : null;
    if (rec?.type === "stem_program") {
      const p = parseStemProgram(rec);
      if (p) onStem?.(p);
      return;
    }
    if (rec?.type === "moment") {
      const fm = parseFeedMoment(rec);
      if (fm) onMoment?.(fm);
      return;
    }
    const ing = parseDeckMessage(raw);
    if (ing) onSnap({ ...ing, via });
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
          ingestRaw(JSON.parse(String(ev.data)), "ws");
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
    const st0 = useTheater.getState();
    const wsOpen = ws != null && ws.readyState === WebSocket.OPEN;
    const wsFresh = wsOpen && st0.deckLive && Date.now() - st0.deckAt < WS_OPTICS_HOLD_MS;
    const clipsBody = await readJson(`${probe.origin}/api/clips`);
    useTheater.getState().ingestClips(parseHdmiClipList(clipsBody, probe.origin));
    // match_agent lives on /api/situation (and /health), not /retina WS.
    // Harvest even while WS is fresh — do not ingest optics/board from this poll.
    if (wsFresh) {
      const sit = await readJson(`${probe.origin}/api/situation`);
      if (sit != null) useTheater.getState().ingestMatchAgent(parseMatchAgentNote(sit));
      return;
    }
    const [body, snap, events, planeBody] = await Promise.all([
      readJson(`${probe.origin}/api/situation`),
      readJson(`${probe.origin}/api/agent/snapshot`),
      readJson(`${probe.origin}/api/agent/events?limit=12`),
      readJson(`${probe.origin}/api/agent/plane`),
    ]);
    if (body != null) useTheater.getState().ingestMatchAgent(parseMatchAgentNote(body));
    if (body) ingestRaw(body, "poll");
    if (snap) ingestRaw(snap, "poll");
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
