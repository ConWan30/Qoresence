#!/usr/bin/env node
/**
 * LAB / FIXTURE harness — X LIVE 0-1 crop_hash move silence.
 * NON-CLAIM. Does not start --play. Prints no secrets.
 */
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  parseDeckMessage,
  pickBoard,
  scorebugPair,
  ticketFresh,
} from "../../glass/src/lib/coupling/board.ts";

const here = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(join(here, "FIXTURE.json"), "utf8"));

function overlayScore(s, snap) {
  const lc = (snap?.confirm && snap.confirm.last_confirm) || s.last_confirm || {};
  const tid = String(lc.ticket_id || s.confirm_ticket_id || "").trim();
  const vlm = s.score_vlm_locked === true || lc.score_vlm_locked === true;
  if (!tid || !vlm) return "";
  const ticketCrop = String(lc.crop_hash || "").trim();
  const liveCrop = String(s.crop_hash || s.frame_hash || "").trim();
  const crop = ticketCrop || liveCrop;
  if (!crop) return "";
  if (ticketCrop && liveCrop && ticketCrop !== liveCrop) return "";
  const video = snap?.video || {};
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
  const board = pickBoard(snap, snap.situation, snap.confirm, snap.video);
  const ing = parseDeckMessage(snap);
  const pair = ing ? scorebugPair(ing) : "";
  const sit = snap.situation || {};
  const overlay = overlayScore(sit, snap);
  const row = {
    id: c.id,
    pickBoard: { home: board.home, away: board.away, locked: board.locked },
    ingest: ing
      ? { home: ing.homeScore, away: ing.awayScore, locked: ing.boardLocked, scorebug: pair }
      : null,
    overlay_score: overlay,
  };
  receipt.cases.push(row);

  const exp = c.expect;
  if (board.home !== exp.home || board.away !== exp.away || board.locked !== exp.locked) {
    fail(`${c.id} pickBoard ${JSON.stringify(row.pickBoard)} want ${JSON.stringify(exp)}`);
  }
  if (!ing || ing.homeScore !== exp.home || ing.awayScore !== exp.away || ing.boardLocked !== exp.locked) {
    fail(`${c.id} ingest ${JSON.stringify(row.ingest)} want locked=${exp.locked}`);
  }
  if (pair !== exp.scorebug) {
    fail(`${c.id} scorebugPair "${pair}" want "${exp.scorebug}"`);
  }
  if (overlay !== exp.overlay_score) {
    fail(`${c.id} overlay "${overlay}" want "${exp.overlay_score}"`);
  }
}

const moved = fixture.cases.find((c) => c.id === "stuck_01_crop_moved_silence");
if (moved) {
  const lc = moved.snapshot.confirm.last_confirm;
  if (lc.home_score !== 0 || lc.away_score !== 1) fail("silence case last_confirm must stay 0-1");
  if (!ticketFresh({ ticketCropHash: lc.crop_hash, liveCropHash: moved.snapshot.video.crop_hash })) {
    /* expected: crop move is not ticket-fresh */
  } else {
    fail("ticketFresh must be false after FrameHub crop_hash move");
  }
}

console.log(JSON.stringify(receipt, null, 2));
if (!process.exitCode) console.error("PASS x-live-01 crop_hash move silence");
