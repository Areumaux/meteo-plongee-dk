(() => {
  const KEY  = "dive-theme";
  const html = document.documentElement;

  function apply(light) {
    if (light) {
      html.setAttribute("data-theme", "light");
    } else {
      html.removeAttribute("data-theme");
    }
    const btn = document.getElementById("themeBtn");
    if (btn) btn.textContent = light ? "☀️" : "🌙";
  }

  // Restore saved preference immediately (avoids flash)
  const saved = localStorage.getItem(KEY);
  apply(saved === "light");

  // Wire up button after DOM ready
  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("themeBtn");
    if (!btn) return;
    // sync icon in case apply() ran before DOMContentLoaded
    btn.textContent = html.hasAttribute("data-theme") ? "☀️" : "🌙";
    btn.addEventListener("click", () => {
      const light = !html.hasAttribute("data-theme");
      localStorage.setItem(KEY, light ? "light" : "dark");
      apply(light);
    });
  });
})();
