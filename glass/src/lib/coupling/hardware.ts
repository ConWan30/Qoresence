/** Live DualSense + capture card. Frames never leave the browser. */

import {
  DEFAULT_PREFER_NAME,
  isAllowedCaptureName,
  isObsVirtualCameraName,
  isPhysicalCardName,
  resolveCaptureDevice,
  type DshowDevice,
} from "./capture-resolve";
import { deckLiveJpgUrl, deckMjpegUrl, probeDeck } from "./qoresence-deck";

type HidDeviceLike = {
  open: () => Promise<void>;
  addEventListener: (type: "inputreport", fn: (ev: HidReportLike) => void) => void;
};

type HidReportLike = {
  data: DataView;
  reportId: number;
};

type NavigatorHid = {
  hid?: {
    requestDevice: (opts: { filters: { vendorId: number; productId: number }[] }) => Promise<HidDeviceLike[]>;
  };
};

export type PadSample = {
  connected: boolean;
  name: string;
  r2: number;
  left: number;
  held: string[];
  reports: number;
};

export type CaptureStatus =
  | "off"
  | "arming"
  | "live"
  | "blocked"
  | "busy"
  | "missing"
  | "framed";

export type CaptureSample = {
  status: CaptureStatus;
  label: string;
  motion: number;
  energy: number;
  fresh: boolean;
};

export type VideoDevice = {
  id: string;
  label: string;
  score: number;
  kind: "capture" | "camera";
  allowed: boolean;
};

export type ArmResult = {
  status: CaptureStatus;
  label: string;
  error: string;
  devices: VideoDevice[];
};

export type EnvHint = {
  framed: boolean;
  camera: boolean | null;
  display: boolean | null;
  gamepad: number;
};

const LAST_NAME_KEY = "qoresence.capturePreferName";

const FACE = ["cross", "circle", "square", "triangle"] as const;
const BUMP = ["l1", "r1", "l2", "r2"] as const;

let stream: MediaStream | null = null;
let video: HTMLVideoElement | null = null;
let captureLabel = "";
let captureStatus: CaptureStatus = "off";
let lastError = "";
let lastVideoTime = -1;
let lastAdvanceAt = 0;
let prevLuma: Float32Array | null = null;
let lumaCanvas: HTMLCanvasElement | null = null;
let padReports = 0;
let hidDevice: HidDeviceLike | null = null;
let hidSample: PadSample | null = null;
let armedOnce = false;
let feedKind: "none" | "deck" | "uvc" | "share" = "none";
let deckSrc = "";
let deckMotion = 0;
let deckEnergy = 0.45;
let deckPump = 0;
let deckJpg: HTMLImageElement | null = null;
let lastMjpegBump = 0;

export async function cameraGranted(): Promise<boolean> {
  try {
    const nav = navigator as Navigator & {
      permissions?: { query: (q: { name: string }) => Promise<{ state: string }> };
    };
    const p = await nav.permissions?.query({ name: "camera" });
    return p?.state === "granted";
  } catch {
    return false;
  }
}

export function keepVideoPlaying() {
  if (feedKind === "deck") {
    if (stream) stopTracks();
    return;
  }
  if (video?.paused) void video.play().catch(() => undefined);
  const track = stream?.getVideoTracks()[0];
  if (captureStatus === "live" && (!track || track.readyState === "ended")) {
    captureStatus = "off";
  }
}

export function captureNeedsRebind(): boolean {
  keepVideoPlaying();
  if (feedKind === "deck") {
    // Theater owns a single MJPEG <img>. JPEG thaw/rebind flickers the stage.
    return false;
  }
  if (captureStatus === "live" || captureStatus === "arming") return false;
  if (captureStatus === "blocked" || captureStatus === "framed") return false;
  return armedOnce;
}

export function getDeckJpg(): HTMLImageElement | null {
  return deckJpg && deckJpg.naturalWidth > 0 ? deckJpg : null;
}

export function bumpDeckMjpeg(): string {
  if (feedKind !== "deck") return deckSrc;
  deckSrc = deckMjpegUrl();
  lastMjpegBump = performance.now();
  return deckSrc;
}

export function thawDeck(): string {
  if (feedKind !== "deck") return deckSrc;
  return deckSrc;
}

export function getDeckSrc(): string {
  return deckSrc;
}

export function getFeedKind(): "none" | "deck" | "uvc" | "share" {
  return feedKind;
}

export function getCaptureVideo(): HTMLVideoElement | null {
  return video;
}

export function getCaptureStatus(): { status: CaptureStatus; label: string; error: string } {
  return { status: captureStatus, label: captureLabel, error: lastError };
}

export function diagnoseEnv(): EnvHint {
  const framed = typeof window !== "undefined" && window.self !== window.top;
  const policy = (document as Document & {
    featurePolicy?: { allowsFeature: (n: string) => boolean };
    permissionsPolicy?: { allowsFeature: (n: string) => boolean };
  }).featurePolicy ?? (document as Document & {
    permissionsPolicy?: { allowsFeature: (n: string) => boolean };
  }).permissionsPolicy;
  const allows = (n: string): boolean | null => {
    try {
      if (!policy?.allowsFeature) return null;
      return policy.allowsFeature(n);
    } catch {
      return null;
    }
  };
  const pads = typeof navigator !== "undefined" ? (navigator.getGamepads?.() ?? []) : [];
  return {
    framed,
    camera: allows("camera"),
    display: allows("display-capture"),
    gamepad: pads.filter(Boolean).length,
  };
}

export function readPad(): PadSample {
  if (hidSample?.connected) return hidSample;
  const pads = typeof navigator !== "undefined" ? (navigator.getGamepads?.() ?? []) : [];
  for (const pad of pads) {
    if (!pad) continue;
    padReports += 1;
    const r2 = pad.buttons[7]?.value ?? 0;
    const left = Math.min(1, Math.hypot(pad.axes[0] ?? 0, pad.axes[1] ?? 0));
    const held: string[] = [];
    FACE.forEach((n, i) => {
      if (pad.buttons[i]?.pressed) held.push(n);
    });
    BUMP.forEach((n, i) => {
      const b = pad.buttons[i + 4];
      if (n === "l2" || n === "r2") {
        if ((b?.value ?? 0) > 0.08) held.push(n);
      } else if (b?.pressed) held.push(n);
    });
    return {
      connected: true,
      name: padName(pad.id),
      r2,
      left,
      held,
      reports: padReports,
    };
  }
  return {
    connected: false,
    name: "",
    r2: 0,
    left: 0,
    held: [],
    reports: padReports,
  };
}

export function padName(id: string): string {
  if (/dualsense|0ce6|0df2/i.test(id)) return "DualSense";
  if (/054c|sony|wireless controller/i.test(id)) return "DualSense";
  if (/xbox|045e/i.test(id)) return "Xbox pad";
  return "Pad";
}

function classifyError(err: unknown): { status: CaptureStatus; error: string } {
  const name = err instanceof DOMException ? err.name : "";
  const msg = err instanceof Error ? err.message : String(err);
  const env = diagnoseEnv();
  if (name === "NotAllowedError" || name === "SecurityError") {
    if (env.framed || env.camera === false) {
      return {
        status: "framed",
        error:
          "Stay in this preview. The sandbox host cannot be opened as its own tab. Click Arm HDMI here and allow camera if asked.",
      };
    }
    return { status: "blocked", error: "Permission denied. Allow camera, then Arm HDMI again." };
  }
  if (name === "NotReadableError" || name === "AbortError" || /in use|busy|could not start/i.test(msg)) {
    return {
      status: "busy",
      error:
        "Windows still holds this camera. Close Edge and ZCode tabs that used a camera, unplug the dongle, plug it back, then Arm HDMI.",
    };
  }
  if (name === "NotFoundError") {
    return { status: "missing", error: "No video device. Plug in the capture card, then Arm HDMI." };
  }
  if (name === "OverconstrainedError") {
    return { status: "missing", error: "That mode is not on the dongle. Pick the card from the list." };
  }
  return { status: "missing", error: `${name || "Error"}: ${msg}`.slice(0, 160) };
}

function toVideoDevice(d: MediaDeviceInfo): VideoDevice {
  const label = d.label || "";
  const allowed = isAllowedCaptureName(label);
  const physical = isPhysicalCardName(label);
  return {
    id: d.deviceId,
    label: label || "(unknown)",
    score: physical ? 10 : allowed ? 1 : -1,
    kind: physical ? "capture" : "camera",
    allowed,
  };
}

async function stopAndWait(s: MediaStream | null) {
  if (!s) return;
  for (const t of s.getTracks()) {
    t.stop();
    s.removeTrack(t);
  }
  await new Promise((r) => window.setTimeout(r, 180));
}

async function listVideoDevices(): Promise<VideoDevice[]> {
  const infos = await navigator.mediaDevices.enumerateDevices();
  return infos.filter((d) => d.kind === "videoinput").map(toVideoDevice);
}

async function probeThenList(): Promise<VideoDevice[]> {
  // Never unconstrained camera probe — that opens the laptop webcam when
  // the HDMI card is unplugged. Enumerate only; blank labels stay refused.
  return listVideoDevices();
}

function toDshow(list: VideoDevice[]): DshowDevice[] {
  return list.map((d, index) => ({
    index,
    id: d.id,
    name: d.label,
    allowed: d.allowed,
  }));
}

function stickyPreferName(): string {
  try {
    return localStorage.getItem(LAST_NAME_KEY) || DEFAULT_PREFER_NAME;
  } catch {
    return DEFAULT_PREFER_NAME;
  }
}

function resolveFromList(list: VideoDevice[], preferredId?: string): VideoDevice | null {
  const dshow = toDshow(list);
  if (preferredId) {
    const hit = list.find((d) => d.id === preferredId);
    if (!hit || !hit.allowed) return null;
    if (isObsVirtualCameraName(hit.label)) return hit;
    const got = resolveCaptureDevice(dshow, {
      preferName: hit.label,
      allowObsVcam: false,
    });
    return got ? list.find((d) => d.id === got.id) ?? null : null;
  }
  const got = resolveCaptureDevice(dshow, {
    preferName: stickyPreferName(),
    allowObsVcam: false,
  });
  return got ? list.find((d) => d.id === got.id) ?? null : null;
}

async function openDongle(deviceId: string): Promise<MediaStream> {
  const ladder: MediaStreamConstraints[] = [
    { audio: false, video: { deviceId: { exact: deviceId } } },
    { audio: false, video: { deviceId: { exact: deviceId }, width: { exact: 1920 }, height: { exact: 1080 } } },
    { audio: false, video: { deviceId: { exact: deviceId }, width: { exact: 1280 }, height: { exact: 720 } } },
    { audio: false, video: { deviceId: { exact: deviceId }, width: { exact: 720 }, height: { exact: 480 } } },
    { audio: false, video: { deviceId: { exact: deviceId }, width: { exact: 640 }, height: { exact: 480 } } },
    { audio: false, video: { deviceId: { ideal: deviceId } } },
  ];
  let last: unknown = null;
  for (const c of ladder) {
    try {
      return await navigator.mediaDevices.getUserMedia(c);
    } catch (err) {
      last = err;
    }
  }
  throw last instanceof Error ? last : new Error("Dongle refused every mode");
}

export async function armCapture(deviceId?: string): Promise<ArmResult> {
  lastError = "";
  if (!deviceId) {
    stopTracks();
    captureStatus = "arming";
    const deck = await probeDeck();
    deckSrc = deckMjpegUrl();
    feedKind = "deck";
    captureLabel = deck.up ? deck.label : "Qoresence LIVE";
    captureStatus = "live";
    lastError = deck.up ? "" : "Watching Deck JPEG. Qoresence owns the card.";
    armedOnce = true;
    lastAdvanceAt = performance.now();
    lastMjpegBump = performance.now();
    startDeckPump();
    return pack([]);
  }

  lastError = "";
  releaseCapture();
  captureStatus = "arming";

  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    captureStatus = "missing";
    lastError = "Deck is down. Start --play --deck, or plug in USB3.0 Video.";
    return pack([]);
  }
  captureStatus = "arming";
  let list: VideoDevice[] = [];
  try {
    list = await probeThenList();
  } catch (err) {
    const mapped = classifyError(err);
    captureStatus = mapped.status;
    lastError = mapped.error;
    return pack([]);
  }
  const picked = resolveFromList(list, deviceId);
  if (!picked) {
    captureStatus = "missing";
    lastError = "No capture card found (USB3.0 Video / HDMI unplugged?). Laptop cams are refused.";
    return pack(list);
  }
  try {
    const s = await openDongle(picked.id);
    await attachStream(s, picked.label);
    armedOnce = true;
    feedKind = "uvc";
    deckSrc = "";
    try {
      localStorage.setItem(LAST_NAME_KEY, picked.label);
    } catch {
      /* ignore */
    }
    captureStatus = "live";
    lastError = "";
    return pack(list);
  } catch (err) {
    const mapped = classifyError(err);
    captureStatus = mapped.status;
    lastError = mapped.error;
    return pack(list);
  }
}

export async function armShare(): Promise<ArmResult> {
  lastError = "";
  const env = diagnoseEnv();
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getDisplayMedia) {
    captureStatus = "missing";
    lastError = "This browser cannot share a window.";
    return pack([]);
  }
  captureStatus = "arming";
  try {
    const s = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: false,
    });
    const label = s.getVideoTracks()[0]?.label || "shared picture";
    s.getVideoTracks()[0]?.addEventListener("ended", () => {
      if (stream === s) releaseCapture();
    });
    await attachStream(s, label);
    captureStatus = "live";
    lastError = "";
    feedKind = "share";
    deckSrc = "";
    armedOnce = true;
    return pack([]);
  } catch (err) {
    const mapped = classifyError(err);
    captureStatus = mapped.status === "blocked" && env.framed ? "framed" : mapped.status;
    lastError =
      mapped.status === "blocked" && env.framed
        ? "Stay in this preview. Click Share picture here — do not open the sandbox host in a new tab."
        : mapped.error;
    return pack([]);
  }
}

function pack(devices: VideoDevice[]): ArmResult {
  return {
    status: captureStatus,
    label: captureLabel,
    error: lastError,
    devices,
  };
}

export function releaseCapture() {
  stopDeckPump();
  stopTracks();
  prevLuma = null;
  lastVideoTime = -1;
  deckSrc = "";
  feedKind = "none";
  if (captureStatus === "live" || captureStatus === "arming") captureStatus = "off";
}

function stopTracks() {
  stream?.getTracks().forEach((t) => t.stop());
  stream = null;
  if (video) {
    video.srcObject = null;
    video = null;
  }
}

async function attachStream(s: MediaStream, label: string) {
  stopTracks();
  stream = s;
  captureLabel = shortenLabel(label);
  const el = document.createElement("video");
  el.muted = true;
  el.playsInline = true;
  el.autoplay = true;
  el.setAttribute("playsinline", "true");
  el.srcObject = s;
  el.loop = false;
  await el.play().catch(() => undefined);
  video = el;
  lastAdvanceAt = performance.now();
  const track = s.getVideoTracks()[0];
  track?.addEventListener("ended", () => {
    if (stream === s) {
      captureStatus = "off";
    }
  });
}

function stopDeckPump() {
  if (deckPump) window.clearTimeout(deckPump);
  deckPump = 0;
  deckJpg = null;
}

function startDeckPump() {
  if (deckPump) window.clearTimeout(deckPump);
  const tick = () => {
    if (feedKind !== "deck") return;
    const next = new Image();
    next.onload = () => {
      deckJpg = next;
      lastAdvanceAt = performance.now();
    };
    next.src = deckLiveJpgUrl();
    deckPump = window.setTimeout(tick, 400);
  };
  tick();
}

function sampleDeckFrame(img: HTMLImageElement) {
  if (!img.naturalWidth) return;
  if (!lumaCanvas) lumaCanvas = document.createElement("canvas");
  const cols = 80;
  const rows = 45;
  lumaCanvas.width = cols;
  lumaCanvas.height = rows;
  const ctx = lumaCanvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return;
  ctx.drawImage(img, 0, 0, cols, rows);
  const pix = ctx.getImageData(0, 0, cols, rows).data;
  const n = cols * rows;
  if (!prevLuma || prevLuma.length !== n) prevLuma = new Float32Array(n);
  let energy = 0;
  let diff = 0;
  for (let i = 0; i < n; i++) {
    const o = i * 4;
    const y = 0.299 * pix[o] + 0.587 * pix[o + 1] + 0.114 * pix[o + 2];
    energy += y;
    diff += Math.abs(y - prevLuma[i]);
    prevLuma[i] = y;
  }
  deckEnergy = energy / n / 255;
  deckMotion = Math.min(8, diff / n / 8);
}

function shortenLabel(label: string): string {
  const t = label.replace(/\s*\([0-9a-f:]{5,}\)\s*/i, "").trim();
  return t.slice(0, 42) || "capture";
}

export async function wakePad(): Promise<PadSample> {
  const gp = readPad();
  if (gp.connected) return gp;
  const nav = navigator as Navigator & NavigatorHid;
  if (!nav.hid?.requestDevice) return gp;
  try {
    const list = await nav.hid.requestDevice({
      filters: [
        { vendorId: 0x054c, productId: 0x0ce6 },
        { vendorId: 0x054c, productId: 0x0df2 },
      ],
    });
    const dev = list[0];
    if (!dev) return gp;
    await dev.open();
    hidDevice = dev;
    dev.addEventListener("inputreport", onHidReport);
    hidSample = {
      connected: true,
      name: "DualSense",
      r2: 0,
      left: 0,
      held: [],
      reports: 0,
    };
    return hidSample;
  } catch {
    return gp;
  }
}

function onHidReport(ev: HidReportLike) {
  const d = new Uint8Array(ev.data.buffer);
  if (d.length < 6) return;
  const lx = (d[0] - 128) / 128;
  const ly = (d[1] - 128) / 128;
  const r2 = d[5] / 255;
  padReports += 1;
  hidSample = {
    connected: true,
    name: "DualSense",
    r2,
    left: Math.min(1, Math.hypot(lx, ly)),
    held: r2 > 0.08 ? ["r2"] : [],
    reports: padReports,
  };
}

export function sampleCapture(): CaptureSample {
  const st = getCaptureStatus();
  if (feedKind === "deck" && st.status === "live") {
    const fresh = performance.now() - lastAdvanceAt < 400;
    return {
      status: st.status,
      label: st.label,
      motion: deckMotion,
      energy: deckEnergy,
      fresh,
    };
  }
  if (st.status !== "live" || !video || video.readyState < 2) {
    return { status: st.status, label: st.label, motion: 0, energy: 0, fresh: false };
  }
  const vw = video.videoWidth;
  const vh = video.videoHeight;
  if (!vw || !vh) {
    return { status: st.status, label: st.label, motion: 0, energy: 0, fresh: false };
  }

  if (!lumaCanvas) lumaCanvas = document.createElement("canvas");
  const cols = 80;
  const rows = 45;
  lumaCanvas.width = cols;
  lumaCanvas.height = rows;
  const ctx = lumaCanvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return { status: st.status, label: st.label, motion: 0, energy: 0, fresh: false };
  ctx.drawImage(video, 0, 0, cols, rows);
  const pix = ctx.getImageData(0, 0, cols, rows).data;
  const n = cols * rows;
  if (!prevLuma || prevLuma.length !== n) prevLuma = new Float32Array(n);

  let energy = 0;
  let diff = 0;
  for (let i = 0; i < n; i++) {
    const o = i * 4;
    const y = 0.299 * pix[o] + 0.587 * pix[o + 1] + 0.114 * pix[o + 2];
    energy += y;
    diff += Math.abs(y - prevLuma[i]);
    prevLuma[i] = y;
  }
  energy /= n * 255;
  const motion = Math.min(8, diff / n / 8);
  const t = video.currentTime;
  const now2 = performance.now();
  if (t !== lastVideoTime) {
    lastVideoTime = t;
    lastAdvanceAt = now2;
  }
  const fresh = now2 - lastAdvanceAt < 350;
  return { status: st.status, label: st.label, motion, energy, fresh };
}

export function captureFreshMs(now = performance.now()): number {
  return now - lastAdvanceAt;
}

void hidDevice;
