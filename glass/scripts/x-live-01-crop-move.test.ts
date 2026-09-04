import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  parseDeckMessage,
  pickBoard,
  scorebugPair,
  ticketFresh,
} from "../src/lib/coupling/board.ts";

const fixture = JSON.parse(
  readFileSync(join(dirname(fileURLToPath(import.meta.url)), "../../lab/x_live_01_crop_move/FIXTURE.json"), "utf8"),
);

test("FIXTURE x-live-01 is labeled NON-CLAIM", () => {
  assert.equal(fixture.label, "FIXTURE");
  assert.equal(fixture.kind, "NON-CLAIM");
  assert.equal(fixture.after.pr_152_pickBoard, "374e940");
  assert.equal(fixture.after.pr_153_docs, "7a7393f");
});

test("x-live-01 control: fresh 0-1 paints when crop matches", () => {
  const c = fixture.cases.find((row: { id: string }) => row.id === "control_fresh_01_paints");
  const snap = c.snapshot;
  const b = pickBoard(snap, snap.situation, snap.confirm, snap.video);
  assert.equal(b.home, 0);
  assert.equal(b.away, 1);
  assert.equal(b.locked, true);
  const ing = parseDeckMessage(snap);
  assert.ok(ing);
  assert.equal(ing.homeScore, 0);
  assert.equal(ing.awayScore, 1);
  assert.equal(scorebugPair(ing), "0-1");
});

test("x-live-01 FIXTURE: stuck 0-1 + crop_hash move — blank beats hold", () => {
  const c = fixture.cases.find((row: { id: string }) => row.id === "stuck_01_crop_moved_silence");
  const snap = c.snapshot;
  const lc = snap.confirm.last_confirm;
  assert.equal(lc.home_score, 0);
  assert.equal(lc.away_score, 1);
  assert.equal(lc.crop_hash, fixture.crop_was);
  assert.equal(snap.situation.home_score, 0);
  assert.equal(snap.situation.away_score, 1);
  assert.equal(snap.video.crop_hash, fixture.crop_now);
  assert.equal(snap.situation.crop_hash, fixture.crop_now);
  assert.equal(ticketFresh({ ticketCropHash: lc.crop_hash, liveCropHash: snap.video.crop_hash }), false);

  const b = pickBoard(snap, snap.situation, snap.confirm, snap.video);
  assert.equal(b.home, null);
  assert.equal(b.away, null);
  assert.equal(b.locked, false);

  const ing = parseDeckMessage(snap);
  assert.ok(ing);
  assert.equal(ing.homeScore, null);
  assert.equal(ing.awayScore, null);
  assert.equal(ing.boardLocked, false);
  assert.equal(scorebugPair(ing), "");
  assert.doesNotMatch(scorebugPair(ing), /0-1/);
});

test("x-live-01 FrameHub video crop_hash move empties pickBoard", () => {
  const c = fixture.cases.find((row: { id: string }) => row.id === "stuck_01_framehub_video_only_pickboard");
  const snap = c.snapshot;
  assert.equal(snap.confirm.last_confirm.home_score, 0);
  assert.equal(snap.confirm.last_confirm.away_score, 1);
  assert.equal(snap.situation.crop_hash, fixture.crop_was);
  assert.equal(snap.video.crop_hash, fixture.crop_now);
  const b = pickBoard(snap, snap.situation, snap.confirm, snap.video);
  assert.equal(b.home, null);
  assert.equal(b.away, null);
  assert.equal(b.locked, false);
  const ing = parseDeckMessage(snap);
  assert.ok(ing);
  assert.equal(ing.homeScore, null);
  assert.equal(ing.awayScore, null);
  assert.equal(scorebugPair(ing), "");
});
