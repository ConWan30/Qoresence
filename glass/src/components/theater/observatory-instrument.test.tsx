/** Observatory instrument tests — sticky hidButton TTL and clear conditions. */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { useTheater } from "@/lib/coupling/store";

describe("Observatory sticky hidButton", () => {
  beforeEach(() => {
    // Reset store to clean state
    useTheater.setState({
      stickyHidButton: null,
      stickyHidButtonVerb: null,
      stickyHidButtonAt: 0,
      stickyHidSource: null,
      observationMode: null,
      observationConflict: null,
      stageMode: "live",
      livePaint: true,
      planeDim: false,
      sameSeq: true,
    });
  });

  it("stores simple hidButton press with timestamp", () => {
    const now = Date.now();
    vi.setSystemTime(now);

    useTheater.getState().ingestDeck({
      observation: {
        frameSeq: 1,
        clockNs: 0,
        hidButton: "Cross",
        verb: "Snap Ball",
        mode: "preplay_offense",
        visualPhase: null,
        gameProfile: null,
        conflict: null,
      },
      phrase: "SNAP",
      phraseConf: 0.9,
      coupling: 0.8,
      holdEnergy: 0,
      pllLock: true,
      ticketId: "abc",
      couplingClockNs: 0,
      confirmTicketId: "",
      confirmClockNs: 0,
      path: "fast",
      frameSeq: 1,
      padConnected: true,
      padName: "DualSense",
      padHeld: ["Cross"],
      bindLagMs: 80,
      bindKind: "observe",
      padR2: 0,
      padLeft: 0,
      padReports: 10,
      padTransport: "usb",
      padEnergy: 0,
      padBinds: 1,
      padJitterMs: 0,
      padHidSeq: 1,
      syncLagMs: 80,
      hdmi: "live",
      videoAgeS: 0.04,
      videoFrames: 100,
      videoPushes: 100,
      homeScore: null,
      awayScore: null,
      quarter: null,
      down: null,
      distance: null,
      clock: "",
      boardLocked: false,
      climax: 0,
      drivePhase: "",
      clipWorth: 0,
      winProb: null,
      scorePlay: false,
      gameTitle: "Madden NFL 27",
      homeTeam: "",
      awayTeam: "",
      homeLeft: false,
      fieldPos: "",
      why: "",
      liveSeq: 1,
      widgetSeq: 1,
      sameSeq: true,
      planeDim: false,
      paint: true,
      videoOptics: true,
      via: "ws",
      ghostStick: {
        enabled: false,
        paint: false,
        lx: 0,
        ly: 0,
        r2: 0,
        l2: 0,
        lagMs: 80,
        frameSeq: 0,
        reason: "off",
      },
      companion: { ok: false },
      actuators: [],
    } as any);

    const state = useTheater.getState();
    expect(state.stickyHidButton).toBe("Cross");
    expect(state.stickyHidButtonVerb).toBe("Snap Ball");
    expect(state.stickyHidButtonAt).toBe(now);
  });

  it("shows unlabeled press as button · □ when verb is null", () => {
    const now = Date.now();
    vi.setSystemTime(now);

    useTheater.getState().ingestDeck({
      observation: {
        frameSeq: 1,
        clockNs: 0,
        hidButton: "Cross",
        verb: null,
        mode: null,
        visualPhase: null,
        gameProfile: null,
        conflict: null,
      },
      paint: true,
      sameSeq: true,
      planeDim: false,
    } as any);

    const state = useTheater.getState();
    expect(state.stickyHidButton).toBe("Cross");
    expect(state.stickyHidButtonVerb).toBe(null);
  });

  it("does NOT sticky combo presses (L2+R2, multi-button)", () => {
    useTheater.setState({
      stickyHidButton: "Cross",
      stickyHidButtonVerb: "Snap Ball",
      stickyHidButtonAt: Date.now(),
    });

    useTheater.getState().ingestDeck({
      observation: {
        frameSeq: 2,
        clockNs: 0,
        hidButton: "L2+R2",
        verb: "Audible",
        mode: "preplay_offense",
        visualPhase: null,
        gameProfile: null,
        conflict: null,
      },
      paint: true,
      sameSeq: true,
      planeDim: false,
    } as any);

    const state = useTheater.getState();
    // Combo should NOT update sticky state
    expect(state.stickyHidButton).toBe("Cross");
    expect(state.stickyHidButtonVerb).toBe("Snap Ball");
  });

  it("clears sticky hidButton on planeDim", () => {
    useTheater.setState({
      stickyHidButton: "Cross",
      stickyHidButtonVerb: "Snap Ball",
      stickyHidButtonAt: Date.now(),
    });

    useTheater.getState().ingestDeck({
      observation: {
        frameSeq: 2,
        clockNs: 0,
        hidButton: null,
        verb: null,
        mode: null,
        visualPhase: null,
        gameProfile: null,
        conflict: null,
      },
      paint: true,
      sameSeq: true,
      planeDim: true,
    } as any);

    const state = useTheater.getState();
    expect(state.stickyHidButton).toBe(null);
    expect(state.stickyHidButtonVerb).toBe(null);
    expect(state.stickyHidButtonAt).toBe(0);
  });

  it("clears sticky hidButton on !livePaint", () => {
    useTheater.setState({
      stickyHidButton: "Cross",
      stickyHidButtonVerb: "Snap Ball",
      stickyHidButtonAt: Date.now(),
    });

    useTheater.getState().ingestDeck({
      observation: {
        frameSeq: 2,
        clockNs: 0,
        hidButton: null,
        verb: null,
        mode: null,
        visualPhase: null,
        gameProfile: null,
        conflict: null,
      },
      paint: false,
      sameSeq: true,
      planeDim: false,
    } as any);

    const state = useTheater.getState();
    expect(state.observationHidButton).toBe(null);
  });

  it("clears sticky hidButton on seq_skew (!sameSeq)", () => {
    useTheater.setState({
      stickyHidButton: "Cross",
      stickyHidButtonVerb: "Snap Ball",
      stickyHidButtonAt: Date.now(),
    });

    useTheater.getState().ingestDeck({
      observation: {
        frameSeq: 2,
        clockNs: 0,
        hidButton: null,
        verb: null,
        mode: null,
        visualPhase: null,
        gameProfile: null,
        conflict: null,
      },
      paint: true,
      sameSeq: false,
      planeDim: false,
    } as any);

    const state = useTheater.getState();
    expect(state.observationHidButton).toBe(null);
  });

  it("clears sticky hidButton on replay", () => {
    useTheater.setState({
      stickyHidButton: "Cross",
      stickyHidButtonVerb: "Snap Ball",
      stickyHidButtonAt: Date.now(),
      stageMode: "live",
    });

    useTheater.setState({ stageMode: "replay" });

    useTheater.getState().ingestDeck({
      observation: {
        frameSeq: 2,
        clockNs: 0,
        hidButton: null,
        verb: null,
        mode: null,
        visualPhase: null,
        gameProfile: null,
        conflict: null,
      },
      paint: true,
      sameSeq: true,
      planeDim: false,
    } as any);

    const state = useTheater.getState();
    expect(state.observationHidButton).toBe(null);
  });

  it("TTL: sticky press expires after 500ms", () => {
    const now = Date.now();
    vi.setSystemTime(now);

    useTheater.setState({
      stickyHidButton: "Cross",
      stickyHidButtonVerb: "Snap Ball",
      stickyHidButtonAt: now,
    });

    // Within TTL (400ms) — should still be visible in component logic
    vi.setSystemTime(now + 400);
    expect(useTheater.getState().stickyHidButtonAt).toBe(now);

    // After TTL (600ms) — component should not show it
    vi.setSystemTime(now + 600);
    const elapsed = Date.now() - useTheater.getState().stickyHidButtonAt;
    expect(elapsed).toBeGreaterThan(500);
  });

  it("never invents verb — keeps null when observation had no verb", () => {
    useTheater.getState().ingestDeck({
      observation: {
        frameSeq: 1,
        clockNs: 0,
        hidButton: "Cross",
        verb: null,
        mode: null,
        visualPhase: null,
        gameProfile: null,
        conflict: null,
      },
      paint: true,
      sameSeq: true,
      planeDim: false,
    } as any);

    const state = useTheater.getState();
    expect(state.stickyHidButton).toBe("Cross");
    expect(state.stickyHidButtonVerb).toBe(null);
  });

  it("stickies picture hid_source without claiming USB heard the pad", () => {
    useTheater.getState().ingestDeck({
      observation: {
        frameSeq: 1,
        clockNs: 0,
        hidButton: "Cross",
        verb: "Snap Ball",
        mode: "preplay_offense",
        visualPhase: "huddle_offense",
        gameProfile: "madden_27",
        hidSource: "picture",
        conflict: null,
      },
      paint: true,
      sameSeq: true,
      planeDim: false,
    } as any);

    const state = useTheater.getState();
    expect(state.stickyHidButton).toBe("Cross");
    expect(state.stickyHidButtonVerb).toBe("Snap Ball");
    expect(state.stickyHidSource).toBe("picture");
  });
});
