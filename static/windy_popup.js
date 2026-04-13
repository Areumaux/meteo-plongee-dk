(() => {
  const LAT  = 51.035;
  const LON  = 2.377;
  const ZOOM = 9;

  const CONFIGS = {
    wind:     { label: "VENT — Windy Dunkerque",    overlay: "wind"     },
    waves:    { label: "VAGUES — Windy Dunkerque",  overlay: "waves"    },
    currents: { label: "COURANTS — Windy Dunkerque", overlay: "currents" },
  };

  // ── Build Windy embed URL ──────────────────────────────────────
  function buildUrl(overlay, isoDate) {
    const base = "https://embed.windy.com/embed2.html";
    const p = new URLSearchParams({
      lat:        LAT,
      lon:        LON,
      detailLat:  LAT,
      detailLon:  LON,
      zoom:       ZOOM,
      level:      "surface",
      overlay:    overlay,
      product:    "ecmwf",
      message:    "true",
      marker:     "true",
      calendar:   isoDate || "now",
      type:       "map",
      location:   "coordinates",
      metricWind: "kt",
      metricTemp: "°C",
    });
    return `${base}?${p.toString()}`;
  }

  // ── Create popup DOM ───────────────────────────────────────────
  const overlay = document.createElement("div");
  overlay.id = "wp-overlay";
  overlay.innerHTML = `
    <div id="wp-modal">
      <div id="wp-header">
        <span id="wp-title"></span>
        <button id="wp-close" aria-label="Fermer">✕</button>
      </div>
      <div id="wp-body">
        <iframe id="wp-frame" allowfullscreen frameborder="0"></iframe>
      </div>
      <div id="wp-footer">Dunkerque · 51.035°N 2.377°E · <a href="https://www.windy.com" target="_blank" rel="noopener">windy.com</a></div>
    </div>
  `;
  document.body.appendChild(overlay);

  const modal  = document.getElementById("wp-modal");
  const frame  = document.getElementById("wp-frame");
  const title  = document.getElementById("wp-title");
  const closeBtn = document.getElementById("wp-close");

  // ── Open / close ───────────────────────────────────────────────
  function open(windyKey, isoDate) {
    const cfg = CONFIGS[windyKey];
    if (!cfg) return;
    title.textContent = cfg.label;
    frame.src = buildUrl(cfg.overlay, isoDate);
    overlay.classList.add("active");
    document.body.style.overflow = "hidden";
  }

  function close() {
    overlay.classList.remove("active");
    frame.src = "";
    document.body.style.overflow = "";
  }

  closeBtn.addEventListener("click", close);

  overlay.addEventListener("click", (e) => {
    if (!modal.contains(e.target)) close();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") close();
  });

  // ── Attach to metric boxes ─────────────────────────────────────
  document.addEventListener("click", (e) => {
    const metric = e.target.closest(".metric[data-windy]");
    if (!metric) return;
    const card = metric.closest(".score-card");
    const isoDate = card ? card.dataset.date : null;
    open(metric.dataset.windy, isoDate);
  });
})();
