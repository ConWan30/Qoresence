import { ghostStickQuiet } from "@/lib/coupling/board";
import { useTheater } from "@/lib/coupling/store";

/** DualSense locus on LIVE. Draws only during play on a real join. */
export function GhostStickOverlay() {
  const g = useTheater((s) => s.ghostStick);
  const witnessKind = useTheater((s) => s.frameWitnessKind);
  const witnessSource = useTheater((s) => s.frameWitnessSource);
  if (ghostStickQuiet({ witnessKind, witnessSource, joinId: g.joinId })) return null;
  if (!g.enabled || !g.paint) return null;
  const cx = 40 + g.lx * 16;
  const cy = 40 + g.ly * 16;
  const r2h = 4 + g.r2 * 10;
  const l2h = 4 + g.l2 * 10;
  return (
    <svg
      data-ghost-stick="on"
      data-ghost-reason={g.reason}
      viewBox="0 0 80 80"
      className="pointer-events-none absolute bottom-3 left-3 h-16 w-16 text-live"
      aria-hidden
    >
      <circle cx="40" cy="40" r="22" fill="none" stroke="currentColor" strokeWidth="1.2" opacity="0.35" />
      <rect x="12" y={36 - l2h} width="6" height={l2h} rx="1.5" fill="currentColor" opacity={g.l2 > 0.08 ? 0.85 : 0.2} />
      <rect x="62" y={36 - r2h} width="6" height={r2h} rx="1.5" fill="currentColor" opacity={g.r2 > 0.08 ? 0.85 : 0.2} />
      <circle cx={cx} cy={cy} r="6" fill="currentColor" opacity="0.9" />
    </svg>
  );
}
