/* Session Theater — render a fail-closed view model. Digits only via lockedValue(). */
(function () {
  const PRESS = { press_to_score: 1, spam_window: 1 };

  function formatTimestamp(clockNs) {
    const ms = Math.max(0, Math.floor(Number(clockNs || 0) / 1e6));
    let minutes = Math.floor(ms / 60000);
    const rem = ms % 60000;
    const seconds = Math.floor(rem / 1000);
    const millis = rem % 1000;
    const hours = Math.floor(minutes / 60);
    minutes = minutes % 60;
    const pad = (n, w) => String(n).padStart(w, "0");
    if (hours) return pad(hours, 2) + ":" + pad(minutes, 2) + ":" + pad(seconds, 2) + "." + pad(millis, 3);
    return pad(minutes, 2) + ":" + pad(seconds, 2) + "." + pad(millis, 3);
  }

  function intOrNull(v) {
    if (v === null || v === undefined || v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) ? Math.trunc(n) : null;
  }

  function scoreOf(sit, locked) {
    if (!locked || !sit) return null;
    const home = intOrNull(sit.home_score);
    const away = intOrNull(sit.away_score);
    if (home === null || away === null) return null;
    return { home: home, away: away };
  }

  function qualification(type, locked, bodied) {
    if (PRESS[type] && (!bodied || !locked)) return "suppressed";
    if (type === "situation_shift" && !locked) return "suppressed";
    return locked ? "confirmed" : "unavailable";
  }

  function normalizeEvent(raw, locked, bodied) {
    const sit = raw && raw.situation_summary && typeof raw.situation_summary === "object"
      ? raw.situation_summary
      : raw && raw.situation && typeof raw.situation === "object"
        ? raw.situation
        : null;
    const inp = raw && raw.input_summary && typeof raw.input_summary === "object"
      ? raw.input_summary
      : raw && raw.input && typeof raw.input === "object"
        ? raw.input
        : null;
    const ev = raw && raw.evidence && typeof raw.evidence === "object" ? raw.evidence : {};
    const type = String((raw && raw.event_type) || "unknown");
    const t0 = intOrNull(raw && raw.t_start_ns) || 0;
    const input = {};
    if (inp) {
      if (inp.latency_ns != null) input.latency_ns = intOrNull(inp.latency_ns);
      if (inp.count != null) input.count = intOrNull(inp.count);
      if (inp.press_clock_ns != null) input.press_clock_ns = intOrNull(inp.press_clock_ns);
      if (bodied && inp.button) input.button = String(inp.button);
    }
    return {
      event_id: String((raw && raw.event_id) || ""),
      event_type: type,
      session_id: String((raw && raw.session_id) || ""),
      t_start_ns: t0,
      timestamp: formatTimestamp(t0),
      state: locked ? "locked" : "unlocked",
      bodied: !!bodied,
      score: scoreOf(sit, locked),
      yard_line: locked ? intOrNull(sit && sit.yard_line) : null,
      input: Object.keys(input).length ? input : null,
      coach_context: { available: !!ev.coach_type, coach_type: ev.coach_type || null },
      clip_ids: (ev.clip_ids || []).map(String).filter(Boolean),
      qualification: qualification(type, locked, bodied),
    };
  }

  function normalizePack(pack) {
    const raw = pack && typeof pack === "object" ? pack : {};
    const locked = !!raw.board_locked;
    const bodied = !!raw.controller_bodied;
    const events = (Array.isArray(raw.events) ? raw.events : [])
      .filter((e) => e && typeof e === "object")
      .map((e) => normalizeEvent(e, locked, bodied));
    events.sort((a, b) => a.t_start_ns - b.t_start_ns || String(a.event_id).localeCompare(String(b.event_id)));
    const persisted = !!(raw.persisted || raw.path);
    let confirmed = { available: false, score: null, yard_line: null };
    if (locked) {
      for (const e of events) {
        if (e.score) confirmed.score = e.score;
        if (e.yard_line != null) confirmed.yard_line = e.yard_line;
      }
      confirmed.available = !!(confirmed.score || confirmed.yard_line != null);
    }
    let next = { kind: "awaiting", label: "Awaiting event", event_id: null };
    for (let i = events.length - 1; i >= 0; i--) {
      if (events[i].coach_context && events[i].coach_context.available) {
        next = { kind: "coach", label: "Coach · " + events[i].coach_context.coach_type, event_id: events[i].event_id };
        break;
      }
    }
    return {
      session_id: String(raw.session_id || ""),
      controller_bodied: bodied,
      board_locked: locked,
      persisted: persisted,
      events: events,
      confirmed: confirmed,
      current_moment: events.length ? events[events.length - 1] : null,
      next_signal: next,
      empty_reason: events.length ? null : persisted ? "no_events" : "not_persisted",
    };
  }

  function lockedValue(confirmed) {
    if (!confirmed || !confirmed.available) {
      return '<p class="UnavailableValue">Awaiting confirmed board state</p>';
    }
    const bits = [];
    const s = confirmed.score;
    if (s && s.home != null && s.away != null) {
      bits.push('<span class="LockedValue" data-kind="score">' + Number(s.home) + "–" + Number(s.away) + "</span>");
    }
    if (confirmed.yard_line != null) {
      bits.push('<span class="LockedValue" data-kind="yard">Yard ' + Number(confirmed.yard_line) + "</span>");
    }
    return bits.join("") || '<p class="UnavailableValue">Awaiting confirmed board state</p>';
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function cardHtml(ev) {
    const sitBits = [];
    if (ev.score) sitBits.push(ev.score.home + "–" + ev.score.away);
    if (ev.yard_line != null) sitBits.push("Yard " + ev.yard_line);
    const sit = sitBits.length
      ? '<div class="LockedValue" data-kind="card">' + escapeHtml(sitBits.join(" · ")) + "</div>"
      : "";
    const inp = ev.input || {};
    const inputBits = [];
    if (inp.latency_ns != null) inputBits.push("latency_ns=" + inp.latency_ns);
    if (inp.count != null) inputBits.push("count=" + inp.count);
    if (inp.button) inputBits.push("button=" + inp.button);
    const coach = ev.coach_context && ev.coach_context.available
      ? '<div class="CoachResult">Coach context · ' + escapeHtml(ev.coach_context.coach_type) + "</div>"
      : "";
    const clip = ev.clip_ids && ev.clip_ids.length
      ? '<div class="ClipLink">Clip ' + escapeHtml(ev.clip_ids.join(", ")) + "</div>"
      : "";
    return (
      '<article class="NarrativeCard" data-event-id="' + escapeHtml(ev.event_id) + '">' +
      "<header><span class=\"etype\">" + escapeHtml(ev.event_type) + "</span>" +
      '<span class="moment-time">' + escapeHtml(ev.timestamp) + "</span>" +
      '<span class="ConfidenceIndicator ' + escapeHtml(ev.qualification) + ' analyst-only">' +
      escapeHtml(ev.qualification) + "</span></header>" +
      sit +
      (inputBits.length ? "<div>" + escapeHtml(inputBits.join(" · ")) + "</div>" : "") +
      coach + clip +
      "</article>"
    );
  }

  function emptyCopy(reason) {
    if (reason === "not_persisted") return "Narrative log was not persisted for this session.";
    return "No narrative events occurred.";
  }

  function render(view, mode) {
    document.body.className = mode === "gamer" ? "gamer" : "analyst";
    document.getElementById("sid").textContent = "Session " + (view.session_id || "—");
    const live = document.getElementById("badge-live");
    live.textContent = "Fixture";
    live.className = "StateBadge on";
    const lock = document.getElementById("badge-lock");
    lock.textContent = view.board_locked ? "Locked" : "Unlocked";
    lock.className = "StateBadge" + (view.board_locked ? " on" : " warn");
    const body = document.getElementById("badge-body");
    body.textContent = view.controller_bodied ? "Bodied" : "Unbodied";
    body.className = "StateBadge" + (view.controller_bodied ? " on" : " warn");
    document.getElementById("clock").textContent = view.current_moment
      ? view.current_moment.timestamp
      : "00:00.000";
    document.getElementById("confirmed").innerHTML = lockedValue(view.confirmed);
    const moment = document.getElementById("moment");
    if (view.current_moment) {
      moment.innerHTML =
        '<div class="moment-type">' + escapeHtml(view.current_moment.event_type.replace(/_/g, " ")) + "</div>" +
        '<div class="moment-time">' + escapeHtml(view.current_moment.timestamp) + "</div>";
    } else {
      moment.innerHTML = '<p class="UnavailableValue">Awaiting event</p>';
    }
    document.getElementById("next").textContent = view.next_signal ? view.next_signal.label : "Awaiting event";
    const persist = document.getElementById("persist");
    persist.textContent = view.persisted ? "Narrative log persisted" : "Narrative log not persisted";
    persist.className = "PersistenceStatus analyst-only";
    const list = document.getElementById("stream");
    if (!view.events.length) {
      list.innerHTML = '<p class="empty">' + emptyCopy(view.empty_reason) + "</p>";
      return;
    }
    list.innerHTML = '<ol class="TimelineMarker">' + view.events.map((e) => "<li>" + cardHtml(e) + "</li>").join("") + "</ol>";
  }

  const ALLOWED = [
    "bodied_locked",
    "unbodied_locked",
    "bodied_unlocked",
    "empty_not_persisted",
    "empty_persisted",
  ];
  const params = new URLSearchParams(location.search);
  const requested = params.get("fixture") || "bodied_locked";
  const fixture = ALLOWED.indexOf(requested) >= 0 ? requested : "";
  const mode = params.get("mode") === "gamer" ? "gamer" : "analyst";

  document.querySelectorAll("[data-mode]").forEach((btn) => {
    btn.setAttribute("aria-pressed", btn.getAttribute("data-mode") === mode ? "true" : "false");
    btn.addEventListener("click", () => {
      const next = btn.getAttribute("data-mode");
      const u = new URL(location.href);
      u.searchParams.set("mode", next);
      history.replaceState({}, "", u);
      if (window.__view) render(window.__view, next);
    });
  });

  const sel = document.getElementById("fixture");
  if (sel && fixture) sel.value = fixture;

  function applyView(pack) {
    const view = normalizePack(pack);
    window.__view = view;
    render(view, mode);
  }

  if (!fixture) {
    applyView({ events: [], persisted: false, board_locked: false, controller_bodied: false });
  } else {
    fetch("/session_fixtures/" + encodeURIComponent(fixture) + ".json")
      .then((r) => {
        if (!r.ok) throw new Error("fixture");
        return r.json();
      })
      .then((pack) => applyView(pack))
      .catch(() => applyView({ events: [], persisted: false, board_locked: false, controller_bodied: false }));
  }
})();
