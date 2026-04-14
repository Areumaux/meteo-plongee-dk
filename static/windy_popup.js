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
  function buildUrl(overlay) {
    const base = "https://embed.windy.com/embed2.html";
    const params = {
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
      calendar:   "now",
      type:       "map",
      location:   "coordinates",
      metricWind: "kt",
      metricTemp: "°C",
    };
    return `${base}?${new URLSearchParams(params).toString()}`;
  }

  // ── Seek Windy to a specific date via postMessage ──────────────
  // Windy embed listens for { timestamp } in milliseconds.
  // We retry a few times to make sure the player is ready.
  function seekWindy(tsMs) {
    let attempts = 0;
    const send = () => {
      try {
        frame.contentWindow.postMessage({ timestamp: tsMs }, "*");
      } catch (_) {}
    };
    // Fire at 1 s, 2 s, 3.5 s after iframe load
    [1000, 2000, 3500].forEach((delay) => {
      setTimeout(send, delay);
    });
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

    // Compute target timestamp (noon UTC of the card's date)
    const tsMs = isoDate
      ? new Date(isoDate + "T12:00:00Z").getTime()
      : null;

    // Update title with date hint
    if (isoDate) {
      const d = new Date(isoDate + "T12:00:00Z");
      const label = d.toLocaleDateString("fr-FR", { weekday: "long", day: "numeric", month: "long" });
      title.textContent = `${cfg.label} — ${label}`;
    }

    // Load iframe, then seek to date via postMessage
    frame.onload = () => { if (tsMs) seekWindy(tsMs); };
    frame.src = buildUrl(cfg.overlay);

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
