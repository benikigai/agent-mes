// AgentMES live kanban — vanilla JS SSE consumer.
// Connects to /api/events, hydrates from /api/state, renders cards.
// Incremental diffing so cards animate a green-flash "stage complete"
// when their current_stage advances, instead of wholesale re-render.
//
// Each stage inside a card is a <details> disclosure. Current stage
// auto-expands; past stages collapse. User expand/collapse state is
// preserved across re-renders via detailsState.

const STAGES = ["plan", "design", "build", "test", "review", "document", "deploy"];
const STAGE_LABELS = {
  plan: "PLAN", design: "DESIGN", build: "BUILD", test: "TEST",
  review: "REVIEW", document: "DOCUMENT", deploy: "DEPLOY",
};
// Icons match the lane-header icons (index.html lane-icon spans)
const STAGE_ICONS = {
  plan: "☑",
  design: "✦",
  build: "⚒",
  test: "⌕",
  review: "◉",
  document: "✎",
  deploy: "⏱",
};
const SYMBOLS = {
  PASS: "✓", FAIL: "✗", KILLED: "✗", DRIFT: "⚠", WARN: "⚠", RUN: "⏳",
};
const SYMBOL_CLASSES = {
  PASS: "pass", FAIL: "fail", KILLED: "killed", DRIFT: "drift", WARN: "warn", RUN: "run",
};
const STATUS_RANK = { PASS: 0, RUN: 1, WARN: 1, DRIFT: 2, FAIL: 3, KILLED: 3 };

// Stage-complete animation duration — must match the @keyframes in
// style.css (see `@keyframes stage-complete`).
const STAGE_COMPLETE_MS = 650;

const state = {
  tasks: {},             // id → task payload
  launching: new Set(),  // ids the browser optimistically marked as launching
};

// Per-(taskId, stage) expand/collapse state — survives re-renders so the
// user's open/close choice isn't blown away every time a new event lands.
const detailsState = {};

function detailsKey(taskId, stage) { return `${taskId}::${stage}`; }

// ─── DOM helpers ────────────────────────────────────────────────────────────

function el(tag, className, text) {
  const e = document.createElement(tag);
  if (className) e.className = className;
  if (text != null) e.textContent = text;
  return e;
}

function setStateLabel(label, cls) {
  const ind = document.getElementById("state-indicator");
  ind.textContent = label;
  ind.className = "state-indicator" + (cls ? " " + cls : "");
}

function isArtifactLink(ref) {
  if (!ref || typeof ref !== "string") return false;
  return ref.startsWith("/artifact/") || ref.startsWith("/artifacts/") ||
         ref.startsWith("http://") || ref.startsWith("https://");
}

// ─── card rendering (pure function — builds a fresh DOM element) ───────────

function renderCard(task) {
  const card = el("div", `card ${task.status}`);
  card.id = `card-${task.id}`;
  card.dataset.taskId = task.id;
  card.dataset.stage = task.current_stage;

  const icon = task.type === "code" ? "⚙" : "✉";
  const isPreLaunch = !task.events || task.events.length === 0;
  const isLaunching = state.launching.has(task.id);

  // Title row — title on the left, expand-all toggle on the right (only
  // once the card has any stage content to expand)
  const titleRow = el("div", "card-title-row");
  titleRow.appendChild(el("div", "card-title", `${icon} ${task.id}`));
  if (!isPreLaunch || isLaunching) {
    const expandBtn = el("button", "card-expand-btn", "⇵ expand all");
    expandBtn.type = "button";
    expandBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      toggleAllStages(task.id);
    });
    titleRow.appendChild(expandBtn);
  }
  card.appendChild(titleRow);

  if (isPreLaunch && !isLaunching) {
    // Pre-launch — compact, shows the inbound message + Start button
    card.appendChild(el("div", "card-meta", `from: ${task.requester} in ${task.source}`));
    card.appendChild(el("hr", "card-divider"));
    card.appendChild(el("div", "card-raw", task.raw_input));

    const btn = el("button", "start-btn", `▶ Start ${task.id}`);
    btn.addEventListener("click", () => launchTask(task.id));
    card.appendChild(btn);
    return card;
  }

  // Running / complete
  if (task.intent) {
    card.appendChild(el("div", "card-intent", task.intent));
  } else if (isLaunching) {
    card.appendChild(el("div", "card-intent", "starting pipeline…"));
  }

  // Group events by stage
  const byStage = {};
  for (const ev of task.events || []) {
    if (!byStage[ev.stage]) byStage[ev.stage] = [];
    byStage[ev.stage].push(ev);
  }

  for (const stage of STAGES) {
    if (!byStage[stage]) continue;
    card.appendChild(renderStageDetails(task, stage, byStage[stage]));
  }

  // Inline gate controls when blocked at a human gate (Review or Deploy):
  // approve (proceed) · reject (close the ticket) · reject + re-plan (rework).
  if (task.status === "blocked") {
    const btn = el("button", "approve-btn", `[APPROVE ${task.id}]`);
    btn.addEventListener("click", () => approveTask(task.id, task.current_stage));
    card.appendChild(btn);

    const rejectBtn = el("button", "reject-btn", "✗ Reject — close ticket");
    rejectBtn.addEventListener("click", () => rejectTask(task.id, task.current_stage));
    card.appendChild(rejectBtn);

    const box = el("div", "feedback-box");
    box.appendChild(el("div", "feedback-label", "or send back to Plan with feedback"));
    const ta = document.createElement("textarea");
    ta.className = "feedback-input";
    ta.placeholder = "What should change? e.g. 'drop the AC about test_isolation, broaden blast_radius to include auth/*'";
    box.appendChild(ta);
    const fbBtn = el("button", "feedback-btn", "↺ Reject + Re-plan");
    fbBtn.addEventListener("click", async () => {
      const text = ta.value.trim();
      if (!text) {
        ta.focus();
        return;
      }
      fbBtn.disabled = true;
      ta.disabled = true;
      await sendFeedback(task.id, text);
    });
    box.appendChild(fbBtn);
    card.appendChild(box);
  }

  return card;
}

function renderStageDetails(task, stage, stageEvents) {
  const key = detailsKey(task.id, stage);
  // First time we see this stage in this task, open it iff it's the
  // current stage. Once the user toggles it, we remember their choice.
  if (detailsState[key] === undefined) {
    detailsState[key] = stage === task.current_stage;
  }

  const section = document.createElement("details");
  section.className = "stage-details";
  section.dataset.detailsKey = key;
  section.open = detailsState[key];
  section.addEventListener("toggle", () => {
    detailsState[key] = section.open;
  });

  // ─── summary (always visible) ────────────────────────────────────────
  const summary = document.createElement("summary");
  summary.className = "stage-summary";

  // Worst-status mark so the collapsed row tells the eye what happened
  let worstStatus = "PASS";
  for (const ev of stageEvents) {
    const s = (ev.metadata && ev.metadata.status) || "PASS";
    if ((STATUS_RANK[s] || 0) > (STATUS_RANK[worstStatus] || 0)) worstStatus = s;
  }
  const markCls = SYMBOL_CLASSES[worstStatus] || "pass";
  const mark = el("span", `stage-summary-mark ${markCls}`, SYMBOLS[worstStatus] || "✓");
  summary.appendChild(mark);

  // Stage icon — matches the lane header icon so each collapsed row is
  // visually tied back to its lane
  summary.appendChild(
    el("span", `stage-summary-icon stage-icon-${stage}`, STAGE_ICONS[stage] || "")
  );
  summary.appendChild(el("span", "stage-summary-name", STAGE_LABELS[stage]));
  summary.appendChild(el("span", "stage-summary-count", `${stageEvents.length}`));

  // Artifact-link indicator — click opens the rendered stage output
  let linkArtifact = null;
  for (const ev of stageEvents) {
    for (const a of (ev.artifacts || [])) {
      if (isArtifactLink(a.ref)) { linkArtifact = a; break; }
    }
    if (linkArtifact) break;
  }
  if (linkArtifact) {
    const anchor = document.createElement("a");
    anchor.className = "stage-summary-link";
    anchor.href = linkArtifact.ref;
    anchor.target = "_blank";
    anchor.rel = "noopener";
    anchor.textContent = "↗";
    anchor.title = linkArtifact.summary || "open stage output";
    // Don't toggle the disclosure when the link is clicked
    anchor.addEventListener("click", (e) => e.stopPropagation());
    summary.appendChild(anchor);
  }

  section.appendChild(summary);

  // ─── body (expanded) ─────────────────────────────────────────────────
  const body = el("div", "stage-body");
  for (const ev of stageEvents) {
    const status = (ev.metadata && ev.metadata.status) || "PASS";
    const sym = SYMBOLS[status] || "•";
    const cls = SYMBOL_CLASSES[status] || "pass";
    const line = el("div", `event-line ${cls}`);
    line.appendChild(el("span", "symbol", sym));
    line.appendChild(document.createTextNode(`[${(ev.agent || "").split(" ")[0]}] ${ev.action}`));
    body.appendChild(line);

    if (ev.metadata) {
      for (const [k, v] of Object.entries(ev.metadata)) {
        if (k === "status" || k === "ticket_id") continue;
        const valStr = typeof v === "string" ? v : JSON.stringify(v);
        body.appendChild(el("div", "event-meta", `${k}: ${valStr.slice(0, 60)}`));
      }
    }

    if (ev.artifacts) {
      for (const a of ev.artifacts) {
        const artLine = el("div", "event-artifact");
        artLine.appendChild(document.createTextNode(`→ ${a.type}: `));
        if (isArtifactLink(a.ref)) {
          const link = el("a", "artifact-link");
          link.href = a.ref;
          link.target = "_blank";
          link.rel = "noopener";
          link.textContent = a.summary || a.ref.split("/").pop() || "open";
          artLine.appendChild(link);
        } else {
          const refText = a.ref || "";
          artLine.appendChild(document.createTextNode(refText.slice(0, 48)));
        }
        body.appendChild(artLine);
      }
    }
  }
  section.appendChild(body);
  return section;
}

// ─── incremental sync ──────────────────────────────────────────────────────

function upsertCard(task) {
  const targetCol = document.getElementById(`col-${task.current_stage}`);
  if (!targetCol) return;

  const existing = document.getElementById(`card-${task.id}`);

  if (!existing) {
    const fresh = renderCard(task);
    fresh.classList.add("stage-arrive");
    targetCol.appendChild(fresh);
    return;
  }

  const currentCol = existing.parentElement;
  if (currentCol === targetCol) {
    // Same lane — swap content in place. detailsState preserves open/close.
    const fresh = renderCard(task);
    existing.replaceWith(fresh);
    return;
  }

  // Stage transition — force-open the new stage so the audience sees
  // what the card just walked into
  detailsState[detailsKey(task.id, task.current_stage)] = true;

  existing.id = `card-${task.id}-leaving`;
  existing.classList.add("stage-complete");
  const taskId = task.id;
  setTimeout(() => {
    if (existing.parentElement) existing.remove();
    const latest = state.tasks[taskId];
    if (!latest) return;
    if (document.getElementById(`card-${taskId}`)) return;  // a later event already upserted
    const fresh = renderCard(latest);
    fresh.classList.add("stage-arrive");
    const col = document.getElementById(`col-${latest.current_stage}`);
    (col || targetCol).appendChild(fresh);
  }, STAGE_COMPLETE_MS);
}

function clearAllCards() {
  for (const stage of STAGES) {
    document.getElementById(`col-${stage}`).innerHTML = "";
  }
}

// Flip every stage dropdown inside a given card. If any are closed, opens
// them all; otherwise closes them all. State is persisted into detailsState
// so a subsequent re-render keeps them in the same position.
function toggleAllStages(taskId) {
  const card = document.getElementById(`card-${taskId}`);
  if (!card) return;
  const details = card.querySelectorAll(".stage-details");
  if (!details.length) return;
  const anyClosed = Array.from(details).some((d) => !d.open);
  for (const d of details) {
    d.open = anyClosed;
    const key = d.dataset.detailsKey;
    if (key) detailsState[key] = anyClosed;
  }
}

function clearDetailsState() {
  for (const k of Object.keys(detailsState)) delete detailsState[k];
}

function syncAllCards() {
  document.querySelectorAll(".card").forEach((c) => {
    const id = c.dataset.taskId;
    if (id && !state.tasks[id]) c.remove();
  });
  for (const task of Object.values(state.tasks)) {
    upsertCard(task);
  }
}

// ─── API ────────────────────────────────────────────────────────────────────

async function loadInitialState() {
  const r = await fetch("/api/state");
  const s = await r.json();
  state.tasks = {};
  for (const t of s.tasks) state.tasks[t.id] = t;
  state.launching.clear();
  clearDetailsState();
  clearAllCards();
  syncAllCards();
  updateStateLabel();
}

async function launchTask(taskId) {
  if (state.launching.has(taskId)) return;
  state.launching.add(taskId);

  if (state.tasks[taskId]) upsertCard(state.tasks[taskId]);
  setStateLabel(`launching ${taskId}…`, "running");

  try {
    const r = await fetch(`/api/launch/${taskId}`, { method: "POST" });
    if (!r.ok && r.status !== 409) {
      console.error("launch failed", r.status);
      state.launching.delete(taskId);
      if (state.tasks[taskId]) upsertCard(state.tasks[taskId]);
      setStateLabel("launch failed — check console");
    }
  } catch (e) {
    console.error(e);
    state.launching.delete(taskId);
  }
}

async function resetBoard() {
  try {
    await fetch("/api/reset", { method: "POST" });
    state.launching.clear();
    clearDetailsState();
    setStateLabel("reset — click Start on a ticket");
  } catch (e) {
    console.error("reset failed", e);
    setStateLabel("reset failed — check console");
  }
}

async function approveTask(taskId, stage) {
  await fetch(`/api/approve/${taskId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stage }),
  });
}

async function rejectTask(taskId, stage) {
  // Terminal reject — closes the ticket. Distinct from sendFeedback, which
  // rejects-and-replans. The {stage} lets the server 409 a stale click.
  await fetch(`/api/reject/${taskId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ stage }),
  });
}

async function sendFeedback(taskId, text) {
  setStateLabel(`re-planning ${taskId} with feedback…`, "running");
  try {
    const r = await fetch(`/api/feedback/${taskId}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    if (!r.ok) {
      console.error("feedback failed", r.status);
      setStateLabel("feedback failed — check console");
    }
  } catch (e) {
    console.error(e);
    setStateLabel("feedback failed — check console");
  }
}

function updateStateLabel() {
  const tasks = Object.values(state.tasks);
  if (tasks.length === 0) {
    setStateLabel("ready — click Start on a ticket");
    return;
  }
  const running = tasks.filter((t) => t.status === "running");
  const blocked = tasks.filter((t) => t.status === "blocked");
  const merged = tasks.filter((t) => t.status === "merged");
  const closed = tasks.filter((t) => ["rejected", "expired", "killed"].includes(t.status));
  if (blocked.length) {
    setStateLabel(`awaiting approval — click [APPROVE] on ${blocked[0].id}`, "running");
  } else if (running.length) {
    setStateLabel(`${running.map((t) => t.id).join(", ")} in flight`, "running");
  } else if (merged.length === tasks.length) {
    setStateLabel("complete — all tickets merged ✓", "complete");
  } else if (merged.length || closed.length) {
    const parts = [];
    if (merged.length) parts.push(`${merged.length} merged`);
    if (closed.length) parts.push(`${closed.length} closed (rejected/expired)`);
    setStateLabel(`${parts.join(" · ")} — start the next ticket`);
  } else {
    setStateLabel("ready — click Start on a ticket");
  }
}

// ─── SSE ────────────────────────────────────────────────────────────────────

function connectSSE() {
  const es = new EventSource("/api/events");
  es.onmessage = (msg) => {
    try {
      const payload = JSON.parse(msg.data);
      if (payload.type === "state") {
        state.tasks = {};
        for (const t of payload.tasks) state.tasks[t.id] = t;
        state.launching.clear();
        clearDetailsState();
        clearAllCards();
        syncAllCards();
        updateStateLabel();
      } else if (payload.type === "event") {
        const t = payload.task;
        state.tasks[t.id] = t;
        state.launching.delete(t.id);
        upsertCard(t);
        updateStateLabel();
      }
    } catch (e) {
      console.error("SSE parse", e);
    }
  };
  es.onerror = (e) => {
    console.error("SSE error", e);
    setStateLabel("SSE disconnected — retrying...", "");
  };
}

// ─── boot ───────────────────────────────────────────────────────────────────

document.getElementById("reset-btn").addEventListener("click", resetBoard);

// Flip the topbar mode chip based on which integrations are active
async function loadMode() {
  try {
    const r = await fetch("/api/mode");
    if (!r.ok) return;
    const m = await r.json();
    const chip = document.getElementById("mode-chip");
    if (!chip) return;
    if (m.real_pr) {
      chip.dataset.mode = "live";
      chip.textContent = "● LIVE PR";
      chip.title = `Real PRs opened against ${m.github_repo || 'the repo'}`;
    } else {
      chip.dataset.mode = "stub";
      chip.textContent = "dry-run";
      chip.title = "Dry-run mode — set AGENTMES_OPEN_REAL_PR=1 to open real PRs";
    }
  } catch (e) {
    console.error("mode check failed", e);
  }
}

loadInitialState().then(() => {
  connectSSE();
  loadMode();
});
