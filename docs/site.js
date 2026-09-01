(() => {
  const page = (location.pathname.split("/").pop() || "index.html") || "index.html";
  const isHome = page === "" || page === "index.html";
  const raw = (location.hash || "").replace(/^#/, "");
  const hashMap = {
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
    download: "install.html",
  };
  if (isHome && raw && hashMap[raw]) {
    location.replace(hashMap[raw]);
    return;
  }

  const menu = document.querySelector("[data-menu]");
  const nav = document.querySelector("[data-nav]");
  if (menu && nav) {
    menu.addEventListener("click", () => {
      const open = nav.classList.toggle("open");
      menu.setAttribute("aria-expanded", String(open));
    });
    nav.querySelectorAll("a").forEach((a) => {
      a.addEventListener("click", () => {
        nav.classList.remove("open");
        menu.setAttribute("aria-expanded", "false");
      });
    });
  }

  document.querySelectorAll("[data-copy]").forEach((button) => {
    button.addEventListener("click", async () => {
      const host = button.parentElement;
      const code = (host && host.dataset.code) || (host ? host.textContent : "").replace(/copy$/i, "").trim();
      try {
        await navigator.clipboard.writeText(code);
        button.textContent = "copied";
        setTimeout(() => {
          button.textContent = "copy";
        }, 1400);
      } catch (_) {
        button.textContent = "select";
      }
    });
  });

  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.querySelectorAll("[data-shutter]").forEach((el) => {
    if (reduced) {
      el.classList.add("is-open");
      return;
    }
    requestAnimationFrame(() => {
      requestAnimationFrame(() => el.classList.add("is-open"));
    });
  });
})();
