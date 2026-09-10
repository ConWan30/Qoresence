/* Recap notary door — separate file so Theater JS stays untouched. */
(function () {
  const params = new URLSearchParams(location.search);
  const ALLOWED = [
    "bodied_locked",
    "unbodied_locked",
    "bodied_unlocked",
    "empty_not_persisted",
    "empty_persisted",
  ];
  const requested = params.get("fixture") || "";
  const fixture = requested && ALLOWED.indexOf(requested) >= 0 ? requested : "";
  const sessionId = params.get("session_id") || params.get("session") || "";

  function downloadJson(name, obj) {
    const blob = new Blob([JSON.stringify(obj, null, 2) + "\n"], { type: "application/json" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = name;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  function setDoorStatus(text) {
    const el = document.getElementById("notary-status");
    if (el) el.textContent = text;
  }

  function setDoorHash(commit) {
    const el = document.getElementById("notary-hash");
    if (el) el.textContent = commit ? "clock " + commit : "clock —";
  }

  function qs() {
    const q = new URLSearchParams();
    if (fixture) q.set("fixture", fixture);
    if (sessionId) q.set("session_id", sessionId);
    return q.toString() ? "?" + q.toString() : "";
  }

  async function exportRecapDoor() {
    const r = await fetch("/api/session/clock-notary" + qs());
    const body = await r.json();
    window.__notaryEnvelope = body;
    setDoorHash(body.clock_commitment || "");
    if (!body.ok) {
      setDoorStatus("export refused: " + (body.error || body.reason || "no session"));
      return body;
    }
    downloadJson("observation-envelope.json", body);
    setDoorStatus("exported UNSEALED · " + (body.clock_commitment || ""));
    return body;
  }

  async function sealRecapDoor() {
    let env = window.__notaryEnvelope;
    if (!env || !env.clock_commitment) env = await exportRecapDoor();
    const gamer = (document.getElementById("notary-gamer") || {}).value || "";
    const purpose = (document.getElementById("notary-purpose") || {}).value || "portcert";
    const wallet = (document.getElementById("notary-wallet") || {}).value || "";
    const phrase = (document.getElementById("notary-phrase") || {}).value || "";
    const r = await fetch("/api/session/clock-notary/seal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        envelope: env,
        gamer: gamer,
        signed_by: gamer,
        purpose: purpose,
        wallet: wallet,
        phrase: phrase,
        granted: true,
      }),
    });
    const body = await r.json();
    window.__notaryWrap = body;
    setDoorHash(body.clock_commitment || (env && env.clock_commitment) || "");
    if (!body.ok) {
      setDoorStatus("REFUSED · " + (body.reason || "") + " · " + (body.hint || ""));
      return;
    }
    downloadJson("notary-wrap.json", body.wrap || body);
    setDoorStatus((body.discord_card || "SEALED") + "\nchain " + (body.chain || "paused"));
  }

  async function verifyRecapDoor() {
    const env = window.__notaryEnvelope;
    const wrap = window.__notaryWrap;
    if (!env || !wrap) {
      setDoorStatus("export and seal first");
      return;
    }
    const r = await fetch("/api/session/clock-notary/verify", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ envelope: env, wrap: wrap }),
    });
    const body = await r.json();
    const lines = (body.checks || []).map(function (c) {
      return (c.ok ? "PASS " : "FAIL ") + c.name + (c.detail ? " · " + c.detail : "");
    });
    setDoorStatus((body.ok ? "VERIFIED " : "UNTRUSTED ") + body.passed + "/" + body.total + "\n" + lines.join("\n"));
  }

  function copyText(text) {
    if (!text) return;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text);
      return;
    }
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }

  function bind(id, fn) {
    const el = document.getElementById(id);
    if (el) el.addEventListener("click", function () { fn().catch(function (err) { setDoorStatus(String(err)); }); });
  }

  bind("btn-export-recap", exportRecapDoor);
  bind("btn-seal-recap", sealRecapDoor);
  bind("btn-verify-wrap", verifyRecapDoor);
  const copyHashBtn = document.getElementById("btn-copy-hash");
  if (copyHashBtn) copyHashBtn.addEventListener("click", function () {
    const commit = window.__notaryEnvelope && window.__notaryEnvelope.clock_commitment;
    copyText(commit || "");
    setDoorStatus(commit ? "hash copied" : "export first");
  });
  const copyCardBtn = document.getElementById("btn-copy-card");
  if (copyCardBtn) copyCardBtn.addEventListener("click", function () {
    const card = window.__notaryWrap && window.__notaryWrap.discord_card;
    copyText(card || "");
    setDoorStatus(card ? "Discord card copied" : "seal first");
  });
})();
