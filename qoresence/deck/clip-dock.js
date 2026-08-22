/* HDMI clip dock — vanilla, always on top of Theater glass. */
(function () {
  if (window.__qoreClipDock) return;
  window.__qoreClipDock = true;

  function el(html) {
    const t = document.createElement("template");
    t.innerHTML = html.trim();
    return t.content.firstElementChild;
  }

  const player = el(
    '<div id="qore-clip-player" data-qore-clip-dock="player">' +
      '<button type="button" class="back" data-action="live">LIVE</button>' +
      "<video controls playsinline></video></div>",
  );
  const dock = el(
    '<div id="qore-clip-dock" data-qore-clip-dock="bar">' +
      '<div class="row">' +
      '<button type="button" class="live" data-action="live">LIVE</button>' +
      '<button type="button" class="make" data-action="clip">▶ Make HDMI Clip (30s)</button>' +
      '<span class="meta" data-count>HDMI clips · 00</span></div>' +
      '<div class="tiles" data-tiles></div></div>',
  );

  function mount() {
    if (!document.body) return;
    if (!document.getElementById("qore-clip-player")) document.body.appendChild(player);
    if (!document.getElementById("qore-clip-dock")) document.body.appendChild(dock);
  }

  const video = player.querySelector("video");
  const tiles = dock.querySelector("[data-tiles]");
  const count = dock.querySelector("[data-count]");
  const makeBtn = dock.querySelector("[data-action=clip]");

  function goLive() {
    player.classList.remove("on");
    try {
      video.pause();
    } catch (e) {}
    video.removeAttribute("src");
  }

  function playClip(url, name) {
    if (!url) return;
    const src = url + (url.indexOf("?") >= 0 ? "&" : "?") + "v=" + Date.now();
    video.src = src;
    player.classList.add("on");
    const go = function () {
      video.play().catch(function () {});
    };
    if (video.readyState >= 2) go();
    else video.oncanplay = function () {
      video.oncanplay = null;
      go();
    };
    count.textContent = "REPLAY · " + (name || url.split("/").pop() || "clip");
  }

  function render(clips) {
    const list = Array.isArray(clips) ? clips : [];
    count.textContent = "HDMI clips · " + String(list.length).padStart(2, "0");
    tiles.innerHTML = "";
    if (!list.length) {
      const p = document.createElement("p");
      p.className = "meta";
      p.textContent = "No hdmi_clip_*.mp4 yet — tap Make HDMI Clip";
      tiles.appendChild(p);
      return;
    }
    list.slice(0, 20).forEach(function (c) {
      const href = c.url || c.href || (c.name ? "/media/clips/" + c.name : "");
      const name = c.name || (href.split("/").pop() || "clip");
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tile";
      b.setAttribute("data-clip-href", href);
      b.setAttribute("data-clip-name", name);
      b.innerHTML =
        '<span class="go">▶</span><span>' +
        name.replace(/[<>]/g, "") +
        "</span>";
      b.onclick = function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        playClip(href, name);
      };
      tiles.appendChild(b);
    });
  }

  async function refresh() {
    try {
      const r = await fetch("/api/clips", { cache: "no-store" });
      const j = await r.json();
      render(j && j.clips ? j.clips : []);
    } catch (e) {
      /* Deck down */
    }
  }

  async function makeClip() {
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
    if (t.getAttribute("data-action") === "clip") void makeClip();
  });
  player.querySelector("[data-action=live]").onclick = goLive;

  window.addEventListener("keydown", function (e) {
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
  });

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
  void refresh();
  setInterval(refresh, 2000);
})();
