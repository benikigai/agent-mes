// AgentMES live kanban — vanilla JS SSE consumer.
// Connects to /api/events, hydrates from /api/state, renders cards.

const STAGES = ["plan", "design", "build", "test", "review", "document", "deploy"];
const STAGE_LABELS = {
  plan: "PLAN", design: "DESIGN", build: "BUILD", test: "TEST",
  review: "REVIEW", document: "DOCUMENT", deploy: "DEPLOY",
};
const SYMBOLS = {
  PASS: "✓", FAIL: "✗", KILLED: "✗", DRIFT: "⚠", WARN: "⚠", RUN: "⏳",
};
const SYMBOL_CLASSES = {
  PASS: "pass", FAIL: "fail", KILLED: "killed", DRIFT: "drift", WARN: "warn", RUN: "run",
};

const state = {
  tasks: {},
  running: false,
};

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

// ─── card rendering ────────────────────────────────────────────────────────

function renderCard(task) {
  const card = el("div", `card ${task.status}`);
  card.id = `card-${task.id}`;
  card.dataset.taskId = task.id;
  card.dataset.stage = task.current_stage;

  const icon = task.type === "code" ? "⚙" : "✉";
  card.appendChild(el("div", "card-title", `${icon} ${task.id}`));

  if (!task.events || task.events.length === 0) {
    // Pre-launch state — show inbound message
    card.appendChild(el("div", "card-meta", `from: ${task.requester} in ${task.source}`));
    card.appendChild(el("hr", "card-divider"));
    card.appendChild(el("div", "card-raw", task.raw_input));
  } else {
    // Running / complete — show detailed changelog
    if (task.intent) {
      card.appendChild(el("div", "card-intent", task.intent));
    }
    card.appendChild(el("hr", "card-divider"));

    // Group events by stage
    const byStage = {};
    for (const ev of task.events) {
      if (!byStage[ev.stage]) byStage[ev.stage] = [];
      byStage[ev.stage].push(ev);
    }

    for (const stage of STAGES) {
      if (!byStage[stage]) continue;
      const section = el("div", "stage-section");
      section.appendChild(el("div", "stage-header", `━ ${STAGE_LABELS[stage]} ━`));
      for (const ev of byStage[stage]) {
        const status = (ev.metadata && ev.metadata.status) || "PASS";
        const sym = SYMBOLS[status] || "•";
        const cls = SYMBOL_CLASSES[status] || "pass";
        const line = el("div", `event-line ${cls}`);
        const symEl = el("span", "symbol", sym);
        line.appendChild(symEl);
        line.appendChild(document.createTextNode(`[${(ev.agent || "").split(" ")[0]}] ${ev.action}`));
        section.appendChild(line);

        // Indented metadata
        if (ev.metadata) {
          for (const [k, v] of Object.entries(ev.metadata)) {
            if (k === "status" || k === "ticket_id") continue;
            const valStr = typeof v === "string" ? v : JSON.stringify(v);
            section.appendChild(el("div", "event-meta", `${k}: ${valStr.slice(0, 60)}`));
          }
        }

        // Indented artifacts
        if (ev.artifacts) {
          for (const a of ev.artifacts) {
            section.appendChild(el("div", "event-artifact", `→ ${a.type}: ${a.ref.slice(0, 48)}`));
          }
        }
      }
      card.appendChild(section);
    }
  }

  // Inline approve button if blocked
  if (task.status === "blocked") {
    const btn = el("button", "approve-btn", `[APPROVE ${task.id}]`);
    btn.addEventListener("click", () => approveTask(task.id));
    card.appendChild(btn);
  }

  return card;
}

function renderAll() {
  // Clear all columns
  for (const stage of STAGES) {
    document.getElementById(`col-${stage}`).innerHTML = "";
  }
  // Place cards by current_stage
  for (const task of Object.values(state.tasks)) {
    const col = document.getElementById(`col-${task.current_stage}`);
    if (col) col.appendChild(renderCard(task));
  }
}

// ─── API ────────────────────────────────────────────────────────────────────

async function loadInitialState() {
  const r = await fetch("/api/state");
  const s = await r.json();
  state.tasks = {};
  for (const t of s.tasks) state.tasks[t.id] = t;
  state.running = s.running;
  renderAll();
  updateLaunchButton();
}

async function launchPipeline() {
  const btn = document.getElementById("launch-btn");
  btn.disabled = true;
  setStateLabel("pipeline running...", "running");
  try {
    const r = await fetch("/api/launch", { method: "POST" });
    if (!r.ok && r.status !== 409) {
      console.error("launch failed", r.status);
      btn.disabled = false;
      setStateLabel("launch failed — check console");
    }
  } catch (e) {
    console.error(e);
    btn.disabled = false;
  }
}

async function approveTask(taskId) {
  await fetch(`/api/approve/${taskId}`, { method: "POST" });
}

function updateLaunchButton() {
  const btn = document.getElementById("launch-btn");
  if (state.running) {
    btn.disabled = true;
    btn.textContent = "▶ Running...";
  } else {
    const allMerged = Object.values(state.tasks).every((t) => t.status === "merged");
    btn.disabled = false;
    btn.textContent = allMerged ? "↻ Run Again" : "▶ Launch Pipeline";
  }
}

function checkComplete() {
  const tasks = Object.values(state.tasks);
  if (tasks.length === 0) return;
  if (tasks.every((t) => t.status === "merged")) {
    state.running = false;
    setStateLabel("complete — both tickets merged ✓", "complete");
    updateLaunchButton();
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
        renderAll();
        updateLaunchButton();
      } else if (payload.type === "event") {
        const t = payload.task;
        state.tasks[t.id] = t;
        renderAll();
        if (t.status === "merged") checkComplete();
        if (t.status === "blocked") {
          state.running = true;
          setStateLabel("awaiting approval — click [APPROVE]", "running");
        }
      }
    } catch (e) {
      console.error("SSE parse", e);
    }
  };
  es.onerror = (e) => {
    console.error("SSE error", e);
    setStateLabel("SSE disconnected — retrying...", "");
    // EventSource auto-reconnects
  };
}

// ─── boot ───────────────────────────────────────────────────────────────────

document.getElementById("launch-btn").addEventListener("click", launchPipeline);
loadInitialState().then(() => {
  connectSSE();
});
