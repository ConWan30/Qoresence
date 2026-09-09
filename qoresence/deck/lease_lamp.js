/* DeckLeaseLamp — subscribe-not-own chrome. Hidden unless /health says enabled. */
(function () {
  if (window.__qoreLeaseLamp) return;
  window.__qoreLeaseLamp = true;

  var PLANE = "qoresence-observation";
  var FLAG = "deck_lease_lamp";

  function ensureEl() {
    var el = document.getElementById("deckLeaseLamp");
    if (el) return el;
    el = document.createElement("div");
    el.id = "deckLeaseLamp";
    el.hidden = true;
    el.setAttribute("data-plane", PLANE);
    el.setAttribute("data-lamp", "off");
    el.setAttribute("data-flag", FLAG);
    el.setAttribute("aria-label", "Deck lease lamp");
    el.innerHTML =
      '<span class="dll-dot" aria-hidden="true"></span>' +
      '<span class="dll-text" id="deckLeaseLampText">LEASE OFF</span>';
    var host =
      document.getElementById("cmd") ||
      document.querySelector("header") ||
      document.body;
    host.appendChild(el);
    return el;
  }

  function ensureStyle() {
    if (document.getElementById("deckLeaseLampStyle")) return;
    var s = document.createElement("style");
    s.id = "deckLeaseLampStyle";
    s.textContent =
      "#deckLeaseLamp{display:inline-flex;align-items:center;gap:8px;min-height:28px;padding:6px 10px;border:1px solid rgba(155,231,255,.22);border-radius:8px;background:rgba(5,6,10,.72);color:#8b90a0;font:700 10px/1 IBM Plex Mono,ui-monospace,monospace;letter-spacing:.08em;text-transform:uppercase}" +
      "#deckLeaseLamp[hidden]{display:none!important}" +
      "#deckLeaseLamp .dll-dot{width:8px;height:8px;border-radius:50%;background:#5b6070;box-shadow:none}" +
      "#deckLeaseLamp[data-lamp=dark]{color:#8b90a0;border-color:rgba(139,144,160,.28)}" +
      "#deckLeaseLamp[data-lamp=dark] .dll-dot{background:#5b6070}" +
      "#deckLeaseLamp[data-lamp=on]{color:#9be7ff;border-color:rgba(155,231,255,.55)}" +
      "#deckLeaseLamp[data-lamp=on] .dll-dot{background:#9be7ff;box-shadow:0 0 10px rgba(155,231,255,.55)}";
    document.head.appendChild(s);
  }

  function paint(health) {
    var el = ensureEl();
    var text = document.getElementById("deckLeaseLampText");
    el.setAttribute("data-plane", PLANE);
    el.setAttribute("data-flag", FLAG);
    var lamp = health && health.deck_lease_lamp;
    if (!lamp || !lamp.enabled) {
      el.hidden = true;
      el.setAttribute("data-lamp", "off");
      el.setAttribute("data-lease-ok", "false");
      el.setAttribute("data-subscribed", "false");
      if (text) text.textContent = "LEASE OFF";
      return;
    }
    var state = lamp.lamp === "on" ? "on" : "dark";
    el.hidden = false;
    el.setAttribute("data-lamp", state);
    el.setAttribute("data-lease-ok", lamp.lease_ok ? "true" : "false");
    el.setAttribute("data-subscribed", lamp.subscribed ? "true" : "false");
    el.setAttribute("data-owner", String(lamp.owner || ""));
    el.setAttribute("data-pid", String(lamp.pid || 0));
    el.setAttribute("data-device", String(lamp.device || ""));
    var bits = [];
    if (state === "on") bits.push("LEASE ON");
    else bits.push("LEASE DARK");
    if (lamp.owner) bits.push(String(lamp.owner));
    if (lamp.pid) bits.push("pid " + lamp.pid);
    if (lamp.device) bits.push(String(lamp.device));
    if (lamp.subscribed) bits.push("subscribed");
    else bits.push("subscribe missing");
    if (lamp.age_s != null) bits.push("age " + lamp.age_s + "s");
    if (lamp.frames != null) bits.push("frames " + lamp.frames);
    if (text) text.textContent = bits.join(" · ");
  }

  function tick() {
    fetch("/health", { cache: "no-store" })
      .then(function (r) {
        return r.json();
      })
      .then(paint)
      .catch(function () {
        paint(null);
      });
  }

  ensureStyle();
  ensureEl();
  tick();
  setInterval(tick, 1500);
})();
