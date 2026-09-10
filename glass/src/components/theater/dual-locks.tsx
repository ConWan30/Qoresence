/** Dual plane glyphs. LIVE Theater may light OBS only. */

export type LockPlane = {
  glyph: string;
  state: "DARK" | "OBS" | "TRUTH";
  color: string;
  plane: "observation" | "truth";
};

export function DualLocks(props: {
  obs?: LockPlane;
  truth?: LockPlane;
  live?: boolean;
}) {
  const obs = props.obs ?? { glyph: "\u25a1", state: "DARK", color: "#0b0f0d", plane: "observation" };
  const truth = props.live
    ? { glyph: "\u25a1", state: "DARK" as const, color: "#0b0f0d", plane: "truth" as const }
    : props.truth ?? { glyph: "\u25a1", state: "DARK", color: "#0b0f0d", plane: "truth" };
  return (
    <div className="dual-locks" data-live={props.live ? "1" : "0"}>
      <span className="dual-lock obs" data-state={obs.state} style={{ color: obs.color }}>
        {obs.glyph}
      </span>
      <span className="dual-lock truth" data-state={truth.state} style={{ color: truth.color }}>
        {truth.glyph}
      </span>
    </div>
  );
}
