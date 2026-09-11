/* Recap observation export — separate file so Theater JS stays untouched. */
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
    setDoorStatus("exported · eyes only · " + (body.clock_commitment || ""));
    return body;
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
  const copyHashBtn = document.getElementById("btn-copy-hash");
  if (copyHashBtn) copyHashBtn.addEventListener("click", function () {
    const commit = window.__notaryEnvelope && window.__notaryEnvelope.clock_commitment;
    copyText(commit || "");
    setDoorStatus(commit ? "hash copied" : "export first");
  });
})();
