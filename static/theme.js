(() => {
  const KEY  = "dive-theme";
  const html = document.documentElement;

  function apply(light) {
    if (light) {
      html.setAttribute("data-theme", "light");
    } else {
      html.removeAttribute("data-theme");
    }
    const icon   = document.getElementById("themeFabIcon");
    const toggle = document.getElementById("themeToggle");
    if (icon)   icon.textContent = light ? "☀️" : "🌙";
    if (toggle) toggle.checked   = light;
  }

  // Apply before paint to avoid flash. Light is the default unless dark was explicitly selected.
  apply(localStorage.getItem(KEY) !== "dark");

  document.addEventListener("DOMContentLoaded", () => {
    // Sync in case apply() ran before DOM was ready
    apply(html.hasAttribute("data-theme"));

    const toggle = document.getElementById("themeToggle");
    if (toggle) {
      toggle.addEventListener("change", () => {
        const light = toggle.checked;
        localStorage.setItem(KEY, light ? "light" : "dark");
        apply(light);
      });
    }
  });
})();
