/* Qoresence Pages — one script for every page in docs/.
 *
 * - Site chrome: legacy hash redirects (home), copy buttons, code wrapping,
 *   anchor padding under the sticky header.
 * - Motion: one-shot shutter on video plinths, scroll settle for plates, and
 *   the home read stage ([data-read-stage]):
 *     dark → read 1/3 → 2/3 → 3/3 → LOCKED (aperture opens, gold board)
 *     → replay banner: DARK → suspicious jump: recheck 0/9…4/9 → blank read
 *     resets: still DARK → loop.
 * - The stage is a demo on fixture frames ("Demo · fixture frames · not
 *   live"). Nothing here calls a server, holds a key, or claims LIVE. Digits
 *   reach the board only on the locked beat; every doubtful beat is □ – □.
 * - Only classes and text change; CSS animates transform / opacity only.
 * - prefers-reduced-motion: no reveal, no loop; the stage keeps the settled
 *   LOCKED frame that the markup already shows (also the no-JS view).
 * - Hidden tab: timers stop, html.is-tab-hidden pauses CSS loops; the loop
 *   restarts from the top when the tab is visible again.
 *
 * Exports (Node): { read, LOOP, beatAt } for tests.
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

  /* ── Read stage (home). Fixture frames, not live. ─────────────────────
     A Madden-style scorebug on a capture frame. Scores avoid the digit 8
     and clocks stay under 10:00 (the reader does not know those yet). */
  var LOOP = 16000;
  var BUG = { l: "14", r: "10", q: "2nd" };
  var DARK_BOARD = { state: "dark", mark: "dark", word: "dark", score: null, meta: "— · —:—" };
  var BEATS = [
    { key: "dark", t: 0, dot: 0, seq: 412, bug: { c: "3:12" }, cover: false, iris: false, scan: false,
      board: DARK_BOARD, reads: [0, 3], stamp: "0/3",
      line: "waiting for a sure read",
      step: "Capture frame in. Nothing confirmed yet, so the board stays dark." },
    { key: "read-1", t: 1000, dot: 1, seq: 418, bug: { c: "3:12" }, scan: true,
      board: { state: "reading", mark: "read", word: "reading", score: null, meta: "— · —:—" }, reads: [1, 3], stamp: "1/3",
      line: "read 1/3 → <b>14 · 10 · 2nd · 3:12</b>",
      step: "Read 1/3: score, quarter and clock glyphs off the scorebug." },
    { key: "read-2", t: 2000, dot: 1, seq: 425, bug: { c: "3:11" }, scan: true,
      board: { state: "reading", mark: "read", word: "reading", score: null, meta: "— · —:—" }, reads: [2, 3], stamp: "2/3",
      line: "read 2/3 → <b>14 · 10 · 2nd · 3:11</b>",
      step: "Read 2/3: same score, same quarter, a few hundred ms later." },
    { key: "read-3", t: 3000, dot: 1, seq: 431, bug: { c: "3:10" }, scan: true,
      board: { state: "reading", mark: "read", word: "reading", score: null, meta: "— · —:—" }, reads: [3, 3], stamp: "3/3",
      line: "read 3/3 → <b>14 · 10 · 2nd · 3:10</b>",
      step: "Read 3/3: all three match." },
    { key: "locked", t: 3700, dot: 2, seq: 433, bug: { c: "3:10" }, iris: true,
      board: { state: "locked", mark: "locked", word: "locked", score: ["14", "10"], meta: "2nd · 3:10" }, reads: [3, 3], stamp: "3/3",
      line: "read 3/3 → <b>14 · 10 · 2nd · 3:10</b>",
      step: "Three matching reads. The aperture opens; the board locks." },
    { key: "doubt", t: 7600, dot: 3, seq: 512, bug: { c: "3:02" }, cover: true, iris: false,
      board: DARK_BOARD, reads: [0, 3], stamp: "—",
      line: "replay banner over the score → <b>no read</b>",
      step: "A replay banner covers the score. Unsure, so the board goes dark, not last-good." },
    { key: "recheck", t: 10400, dot: 4, seq: 590, bug: { r: "14", c: "2:57" }, cover: false, scan: true,
      board: { state: "recheck", mark: "recheck", word: "recheck", score: null, meta: "— · —:—" }, reads: [0, 9], stamp: "0/9",
      line: "14 – 10 → <b>14 – 14</b> · not a football step",
      step: "14–10 to 14–14 is a suspicious jump. It needs 9 reads over 2 s." },
    { key: "recheck-1", bug: { c: "2:57" }, t: 10900, dot: 4, seq: 594, scan: true, reads: [1, 9], stamp: "1/9", line: "recheck 1/9 → <b>14 · 14 · 2nd · 2:57</b>" },
    { key: "recheck-2", bug: { c: "2:56" }, t: 11300, dot: 4, seq: 598, scan: true, reads: [2, 9], stamp: "2/9", line: "recheck 2/9 → <b>14 · 14 · 2nd · 2:56</b>" },
    { key: "recheck-3", bug: { c: "2:56" }, t: 11700, dot: 4, seq: 602, scan: true, reads: [3, 9], stamp: "3/9", line: "recheck 3/9 → <b>14 · 14 · 2nd · 2:56</b>" },
    { key: "recheck-4", bug: { c: "2:55" }, t: 12100, dot: 4, seq: 606, scan: true, reads: [4, 9], stamp: "4/9", line: "recheck 4/9 → <b>14 · 14 · 2nd · 2:55</b>" },
    { key: "reset", t: 12700, dot: 5, seq: 611, bug: { r: "", c: "" }, scan: false,
      board: DARK_BOARD, reads: [0, 9], stamp: "0/9",
      line: "blank read → <b>run resets</b>",
      step: "A blank read resets the run. The board stays dark instead of guessing." },
    { key: "fade", t: 14900, fade: true }
  ];
  var SETTLED = 4; /* locked */

  function beatAt(ms) {
    var x = ms % LOOP;
    if (x < 0) x += LOOP;
    var idx = 0;
    for (var i = 0; i < BEATS.length; i++) if (BEATS[i].t <= x) idx = i;
    return idx;
  }

  function reduceQuery() {
    return typeof window !== "undefined" && window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  function restart(node, cls) {
    if (!node) return;
    node.classList.remove(cls);
    void node.offsetWidth;
    node.classList.add(cls);
  }

  function mountReadStage(stage, reduce) {
    function q(sel) { return stage.querySelector(sel); }
    var n = {
      seq: q("[data-seq]"), l: q("[data-bug-l]"), r: q("[data-bug-r]"), qtr: q("[data-bug-q]"), c: q("[data-bug-c]"),
      cover: q("[data-cover]"), scan: q("[data-scan]"), bug: q("[data-bug]"), pulse: q("[data-pulse]"),
      line: q("[data-readline]"), iris: q("[data-iris]"), board: q("[data-board]"), mark: q("[data-mark]"),
      stamp: q("[data-stamp]"), score: q("[data-score]"), meta: q("[data-meta]"), reads: q("[data-reads]"),
      step: q("[data-step]"), dots: stage.querySelectorAll("[data-dots] i")
    };
    var timers = [];
    var state = { bug: { l: BUG.l, r: BUG.r, q: BUG.q, c: "" }, reads: [-1, -1], board: null };

    function setReads(on, of, animate) {
      if (!n.reads) return;
      var cells = n.reads.querySelectorAll("i");
      if (cells.length !== of) {
        var label = n.reads.querySelector("span");
        n.reads.textContent = "";
        for (var i = 0; i < of; i++) n.reads.appendChild(el("i"));
        if (label) n.reads.appendChild(label);
        cells = n.reads.querySelectorAll("i");
        state.reads = [0, of];
      }
      n.reads.classList.toggle("is-nine", of === 9);
      for (var k = 0; k < cells.length; k++) {
        var was = cells[k].classList.contains("on");
        cells[k].classList.toggle("on", k < on);
        cells[k].classList.remove("is-new");
        if (animate && !was && k < on) { void cells[k].offsetWidth; cells[k].classList.add("is-new"); }
      }
      var label2 = n.reads.querySelector("span");
      if (label2) label2.textContent = on + " of " + of + (of === 9 ? " (recheck)" : " match");
      state.reads = [on, of];
    }

    function setBoard(b, animate) {
      if (!b || !n.board) return;
      var was = state.board;
      n.board.className = "q-board is-" + b.state;
      if (animate && b.state === "locked" && was !== "locked") { void n.board.offsetWidth; n.board.classList.add("is-new"); }
      n.mark.className = "mark " + b.mark;
      n.mark.textContent = b.word;
      n.score.innerHTML = b.score ? b.score[0] + "<i>–</i>" + b.score[1] : "□<i>–</i>□";
      n.meta.textContent = b.meta;
      state.board = b.state;
    }

    function apply(beat, animate) {
      stage.setAttribute("data-state", beat.key);
      if (beat.fade) { stage.classList.add("is-fading"); return; }
      stage.classList.remove("is-fading");
      if (beat.bug) {
        for (var k in beat.bug) if (Object.prototype.hasOwnProperty.call(beat.bug, k)) state.bug[k] = beat.bug[k];
        if (beat.key === "dark") { state.bug.l = BUG.l; state.bug.r = BUG.r; state.bug.q = BUG.q; }
        if (beat.key === "reset") { state.bug.l = ""; state.bug.q = ""; }
        n.l.textContent = state.bug.l; n.r.textContent = state.bug.r; n.qtr.textContent = state.bug.q; n.c.textContent = state.bug.c;
      }
      if (n.seq && beat.seq) n.seq.textContent = "f " + ("0000" + beat.seq).slice(-4);
      if (typeof beat.cover === "boolean") stage.classList.toggle("is-doubt", beat.cover);
      if (beat.board) setBoard(beat.board, animate);
      var st = state.board;
      stage.classList.toggle("is-reading", st === "reading");
      stage.classList.toggle("is-recheck", st === "recheck");
      stage.classList.toggle("is-locked", st === "locked");
      if (typeof beat.iris === "boolean" && n.iris) n.iris.classList.toggle("is-open", beat.iris);
      if (beat.reads) setReads(beat.reads[0], beat.reads[1], animate);
      if (beat.stamp != null && n.stamp) {
        var changed = n.stamp.textContent !== beat.stamp;
        n.stamp.textContent = beat.stamp;
        if (animate && changed) restart(n.stamp, "is-new");
      }
      if (beat.line != null && n.line) n.line.innerHTML = beat.line;
      if (beat.step && n.step) n.step.textContent = beat.step;
      if (beat.dot != null) for (var d = 0; d < n.dots.length; d++) n.dots[d].classList.toggle("on", d <= beat.dot);
      if (animate && beat.scan) {
        if (n.scan && n.bug) n.scan.style.setProperty("--scan-x", Math.round(n.bug.getBoundingClientRect().width - 3) + "px");
        restart(n.scan, "is-sweep");
        restart(n.pulse, "is-pulse");
      }
    }

    function clear() { while (timers.length) clearTimeout(timers.pop()); }
    function run() {
      clear();
      BEATS.forEach(function (beat) {
        timers.push(setTimeout(function () { apply(beat, true); }, beat.t));
      });
      timers.push(setTimeout(run, LOOP));
    }
    function still() {
      clear();
      /* Rebuild the settled LOCKED frame from the top so state is consistent. */
      for (var i = 0; i <= SETTLED; i++) apply(BEATS[i], false);
      if (n.scan) n.scan.classList.remove("is-sweep");
      if (n.pulse) n.pulse.classList.remove("is-pulse");
      if (n.board) n.board.classList.remove("is-new");
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
    ".contrast-pair", ".q-legend", ".q-rules", ".sidecar-row", ".steps", ".package", ".split-two",
    ".glasses", ".community", ".checklist", ".q-opener-facts"
  ];
  var REVEAL_SINGLES = [
    ".section-head", ".section .holo-plinth", ".faq", ".notice", ".q-band", ".q-cta",
    ".essay article", ".trace-main > .wrap > .card"
  ];

  function mountReveal(reduce) {
    if ((reduce && reduce.matches) || typeof IntersectionObserver === "undefined") return;
    var g, k, kids;
    var groups = document.querySelectorAll(REVEAL_GROUPS.join(","));
    for (g = 0; g < groups.length; g++) {
      kids = groups[g].children;
      for (k = 0; k < kids.length; k++) {
        kids[k].setAttribute("data-reveal", "");
        kids[k].style.setProperty("--d", (k * 70) + "ms");
      }
    }
    var singles = document.querySelectorAll(REVEAL_SINGLES.join(","));
    for (g = 0; g < singles.length; g++) singles[g].setAttribute("data-reveal", "");

    var items = document.querySelectorAll("[data-reveal]");
    if (!items.length) return;
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (entry) {
        if (!entry.isIntersecting) return;
        var t = entry.target;
        io.unobserve(t);
        t.classList.add("is-in");
        /* Hand the element back to its normal styles afterwards. */
        t.addEventListener("animationend", function done(ev) {
          if (ev.target !== t) return;
          t.removeEventListener("animationend", done);
          t.removeAttribute("data-reveal");
          t.classList.remove("is-in");
        });
      });
    }, { rootMargin: "0px 0px -6% 0px", threshold: 0.08 });
    for (var i = 0; i < items.length; i++) io.observe(items[i]);
    if (reduce && typeof reduce.addEventListener === "function") {
      reduce.addEventListener("change", function () {
        if (reduce.matches) document.documentElement.classList.remove("q-motion");
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

  /* Phones: the nav is one swipeable row; keep the current page in view. */
  function mountNav() {
    var nav = document.querySelector("[data-nav]");
    if (!nav) return;
    var cur = nav.querySelector('[aria-current="page"]');
    if (cur && nav.scrollWidth > nav.clientWidth) {
      nav.scrollLeft = Math.max(0, cur.offsetLeft - (nav.clientWidth - cur.offsetWidth) / 2);
    }
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
        leaves.forEach(function (node) { node.classList.add("is-open"); });
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

  /* Anchor jumps land below the sticky header, whatever height it wraps to
     (on phones the header scrolls away, so only a small gap is kept). */
  function mountScrollPadding() {
    var header = document.querySelector(".holo-header");
    if (!header) return;
    function set() {
      var sticky = getComputedStyle(header).position === "sticky";
      document.documentElement.style.scrollPaddingTop = (sticky ? Math.ceil(header.getBoundingClientRect().height + 16) : 16) + "px";
    }
    set();
    if (typeof ResizeObserver !== "undefined") new ResizeObserver(set).observe(header);
    else window.addEventListener("resize", set);
  }

  /* Page-wide: every CSS loop holds still while the tab is hidden. */
  function mountHiddenFlag() {
    var root = document.documentElement;
    function flag() { root.classList.toggle("is-tab-hidden", !!document.hidden); }
    document.addEventListener("visibilitychange", flag);
    flag();
  }

  function boot() {
    if (redirectLegacyHash()) return;
    mountHiddenFlag();
    mountScrollPadding();
    var reduce = reduceQuery();
    if (!(reduce && reduce.matches)) document.documentElement.classList.add("q-motion");
    mountNav();
    mountCopy();
    mountCodeWrap();
    mountShutter();
    var stage = document.querySelector("[data-read-stage]");
    if (stage) mountReadStage(stage, reduce);
    mountReveal(reduce);
  }

  return {
    LOOP: LOOP,
    beatAt: beatAt,
    read: {
      BEATS: BEATS.map(function (b) { return { key: b.key, t: b.t }; }),
      SETTLED: SETTLED,
      raw: BEATS
    },
    boot: boot
  };
});
