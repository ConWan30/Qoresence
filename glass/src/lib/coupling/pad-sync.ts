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

/** Picture lag in ms from lag_center_ms / last_bind_ms / video.age_s. Null if unmeasured. Never 0. */
export function pictureLagMs(videoAgeS: number, bindMs = 0, pllMs = 0): number | null {
  if (pllMs >= 16 && pllMs <= 220) return Math.round(pllMs);
  if (bindMs >= 16 && bindMs <= 220) return Math.round(bindMs);
  const age = Number(videoAgeS) * 1000;
  if (Number.isFinite(age) && age >= 8 && age <= 220) return Math.round(age);
  return null;
}

/** SYNC chip: measured lag or UNBOUND. Never decorate 0. */
export function syncChipText(lagMs: number | null | undefined): string {
  const n = Number(lagMs);
  if (!Number.isFinite(n) || n <= 0) return "UNBOUND";
  return `${Math.round(n)}ms`;
}

export function scorePadSync(ing: PadSyncInput): PadSyncScore {
  if (!ing.connected) {
    // Default live topology: DualSense stays on the PS5. Empty laptop HID is success.
    return { hid: "wait", lock: "open", registering: false, why: "pad_not_on_this_host" };
  }
  const hidClimb = ing.reports > ing.prevReports;
  const hot = ing.energy > 0.08 || ing.held.length > 0;
  const registering = hidClimb || hot || ing.reports > 0;
  const videoFresh = Number.isFinite(ing.videoAgeS) && ing.videoAgeS >= 0 && ing.videoAgeS < 1;
  const seqs = ing.hidSeq > 0 && ing.videoSeq > 0;
  const seqLock = seqs && Math.abs(ing.hidSeq - ing.videoSeq) <= 4;
  const lag = pictureLagMs(ing.videoAgeS, 0, ing.lagMs);
  const lagBit = lag != null ? ` · ${lag}ms` : "";
  if (ing.pllLock || (videoFresh && seqLock)) {
    return {
      hid: "live",
      lock: "lock",
      registering,
      why: ing.pllLock ? `PLL lock${lagBit}` : `HID on video clock${lagBit}`,
    };
  }
  if (!videoFresh || (seqs && Math.abs(ing.hidSeq - ing.videoSeq) > 12)) {
    return { hid: "live", lock: "drift", registering, why: "HID live · picture clock drifted" };
  }
  return { hid: "live", lock: "open", registering, why: "HID live · PLL open" };
}
