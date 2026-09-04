#!/usr/bin/env node
/**
 * LAB / FIXTURE harness — X LIVE 0-1 crop_hash move silence.
 * NON-CLAIM. Plain JS for CI Node 20. No TypeScript sources.
 * Does not start --play. Prints no secrets.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const MAX_AGE_NS = 8_000_000_000;
const here = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(join(here, "FIXTURE.json"), "utf8"));

function rec(v) {
  return v && typeof v === "object" && !Array.isArray(v) ? v : {};
}
function num(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}
function intOrNull(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? Math.trunc(n) : null;
}
function firstNum(o, keys) {
  for (const k of keys) {
    if (o[k] == null || o[k] === "") continue;
    const n = intOrNull(o[k]);
    if (n != null) return n;
  }
  return null;
}
function firstStr(o, keys) {
  for (const k of keys) {
    const v = o[k];
    if (typeof v !== "string") continue;
    const s = v.trim();
    if (s && s !== "true" && s !== "false") return s;
  }
  return "";
}
function firstBool(o, keys) {
  for (const k of keys) {
    const v = o[k];
    if (v === true || v === false) return v;
    if (v === 1 || v === 0) return Boolean(v);
    if (typeof v === "string") {
      const s = v.trim().toLowerCase();
      if (s === "true" || s === "yes" || s === "on") return true;
      if (s === "false" || s === "no" || s === "off") return false;
    }
  }
  return null;
}
function parsePair(raw) {
  const m = String(raw ?? "").match(/\b(\d{1,2})\s*[-–—]\s*(\d{1,2})\b/);
  return m ? [Number(m[1]), Number(m[2])] : null;
}
function cropOf(o) {
  return firstStr(o, ["crop_hash", "cropHash", "frame_hash", "frameHash"]);
}
function confirmIdOf(o) {
  return firstStr(o, ["ticket_id", "ticketId", "confirm_ticket_id", "confirmTicketId"]);
}
function scorePairOf(o) {
  const h = firstNum(o, ["home_score", "score_home", "homeScore"]);
  const a = firstNum(o, ["away_score", "score_away", "awayScore"]);
  if (h != null && a != null) return [h, a];
  return parsePair(o.score ?? o.scoreline ?? o.board);
}

function ticketFresh(args) {
  const ticketCrop = String(args.ticketCropHash || "").trim();
  if (!ticketCrop) return false;
  const liveCrop = String(args.liveCropHash || "").trim();
  if (liveCrop && liveCrop !== ticketCrop) return false;
  if (args.sameSeq === false) return false;
  const tClock = Number(args.ticketClockNs) || 0;
  const lClock = Number(args.liveClockNs) || 0;
  if (tClock > 0 && lClock > 0 && lClock - tClock > (args.maxAgeNs ?? MAX_AGE_NS)) return false;
  return true;
}

function digitsLicensed(args) {
  if (!String(args.confirmTicketId || "").trim()) return false;
  if (!args.scoreVlmLocked) return false;
  return ticketFresh(args);
}

function pickBoard(...bags) {
  let candHome = null;
  let candAway = null;
  let confirmTicketId = "";
  let scoreVlmLocked = false;
  let ticketCrop = "";
  let liveCrop = "";
  let sameSeq = null;
  let ticketClockNs = 0;
  let liveClockNs = 0;

  const takeCandidate = (o, prefer) => {
    const pair = scorePairOf(o);
    if (!pair) return;
    if (prefer || candHome == null) {
      candHome = pair[0];
      candAway = pair[1];
    }
  };
  const takeTicket = (o) => {
    if (!o || !Object.keys(o).length) return;
    const tid = confirmIdOf(o);
    if (tid && !confirmTicketId) confirmTicketId = tid;
    const crop = cropOf(o);
    if (crop && !ticketCrop) ticketCrop = crop;
    const clk = num(o.clock_ns ?? o.clockNs, 0);
    if (clk && !ticketClockNs) ticketClockNs = clk;
    if (firstBool(o, ["score_vlm_locked", "scoreVlmLocked"]) === true) scoreVlmLocked = true;
    takeCandidate(o, true);
  };
  const takeLive = (o) => {
    if (!o || !Object.keys(o).length) return;
    if (firstBool(o, ["score_vlm_locked", "scoreVlmLocked"]) === true) scoreVlmLocked = true;
    const tid = firstStr(o, ["confirm_ticket_id", "confirmTicketId"]);
    if (tid && !confirmTicketId) confirmTicketId = tid;
    const crop = cropOf(o);
    if (crop) liveCrop = crop;
    if (o.same_seq != null || o.sameSeq != null) sameSeq = Boolean(o.same_seq ?? o.sameSeq);
    const clk = num(o.clock_ns ?? o.clockNs ?? o.updated_ns ?? o.updatedNs, 0);
    if (clk) liveClockNs = clk;
    takeCandidate(o, false);
  };

  for (const bag of bags) {
    const confirm = rec(bag.confirm);
    takeTicket(rec(confirm.last_confirm));
    takeTicket(rec(bag.last_confirm));
    takeLive(bag);
    takeLive(rec(bag.situation));
    takeLive(rec(bag.payload));
    takeLive(rec(bag.visual_context));
    takeLive(rec(bag.scoreboard));
    takeLive(rec(bag.video));
    takeLive(rec(confirm.last_fast));
    takeLive(rec(bag.last_fast));
  }
  if (confirmTicketId && !ticketCrop && liveCrop) ticketCrop = liveCrop;
  const locked = digitsLicensed({
    confirmTicketId,
    scoreVlmLocked,
    ticketCropHash: ticketCrop,
    liveCropHash: liveCrop,
    sameSeq,
    ticketClockNs,
    liveClockNs,
  });
  return { home: locked ? candHome : null, away: locked ? candAway : null, locked };
}

function scorebugPair(home, away) {
  if (home == null || away == null) return "";
  return `${home}-${away}`;
}

function overlayScore(s, snap) {
  const lc = (snap && snap.confirm && snap.confirm.last_confirm) || s.last_confirm || {};
  const tid = String(lc.ticket_id || s.confirm_ticket_id || "").trim();
  const vlm = s.score_vlm_locked === true || lc.score_vlm_locked === true;
  if (!tid || !vlm) return "";
  const ticketCrop = String(lc.crop_hash || "").trim();
  const liveCrop = String(s.crop_hash || s.frame_hash || "").trim();
  const crop = ticketCrop || liveCrop;
  if (!crop) return "";
  if (ticketCrop && liveCrop && ticketCrop !== liveCrop) return "";
  const video = (snap && snap.video) || {};
  if (video.same_seq === false) return "";
  if (s.score_home != null) return `${s.score_home}-${s.score_away}`;
  if (s.home_score != null) return `${s.home_score}-${s.away_score}`;
  return s.score != null ? String(s.score) : "";
}

function fail(msg) {
  console.error(`FAIL ${msg}`);
  process.exitCode = 1;
}

if (fixture.label !== "FIXTURE" || fixture.kind !== "NON-CLAIM") {
  fail("fixture must be labeled FIXTURE / NON-CLAIM");
}

const receipt = {
  label: fixture.label,
  kind: fixture.kind,
  name: fixture.name,
  after: fixture.after,
  cases: [],
};

for (const c of fixture.cases) {
  const snap = c.snapshot;
  const board = pickBoard(snap, snap.situation || {}, snap.confirm || {}, snap.video || {});
  const pair = scorebugPair(board.home, board.away);
  const overlay = overlayScore(snap.situation || {}, snap);
  const row = {
    id: c.id,
    pickBoard: { home: board.home, away: board.away, locked: board.locked },
    ingest: { home: board.home, away: board.away, locked: board.locked, scorebug: pair },
    overlay_score: overlay,
  };
  receipt.cases.push(row);
  const exp = c.expect;
  if (board.home !== exp.home || board.away !== exp.away || board.locked !== exp.locked) {
    fail(`${c.id} pickBoard ${JSON.stringify(row.pickBoard)} want ${JSON.stringify(exp)}`);
  }
  if (pair !== exp.scorebug) fail(`${c.id} scorebugPair "${pair}" want "${exp.scorebug}"`);
  if (overlay !== exp.overlay_score) fail(`${c.id} overlay "${overlay}" want "${exp.overlay_score}"`);
}

const moved = fixture.cases.find((c) => c.id === "stuck_01_crop_moved_silence");
if (moved) {
  const lc = moved.snapshot.confirm.last_confirm;
  if (lc.home_score !== 0 || lc.away_score !== 1) fail("silence case last_confirm must stay 0-1");
  if (ticketFresh({ ticketCropHash: lc.crop_hash, liveCropHash: moved.snapshot.video.crop_hash })) {
    fail("ticketFresh must be false after FrameHub crop_hash move");
  }
}

console.log(JSON.stringify(receipt, null, 2));
if (!process.exitCode) console.error("PASS x-live-01 crop_hash move silence");
