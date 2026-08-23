/** Retina Stem — consume bus stem_program. Local director is fallback. */

export type StemMode = "watch" | "prime" | "armed" | "hold" | "encode";

export type StemProgram = {
  mode: StemMode;
  why: string;
  armHot: boolean;
};

export function parseStemProgram(raw: unknown): StemProgram | null {
  const rec = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : null;
  if (!rec) return null;
  const payload =
    rec.type === "stem_program" && rec.payload && typeof rec.payload === "object"
      ? (rec.payload as Record<string, unknown>)
      : rec.mode
        ? rec
        : null;
  if (!payload) return null;
  const mode = String(payload.mode || "");
  if (!["watch", "prime", "armed", "hold", "encode"].includes(mode)) return null;
  return {
    mode: mode as StemMode,
    why: String(payload.why || ""),
    armHot: Boolean(payload.arm_hot ?? payload.armHot),
  };
}
