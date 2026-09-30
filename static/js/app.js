(() => {
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const { escapeHtml, historyMarkup, requestJson, validateFile } = window.ResumeIQ;

  function toast(message, type = "info") {
    const node = $(".toast");
    if (!node) return;
    node.textContent = message;
    node.className = `toast show ${type}`;
    window.clearTimeout(toast.timer);
    toast.timer = window.setTimeout(() => node.classList.remove("show"), 3500);
  }

  const request = (url, options = {}) => requestJson(fetch, url, options);

  async function runDemo(button) {
    const original = button.textContent;
    button.disabled = true;
    button.textContent = "Running demo…";
    try {
      const data = await request("/api/demo", { method: "POST" });
      window.location.assign(`/results/${data.id}`);
    } catch (error) {
      toast(error.message, "error");
      button.disabled = false;
      button.textContent = original;
    }
  }

  $$(".js-demo").forEach((button) => button.addEventListener("click", () => runDemo(button)));

  function formatBytes(bytes) {
    if (bytes < 1024) return `${bytes} bytes`;
    return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  }

  function setupDashboard() {
    const form = $("#analysis-form");
    if (!form) return;
    const input = $("#resume-file");
    const zone = $("#drop-zone");
    const selection = $("#file-selection");
    const message = $("#form-message");
    const textarea = $("#job-description");

    function showFile(file) {
      if (!file) {
        selection.hidden = true;
        zone.hidden = false;
        input.value = "";
        return;
      }
      const validationError = validateFile(file);
      if (validationError) {
        message.textContent = validationError;
        message.className = "form-message error";
        input.value = "";
        return;
      }
      const extension = file.name.split(".").pop().toUpperCase();
      $(".file-type", selection).textContent = extension;
      $("#file-name").textContent = file.name;
      $("#file-size").textContent = formatBytes(file.size);
      zone.hidden = true;
      selection.hidden = false;
      message.textContent = "";
    }

    input.addEventListener("change", () => showFile(input.files[0]));
    $("#remove-file").addEventListener("click", () => showFile(null));
    ["dragenter", "dragover"].forEach((name) => zone.addEventListener(name, (event) => {
      event.preventDefault(); zone.classList.add("dragging");
    }));
    ["dragleave", "drop"].forEach((name) => zone.addEventListener(name, (event) => {
      event.preventDefault(); zone.classList.remove("dragging");
    }));
    zone.addEventListener("drop", (event) => {
      if (!event.dataTransfer.files.length) return;
      const transfer = new DataTransfer();
      transfer.items.add(event.dataTransfer.files[0]);
      input.files = transfer.files;
      showFile(input.files[0]);
    });
    textarea.addEventListener("input", () => {
      $("#character-count").textContent = `${textarea.value.length.toLocaleString()} / 20,000`;
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const validationError = validateFile(input.files[0]);
      if (validationError) {
        message.textContent = validationError;
        message.className = "form-message error";
        return;
      }
      const button = $(".analyze-button");
      button.classList.add("loading");
      button.disabled = true;
      message.textContent = "Extracting text and calculating your scores…";
      message.className = "form-message working";
      try {
        const data = await request("/api/analyze-resume", { method: "POST", body: new FormData(form) });
        window.location.assign(`/results/${data.id}`);
      } catch (error) {
        message.textContent = error.message;
        message.className = "form-message error";
        button.classList.remove("loading");
        button.disabled = false;
      }
    });

    $("#refresh-history").addEventListener("click", loadHistory);
    loadHistory();
  }

  async function loadHistory() {
    const list = $("#history-list");
    if (!list) return;
    list.innerHTML = '<div class="history-loading">Loading your analysis history…</div>';
    try {
      const data = await request("/api/history?limit=10");
      list.innerHTML = historyMarkup(data.analyses, formatDate);
      if (!data.analyses.length) return;
      $$(".history-delete", list).forEach((button) => button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          await request(`/api/history/${encodeURIComponent(button.dataset.analysisId)}`, { method: "DELETE" });
          toast("Analysis deleted.");
          loadHistory();
        } catch (error) {
          toast(error.message, "error");
          button.disabled = false;
        }
      }));
    } catch (error) {
      list.innerHTML = `<div class="empty-state">${escapeHtml(error.message)}</div>`;
    }
  }

  function formatDate(value) {
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : new Intl.DateTimeFormat(undefined, {
      dateStyle: "medium", timeStyle: "short",
    }).format(date);
  }

  $$(".js-date").forEach((node) => { node.textContent = formatDate(node.dateTime); });
  $$(".js-print").forEach((button) => button.addEventListener("click", () => window.print()));
  setupDashboard();
})();
