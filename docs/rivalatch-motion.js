/* Rivalatch door loop — Gloss motion language on the Qoresence Pages hallway.
 *
 * Example knocks only (callers A and B, key k-01). Nothing here calls the
 * door, holds a key, or invents Spec fields. Wire numbers are the frozen door:
 * 202 Lodged · 200 Recalled · 409 held | incoming (Occupied · Contested).
 *
 * 16s period, eight 2s beats:
 *   Knock → Lodged(202) → held → Replay → Recalled(200) → Rival → Contested(409) → return
 *
 * Motion rules (from Gloss docs/MOTION_NOTES.md): a plate animates only when it
 * is new or when its tag changes; one settle curve; no bounce, no glow. The
 * tape advances linearly in CSS (transform only). prefers-reduced-motion shows
 * one settled frame and never loops. Hidden tabs stop the timers.
 */
(function (factory) {
  "use strict";
  var api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof document !== "undefined") {
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", api.mount);
    else api.mount();
  }
})(function () {
  "use strict";

  var PERIOD = 16;
  var BEAT = 2;
  var KEY = "k-01";

  /* plates: a = caller A first knock, r = caller A replay, b = caller B rival.
   * Each entry: [tag, meta, code]. null = plate off (vacant slot). */
  var BEATS = [
    { key: "knock", t: 0, gate: [null, KEY + " · new key"], tone: "knock",
      wire: ["POST", "/v1/gate/run", "…", "{ idempotency_key }"],
      step: "Caller A knocks with a new key.",
      plates: { a: null, r: null, b: null } },
    { key: "lodged", t: 2, gate: ["lodged", KEY + " · lodged"], tone: "lodged",
      wire: ["POST", "/v1/gate/run", "202", "{ job_id, state }"],
      step: "Lodged. First caller gets in.",
      plates: { a: ["lodged", "new key · first caller gets in", "202"], r: null, b: null } },
    { key: "held", t: 4, gate: ["lodged", KEY + " · held"], tone: "held",
      wire: ["GET", "/v1/gate/status/{job_id}", "", "{ state }"],
      step: "The first story is held on the door.",
      plates: { a: ["held", "first caller · the held story", "202"], r: null, b: null } },
    { key: "replay", t: 6, gate: [null, KEY + " · seen"], tone: "knock",
      wire: ["POST", "/v1/gate/run", "…", "same key · same payload"],
      step: "Caller A knocks again. Same key, same payload.",
      plates: { a: ["held", "first caller · the held story", "202"], r: ["knock", "same key · same payload", "…"], b: null } },
    { key: "recalled", t: 8, gate: ["recalled", KEY + " · recalled"], tone: "recalled",
      wire: ["POST", "/v1/gate/run", "200", "{ job_id, state }"],
      step: "Recalled. Idempotent return — no second ship.",
      plates: { a: ["held", "first caller · the held story", "202"], r: ["recalled", "same job_id · no second ship", "200"], b: null } },
    { key: "rival", t: 10, gate: [null, KEY + " · seen"], tone: "knock",
      wire: ["POST", "/v1/gate/run", "…", "same key · different payload"],
      step: "Caller B knocks the same key with a different payload.",
      plates: { a: ["held", "first caller · the held story", "202"], r: ["recalled", "same job_id · no second ship", "200"], b: ["knock", "same key · different payload", "…"] } },
    { key: "contested", t: 12, gate: ["contested", KEY + " · held | incoming"], tone: "contested",
      wire: ["POST", "/v1/gate/run", "409", "held | incoming"],
      step: "409. Public held | incoming. Neither story is crowned.",
      plates: { a: ["held", "first caller · the held story", "202"], r: ["recalled", "same job_id · no second ship", "200"], b: ["contested", "same key · different payload", "409"] } },
    { key: "return", t: 14, gate: [null, KEY + " · door clear"], tone: "knock",
      wire: ["POST", "/v1/gate/run", "…", "{ idempotency_key }"],
      step: "The loop returns to Knock. Example knocks, not live.",
      plates: { a: "off", r: "off", b: "off" } }
  ];

  var SETTLED = 6; /* reduced motion / no loop: the contested beat, all plates in place */

  /* Example tape frames: who knocked, with which key and payload. */
  var FRAMES = [
    { who: "A", note: "knock", payload: "story A", tone: "lodged" },
    { who: "A", note: "replay", payload: "story A", tone: "recalled" },
    { who: "B", note: "rival", payload: "story B", tone: "contested" },
    { who: "·", note: "", payload: "", tone: "idle" },
    { who: "A", note: "knock", payload: "story A", tone: "lodged" },
    { who: "·", note: "", payload: "", tone: "idle" },
    { who: "A", note: "replay", payload: "story A", tone: "recalled" },
    { who: "B", note: "rival", payload: "story B", tone: "contested" }
  ];

  function norm(t) {
    var x = t % PERIOD;
    return x < 0 ? x + PERIOD : x;
  }

  function beatAt(t) {
    return Math.floor(norm(t) / BEAT) % BEATS.length;
  }

  var TONE_VAR = {
    knock: "var(--knock)", lodged: "var(--lodged)", held: "var(--held)",
    recalled: "var(--recalled)", contested: "var(--contested)"
  };

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function buildReel(reel) {
    var frag = document.createDocumentFragment();
    var copy, i, f, node, b;
    for (copy = 0; copy < 2; copy++) { /* two copies: -50% loops seamlessly */
      for (i = 0; i < FRAMES.length; i++) {
        f = FRAMES[i];
        node = el("div", "rl-frame " + f.tone);
        if (f.tone !== "idle") node.style.setProperty("--tone", TONE_VAR[f.tone] || "var(--knock)");
        b = el("b", null, f.who);
        if (f.note) b.appendChild(el("small", null, "caller"));
        node.appendChild(b);
        node.appendChild(el("code", null, f.tone === "idle" ? "—" : KEY));
        if (f.payload) node.appendChild(el("em", null, f.payload));
        node.appendChild(el("span", null, f.note || "idle"));
        frag.appendChild(node);
      }
    }
    reel.textContent = "";
    reel.appendChild(frag);
  }

  function mountStage(stage, reduce) {
    var reel = stage.querySelector("[data-reel]");
    var gate = stage.querySelector("[data-gate]");
    var gateB = stage.querySelector("[data-gate-b]");
    var stepEl = stage.querySelector("[data-step]");
    var dots = stage.querySelectorAll("[data-dots] i");
    var wire = document.querySelector("[data-wire]");
    var wireBox = wire ? wire.closest(".rl-wire") : null;
    var plates = {};
    var nodes = stage.querySelectorAll("[data-plate]");
    var i;
    for (i = 0; i < nodes.length; i++) {
      plates[nodes[i].getAttribute("data-plate")] = {
        card: nodes[i],
        mark: nodes[i].querySelector("[data-mark]"),
        meta: nodes[i].querySelector("[data-meta]"),
        code: nodes[i].querySelector("[data-code]"),
        tag: null
      };
    }
    if (reel) buildReel(reel);

    var timers = [];
    var lastWire = "";

    function setWire(w, tone, animate) {
      if (!wire) return;
      var sig = w.join("|");
      if (wireBox) wireBox.style.setProperty("--tone", TONE_VAR[tone] || "var(--knock)");
      if (sig === lastWire) return;
      lastWire = sig;
      wire.textContent = "";
      wire.appendChild(el("span", "rl-wire-verb", w[0]));
      wire.appendChild(document.createTextNode(" " + w[1] + " "));
      if (w[2]) {
        wire.appendChild(el("span", "rl-wire-arrow", "→"));
        wire.appendChild(document.createTextNode(" "));
        wire.appendChild(el("b", null, w[2]));
        wire.appendChild(document.createTextNode(" "));
      } else {
        wire.appendChild(el("span", "rl-wire-arrow", "→"));
        wire.appendChild(document.createTextNode(" "));
      }
      wire.appendChild(document.createTextNode(w[3]));
      if (animate) {
        wire.classList.remove("is-new");
        void wire.offsetWidth;
        wire.classList.add("is-new");
      }
    }

    function setPlate(p, spec, animate) {
      if (!p) return;
      var card = p.card;
      if (spec === null || spec === "off") {
        if (spec === null) {
          card.className = "rl-card knock is-off";
          p.tag = null;
        } else {
          card.classList.add("is-off");
        }
        return;
      }
      var tag = spec[0];
      var wasOff = card.classList.contains("is-off") || p.tag === null;
      var changed = p.tag !== tag;
      p.mark.className = "rl-mark " + tag;
      p.mark.textContent = tag;
      p.meta.textContent = spec[1];
      p.code.textContent = spec[2];
      card.className = "rl-card " + tag;
      if (animate && wasOff) {
        void card.offsetWidth;
        card.classList.add("is-new");
      } else if (animate && changed) {
        void card.offsetWidth;
        card.classList.add("is-remarked");
      }
      p.tag = tag;
    }

    function apply(index, animate) {
      var beat = BEATS[index];
      var tone = beat.gate[0];
      if (tone) gate.setAttribute("data-tone", tone);
      else gate.removeAttribute("data-tone");
      if (gateB) gateB.textContent = beat.gate[1];
      if (animate && tone && beat.key !== "held") {
        gate.classList.remove("tap");
        void gate.offsetWidth;
        gate.classList.add("tap");
      }
      setPlate(plates.a, beat.plates.a, animate);
      setPlate(plates.r, beat.plates.r, animate);
      setPlate(plates.b, beat.plates.b, animate);
      if (stepEl) stepEl.textContent = beat.step;
      for (var d = 0; d < dots.length; d++) dots[d].classList.toggle("on", d <= index);
      setWire(beat.wire, beat.tone, animate);
    }

    function clear() {
      while (timers.length) clearTimeout(timers.pop());
    }

    function run() {
      clear();
      BEATS.forEach(function (beat, idx) {
        timers.push(setTimeout(function () { apply(idx, true); }, beat.t * 1000));
      });
      timers.push(setTimeout(run, PERIOD * 1000));
    }

    function still() {
      clear();
      apply(SETTLED, false);
      for (var k in plates) {
        if (Object.prototype.hasOwnProperty.call(plates, k)) plates[k].card.classList.remove("is-new", "is-remarked");
      }
      gate.classList.remove("tap");
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

  function mountReveal(reduce) {
    var items = document.querySelectorAll("[data-reveal]");
    if (!items.length) return;
    if ((reduce && reduce.matches) || typeof IntersectionObserver === "undefined") return;
    var groups = document.querySelectorAll("[data-reveal-group]");
    var g, kids, k;
    for (g = 0; g < groups.length; g++) {
      kids = groups[g].querySelectorAll("[data-reveal]");
      for (k = 0; k < kids.length; k++) kids[k].style.setProperty("--d", (k * 70) + "ms");
    }
    document.documentElement.classList.add("rl-motion");
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-in");
        io.unobserve(entry.target);
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.12 });
    for (var i = 0; i < items.length; i++) io.observe(items[i]);
    if (reduce && typeof reduce.addEventListener === "function") {
      reduce.addEventListener("change", function () {
        if (!reduce.matches) return;
        for (var j = 0; j < items.length; j++) items[j].classList.add("is-in");
        document.documentElement.classList.remove("rl-motion");
      });
    }
  }

  function mount() {
    var reduce = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
    var stage = document.querySelector("[data-door-stage]");
    if (stage) mountStage(stage, reduce);
    mountReveal(reduce);
  }

  return {
    PERIOD: PERIOD,
    BEAT: BEAT,
    BEATS: BEATS,
    SETTLED: SETTLED,
    beatAt: beatAt,
    mount: mount
  };
});
