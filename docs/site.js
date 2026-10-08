/* Qoresence Pages — one script for every page in docs/.
 *
 * - Site chrome: legacy hash redirects (home), mobile menu, copy buttons.
 * - Motion: one-shot shutter on video plinths, scroll settle for plates,
 *   and two beat stages that share one engine:
 *     · Hold loop (home):      Open card → Card → HOLD → Board □–□ → Idle → No ticket → not play → return
 *     · Door loop (Rivalatch): Knock → Lodged 202 → held → Replay → Recalled 200 → Rival → Contested 409 → return
 * - Both stages are demos with example labels. Nothing here calls a server,
 *   holds a key, paints a score, or claims LIVE.
 * - prefers-reduced-motion: no reveal, no loop; stages show one settled
 *   frame. Hidden tabs stop the timers. Without JS the markup already shows
 *   the settled frame and every plate is visible.
 *
 * Exports (Node): { door, hold, beatAt, PERIOD, BEAT } for tests.
 */
(function (factory) {
  "use strict";
  var api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", api.boot);
    else api.boot();
  }
})(function () {
  "use strict";

  var PERIOD = 16;
  var BEAT = 2;

  function norm(t) {
    var x = t % PERIOD;
    return x < 0 ? x + PERIOD : x;
  }
  function beatAt(t) {
    return Math.floor(norm(t) / BEAT) % 8;
  }

  /* ── Door loop (Rivalatch). Example callers A/B, key k-01. ─────────── */
  var KEY = "k-01";
  var A_HELD = ["held", "first caller · the held story", "202"];
  var R_DONE = ["recalled", "same job_id · no second ship", "200"];
  var DOOR = {
    key: "door",
    settled: 6,
    readout: "door",
    beats: [
      { key: "knock", gate: [null, KEY + " · new key"], tone: "knock",
        wire: ["POST", "/v1/gate/run", "…", "{ idempotency_key }"],
        step: "Caller A knocks with a new key.",
        plates: { a: null, r: null, b: null } },
      { key: "lodged", gate: ["lodged", KEY + " · lodged"], tone: "lodged",
        wire: ["POST", "/v1/gate/run", "202", "{ job_id, state }"],
        step: "Lodged. First caller gets in.",
        plates: { a: ["lodged", "new key · first caller gets in", "202"], r: null, b: null } },
      { key: "held", gate: ["held", KEY + " · held"], tone: "held",
        wire: ["GET", "/v1/gate/status/{job_id}", "", "{ state }"],
        step: "The first story is held on the door.",
        plates: { a: A_HELD, r: null, b: null } },
      { key: "replay", gate: [null, KEY + " · seen"], tone: "knock",
        wire: ["POST", "/v1/gate/run", "…", "same key · same payload"],
        step: "Caller A knocks again. Same key, same payload.",
        plates: { a: A_HELD, r: ["knock", "same key · same payload", "…"], b: null } },
      { key: "recalled", gate: ["recalled", KEY + " · recalled"], tone: "recalled",
        wire: ["POST", "/v1/gate/run", "200", "{ job_id, state }"],
        step: "Recalled. Idempotent return — no second ship.",
        plates: { a: A_HELD, r: R_DONE, b: null } },
      { key: "rival", gate: [null, KEY + " · seen"], tone: "knock",
        wire: ["POST", "/v1/gate/run", "…", "same key · different payload"],
        step: "Caller B knocks the same key with a different payload.",
        plates: { a: A_HELD, r: R_DONE, b: ["knock", "same key · different payload", "…"] } },
      { key: "contested", gate: ["contested", KEY + " · held | incoming"], tone: "contested",
        wire: ["POST", "/v1/gate/run", "409", "held | incoming"],
        step: "409. Public held | incoming. Neither story is crowned.",
        plates: { a: A_HELD, r: R_DONE, b: ["contested", "same key · different payload", "409"] } },
      { key: "return", gate: [null, KEY + " · door clear"], tone: "knock",
        wire: ["POST", "/v1/gate/run", "…", "{ idempotency_key }"],
        step: "The loop returns to Knock. Example knocks, not live.",
        plates: { a: "off", r: "off", b: "off" } }
    ],
    frames: [
      { who: "A", small: "caller", code: KEY, em: "story A", note: "knock", tone: "lodged" },
      { who: "A", small: "caller", code: KEY, em: "story A", note: "replay", tone: "recalled" },
      { who: "B", small: "caller", code: KEY, em: "story B", note: "rival", tone: "contested" },
      { idle: true },
      { who: "A", small: "caller", code: KEY, em: "story A", note: "knock", tone: "lodged" },
      { idle: true },
      { who: "A", small: "caller", code: KEY, em: "story A", note: "replay", tone: "recalled" },
      { who: "B", small: "caller", code: KEY, em: "story B", note: "rival", tone: "contested" }
    ]
  };

  /* ── Hold loop (home). Not a live session; no score, no clock value. ── */
  var CARD_ON = ["card", "every view reads the same frames", "1 owner", "Card · opened once"];
  var BOARD_HOLD = ["hold", "empty glyphs stay empty", "□ – □", "Board not licensed"];
  var BOARD_NOTICKET = ["hold", "no confirm check · score stays blank", "□ – □", "Board not licensed"];
  var PAD_IDLE = ["idle", "a still pad is presence evidence, not a fail", "idle", "Pad · Idle"];
  var HOLD = {
    key: "hold",
    settled: 5,
    readout: "window",
    beats: [
      { key: "open", gate: [null, "one clock · card not open"], tone: "knock",
        step: "Open card. One owner opens it once.",
        plates: { card: ["open", "one owner: Qoresence", "—", "Open card"], board: null, pad: null } },
      { key: "capture", gate: ["card", "card · opened once"], tone: "lodged",
        step: "Card. Every view reads the same frames; nothing else opens it.",
        plates: { card: CARD_ON, board: null, pad: null } },
      { key: "frame", gate: ["hold", "HOLD · this is a page"], tone: "held",
        step: "HOLD. The well shows the ident, not a game image.",
        plates: { card: CARD_ON, board: ["hold", "Aperture ident, not a game image", "HOLD", "Picture well"], pad: null } },
      { key: "board", gate: ["hold", "board □ – □"], tone: "held",
        step: "Board not licensed. Empty glyphs stay empty.",
        plates: { card: CARD_ON, board: BOARD_HOLD, pad: null } },
      { key: "pad", gate: ["hold", "pad · idle"], tone: "held",
        step: "Pad at rest. Idle is presence evidence, not a fail.",
        plates: { card: CARD_ON, board: BOARD_HOLD, pad: PAD_IDLE } },
      { key: "ticket", gate: ["hold", "no confirm check"], tone: "held",
        step: "No confirmed score. The board stays blank — no invented digits.",
        plates: { card: CARD_ON, board: BOARD_NOTICKET, pad: PAD_IDLE } },
      { key: "dark", gate: ["dark", "not play · goes dark"], tone: "knock", dark: true,
        step: "Not play. The theater goes dark instead of lying.",
        plates: { card: CARD_ON, board: BOARD_NOTICKET, pad: PAD_IDLE } },
      { key: "return", gate: [null, "one clock · card not open"], tone: "knock",
        step: "The loop returns. Not a live session. No score.",
        plates: { card: "off", board: "off", pad: "off" } }
    ],
    frames: [
      { who: "HDMI", code: "frame", em: "shared feed", note: "picture", tone: "lodged" },
      { who: "HID", code: "edge", em: "button log", note: "pad", tone: "held" },
      { idle: true },
      { who: "HDMI", code: "frame", em: "shared feed", note: "picture", tone: "lodged" },
      { who: "HDMI", code: "frame", em: "shared feed", note: "picture", tone: "lodged" },
      { idle: true },
      { who: "HID", code: "edge", em: "button log", note: "pad", tone: "held" },
      { who: "HDMI", code: "frame", em: "shared feed", note: "picture", tone: "lodged" }
    ]
  };

  var TONE_VAR = {
    knock: "var(--st-knock)", lodged: "var(--st-lodged)", held: "var(--st-held)",
    recalled: "var(--st-recalled)", contested: "var(--st-contested)"
  };

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function reduceQuery() {
    return window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  }

  /* ── Beat stage engine ─────────────────────────────────────────────── */
  function buildReel(reel, frames) {
    var frag = document.createDocumentFragment();
    var copy, i, f, node, b;
    for (copy = 0; copy < 2; copy++) { /* two copies: -50% loops seamlessly */
      for (i = 0; i < frames.length; i++) {
        f = frames[i];
        node = el("div", "q-frame " + (f.idle ? "idle" : f.tone));
        if (!f.idle) node.style.setProperty("--tone", TONE_VAR[f.tone] || "var(--st-knock)");
        b = el("b", null, f.idle ? "·" : f.who);
        if (f.small) b.appendChild(el("small", null, f.small));
        node.appendChild(b);
        node.appendChild(el("code", null, f.idle ? "—" : f.code));
        if (f.em) node.appendChild(el("em", null, f.em));
        node.appendChild(el("span", null, f.idle ? "idle" : f.note));
        frag.appendChild(node);
      }
    }
    reel.textContent = "";
    reel.appendChild(frag);
  }

  function mountStage(stage, spec, reduce) {
    var reel = stage.querySelector("[data-reel]");
    var gate = stage.querySelector("[data-gate]");
    var readout = stage.querySelector("[data-gate-readout]");
    var readB = stage.querySelector("[data-gate-b]");
    var stepEl = stage.querySelector("[data-step]");
    var dots = stage.querySelectorAll("[data-dots] i");
    var wire = document.querySelector("[data-wire]");
    var wireBox = wire ? wire.closest(".q-wire") : null;
    var plates = {};
    var nodes = stage.querySelectorAll("[data-plate]");
    var i;
    for (i = 0; i < nodes.length; i++) {
      plates[nodes[i].getAttribute("data-plate")] = {
        card: nodes[i],
        mark: nodes[i].querySelector("[data-mark]"),
        label: nodes[i].querySelector("[data-label]"),
        meta: nodes[i].querySelector("[data-meta]"),
        code: nodes[i].querySelector("[data-code]"),
        sig: null
      };
    }
    if (reel) buildReel(reel, spec.frames);

    var timers = [];
    var lastWire = "";

    function setWire(w, tone, animate) {
      if (!wire || !w) return;
      if (wireBox) wireBox.style.setProperty("--tone", TONE_VAR[tone] || "var(--st-knock)");
      var sig = w.join("|");
      if (sig === lastWire) return;
      lastWire = sig;
      wire.textContent = "";
      wire.appendChild(el("span", "q-wire-verb", w[0]));
      wire.appendChild(document.createTextNode(" " + w[1] + " "));
      wire.appendChild(el("span", "q-wire-arrow", "→"));
      wire.appendChild(document.createTextNode(" "));
      if (w[2]) {
        wire.appendChild(el("b", null, w[2]));
        wire.appendChild(document.createTextNode(" "));
      }
      wire.appendChild(document.createTextNode(w[3]));
      if (animate) {
        wire.classList.remove("is-new");
        void wire.offsetWidth;
        wire.classList.add("is-new");
      }
    }

    function setPlate(p, s, animate) {
      if (!p) return;
      var card = p.card;
      if (s === null) {
        card.className = "q-card knock is-off";
        p.sig = null;
        return;
      }
      if (s === "off") {
        card.classList.add("is-off");
        return;
      }
      var tag = s[0];
      var wasOff = p.sig === null || card.classList.contains("is-off");
      var sig = s.join("|");
      var changed = p.sig !== sig;
      p.mark.className = "q-mark " + tag;
      p.mark.textContent = tag;
      if (p.meta) p.meta.textContent = s[1];
      if (p.code) p.code.textContent = s[2];
      if (p.label && s[3]) p.label.textContent = s[3];
      card.className = "q-card " + tag;
      if (animate && wasOff) {
        void card.offsetWidth;
        card.classList.add("is-new");
      } else if (animate && changed) {
        void card.offsetWidth;
        card.classList.add("is-remarked");
      }
      p.sig = sig;
    }

    function apply(index, animate) {
      var beat = spec.beats[index];
      var tone = beat.gate[0];
      [gate, readout].forEach(function (n) {
        if (!n) return;
        if (tone) n.setAttribute("data-tone", tone);
        else n.removeAttribute("data-tone");
      });
      if (readB) readB.textContent = beat.gate[1];
      if (animate && tone && gate) {
        gate.classList.remove("tap");
        void gate.offsetWidth;
        gate.classList.add("tap");
      }
      stage.classList.toggle("is-dark", !!beat.dark);
      for (var k in beat.plates) {
        if (Object.prototype.hasOwnProperty.call(beat.plates, k)) setPlate(plates[k], beat.plates[k], animate);
      }
      if (stepEl) stepEl.textContent = beat.step;
      for (var d = 0; d < dots.length; d++) dots[d].classList.toggle("on", d <= index);
      setWire(beat.wire, beat.tone, animate);
    }

    function clear() {
      while (timers.length) clearTimeout(timers.pop());
    }
    function run() {
      clear();
      spec.beats.forEach(function (beat, idx) {
        timers.push(setTimeout(function () { apply(idx, true); }, idx * BEAT * 1000));
      });
      timers.push(setTimeout(run, PERIOD * 1000));
    }
    function still() {
      clear();
      apply(spec.settled, false);
      for (var k in plates) {
        if (Object.prototype.hasOwnProperty.call(plates, k)) plates[k].card.classList.remove("is-new", "is-remarked");
      }
      if (gate) gate.classList.remove("tap");
      if (wire) wire.classList.remove("is-new");
    }
    function start() {
      if (reduce && reduce.matches) still();
      else run();
    }

    document.addEventListener("visibilitychange", function () {
      if (document.hidden) clear();
      else start();
    });
    if (reduce && typeof reduce.addEventListener === "function") reduce.addEventListener("change", start);
    start();
  }

  /* ── Scroll settle ─────────────────────────────────────────────────── */
  var REVEAL_GROUPS = [
    ".contrast-pair", ".glasses", ".sidecar-row", ".steps", ".package", ".split-two",
    ".community", ".checklist", ".q-legend", ".q-rules", ".q-surfaces", ".q-viz"
  ];
  var REVEAL_SINGLES = [
    ".section-head", ".section .holo-plinth", ".faq", ".notice", ".q-different",
    ".essay article > h2", ".trace-main > .wrap > .card"
  ];

  function mountReveal(reduce) {
    if ((reduce && reduce.matches) || typeof IntersectionObserver === "undefined") return;
    var g, gi, kids, k;
    var groups = document.querySelectorAll(REVEAL_GROUPS.join(","));
    for (g = 0; g < groups.length; g++) {
      kids = groups[g].children;
      for (k = 0; k < kids.length; k++) {
        if (!kids[k].hasAttribute("data-reveal")) kids[k].setAttribute("data-reveal", "");
        kids[k].style.setProperty("--d", (k * 70) + "ms");
      }
    }
    var singles = document.querySelectorAll(REVEAL_SINGLES.join(","));
    for (gi = 0; gi < singles.length; gi++) singles[gi].setAttribute("data-reveal", "");
    /* Explicit [data-reveal-group] children (Rivalatch markup). */
    var explicit = document.querySelectorAll("[data-reveal-group]");
    for (g = 0; g < explicit.length; g++) {
      kids = explicit[g].querySelectorAll("[data-reveal]");
      for (k = 0; k < kids.length; k++) kids[k].style.setProperty("--d", (k * 70) + "ms");
    }

    var items = document.querySelectorAll("[data-reveal]");
    if (!items.length) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var t = entry.target;
        io.unobserve(t);
        t.classList.add("is-in");
        /* Hand the element back to its normal styles (hover lift, etc.). */
        t.addEventListener("animationend", function done(ev) {
          if (ev.target !== t) return;
          t.removeEventListener("animationend", done);
          t.removeAttribute("data-reveal");
        });
      });
    }, { rootMargin: "0px 0px -6% 0px", threshold: 0.08 });
    for (var i = 0; i < items.length; i++) io.observe(items[i]);
    if (reduce && typeof reduce.addEventListener === "function") {
      reduce.addEventListener("change", function () {
        if (!reduce.matches) return;
        document.documentElement.classList.remove("q-motion");
      });
    }
  }

  /* ── Chrome ────────────────────────────────────────────────────────── */
  var HASH_MAP = {
    otel: "watch.html#sidecars",
    "trace-viewer": "watch.html#why",
    glasses: "limits.html#glasses",
    caps: "limits.html",
    plane: "limits.html",
    spine: "limits.html",
    orchestrate: "limits.html",
    community: "limits.html#desk",
    faq: "limits.html#faq",
    privacy: "limits.html#ceiling",
    download: "install.html"
  };

  function redirectLegacyHash() {
    var page = location.pathname.split("/").pop() || "index.html";
    var isHome = page === "" || page === "index.html";
    var raw = (location.hash || "").replace(/^#/, "");
    if (isHome && raw && HASH_MAP[raw]) {
      location.replace(HASH_MAP[raw]);
      return true;
    }
    return false;
  }

  function mountMenu() {
    var menu = document.querySelector("[data-menu]");
    var nav = document.querySelector("[data-nav]");
    if (!menu || !nav) return;
    function set(open) {
      nav.classList.toggle("open", open);
      menu.setAttribute("aria-expanded", String(open));
    }
    menu.addEventListener("click", function () { set(!nav.classList.contains("open")); });
    nav.querySelectorAll("a").forEach(function (a) { a.addEventListener("click", function () { set(false); }); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") set(false); });
  }

  function mountCopy() {
    document.querySelectorAll("[data-copy]").forEach(function (button) {
      var host = button.parentElement;
      /* The button floats first so wrapped text flows around it, never under it. */
      if (host && host.firstChild !== button) host.insertBefore(button, host.firstChild);
      button.addEventListener("click", function () {
        var code = (host && host.dataset.code) || (host ? host.textContent : "").replace(/^\s*copy/i, "").trim();
        if (!navigator.clipboard) { button.textContent = "select"; return; }
        navigator.clipboard.writeText(code).then(function () {
          button.textContent = "copied";
          setTimeout(function () { button.textContent = "copy"; }, 1400);
        }, function () { button.textContent = "select"; });
      });
    });
  }

  function mountShutter() {
    var leaves = document.querySelectorAll("[data-shutter]");
    if (!leaves.length || !document.documentElement.classList.contains("q-motion")) return;
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        leaves.forEach(function (n) { n.classList.add("is-open"); });
      });
    });
  }

  /* Commands wrap at spaces, not after the hyphen in "--flag": each token is an
     inline-block that only breaks inside itself when wider than the line. */
  function mountCodeWrap() {
    document.querySelectorAll(".code").forEach(function (block) {
      Array.prototype.slice.call(block.childNodes).forEach(function (node) {
        if (node.nodeType !== 3 || !node.nodeValue.trim()) return;
        var frag = document.createDocumentFragment();
        node.nodeValue.split(/(\s+)/).forEach(function (part) {
          if (!part) return;
          if (/^\s+$/.test(part)) frag.appendChild(document.createTextNode(part));
          else frag.appendChild(el("span", "code-tok", part));
        });
        block.replaceChild(frag, node);
      });
    });
  }

  /* Anchor jumps land below the sticky mast, whatever height it wraps to. */
  function mountScrollPadding() {
    var header = document.querySelector(".holo-header");
    if (!header) return;
    function set() {
      document.documentElement.style.scrollPaddingTop = Math.ceil(header.getBoundingClientRect().height + 16) + "px";
    }
    set();
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(set).observe(header);
    else window.addEventListener("resize", set);
  }

  function boot() {
    if (redirectLegacyHash()) return;
    mountScrollPadding();
    var reduce = reduceQuery();
    var motion = !(reduce && reduce.matches);
    if (motion) document.documentElement.classList.add("q-motion");
    mountMenu();
    mountCopy();
    mountCodeWrap();
    mountShutter();
    var door = document.querySelector("[data-door-stage]");
    if (door) mountStage(door, DOOR, reduce);
    var hold = document.querySelector("[data-hold-stage]");
    if (hold) mountStage(hold, HOLD, reduce);
    mountReveal(reduce);
  }

  function pub(spec) {
    return {
      BEATS: spec.beats.map(function (b, i) { return { key: b.key, t: i * BEAT }; }),
      SETTLED: spec.settled,
      raw: spec
    };
  }

  return {
    PERIOD: PERIOD,
    BEAT: BEAT,
    beatAt: beatAt,
    door: pub(DOOR),
    hold: pub(HOLD),
    boot: boot
  };
});
