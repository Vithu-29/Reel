/**
 * Shared helpers used by every other script on the page. Loaded first,
 * everything hangs off the single `Reel` namespace object so the plain
 * <script> tags don't need a bundler or ES module wiring.
 */
window.Reel = window.Reel || {};

(function (Reel) {
  "use strict";

  // ---- API -----------------------------------------------------------

  async function api(path, options = {}) {
    const res = await fetch(`/api${path}`, {
      ...options,
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": document.querySelector('meta[name="csrf-token"]')?.content || "", ...(options.headers || {}) },
    });
    let body = null;
    try {
      body = await res.json();
    } catch (_) {
      // no body / not JSON - fine for e.g. file downloads
    }
    if (res.status === 401) {
      window.location.replace("/login");
      throw new Error("Please sign in again.");
    }
    if (!res.ok) {
      const message = (body && body.error) || `Request failed (${res.status})`;
      throw new Error(message);
    }
    return body;
  }

  Reel.get = (path) => api(path);
  Reel.post = (path, data) => api(path, { method: "POST", body: data ? JSON.stringify(data) : undefined });
  Reel.del = (path) => api(path, { method: "DELETE" });

  // ---- Toasts ----------------------------------------------------------

  function toast(message, type = "info", timeout = 4200) {
    const stack = document.getElementById("toastStack");
    if (!stack) return;
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = message;
    stack.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transition = "opacity 200ms ease";
      setTimeout(() => el.remove(), 220);
    }, timeout);
  }
  Reel.toast = toast;

  // ---- Formatting --------------------------------------------------------

  Reel.formatBytes = function (bytes) {
    if (!bytes || bytes <= 0) return "0 MB";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0;
    let n = bytes;
    while (n >= 1024 && i < units.length - 1) {
      n /= 1024;
      i += 1;
    }
    return `${n.toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
  };

  Reel.formatDuration = function (seconds) {
    if (!seconds) return "—";
    seconds = Math.round(seconds);
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    const pad = (v) => String(v).padStart(2, "0");
    return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
  };

  Reel.formatDate = function (epochSeconds) {
    if (!epochSeconds) return "";
    return new Date(epochSeconds * 1000).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  };

  Reel.escapeHtml = function (str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : String(str);
    return div.innerHTML.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  };

  // ---- Theme ---------------------------------------------------------

  Reel.applyTheme = function (theme) {
    document.documentElement.setAttribute("data-theme", theme);
    const moon = document.querySelector(".icon-moon");
    const sun = document.querySelector(".icon-sun");
    if (moon && sun) {
      moon.hidden = theme === "dark";
      sun.hidden = theme !== "dark";
    }
  };

  // ---- Clipboard -------------------------------------------------------

  const URL_RE = /^https?:\/\/[^\s]+$/i;
  Reel.looksLikeUrl = (text) => URL_RE.test((text || "").trim());

  /** Best-effort "clipboard monitoring": browsers only allow reading the
   * clipboard on user gesture / focus, not truly in the background, so we
   * check it whenever the tab regains focus rather than polling forever. */
  Reel.watchClipboardOnFocus = function (onUrlFound) {
    let lastSeen = "";
    window.addEventListener("focus", async () => {
      if (!navigator.clipboard || !navigator.clipboard.readText) return;
      try {
        const text = (await navigator.clipboard.readText()).trim();
        if (text && text !== lastSeen && Reel.looksLikeUrl(text)) {
          lastSeen = text;
          onUrlFound(text);
        }
      } catch (_) {
        // permission denied / insecure context - silently do nothing
      }
    });
  };
})(window.Reel);
