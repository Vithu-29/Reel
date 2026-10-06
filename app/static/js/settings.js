/** Settings tab. */
window.Reel = window.Reel || {};

(function (Reel) {
  "use strict";

  const el = {
    folder: document.getElementById("settingFolder"),
    browseBtn: document.getElementById("settingBrowseBtn"),
    concurrency: document.getElementById("settingConcurrency"),
    sponsor: document.getElementById("settingSponsor"),
    meta: document.getElementById("settingMeta"),
    saveBtn: document.getElementById("saveSettingsBtn"),
    updateBtn: document.getElementById("updateYtdlpBtn"),
    updateResult: document.getElementById("updateYtdlpResult"),
  };

  async function load() {
    const s = await Reel.get("/settings");
    el.folder.value = s.download_folder || "";
    el.concurrency.value = s.concurrency || 3;
    el.sponsor.checked = !!s.sponsorblock_default;
    el.meta.checked = !!s.embed_metadata_default;
    Reel.applyTheme(s.theme || "dark");
    return s;
  }

  el.browseBtn.addEventListener("click", async () => {
    try {
      const data = await Reel.post("/browse-directory");
      if (data.path) el.folder.value = data.path;
    } catch (err) {
      Reel.toast(err.message, "error");
    }
  });

  el.saveBtn.addEventListener("click", async () => {
    try {
      await Reel.post("/settings", {
        download_folder: el.folder.value.trim(),
        concurrency: parseInt(el.concurrency.value, 10) || 3,
        sponsorblock_default: el.sponsor.checked,
        embed_metadata_default: el.meta.checked,
      });
      Reel.toast("Settings saved.", "success");
    } catch (err) {
      Reel.toast(err.message, "error");
    }
  });

  el.updateBtn.addEventListener("click", async () => {
    el.updateBtn.disabled = true;
    el.updateResult.textContent = "Updating yt-dlp…";
    try {
      const data = await Reel.post("/update-ytdlp");
      el.updateResult.textContent = data.message;
      Reel.toast("Update installed. Restart the server to activate it.", "success", 8000);
    } catch (err) {
      el.updateResult.textContent = "";
      Reel.toast(err.message, "error");
    } finally {
      el.updateBtn.disabled = false;
    }
  });

  async function loadStatus() {
    const status = document.getElementById("systemStatus");
    try {
      const s = await Reel.get("/system-status");
      status.textContent = `yt-dlp ${s.yt_dlp} · Flask ${s.flask} · FFmpeg ${s.ffmpeg ? "ready" : "missing"} · JavaScript: ${s.js_runtimes.join(", ") || "missing"} · EJS ${s.ejs || "missing"}. ${s.warnings.join(" ")}`;
    } catch (err) { status.textContent = err.message; }
  }
  document.getElementById("refreshSystemBtn").addEventListener("click", loadStatus);
  Reel.initSettings = async () => { const s = await load(); await loadStatus(); return s; };

  Reel.toggleTheme = async function () {
    const current = document.documentElement.getAttribute("data-theme");
    const next = current === "dark" ? "light" : "dark";
    Reel.applyTheme(next);
    try {
      await Reel.post("/settings", { theme: next });
    } catch (_) {
      // theme still applied client-side even if the save fails
    }
  };
})(window.Reel);
