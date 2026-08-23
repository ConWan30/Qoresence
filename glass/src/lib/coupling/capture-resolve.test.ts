import assert from "node:assert/strict";
import { test } from "node:test";
import {
  isAllowedCaptureName,
  resolveCaptureDevice,
  type DshowDevice,
} from "./capture-resolve.ts";

function row(index: number, name: string): DshowDevice {
  return { index, id: String(index), name, allowed: isAllowedCaptureName(name) };
}

test("prefers USB3.0 Video over webcam and vcam", () => {
  const devices = [
    row(0, "720p HD Camera"),
    row(1, "USB3.0 Video"),
    row(2, "OBS Virtual Camera"),
  ];
  const got = resolveCaptureDevice(devices, { requestedIndex: 0, preferName: null, allowObsVcam: false });
  assert.equal(got?.name, "USB3.0 Video");
  assert.equal(got?.index, 1);
});

test("sticky name survives unplug/replug index shift", () => {
  const devices = [
    row(0, "720p HD Camera"),
    row(1, "OBS Virtual Camera"),
    row(2, "USB3.0 Video"),
  ];
  const got = resolveCaptureDevice(devices, {
    requestedIndex: 0,
    preferName: "USB3.0 Video",
    allowObsVcam: false,
  });
  assert.equal(got?.name, "USB3.0 Video");
  assert.equal(got?.index, 2);
});

test("none when unplugged", () => {
  const devices = [row(0, "720p HD Camera"), row(1, "OBS Virtual Camera")];
  const got = resolveCaptureDevice(devices, {
    preferName: "USB3.0 Video",
    allowObsVcam: false,
  });
  assert.equal(got, null);
});

test("OBS VCam only when opted in", () => {
  const devices = [row(0, "720p HD Camera"), row(1, "OBS Virtual Camera")];
  const off = resolveCaptureDevice(devices, { preferName: null, allowObsVcam: false });
  const on = resolveCaptureDevice(devices, { preferName: null, allowObsVcam: true });
  assert.equal(off, null);
  assert.equal(on?.name, "OBS Virtual Camera");
});

test("unplugged never binds generic USB Video Device", () => {
  const devices = [row(0, "USB Video Device"), row(1, "OBS Virtual Camera")];
  const got = resolveCaptureDevice(devices, {
    requestedIndex: 0,
    preferName: "USB3.0 Video",
    allowObsVcam: false,
  });
  assert.equal(got, null);
  assert.equal(isAllowedCaptureName("USB Video Device"), false);
});

test("unknown and laptop names are not capture cards", () => {
  for (const name of ["Logitech BRIO", "HP Wide Vision", "USB2.0 HD UVC Device", "Something"]) {
    assert.equal(isAllowedCaptureName(name), false, name);
  }
});

test("empty name is refused", () => {
  assert.equal(isAllowedCaptureName(""), false);
  assert.equal(isAllowedCaptureName(null), false);
});
