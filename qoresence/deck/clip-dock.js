/* HDMI clip dock — click a clip to REPLAY on the stage, LIVE returns to HDMI. */
(function () {
  if (window.__qoreClipDock) return;
  window.__qoreClipDock = true;

  function el(html) {
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  function mediaHref(raw) {
    const s = String(raw || "").trim();
    if (!s) return "";
    if (/^https?:\/\//i.test(s) && s.indexOf("/media/clips/") >= 0) {
      try {
        return new URL(s).pathname;
      } catch (e) {
        return "";
      }
    }
    if (s.indexOf("/media/clips/") === 0) return s.split("?")[0];
    const m = s.replace(/\\/g, "/").match(/hdmi_clip_[\w.\-]+\.(mp4|avi)/i);
    return m ? "/media/clips/" + m[0] : "";
  }

  window.qoreClipHref = mediaHref;

  const player = el(
    '<div id="qore-clip-player" data-qore-clip-dock="player">' +
      '<div class="hud">' +
      '<button type="button" class="back" data-action="live">← LIVE feed</button>' +
      '<span class="label" data-label>REPLAY</span></div>' +
      "<video controls playsinline></video></div>",
  );
  const dock = el(
    '<div id="qore-clip-dock" data-qore-clip-dock="bar">' +
      '<div class="row">' +
      '<button type="button" class="live" data-action="live">LIVE feed</button>' +
      '<button type="button" class="replay" data-action="replay">REPLAY last</button>' +
      '<button type="button" class="make" data-action="clip">▶ Clip 30s</button>' +
      '<button type="button" class="toggle" data-action="toggle">Clips</button>' +
      '<span class="meta" data-count>00</span></div>' +
      '<div class="tiles" data-tiles></div></div>',
  );

  const video = player.querySelector("video");
  const tiles = dock.querySelector("[data-tiles]");
  const count = dock.querySelector("[data-count]");
  const makeBtn = dock.querySelector("[data-action=clip]");
  const label = player.querySelector("[data-label]");
  let lastHref = "";
  let lastName = "";

  function findStage() {
    return (
      document.querySelector("[data-stage-mode]") ||
      document.querySelector("#playerWrap") ||
      document.querySelector("img[data-hdmi-keep]") &&
        document.querySelector("img[data-hdmi-keep]").closest("div.relative, section")
    );
  }

  function attachPlayer() {
    const stage = findStage();
    if (stage) {
      const cs = window.getComputedStyle(stage);
      if (cs.position === "static") stage.style.position = "relative";
      if (player.parentElement !== stage) stage.appendChild(player);
      player.setAttribute("data-on-stage", "1");
    } else if (!player.parentElement) {
      document.body.appendChild(player);
    }
  }

  function glassOwnsStage() {
    return Boolean(document.querySelector('[data-clip-owner="hdmi-stage"]'));
  }

  function standDown() {
    try {
      video.pause();
    } catch (e) {}
    video.removeAttribute("src");
    try {
      video.load();
    } catch (e) {}
    player.classList.remove("on");
    player.remove();
    dock.remove();
    document.body.classList.remove("qore-has-clip-dock", "qore-replay");
  }

  function mount() {
    if (!document.body) return;
    if (glassOwnsStage()) {
      standDown();
      return;
    }
    if (!document.getElementById("qore-clip-dock")) {
      document.body.appendChild(dock);
      document.body.classList.add("qore-has-clip-dock");
    }
    attachPlayer();
  }

  function goLive() {
    player.classList.remove("on");
    document.body.classList.remove("qore-replay");
    const stage = findStage();
    if (stage) stage.setAttribute("data-stage-mode", "live");
    try {
      video.pause();
    } catch (e) {}
    video.removeAttribute("src");
    try {
      video.load();
    } catch (e) {}
    count.textContent =
      "LIVE · HDMI clips · " + String(tiles.querySelectorAll(".tile").length).padStart(2, "0");
  }

  function playClip(url, name) {
    if (glassOwnsStage()) {
      standDown();
      return;
    }
    const href = mediaHref(url) || url;
    if (!href || href.indexOf("/media/clips/") !== 0) return;
    attachPlayer();
    lastHref = href;
    lastName = name || href.split("/").pop() || "clip";
    const src = href + (href.indexOf("?") >= 0 ? "&" : "?") + "v=" + Date.now();
    video.src = src;
    player.classList.add("on");
    document.body.classList.add("qore-replay");
    const stage = findStage();
    if (stage) stage.setAttribute("data-stage-mode", "replay");
    label.textContent = "REPLAY · " + lastName;
    const go = function () {
      video.play().catch(function () {});
    };
    if (video.readyState >= 2) go();
    else
      video.oncanplay = function () {
        video.oncanplay = null;
        go();
      };
    count.textContent = "REPLAY · " + lastName;
  }

  function render(clips) {
    const list = Array.isArray(clips) ? clips : [];
    if (!player.classList.contains("on")) {
      count.textContent = "HDMI clips · " + String(list.length).padStart(2, "0");
    }
    tiles.innerHTML = "";
    if (!list.length) {
      const p = document.createElement("p");
      p.className = "meta";
      p.textContent = "No hdmi_clip_*.mp4 yet — tap Make HDMI Clip";
      tiles.appendChild(p);
      return;
    }
    list.slice(0, 20).forEach(function (c) {
      const href = mediaHref(c.url || c.href || c.path || c.name);
      if (!href) return;
      const name = c.name || href.split("/").pop() || "clip";
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tile";
      b.setAttribute("data-clip-href", href);
      b.setAttribute("data-clip-name", name);
      const m = name.match(/hdmi_clip_(\d{8})_(\d{6})/i);
      const stamp = m
        ? m[2].slice(0, 2) + ":" + m[2].slice(2, 4) + ":" + m[2].slice(4, 6)
        : "▶";
      b.textContent = "▶ " + stamp;
      b.onclick = function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        playClip(href, name);
      };
      tiles.appendChild(b);
    });
  }

  function hydratePaths() {
    const re = /hdmi_clip_[\w.\-]+\.(mp4|avi)/i;
    const nodes = document.querySelectorAll("article, button, p, span, li, div");
    for (let i = 0; i < nodes.length && i < 400; i++) {
      const n = nodes[i];
      if (n.closest("#qore-clip-dock, #qore-clip-player")) continue;
      if (n.getAttribute("data-qore-hydrated") === "1") continue;
      const text = (n.textContent || "").trim();
      if (!re.test(text) || text.length > 240) continue;
      const href = mediaHref(text);
      if (!href) continue;
      n.setAttribute("data-qore-hydrated", "1");
      n.setAttribute("data-clip-href", href);
      n.style.cursor = "pointer";
      if (!/\bplay\b/i.test(text)) {
        const hint = document.createElement("span");
        hint.className = "qore-play-hint";
        hint.textContent = " ▶ Replay";
        n.appendChild(hint);
      }
    }
  }

  async function refresh() {
    if (glassOwnsStage()) {
      standDown();
      return;
    }
    try {
      const r = await fetch("/api/clips", { cache: "no-store" });
      const j = await r.json();
      render(j && j.clips ? j.clips : []);
    } catch (e) {
      /* Deck down */
    }
    hydratePaths();
    attachPlayer();
  }

  async function makeClip() {
    if (glassOwnsStage()) {
      standDown();
      return;
    }
    makeBtn.disabled = true;
    const prev = makeBtn.textContent;
    makeBtn.textContent = "Encoding…";
    try {
      const r = await fetch("/api/clip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seconds: 30 }),
      });
      const j = await r.json();
      if (j && j.ok && j.clip && j.clip.url) {
        playClip(j.clip.url, j.clip.name);
        void refresh();
      } else {
        count.textContent = (j && j.error) || "clip failed";
      }
    } catch (e) {
      count.textContent = "clip error";
    } finally {
      makeBtn.disabled = false;
      makeBtn.textContent = prev;
    }
  }

  dock.addEventListener("click", function (ev) {
    const t = ev.target.closest("[data-action]");
    if (!t) return;
    if (t.getAttribute("data-action") === "live") goLive();
    if (t.getAttribute("data-action") === "replay") playClip(lastHref, lastName);
    if (t.getAttribute("data-action") === "clip") void makeClip();
    if (t.getAttribute("data-action") === "toggle") dock.classList.toggle("open");
  });
  player.querySelector("[data-action=live]").onclick = function (ev) {
    ev.preventDefault();
    goLive();
  };

  document.addEventListener(
    "click",
    function (ev) {
      if (glassOwnsStage()) return;
      if (ev.target.closest("#qore-clip-dock, #qore-clip-player")) return;
      const hit = ev.target.closest("[data-clip-href]");
      if (hit) {
        const href = mediaHref(hit.getAttribute("data-clip-href"));
        if (href) {
          ev.preventDefault();
          ev.stopPropagation();
          playClip(href, hit.getAttribute("data-clip-name") || "");
        }
        return;
      }
      const href = mediaHref((ev.target.textContent || "").trim());
      if (href && /hdmi_clip/i.test(ev.target.textContent || "")) {
        ev.preventDefault();
        ev.stopPropagation();
        playClip(href);
      }
    },
    true,
  );

  window.addEventListener("keydown", function (e) {
    if (glassOwnsStage()) return;
    const tag = e.target && e.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA") return;
    if (e.key === "c" || e.key === "C") {
      e.preventDefault();
      if (!makeBtn.disabled) void makeClip();
    }
    if (e.key === "l" || e.key === "L") {
      e.preventDefault();
      goLive();
    }
    if (e.key === "r" || e.key === "R") {
      e.preventDefault();
      if (lastHref) playClip(lastHref, lastName);
    }
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
  void refresh();
  [50, 150, 400, 800].forEach(function (ms) {
    window.setTimeout(refresh, ms);
  });
  setInterval(refresh, 2000);
})();
