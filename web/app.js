/* NextStep Prompt Inspector — client */
(() => {
  'use strict';
  const $ = s => document.querySelector(s);
  const $$ = s => Array.from(document.querySelectorAll(s));
  const API = "";  // same origin (served by FastAPI)

  const el = {
    input: $("#input"),
    btnRun: $("#btn-run"),
    status: $("#status"),
    results: $("#results"),
    badgeProvider: $("#badge-provider"),
    badgePrompt: $("#badge-prompt"),

    // preprocess
    ppOrig: $("#pp-orig"), ppKept: $("#pp-kept"), ppDropNote: $("#pp-drop-note"),
    ppInj: $("#pp-inj"), ppInjNote: $("#pp-inj-note"),
    ppTime: $("#pp-time"), ppContra: $("#pp-contra"), ppQuarantine: $("#pp-quarantine"),

    // prompt
    promptSystem: $("#prompt-system"), promptSchema: $("#prompt-schema"),

    // assessment
    asmtSummary: $("#asmt-summary"), asmtLatency: $("#asmt-latency"),
    asmtUrgency: $("#asmt-urgency"), asmtMode: $("#asmt-mode"), asmtFlags: $("#asmt-flags"),
    asmtPriorities: $("#asmt-priorities"), asmtMissing: $("#asmt-missing"), asmtRaw: $("#asmt-raw"),

    // uncertainty
    uncRing: $("#unc-ring"), uncValue: $("#unc-value"), uncNote: $("#unc-note"), uncBars: $("#unc-bars"),

    // linter
    lintStatus: $("#lint-status"), lintBody: $("#lint-body"),

    // eval
    evalBody: $("#eval-body"),
  };

  function escapeHtml(s) {
    if (s == null) return "";
    return String(s).replace(/[&<>"']/g, c => (
      { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
    ));
  }

  async function init() {
    // load health + prompt
    try {
      const h = await fetch(API + "/api/health").then(r => r.json());
      el.badgeProvider.textContent = `provider: ${h.provider} · ${h.model}`;
      el.badgePrompt.textContent = `prompt: ${h.prompt_version}`;
    } catch { el.badgeProvider.textContent = "provider: unreachable"; }

    try {
      const p = await fetch(API + "/api/prompt").then(r => r.json());
      el.promptSystem.textContent = p.system_prompt;
      el.promptSchema.textContent = p.schema_hint;
    } catch { /* leave empty */ }

    // load default eval report
    loadEvalReport("mock");

    // wiring
    $$(".chip").forEach(b => b.addEventListener("click", () => {
      el.input.value = SAMPLES[b.dataset.sample] || "";
      el.input.focus();
    }));
    el.btnRun.addEventListener("click", run);
    el.input.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") run();
    });
    $$(".tab-btn").forEach(b => b.addEventListener("click", () => {
      $$(".tab-btn").forEach(x => x.classList.remove("active"));
      b.classList.add("active");
      loadEvalReport(b.dataset.kind);
    }));
  }

  async function run() {
    const text = (el.input.value || "").trim();
    if (!text) return;
    el.btnRun.disabled = true;
    el.status.textContent = "running…";
    el.results.hidden = false;

    try {
      const t0 = performance.now();
      const resp = await fetch(API + "/api/reason", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await resp.json();
      const dt = Math.round(performance.now() - t0);
      if (!data.ok) {
        el.status.textContent = `error: ${data.error || "unknown"}`;
        return;
      }
      renderAll(data);
      el.status.textContent = `done in ${dt}ms`;
    } catch (e) {
      el.status.textContent = `network error: ${e.message}`;
    } finally {
      el.btnRun.disabled = false;
    }
  }

  function renderAll(data) {
    renderPreprocess(data.preprocess_notes);
    renderAssessment(data.assessment, data.llm);
    renderUncertainty(data.assessment.uncertainty, data.uncertainty_breakdown);
    renderLinter(data.lint_report);
  }

  function renderPreprocess(pp) {
    const d = pp.distillation;
    el.ppOrig.textContent = d.original_words;
    el.ppKept.textContent = d.kept_words;
    el.ppDropNote.textContent = d.note || "no distillation needed";

    const hits = pp.injection_hits || [];
    el.ppInj.textContent = hits.length ? "DETECTED" : "clean";
    el.ppInj.setAttribute("data-ok", hits.length ? "false" : "true");
    el.ppInjNote.textContent = hits.length
      ? `patterns: ${hits.map(h => "/" + h + "/").join(", ")}`
      : "no injection patterns matched";

    const tc = pp.time_context;
    el.ppTime.textContent =
      `now_iso:     ${tc.now_iso}\n` +
      `day_of_week: ${tc.day_of_week}\n` +
      `resolved:    ${JSON.stringify(tc.resolved, null, 2)}`;

    const cs = pp.contradictions || [];
    el.ppContra.innerHTML = cs.length
      ? cs.map(c => `<div class="mono" style="margin-top:6px">${escapeHtml(c)}</div>`).join("")
      : `<div class="tiny">none spotted</div>`;

    // build the quarantined text preview from the notes
    el.ppQuarantine.textContent =
      `<user_input source="paste_or_type" trust="data_only">\n` +
      `  … your input (${d.kept_words} words after distillation) …\n` +
      `</user_input>\n\n` +
      `<time_context>\n` +
      `  now_iso: ${tc.now_iso}\n` +
      `  day_of_week: ${tc.day_of_week}\n` +
      `</time_context>` +
      (cs.length ? `\n\n<contradictions_spotted>\n${cs.map(c => "  - " + c).join("\n")}\n</contradictions_spotted>` : "");
  }

  function renderAssessment(a, llm) {
    el.asmtSummary.textContent = a.summary;
    el.asmtLatency.textContent = llm ? `${llm.model} · ${llm.latency_ms}ms · ${llm.repair_attempts} repair attempt(s)` : "";
    el.asmtUrgency.textContent = `urgency: ${a.urgency}`;
    el.asmtUrgency.setAttribute("data-level", a.urgency);
    const mode = a.calm_mode ? "calm mode" : a.recovery_mode ? "recovery mode" : "";
    el.asmtMode.textContent = mode;
    el.asmtMode.hidden = !mode;
    const flags = (a.risk_flags || []);
    el.asmtFlags.textContent = flags.length ? `flags: ${flags.join(", ")}` : "flags: none";

    el.asmtPriorities.innerHTML = "";
    if (a.priorities.length === 0) {
      el.asmtPriorities.innerHTML = `<div class="tiny">no priorities returned</div>`;
    }
    for (const p of a.priorities) {
      const item = document.createElement("div");
      item.className = "priority-item";
      item.setAttribute("data-rank", p.rank);
      const tied = p.tied_with && p.tied_with.length ? ` <span class="tiny">(tied with ${p.tied_with.join(", ")})</span>` : "";
      item.innerHTML = `
        <div class="prio-badge">${p.rank}</div>
        <div>
          <h4>${escapeHtml(p.title)}${tied}</h4>
          <p class="why">${escapeHtml(p.why)}</p>
          <p class="action">${p.action ? escapeHtml(p.action) : '<em>needs clarification before an action can be given</em>'}</p>
          <span class="conf">confidence: ${p.confidence.toFixed(2)}</span>
        </div>`;
      el.asmtPriorities.appendChild(item);
    }

    el.asmtMissing.innerHTML = "";
    if ((a.missing_info || []).length === 0) {
      el.asmtMissing.innerHTML = `<li class="tiny" style="background:transparent;border:0">nothing flagged</li>`;
    } else {
      for (const m of a.missing_info) {
        const li = document.createElement("li");
        li.textContent = m;
        el.asmtMissing.appendChild(li);
      }
    }
    el.asmtRaw.textContent = JSON.stringify(a, null, 2);
  }

  function renderUncertainty(total, breakdown) {
    el.uncValue.textContent = total.toFixed(2);
    el.uncRing.style.setProperty("--v", Math.round(total * 100));
    el.uncNote.textContent = total >= 0.5
      ? "High uncertainty — treat the ranking as a starting point, not a verdict."
      : total >= 0.3
      ? "Moderate uncertainty — the ranking is directional."
      : "Low uncertainty — the signals converge.";

    const rows = [
      ["missing_info", breakdown.missing, "+0.1 per missing_info item, capped 0.4"],
      ["contradiction", breakdown.contradict, "+0.25 if contradiction flag set"],
      ["confidence", breakdown.confidence, "up to +0.3 from (1 - avg priority confidence)"],
      ["ensemble", breakdown.ensemble, "up to +0.35 from disagreement across k samples (0 here — single sample)"],
    ];
    el.uncBars.innerHTML = "";
    for (const [label, val, note] of rows) {
      const bar = document.createElement("div");
      bar.className = "bar";
      bar.title = note;
      bar.innerHTML = `
        <span class="bar-label">${label}</span>
        <div class="bar-track"><div class="bar-fill" style="width: ${Math.min(100, val / 0.4 * 100).toFixed(0)}%"></div></div>
        <span class="bar-value">+${val.toFixed(2)}</span>`;
      el.uncBars.appendChild(bar);
    }
  }

  function renderLinter(rep) {
    if (!rep) { el.lintStatus.textContent = "not run"; el.lintBody.innerHTML = ""; return; }
    if (rep.ok) {
      el.lintStatus.textContent = "clean";
      el.lintBody.innerHTML = `<div class="lint-ok">✓ No invented facts or stale missing_info detected.</div>`;
      return;
    }
    el.lintStatus.textContent = "issues found";
    let html = `<div class="lint-fail">`;
    if ((rep.invented_facts || []).length) {
      html += `<h4>⚠ Invented facts</h4><p class="tiny">These appear in the assessment but not in your input:</p><ul>`;
      html += rep.invented_facts.map(f => `<li><code>${escapeHtml(f)}</code></li>`).join("");
      html += `</ul>`;
    }
    if ((rep.stale_missing_info || []).length) {
      html += `<h4>⚠ Stale missing_info</h4><p class="tiny">These claim something is missing, but it's actually in your input:</p><ul>`;
      html += rep.stale_missing_info.map(f => `<li><code>${escapeHtml(f)}</code></li>`).join("");
      html += `</ul>`;
    }
    html += `</div>`;
    el.lintBody.innerHTML = html;
  }

  // very small markdown renderer for the eval report -- handles h1/h2/h3, tables, code, ul
  function renderMarkdown(md) {
    const lines = md.split("\n");
    let html = "";
    let inTable = false, inList = false;
    for (let i = 0; i < lines.length; i++) {
      let ln = lines[i];
      if (/^\|.*\|$/.test(ln.trim())) {
        // table row
        const cells = ln.trim().slice(1, -1).split("|").map(c => c.trim());
        if (!inTable) { html += `<table><thead><tr>${cells.map(c => "<th>" + inlineMd(c) + "</th>").join("")}</tr></thead><tbody>`; inTable = true; i++; continue; }
        if (/^\|[-: |]+\|$/.test(ln.trim())) continue; // separator
        html += `<tr>${cells.map(c => "<td>" + inlineMd(c) + "</td>").join("")}</tr>`;
        if (i + 1 >= lines.length || !/^\|.*\|$/.test((lines[i+1] || "").trim())) {
          html += "</tbody></table>"; inTable = false;
        }
        continue;
      }
      if (/^\s*-\s/.test(ln)) {
        if (!inList) { html += "<ul>"; inList = true; }
        html += "<li>" + inlineMd(ln.replace(/^\s*-\s/, "")) + "</li>";
        continue;
      } else if (inList) { html += "</ul>"; inList = false; }

      if (/^# /.test(ln)) html += "<h1>" + inlineMd(ln.slice(2)) + "</h1>";
      else if (/^## /.test(ln)) html += "<h2>" + inlineMd(ln.slice(3)) + "</h2>";
      else if (/^### /.test(ln)) html += "<h3>" + inlineMd(ln.slice(4)) + "</h3>";
      else if (ln.trim() === "") { /* skip */ }
      else html += "<p>" + inlineMd(ln) + "</p>";
    }
    if (inTable) html += "</tbody></table>";
    if (inList) html += "</ul>";
    return html;
  }
  function inlineMd(s) {
    return escapeHtml(s)
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/✅/g, '<span style="color: var(--c-steady)">✅</span>')
      .replace(/❌/g, '<span style="color: var(--c-urgent)">❌</span>');
  }

  async function loadEvalReport(kind) {
    el.evalBody.innerHTML = `<p class="tiny">Loading ${kind} report…</p>`;
    try {
      const r = await fetch(API + `/api/eval-report?kind=${kind}`).then(x => x.json());
      if (!r.exists) {
        el.evalBody.innerHTML = `<p class="tiny">${kind === 'gemini' ? 'Run <code>python evals/runner.py --provider gemini --out evals/report_gemini.md</code> to generate.' : 'No report generated yet.'}</p>`;
        return;
      }
      el.evalBody.innerHTML = renderMarkdown(r.markdown);
    } catch (e) {
      el.evalBody.innerHTML = `<p class="tiny">Could not load: ${e.message}</p>`;
    }
  }

  document.addEventListener("DOMContentLoaded", init);
})();
