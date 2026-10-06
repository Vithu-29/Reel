/**
 * The Download tab (URL entry, info preview, format options) and the
 * Queue tab (polling + render + pause/resume/cancel/retry actions).
 */
window.Reel = window.Reel || {};

(function (Reel) {
  "use strict";

  const AUDIO_CONTAINERS = new Set(["mp3", "m4a", "wav", "flac"]);

  const el = {
    urlInput: document.getElementById("urlInput"),
    dropzone: document.getElementById("dropzone"),
    pasteBtn: document.getElementById("pasteBtn"),
    previewCard: document.getElementById("previewCard"),
    previewThumb: document.getElementById("previewThumb"),
    previewTitle: document.getElementById("previewTitle"),
    previewChips: document.getElementById("previewChips"),
    playlistNotice: document.getElementById("playlistNotice"),
    playlistCount: document.getElementById("playlistCount"),
    playlistModeControl: document.getElementById("playlistModeControl"),
    playlistItems: document.getElementById("playlistItems"),
    containerSelect: document.getElementById("containerSelect"),
    videoQualityWrap: document.getElementById("videoQualityWrap"),
    videoQualitySelect: document.getElementById("videoQualitySelect"),
    audioQualityWrap: document.getElementById("audioQualityWrap"),
    audioQualitySelect: document.getElementById("audioQualitySelect"),
    savePathInput: document.getElementById("savePathInput"),
    browseBtn: document.getElementById("browseBtn"),
    subsToggle: document.getElementById("subsToggle"),
    thumbToggle: document.getElementById("thumbToggle"),
    metaToggle: document.getElementById("metaToggle"),
    sponsorToggle: document.getElementById("sponsorToggle"),
    queueBtn: document.getElementById("queueBtn"),
    queueList: document.getElementById("queueList"),
    queueBadge: document.getElementById("queueBadge"),
    concurrencyLabel: document.getElementById("concurrencyLabel"),
    clearCompletedBtn: document.getElementById("clearCompletedBtn"),
    clearAllBtn: document.getElementById("clearAllBtn"),
    statActive: document.getElementById("statActive"),
    statQueued: document.getElementById("statQueued"),
    statDone: document.getElementById("statDone"),
    statFailed: document.getElementById("statFailed"),
    statSize: document.getElementById("statSize"),
  };

  let playlistMode = "single";
  let lastInfoUrl = "";
  let fetchTimer = null;

  // ---- Options population --------------------------------------------

  async function loadFormats() {
    const data = await Reel.get("/formats");
    el.containerSelect.innerHTML = data.containers.map((c) => `<option value="${c}">${c.toUpperCase()}</option>`).join("");
    el.videoQualitySelect.innerHTML = data.video_qualities
      .map((q) => `<option value="${q}">${q === "best" ? "Best available" : q}</option>`)
      .join("");
    el.audioQualitySelect.innerHTML = data.audio_qualities
      .map((q) => `<option value="${q}">${q === "best" ? "Best available" : q + " kbps"}</option>`)
      .join("");
  }

  function onContainerChange() {
    const isAudio = AUDIO_CONTAINERS.has(el.containerSelect.value);
    el.videoQualityWrap.hidden = isAudio;
    el.audioQualityWrap.hidden = !isAudio;
  }

  // ---- Info preview ----------------------------------------------------

  function resetPreview() {
    el.previewCard.hidden = true;
    el.playlistNotice.hidden = true;
    lastInfoUrl = "";
  }

  async function fetchInfo(url) {
    if (!url || !Reel.looksLikeUrl(url) || url === lastInfoUrl) return;
    lastInfoUrl = url;
    try {
      const data = await Reel.get(`/info?url=${encodeURIComponent(url)}&playlist_mode=entire`);
      renderPreview(data);
    } catch (err) {
      Reel.toast(err.message, "error");
      resetPreview();
    }
  }

  function renderPreview(data) {
    el.previewCard.hidden = false;
    if (data.is_playlist) {
      el.previewThumb.src = (data.entries[0] && data.entries[0].thumbnail) || "";
      el.previewTitle.textContent = data.playlist_title || "Playlist";
      el.previewChips.innerHTML = `<span class="chip">${data.playlist_count} items</span>`;
      el.playlistNotice.hidden = false;
      el.playlistCount.textContent = data.playlist_count;
      playlistMode = "single";
      updatePlaylistModeButtons();
    } else {
      el.previewThumb.src = data.thumbnail || "";
      el.previewTitle.textContent = data.title || "Untitled";
      const chips = [];
      if (data.duration) chips.push(Reel.formatDuration(data.duration));
      if (data.uploader) chips.push(Reel.escapeHtml(data.uploader));
      if (data.resolutions && data.resolutions.length) chips.push(`${data.resolutions[0]}p max`);
      if (data.filesize_approx) chips.push(`~${Reel.formatBytes(data.filesize_approx)}`);
      if (data.fps) chips.push(`${data.fps} fps`);
      el.previewChips.innerHTML = chips.map((c) => `<span class="chip">${c}</span>`).join("");
      el.playlistNotice.hidden = true;
    }
  }

  function updatePlaylistModeButtons() {
    [...el.playlistModeControl.querySelectorAll("button")].forEach((b) => {
      b.classList.toggle("is-active", b.dataset.value === playlistMode);
    });
    el.playlistItems.hidden = playlistMode !== "selected";
  }

  el.playlistModeControl?.addEventListener("click", (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    playlistMode = btn.dataset.value;
    updatePlaylistModeButtons();
  });

  // ---- URL input: paste / drag&drop / debounce fetch --------------------

  function scheduleFetch() {
    clearTimeout(fetchTimer);
    fetchTimer = setTimeout(() => fetchInfo(el.urlInput.value.trim()), 500);
  }

  el.urlInput.addEventListener("input", () => {
    if (!el.urlInput.value.trim()) resetPreview();
    scheduleFetch();
  });

  el.urlInput.addEventListener("paste", () => setTimeout(scheduleFetch, 30));

  el.pasteBtn.addEventListener("click", async () => {
    try {
      const text = await navigator.clipboard.readText();
      el.urlInput.value = text.trim();
      scheduleFetch();
    } catch (_) {
      Reel.toast("Couldn't read the clipboard - paste manually with Ctrl+V.", "error");
    }
  });

  ["dragenter", "dragover"].forEach((evt) =>
    el.dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      el.dropzone.classList.add("is-dragover");
    })
  );
  ["dragleave", "drop"].forEach((evt) =>
    el.dropzone.addEventListener(evt, () => el.dropzone.classList.remove("is-dragover"))
  );
  el.dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    const text = e.dataTransfer.getData("text/plain") || e.dataTransfer.getData("text/uri-list");
    if (text) {
      el.urlInput.value = text.trim();
      scheduleFetch();
    }
  });

  // ---- Server folder browse ---------------------------------------------

  el.browseBtn.addEventListener("click", async () => {
    try {
      const data = await Reel.post("/browse-directory");
      if (data.path) el.savePathInput.value = data.path;
    } catch (err) {
      Reel.toast(err.message, "error");
    }
  });

  // ---- Queue submission --------------------------------------------------

  el.queueBtn.addEventListener("click", async () => {
    const url = el.urlInput.value.trim();
    if (!url) {
      Reel.toast("Paste a link first.", "error");
      return;
    }
    const container = el.containerSelect.value;
    const payload = {
      url,
      container,
      video_quality: el.videoQualitySelect.value,
      audio_only: AUDIO_CONTAINERS.has(container),
      audio_quality: el.audioQualitySelect.value,
      playlist_mode: playlistMode,
      playlist_items: el.playlistItems.value.trim(),
      download_subtitles: el.subsToggle.checked,
      embed_thumbnail: el.thumbToggle.checked,
      embed_metadata: el.metaToggle.checked,
      sponsorblock: el.sponsorToggle.checked,
      save_path: el.savePathInput.value.trim(),
    };
    el.queueBtn.disabled = true;
    try {
      await Reel.post("/download", payload);
      Reel.toast("Added to the queue.", "success");
      el.urlInput.value = "";
      resetPreview();
      Reel.switchTab("queue");
      refreshQueue();
    } catch (err) {
      Reel.toast(err.message, "error");
    } finally {
      el.queueBtn.disabled = false;
    }
  });

  // ---- Queue rendering ----------------------------------------------------

  function statusLabel(status) {
    return { starting: "Starting", downloading: "Downloading", processing: "Processing", finished: "Done", error: "Failed", canceled: "Canceled", queued: "Queued", paused: "Paused" }[status] || status;
  }

  function renderQueue(items) {
    if (!items.length) {
      el.queueList.innerHTML = '<p class="empty-state">Nothing queued yet — add a link from the Download tab.</p>';
      return;
    }
    el.queueList.innerHTML = items.map(renderItem).join("");
  }

  function renderItem(item) {
    const s = item.status;
    const showProgress = ["starting", "downloading", "processing"].includes(s);
    const pct = Math.max(0, Math.min(100, item.percent || 0));
    const subBits = [];
    if (s === "downloading") {
      if (item.speed) subBits.push(item.speed);
      if (item.eta) subBits.push(`ETA ${item.eta}`);
      if (item.total_bytes) subBits.push(`${Reel.formatBytes(item.downloaded_bytes)} / ${Reel.formatBytes(item.total_bytes)}`);
    } else if (s === "error" && item.error) {
      subBits.push(item.error.slice(0, 140));
    } else if (s === "finished") {
      subBits.push(item.options.save_path ? `Saved to ${item.options.save_path}` : "Ready to download");
    } else {
      subBits.push(item.options.container.toUpperCase(), item.options.video_quality);
    }

    const actions = [];
    if (s === "queued") actions.push(btn(item.task_id, "pause", "Pause"));
    if (s === "paused") actions.push(btn(item.task_id, "resume", "Resume"));
    if (["queued", "paused", "starting", "downloading", "processing"].includes(s)) actions.push(btn(item.task_id, "cancel", "Cancel"));
    if (["error", "canceled"].includes(s)) actions.push(btn(item.task_id, "retry", "Retry"));
    if (s === "finished" && !item.options.save_path) actions.push(`<a class="btn btn-ghost btn-sm" href="/api/download-file/${item.task_id}">Save file</a>`);

    return `
      <div class="item-card" data-task-id="${item.task_id}">
        <div class="item-top">
          ${item.thumbnail ? `<img class="item-thumb" src="${item.thumbnail}" alt="">` : '<div class="item-thumb"></div>'}
          <div class="item-info">
            <div class="item-title">${Reel.escapeHtml(item.title || item.url)}</div>
            <div class="item-sub"><span class="status-pill ${s}">${statusLabel(s)}</span>${subBits.map((b) => `<span>${Reel.escapeHtml(b)}</span>`).join("")}</div>
          </div>
          <div class="item-actions">${actions.join("")}</div>
        </div>
        ${showProgress ? `<div class="sprocket-progress" style="--pct:${pct}%"><span class="sprocket-label">${s === "processing" ? "Processing…" : pct.toFixed(0) + "%"}</span></div>` : ""}
      </div>`;
  }

  function btn(taskId, action, label) {
    return `<button class="btn btn-ghost btn-sm" data-action="${action}" data-task-id="${taskId}" type="button">${label}</button>`;
  }

  el.queueList.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-action]");
    if (!b) return;
    const { action, taskId } = { action: b.dataset.action, taskId: b.dataset.taskId };
    b.disabled = true;
    try {
      if (action === "retry") {
        await Reel.post(`/queue/${taskId}/retry`);
      } else {
        await Reel.post(`/queue/${taskId}/${action}`);
      }
      refreshQueue();
    } catch (err) {
      Reel.toast(err.message, "error");
      b.disabled = false;
    }
  });

  el.clearCompletedBtn.addEventListener("click", async () => {
    await Reel.post("/queue/clear-completed");
    refreshQueue();
  });
  el.clearAllBtn.addEventListener("click", async () => {
    if (!confirm("Cancel and remove everything in the queue?")) return;
    await Reel.post("/queue/clear");
    refreshQueue();
  });

  function renderStats(stats) {
    el.statActive.textContent = stats.active;
    el.statQueued.textContent = stats.queued;
    el.statDone.textContent = stats.completed;
    el.statFailed.textContent = stats.failed;
    el.statSize.textContent = Reel.formatBytes(stats.total_downloaded_bytes);
    el.concurrencyLabel.textContent = stats.concurrency;
    const busy = stats.active + stats.queued;
    el.queueBadge.hidden = busy === 0;
    el.queueBadge.textContent = busy;
  }

  async function refreshQueue() {
    try {
      const data = await Reel.get("/queue");
      renderQueue(data.items);
      renderStats(data.stats);
    } catch (_) {
      // transient network hiccup - next poll will retry
    }
  }

  // ---- init --------------------------------------------------------------

  Reel.initDownloads = async function () {
    await loadFormats();
    el.containerSelect.addEventListener("change", onContainerChange);
    onContainerChange();
    updatePlaylistModeButtons();
    await refreshQueue();
    setInterval(refreshQueue, 1500);

    Reel.watchClipboardOnFocus((url) => {
      if (document.activeElement === el.urlInput) return;
      Reel.toast("Detected a link on your clipboard — paste it with the clipboard button.", "info");
    });
  };

  Reel.getUrlInput = () => el.urlInput;
})(window.Reel);
