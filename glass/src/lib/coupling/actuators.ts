/** Clock-licensed actuator receipts — Aperture / Bind / License / Arm. */

export const ACTUATOR_NAMES = ["aperture", "bind", "license", "arm"] as const;
export type ActuatorName = (typeof ACTUATOR_NAMES)[number];

export type ActuatorReceipt = {
  actuator: ActuatorName | string;
  path: "fast" | "confirm" | string;
  kind: string;
  text: string;
  ticketId: string;
  clockNs: number;
  frameSeq: number | null;
};

function rec(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v) ? (v as Record<string, unknown>) : {};
}

function str(v: unknown): string {
  return v == null ? "" : String(v);
}

function num(v: unknown, fallback = 0): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

export function parseActuatorReceipts(raw: unknown): ActuatorReceipt[] {
  const root = rec(raw);
  const list = Array.isArray(raw)
    ? raw
    : Array.isArray(root.receipts)
      ? root.receipts
      : [];
  const out: ActuatorReceipt[] = [];
  for (const row of list) {
    const r = rec(row);
    const name = str(r.actuator || r.name).toLowerCase();
    if (!name) continue;
    out.push({
      actuator: name,
      path: str(r.path) || "fast",
      kind: str(r.kind),
      text: str(r.text || r.kind),
      ticketId: str(r.ticket_id || r.ticketId),
      clockNs: num(r.clock_ns ?? r.clockNs),
      frameSeq: r.frame_seq == null && r.frameSeq == null ? null : num(r.frame_seq ?? r.frameSeq),
    });
  }
  return out;
}

export function actuatorChips(rows: ActuatorReceipt[]): ActuatorReceipt[] {
  const by = new Map<string, ActuatorReceipt>();
  for (const r of rows) by.set(r.actuator, r);
  return ACTUATOR_NAMES.map((n) => by.get(n)).filter((r): r is ActuatorReceipt => Boolean(r));
}
