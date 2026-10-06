/** Tab switching, keyboard shortcuts, and boot sequence. */
window.Reel = window.Reel || {};

(function (Reel) {
  "use strict";

  const TABS = ["download", "queue", "history", "search", "settings", "about"];

  function switchTab(name) {
    if (!TABS.includes(name)) return;
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("is-active", p.id === `panel-${name}`));
    document.querySelectorAll(".rail-tab").forEach((b) => b.classList.toggle("is-active", b.dataset.tab === name));
    document.querySelectorAll(".tabbar-btn").forEach((b) => b.classList.toggle("is-active", b.dataset.tab === name));
  }
  Reel.switchTab = switchTab;

  document.querySelectorAll(".rail-tab, .tabbar-btn").forEach((btn) => {
    btn.addEventListener("click", () => switchTab(btn.dataset.tab));
  });

  document.getElementById("themeToggle").addEventListener("click", () => Reel.toggleTheme());

  // Keyboard shortcuts: 1-5 jump tabs (unless typing), Ctrl/Cmd+Enter queues
  // the current link, Esc clears it while the URL field is focused.
  document.addEventListener("keydown", (e) => {
    const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);

    if (!typing && /^[1-5]$/.test(e.key)) {
      switchTab(TABS[Number(e.key) - 1]);
      return;
    }

    const urlInput = Reel.getUrlInput();
    if (document.activeElement === urlInput && e.key === "Escape") {
      urlInput.value = "";
      urlInput.dispatchEvent(new Event("input"));
    }

    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      const queueBtn = document.getElementById("queueBtn");
      if (document.getElementById("panel-download").classList.contains("is-active") && !document.getElementById("previewCard").hidden) {
        queueBtn.click();
      }
    }
  });

  document.addEventListener("DOMContentLoaded", async () => {
    try {
      await Reel.initSettings();
    } catch (_) {
      Reel.applyTheme("dark");
    }
    await Reel.initDownloads();
    Reel.initHistory();
    Reel.initSearch();

    document.querySelectorAll(".rail-tab, .tabbar-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (btn.dataset.tab === "history") Reel.initHistory();
      });
    });
  });
})(window.Reel);
