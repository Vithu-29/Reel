/** History tab. */
window.Reel = window.Reel || {};

(function (Reel) {
  "use strict";

  const list = document.getElementById("historyList");
  const clearBtn = document.getElementById("clearHistoryBtn");

  function renderRow(entry) {
    const ok = ["finished", "downloaded (browser)", "ready for browser"].includes(entry.status);
    return `
      <div class="item-card" data-id="${entry.id}">
        <div class="item-top">
          <div class="item-thumb"></div>
          <div class="item-info">
            <div class="item-title">${Reel.escapeHtml(entry.filename)}</div>
            <div class="item-sub">
              <span class="status-pill ${ok ? "finished" : "error"}">${Reel.escapeHtml(entry.status)}</span>
              <span>${Reel.escapeHtml(entry.container || "")}</span>
              <span>${Reel.escapeHtml(entry.resolution || "")}</span>
              <span>${Reel.formatDate(entry.downloaded_at)}</span>
              ${entry.filepath ? `<span>${Reel.escapeHtml(entry.filepath)}</span>` : ""}
            </div>
          </div>
          <div class="item-actions">
            <button class="btn btn-ghost btn-sm" data-action="redownload" data-id="${entry.id}" type="button">Redownload</button>
            <button class="btn btn-danger btn-sm" data-action="delete" data-id="${entry.id}" type="button">Delete</button>
          </div>
        </div>
      </div>`;
  }

  async function refresh() {
    const data = await Reel.get("/history");
    list.innerHTML = data.items.length
      ? data.items.map(renderRow).join("")
      : '<p class="empty-state">No downloads yet.</p>';
  }

  list.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b) return;
    const id = b.dataset.id;
    try {
      if (b.dataset.action === "delete") {
        await Reel.del(`/history/${id}`);
      } else {
        await Reel.post(`/history/${id}/redownload`);
        Reel.toast("Added to the queue.", "success");
        Reel.switchTab("queue");
      }
      refresh();
    } catch (err) {
      Reel.toast(err.message, "error");
    }
  });

  clearBtn.addEventListener("click", async () => {
    if (!confirm("Delete all download history?")) return;
    await Reel.del("/history");
    refresh();
  });

  Reel.initHistory = refresh;
})(window.Reel);
