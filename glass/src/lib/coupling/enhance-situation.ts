import type { ClutchSnap } from "./clutch.ts";
import type { ConfirmTicket, PhraseResult } from "./engine.ts";

export type EnhanceHdmiMode = "live" | "menu" | "stale";

/** Title-presence only — never invent Madden/CFB when gameTitle is empty. */
export function buildEnhanceSituation(s: {
  gameTitle: string;
  hdmi: EnhanceHdmiMode;
  phrase: PhraseResult;
  coupling: number;
  clutch: ClutchSnap;
  confirm: ConfirmTicket | null;
}): Record<string, unknown> {
  const situation: Record<string, unknown> = {
    game_title: s.gameTitle,
    game_state: s.hdmi === "menu" ? "menu" : "gameplay",
    game_category: "football",
    phrase: s.phrase.phrase,
    coupling: s.coupling,
    climax_score: s.clutch.score,
    clutch_kind: s.clutch.kind,
    down: null,
    clock: "",
  };
  if (s.confirm) {
    situation.home_score = s.confirm.homeScore;
    situation.away_score = s.confirm.awayScore;
    situation.score_vlm_locked = true;
  }
  return situation;
}
