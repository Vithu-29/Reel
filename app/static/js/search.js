/** Search tab. */
window.Reel = window.Reel || {};

(function (Reel) {
  "use strict";

  const input = document.getElementById("searchInput");
  const btn = document.getElementById("searchBtn");
  const results = document.getElementById("searchResults");

  function renderCard(r) {
    return `
      <div class="result-card" data-url="${Reel.escapeHtml(r.url)}">
        ${r.thumbnail ? `<img class="result-thumb" src="${Reel.escapeHtml(r.thumbnail)}" alt="">` : '<div class="result-thumb"></div>'}
        <div class="result-body">
          <div class="result-title">${Reel.escapeHtml(r.title)}</div>
          <div class="result-sub">${Reel.escapeHtml(r.uploader || "")} ${r.duration ? "· " + Reel.formatDuration(r.duration) : ""}</div>
        </div>
      </div>`;
  }

  async function runSearch() {
    const q = input.value.trim();
    if (!q) return;
    results.innerHTML = '<p class="empty-state">Searching…</p>';
    try {
      const data = await Reel.get(`/search?q=${encodeURIComponent(q)}`);
      results.innerHTML = data.results.length
        ? data.results.map(renderCard).join("")
        : '<p class="empty-state">No results.</p>';
    } catch (err) {
      results.innerHTML = "";
      Reel.toast(err.message, "error");
    }
  }

  btn.addEventListener("click", runSearch);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") runSearch();
  });

  results.addEventListener("click", (e) => {
    const card = e.target.closest(".result-card");
    if (!card) return;
    Reel.switchTab("download");
    const urlInput = Reel.getUrlInput();
    urlInput.value = card.dataset.url;
    urlInput.dispatchEvent(new Event("input"));
  });

  Reel.initSearch = function () {};
})(window.Reel);
