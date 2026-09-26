// LexGuide AI — frontend application logic (no build step; vanilla JS)
const API_BASE = window.LEXGUIDE_API_BASE || "http://127.0.0.1:8000";

const state = {
  documents: [],          // list from GET /documents
  insightsCache: {},       // doc_id -> insights payload
  askDocIds: new Set(),
  briefDocIds: new Set(),
  currentWorkspaceDocId: null,
  currentClauseId: null,
};

// ---------------- Utilities ----------------
function $(sel, root = document) { return root.querySelector(sel); }
function $all(sel, root = document) { return [...root.querySelectorAll(sel)]; }

async function api(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = "Request failed.";
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    throw new Error(detail);
  }
  return res.json();
}

function toast(msg, isError = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.style.background = isError ? "#7a2622" : "#1b2430";
  el.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => { el.hidden = true; }, 3800);
}

function badge(level) {
  const map = { HIGH: "badge-high", MEDIUM: "badge-medium", LOW: "badge-low" };
  return `<span class="badge ${map[level] || "badge-low"}">${level}</span>`;
}

function escapeHtml(str) {
  return (str || "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------------- Tab navigation ----------------
function initTabs() {
  $all(".tab").forEach(btn => {
    btn.addEventListener("click", () => activateTab(btn.dataset.tab));
  });
  $all("[data-goto]").forEach(btn => {
    btn.addEventListener("click", () => activateTab(btn.dataset.goto));
  });
}

function activateTab(name) {
  $all(".tab").forEach(t => {
    const active = t.dataset.tab === name;
    t.classList.toggle("active", active);
    t.setAttribute("aria-selected", String(active));
  });
  $all(".tab-panel").forEach(p => p.classList.toggle("active", p.id === `tab-${name}`));
  if (name === "documents") refreshDocumentsUI();
  if (name === "workspace") refreshWorkspaceSelectors();
  if (name === "compare") refreshCompareSelectors();
  if (name === "ask") refreshAskPicker();
  if (name === "actionplan") refreshActionPlanSelector();
  if (name === "brief") refreshBriefPicker();
  if (name === "privacy") refreshPrivacyUI();
  if (name === "dashboard") refreshDashboard();
}

// ---------------- Document loading ----------------
async function loadDocuments() {
  state.documents = await api("/documents");
  return state.documents;
}

async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  form.append("jurisdiction", $("#jurisdictionSelect")?.value || "Not specified");
  toast(`Uploading ${file.name}…`);
  try {
    const doc = await api("/documents/upload", { method: "POST", body: form });
    if (doc.status === "error") {
      toast(`${doc.filename} could not be processed: ${doc.error_message}`, true);
    } else {
      toast(`${doc.filename} analyzed — ${doc.status}.`);
    }
    if (doc.injection_flagged) {
      toast("⚠ " + doc.injection_note, true);
    }
    if (doc.content_mismatch) {
      toast("⚠ " + doc.content_mismatch_note, true);
    }
    await loadDocuments();
    refreshDocumentsUI();
    refreshDashboard();
  } catch (e) {
    toast("Upload failed: " + e.message, true);
  }
}

function initUpload() {
  const dz = $("#dropzone");
  const input = $("#fileInput");
  dz.addEventListener("click", () => input.click());
  dz.addEventListener("keydown", e => { if (e.key === "Enter") input.click(); });
  input.addEventListener("change", () => { if (input.files[0]) uploadFile(input.files[0]); });
  ["dragover", "dragenter"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("dragover"); }));
  ["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("dragover"); }));
  dz.addEventListener("drop", e => {
    const file = e.dataTransfer.files[0];
    if (file) uploadFile(file);
  });

  $all("[data-demo]").forEach(btn => {
    btn.addEventListener("click", () => loadDemoDoc(btn.dataset.demo));
  });
}

const DEMO_FILES = {
  employment_v1: "demo-data/employment_agreement_v1.txt",
  employment_v2: "demo-data/employment_agreement_v2.txt",
  nda: "demo-data/nda.txt",
  rental: "demo-data/rental_agreement.txt",
};

async function loadDemoDoc(key) {
  try {
    const resp = await fetch(DEMO_FILES[key]);
    if (!resp.ok) throw new Error("Demo file not found — is the frontend served from its own folder?");
    const blob = await resp.blob();
    const filename = DEMO_FILES[key].split("/").pop();
    const file = new File([blob], filename, { type: "text/plain" });
    await uploadFile(file);
  } catch (e) {
    toast("Could not load demo document: " + e.message, true);
  }
}

function refreshDocumentsUI() {
  const tbody = $("#docTable tbody");
  tbody.innerHTML = "";
  state.documents.forEach(doc => {
    const tr = document.createElement("tr");
    const isError = doc.status === "error";
    tr.innerHTML = `
      <td>${escapeHtml(doc.filename)}</td>
      <td>${escapeHtml(doc.doc_type)}</td>
      <td>${doc.pages}</td>
      <td>${doc.word_count}</td>
      <td>${isError ? `<span class="badge badge-high">error</span> <span class="muted small">${escapeHtml(doc.error_message)}</span>` : `${doc.status}${doc.ocr_used ? " · OCR" : ""}`}</td>
      <td>
        ${isError
          ? `<button class="btn btn-secondary" data-retry="${doc.id}">Retry</button>`
          : `<button class="btn btn-secondary" data-open="${doc.id}">Open</button>`}
        <button class="btn btn-danger" data-del="${doc.id}">Delete</button>
      </td>`;
    tbody.appendChild(tr);
  });
  $all("[data-open]", tbody).forEach(b => b.addEventListener("click", () => {
    state.currentWorkspaceDocId = b.dataset.open;
    activateTab("workspace");
  }));
  $all("[data-retry]", tbody).forEach(b => b.addEventListener("click", async () => {
    try {
      const doc = await api(`/documents/${b.dataset.retry}/reprocess`, { method: "POST" });
      toast(doc.status === "error" ? `Retry failed: ${doc.error_message}` : `${doc.filename} reprocessed successfully.`, doc.status === "error");
      await loadDocuments();
      refreshDocumentsUI();
      refreshDashboard();
    } catch (e) {
      toast("Retry failed: " + e.message, true);
    }
  }));
  $all("[data-del]", tbody).forEach(b => b.addEventListener("click", async () => {
    await api(`/documents/${b.dataset.del}`, { method: "DELETE" });
    toast("Document deleted.");
    await loadDocuments();
    refreshDocumentsUI();
    refreshDashboard();
  }));
}

// ---------------- Dashboard ----------------
async function refreshDashboard() {
  await loadDocuments();
  const recent = $("#dashRecentDocs");
  recent.innerHTML = state.documents.length
    ? state.documents.slice(0, 5).map(d => `
        <div class="doc-list-item">
          <span>${escapeHtml(d.filename)} <span class="muted small">(${escapeHtml(d.doc_type)})</span></span>
          <button data-open="${d.id}">Open →</button>
        </div>`).join("")
    : `<p class="muted small">No documents yet. Upload one to get started.</p>`;
  $all("[data-open]", recent).forEach(b => b.addEventListener("click", () => {
    state.currentWorkspaceDocId = b.dataset.open;
    activateTab("workspace");
  }));

  if (!state.documents.length) {
    $("#dashAttention").textContent = "No documents analyzed yet.";
    $("#dashDeadlines").textContent = "No documents analyzed yet.";
    return;
  }

  let totalAttn = 0, totalDeadlines = 0;
  const deadlineLines = [];
  for (const doc of state.documents.slice(0, 6)) {
    try {
      const ins = await getInsights(doc.id);
      totalAttn += (ins.attention_counts.HIGH || 0) + (ins.attention_counts.MEDIUM || 0);
      totalDeadlines += ins.deadlines.length;
      ins.deadlines.slice(0, 2).forEach(d => deadlineLines.push(`${escapeHtml(doc.filename)}: ${escapeHtml(d.date_text)}`));
    } catch (_) {}
  }
  $("#dashAttention").innerHTML = `<b style="font-size:1.4rem">${totalAttn}</b> clause(s) across your documents may warrant review.`;
  $("#dashDeadlines").innerHTML = totalDeadlines
    ? `<b style="font-size:1.4rem">${totalDeadlines}</b> date reference(s) detected.<br>` + deadlineLines.slice(0, 4).join("<br>")
    : "No deadlines detected yet.";
}

// ---------------- Insights (cached) ----------------
async function getInsights(docId, force = false) {
  if (!force && state.insightsCache[docId]) return state.insightsCache[docId];
  const data = await api(`/documents/${docId}/insights`);
  state.insightsCache[docId] = data;
  return data;
}

// ---------------- Workspace ----------------
function refreshWorkspaceSelectors() {
  const sel = $("#workspaceDocSelect");
  sel.innerHTML = state.documents.map(d => `<option value="${d.id}">${escapeHtml(d.filename)}</option>`).join("");
  if (state.currentWorkspaceDocId) sel.value = state.currentWorkspaceDocId;
  else if (state.documents[0]) state.currentWorkspaceDocId = state.documents[0].id;
  if (state.currentWorkspaceDocId) sel.value = state.currentWorkspaceDocId;
  sel.onchange = () => { state.currentWorkspaceDocId = sel.value; renderWorkspace(sel.value); };
  if (state.currentWorkspaceDocId) renderWorkspace(state.currentWorkspaceDocId);
  else {
    $("#docMap").innerHTML = `<p class="muted small">Upload a document first.</p>`;
    $("#docViewer").innerHTML = "";
  }
}

async function renderWorkspace(docId) {
  const doc = await api(`/documents/${docId}`);
  const ins = await getInsights(docId);

  $("#ocrBadge").textContent = doc.ocr_used ? "(OCR-derived text — verify against original document)" : "";

  // Document map
  const map = $("#docMap");
  map.innerHTML = ins.clauses.map(c =>
    `<div data-jump="${c.id}">${badge(c.attention)} ${escapeHtml(c.heading || "Untitled clause")}</div>`
  ).join("") || `<p class="muted small">No sections detected.</p>`;
  $all("[data-jump]", map).forEach(el => el.addEventListener("click", () => showClauseDetail(docId, el.dataset.jump)));

  // Viewer — highlight clause spans by attention
  const clean = doc.raw_text.replace(/\[PAGE \d+\]/g, "");
  let viewerHtml = escapeHtml(clean);
  // naive highlight: wrap each clause's first 60 chars occurrence
  ins.clauses.forEach(c => {
    if (c.attention === "LOW") return;
    const snippet = c.text.slice(0, 50).trim();
    if (!snippet) return;
    const escSnippet = escapeHtml(snippet);
    if (viewerHtml.includes(escSnippet)) {
      viewerHtml = viewerHtml.replace(escSnippet, `<mark class="attn-${c.attention}" data-jump="${c.id}">${escSnippet}</mark>`);
    }
  });
  $("#docViewer").innerHTML = viewerHtml;
  $all("[data-jump]", $("#docViewer")).forEach(el => el.addEventListener("click", () => showClauseDetail(docId, el.dataset.jump)));

  renderInsightTabs(docId, ins);
}

function renderInsightTabs(docId, ins) {
  $("#insight-summary").innerHTML = `
    <p>${escapeHtml(ins.executive_summary)}</p>
    <h3>Document Understanding</h3>
    ${Object.entries(ins.understanding).map(([field, v]) => `
      <div class="clause-card" style="cursor:default">
        <div class="ch-head"><span>${escapeHtml(field)}</span></div>
        <div class="ch-reason">${escapeHtml(v.value)}${v.source ? ` <span class="muted small">— p.${v.source.page}</span>` : ""}</div>
      </div>`).join("")}
    <p class="muted small">Analytics: ${ins.analytics.clauses_detected} clauses · ${ins.analytics.obligations_detected} obligations · ${ins.analytics.deadlines_detected} dates · ${ins.analytics.attention_areas} attention areas</p>
  `;

  $("#insight-risks").innerHTML = ins.clauses
    .filter(c => c.attention !== "LOW")
    .sort((a, b) => (a.attention === "HIGH" ? -1 : 1))
    .map(c => `
      <div class="clause-card" data-jump="${c.id}">
        <div class="ch-head"><span>${escapeHtml(c.heading || c.category)}</span>${badge(c.attention)}</div>
        <div class="ch-reason">${escapeHtml(c.reason)}</div>
      </div>`).join("") || `<p class="muted small">No elevated-attention clauses detected.</p>`;
  $all("[data-jump]", $("#insight-risks")).forEach(el => el.addEventListener("click", () => showClauseDetail(docId, el.dataset.jump)));

  $("#insight-obligations").innerHTML = ins.obligations.length
    ? `<table class="doc-table"><thead><tr><th>Done</th><th>Who</th><th>What</th><th>When</th><th>Source</th></tr></thead><tbody>${
        ins.obligations.map(o => `<tr class="${o.completed ? "obligation-done" : ""}">
          <td><input type="checkbox" data-obligation="${o.id}" ${o.completed ? "checked" : ""} aria-label="Mark obligation complete" /></td>
          <td>${escapeHtml(o.who)}</td><td>${escapeHtml(o.what)}</td><td>${escapeHtml(o.when)}</td>
          <td class="muted small">${escapeHtml(o.source_heading || "")}${o.page ? " · p." + o.page : ""}</td>
        </tr>`).join("")
      }</tbody></table>`
    : `<p class="muted small">No obligation statements automatically detected.</p>`;
  $all("[data-obligation]", $("#insight-obligations")).forEach(cb => cb.addEventListener("change", async () => {
    try {
      await api(`/documents/${docId}/obligations/${cb.dataset.obligation}?completed=${cb.checked}`, { method: "PATCH" });
      cb.closest("tr").classList.toggle("obligation-done", cb.checked);
      if (state.insightsCache[docId]) {
        const ob = state.insightsCache[docId].obligations.find(o => o.id === cb.dataset.obligation);
        if (ob) ob.completed = cb.checked;
      }
    } catch (e) {
      toast("Could not update obligation: " + e.message, true);
      cb.checked = !cb.checked;
    }
  }));

  $("#insight-dates").innerHTML = ins.deadlines.length
    ? ins.deadlines.map(d => `<div class="clause-card" style="cursor:default"><div class="ch-head"><span>${escapeHtml(d.date_text)}</span></div><div class="ch-reason">${escapeHtml(d.label)}</div></div>`).join("")
    : `<p class="muted small">No dates automatically detected.</p>`;

  $("#insight-health").innerHTML = ins.health_check.map(h => `
    <div class="clause-card" style="cursor:default">
      <div class="ch-head"><span>${escapeHtml(h.type)}</span>${badge(h.severity)}</div>
      <div class="ch-reason">${escapeHtml(h.detail)}</div>
    </div>`).join("");
}

function initInsightTabs() {
  $all(".itab").forEach(btn => {
    btn.addEventListener("click", () => {
      $all(".itab").forEach(b => b.classList.toggle("active", b === btn));
      $all(".insight-body").forEach(b => b.classList.toggle("active", b.id === `insight-${btn.dataset.itab}`));
    });
  });
}

let glossaryTerms = [];

async function initGlossary() {
  try {
    const data = await api("/documents/glossary/terms");
    glossaryTerms = data.terms;
    const sel = $("#glossaryTermSelect");
    sel.innerHTML = glossaryTerms.map(t => `<option value="${t}">${t.replace(/\b\w/g, c => c.toUpperCase())}</option>`).join("");
  } catch (e) { /* glossary is a nice-to-have; fail silently if unreachable */ }

  $("#glossaryLookupBtn").addEventListener("click", async () => {
    const term = $("#glossaryTermSelect").value;
    const docId = state.currentWorkspaceDocId;
    const resultEl = $("#glossaryResult");
    if (!docId) { toast("Open a document in the Workspace first.", true); return; }
    resultEl.innerHTML = `<p class="muted small">Looking up…</p>`;
    try {
      const data = await api(`/documents/${docId}/glossary/${encodeURIComponent(term)}`);
      resultEl.innerHTML = `
        <div class="clause-card" style="cursor:default">
          <div class="ch-head"><span>${escapeHtml(data.term.replace(/\b\w/g, c => c.toUpperCase()))}</span></div>
          <p><b>Simple definition:</b> ${escapeHtml(data.simple)}</p>
          <p><b>Example:</b> ${escapeHtml(data.example)}</p>
          <p><b>Why it matters:</b> ${escapeHtml(data.why_it_matters)}</p>
          <p><b>In this document:</b> ${data.found_in_document
            ? `<span class="cd-orig">${escapeHtml(data.document_context)}</span>`
            : `<span class="muted small">Not found in document</span>`}</p>
          <p class="muted small">${escapeHtml(data.note)}</p>
        </div>`;
    } catch (e) {
      resultEl.innerHTML = `<p class="muted small">${escapeHtml(e.message)}</p>`;
    }
  });
}

async function showClauseDetail(docId, clauseId) {
  const panel = $("#clauseDetailPanel");
  panel.hidden = false;
  panel.innerHTML = `<p class="muted small">Loading plain-language explanation…</p>`;
  panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
  try {
    const data = await api(`/documents/${docId}/explain-clause/${clauseId}`, { method: "POST" });
    const c = data.clause;
    panel.innerHTML = `
      <h3>${escapeHtml(c.heading || c.category)} ${badge(c.attention)}</h3>
      <div class="cd-section"><div class="cd-label">Original clause</div><div class="cd-orig">${escapeHtml(c.text)}</div></div>
      <div class="cd-section"><div class="cd-label">In simple terms</div><p>${escapeHtml(data.plain_language.simple)}</p></div>
      <div class="cd-section"><div class="cd-label">Why this matters</div><p>${escapeHtml(data.plain_language.why_it_matters)}</p></div>
      <div class="cd-section"><div class="cd-label">Questions to consider</div>
        <ul>${data.plain_language.questions.map(q => `<li>${escapeHtml(q)}</li>`).join("")}</ul></div>
      <div class="cd-source">Source: ${escapeHtml(data.source_type)} — page ${c.page ?? "n/a"}. Why am I seeing this? ${escapeHtml(c.reason)}</div>
    `;
  } catch (e) {
    panel.innerHTML = `<p class="muted small">Could not load explanation: ${escapeHtml(e.message)}</p>`;
  }
}

// ---------------- Compare ----------------
let activeCompareFilter = null;

function refreshCompareSelectors() {
  const a = $("#compareDocA"), b = $("#compareDocB");
  const opts = state.documents.map(d => `<option value="${d.id}">${escapeHtml(d.filename)}</option>`).join("");
  a.innerHTML = opts; b.innerHTML = opts;
  if (state.documents.length > 1) b.selectedIndex = 1;
}

function initCompare() {
  $("#runCompareBtn").addEventListener("click", runCompare);
}

async function runCompare() {
  const a = $("#compareDocA").value, b = $("#compareDocB").value;
  if (!a || !b || a === b) { toast("Pick two different documents to compare.", true); return; }
  try {
    const result = await api("/compare", { method: "POST", body: JSON.stringify({ document_a_id: a, document_b_id: b }) });
    renderCompareResult(result);
  } catch (e) {
    toast("Comparison failed: " + e.message, true);
  }
}

function renderCompareResult(result) {
  $("#compareSummary").innerHTML = `
    <div><b>${result.summary.added_count}</b>Added</div>
    <div><b>${result.summary.removed_count}</b>Removed</div>
    <div><b>${result.summary.modified_count}</b>Modified</div>`;

  const filters = $("#compareFilters");
  filters.innerHTML = result.filterable_categories.map(c => `<button data-f="${c}">${c}</button>`).join("") +
    `<button data-f="__all">All changes</button>`;
  activeCompareFilter = null;
  $all("button", filters).forEach(btn => btn.addEventListener("click", () => {
    activeCompareFilter = btn.dataset.f === "__all" ? null : btn.dataset.f;
    $all("button", filters).forEach(b => b.classList.toggle("active", b === btn));
    renderCompareCards(result);
  }));

  renderCompareCards(result);
}

function renderCompareCards(result) {
  const container = $("#compareResults");
  const filt = c => !activeCompareFilter || c.category === activeCompareFilter;
  let html = "";

  result.added.filter(filt).forEach(c => {
    html += `<div class="diff-card diff-added"><div class="diff-head"><b>+ Added: ${escapeHtml(c.heading)}</b><span class="muted small">${escapeHtml(c.category)} · p.${c.page}</span></div><p>${escapeHtml(c.text)}</p></div>`;
  });
  result.removed.filter(filt).forEach(c => {
    html += `<div class="diff-card diff-removed"><div class="diff-head"><b>− Removed: ${escapeHtml(c.heading)}</b><span class="muted small">${escapeHtml(c.category)} · p.${c.page}</span></div><p>${escapeHtml(c.text)}</p></div>`;
  });
  result.modified.filter(filt).forEach(c => {
    html += `<div class="diff-card diff-modified">
      <div class="diff-head"><b>~ ${escapeHtml(c.heading)}</b>${badge(c.attention)}</div>
      <div class="diff-cols">
        <div class="diff-old"><b>Previous</b> (p.${c.previous_page})<br>${escapeHtml(c.previous)}</div>
        <div class="diff-new"><b>New</b> (p.${c.new_page})<br>${escapeHtml(c.new)}</div>
      </div>
      <p class="muted small" style="margin-top:8px">${escapeHtml(c.change_summary)}</p>
    </div>`;
  });

  container.innerHTML = html || `<p class="muted small">No changes in this category.</p>`;
}

// ---------------- Ask ----------------
function refreshAskPicker() {
  const picker = $("#askDocPicker");
  picker.innerHTML = state.documents.map(d =>
    `<button class="chip ${state.askDocIds.has(d.id) ? "active" : ""}" data-id="${d.id}">${escapeHtml(d.filename)}</button>`
  ).join("") || `<p class="muted small">Upload a document to start asking questions.</p>`;
  $all("button[data-id]", picker).forEach(chip => chip.addEventListener("click", () => {
    const id = chip.dataset.id;
    if (state.askDocIds.has(id)) state.askDocIds.delete(id); else state.askDocIds.add(id);
    chip.classList.toggle("active");
    toggleCrossDocPanel();
  }));
  if (state.askDocIds.size === 0 && state.documents.length) {
    state.askDocIds.add(state.documents[0].id);
    refreshAskPicker();
  }
  toggleCrossDocPanel();
}

function toggleCrossDocPanel() {
  $("#crossDocPanel").hidden = state.askDocIds.size !== 2;
}

function initCrossDocAsk() {
  $("#crossDocForm").addEventListener("submit", async e => {
    e.preventDefault();
    const question = $("#crossDocInput").value.trim();
    if (!question || state.askDocIds.size !== 2) return;
    const [a, b] = [...state.askDocIds];
    const resultEl = $("#crossDocResult");
    resultEl.innerHTML = `<p class="muted small">Comparing…</p>`;
    try {
      const res = await api("/questions/cross-document", {
        method: "POST",
        body: JSON.stringify({ document_a_id: a, document_b_id: b, question }),
      });
      resultEl.innerHTML = `
        <div class="ask-msg-ai">
          <p><b>${escapeHtml(res.document_a)}</b> vs <b>${escapeHtml(res.document_b)}</b></p>
          <p>${escapeHtml(res.answer)}</p>
          <div class="diff-cols">
            <div class="diff-old"><b>${escapeHtml(res.document_a)}</b><br>${
              res.evidence_a.map(e => `<span class="muted small">p.${e.page ?? "n/a"}: "${escapeHtml(e.excerpt)}…"</span><br>`).join("") || "<span class=\"muted small\">No relevant evidence found.</span>"
            }</div>
            <div class="diff-new"><b>${escapeHtml(res.document_b)}</b><br>${
              res.evidence_b.map(e => `<span class="muted small">p.${e.page ?? "n/a"}: "${escapeHtml(e.excerpt)}…"</span><br>`).join("") || "<span class=\"muted small\">No relevant evidence found.</span>"
            }</div>
          </div>
          ${res.potential_conflicts && res.potential_conflicts.length ? `
            <div class="conflict-block">
              <b>⚠ Potential conflicts detected:</b>
              ${res.potential_conflicts.map(c => `
                <div class="clause-card" style="cursor:default">
                  <div class="ch-head"><span>${escapeHtml(c.category)}</span></div>
                  <div class="ch-reason">${escapeHtml(c.document_a.name)}: ${escapeHtml(c.document_a.values.join(", "))}
                    vs ${escapeHtml(c.document_b.name)}: ${escapeHtml(c.document_b.values.join(", "))}<br>
                    ${escapeHtml(c.note)}</div>
                </div>`).join("")}
            </div>` : ""}
        </div>`;
      $("#crossDocInput").value = "";
    } catch (err) {
      resultEl.innerHTML = `<p class="muted small">Could not complete cross-document comparison: ${escapeHtml(err.message)}</p>`;
    }
  });
}

function initAsk() {
  $("#askForm").addEventListener("submit", e => { e.preventDefault(); submitQuestion($("#askInput").value); });
  $all(".chip[data-q]").forEach(c => c.addEventListener("click", () => submitQuestion(c.dataset.q)));
  initCrossDocAsk();
}

async function submitQuestion(question) {
  question = (question || "").trim();
  if (!question) return;
  if (state.askDocIds.size === 0) { toast("Select at least one document first.", true); return; }
  $("#askInput").value = "";
  const thread = $("#askThread");
  thread.insertAdjacentHTML("beforeend", `<div class="ask-msg-user">${escapeHtml(question)}</div>`);
  const loadingId = "loading-" + Date.now();
  thread.insertAdjacentHTML("beforeend", `<div class="ask-msg-ai" id="${loadingId}"><span class="streaming-text"></span></div>`);
  thread.scrollTop = thread.scrollHeight;
  const bubble = document.getElementById(loadingId);
  const textSpan = bubble.querySelector(".streaming-text");

  try {
    // Real network streaming (Server-Sent Events) -- tokens are appended to
    // the DOM as they arrive over the wire, not simulated client-side.
    const res = await fetch(`${API_BASE}/questions/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, document_ids: [...state.askDocIds] }),
    });
    if (!res.ok || !res.body) throw new Error(`Request failed (${res.status})`);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let finalData = null;
    let streamedText = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop(); // keep the last, possibly-incomplete chunk
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        const payload = JSON.parse(line.slice(6));
        if (payload.type === "token") {
          streamedText += payload.text;
          textSpan.textContent = streamedText;
          thread.scrollTop = thread.scrollHeight;
        } else if (payload.type === "done") {
          finalData = payload;
        }
      }
    }

    const res2 = finalData || { grounded: false, evidence: [] };
    const groundingTag = res2.grounded
      ? `<span class="grounding-tag grounding-yes">Grounded in uploaded documents</span>`
      : `<span class="grounding-tag grounding-no">Not found in uploaded documents</span>`;
    const evidenceHtml = (res2.evidence || []).length
      ? `<div class="ask-evidence">${res2.evidence.map(e => `
          <div class="ev-item"><b>${escapeHtml(e.document_name)}</b> — p.${e.page ?? "n/a"}, ${escapeHtml(e.section || "unspecified section")}<br>
          <span class="muted small">"${escapeHtml(e.excerpt)}…"</span></div>`).join("")}</div>`
      : "";
    bubble.innerHTML = `
      <p>${escapeHtml(streamedText)}</p>
      ${groundingTag}
      ${evidenceHtml}
      ${res2.injection_notice ? `<p class="muted small">⚠ ${escapeHtml(res2.injection_notice)}</p>` : ""}`;
  } catch (e) {
    bubble.outerHTML = `<div class="ask-msg-ai">Something went wrong: ${escapeHtml(e.message)}</div>`;
  }
  thread.scrollTop = thread.scrollHeight;
}

// ---------------- Action plan ----------------
function refreshActionPlanSelector() {
  const sel = $("#actionPlanDocSelect");
  sel.innerHTML = state.documents.map(d => `<option value="${d.id}">${escapeHtml(d.filename)}</option>`).join("");
}

function initActionPlan() {
  $("#generatePlanBtn").addEventListener("click", async () => {
    const docId = $("#actionPlanDocSelect").value;
    if (!docId) { toast("Upload a document first.", true); return; }
    try {
      const res = await api("/action-plan", { method: "POST", body: JSON.stringify({ document_id: docId }) });
      renderActionPlan(res.grouped);
    } catch (e) {
      toast("Could not generate action plan: " + e.message, true);
    }
  });
}

const AP_LABELS = { DO_NOW: "Do Now", VERIFY: "Verify", ASK_OTHER_PARTY: "Ask the Other Party", ASK_LAWYER: "Ask a Legal Professional" };

function renderActionPlan(grouped) {
  const container = $("#actionPlanResults");
  container.innerHTML = Object.entries(AP_LABELS).map(([key, label]) => `
    <div class="ap-col">
      <h3>${label}</h3>
      ${(grouped[key] || []).map(item => `
        <div class="ap-item">${escapeHtml(item.text)}
          ${item.source ? `<div class="src">${escapeHtml(item.source.heading || "")}${item.source.page ? " · p." + item.source.page : ""}</div>` : ""}
        </div>`).join("") || `<p class="muted small">Nothing in this category.</p>`}
    </div>`).join("");
}

// ---------------- Consultation brief ----------------
function refreshBriefPicker() {
  const picker = $("#briefDocPicker");
  picker.innerHTML = state.documents.map(d =>
    `<button class="chip ${state.briefDocIds.has(d.id) ? "active" : ""}" data-id="${d.id}">${escapeHtml(d.filename)}</button>`
  ).join("") || `<p class="muted small">Upload a document first.</p>`;
  $all("button[data-id]", picker).forEach(chip => chip.addEventListener("click", () => {
    const id = chip.dataset.id;
    if (state.briefDocIds.has(id)) state.briefDocIds.delete(id); else state.briefDocIds.add(id);
    chip.classList.toggle("active");
  }));
}

function initBrief() {
  $("#generateBriefBtn").addEventListener("click", async () => {
    if (state.briefDocIds.size === 0) { toast("Select at least one document.", true); return; }
    try {
      const res = await api("/consultation-brief", {
        method: "POST",
        body: JSON.stringify({ document_ids: [...state.briefDocIds], concerns: $("#briefConcerns").value }),
      });
      renderBrief(res);
    } catch (e) {
      toast("Could not generate brief: " + e.message, true);
    }
  });
}

function renderBrief(brief) {
  $("#briefResult").innerHTML = `
    <div class="brief-export-bar">
      <span class="muted small">Export:</span>
      <button class="btn btn-secondary" data-export="txt">TXT</button>
      <button class="btn btn-secondary" data-export="docx">DOCX</button>
      <button class="btn btn-secondary" data-export="pdf">PDF</button>
    </div>
    <h2>Legal Consultation Brief</h2>
    <p><b>Matter:</b> ${escapeHtml(brief.matter)}</p>
    <p>${escapeHtml(brief.situation_summary)}</p>
    <h3>Documents Reviewed</h3>
    <ul>${brief.documents_reviewed.map(d => `<li>${escapeHtml(d.filename)} (${escapeHtml(d.type)})</li>`).join("")}</ul>
    <h3>Key Areas</h3>
    <ul>${brief.key_areas.map(a => `<li>${escapeHtml(a)}</li>`).join("") || "<li>None flagged</li>"}</ul>
    <h3>Questions for Your Lawyer</h3>
    <ol>${brief.questions.map(q => `<li>${escapeHtml(q)}</li>`).join("")}</ol>
    <h3>Important Dates</h3>
    <ul>${brief.important_dates.map(d => `<li>${escapeHtml(d.document)}: ${escapeHtml(d.date)} — ${escapeHtml(d.context)}</li>`).join("") || "<li>None detected</li>"}</ul>
    <h3>Missing Information</h3>
    <ul>${brief.missing_information.map(m => `<li>${escapeHtml(m)}</li>`).join("") || "<li>None</li>"}</ul>
    <div class="disclaimer">${escapeHtml(brief.disclaimer)}</div>
  `;
  $all("[data-export]", $("#briefResult")).forEach(btn => {
    btn.addEventListener("click", () => {
      window.open(`${API_BASE}/consultation-brief/${brief.id}/export?format=${btn.dataset.export}`, "_blank");
    });
  });
}

// ---------------- Privacy ----------------
function refreshPrivacyUI() {
  const list = $("#privacyDocList");
  list.innerHTML = state.documents.map(d => `
    <div class="doc-list-item"><span>${escapeHtml(d.filename)}</span><button data-del="${d.id}">Delete</button></div>
  `).join("") || `<p class="muted small">No documents stored.</p>`;
  $all("[data-del]", list).forEach(b => b.addEventListener("click", async () => {
    await api(`/documents/${b.dataset.del}`, { method: "DELETE" });
    await loadDocuments();
    refreshPrivacyUI();
    toast("Document deleted.");
  }));

  api("/health").then(h => {
    $("#apiStatus").textContent = `Connected to ${h.app} (${h.env}) · AI provider: ${h.llm_provider}`;
  }).catch(() => { $("#apiStatus").textContent = "Could not reach backend API."; });
}

function initPrivacy() {
  $("#deleteAllBtn").addEventListener("click", async () => {
    if (!confirm("Delete ALL documents and analysis data? This cannot be undone.")) return;
    const res = await api("/documents", { method: "DELETE" });
    toast(`Deleted ${res.count} document(s).`);
    state.insightsCache = {};
    state.askDocIds.clear();
    state.briefDocIds.clear();
    await loadDocuments();
    refreshPrivacyUI();
    refreshDashboard();
  });
}

// ---------------- Accessibility ----------------
function initAccessibility() {
  const btn = $("#accessibilityToggle");
  btn.addEventListener("click", () => {
    const on = document.body.classList.toggle("a11y-mode");
    btn.setAttribute("aria-pressed", String(on));
    toast(on ? "Accessibility mode on." : "Accessibility mode off.");
  });
}

// ---------------- Guided demo ----------------
const GUIDED_STEPS = [
  { text: "Welcome to LexGuide AI. This guided demo walks through a complete document review journey in a few clicks.", tab: "dashboard" },
  { text: "First, load a demo document — we'll use the Employment Agreement.", action: async () => { await loadDemoDoc("employment_v1"); }, tab: "documents" },
  { text: "The system analyzed the document automatically: summary, parties, obligations, and attention areas.", tab: "workspace", action: async () => { if (state.documents[0]) { state.currentWorkspaceDocId = state.documents.find(d => d.filename.includes("v1"))?.id || state.documents[0].id; renderWorkspace(state.currentWorkspaceDocId); } } },
  { text: "Click any highlighted clause to see it explained in plain language, with the exact source.", tab: "workspace" },
  { text: "Now let's ask a grounded question about the document.", tab: "ask", action: async () => { state.askDocIds = new Set([state.documents.find(d => d.filename.includes("v1"))?.id]); refreshAskPicker(); await submitQuestion("What happens if I terminate this agreement?"); } },
  { text: "Let's compare this against a revised version of the contract.", tab: "documents", action: async () => { await loadDemoDoc("employment_v2"); } },
  { text: "Compare shows exactly what changed — added, removed, and modified clauses, with evidence.", tab: "compare", action: async () => {
      refreshCompareSelectors();
      const v1 = state.documents.find(d => d.filename.includes("v1"));
      const v2 = state.documents.find(d => d.filename.includes("v2"));
      if (v1 && v2) { $("#compareDocA").value = v1.id; $("#compareDocB").value = v2.id; await runCompare(); }
    } },
  { text: "The Action Plan turns analysis into concrete next steps, categorized by urgency.", tab: "actionplan", action: async () => {
      refreshActionPlanSelector();
      const v1 = state.documents.find(d => d.filename.includes("v1"));
      if (v1) { $("#actionPlanDocSelect").value = v1.id; $("#generatePlanBtn").click(); }
    } },
  { text: "Finally, generate a Legal Consultation Brief to bring to a qualified professional.", tab: "brief", action: async () => {
      const v1 = state.documents.find(d => d.filename.includes("v1"));
      if (v1) { state.briefDocIds = new Set([v1.id]); refreshBriefPicker(); $("#generateBriefBtn").click(); }
    } },
  { text: "That's the full journey: Document → Understand → Verify → Compare → Identify Risks → Ask → Act. LexGuide AI doesn't replace legal professionals — it helps you understand what you have, what to look at, and what to ask.", tab: "brief" },
];

let guidedIndex = 0;

function initGuidedDemo() {
  $("#guidedDemoBtn").addEventListener("click", startGuidedDemo);
  $("#guidedNext").addEventListener("click", advanceGuidedDemo);
  $("#guidedSkip").addEventListener("click", stopGuidedDemo);
}

function startGuidedDemo() {
  guidedIndex = 0;
  $("#guidedOverlay").hidden = false;
  runGuidedStep();
}

async function runGuidedStep() {
  const step = GUIDED_STEPS[guidedIndex];
  $("#guidedStepText").textContent = step.text;
  $("#guidedProgressBar").style.width = `${((guidedIndex + 1) / GUIDED_STEPS.length) * 100}%`;
  $("#guidedNext").textContent = guidedIndex === GUIDED_STEPS.length - 1 ? "Finish" : "Next →";
  if (step.tab) activateTab(step.tab);
  if (step.action) { try { await step.action(); } catch (e) { console.error(e); } }
}

async function advanceGuidedDemo() {
  if (guidedIndex >= GUIDED_STEPS.length - 1) { stopGuidedDemo(); return; }
  guidedIndex += 1;
  await runGuidedStep();
}

function stopGuidedDemo() {
  $("#guidedOverlay").hidden = true;
}

// ---------------- Init ----------------
async function init() {
  initTabs();
  initUpload();
  initInsightTabs();
  initGlossary();
  initCompare();
  initAsk();
  initActionPlan();
  initBrief();
  initPrivacy();
  initAccessibility();
  initGuidedDemo();

  try {
    await loadDocuments();
  } catch (e) {
    toast("Could not reach the LexGuide AI backend at " + API_BASE + ". Is it running?", true);
  }
  refreshDashboard();
}

document.addEventListener("DOMContentLoaded", init);
