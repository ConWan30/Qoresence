/** Video-clock HID retimer.
 *  USB arrives early. HDMI is late. Glass paints the press on the picture clock
 *  so DualSense ghosts land on the frame they belong to — not on packet time.
 */

export type HidSample = {
  t: number;
  r2: number;
  left: number;
  held: string[];
};

const CAP = 120;
const ring: HidSample[] = [];
const EMPTY: HidSample = { t: 0, r2: 0, left: 0, held: [] };

export function pushHid(s: HidSample): void {
  ring.push(s);
  if (ring.length > CAP) ring.splice(0, ring.length - CAP);
}

export function hidAt(t: number): HidSample {
  if (!ring.length) return EMPTY;
  let best = ring[0];
  for (let i = 1; i < ring.length; i++) {
    if (ring[i].t <= t) best = ring[i];
    else break;
  }
  return best;
}

/** Prefer IVC PLL center, then luma bind, then FrameHub age. Clamp 16–220 ms. */
export function measureLag(videoAgeS: number, bindMs: number, pllMs = 0): number {
  if (pllMs >= 16 && pllMs <= 220) return Math.round(pllMs);
  if (bindMs >= 16 && bindMs <= 220) return Math.round(bindMs);
  const age = videoAgeS * 1000;
  if (age >= 8 && age <= 220) return Math.round(age);
  return 80;
}

export function videoClock(now: number, lagMs: number): number {
  return now - Math.max(0, lagMs);
}

export function resetHid(): void {
  ring.length = 0;
}
