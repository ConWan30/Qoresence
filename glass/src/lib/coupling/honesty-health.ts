/** Sight Honesty — TicketGlass + SyncGlass votes from /health.
 *
 * Fail-closed. Never licenses score digits. Never invents score pairs.
 * Observation only: parse JSON, no capture / JPEG / WS decode.
 */

export const HONESTY_CONF_ACT = 0.7;
export const HONESTY_CONF_SOFT = 0.4;
export const PAINT_BLOCK_ACT = 0.7;

export type HonestyConf = "solid" | "dim" | "ghost";
export type HonestyState = "live" | "dark";
export type HonestyGlyphId = "lock" | "tension" | "cut" | "bind" | "lag" | "haptic";

export const HONESTY_GLYPH_ORDER: readonly HonestyGlyphId[] = [
  "lock",
  "tension",
  "cut",
  "bind",
  "lag",
  "haptic",
] as const;

export type HonestyGlyph = {
  id: HonestyGlyphId;
  value: string;
  conf: HonestyConf;
  title: string;
};

export type HonestyHealth = {
  state: HonestyState;
  enabled: boolean;
  licensesDigits: false;
  paintBlocked: boolean;
  lockBlocked: boolean;
  glassRoute: string;
  tension: number;
  cut: string;
  lagClass: string;
  severity: number;
  glyphs: HonestyGlyph[];
  ticketEnabled: boolean;
  syncEnabled: boolean;
};

const DARK_VALUES: Record<HonestyGlyphId, string> = {
  lock: "unknown",
  tension: "0",
  cut: "off",
  bind: "unknown",
  lag: "unknown",
  haptic: "unknown",
};

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function num(v: unknown): number | null {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function str(v: unknown): string {
  return v == null ? "" : String(v).trim();
}

/** Never let a Jev/health field paint a score pair into a glyph. */
function enumText(v: unknown, fallback: string): string {
  const s = str(v);
  if (!s) return fallback;
  if (/\b\d{1,2}\s*[-–—]\s*\d{1,2}\b/.test(s)) return fallback;
  return s.slice(0, 32);
}

export function confBand(n: number | null | undefined): HonestyConf {
  if (n == null || !Number.isFinite(n)) return "ghost";
  if (n >= HONESTY_CONF_ACT) return "solid";
  if (n >= HONESTY_CONF_SOFT) return "dim";
  return "ghost";
}

function bandName(raw: unknown): HonestyConf | null {
  const s = str(raw).toLowerCase();
  if (s === "act" || s === "solid") return "solid";
  if (s === "soft" || s === "dim" || s === "watch") return "dim";
  if (s === "observe" || s === "ghost" || s === "dark" || s === "unknown") return "ghost";
  return null;
}

function pickConf(explicit: unknown, noul: number | null, fallback: HonestyConf): HonestyConf {
  const named = bandName(explicit);
  if (named) return named;
  const n = num(explicit);
  if (n != null) return confBand(n);
  if (noul != null) return confBand(noul);
  return fallback;
}

function darkGlyph(id: HonestyGlyphId): HonestyGlyph {
  const value = DARK_VALUES[id];
  return { id, value, conf: "ghost", title: `${id}=${value}` };
}

export const EMPTY_HONESTY: HonestyHealth = {
  state: "dark",
  enabled: false,
  licensesDigits: false,
  paintBlocked: false,
  lockBlocked: false,
  glassRoute: "dark",
  tension: 0,
  cut: "off",
  lagClass: "unknown",
  severity: 0,
  glyphs: HONESTY_GLYPH_ORDER.map(darkGlyph),
  ticketEnabled: false,
  syncEnabled: false,
};

/** TicketGlass veto — lock=blocked OR board_paint_block ≥ 0.7 OR paint_block=block. */
export function digitsPaintBlocked(...bags: Record<string, unknown>[]): boolean {
  const walk = (o: Record<string, unknown>): boolean => {
    if (!o || !Object.keys(o).length) return false;
    const glyphs = rec(o.glyphs);
    const lock = str(glyphs.lock ?? o.lock).toLowerCase();
    if (lock === "blocked") return true;
    const pb = str(o.paint_block ?? o.paintBlock).toLowerCase();
    if (pb === "block") return true;
    const n = num(o.board_paint_block ?? o.boardPaintBlock);
    if (n != null && n >= PAINT_BLOCK_ACT) return true;
    return false;
  };
  for (const bag of bags) {
    if (!bag || typeof bag !== "object") continue;
    if (walk(bag)) return true;
    if (walk(rec(bag.ticket_glass))) return true;
    if (walk(rec(rec(bag.health).ticket_glass))) return true;
  }
  return false;
}

export function tensionPlinth(tension: number, cut?: string): "off" | "near" | "hot" {
  const t = Number.isFinite(tension) ? Math.max(0, Math.min(3, Math.round(tension))) : 0;
  if (t >= 3) return "hot";
  if (t >= 1) return "near";
  if (String(cut || "").toLowerCase() === "on") return "hot";
  return "off";
}

const SCORE_PAIR = /\b\d{1,2}\s*[-–—]\s*\d{1,2}\b/g;

/** Digit-silent: replace score pairs in chrome text. Madden abbrev gate is unchanged. */
export function silenceScorePair(text: string, blocked: boolean): string {
  if (!blocked) return text;
  return String(text || "").replace(SCORE_PAIR, "□–□");
}

function clampTension(v: unknown): number {
  const n = num(v);
  if (n == null) return 0;
  return Math.max(0, Math.min(3, Math.round(n)));
}

export function parseHonestyHealth(raw: unknown): HonestyHealth {
  if (raw == null || typeof raw !== "object" || Array.isArray(raw)) {
    return EMPTY_HONESTY;
  }
  const root = rec(raw);
  const ticket = rec(root.ticket_glass ?? root.ticketGlass);
  const sync = rec(root.sync_glass ?? root.syncGlass);
  const ticketEnabled = Boolean(ticket.enabled);
  const syncEnabled = Boolean(sync.enabled);
  const enabled = ticketEnabled || syncEnabled;
  if (!enabled) {
    return {
      ...EMPTY_HONESTY,
      ticketEnabled,
      syncEnabled,
    };
  }

  const tGlyphs = rec(ticket.glyphs);
  const sGlyphs = rec(sync.glyphs);
  const tBands = rec(ticket.bands);
  const sBands = rec(sync.bands);

  const lock = enumText(tGlyphs.lock, "unknown").toLowerCase() || "unknown";
  const tension = clampTension(tGlyphs.tension ?? ticket.lens_tension);
  const cut = enumText(tGlyphs.cut, "off").toLowerCase() || "off";
  const bind = enumText(sGlyphs.bind, "unknown").toLowerCase() || "unknown";
  const lag = enumText(sGlyphs.lag ?? sync.lag_class, "unknown").toLowerCase() || "unknown";
  const haptic = enumText(sGlyphs.haptic, "unknown").toLowerCase() || "unknown";

  const blockNoul = num(ticket.board_paint_block ?? ticket.boardPaintBlock);
  const bindNoul = num(sync.bind_healthy ?? sync.bindHealthy);
  const hapNoul = num(sync.haptic_coupled ?? sync.hapticCoupled);

  const lockBlocked = lock === "blocked";
  const paintBlocked =
    lockBlocked ||
    str(ticket.paint_block ?? ticket.paintBlock).toLowerCase() === "block" ||
    (blockNoul != null && blockNoul >= PAINT_BLOCK_ACT);

  const lockConf = pickConf(
    tBands.lock ?? ticket.lock_confidence ?? ticket.lockConfidence,
    lockBlocked ? blockNoul : null,
    lock === "unknown" ? "ghost" : lock === "open" ? "dim" : "solid",
  );
  const tensionConf = pickConf(
    tBands.lens_tension ?? ticket.tension_confidence ?? ticket.tensionConfidence,
    null,
    tension >= 3 ? "solid" : tension >= 1 ? "dim" : "ghost",
  );
  const cutConf = pickConf(
    tBands.clip_now ?? ticket.clip_confidence ?? ticket.clipConfidence,
    null,
    cut === "on" ? "solid" : "ghost",
  );
  const bindConf = pickConf(sBands.bind_healthy ?? sBands.bind, bindNoul, bind === "ok" ? "solid" : bind === "soft" ? "dim" : "ghost");
  const lagConf = pickConf(
    sBands.lag_class ?? sync.lag_confidence ?? sync.lagConfidence,
    null,
    lag === "unknown" ? "ghost" : lag === "ok" ? "solid" : "dim",
  );
  const hapConf = pickConf(sBands.haptic_coupled ?? sBands.haptic, hapNoul, haptic === "on" ? "solid" : "ghost");

  const values: Record<HonestyGlyphId, string> = {
    lock,
    tension: String(tension),
    cut: cut === "on" ? "on" : "off",
    bind,
    lag,
    haptic,
  };
  const confs: Record<HonestyGlyphId, HonestyConf> = {
    lock: lockConf,
    tension: tensionConf,
    cut: cutConf,
    bind: bindConf,
    lag: lagConf,
    haptic: hapConf,
  };

  const glyphs: HonestyGlyph[] = HONESTY_GLYPH_ORDER.map((id) => ({
    id,
    value: values[id],
    conf: confs[id],
    title: `${id}=${values[id]}`,
  }));

  return {
    state: "live",
    enabled: true,
    licensesDigits: false,
    paintBlocked,
    lockBlocked,
    glassRoute: enumText(ticket.glass_route ?? ticket.glassRoute, "dark"),
    tension,
    cut: values.cut,
    lagClass: lag,
    severity: clampTension(sync.severity),
    glyphs,
    ticketEnabled,
    syncEnabled,
  };
}
