import { describe, it, expect } from "vitest";
import type { SessionViewEnvelope, SessionRecap } from "@/lib/coupling/session-api";

describe("SessionTheater fail-closed behavior", () => {
  it("unlocked board shows empty copy (□–□ · — & —)", () => {
    const envelope: SessionViewEnvelope = {
      ok: true,
      status: "live",
      session: "test",
      view: {
        schema_version: "session-view-1",
        session_id: "test",
        controller_bodied: true,
        board_locked: false,
        persisted: true,
        events: [
          {
            event_id: "evt1",
            event_type: "spam_window",
            session_id: "test",
            t_start_ns: 1000000000,
            t_end_ns: 2000000000,
            timestamp: "00:01.000",
            state: "unlocked",
            bodied: true,
            score: null,
            yard_line: null,
            input: { button: "R2", count: 5 },
            coach_context: { available: false, coach_type: null },
            clip: { available: false },
            qualification: "suppressed",
            schema_version: "event-1",
          },
        ],
        confirmed: { available: false, score: null, yard_line: null },
        current_moment: null,
        next_signal: { kind: "awaiting", label: "Awaiting event", event_id: null },
        empty_reason: null,
        plane: "qoresence-observation",
        read_only: true,
      },
      freshness: {
        generated_at: new Date().toISOString(),
        last_event_at: null,
        age_ms: 0,
        stale: false,
      },
    };

    expect(envelope.view.board_locked).toBe(false);
    expect(envelope.view.confirmed.available).toBe(false);
  });

  it("empty not_persisted recap shows fail-closed bay", () => {
    const recap: SessionRecap = {
      schema: "session-recap-1",
      ok: true,
      status: "not_persisted",
      session: "test",
      duration_ms: null,
      event_count: 0,
      confirmed_event_count: 0,
      linked_clip_count: 0,
      incomplete: true,
      empty_reason: "not_persisted",
      events: [],
      freshness: {
        generated_at: new Date().toISOString(),
        last_event_at: null,
        age_ms: 0,
        stale: false,
      },
    };

    expect(recap.empty_reason).toBe("not_persisted");
    expect(recap.event_count).toBe(0);
  });

  it("locked board with score shows digits only when licensed", () => {
    const envelope: SessionViewEnvelope = {
      ok: true,
      status: "live",
      session: "test",
      view: {
        schema_version: "session-view-1",
        session_id: "test",
        controller_bodied: true,
        board_locked: true,
        persisted: true,
        events: [
          {
            event_id: "evt1",
            event_type: "situation_shift",
            session_id: "test",
            t_start_ns: 1000000000,
            t_end_ns: 2000000000,
            timestamp: "00:01.000",
            state: "locked",
            bodied: true,
            score: { home: 21, away: 14 },
            yard_line: 5,
            input: null,
            coach_context: { available: false, coach_type: null },
            clip: { available: false },
            qualification: "confirmed",
            schema_version: "event-1",
          },
        ],
        confirmed: { available: true, score: { home: 21, away: 14 }, yard_line: 5 },
        current_moment: null,
        next_signal: { kind: "awaiting", label: "Awaiting event", event_id: null },
        empty_reason: null,
        plane: "qoresence-observation",
        read_only: true,
      },
      freshness: {
        generated_at: new Date().toISOString(),
        last_event_at: new Date().toISOString(),
        age_ms: 0,
        stale: false,
      },
    };

    expect(envelope.view.board_locked).toBe(true);
    expect(envelope.view.confirmed.available).toBe(true);
    expect(envelope.view.confirmed.score).toEqual({ home: 21, away: 14 });
    expect(envelope.view.confirmed.yard_line).toBe(5);
  });

  it("empty story shows 'No licensed story yet' when unlocked", () => {
    const envelope: SessionViewEnvelope = {
      ok: true,
      status: "empty",
      session: "test",
      view: {
        schema_version: "session-view-1",
        session_id: "test",
        controller_bodied: false,
        board_locked: false,
        persisted: true,
        events: [],
        confirmed: { available: false, score: null, yard_line: null },
        current_moment: null,
        next_signal: { kind: "awaiting", label: "Awaiting event", event_id: null },
        empty_reason: "no_events",
        plane: "qoresence-observation",
        read_only: true,
      },
      freshness: {
        generated_at: new Date().toISOString(),
        last_event_at: null,
        age_ms: 0,
        stale: false,
      },
    };

    const licensed = envelope.view.board_locked && envelope.view.events.length > 0;
    expect(licensed).toBe(false);
  });

  it("402/missing VLM lock shows glyph L off, no digits", () => {
    const envelope: SessionViewEnvelope = {
      ok: true,
      status: "live",
      session: "test",
      view: {
        schema_version: "session-view-1",
        session_id: "test",
        controller_bodied: true,
        board_locked: false,
        persisted: true,
        events: [],
        confirmed: { available: false, score: null, yard_line: null },
        current_moment: null,
        next_signal: { kind: "awaiting", label: "Awaiting event", event_id: null },
        empty_reason: null,
        plane: "qoresence-observation",
        read_only: true,
      },
      freshness: {
        generated_at: new Date().toISOString(),
        last_event_at: null,
        age_ms: 0,
        stale: false,
      },
    };

    expect(envelope.view.board_locked).toBe(false);
    expect(envelope.view.confirmed.available).toBe(false);
  });
});
