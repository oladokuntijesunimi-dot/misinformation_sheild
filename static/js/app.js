/* Misinformation Shield — client-side glue.
 * Talks to the /api/* JSON endpoints served by this same Flask app,
 * using the fixed demo bearer token that DEMO_MODE accepts. */

const MS = (() => {
  const TOKEN = "demo-token";

  async function api(path, opts = {}) {
    const headers = { Authorization: `Bearer ${TOKEN}`, ...(opts.headers || {}) };
    const res = await fetch(path, { ...opts, headers });
    if (!res.ok) {
      let msg = res.statusText;
      try { msg = (await res.json()).error || msg; } catch (_) {}
      throw new Error(msg || `Request failed (${res.status})`);
    }
    const ct = res.headers.get("content-type") || "";
    return ct.includes("application/json") ? res.json() : res;
  }

  function toast(message, isError = false) {
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " error" : "");
    el.textContent = message;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 4200);
  }

  function escapeHtml(str) {
    return (str || "").replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[c]);
  }

  function timeAgo(iso) {
    if (!iso) return "";
    const diff = (Date.now() - new Date(iso).getTime()) / 1000;
    if (diff < 60) return "just now";
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
    return `${Math.floor(diff / 86400)}d ago`;
  }

  return { api, toast, escapeHtml, timeAgo, TOKEN };
})();

const AGENT_PIPELINE = [
  ["claim_extraction", "Claim extracted from your input"],
  ["claim_analysis", "Claim classified and normalized"],
  ["web_research", "Web sources researched"],
  ["rag", "Knowledge base cross-referenced"],
  ["evidence", "Evidence sorted and scored"],
  ["source_credibility", "Source credibility weighed"],
  ["contradiction", "Adversarial contradiction check"],
  ["verification", "Verdict and confidence computed"],
  ["report_generation", "Report assembled"],
];

const VERDICT_LABELS = {
  verified: "Verified",
  mostly_true: "Mostly True",
  partially_true: "Partially True",
  misleading: "Misleading",
  mostly_false: "Mostly False",
  false: "False",
  unverifiable: "Unverifiable",
};

const INVESTIGATION_POLL_MS = 5000;

/* ---------------- submit-a-claim forms (home quick box + /verify) ---------------- */
function wireClaimForm(formEl) {
  if (!formEl) return;
  formEl.addEventListener("submit", async (e) => {
    e.preventDefault();
    const submitBtn = formEl.querySelector("button[type=submit]");
    const original = submitBtn.textContent;
    const data = new FormData(formEl);
    const inputType = data.get("input_type") || "text";
    const content = (data.get("content") || "").trim();
    const category = data.get("category") || "";

    if (!content) {
      MS.toast("Enter a claim, headline, or link first.", true);
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Opening case…";
    try {
      const payload = { input_type: inputType, content, category: category || undefined };
      if (inputType === "url") payload.source_url = content;
      const investigation = await MS.api("/api/investigations", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      window.location.href = `/investigations/${investigation.id}`;
    } catch (err) {
      MS.toast(err.message || "Could not start the investigation.", true);
      submitBtn.disabled = false;
      submitBtn.textContent = original;
    }
  });
}

/* ---------------- investigation detail: poll + render ---------------- */
function initInvestigationDetail(investigationId) {
  const root = document.getElementById("investigation-root");
  if (!root) return;

  let timer = null;

  async function tick() {
    try {
      const inv = await MS.api(`/api/investigations/${investigationId}`);
      render(inv);
      if (["completed", "failed", "unverifiable"].includes(inv.status)) {
        clearTimeout(timer);
      } else {
        timer = setTimeout(tick, INVESTIGATION_POLL_MS);
      }
    } catch (err) {
      root.innerHTML = `<div class="empty-state"><h3>Case not found</h3><p>${MS.escapeHtml(err.message)}</p><a class="btn btn-accent" href="/verify">Start a new investigation</a></div>`;
    }
  }

  function render(inv) {
    if (inv.status === "completed" && inv.claims && inv.claims.length) {
      root.innerHTML = renderVerdict(inv);
    } else if (inv.status === "failed") {
      root.innerHTML = `
        <div class="empty-state">
          <h3>Investigation failed</h3>
          <p>${MS.escapeHtml(inv.error_message || "Something interrupted the pipeline.")}</p>
          <a class="btn btn-accent" href="/verify">Try another claim</a>
        </div>`;
    } else {
      root.innerHTML = renderProgress(inv);
    }
  }

  function renderProgress(inv) {
    const agentsByName = {};
    (inv.agents || []).forEach((a) => { agentsByName[a.agent_name] = a; });
    const pct = Math.max(4, inv.progress || 0);

    const steps = AGENT_PIPELINE.map(([name, label]) => {
      const a = agentsByName[name];
      const status = a ? a.status : "pending";
      const cls = status === "completed" ? "done" : status === "running" ? "active" : "";
      const mark = status === "completed" ? "✓" : status === "running" ? "" : "";
      return `
        <div class="trail-step ${cls}">
          <span class="trail-dot">${mark}</span>
          <span class="trail-label">${label}</span>
        </div>`;
    }).join("");

    return `
      <div class="progress-narrow">
        <div class="progress-header">
          <div class="eyebrow" style="justify-content:center">Case ${investigationId.slice(0, 8)}</div>
          <p class="progress-claim">&ldquo;${MS.escapeHtml(inv.original_content)}&rdquo;</p>
          <p>Nine independent agents are working the case. This usually takes under a minute.</p>
        </div>
        <div class="progress-bar-track"><div class="progress-bar-fill" style="width:${pct}%"></div></div>
        <div class="trail">${steps}</div>
      </div>`;
  }

  function renderVerdict(inv) {
    const claim = inv.claims[0];
    const verdict = claim.verdict || "unverifiable";
    const evidence = claim.evidence || [];
    const supporting = evidence.filter((e) => e.evidence_type === "supporting");
    const contradicting = evidence.filter((e) => e.evidence_type === "contradicting");

    const evidenceCard = (e) => `
      <div class="evidence-card">
        <div class="title">${MS.escapeHtml(e.title)}</div>
        <div class="meta">${MS.escapeHtml(e.publisher || "Unknown source")} ${e.published_at ? "· " + MS.escapeHtml(e.published_at.slice(0, 10)) : ""}</div>
        <p class="snippet">${MS.escapeHtml(e.snippet || "")}</p>
      </div>`;

    return `
      <div class="verdict-top">
        <div>
          <div class="verdict-claim-label">Case ${investigationId.slice(0, 8)} · ${MS.escapeHtml(inv.category || "General")}</div>
          <div class="verdict-claim-text">&ldquo;${MS.escapeHtml(claim.claim_text)}&rdquo;</div>
        </div>
        <span class="stamp-badge ${verdict}">${VERDICT_LABELS[verdict] || verdict}</span>
      </div>

      <div class="score-row">
        <div class="score-card"><div class="k">Veracity</div><div class="v">${claim.veracity_score ?? "—"}<small>/100</small></div></div>
        <div class="score-card"><div class="k">Confidence</div><div class="v">${claim.confidence_score ?? "—"}<small>%</small></div></div>
        <div class="score-card"><div class="k">Evidence reviewed</div><div class="v">${evidence.length}<small>items</small></div></div>
      </div>

      <div class="summary-block">
        <h3>Assessment</h3>
        <p>${MS.escapeHtml(claim.summary || "No summary available.")}</p>
        ${(claim.key_findings || []).length ? `<h3 style="margin-top:18px;">Key findings</h3><ul class="findings-list">${claim.key_findings.map((f) => `<li>${MS.escapeHtml(f)}</li>`).join("")}</ul>` : ""}
        ${(claim.limitations || []).length ? `<h3 style="margin-top:18px;">Limitations</h3><ul class="findings-list">${claim.limitations.map((f) => `<li>${MS.escapeHtml(f)}</li>`).join("")}</ul>` : ""}
      </div>

      <div class="evidence-cols">
        <div class="evidence-col supporting">
          <h3>Supporting (${supporting.length})</h3>
          ${supporting.length ? supporting.map(evidenceCard).join("") : '<p class="evidence-empty">No supporting evidence found.</p>'}
        </div>
        <div class="evidence-col contradicting">
          <h3>Contradicting (${contradicting.length})</h3>
          ${contradicting.length ? contradicting.map(evidenceCard).join("") : '<p class="evidence-empty">No contradicting evidence found.</p>'}
        </div>
      </div>

      <div class="report-actions">
        <a class="btn btn-accent" href="/api/reports/${investigationId}/export" target="_blank" rel="noopener">Export PDF report</a>
        <a class="btn" href="/verify">Investigate another claim</a>
      </div>`;
  }

  tick();
}

/* ---------------- case log / history list ---------------- */
function initCaseLog() {
  const root = document.getElementById("case-log-root");
  if (!root) return;

  MS.api("/api/investigations")
    .then((rows) => {
      if (!rows.length) {
        root.innerHTML = `
          <div class="empty-state">
            <h3>No cases yet</h3>
            <p>Every claim you investigate will show up here.</p>
            <a class="btn btn-accent" href="/verify">Open your first case</a>
          </div>`;
        return;
      }
      root.innerHTML = rows.map((r) => `
        <a class="case-row" href="/investigations/${r.id}">
          <span class="cid">#${r.id.slice(0, 8)}</span>
          <span class="claim">${MS.escapeHtml(r.original_content)}</span>
          <span class="cat">${MS.escapeHtml(r.category || "General")}</span>
          <span class="badge ${r.status}">${r.status.replace("_", " ")}</span>
          <span class="cid">${MS.timeAgo(r.created_at)}</span>
        </a>`).join("");
    })
    .catch((err) => {
      root.innerHTML = `<div class="empty-state"><h3>Could not load the case log</h3><p>${MS.escapeHtml(err.message)}</p></div>`;
    });
}

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("form[data-claim-form]").forEach(wireClaimForm);
  initCaseLog();
  const root = document.getElementById("investigation-root");
  if (root) initInvestigationDetail(root.dataset.investigationId);
});
