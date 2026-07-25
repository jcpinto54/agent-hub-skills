(function () {
  const state = {
    payload: null,
    selectedId: "",
    dataUrl: "",
    livePollTimer: 0,
    filters: {
      change: "",
      priority: "",
      owner: "",
      hideCompleted: false,
    },
  };

  const elements = {
    projectMeta: document.querySelector("#project-meta"),
    sourceLabel: document.querySelector("#source-label"),
    generatedLabel: document.querySelector("#generated-label"),
    errorBanner: document.querySelector("#error-banner"),
    changeFilter: document.querySelector("#change-filter"),
    priorityFilter: document.querySelector("#priority-filter"),
    ownerFilter: document.querySelector("#owner-filter"),
    hideCompleted: document.querySelector("#hide-completed"),
    auditMetrics: document.querySelector("#audit-metrics"),
    readinessMetrics: document.querySelector("#readiness-metrics"),
    board: document.querySelector("#board"),
    detailPanel: document.querySelector("#detail-panel"),
  };

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function queryDataUrl() {
    const params = new URLSearchParams(window.location.search);
    if (params.get("data")) return params.get("data");
    if (window.location.protocol === "http:" || window.location.protocol === "https:") return "/api/state";
    return "./hub-state.json";
  }

  function hasCustomDataUrl() {
    return new URLSearchParams(window.location.search).has("data");
  }

  function fallbackDataUrls(primaryUrl) {
    const urls = [primaryUrl];
    if (primaryUrl !== "./hub-state.json") urls.push("./hub-state.json");
    urls.push("./hub-state.sample.json");
    return urls;
  }

  async function fetchPayload(url) {
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`${url} returned ${response.status}`);
    }
    return response.json();
  }

  async function loadPayload({ silent = false } = {}) {
    const primaryUrl = state.dataUrl || queryDataUrl();
    let firstError = null;
    for (const url of fallbackDataUrls(primaryUrl)) {
      try {
        const payload = await fetchPayload(url);
        state.dataUrl = url;
        if (!silent) clearError();
        return payload;
      } catch (error) {
        firstError = firstError || error;
      }
    }
    if (!silent && firstError) {
      showError(`Unable to load dashboard state because ${firstError.message}.`);
    }
    throw firstError || new Error("Unable to load dashboard state.");
  }

  async function refreshPayload() {
    try {
      const previousSelectedId = state.selectedId;
      state.payload = await loadPayload({ silent: true });
      renderFilters(state.payload);
      if (previousSelectedId && allIssues().some((issue) => issue.id === previousSelectedId)) {
        state.selectedId = previousSelectedId;
      }
      render();
      clearError();
    } catch (error) {
      showError(`Live refresh failed because ${error.message}.`);
    }
  }

  function bindLiveUpdates() {
    if (hasCustomDataUrl() || state.dataUrl !== "/api/state") return;
    if (typeof EventSource === "undefined") {
      startLivePolling();
      return;
    }
    const events = new EventSource("/api/events");
    events.addEventListener("revision", () => {
      refreshPayload();
    });
    events.addEventListener("error", () => {
      showError("Live updates disconnected; the current snapshot remains visible.");
      startLivePolling();
    });
  }

  function startLivePolling() {
    if (state.livePollTimer) return;
    state.livePollTimer = window.setInterval(refreshPayload, 2000);
  }

  function clearError() {
    elements.errorBanner.hidden = true;
    elements.errorBanner.textContent = "";
  }

  function showError(message) {
    elements.errorBanner.hidden = false;
    elements.errorBanner.textContent = message;
  }

  function allIssues(payload = state.payload) {
    return (payload?.columns || []).flatMap((column) =>
      (column.issues || []).map((issue) => ({ ...issue, column_id: column.id }))
    );
  }

  function uniqueValues(values) {
    return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b));
  }

  function severityCounts(payload) {
    const counts = { error: 0, warning: 0, info: 0 };
    const topLevelDiagnostics = payload?.diagnostics || [];
    if (topLevelDiagnostics.length) {
      for (const diagnostic of topLevelDiagnostics) {
        if (counts[diagnostic.severity] !== undefined) {
          counts[diagnostic.severity] += 1;
        }
      }
      return counts;
    }
    for (const issue of allIssues(payload)) {
      for (const diagnostic of issue.diagnostics || []) {
        if (counts[diagnostic.severity] !== undefined) counts[diagnostic.severity] += 1;
      }
    }
    return counts;
  }

  function readinessCounts(issues) {
    const counts = { Ready: 0, Blocked: 0, Unknown: 0, Other: 0 };
    for (const issue of issues) {
      const readiness = issue.readiness?.state || "Other";
      if (counts[readiness] === undefined) {
        counts.Other += 1;
      } else {
        counts[readiness] += 1;
      }
    }
    return counts;
  }

  function setOptions(select, values, emptyLabel) {
    const current = select.value;
    select.innerHTML = `<option value="">${escapeHtml(emptyLabel)}</option>`;
    for (const value of values) {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.append(option);
    }
    select.value = values.includes(current) ? current : "";
  }

  function renderMeta(payload) {
    const project = payload?.hub?.project || payload?.project || "Agent Hub";
    const change = payload?.change || "all changes";
    const issueCount = payload?.summary?.issue_count ?? allIssues(payload).length;
    elements.projectMeta.textContent = `${project} / ${change} / ${issueCount} issues`;
    elements.sourceLabel.textContent = `Source: ${payload?.mode || "read-only"} hub`;
    elements.generatedLabel.textContent = `Generated: ${payload?.generated_at || "snapshot"}`;
  }

  function renderFilters(payload) {
    const issues = allIssues(payload);
    const changes = uniqueValues(issues.map((issue) => issue.change));
    const priorities = uniqueValues(issues.map((issue) => issue.priority));
    const owners = uniqueValues(issues.map((issue) => issue.owner || "Unassigned"));
    setOptions(elements.changeFilter, changes, "All changes");
    setOptions(elements.priorityFilter, priorities, "All priorities");
    setOptions(elements.ownerFilter, owners, "All owners");
    if (payload.change && changes.includes(payload.change)) {
      elements.changeFilter.value = payload.change;
      state.filters.change = payload.change;
    }
  }

  function renderMetricRows(container, rows) {
    container.innerHTML = rows
      .map(
        (row) => `
          <div class="metric-row">
            <span><span class="dot ${escapeHtml(row.tone)}"></span>${escapeHtml(row.label)}</span>
            <span class="metric-value">${escapeHtml(row.value)}</span>
          </div>
        `
      )
      .join("");
  }

  function filteredColumns() {
    const payload = state.payload;
    return (payload.columns || []).map((column) => {
      const issues = (column.issues || []).filter((issue) => {
        if (state.filters.hideCompleted && column.id === "completed") return false;
        if (state.filters.change && issue.change !== state.filters.change) return false;
        if (state.filters.priority && issue.priority !== state.filters.priority) return false;
        const owner = issue.owner || "Unassigned";
        if (state.filters.owner && owner !== state.filters.owner) return false;
        return true;
      });
      return { ...column, issues };
    });
  }

  function renderMetrics() {
    const issues = filteredColumns().flatMap((column) => column.issues || []);
    const severity = severityCounts(state.payload);
    const readiness = readinessCounts(issues);
    renderMetricRows(elements.auditMetrics, [
      { label: "Failures", value: severity.error, tone: "error" },
      { label: "Warnings", value: severity.warning, tone: "warning" },
      { label: "Info", value: severity.info, tone: "info" },
      { label: "Total Issues", value: issues.length, tone: "" },
    ]);
    renderMetricRows(elements.readinessMetrics, [
      { label: "Ready", value: readiness.Ready, tone: "ready" },
      { label: "Blocked", value: readiness.Blocked, tone: "error" },
      { label: "Unknown", value: readiness.Unknown, tone: "warning" },
      { label: "Other", value: readiness.Other, tone: "" },
    ]);
  }

  function chipHtml(label, tone = "") {
    return `<span class="chip ${escapeHtml(tone)}">${escapeHtml(label)}</span>`;
  }

  function diagnosticTone(diagnostic) {
    return diagnostic.severity === "error"
      ? "error"
      : diagnostic.severity === "warning"
        ? "warning"
        : "info";
  }

  function issueCard(issue) {
    const selected = issue.id === state.selectedId ? " is-selected" : "";
    const diagnostics = (issue.diagnostics || []).slice(0, 3);
    const diagChips = diagnostics.map((diag) => chipHtml(diag.code, diagnosticTone(diag))).join("");
    const depText = (issue.depends_on || []).length ? issue.depends_on.join(", ") : "-";
    const blockedText = issue.blockers || issue.readiness?.reason || "-";
    return `
      <button class="issue-card${selected}" type="button" data-issue-id="${escapeHtml(issue.id)}">
        <div class="card-kicker">${escapeHtml(issue.id)}</div>
        <h3 class="card-title">${escapeHtml(issue.title)}</h3>
        <div class="chip-row">
          <span class="priority ${(issue.priority || "").toLowerCase()}">${escapeHtml(issue.priority || "P?")}</span>
          ${chipHtml(issue.readiness?.state || issue.status, (issue.readiness?.state || "").toLowerCase())}
        </div>
        <div class="card-fields">
          <span>Owner: ${escapeHtml(issue.owner || "Unassigned")}</span>
          <span>Deps: ${escapeHtml(depText)}</span>
          <span>Reason: ${escapeHtml(blockedText)}</span>
        </div>
        <div class="chip-row">${diagChips || chipHtml(issue.change || "no-change", "info")}</div>
      </button>
    `;
  }

  function renderBoard() {
    const columns = filteredColumns();
    elements.board.innerHTML = columns
      .map(
        (column) => `
          <section class="column" aria-label="${escapeHtml(column.title)}">
            <div class="column-header">
              <span>${escapeHtml(column.title)}</span>
              <span class="count">${column.issues.length}</span>
            </div>
            <div class="card-list">
              ${column.issues.length ? column.issues.map(issueCard).join("") : '<div class="empty-column">No issues</div>'}
            </div>
          </section>
        `
      )
      .join("");
  }

  function findSelectedIssue() {
    const issues = allIssues();
    return issues.find((issue) => issue.id === state.selectedId) || issues[0] || null;
  }

  function renderDetail() {
    const issue = findSelectedIssue();
    if (!issue) {
      elements.detailPanel.innerHTML = '<section class="detail-section"><h2>No issue selected</h2></section>';
      return;
    }
    state.selectedId = issue.id;
    const doneCriteria = issue.done_criteria?.length ? issue.done_criteria : ["No done criteria recorded."];
    const diagnostics = issue.diagnostics?.length ? issue.diagnostics : [];
    const first = issue.verification?.first_test || {};
    const final = issue.verification?.final_verification || {};
    elements.detailPanel.innerHTML = `
      <section class="detail-section">
        <div class="detail-title">
          <span class="priority ${(issue.priority || "").toLowerCase()}">${escapeHtml(issue.priority || "P?")}</span>
          <h2>${escapeHtml(issue.title)}</h2>
        </div>
        <div class="detail-meta">
          ${escapeHtml(issue.id)} / ${escapeHtml(issue.status)} / ${escapeHtml(issue.owner || "Unassigned")}
        </div>
        <p>${escapeHtml(issue.summary || issue.readiness?.reason || "No summary recorded.")}</p>
        <div class="chip-row">
          ${chipHtml(issue.change || "no-change", "info")}
          ${chipHtml(issue.readiness?.state || "Unknown", (issue.readiness?.state || "").toLowerCase())}
        </div>
      </section>
      <section class="detail-section">
        <h3>Done Criteria</h3>
        <ul class="detail-list">
          ${doneCriteria.map((item) => `<li>${escapeHtml(item.replace(/^- \[[ xX]\]\s*/, ""))}</li>`).join("")}
        </ul>
      </section>
      <section class="detail-section">
        <h3>Verification</h3>
        <pre class="detail-code">First Test: ${escapeHtml(first.path || "-")}
Expected: ${escapeHtml(first.expected_initial_result || "-")}

Final: ${escapeHtml(final.commands || "-")}
Expected: ${escapeHtml(final.expected_result || "-")}</pre>
        <h3>Diagnostics</h3>
        <div class="chip-row">
          ${diagnostics.length ? diagnostics.map((diag) => chipHtml(diag.code, diagnosticTone(diag))).join("") : chipHtml("no diagnostics", "ready")}
        </div>
      </section>
    `;
  }

  function render() {
    renderMeta(state.payload);
    renderMetrics();
    renderBoard();
    renderDetail();
  }

  function bindEvents() {
    elements.changeFilter.addEventListener("change", (event) => {
      state.filters.change = event.target.value;
      render();
    });
    elements.priorityFilter.addEventListener("change", (event) => {
      state.filters.priority = event.target.value;
      render();
    });
    elements.ownerFilter.addEventListener("change", (event) => {
      state.filters.owner = event.target.value;
      render();
    });
    elements.hideCompleted.addEventListener("change", (event) => {
      state.filters.hideCompleted = event.target.checked;
      render();
    });
    elements.board.addEventListener("click", (event) => {
      const card = event.target.closest("[data-issue-id]");
      if (!card) return;
      state.selectedId = card.dataset.issueId;
      renderBoard();
      renderDetail();
    });
  }

  async function init() {
    bindEvents();
    state.payload = await loadPayload();
    renderFilters(state.payload);
    const firstIssue = allIssues()[0];
    state.selectedId = firstIssue ? firstIssue.id : "";
    render();
    bindLiveUpdates();
  }

  init().catch((error) => {
    showError(error.message);
  });
})();
