import { useEffect } from "react";
import { cameraGranted, captureNeedsRebind, diagnoseEnv, getFeedKind, keepVideoPlaying, readPad } from "./hardware";
import { probeDeck } from "./qoresence-deck";
import { startDeckMonitor } from "./monitor";
import { useTheater } from "./store";
import { hidAt, pushHid, videoClock } from "./sync";

export function useTheaterLoop() {
  useEffect(() => {
    let raf = 0;
    let last = 0;
    let prevR2 = 0;
    let rebindAt = 0;

    const env = diagnoseEnv();
    useTheater.getState().noteFramed(env.framed);

    const ingestPad = () => {
      const st = useTheater.getState();
      // Qoresence hidapi owns DualSense. Browser Gamepad cannot see that
      // exclusive open — never let it clobber a fresh Deck snapshot.
      if (st.deckLive && Date.now() - st.deckAt < 4000) {
        const now = performance.now();
        pushHid({ t: now, r2: st.r2, left: st.left, held: st.padHeld });
        const vis = hidAt(videoClock(now, st.syncLagMs));
        st.setFramePad({ r2: vis.r2, left: vis.left, lagMs: st.syncLagMs });
        return;
      }
      const pad = readPad();
      if (pad.connected !== st.padConnected || pad.name !== st.padName || pad.held.join() !== st.padHeld.join()) {
        st.setPad({ connected: pad.connected, name: pad.name, held: pad.held });
      }
      if (pad.connected && st.drill === null) {
        st.setR2(pad.r2);
        st.setLeft(pad.left);
      }
      const now = performance.now();
      pushHid({ t: now, r2: pad.connected ? pad.r2 : st.r2, left: pad.connected ? pad.left : st.left, held: pad.held });
      const vis = hidAt(videoClock(now, st.syncLagMs));
      st.setFramePad({ r2: vis.r2, left: vis.left, lagMs: st.syncLagMs });
    };

    const boot = async () => {
      if ((await probeDeck()).up || (await cameraGranted())) {
        void useTheater.getState().ensureCapture();
      }
    };
    void boot();
    void useTheater.getState().probeQuicksilver();

    const stopMonitor = startDeckMonitor(
      (ing) => {
        useTheater.getState().ingestDeck(ing);
      },
      (plane) => useTheater.getState().ingestAgentPlane(plane),
      (m) => useTheater.getState().ingestMoment(m),
    );

    const frame = (t: number) => {
      raf = requestAnimationFrame(frame);
      ingestPad();
      keepVideoPlaying();
      if (t - last < 33) return;
      last = t;
      const r2 = useTheater.getState().r2;
      useTheater.getState().tick(prevR2);
      prevR2 = r2;
      if (captureNeedsRebind() && t - rebindAt > 1200) {
        rebindAt = t;
        if (getFeedKind() === "deck") useTheater.getState().thawDeck();
        else void useTheater.getState().ensureCapture();
      }
    };
    raf = requestAnimationFrame(frame);

    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLInputElement) return;
      const st = useTheater.getState();
      void st.ensureCapture();
      if (e.code === "Space") {
        e.preventDefault();
        if (st.drill === null && !st.padConnected) st.setR2(e.type === "keydown" ? 1 : 0);
      }
      if (e.type !== "keydown") return;
      if (e.key === "m" || e.key === "M") {
        st.setHdmi(st.hdmi === "menu" ? "live" : "menu");
      }
      if (e.key === "p" || e.key === "P") st.setPllLock(!st.pllLock);
      if (e.key === "s" || e.key === "S") {
        if (!e.metaKey && !e.ctrlKey) st.setHdmi(st.hdmi === "stale" ? "live" : "stale");
      }
      if (e.key === "l" || e.key === "L") {
        st.setView(st.view === "lens" ? "deck" : "lens");
      }
    };
    const onPad = () => {
      ingestPad();
      void useTheater.getState().ensureCapture();
    };
    const onPointer = () => {
      void useTheater.getState().ensureCapture();
    };
    const onDevices = () => {
      void useTheater.getState().ensureCapture();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("keyup", onKey);
    window.addEventListener("pointerdown", onPointer);
    window.addEventListener("gamepadconnected", onPad);
    window.addEventListener("gamepaddisconnected", onPad);
    navigator.mediaDevices?.addEventListener?.("devicechange", onDevices);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("keyup", onKey);
      window.removeEventListener("pointerdown", onPointer);
      window.removeEventListener("gamepadconnected", onPad);
      window.removeEventListener("gamepaddisconnected", onPad);
      navigator.mediaDevices?.removeEventListener?.("devicechange", onDevices);
      stopMonitor();
    };
  }, []);
}