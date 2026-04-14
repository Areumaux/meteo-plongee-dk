(() => {
  // ── Build popup DOM ────────────────────────────────────────────
  const popup = document.createElement("div");
  popup.id = "slotPopup";
  popup.innerHTML = `
    <div class="sp-title" id="spTitle"></div>
    <div class="sp-row"><span class="sp-key">Vent</span>    <span class="sp-val" id="spWind"></span></div>
    <div class="sp-row"><span class="sp-key">Direction</span><span class="sp-val" id="spDir"></span></div>
    <div class="sp-row"><span class="sp-key">Vagues</span>  <span class="sp-val" id="spWave"></span></div>
    <div class="sp-row"><span class="sp-key">Marée</span>   <span class="sp-val" id="spTide"></span></div>
  `;
  document.body.appendChild(popup);

  const elTitle = document.getElementById("spTitle");
  const elWind  = document.getElementById("spWind");
  const elDir   = document.getElementById("spDir");
  const elWave  = document.getElementById("spWave");
  const elTide  = document.getElementById("spTide");

  // ── Wind direction label ───────────────────────────────────────
  function dirLabel(deg) {
    if (deg === "" || deg === null || isNaN(+deg)) return "—";
    const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSO","SO","OSO","O","ONO","NO","NNO"];
    const arrow = "↑";
    const rot   = `<span style="display:inline-block;transform:rotate(${(+deg+180)%360}deg)">${arrow}</span>`;
    const sector = dirs[Math.round(+deg / 22.5) % 16];
    return `${rot} ${sector} (${deg}°)`;
  }

  // ── Position popup (fixed coords = viewport-relative, no scrollY) ─
  function position(rect) {
    popup.style.top  = "0";
    popup.style.left = "0";

    const pw = popup.offsetWidth  || 200;
    const ph = popup.offsetHeight || 140;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const GAP = 6;

    // Prefer below the row; flip above if it would overflow
    let top  = rect.bottom + GAP;
    let left = rect.left;

    if (top + ph > vh - 8) top = rect.top - ph - GAP;
    if (top < 8)            top = 8;

    // Clamp horizontally
    if (left + pw > vw - 8) left = vw - pw - 8;
    if (left < 8)            left = 8;

    popup.style.top  = `${top}px`;
    popup.style.left = `${left}px`;
  }

  // ── Show popup ─────────────────────────────────────────────────
  let activeRow = null;

  function show(row) {
    const wind   = row.dataset.wind;
    const dir    = row.dataset.dir;
    const wave   = row.dataset.wave;
    const rising = row.dataset.rising === "true";
    const range  = row.dataset.range || "";

    elTitle.textContent = `Créneau  ${range}`;
    elWind.textContent  = wind ? `${wind} nds` : "—";
    elDir.innerHTML     = dirLabel(dir);
    elWave.textContent  = wave ? `${wave} m`   : "—";
    elTide.innerHTML    = rising
      ? `<span style="color:#4fc">↑ Montante</span>`
      : `<span style="color:#f84">↓ Descendante</span>`;

    popup.classList.add("visible");
    activeRow = row;
    row.classList.add("slot-active");

    // Position after visible so offsetWidth/Height are known
    requestAnimationFrame(() => position(row.getBoundingClientRect()));
  }

  function hide() {
    popup.classList.remove("visible");
    if (activeRow) {
      activeRow.classList.remove("slot-active");
      activeRow = null;
    }
  }

  // ── Event handling (pointer covers both mouse and touch) ───────
  document.addEventListener("pointerup", (e) => {
    const row = e.target.closest(".slot-row");
    if (row) {
      if (activeRow === row) { hide(); return; }
      hide();
      show(row);
      return;
    }
    if (!popup.contains(e.target)) hide();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
  });
})();
