// Light/dark toggle. With nothing saved the page follows the system setting; a choice is kept in
// localStorage and applied by a one-line script in each page's <head>, before anything is drawn.
(() => {
  const root = document.documentElement;
  const system = matchMedia("(prefers-color-scheme: dark)");
  const isDark = () => (root.dataset.theme ? root.dataset.theme === "dark" : system.matches);
  const SUN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const MOON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linejoin="round" aria-hidden="true"><path d="M20.5 14.5A8.5 8.5 0 0 1 9.5 3.5a8.5 8.5 0 1 0 11 11z"/></svg>';

  // The button shows what clicking it switches to.
  function render() {
    for (const b of document.querySelectorAll(".theme-toggle")) {
      b.innerHTML = isDark() ? SUN : MOON;
      b.title = isDark() ? "Switch to light mode" : "Switch to dark mode";
      b.setAttribute("aria-label", b.title);
    }
  }
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".theme-toggle")) return;
    root.dataset.theme = isDark() ? "light" : "dark";
    try { localStorage.setItem("theme", root.dataset.theme); } catch {}
    render();
  });
  system.addEventListener("change", render);
  render();
})();
