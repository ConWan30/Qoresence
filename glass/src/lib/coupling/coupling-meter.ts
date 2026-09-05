/** Pad↔picture co-occurrence bins. Observation only. */

export type CouplingBin = { ms: number; n: number };

export const COUPLING_EDGES = [0, 16, 33, 50, 66, 83, 100, 120] as const;

export function couplingMeter(args: {
  lagMs: number | null;
  pllLock: boolean;
  sameSeq: boolean;
}): { bins: CouplingBin[]; label: "unbound" | "co-occurrence"; skewMs: number | null } {
  const bins: CouplingBin[] = COUPLING_EDGES.map((ms) => ({ ms, n: 0 }));
  if (args.lagMs == null || !args.pllLock) {
    return { bins, label: "unbound", skewMs: args.lagMs };
  }
  const lag = Number(args.lagMs) || 0;
  let idx = COUPLING_EDGES.findIndex((ms) => lag <= ms);
  if (idx < 0) idx = COUPLING_EDGES.length - 1;
  bins[idx] = { ms: COUPLING_EDGES[idx], n: 1 };
  const label = args.sameSeq && args.pllLock ? "co-occurrence" : "unbound";
  return { bins, label, skewMs: lag };
}
