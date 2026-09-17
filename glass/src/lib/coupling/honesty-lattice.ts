/** Honesty Lattice — operator composite of Noul dimensions.
 *
 * Inverse of ScoreboardOCR last-good freeze. Weights live in this file.
 * Never licenses score digits. Presence tokens are join density, not clutch.
 */

export const HONESTY_WEIGHTS = {
  boardHonesty: 0.55,
  presenceDensity: 0.25,
  abstainCredit: 0.2,
} as const;

export type HonestyBand = "ok" | "amber" | "void" | "ident";
export type PresenceToken = "idle" | "join" | "dense";

export type HonestyLattice = {
  honestyBand: HonestyBand;
  honestyComposite: number;
  presenceToken: PresenceToken;
  identNow: boolean;
  licensesDigits: false;
};

export const EMPTY_LATTICE: HonestyLattice = {
  honestyBand: "void",
  honestyComposite: 0,
  presenceToken: "idle",
  identNow: false,
  licensesDigits: false,
};

function num(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function str(v: unknown): string {
  return v == null ? "" : String(v);
}

export function composeHonestyLattice(args: {
  boardHonesty?: number | null;
  presenceDensity?: number | null;
  lastGoodTemptation?: number | null;
  groundedNoul?: number | null;
  coupling?: number;
  redZone?: boolean;
  lateClose?: boolean;
}): HonestyLattice {
  const honesty = args.boardHonesty == null ? 0 : Number(args.boardHonesty) || 0;
  const dens = args.presenceDensity == null ? 0 : Number(args.presenceDensity) || 0;
  const tempt = args.lastGoodTemptation;
  let abstainCredit = 0;
  let identNow = false;
  if (tempt != null) {
    identNow = tempt >= 0.7;
    abstainCredit = identNow ? 2 : tempt >= 0.4 ? 1 : 0;
  }
  const w = HONESTY_WEIGHTS;
  const composite = w.boardHonesty * honesty + w.presenceDensity * dens + w.abstainCredit * abstainCredit;
  const grounded = args.groundedNoul;
  let band: HonestyBand;
  if (identNow || (grounded != null && grounded <= 0.3)) band = "ident";
  else if (composite >= 1.4) band = "ok";
  else if (composite >= 0.7) band = "amber";
  else band = "void";

  const coupling = Number(args.coupling) || 0;
  let token: PresenceToken = "idle";
  if (dens >= 1.5 && coupling >= 0.5 && (args.redZone || args.lateClose)) token = "dense";
  else if (dens >= 0.7 || coupling >= 0.35) token = "join";

  return {
    honestyBand: band,
    honestyComposite: Math.round(composite * 1000) / 1000,
    presenceToken: token,
    identNow,
    licensesDigits: false,
  };
}

export const GAMER_PRESENCE: Record<PresenceToken, string> = {
  idle: "Pad and picture quiet",
  join: "Pad and picture together",
  dense: "Pad and picture dense — local clip possible",
};

export const GAMER_HONESTY: Record<HonestyBand, string> = {
  ok: "",
  amber: "Board uncertain — holding blank",
  void: "Board not licensed yet",
  ident: "Would rather go blank than keep a stale score",
};

export function gamerHonestyCopy(args: {
  enabled?: boolean;
  honestyBand?: HonestyBand;
  presenceToken?: PresenceToken;
  identNow?: boolean;
}): { line: string; presence: string; ident: boolean } {
  if (!args.enabled) return { line: "", presence: "", ident: false };
  const band: HonestyBand = args.identNow ? "ident" : args.honestyBand || "void";
  const token: PresenceToken = args.presenceToken || "idle";
  return {
    line: GAMER_HONESTY[band] ?? GAMER_HONESTY.void,
    presence: GAMER_PRESENCE[token] || GAMER_PRESENCE.idle,
    ident: band === "ident",
  };
}

export function parseNoulHealth(raw: unknown): HonestyLattice & {
  enabled: boolean;
  hudKind: string;
  boardSpeech: string;
  gamerLine: string;
  gamerPresence: string;
} {
  const root = raw && typeof raw === "object" && !Array.isArray(raw) ? (raw as Record<string, unknown>) : {};
  const noul = root.noul && typeof root.noul === "object" ? (root.noul as Record<string, unknown>) : root;
  const enabled = Boolean(noul.enabled);
  if (!enabled) {
    return { ...EMPTY_LATTICE, enabled: false, hudKind: "", boardSpeech: "", gamerLine: "", gamerPresence: "" };
  }
  const composed = composeHonestyLattice({
    boardHonesty: num(noul.board_honesty ?? noul.boardHonesty),
    presenceDensity: num(noul.presence_density ?? noul.presenceDensity),
    lastGoodTemptation: num(noul.last_good_temptation ?? noul.lastGoodTemptation),
    groundedNoul: num(noul.grounded_noul ?? noul.groundedNoul),
  });
  const band = str(noul.honesty_band || noul.honestyBand) as HonestyBand;
  const token = str(noul.presence_token || noul.presenceToken) as PresenceToken;
  const identNow = Boolean(noul.ident_now ?? noul.identNow ?? composed.identNow);
  const honestyBand = band === "ok" || band === "amber" || band === "void" || band === "ident" ? band : composed.honestyBand;
  const presenceToken = token === "idle" || token === "join" || token === "dense" ? token : composed.presenceToken;
  const gamer = noul.gamer && typeof noul.gamer === "object" ? (noul.gamer as Record<string, unknown>) : null;
  const copy = gamerHonestyCopy({
    enabled: true,
    honestyBand,
    presenceToken,
    identNow,
  });
  return {
    ...composed,
    honestyBand,
    presenceToken,
    identNow,
    honestyComposite: num(noul.honesty_composite ?? noul.honestyComposite) ?? composed.honestyComposite,
    enabled: true,
    hudKind: str(noul.hud_kind || noul.hudKind),
    boardSpeech: str(noul.board_speech || noul.boardSpeech),
    licensesDigits: false,
    gamerLine: str(gamer?.line) || copy.line,
    gamerPresence: str(gamer?.presence) || copy.presence,
  };
}
