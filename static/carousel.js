(() => {
  const track = document.getElementById("scoreCarousel");
  const prevBtn = document.getElementById("prevBtn");
  const nextBtn = document.getElementById("nextBtn");
  if (!track || !prevBtn || !nextBtn) return;

  const step = () => Math.max(240, Math.round(track.clientWidth * 0.8));

  prevBtn.addEventListener("click", () => {
    track.scrollBy({ left: -step(), behavior: "smooth" });
  });

  nextBtn.addEventListener("click", () => {
    track.scrollBy({ left: step(), behavior: "smooth" });
  });
})();

(() => {
  const metrics = document.querySelectorAll(".quality-tint[data-penalty]");
  metrics.forEach((el) => {
    const p = Number(el.getAttribute("data-penalty") || 0);
    let cls = "penalty-0";
    if (p >= 90) cls = "penalty-6";
    else if (p >= 75) cls = "penalty-5";
    else if (p >= 60) cls = "penalty-4";
    else if (p >= 45) cls = "penalty-3";
    else if (p >= 30) cls = "penalty-2";
    else if (p >= 15) cls = "penalty-1";
    el.classList.add(cls);
  });
})();

(() => {
  const ONE_HOUR_MS = 60 * 60 * 1000;
  window.setTimeout(() => {
    window.location.reload();
  }, ONE_HOUR_MS);
})();

(() => {
  const u = new URL(window.location.href);
  let changed = false;
  if (u.searchParams.has("force_refresh")) {
    u.searchParams.delete("force_refresh");
    changed = true;
  }
  if (u.searchParams.has("_")) {
    u.searchParams.delete("_");
    changed = true;
  }
  if (changed) {
    window.history.replaceState({}, "", u.toString());
  }
})();

(() => {
  const meta = document.getElementById("refreshMeta");
  const btn = document.getElementById("forceRefreshBtn");
  if (!meta || !btn) return;

  const COOLDOWN_MS = 5 * 60 * 1000;
  const lastRefreshMs = Number(meta.getAttribute("data-last-refresh-ms") || 0);

  const fmt = (ms) => {
    const totalSec = Math.max(0, Math.ceil(ms / 1000));
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m}:${String(s).padStart(2, "0")}`;
  };

  const updateState = () => {
    const now = Date.now();
    const remaining = lastRefreshMs + COOLDOWN_MS - now;
    if (remaining > 0) {
      btn.disabled = true;
      btn.textContent = `Disponible dans ${fmt(remaining)}`;
    } else {
      btn.disabled = false;
      btn.textContent = "Forcer le rafraîchissement";
    }
  };

  btn.addEventListener("click", () => {
    const now = Date.now();
    if (now < lastRefreshMs + COOLDOWN_MS) return;
    const u = new URL(window.location.href);
    u.searchParams.set("force_refresh", "1");
    u.searchParams.set("_", String(now));
    window.location.assign(u.toString());
  });

  updateState();
  window.setInterval(updateState, 1000);
})();
