const test = require("node:test");
const assert = require("node:assert/strict");
const { escapeHtml, historyMarkup, requestJson, validateFile } = require("./app_helpers.js");

test("file and form validation reject missing, oversized, and unsupported files", () => {
  assert.match(validateFile(null), /Choose a resume/);
  assert.match(validateFile({ name: "resume.pdf", size: 5 * 1024 * 1024 + 1 }), /larger than 5 MB/);
  assert.match(validateFile({ name: "resume.exe", size: 10 }), /PDF or DOCX/);
  assert.equal(validateFile({ name: "resume.DOCX", size: 10 }), "");
});

test("history rendering escapes data and creates encoded links", () => {
  const html = historyMarkup([{ id: "id/1", resume_filename: '<img src=x onerror="x">.pdf', resume_score: 42,
    match_percentage: null, created_at: "today" }], (value) => value);
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img/);
  assert.match(html, /results\/id%2F1/);
  assert.match(html, /—/);
});

test("API helper returns JSON and exposes server and fallback errors", async () => {
  const ok = await requestJson(async () => ({ ok: true, json: async () => ({ id: "one" }) }), "/ok");
  assert.deepEqual(ok, { id: "one" });
  await assert.rejects(
    requestJson(async () => ({ ok: false, json: async () => ({ error: "Invalid file" }) }), "/bad"),
    /Invalid file/,
  );
  await assert.rejects(
    requestJson(async () => ({ ok: false, json: async () => { throw new Error("not json"); } }), "/bad"),
    /Something went wrong/,
  );
});
