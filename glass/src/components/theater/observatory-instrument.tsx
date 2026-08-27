/** Observatory intel-column — play-pad bind instrument (Layer B).
 *
 * Sheet chip: active sheet (Huddle, Run, Pass, Coverage, …) or UNLABELED
 * Last named press: DualSense button · EA verb (e.g. "Cross · Snap Ball")
 * Honesty: conflict display when picture sheet != pad sheet
 *
 * Instrument look: coupling gauge, not sports overlay. Phosphor dark mono.
 * Empty Story / empty pad is not a broken HUD — unlabeled is honest.
 */

import { useTheater } from "@/lib/coupling/store";
import { cn } from "@/lib/utils";

const SHEET_LABELS: Record<string, string> = {
  preplay_offense: "Huddle",
  preplay_defense: "Huddle Defense",
  running: "Run",
  passing: "Pass",
  ball_in_air: "Ball in Air",
  defensive_coverage: "Coverage",
  defensive_coverage_mechanics: "Coverage",
  defense_pursuit: "Pursuit",
  defense_engaged: "Engaged",
  blocking: "Blocking",
  blocking_mechanics: "Blocking",
  player_locked_receiver: "Locked Receiver",
};

export function ObservatoryInstrument() {
  const hidButton = useTheater((s) => s.observationHidButton);
  const verb = useTheater((s) => s.observationVerb);
  const mode = useTheater((s) => s.observationMode);
  const visualPhase = useTheater((s) => s.observationVisualPhase);
  const conflict = useTheater((s) => s.observationConflict);
  const stageMode = useTheater((s) => s.stageMode);
  const livePaint = useTheater((s) => s.livePaint);
  const planeDim = useTheater((s) => s.planeDim);

  // Observatory off during replay or when picture is dark
  if (stageMode === "replay" || !livePaint || planeDim) return null;

  // Sheet chip: human label for active sheet or unlabeled mark
  const sheetLabel = mode ? SHEET_LABELS[mode] || mode.toUpperCase() : null;
  const sheetDisplay = sheetLabel || "□ UNLABELED";
  const unlabeled = !sheetLabel;

  // Last named press: DualSense button · EA verb (fade if no input)
  // hidButton from hid_by_seq observation (honest: may be unlabeled)
  const hasPress = Boolean(hidButton);
  const pressDisplay = hasPress
    ? verb
      ? `${hidButton} · ${verb}`
      : `${hidButton} · □`
    : null;

  // Honesty: conflict when picture sheet != pad sheet
  const hasConflict = Boolean(conflict);
  const conflictDisplay = hasConflict
    ? `${conflict!.pictureSheet} (picture) ≠ ${conflict!.padSheet} (pad)`
    : null;

  return (
    <div className="pointer-events-none absolute right-3 top-16 z-20 flex flex-col gap-2">
      {/* Sheet chip */}
      <div
        className={cn(
          "rounded border px-3 py-1.5 font-mono text-[11px] tracking-wider uppercase backdrop-blur-sm",
          unlabeled
            ? "border-muted-foreground/40 bg-bg/60 text-muted-foreground"
            : "border-sync/60 bg-bg/75 text-sync",
        )}
      >
        {sheetDisplay}
      </div>

      {/* Last named press (fade out quickly when no input) */}
      {pressDisplay && (
        <div className="rounded border border-photon/50 bg-bg/75 px-3 py-1.5 font-mono text-[10px] tracking-wide text-photon backdrop-blur-sm">
          {pressDisplay}
        </div>
      )}

      {/* Honesty: conflict display */}
      {hasConflict && (
        <div className="rounded border border-veto/60 bg-bg/80 px-3 py-1.5 font-mono text-[9px] leading-tight tracking-wide text-veto backdrop-blur-sm">
          <div className="font-bold uppercase">SHEET MISMATCH</div>
          <div className="mt-0.5 opacity-90">{conflictDisplay}</div>
          {conflict!.reason && (
            <div className="mt-0.5 text-[8px] opacity-75">{conflict!.reason}</div>
          )}
        </div>
      )}
    </div>
  );
}
