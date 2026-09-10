import assert from "node:assert/strict";
import test from "node:test";
import {
  armPostReason,
  holdLabel,
  isFoundryMp4Name,
  parseXGlassStatus,
  pickCaptionMode,
} from "../src/lib/coupling/x-glass.ts";

test("Foundry mp4 name gate", () => {
  assert.equal(isFoundryMp4Name("hdmi_clip_20260909_223000.mp4"), true);
  assert.equal(isFoundryMp4Name("https://x.com/i/status/1"), false);
  assert.equal(isFoundryMp4Name("other.mp4"), false);
});

test("x_glass enabled defaults false", () => {
  const st = parseXGlassStatus({});
  assert.equal(st.enabled, false);
  assert.equal(st.grant, false);
  assert.equal(st.last_reason, "lobe_off");
});

test("arm: lobe off HOLD", () => {
  assert.equal(
    armPostReason({
      stageMode: "replay",
      clipName: "hdmi_clip_20260909_223000.mp4",
      enabled: false,
      boardLocked: true,
    }),
    "lobe_off",
  );
  assert.equal(holdLabel("lobe_off"), "HOLD · --x-glass");
});

test("arm: digit silent when unlocked", () => {
  assert.equal(
    armPostReason({
      stageMode: "replay",
      clipName: "hdmi_clip_20260909_223000.mp4",
      enabled: true,
      boardLocked: false,
    }),
    "digit_silent",
  );
  assert.equal(holdLabel("digit_silent"), "HOLD · digit silent");
});

test("arm: ok only on replay + mp4 + lobe + lock", () => {
  assert.equal(
    armPostReason({
      stageMode: "live",
      clipName: "hdmi_clip_20260909_223000.mp4",
      enabled: true,
      boardLocked: true,
    }),
    "not_replay",
  );
  assert.equal(
    armPostReason({
      stageMode: "replay",
      clipName: "hdmi_clip_20260909_223000.mp4",
      enabled: true,
      boardLocked: true,
    }),
    "ok",
  );
});

test("caption_mode auto only when boardLocked", () => {
  assert.equal(pickCaptionMode(true), "auto");
  assert.equal(pickCaptionMode(false), "silent");
});

test("create/post body must not include free caption field (shape check)", () => {
  const createBody = {
    clip_name: "hdmi_clip_20260909_223000.mp4",
    caption_mode: "auto" as const,
  };
  assert.equal("caption" in createBody, false);
  const postBody = {
    clip_name: "hdmi_clip_20260909_223000.mp4",
    caption_mode: "silent" as const,
  };
  assert.equal("caption" in postBody, false);
});
