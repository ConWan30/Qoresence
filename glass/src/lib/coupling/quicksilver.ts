/** Browser glass: Quicksilver stays on the Python spine (ClutchBot / A2A).
 *  Never ships API keys to the page. */
import type { EnhanceIn, EnhanceOut } from "./quicksilver.server";
import { getDeckOrigin } from "./qoresence-deck";

export type { EnhanceIn, EnhanceOut };

export async function qsProbe(): Promise<{ live: boolean; model: string; base: string }> {
  try {
    const origin = getDeckOrigin();
    const res = await fetch(`${origin}/health`, { cache: "no-store" });
    if (!res.ok) return { live: false, model: "", base: origin };
    const j = (await res.json()) as Record<string, unknown>;
    const state = (j.state && typeof j.state === "object" ? j.state : j) as Record<string, unknown>;
    const a2a = Boolean(state.a2a || j.a2a || state.clutchbot);
    return { live: a2a, model: a2a ? "via Deck" : "", base: origin };
  } catch {
    return { live: false, model: "", base: "" };
  }
}

export async function qsEnhance(args: { data: EnhanceIn }): Promise<EnhanceOut> {
  void args;
  return { ok: false, text: "", model: "", error: "qs via Deck ClutchBot" };
}
