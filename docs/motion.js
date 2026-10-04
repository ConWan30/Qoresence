/* Hold loop for the hallway stage.
 * 120 BPM, 8 states, 2s each, 16s period. Every painted value comes from
 * seek(t): a closed-form spring (slight overshoot) or a blur window.
 * No CSS transitions, no audio, no carried velocity between frames.
 * The sample at t and at t+16s is the same, including the cursor.
 */
(function (factory) {
  "use strict";
  var api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof document !== "undefined") api.mount();
})(function () {
  "use strict";

  var PERIOD = 16;
  var ZETA = 0.82;
  var OMEGA = 14;
  var WD = OMEGA * Math.sqrt(1 - ZETA * ZETA);
  var BETA = ZETA * OMEGA;
  var EXIT = 0.14;
  var ENTER_AT = 0.18;
  var ENTER_DUR = 0.22;
  var BLUR = 7;
  var PRESS_HOLD = 0.12;
  var CLICKS = [2, 4, 6, 8, 10, 12, 14];

  /* Geometry fractions of the well. Return matches Open so the seam is one shape. */
  var STATES = [
    { key: "open", t: 0, w: 0.46, h: 0.28, r: 10, cx: 0.5, cy: 0.64 },
    { key: "capture", t: 2, w: 0.3, h: 0.48, r: 8, cx: 0.5, cy: 0.42 },
    { key: "frame", t: 4, w: 0.9, h: 0.82, r: 6, cx: 0.5, cy: 0.5 },
    { key: "board", t: 6, w: 0.78, h: 0.46, r: 4, cx: 0.5, cy: 0.48 },
    { key: "pad", t: 8, w: 0.32, h: 0.58, r: 12, cx: 0.66, cy: 0.54 },
    { key: "ticket", t: 10, w: 0.56, h: 0.32, r: 3, cx: 0.38, cy: 0.62 },
    { key: "dark", t: 12, w: 0.9, h: 0.82, r: 2, cx: 0.5, cy: 0.5 },
    { key: "return", t: 14, w: 0.46, h: 0.28, r: 10, cx: 0.5, cy: 0.64 }
  ];

  var LAYERS = [
    { key: "open", enter: 14, exit: 2 },
    { key: "capture", enter: 2, exit: 4 },
    { key: "frame", enter: 4, exit: 6 },
    { key: "board", enter: 6, exit: 8 },
    { key: "pad", enter: 8, exit: 10 },
    { key: "ticket", enter: 10, exit: 12 },
    { key: "dark", enter: 12, exit: 14 }
  ];

  function norm(t) {
    var x = t % PERIOD;
    return x < 0 ? x + PERIOD : x;
  }

  /* Underdamped step from 0 to 1, rest initial conditions. step(0) = 0, step'(0) = 0. */
  function step(tau) {
    if (tau <= 0) return 0;
    var e = Math.exp(-BETA * tau);
    return 1 - e * (Math.cos(WD * tau) + (BETA / WD) * Math.sin(WD * tau));
  }

  function smooth(a, b, x) {
    if (x <= a) return 0;
    if (x >= b) return 1;
    var u = (x - a) / (b - a);
    return u * u * (3 - 2 * u);
  }

  /* Superposition: one spring per target change, including the previous period. */
  function track(samples, t) {
    var n = samples.length;
    var val = samples[n - 1].v;
    var i, k, prev, time, delta;
    for (k = -1; k <= 0; k++) {
      for (i = 0; i < n; i++) {
        prev = samples[(i - 1 + n) % n].v;
        time = samples[i].t + k * PERIOD;
        delta = samples[i].v - prev;
        if (delta === 0) continue;
        val += delta * step(t - time);
      }
    }
    return val;
  }

  function series(pick) {
    var out = [];
    var i;
    for (i = 0; i < STATES.length; i++) out.push({ t: STATES[i].t, v: pick(STATES[i]) });
    return out;
  }

  var W = series(function (s) { return s.w; });
  var H = series(function (s) { return s.h; });
  var R = series(function (s) { return s.r; });
  var CX = series(function (s) { return s.cx; });
  var CY = series(function (s) { return s.cy; });

  /* Cursor chases the shape just after the click, then rests on it until the next click. */
  var CURSOR = [];
  var ci;
  for (ci = 0; ci < STATES.length; ci++) {
    CURSOR.push({
      t: STATES[ci].t + 0.28,
      cx: STATES[ci].cx,
      cy: STATES[ci].cy
    });
  }
  var CURSOR_X = CURSOR.map(function (s) { return { t: s.t, v: s.cx }; });
  var CURSOR_Y = CURSOR.map(function (s) { return { t: s.t, v: s.cy }; });

  /* Shutters close after the dark well has grown, and open again on the return. */
  var SHUTTER = [
    { t: 0, v: 0 },
    { t: 12.48, v: 1 },
    { t: 14, v: 0 }
  ];

  function clickPress(t) {
    var p = 0;
    var k, i, tc;
    for (k = -1; k <= 0; k++) {
      for (i = 0; i < CLICKS.length; i++) {
        tc = CLICKS[i] + k * PERIOD;
        p += step(t - tc);
        p -= step(t - (tc + PRESS_HOLD));
      }
    }
    return p;
  }

  function layerAt(t, enter, exit) {
    var since = t - enter;
    if (since < 0) since += PERIOD;
    var len = exit - enter;
    if (len <= 0) len += PERIOD;
    if (since >= len + EXIT) return { opacity: 0, blur: 0 };
    var enterP = smooth(ENTER_AT, ENTER_AT + ENTER_DUR, since);
    var exitP = smooth(len, len + EXIT, since);
    var opacity = enterP * (1 - exitP);
    var blur = opacity <= 0.001 ? 0 : Math.max(1 - enterP, exitP) * BLUR;
    return { opacity: opacity, blur: blur };
  }

  function seek(t, boxW, boxH) {
    var time = norm(t);
    var press = clickPress(time);
    var w = track(W, time);
    var h = track(H, time);
    var cx = track(CX, time);
    var cy = track(CY, time);
    var radius = track(R, time);
    var cursorX = track(CURSOR_X, time);
    var cursorY = track(CURSOR_Y, time);
    var shutter = track(SHUTTER, time);
    var layers = {};
    var i, pose;
    for (i = 0; i < LAYERS.length; i++) {
      pose = layerAt(time, LAYERS[i].enter, LAYERS[i].exit);
      layers[LAYERS[i].key] = pose;
    }
    return {
      t: time,
      press: press,
      w: w * boxW,
      h: h * boxH,
      cx: cx * boxW,
      cy: cy * boxH,
      r: radius,
      cursorX: cursorX * boxW,
      cursorY: cursorY * boxH + press * 4,
      shutter: shutter,
      spin: (time / PERIOD) * 360 * 6,
      layers: layers
    };
  }

  function mount() {
    var stage = document.querySelector("[data-motion-stage]");
    if (!stage) return;
    var root = stage.querySelector("[data-motion-root]");
    var shape = stage.querySelector("[data-motion-shape]");
    var cursor = stage.querySelector("[data-motion-cursor]");
    var loader = stage.querySelector("[data-loader]");
    var leaves = stage.querySelectorAll("[data-leaf]");
    var layers = {};
    var nodes = stage.querySelectorAll(".motion-layer");
    var n;
    for (n = 0; n < nodes.length; n++) layers[nodes[n].getAttribute("data-key")] = nodes[n];
    if (!root || !shape || !cursor) return;

    var reduce = window.matchMedia("(prefers-reduced-motion: reduce)");
    var raf = 0;
    var origin = 0;

    function apply(sample) {
      var boxW = root.clientWidth;
      var boxH = root.clientHeight;
      if (boxW < 2 || boxH < 2) return;
      shape.style.left = (sample.cx - sample.w / 2) + "px";
      shape.style.top = (sample.cy - sample.h / 2) + "px";
      shape.style.width = sample.w + "px";
      shape.style.height = sample.h + "px";
      shape.style.borderRadius = Math.max(0, sample.r) + "px";
      shape.style.transform = "translateY(" + (sample.press * 2) + "px)";
      var shut = sample.shutter < 0 ? 0 : sample.shutter;
      var li;
      for (li = 0; li < leaves.length; li++) leaves[li].style.transform = "scaleY(" + shut + ")";
      if (loader) loader.style.transform = "rotate(" + sample.spin + "deg)";
      cursor.style.transform = "translate(" + (sample.cursorX - 1) + "px," + (sample.cursorY - 1) + "px)";
      var key, el, part, blur;
      for (key in layers) {
        if (!Object.prototype.hasOwnProperty.call(layers, key)) continue;
        el = layers[key];
        part = sample.layers[key] || { opacity: 0, blur: 0 };
        el.style.opacity = String(part.opacity);
        blur = part.blur;
        if (part.opacity <= 0.001 || blur < 0.05) {
          el.style.filter = "none";
          el.style.visibility = part.opacity <= 0.001 ? "hidden" : "visible";
        } else {
          el.style.visibility = "visible";
          el.style.filter = "blur(" + blur.toFixed(2) + "px)";
        }
      }
    }

    function frame(now) {
      apply(seek((now - origin) / 1000, root.clientWidth, root.clientHeight));
      raf = window.requestAnimationFrame(frame);
    }

    function start() {
      if (raf) {
        window.cancelAnimationFrame(raf);
        raf = 0;
      }
      if (reduce.matches) {
        stage.classList.remove("is-live");
        return;
      }
      stage.classList.add("is-live");
      origin = performance.now();
      apply(seek(0, root.clientWidth, root.clientHeight));
      raf = window.requestAnimationFrame(frame);
    }

    if (typeof reduce.addEventListener === "function") reduce.addEventListener("change", start);
    window.addEventListener("resize", function () {
      if (reduce.matches) return;
      apply(seek((performance.now() - origin) / 1000, root.clientWidth, root.clientHeight));
    });
    start();
  }

  return {
    PERIOD: PERIOD,
    STATES: STATES,
    step: step,
    seek: seek,
    mount: mount
  };
});
