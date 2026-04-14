(() => {
  const KEY   = "dive-theme";
  const html  = document.documentElement;
  const input = document.getElementById("themeToggle");
  const label = document.getElementById("themeLabel");

  function apply(light) {
    if (light) {
      html.setAttribute("data-theme", "light");
    } else {
      html.removeAttribute("data-theme");
    }
    if (label) label.textContent = light ? "Mode sombre" : "Mode clair";
    if (input) input.checked = light;
  }

  // Restore saved preference immediately (avoids flash)
  const saved = localStorage.getItem(KEY);
  apply(saved === "light");

  // Toggle on click
  if (input) {
    input.addEventListener("change", () => {
      const light = input.checked;
      localStorage.setItem(KEY, light ? "light" : "dark");
      apply(light);
    });
  }
})();
