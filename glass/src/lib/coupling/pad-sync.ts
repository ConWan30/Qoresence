/** DualSense vs HDMI clock — HID registration and video-lock, no invented pose. */

export type PadHid = "live" | "wait";
export type PadLock = "lock" | "open" | "drift";

export type PadSyncInput = {
  connected: boolean;
  reports: number;
  prevReports: number;
  pllLock: boolean;
  binds: number;
  lagMs: number;
  jitterMs: number;
  videoAgeS: number;
  hidSeq: number;
  videoSeq: number;
  energy: number;
  held: string[];
};

export type PadSyncScore = {
  hid: PadHid;
  lock: PadLock;
  registering: boolean;
  why: string;
};

export function scorePadSync(ing: PadSyncInput): PadSyncScore {
  if (!ing.connected) {
    return { hid: "wait", lock: "open", registering: false, why: "PAD WAIT — DualSense not on this box" };
  }
  const hidClimb = ing.reports > ing.prevReports;
  const hot = ing.energy > 0.08 || ing.held.length > 0;
  const registering = hidClimb || hot || ing.reports > 0;
  const videoFresh = Number.isFinite(ing.videoAgeS) && ing.videoAgeS >= 0 && ing.videoAgeS < 1;
  const seqs = ing.hidSeq > 0 && ing.videoSeq > 0;
  const seqLock = seqs && Math.abs(ing.hidSeq - ing.videoSeq) <= 4;
  if (ing.pllLock || (videoFresh && seqLock)) {
    return {
      hid: "live",
      lock: "lock",
      registering,
      why: ing.pllLock
        ? `PLL lock · ${Math.round(ing.lagMs)}ms`
        : `HID on video clock · ${Math.round(ing.lagMs)}ms`,
    };
  }
  if (!videoFresh || (seqs && Math.abs(ing.hidSeq - ing.videoSeq) > 12)) {
    return { hid: "live", lock: "drift", registering, why: "HID live · picture clock drifted" };
  }
  return { hid: "live", lock: "open", registering, why: "HID live · PLL open — press in-game to bind" };
}
