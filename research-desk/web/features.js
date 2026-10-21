let workType = "assignment",
  assignmentDraft =
    "Compare Target and Costco FY2024 operating margins using total revenue, and reported FY2024 total-revenue growth over FY2023.",
  selectedCompanies = ["Target", "Costco"],
  sourceSearch = null,
  sourceQuery = "",
  pendingCuration = null,
  selectedSourceId = "";

function sourceLabel(p) {
  return (
    p.name ||
    `${p.company} · FY${[...new Set(p.cells.map((c) => c.period))].sort().join(" / ")} · ${scope(p)}`
  );
}
function researchJob() {
  return S.jobs.find((j) => j.id === selectedResearchJobId);
}
function researchComposer(c, busy) {
  return `<section class="panel brief-panel"><div class="panel-head"><h2>New analysis</h2><div class="compose-tabs">${["assignment", "brief"].map((k) => `<button data-action="compose-kind" data-kind="${k}" class="${workType === k ? "active" : ""}">${k === "assignment" ? "Assignment" : "Examples"}</button>`).join("")}</div></div><div class="panel-body">${
    workType === "assignment"
      ? `<label class="field-label" for="assignment">Question</label><textarea class="assignment-input" id="assignment" maxlength="1800" ${busy ? "disabled" : ""}>${esc(assignmentDraft)}</textarea><div class="company-select">${[...new Set(S.packs.map((p) => p.company))].map((company) => `<label><input type="checkbox" name="company" value="${esc(company)}" ${selectedCompanies.includes(company) ? "checked" : ""}>${esc(company)}</label>`).join("")}</div><label class="field-label" for="report-select">Report</label><select id="report-select" ${busy ? "disabled" : ""}><option value="">Search eligible reports</option>${S.packs
          .filter((p) => selectedCompanies.includes(p.company))
          .map(
            (p) =>
              `<option value="${esc(p.id)}" ${selectedSourceId === p.id ? "selected" : ""}>${esc(sourceLabel(p))}</option>`,
          )
          .join("")}</select>`
      : `<label class="field-label" for="brief-select">Example</label><select id="brief-select" ${busy ? "disabled" : ""}>${!S.cases.some((v) => v.id === selected) ? "<option selected disabled>Saved assignment result</option>" : ""}${S.cases.map((v) => `<option value="${esc(v.id)}" ${v.id === selected ? "selected" : ""}>${esc(v.company)} · FY${v.period} · ${task(v.task)} · ${v.revenue_basis === "sales" ? "Sales basis" : "Total revenue"}</option>`).join("")}</select><p class="brief-question">${esc(c.question)}</p>`
  }<div class="brief-actions"><select id="memory-mode" aria-label="Procedure use" ${busy ? "disabled" : ""}>${[
    ["lessons", "Validated procedures"],
    ["baseline", "Without memory"],
    ["history", "Correction history"],
  ]
    .map(
      ([v, l]) =>
        `<option value="${v}" ${mode === v ? "selected" : ""}>${l}</option>`,
    )
    .join(
      "",
    )}</select>${button(icon("arrow") + " Run analysis", workType === "assignment" ? "assignment" : "analyze", "primary", busy || !S.model.ready)}</div>${!S.model.ready ? '<p class="error-inline">Start the local model to analyze this evidence.</p>' : ""}</div></section>`;
}

function assignmentResults() {
  const j = researchJob();
  if (!j || !j.result?.results?.length || j.result.results.length < 2)
    return "";
  return `<section class="panel"><div class="panel-head"><h2>Assignment results</h2><span class="badge ${j.status === "waiting_review" ? "amber" : "neutral"}">${j.status === "waiting_review" ? "Assignment awaiting review" : esc(j.status.replaceAll("_", " "))}</span></div><div class="panel-body"><details class="assignment-question"><summary>Assignment</summary><p>${esc(j.payload.question)}</p></details><div class="assignment-results">${j.result.results.map((a) => `<button data-action="select-result" data-id="${a.id}" class="assignment-result ${a.id === selectedAttempt ? "active" : ""}"><span>${esc(a.case.company)} · FY${a.case.period} · ${task(a.case.task)}</span><strong>${pct(a.result.result)}</strong><small>${a.case.revenue_basis === "sales" ? "Sales basis" : "Total-revenue basis"}</small></button>`).join("")}</div></div></section>`;
}

function visiblePacks() {
  return sourceSearch ? sourceSearch.items : S.packs;
}
function sourceTools() {
  return `<div class="source-tools"><label class="sr-only" for="source-query">Search source evidence</label><input type="search" id="source-query" value="${esc(sourceQuery)}" placeholder="Search reports…">${button("Search", "source-search", "", busyGuard())}${button("Import report", "import", "primary", busyGuard())}</div>${sourceSearch ? `<p class="micro-copy">${sourceSearch.items.length} eligible source packs · ${sourceSearch.details.strategy === "hybrid_rrf" ? "Keyword + vector search" : "Keyword search"} ${sourceSearch.details.qualification ? "· Semantic search unavailable; fallback recorded." : ""} ${button("Clear search", "clear-search", "quiet")}</p>` : ""}`;
}
function pendingDocuments() {
  return (S.documents || [])
    .filter((d) => d.status === "needs_curation")
    .map(
      (d) =>
        `<section class="panel pending-source"><div><h3>${esc(d.name)}</h3><p>Extracted report · ${esc(d.company)} · Unavailable to analysis until checked</p></div>${button("Check extracted evidence", "curate", "", busyGuard(), `data-id="${d.id}"`)}</section>`,
    )
    .join("");
}

function importForm() {
  modal(
    "Import a report section",
    `<p>PDF, HTML or text · Up to 8 MB and 80 PDF pages.</p><div class="form-grid"><label>Company<select id="import-company"><option>Target</option><option>Costco</option></select></label><label>Report name<input type="text" id="import-name" maxlength="150"></label></div><label class="field-label" for="import-source">Original source URL</label><input type="url" id="import-source" placeholder="https://…"><label class="field-label" for="import-file">Report section</label><input type="file" id="import-file" accept=".pdf,.html,.htm,.txt"><p class="micro-copy">Check extracted figures and definitions before use. Scanned PDFs need OCR first.</p>`,
    button("Cancel", "close") +
      button("Extract locally", "submit-import", "primary"),
  );
}

function curationRow() {
  return `<div class="curation-row"><input class="cell-year" aria-label="Fiscal year" type="number" min="1990" max="2100" placeholder="FY2024"><input class="cell-label" aria-label="Original line item" type="text" placeholder="Original line item"><input class="cell-value" aria-label="Source figure" type="number" step="any" placeholder="Value"><input class="cell-unit" aria-label="Source units" type="text" value="USD millions"><input class="cell-location" aria-label="Page or table location" type="text" placeholder="Page / table / column"><button class="close-button" data-action="remove-row" aria-label="Remove source row">×</button></div>`;
}
let curationDocument = null;
async function openCuration(identifier) {
  const d = await api("/api/documents/" + identifier);
  curationDocument = d;
  modal(
    "Check the extracted evidence",
    `<p>${esc(d.name)} · ${esc(d.company)}. Preserve original labels, units, periods and definition notes. No automatic accounting interpretation is assumed.</p><details><summary>Extracted source text</summary><pre class="detail-json">${esc(d.content)}</pre></details>${d.tables.length ? `<details><summary>Extracted tables (${d.tables.length})</summary><pre class="detail-json">${esc(JSON.stringify(d.tables, null, 2))}</pre></details>` : ""}<label class="field-label" for="convention">Reporting convention</label><select id="convention"><option value="new_convention">New convention — separately scoped</option>${Object.entries(
      names,
    )
      .filter(([k]) =>
        d.company === "Target"
          ? k.startsWith("target_")
          : k.startsWith("costco_"),
      )
      .map(([k, v]) => `<option value="${k}">${esc(v)}</option>`)
      .join(
        "",
      )}</select><label class="field-label" for="curation-notes">Definition and fiscal-period notes</label><textarea id="curation-notes" placeholder="Explain what the reported revenue includes and any fiscal-week qualifications…"></textarea><p class="micro-copy">Enter at least two checked source figures. Blank rows are ignored.</p><div id="source-rows">${[0, 1, 2, 3].map(() => curationRow()).join("")}</div>${button("+ Add source figure", "add-row", "quiet")}<label class="check-label"><input type="checkbox" id="checked">I checked every figure, original label, fiscal year, unit, location and definition against the original report.</label>`,
    checkedFooter("submit-curation", d.id, "Make evidence available"),
  );
}

async function featureAction(action, target) {
  if (action === "compose-kind") {
    workType = target.dataset.kind;
    render();
    return;
  }
  if (action === "assignment") {
    const job = await api("/api/assignments", {
      question: assignmentDraft,
      companies: selectedCompanies,
      mode,
      source_id: selectedSourceId || null,
    });
    selectedResearchJobId = job.job_id;
    selectedAttempt = null;
    await refresh();
    toast("Research is running locally.");
    return;
  }
  if (action === "select-result") {
    const a = S.attempts.find((a) => a.id === target.dataset.id);
    selected = a.case.id;
    selectedAttempt = a.id;
    selectedResearchJobId = a.workflow_id || null;
    render();
    return;
  }
  if (action === "source-search") {
    sourceQuery = $("#source-query").value;
    await api("/api/search", { query: sourceQuery });
    await refresh();
    toast("Searching source evidence locally.");
    return;
  }
  if (action === "clear-search") {
    sourceSearch = null;
    sourceQuery = "";
    render();
    return;
  }
  if (action === "import") {
    importForm();
    return;
  }
  if (action === "submit-import") {
    const f = $("#import-file").files[0];
    if (!f) throw Error("Select a report section first.");
    if (f.size > 8000000) throw Error("Use a section smaller than 8 MB.");
    const format = f.name.toLowerCase().endsWith(".pdf")
      ? "pdf"
      : /\.html?$/i.test(f.name)
        ? "html"
        : "text";
    let content;
    if (format === "pdf") {
      const bytes = new Uint8Array(await f.arrayBuffer());
      let binary = "";
      for (let i = 0; i < bytes.length; i += 8192)
        binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
      content = btoa(binary);
    } else content = await f.text();
    await api("/api/import", {
      name: $("#import-name").value || f.name,
      company: $("#import-company").value,
      source_url: $("#import-source").value,
      format,
      content,
    });
    $("#dialog").close();
    await refresh();
    toast("Extracting the report section.");
    return;
  }
  if (action === "curate") {
    await openCuration(target.dataset.id);
    return;
  }
  if (action === "add-row") {
    $("#source-rows").insertAdjacentHTML("beforeend", curationRow());
    return;
  }
  if (action === "remove-row") {
    target.closest(".curation-row").remove();
    return;
  }
  if (action === "submit-curation") {
    const d = curationDocument;
    const cells = [...document.querySelectorAll(".curation-row")]
      .filter((row) => row.querySelector(".cell-label").value.trim())
      .map((row, i) => {
        if (
          !row.querySelector(".cell-year").value ||
          !row.querySelector(".cell-value").value
        )
          throw Error(
            "Enter a fiscal year and source figure for every named row.",
          );
        return {
          id: d.id + "_cell_" + i,
          company: d.company,
          period: Number(row.querySelector(".cell-year").value),
          label: row.querySelector(".cell-label").value,
          value: Number(row.querySelector(".cell-value").value),
          unit: row.querySelector(".cell-unit").value,
          source: d.source,
          location: row.querySelector(".cell-location").value,
        };
      });
    await api("/api/curate", {
      document_id: d.id,
      company: d.company,
      convention: $("#convention").value,
      notes: $("#curation-notes").value,
      cells,
      checked: $("#checked").checked,
    });
    sourceSearch = null;
    $("#dialog").close();
    await refresh();
    setView("sources");
    toast("Checked evidence is now available for research.");
    return;
  }
  if (action === "retry") {
    await api("/api/retry", { id: target.dataset.id });
    $("#dialog").close();
    await refresh();
    toast("Resuming the saved research checkpoint.");
    return;
  }
}

document.addEventListener("input", (event) => {
  if (event.target.id === "assignment") assignmentDraft = event.target.value;
  if (event.target.id === "source-query") sourceQuery = event.target.value;
});
document.addEventListener("change", (event) => {
  if (event.target.name === "company") {
    selectedCompanies = [
      ...document.querySelectorAll('input[name="company"]:checked'),
    ].map((v) => v.value);
    if (
      selectedSourceId &&
      (selectedCompanies.length !== 1 ||
        !S.packs.some(
          (p) =>
            p.id === selectedSourceId && p.company === selectedCompanies[0],
        ))
    )
      selectedSourceId = "";
    render();
  }
  if (event.target.id === "report-select") {
    selectedSourceId = event.target.value;
    const report = S.packs.find((p) => p.id === selectedSourceId);
    if (report) selectedCompanies = [report.company];
    render();
  }
});
