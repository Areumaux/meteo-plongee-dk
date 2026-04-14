(() => {
  // ── Build popup DOM ────────────────────────────────────────────
  const popup = document.createElement("div");
  popup.id = "slotPopup";
  popup.innerHTML = `
    <div class="sp-title" id="spTitle"></div>
    <div class="sp-row"><span class="sp-key">Vent</span>   <span class="sp-val" id="spWind"></span></div>
    <div class="sp-row"><span class="sp-key">Direction</span><span class="sp-val" id="spDir"></span></div>
    <div class="sp-row"><span class="sp-key">Vagues</span> <span class="sp-val" id="spWave"></span></div>
    <div class="sp-row"><span class="sp-key">Marée</span>  <span class="sp-val" id="spTide"></span></div>
  `;
  document.body.appendChild(popup);

  const elTitle = document.getElementById("spTitle");
  const elWind  = document.getElementById("spWind");
  const elDir   = document.getElementById("spDir");
  const elWave  = document.getElementById("spWave");
  const elTide  = document.getElementById("spTide");

  // ── Wind direction label ───────────────────────────────────────
  function dirLabel(deg) {
    if (deg === "" || deg === null || isNaN(deg)) return "—";
    const dirs = ["N","NNE","NE","ENE","E","ESE","SE","SSE","S","SSO","SO","OSO","O","ONO","NO","NNO"];
    const arrow = String.fromCodePoint(0x2191); // ↑
    const rotated = `<span style="display:inline-block;transform:rotate(${(+deg + 180) % 360}deg)">${arrow}</span>`;
    const sector = dirs[Math.round(deg / 22.5) % 16];
    return `${rotated} ${sector} (${deg}°)`;
  }

  // ── Position popup near the clicked element ────────────────────
  function position(el) {
    const rect = el.getBoundingClientRect();
    const pw = popup.offsetWidth  || 200;
    const ph = popup.offsetHeight || 130;
    const vw = window.innerWidth;
    const vh = window.innerHeight;

    let top  = rect.bottom + 6;
    let left = rect.left;

    if (left + pw > vw - 8)  left = vw - pw - 8;
    if (top  + ph > vh - 8)  top  = rect.top - ph - 6;
    if (left < 8)             left = 8;

    popup.style.top  = `${top  + window.scrollY}px`;
    popup.style.left = `${left + window.scrollX}px`;
  }

  // ── Show popup ─────────────────────────────────────────────────
  let activeRow = null;

  function show(row) {
    const wind    = row.dataset.wind;
    const dir     = row.dataset.dir;
    const wave    = row.dataset.wave;
    const rising  = row.dataset.rising === "true";
    const range   = row.dataset.range || "";

    elTitle.textContent = `Créneau ${range}`;
    elWind.textContent  = wind  ? `${wind} nds` : "—";
    elDir.innerHTML     = dirLabel(dir);
    elWave.textContent  = wave  ? `${wave} m`   : "—";

    if (rising) {
      elTide.innerHTML = `<span style="color:#4fc">↑ Montante</span>`;
    } else {
      elTide.innerHTML = `<span style="color:#f84">↓ Descendante</span>`;
    }

    popup.classList.add("visible");
    activeRow = row;
    row.classList.add("slot-active");

    // position after making visible so offsetWidth is known
    requestAnimationFrame(() => position(row));
  }

  function hide() {
    popup.classList.remove("visible");
    if (activeRow) {
      activeRow.classList.remove("slot-active");
      activeRow = null;
    }
  }

  // ── Event delegation ──────────────────────────────────────────
  document.addEventListener("click", (e) => {
    const row = e.target.closest(".slot-row");
    if (row) {
      if (activeRow === row) { hide(); return; }
      hide();
      show(row);
      e.stopPropagation();
      return;
    }
    // click outside → close
    if (!popup.contains(e.target)) hide();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
  });
})();
