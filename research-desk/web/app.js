let S,
  view = "dashboard",
  selected = "target24_growth",
  selectedAttempt = null,
  mode = "lessons",
  inspectTab = "evaluation",
  lastJob = null,
  selectedResearchJobId = null,
  researchInitialized = false,
  validationSnapshot = null;
const $ = (s) => document.querySelector(s);
const esc = (v) =>
  String(v ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const num = (v) =>
  Number(v).toLocaleString("en-US", { maximumFractionDigits: 2 });
const pct = (v) =>
  v == null ? "Review" : `${v < 0 ? "−" : ""}${Math.abs(v).toFixed(2)}%`;
const prose = (v) =>
  esc(v)
    .replaceAll("revenue_growth", "revenue growth")
    .replaceAll("operating_margin", "operating margin");
const task = (t) =>
  t === "operating_margin" ? "Operating margin" : "Revenue growth";
const names = {
  target_separate_sales_total_revenue:
    "Sales and Total revenue separately reported",
  target_2024_new: "All-revenue Net Sales",
  costco_net_sales_plus_fees: "Net sales plus membership fees",
};
const scope = (p) =>
  names[p.report] ||
  (p.report?.startsWith("new_convention:")
    ? "Separately scoped report"
    : p.report);
const when = (t) =>
  new Date(t * 1000).toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
const icon = (n) =>
  `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true">${{ arrow: '<path d="M5 12h14m-6-6 6 6-6 6"/>', check: '<path d="m5 12 4 4L19 6"/>', spark: '<path d="m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z"/>', download: '<path d="M12 3v12m-5-5 5 5 5-5M5 17v4h14v-4"/>' }[n] || ""}</svg>`;
const button = (label, action, cls = "", disabled = false, attrs = "") =>
  `<button class="button ${cls}" data-action="${action}" ${disabled ? "disabled" : ""} ${attrs}>${label}</button>`;
const activeJob = () =>
  S?.jobs.find((j) => ["queued", "running"].includes(j.status));
const currentCase = () =>
  S.cases.find((c) => c.id === selected) ||
  S.attempts.find((a) => a.case.id === selected)?.case ||
  S.cases[0];
const currentAttempt = () => {
  if (selectedResearchJobId) {
    const j = researchJob();
    const ids = new Set(j?.result?.results?.map((a) => a.id) || []);
    return (
      S.attempts.find((a) => a.id === selectedAttempt && ids.has(a.id)) ||
      S.attempts.find((a) => a.id === j?.result?.attempt_id)
    );
  }
  return (
    S.attempts.find(
      (a) => a.id === selectedAttempt && a.case.id === selected,
    ) ||
    (workType === "brief"
      ? S.attempts.find((a) => a.case.id === selected)
      : null)
  );
};
function toast(message) {
  $("#toast").textContent = message;
  $("#toast").classList.add("visible");
  setTimeout(() => {
    $("#toast").classList.remove("visible");
    $("#toast").textContent = "";
  }, 4500);
}
async function api(path, body) {
  const response = await fetch(path, {
    method: body ? "POST" : "GET",
    headers: body
      ? { "Content-Type": "application/json", "x-workspace-token": S?.token }
      : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await response.json();
  if (!response.ok)
    throw Error(data.error || data.detail?.[0]?.msg || "The request failed.");
  return data;
}
async function refresh() {
  S = await api("/api/state");
  const validated = S.procedures.find((p) => p.validation);
  if (validated) {
    const key = validated.id + JSON.stringify(validated.validation);
    if (validationSnapshot?.key !== key) {
      validationSnapshot = {
        key,
        procedure: await api("/api/procedures/" + validated.id),
      };
    }
    S.latestValidation = validationSnapshot.procedure;
  }
  if (!researchInitialized) {
    const latest = S.jobs.find((j) => j.kind === "analysis");
    selectedResearchJobId = latest?.id || null;
    if (latest?.payload) {
      assignmentDraft = latest.payload.question || assignmentDraft;
      selectedCompanies = latest.payload.companies || selectedCompanies;
      selectedSourceId = latest.payload.source_id || "";
      mode = latest.payload.mode || mode;
      workType = latest.payload.case ? "brief" : "assignment";
      if (latest.payload.case) selected = latest.payload.case.id;
    }
    researchInitialized = true;
  }
  const j = S.jobs[0];
  if (
    j &&
    ["complete", "waiting_review"].includes(j.status) &&
    j.id !== lastJob
  ) {
    lastJob = j.id;
    if (j.result?.sources)
      sourceSearch = { items: j.result.sources, details: j.result.retrieval };
    if (j.result?.document_id) pendingCuration = j.result.document_id;
    if (j.result?.attempt_id && j.id === selectedResearchJobId) {
      const a = S.attempts.find((a) => a.id === j.result.attempt_id);
      if (a) {
        selected = a.case.id;
        selectedAttempt = a.id;
      }
    }
  }
  const research = researchJob();
  if (!selectedAttempt && research?.result?.attempt_id) {
    const a = S.attempts.find((a) => a.id === research.result.attempt_id);
    if (a) {
      selected = a.case.id;
      selectedAttempt = a.id;
    }
  }
  render();
  if (pendingCuration) {
    const id = pendingCuration;
    pendingCuration = null;
    await openCuration(id);
  }
}
function setView(next) {
  view = next;
  render();
  window.scrollTo(0, 0);
}
function hero(title) {
  return `<div class="hero"><h1>${title}</h1>${button("Inspect", "inspect", "quiet")}</div>`;
}

function render() {
  if (!S) return;
  $("#local-state").textContent = S.model.ready
    ? `${S.model.name} · Ready`
    : "Local model unavailable";
  $("#view-label").textContent = {
    dashboard: "Overview",
    research: "Research",
    memory: "Memory",
    sources: "Sources",
  }[view];
  document
    .querySelectorAll("[data-view]")
    .forEach((b) => b.classList.toggle("active", b.dataset.view === view));
  $("#main").innerHTML = {
    dashboard: dashboard,
    research: research,
    memory: memoryView,
    sources: sourcesView,
  }[view]();
}
function dashboard() {
  const accepted = S.procedures.filter((p) => p.status === "accepted");
  const pending = S.procedures.find(
    (p) => p.status === "candidate" && p.validation?.eligible,
  );
  const validated = S.latestValidation;
  const gate = validated?.validation;
  const total = gate?.rows.length || 0;
  const before = gate?.rows.filter((r) => r.before).length || 0;
  const after = gate?.rows.filter((r) => r.after).length || 0;
  const metrics = [
    ["Source packs", S.packs.length],
    ["Saved analyses", S.attempts.length],
    [
      "Procedure drafts",
      S.procedures.filter((p) => p.status === "candidate").length,
    ],
    ["Accepted procedures", accepted.length],
  ];
  return `<div class="hero dashboard-hero"><h1>Research overview</h1>${button("New analysis", "research", "primary")}</div>
  <div class="dashboard-metrics">${metrics.map(([label, value]) => `<section class="stat-card"><span>${label}</span><strong>${String(value).padStart(2, "0")}</strong></section>`).join("")}</div>
  <div class="dashboard-grid"><div class="main-column">
    <section class="panel validation-panel"><div class="panel-head"><h2>Procedure validation</h2><span class="section-label">RECORDED RUN</span></div><div class="panel-body">${gate ? `<div class="validation-context"><div><h3>${esc(validated.company)} / ${task(validated.task)}</h3><p>${validated.binding ? `${validated.binding.period_kind === "annual" ? "Annual" : "Quarterly"} · ${validated.binding.revenue_basis === "sales" ? "Sales basis" : "Total-revenue basis"}` : esc(scope(validated))}</p></div><span class="badge neutral">${total} development cases</span></div><div class="validation-layout"><div class="bar-comparison"><div class="bar-label"><span>Before</span><strong>${before}<span> / ${total}</span></strong></div><progress class="bar-progress baseline" value="${before}" max="${total}" aria-label="Before: ${before} of ${total} correct"></progress><div class="bar-label"><span>With candidate</span><strong>${after}<span> / ${total}</span></strong></div><progress class="bar-progress candidate" value="${after}" max="${total}" aria-label="With candidate: ${after} of ${total} correct"></progress></div><div class="validation-outcomes"><div><span>Gains</span><strong>${gate.gains}</strong></div><div><span>Regressions</span><strong>${gate.regressions}</strong></div></div></div><div class="panel-bottom-note"><span>${gate.applicable} applicable · ${gate.boundary} boundary cases</span>${button("Inspect cases", "procedure-detail", "quiet", false, `data-id="${esc(validated.id)}"`)}</div>` : `<p class="dashboard-empty">No validated procedure recorded.</p>${button("Open memory", "memory", "quiet")}`}</div></section>
    <section class="panel"><div class="panel-head"><h2>Analysis log</h2><span class="section-label">${S.attempts.length} SAVED</span></div>${
      S.attempts.length
        ? `<div class="source-table-wrap"><table class="recent-table"><thead><tr><th>Analysis</th><th>Result</th><th>Review</th><th></th></tr></thead><tbody>${S.attempts
            .slice(0, 5)
            .map(
              (a) =>
                `<tr><td><strong>${esc(a.case.company)} <span>· FY${a.case.period}</span></strong><small>${task(a.case.task)}</small></td><td class="tabular">${pct(a.result.result)}</td><td><span class="badge ${a.review === "reviewed" ? "" : "amber"}">${esc(a.review === "unreviewed" ? "Awaiting review" : a.review.replaceAll("_", " "))}</span></td><td>${button("Open", "open-attempt", "quiet", false, `data-id="${esc(a.id)}"`)}</td></tr>`,
            )
            .join("")}</tbody></table></div>`
        : `<p class="dashboard-empty panel-body">No saved analyses.</p>`
    }</section>
  </div><div class="side-column">
    <section class="panel approval-panel"><div class="panel-head"><h2>Review queue</h2><span class="queue-count">${pending ? "01" : "00"}</span></div><div class="panel-body">${pending ? `<span class="review-state">AWAITING APPROVAL</span><h3 class="review-title">${esc(pending.company)} / ${task(pending.task)}</h3><dl class="review-facts"><div><dt>Procedure</dt><dd>Version ${pending.version}</dd></div><div><dt>Validation</dt><dd>${pending.validation.gains} gains · ${pending.validation.regressions} regressions</dd></div><div><dt>Scope</dt><dd>${pending.binding ? `${pending.binding.period_kind === "annual" ? "Annual" : "Quarterly"} / ${pending.binding.revenue_basis === "sales" ? "Sales" : "Total revenue"}` : esc(scope(pending))}</dd></div></dl>${button("Review procedure", "accept", "primary", busyGuard(), `data-id="${esc(pending.id)}"`)}${button("Memory", "memory", "quiet")}` : `<p class="dashboard-note">No procedure awaiting approval.</p>${button("Open memory", "memory", "quiet")}`}</div></section>
    <section class="panel"><div class="panel-head"><h2>Source register</h2>${button("All sources", "sources", "quiet")}</div><div class="library-list">${S.packs.map((p, i) => `<div class="library-row"><span class="source-index">${String(i + 1).padStart(2, "0")}</span><div><strong>${esc(p.company)} <span>FY${[...new Set(p.cells.map((c) => c.period))].sort().join(" / ")}</span></strong><small>${esc(p.name || scope(p))}</small><span class="source-state ${p.source_review === "human attested" ? "checked" : ""}">${p.source_review === "human attested" ? "Checked" : "Review pending"}</span></div></div>`).join("")}</div></section>
  </div></div>`;
}
function research() {
  const c = currentCase(),
    a = currentAttempt(),
    busy = !!activeJob();
  const evidence =
    a?.case ||
    (workType === "brief" ? c : S.packs.find((p) => p.id === selectedSourceId));
  return `${hero("Research")}<div class="research-grid"><div class="main-column">${researchComposer(c, busy)}${assignmentResults()}${a ? resultCard(a) : emptyResult()}${evidence ? sourceTable(evidence, a?.result.operand_ids || []) : ""}</div><aside class="side-column">${execution(a)}<section class="panel"><div class="panel-body"><div class="source-title"><h2>Memory</h2><span class="badge neutral">${S.procedures.filter((p) => p.status === "accepted").length} accepted</span></div><p class="model-line">${a?.result.memory.length || 0} ${a?.mode === "history" ? ((a?.result.memory.length || 0) === 1 ? "correction" : "corrections") : (a?.result.memory.length || 0) === 1 ? "procedure" : "procedures"} used in this answer</p>${a?.mode === "history" && a.result.memory.length ? `<details><summary>Feedback used</summary>${a.result.memory.map((m) => `<p class="micro-copy">${esc(m.text)}</p>`).join("")}</details>` : ""}<div class="card-actions">${button("View procedures", "memory", "quiet")}</div></div></section><button class="button quiet report-link" data-action="changes">Report changes</button></aside></div>`;
}
function emptyResult() {
  const j = researchJob();
  if (j?.status === "failed" || j?.status === "interrupted")
    return `<section class="panel empty"><h3>No answer from this run</h3><p>${esc(j.message)}</p></section>`;
  if (j?.status === "complete" && !j.result?.results?.length)
    return `<section class="panel empty"><h3>Clarification needed</h3><p>${esc(j.result?.summary || "Check the assignment details.")}</p></section>`;
  if (j && ["queued", "running"].includes(j.status))
    return `<section class="panel empty"><h3>Analysis running</h3><p>Results will appear when this run is saved.</p></section>`;
  return `<section class="panel empty"><h3>No analyses yet</h3><p>Run an assignment or choose an example.</p></section>`;
}

function resultCard(a) {
  const r = a.result,
    c = a.case;
  return `<section class="panel"><div class="result-top"><span class="section-label">${esc(c.company)} · FY${c.period}</span><span class="badge ${r.status === "answer" ? "" : "amber"}">${r.status === "answer" ? icon("check") + " Arithmetic checked" : "Review requested"}</span></div><div class="result-body"><div class="result-number-row"><div class="result-value">${pct(r.result)}</div><div class="result-description">${task(c.task)}<br />${c.revenue_basis === "sales" ? "On the requested Sales basis" : "On the requested total-revenue basis"}</div></div>${r.formula ? `<div class="formula">${esc(r.formula)}</div>` : ""}<div class="operands">${r.sources.map((v, i) => `<div class="operand"><span class="label">${esc(v.label)}</span><strong>${num(v.value)}</strong><small>FY${v.period} · ${esc(v.unit)}</small><small class="operand-location">${esc(v.location || "")}</small></div>`).join("")}</div>${r.explanation ? `<details class="answer-details"><summary>Reasoning</summary><p class="explanation">${prose(r.explanation)}</p></details>` : ""}${r.procedure_execution ? `<details class="answer-details"><summary>${r.procedure_execution.status === "applied" ? "Procedure applied" : "Procedure needs review"}</summary>${r.procedure_execution.actions.map((action) => `<p class="explanation">Saved procedure v${action.version}: matched ${esc(action.binding.first_label)} first and ${esc(action.binding.second_label)} second in the requested ${action.binding.period_kind} source columns.</p>`).join("")}${r.procedure_execution.issue ? `<p>${esc(r.procedure_execution.issue)}</p>` : ""}</details>` : ""}${r.qualification ? `<div class="qualification"><strong>Note</strong>${prose(r.qualification)}</div>` : ""}</div><div class="result-footer"><div class="result-meta">${when(a.created)} · ${r.seconds}s · ${esc(a.review === "unreviewed" ? "Awaiting review" : a.review.replace("_", " "))}</div><div class="actions">${button("Review", "review", "", false, `data-id="${a.id}"`)}${button("Correct & teach", "teach", "", busyGuard(), `data-id="${a.id}"`)}<a class="button quiet" href="/api/memo/${a.id}" download aria-label="Export analysis memo">${icon("download")}</a></div></div></section>`;
}
function busyGuard() {
  return !!activeJob();
}
function sourceTable(c, ids = []) {
  const years = [...new Set(c.cells.map((v) => v.period))].sort(
    (a, b) => b - a,
  );
  const labels = [...new Set(c.cells.map((v) => v.label))];
  const duplicates =
    new Set(c.cells.map((v) => `${v.period}:${v.label}`)).size !==
    c.cells.length;
  const valueCell = (v) =>
    `<td class="${v && ids.includes(v.id) ? "selected-cell" : ""}">${v ? num(v.value) : "—"}${v && ids.includes(v.id) ? "" : ""}</td>`;
  const table = duplicates
    ? `<thead><tr><th>Reported line item</th><th>Period / source column</th><th>Value</th></tr></thead><tbody>${c.cells.map((v) => `<tr><td>${esc(v.label)}</td><td class="source-location">FY${v.period}<br>${esc(v.location)}</td>${valueCell(v)}</tr>`).join("")}</tbody>`
    : `<thead><tr><th>Reported line item</th>${years.map((y) => `<th>FY ${y}</th>`).join("")}</tr></thead><tbody>${labels.map((label) => `<tr><td>${esc(label)}</td>${years.map((y) => valueCell(c.cells.find((v) => v.period === y && v.label === label))).join("")}</tr>`).join("")}</tbody>`;
  return `<section class="panel"><div class="panel-head"><h2>Source evidence</h2><span class="section-label">${esc(c.company)} / ${esc(c.cells[0].unit)}</span></div>${c.source_name || c.name ? `<p class="evidence-name">${esc(c.source_name || c.name)}</p>` : ""}<div class="source-table-wrap"><table class="source-table">${table}</table></div><div class="source-notes"><details><summary>Report notes</summary><p>${esc(c.notes)}</p></details><a href="${esc(c.cells[0].source)}" target="_blank" rel="noopener noreferrer">View original report</a><p class="micro-copy">${c.source_review === "human attested" ? "Source checked" : "Prepared excerpt · Source review pending"}</p></div></section>`;
}
function execution(a) {
  const j = activeJob() || researchJob();
  const running = j && ["queued", "running"].includes(j.status),
    events = j?.events || [];
  const stages = [
    ["plan", "Plan"],
    ["retrieve", "Retrieve evidence"],
    ["select", "Select figures"],
    ["audit", "Audit & calculate"],
    ["save", "Save"],
  ];
  return `<section class="panel"><div class="panel-head"><h2>Run</h2><span class="execution-dot ${running ? "running" : ""}"></span></div><div class="panel-body"><p class="run-status" role="status">${running ? "Running…" : j?.status === "failed" ? "Needs attention" : j?.status === "interrupted" ? "Interrupted" : j?.status === "waiting_review" ? "Assignment awaiting review" : j?.status === "complete" ? (j.result?.results?.length ? "Reviews recorded" : "Clarification needed") : "Ready"}</p><details class="run-details" ${running ? "open" : ""}><summary>Run details</summary>${j?.kind === "analysis" ? `<div class="execution-steps">${stages.map(([key, label], i) => `<div class="step ${events.some((e) => e.stage === key) ? "done" : ""} ${j?.stage === key && running ? "active" : ""}"><span class="step-index">${events.some((e) => e.stage === key) ? "✓" : i + 1}</span><strong>${label}</strong></div>`).join("")}<div class="step"><span class="step-index">${a?.review === "reviewed" ? "✓" : "6"}</span><strong>Human review</strong></div></div>` : `<p class="execution-message">${esc(j?.title || "Local task")}</p>`}${j?.message ? `<p class="execution-message">${esc(j.message)}</p>` : ""}</details>${j?.status === "failed" ? `<p class="error-inline">${esc(j.message)}</p>` : ""}</div></section>`;
}

function memoryView() {
  const job = activeJob();
  return `${hero("Memory")}<div class="status-strip"><span><strong>${S.procedures.filter((p) => p.status === "accepted").length}</strong> accepted</span><span><strong>${S.procedures.filter((p) => p.status === "candidate").length}</strong> ${S.procedures.filter((p) => p.status === "candidate").length === 1 ? "candidate" : "candidates"}</span>${job ? `<span role="status">${esc(job.title)} · ${esc(job.message)}</span>` : ""}</div><div class="memory-grid">${S.procedures.length ? S.procedures.map(procedureCard).join("") : `<section class="panel empty wide-panel"><h3>No procedures yet</h3><p>Add a checked correction from an analysis.<br>Candidates need validation and approval before use.</p><div class="card-actions">${button("Go to research", "research", "sage")}</div></section>`}</div>`;
}

function bindingSummary(p) {
  if (!p.binding) return "";
  const b = p.binding;
  return `<div class="binding-summary"><strong>${esc(b.first_label)} → ${esc(b.second_label)}</strong><span>${b.period_kind === "annual" ? "Annual" : "Quarterly"} · ${b.revenue_basis === "sales" ? "Sales basis" : "Total-revenue basis"}</span></div>`;
}
function validationAnswer(label, result, passed) {
  return `<section class="split-box"><span class="section-label">${esc(label)} · ${passed ? "Pass" : "Fail"}</span><strong>${pct(result.result)}</strong>${result.formula ? `<div class="formula">${esc(result.formula)}</div>` : ""}<ul class="procedure-conditions">${(result.sources || []).map((c) => `<li>${esc(c.label)}: ${num(c.value)}<br>FY${c.period} · ${esc(c.location)}</li>`).join("")}</ul><p class="micro-copy">${result.memory?.length || 0} procedures supplied${result.procedure_execution?.status === "applied" ? " · Source rule applied" : ""}</p>${result.status !== "answer" ? `<p>${prose(result.qualification || "Review required")}</p>` : ""}</section>`;
}
function procedureCard(p) {
  const g = p.validation;
  return `<article class="panel"><div class="panel-body"><div class="source-title"><h2>${esc(p.company)} / ${task(p.task)}</h2><span class="badge ${p.status === "accepted" ? "" : p.status === "candidate" ? "amber" : "neutral"}">${esc(p.status)} · v${p.version}</span></div><p class="procedure-scope">${esc(scope(p))}</p>${bindingSummary(p)}<details class="procedure-details"><summary>Procedure steps</summary><p class="procedure-text">${esc(p.procedure)}</p></details><ul class="procedure-conditions">${p.conditions.map((c) => `<li>${esc(c)}</li>`).join("")}</ul><p class="procedure-exclusions"><strong>Do not apply:</strong> ${esc(p.exclusions)}</p>${g ? `<div class="gate"><span><strong>${g.gains}</strong> gains</span><span><strong>${g.regressions}</strong> regressions</span><span>${g.eligible ? "Eligible for human approval" : "Acceptance gate not met"}</span></div>` : '<p class="micro-copy">Not validated. This candidate cannot influence an answer.</p>'}<div class="card-actions">${p.status === "candidate" ? button("Validate", "validate", "sage", busyGuard(), `data-id="${p.id}"`) + (!p.binding ? button("Refine draft", "refine", "", busyGuard(), `data-id="${p.id}"`) : "") + button("Review acceptance", "accept", "", !g?.eligible || busyGuard(), `data-id="${p.id}"`) : ""}${["candidate", "accepted"].includes(p.status) ? button(p.status === "accepted" ? "Disable" : "Reject", p.status === "accepted" ? "disable" : "reject", "quiet", false, `data-id="${p.id}"`) : ""}${button("Inspect trace", "procedure-detail", "quiet", false, `data-id="${p.id}"`)}</div></div></article>`;
}
function sourcesView() {
  return `${hero("Sources")}${sourceTools()}<div class="sources-grid">${visiblePacks()
    .map(
      (p) =>
        `<article class="panel source-card"><div class="panel-body"><div class="source-title"><span class="company-letter">${esc(p.company.slice(0, 1))}</span><div><h2>${esc(p.company)}</h2><p>FY ${[...new Set(p.cells.map((c) => c.period))].sort().join(" / ")}</p></div></div><h3>${esc(p.name || scope(p))}</h3><details class="report-notes"><summary>Report notes</summary><p class="source-summary">${esc(p.notes)}</p></details><div class="source-metrics"><span><strong>${p.cells.length}</strong> figures</span><span>${p.source_review === "human attested" ? "Human checked" : "Review pending"}</span></div><div class="card-actions"><a href="${esc(p.cells[0].source)}" target="_blank" rel="noopener noreferrer">Original report</a>${button("Use report", "open-source", "quiet", false, `data-source-id="${esc(p.id)}"`)}</div></div></article>`,
    )
    .join("")}</div>${pendingDocuments()}`;
}
function modal(title, body, footer = "") {
  const d = $("#dialog");
  $("#dialog-content").innerHTML =
    `<div class="dialog-head"><h2 id="dialog-title">${title}</h2><button class="close-button" data-action="close" aria-label="Close dialog">×</button></div><div class="dialog-body">${body}<div class="error-inline" id="dialog-error" role="alert"></div></div>${footer ? `<div class="dialog-footer">${footer}</div>` : ""}`;
  if (!d.open) d.showModal();
}
function inspect(tab = inspectTab) {
  inspectTab = tab;
  const tabs = [
    ["evaluation", "Evaluation"],
    ["changes", "Report changes"],
    ["activity", "Activity"],
  ];
  modal(
    "Inspect",
    `<div class="inspect-tabs">${tabs.map(([id, label]) => `<button data-action="inspect-tab" data-tab="${id}" class="${id === tab ? "active" : ""}">${label}</button>`).join("")}</div>${{ evaluation: evaluationView, changes: changesView, activity: activityView }[tab]()}`,
  );
}
function evaluationView() {
  const e = S.evaluations.find((e) => e.status === "complete"),
    busy = busyGuard();
  return `<div class="split-grid">${[
    ["learning", "Learning"],
    ["validation", "Validation"],
    ["final", "Reserved final"],
  ]
    .map(
      ([k, label]) =>
        `<div class="split-box"><span>${label}</span><strong>${S.integrity.counts[k]}</strong><span>authored questions</span></div>`,
    )
    .join(
      "",
    )}</div><p class="model-line">${S.integrity.groups} supplied source groups · ${S.integrity.passed ? "Split checks pass" : "Split overlap detected"} · Validation is development evidence.</p>${
    e
      ? `<div class="metric-grid">${[
          ["baseline", "Without memory"],
          ["history", "Correction history"],
          ["lessons", "Validated procedures"],
        ]
          .map(
            ([k, label]) =>
              `<div class="metric-box"><span>${label}</span><strong>${e.metrics[k].correct}/${e.metrics[k].cases}</strong><span>numeric + source selection</span></div>`,
          )
          .join(
            "",
          )}</div><div class="notice">Recorded ${e.split} replay: ${e.gains} gains, ${e.regressions} regressions. ${e.procedure_count} accepted procedures and ${e.correction_count} correction traces. ${e.procedure_count === 0 ? "Empty procedure memory cannot demonstrate a learning gain." : ""} ${e.split === "final" && !e.first_final_exposure ? "Repeated final exposure; not an independent test." : ""}</div>${button("Inspect recorded results", "evaluation-detail", "quiet", false, `data-id="${e.id}"`)}`
      : '<div class="notice">No completed three-condition replay yet. Inspect candidate validation in Memory.</div>'
  }<div class="card-actions">${button("Run validation replay", "replay", "sage", busy)}${button("Review & freeze", "freeze", "", busy)}${button("Run reserved final", "final", "", busy || !S.freezes.length)}</div><details class="answer-details"><summary>Experiment details</summary><p class="model-line">Local MLflow tracking: ${S.tracking_enabled ? "enabled" : "disabled"}. ${e?.tracking?.run_id ? "Recorded run: " + esc(e.tracking.run_id) : ""} ${e?.tracking?.error ? esc(e.tracking.error) : ""}</p><p class="model-line">Reference answers are evaluator-only. A reviewed freeze captures code, data, model and memory. Repeated final exposure is recorded. Week-qualification checking is a text heuristic, not a semantic verifier.</p></details>`;
}
function changesView() {
  return `<p class="model-line">Changes are flagged for review. Procedure mappings stay unchanged until approved.</p>${S.changes.map((c) => `<div class="change-column"><span>${esc(c.company)} / previous presentation</span>${esc(c.old_notes)}<p class="micro-copy">Removed labels: ${esc(c.removed.join(", ") || "None")}</p></div><div class="change-column"><span>${esc(c.company)} / later presentation</span>${esc(c.new_notes)}<p class="micro-copy">Added labels: ${esc(c.added.join(", ") || "None")}</p><p class="micro-copy">${S.procedures.filter((p) => p.status === "accepted" && p.company === c.company && p.report === c.old).length} accepted procedures in the earlier convention require applicability review.</p></div>`).join("") || '<div class="notice">No differing report conventions in this source library.</div>'}`;
}
function activityView() {
  return `${S.jobs.map((j) => `<div class="activity-row"><strong>${esc(j.title)} <span class="badge neutral">${esc(j.status)}</span></strong><p>${esc(j.message)} · ${when(j.created)}</p>${j.kind === "analysis" && ["failed", "interrupted"].includes(j.status) ? button("Resume checkpoint", "retry", "quiet", busyGuard(), `data-id="${j.id}"`) : ""}</div>`).join("")}${S.attempts.map((a) => `<div class="activity-row"><strong>${esc(a.case.company)} · ${task(a.case.task)} · ${pct(a.result.result)}</strong><p>${esc(a.case.question)} · ${when(a.created)}</p>${button("Open saved analysis", "open-attempt", "quiet", false, `data-id="${a.id}"`)}</div>`).join("")}${
    S.events
      .slice(0, 12)
      .map(
        (e) =>
          `<div class="activity-row"><strong>${esc(e.action)}</strong><p>${esc(e.detail)}</p></div>`,
      )
      .join("") ||
    '<div class="notice">Run an analysis to begin the workspace history.</div>'
  }`;
}
function checkedFooter(action, id, label) {
  return `${button("Cancel", "close")}${button(label, action, "primary", true, `data-id="${id}" id="checked-submit"`)}`;
}
async function dispatch(action, target) {
  const id = target.dataset.id;
  if (["dashboard", "research", "memory", "sources"].includes(action)) {
    setView(action);
    return;
  }
  if (action === "close") {
    $("#dialog").close();
    return;
  }
  if (action === "inspect") {
    inspect();
    return;
  }
  if (action === "changes") {
    inspect("changes");
    return;
  }
  if (action === "inspect-tab") {
    inspect(target.dataset.tab);
    return;
  }
  if (action === "about") {
    modal(
      "About this workspace",
      `<p>This workspace uses one local Qwen3 model through Ollama. Separate analyst, auditor and teacher calls share fixed weights. Python checks arithmetic; you check the financial interpretation.</p><p>LangGraph coordinates checkpointed research. Hybrid search uses local embeddings and keyword matching. PDF imports require checked curation. SQLite and local MLflow preserve the evidence and experiment trail.</p><div class="notice">Candidate validation is development evidence. Human approval is required before procedure reuse.</div>${button("Inspect evaluation", "inspect", "quiet")}`,
    );
    return;
  }
  if (action === "analyze") {
    const job = await api("/api/analyze", { case_id: selected, mode });
    selectedResearchJobId = job.job_id;
    selectedAttempt = null;
    await refresh();
    toast("The local analyst is working.");
    return;
  }
  if (action === "teach") {
    const a = S.attempts.find((a) => a.id === id);
    const parents = S.procedures.filter(
      (p) =>
        p.status === "accepted" &&
        ["company", "task", "report"].every((k) => p[k] === a.case[k]),
    );
    modal(
      "Teach a checked correction",
      `<p>Explain the actual error, its supporting source definition, and where the reusable procedure should stop applying.</p><div class="notice">${esc(a.case.question)}<br />Saved answer: ${pct(a.result.result)}</div><label class="field-label" for="correction">Source-checked correction</label><textarea id="correction" maxlength="4000" placeholder="What needs to change, and what source evidence supports it?"></textarea>${parents.length ? `<label class="field-label" for="parent">Procedure version</label><select id="parent"><option value="">New procedure</option>${parents.map((p) => `<option value="${p.id}">Revise accepted version ${p.version}</option>`).join("")}</select>` : ""}<label class="check-label"><input type="checkbox" id="checked">I checked this correction against the original report.</label><p class="micro-copy">Candidates need validation and approval before use.</p>`,
      checkedFooter("submit-teach", id, "Propose procedure"),
    );
    return;
  }
  if (action === "submit-teach") {
    await api("/api/corrections", {
      attempt_id: id,
      text: $("#correction").value,
      checked: $("#checked").checked,
      parent_id: $("#parent")?.value || null,
    });
    $("#dialog").close();
    await refresh();
    toast("Generating an inactive candidate.");
    return;
  }
  if (action === "review") {
    modal(
      "Record your source review",
      `<p>Check the selected figures, requested basis, fiscal periods, calculation and qualifications against the original report. This action records your review; it does not approve a learned procedure.</p><label class="check-label"><input type="checkbox" id="checked">I reviewed this analysis and its source evidence.</label>`,
      checkedFooter("submit-review", id, "Mark reviewed") +
        button(
          "Needs correction",
          "needs-correction",
          "",
          false,
          `data-id="${id}"`,
        ),
    );
    return;
  }
  if (action === "submit-review" || action === "needs-correction") {
    await api("/api/reviews", {
      id,
      status: action === "submit-review" ? "reviewed" : "needs_correction",
    });
    $("#dialog").close();
    await refresh();
    toast("Your review was recorded.");
    return;
  }
  if (action === "refine") {
    await api("/api/refine", { id });
    await refresh();
    toast(
      "Drafting a source rule from the existing checked correction. The old candidate is preserved.",
    );
    return;
  }
  if (action === "validate") {
    await api("/api/validate", { id });
    await refresh();
    toast("Checking the candidate on separate validation cases.");
    return;
  }
  if (action === "accept") {
    const p = S.procedures.find((p) => p.id === id);
    modal(
      "Approve scoped reuse",
      `<p>${esc(p.procedure)}</p>${bindingSummary(p)}<div class="notice">Company: ${esc(p.company)}<br />Task: ${task(p.task)}<br />Convention: ${esc(scope(p))}<br />Validation: ${p.validation.gains} gains · ${p.validation.regressions} regressions</div><label class="check-label"><input type="checkbox" id="checked">I reviewed the correction trace, candidate scope and validation outcomes.</label>${button("Inspect validation first", "procedure-detail", "quiet", false, `data-id="${id}"`)}`,
      checkedFooter("submit-accept", id, "Approve procedure"),
    );
    return;
  }
  if (["submit-accept", "disable", "reject"].includes(action)) {
    await api("/api/procedures", {
      id,
      status:
        action === "submit-accept"
          ? "accepted"
          : action === "disable"
            ? "disabled"
            : "rejected",
      reviewed: action === "submit-accept" && $("#checked").checked,
    });
    $("#dialog").close();
    await refresh();
    toast("Procedure status updated.");
    return;
  }
  if (action === "validation-case") {
    const p = await api("/api/procedures/" + id);
    const r = p.validation?.rows.find(
      (row) => row.case_id === target.dataset.caseId,
    );
    if (!r) throw Error("This validation case is not available.");
    modal(
      "Validation comparison",
      `<p>${esc(r.question || r.case_id)}</p><div class="split-grid comparison-grid">${validationAnswer("Before", r.baseline_result, r.before)}${validationAnswer("With candidate", r.candidate_result, r.after)}</div><p class="micro-copy">${r.applicable ? "Applicable to this procedure" : "Outside this procedure's scope"} · Recorded development validation</p>${r.source ? `<a href="${esc(r.source)}" target="_blank" rel="noopener noreferrer">View original report</a>` : ""}`,
    );
    return;
  }
  if (action === "procedure-detail") {
    const p = await api("/api/procedures/" + id);
    modal(
      "Procedure & validation trace",
      `<p>${esc(p.company)} · ${task(p.task)} · ${esc(scope(p))} · version ${p.version}</p><h3>Checked correction</h3><div class="notice">${esc(p.checked_correction.text)}</div><h3>Proposed procedure</h3>${bindingSummary(p)}<p class="procedure-text">${esc(p.procedure)}</p><ul class="procedure-conditions">${p.conditions.map((c) => `<li>${esc(c)}</li>`).join("")}</ul><p class="procedure-exclusions"><strong>Exclusions:</strong> ${esc(p.exclusions)}</p><p class="model-line">${esc(p.rationale)}</p>${p.validation ? `<div class="gate"><span><strong>${p.validation.gains}</strong> gains</span><span><strong>${p.validation.regressions}</strong> regressions</span></div><div class="source-table-wrap"><table class="source-table validation-table"><thead><tr><th>Validation case</th><th>Before</th><th>Candidate</th><th>Scope</th></tr></thead><tbody>${p.validation.rows.map((r) => `<tr><td>${esc(r.question || r.case_id)}<br>${button("View comparison", "validation-case", "quiet", false, `data-id="${p.id}" data-case-id="${esc(r.case_id)}"`)}</td><td>${r.before ? "Pass" : "Fail"}<br><small>${pct(r.baseline_result.result)}</small></td><td>${r.after ? "Pass" : "Fail"}<br><small>${pct(r.candidate_result.result)}</small></td><td>${r.applicable ? "Applicable" : "Boundary"}</td></tr>`).join("")}</tbody></table></div><p class="model-line">${p.validation.eligible ? "Validation gate passed. Human approval and a current configuration are still required." : "Acceptance gate not met. This candidate cannot be reused."}</p>` : '<div class="notice">This candidate has not been validated and remains inactive.</div>'}<details><summary>Raw trace and paired model outputs</summary><pre class="detail-json">${esc(JSON.stringify(p, null, 2))}</pre></details>`,
    );
    return;
  }
  if (action === "open-source") {
    const p = S.packs.find((p) => p.id === target.dataset.sourceId);
    selectedSourceId = p.id;
    selectedResearchJobId = null;
    selectedAttempt = null;
    assignmentDraft = `Calculate FY${Math.max(...p.cells.map((c) => c.period))} ${p.company} operating margin using total revenue.`;
    selectedCompanies = [p.company];
    workType = "assignment";
    setView("research");
    return;
  }
  if (action === "open-attempt") {
    const a = S.attempts.find((a) => a.id === id);
    selected = a.case.id;
    selectedAttempt = id;
    selectedResearchJobId = a.workflow_id || null;
    const payload = researchJob()?.payload;
    mode = a.mode;
    assignmentDraft =
      payload?.question || a.case.request_context || a.case.question;
    selectedCompanies = payload?.companies || [a.case.company];
    selectedSourceId = payload?.source_id || a.case.source_pack_id || "";
    workType =
      payload?.case || S.cases.some((c) => c.id === a.case.id)
        ? "brief"
        : "assignment";
    $("#dialog").close();
    setView("research");
    return;
  }
  if (action === "replay") {
    await api("/api/evaluate", { split: "validation" });
    $("#dialog").close();
    await refresh();
    toast("Running paired validation. Final cases remain reserved.");
    return;
  }
  if (action === "freeze") {
    modal(
      "Freeze a reviewed experiment",
      `<p>Review all source figures, definitions, reference calculations and source-group splits before attesting. The freeze captures model, code, data, memory and correction history.</p><label class="check-label"><input type="checkbox" id="checked">I checked the corpus, references and splits and am ready to freeze this configuration.</label>`,
      checkedFooter("submit-freeze", "", "Create reviewed freeze"),
    );
    return;
  }
  if (action === "submit-freeze") {
    await api("/api/freeze", { reviewed: $("#checked").checked });
    $("#dialog").close();
    await refresh();
    inspect("evaluation");
    toast("Reviewed configuration frozen.");
    return;
  }
  if (action === "final") {
    modal(
      "Expose the reserved final cases?",
      `<p>Final replay uses the most recent reviewed freeze. Its cases will no longer be untouched. Failed or interrupted runs also count as exposure.</p><label class="check-label"><input type="checkbox" id="checked">I am ready to run the frozen final experiment and record this exposure.</label>`,
      checkedFooter("submit-final", "", "Run frozen final"),
    );
    return;
  }
  if (action === "submit-final") {
    await api("/api/evaluate", { split: "final", freeze_id: S.freezes[0].id });
    $("#dialog").close();
    await refresh();
    toast("Running the frozen final experiment.");
    return;
  }
  if (action === "evaluation-detail") {
    const e = await api("/api/evaluations/" + id);
    modal(
      "Recorded experiment",
      `<pre class="detail-json">${esc(JSON.stringify(e, null, 2))}</pre>`,
    );
    return;
  }
  return featureAction(action, target);
}
document.addEventListener("click", async (event) => {
  const target = event.target.closest("[data-action],[data-view]");
  if (!target || target.disabled) return;
  try {
    if (target.dataset.view) {
      setView(target.dataset.view);
      return;
    }
    await dispatch(target.dataset.action, target);
  } catch (error) {
    if ($("#dialog").open) $("#dialog-error").textContent = error.message;
    else toast(error.message);
  }
});
document.addEventListener("change", (event) => {
  if (event.target.id === "brief-select") {
    selected = event.target.value;
    selectedAttempt = null;
    selectedResearchJobId = null;
    render();
  }
  if (event.target.id === "memory-mode") mode = event.target.value;
  if (event.target.id === "checked") syncConfirmation();
});
function syncConfirmation() {
  const submit = $("#checked-submit");
  if (submit)
    submit.disabled =
      !$("#checked")?.checked ||
      (!!$("#correction") && $("#correction").value.trim().length < 10);
}
document.addEventListener("input", (event) => {
  if (event.target.id === "correction") syncConfirmation();
});
$("#dialog").addEventListener("click", (event) => {
  if (event.target === $("#dialog")) $("#dialog").close();
});
refresh().catch((error) => {
  $("#main").innerHTML =
    `<div class="empty"><h2>Workspace unavailable</h2><p>${esc(error.message)}</p><p>Start this edition with scripts/run.sh on port 8503.</p></div>`;
});
setInterval(() => {
  if (S && activeJob()) refresh().catch((error) => toast(error.message));
}, 2000);
