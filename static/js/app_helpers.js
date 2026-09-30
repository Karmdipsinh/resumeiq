(function exposeResumeIQ(root, factory) {
  const helpers = factory();
  if (typeof module === "object" && module.exports) module.exports = helpers;
  if (root) root.ResumeIQ = helpers;
})(typeof window !== "undefined" ? window : globalThis, () => {
  const MAX_FILE_BYTES = 5 * 1024 * 1024;

  function validateFile(file) {
    if (!file) return "Choose a resume before starting the analysis.";
    if (file.size > MAX_FILE_BYTES) return "That file is larger than 5 MB.";
    const extension = String(file.name || "").split(".").pop().toUpperCase();
    return ["PDF", "DOCX"].includes(extension) ? "" : "Please select a PDF or DOCX file.";
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, (character) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[character]);
  }

  function historyMarkup(items, formatDate) {
    if (!items.length) {
      return '<div class="empty-state history-empty"><strong>No analyses yet</strong><span>Upload a resume or try the demo to see results here.</span></div>';
    }
    return items.map((item) => `
      <div class="history-item">
        <span class="history-file">${escapeHtml(item.resume_filename.slice(0, 1).toUpperCase())}</span>
        <a class="history-info" href="/results/${encodeURIComponent(item.id)}"><strong>${escapeHtml(item.resume_filename)}</strong><small>${escapeHtml(formatDate(item.created_at))}</small></a>
        <span class="history-score"><small>Resume</small><strong>${Number(item.resume_score)}</strong></span>
        <span class="history-score"><small>Match</small><strong>${item.match_percentage === null ? "—" : `${Number(item.match_percentage)}%`}</strong></span>
        <button class="history-delete" type="button" data-analysis-id="${escapeHtml(item.id)}" aria-label="Delete ${escapeHtml(item.resume_filename)}">×</button>
      </div>`).join("");
  }

  async function requestJson(fetchImplementation, url, options = {}) {
    const response = await fetchImplementation(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.error || "Something went wrong. Please try again.");
    return data;
  }

  return { MAX_FILE_BYTES, validateFile, escapeHtml, historyMarkup, requestJson };
});
