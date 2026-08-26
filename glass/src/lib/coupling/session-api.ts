/** Session Theater API — session-view-1 and session-recap-1 contracts. */

import { getDeckOrigin } from "./qoresence-deck";

export type SessionViewSchema = "session-view-1";
export type SessionRecapSchema = "session-recap-1";

export type SessionStatus = "live" | "empty" | "not_persisted" | "unavailable" | "invalid";

export type SessionEvent = {
  event_id: string;
  event_type: string;
  session_id: string;
  t_start_ns: number;
  t_end_ns: number;
  timestamp: string;
  state: "locked" | "unlocked";
  bodied: boolean;
  score: { home: number; away: number } | null;
  yard_line: number | null;
  input: {
    latency_ns?: number;
    count?: number;
    press_clock_ns?: number;
    button?: string;
  } | null;
  coach_context: {
    available: boolean;
    coach_type: string | null;
  };
  clip: {
    available: boolean;
    clip_id?: string;
  };
  qualification: "confirmed" | "suppressed" | "unavailable";
  schema_version: string;
};

export type SessionView = {
  schema_version: SessionViewSchema;
  session_id: string;
  controller_bodied: boolean;
  board_locked: boolean;
  persisted: boolean;
  events: SessionEvent[];
  confirmed: {
    available: boolean;
    score: { home: number; away: number } | null;
    yard_line: number | null;
  };
  current_moment: SessionEvent | null;
  next_signal: {
    kind: "coach" | "awaiting";
    label: string;
    event_id: string | null;
  };
  empty_reason: "no_events" | "not_persisted" | "unavailable" | "invalid" | null;
  plane: string;
  read_only: boolean;
};

export type SessionViewEnvelope = {
  ok: boolean;
  status: SessionStatus;
  session: string;
  view: SessionView;
  freshness: {
    generated_at: string;
    last_event_at: string | null;
    age_ms: number;
    stale: boolean;
  };
};

export type SessionRecap = {
  schema: SessionRecapSchema;
  ok: boolean;
  status: SessionStatus;
  session: string;
  duration_ms: number | null;
  event_count: number;
  confirmed_event_count: number;
  linked_clip_count: number;
  incomplete: boolean;
  empty_reason: "no_events" | "not_persisted" | null;
  events: SessionEvent[];
  freshness: {
    generated_at: string;
    last_event_at: string | null;
    age_ms: number;
    stale: boolean;
  };
};

export async function fetchSessionView(
  sessionId?: string,
  fixture?: string,
): Promise<SessionViewEnvelope> {
  const origin = getDeckOrigin();
  const params = new URLSearchParams();
  if (sessionId) params.set("session_id", sessionId);
  if (fixture) params.set("fixture", fixture);
  const url = `${origin}/api/session/view?${params.toString()}`;
  const res = await fetch(url);
  if (!res.ok) {
    return {
      ok: false,
      status: "unavailable",
      session: sessionId || "",
      view: emptyView(false),
      freshness: {
        generated_at: new Date().toISOString(),
        last_event_at: null,
        age_ms: 0,
        stale: false,
      },
    };
  }
  return await res.json();
}

export async function fetchSessionRecap(
  sessionId?: string,
  fixture?: string,
): Promise<SessionRecap> {
  const origin = getDeckOrigin();
  const params = new URLSearchParams();
  if (sessionId) params.set("session_id", sessionId);
  if (fixture) params.set("fixture", fixture);
  const url = `${origin}/api/session/recap?${params.toString()}`;
  const res = await fetch(url);
  if (!res.ok) {
    return {
      schema: "session-recap-1",
      ok: false,
      status: "unavailable",
      session: sessionId || "",
      duration_ms: null,
      event_count: 0,
      confirmed_event_count: 0,
      linked_clip_count: 0,
      incomplete: false,
      empty_reason: null,
      events: [],
      freshness: {
        generated_at: new Date().toISOString(),
        last_event_at: null,
        age_ms: 0,
        stale: false,
      },
    };
  }
  return await res.json();
}

function emptyView(persisted: boolean): SessionView {
  return {
    schema_version: "session-view-1",
    session_id: "",
    controller_bodied: false,
    board_locked: false,
    persisted,
    events: [],
    confirmed: { available: false, score: null, yard_line: null },
    current_moment: null,
    next_signal: { kind: "awaiting", label: "Awaiting event", event_id: null },
    empty_reason: persisted ? "no_events" : "not_persisted",
    plane: "qoresence-observation",
    read_only: true,
  };
}
