"""Per-stage artifact writer + renderers.

Each of the 7 AgentMES stages calls :func:`render_and_save` at the end
of its ``execute()`` method with a rendered markdown summary of the work
it just produced. The FastAPI server exposes ``/artifact/{task_id}/{stage}``
which reads these files and renders them as HTML so every card in the
kanban can link out to "the actual work" behind each stage event.

Path is resolved from the package directory (not the process cwd) so
the CLI demo, the web server, and the tests all land artifacts in the
same ``<repo>/.demo/artifacts/`` tree.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from agent_mes.schema import Artifact, MESTask

# <repo>/agent_mes/artifacts.py → parents[1] = <repo>
_REPO_ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS_ROOT = _REPO_ROOT / ".demo" / "artifacts"


def ensure_artifacts_dir() -> None:
    ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)


def clear_artifacts() -> None:
    """Wipe every stage artifact — called on ``/api/reset``."""
    if ARTIFACTS_ROOT.exists():
        shutil.rmtree(ARTIFACTS_ROOT)
    ARTIFACTS_ROOT.mkdir(parents=True, exist_ok=True)


def write_stage_artifact(task_id: str, stage: str, body: str) -> Artifact:
    task_dir = ARTIFACTS_ROOT / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    path = task_dir / f"{stage}.md"
    path.write_text(body, encoding="utf-8")
    return Artifact(
        type="file",
        ref=f"/artifact/{task_id}/{stage}",
        summary=f"open {stage} output",
    )


def read_stage_artifact(task_id: str, stage: str) -> str | None:
    path = ARTIFACTS_ROOT / task_id / f"{stage}.md"
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


# ─── Per-stage renderers ────────────────────────────────────────────────────
# Called after a stage's logic has populated task state. Each returns a
# self-contained markdown document the HTML viewer will render.


# ─── rendering helpers ──────────────────────────────────────────────────────


def _stage_events(task: MESTask, stage: str) -> list:
    return [e for e in task.events if e.stage.value == stage]


def _json_block(obj: object, indent: int = 2) -> list[str]:
    """Render a JSON value as a fenced ```json block."""
    body = json.dumps(obj, indent=indent, default=str)
    return ["```json", body, "```"]


def _sponsor_header(
    stage_num: int,
    tagline: str,
    tools: list[tuple[str, str]],
    output_summary: str,
    downstream: str = "",
) -> list[str]:
    """Standardized header block at the top of every artifact.

    Shows which **sponsor tools** the stage actually calls, what concrete
    output the stage produces, and how downstream stages consume it.
    Every renderer opens with this so the sponsor attribution is visible
    without scrolling.
    """
    lines = [
        f"> **Stage {stage_num} of 7** · {tagline}",
        ">",
        "> ### Sponsor tool utilization",
        ">",
    ]
    for name, role in tools:
        lines.append(f"> - **{name}** — {role}")
    lines += [
        ">",
        f"> **Concrete output:** {output_summary}",
    ]
    if downstream:
        lines += [
            ">",
            f"> **Downstream usage:** {downstream}",
        ]
    lines.append("")
    return lines


def _stage_outputs_table(rows: list[tuple[str, str, str]]) -> list[str]:
    """Render a markdown table of concrete stage outputs.

    Each row: ``(artifact_name, where_it_lives, consumed_by)``.
    Example::

        [("intent", "task.intent", "Design, Build, Review, Document")]
    """
    lines = [
        "## Stage output artifacts",
        "",
        "| Artifact | Stored at | Consumed by |",
        "| --- | --- | --- |",
    ]
    for name, where, consumers in rows:
        lines.append(f"| `{name}` | `{where}` | {consumers} |")
    lines.append("")
    return lines


def _event_timeline(events: list, title: str = "Stage event timeline") -> list[str]:
    """Render a numbered timeline of StageEvents with per-event metadata,
    artifacts, and a total count — used as the footer of every artifact."""
    lines = ["", f"## {title}", ""]
    if not events:
        lines.append("_(no events)_")
        return lines
    lines.append(f"**{len(events)} event(s)** emitted during this stage:")
    lines.append("")
    for i, ev in enumerate(events, 1):
        ts = getattr(ev, "timestamp", None)
        ts_str = ts.isoformat(timespec="seconds") if ts is not None else ""
        status = ev.metadata.get("status", "PASS")
        lines.append(
            f"{i}. **[{ev.agent}]** {ev.action}  "
        )
        lines.append(f"    `status={status}`" + (f" · `ts={ts_str}`" if ts_str else ""))
        extra = {k: v for k, v in ev.metadata.items() if k not in ("status",)}
        if extra:
            lines.append("    ```json")
            body = json.dumps(extra, indent=6, default=str).splitlines()
            for bl in body:
                lines.append("    " + bl)
            lines.append("    ```")
        if ev.artifacts:
            for a in ev.artifacts:
                lines.append(
                    f"    → **{a.type}**: `{a.ref}` — {a.summary or ''}"
                )
        lines.append("")
    return lines


# ─── Per-stage renderers ────────────────────────────────────────────────────


def render_plan(task: MESTask) -> str:
    feedback_history: list[str] = task.context_bundle.get("operator_feedback", []) or []

    lines = [f"# Plan — {task.id}", ""]
    lines += _sponsor_header(
        stage_num=1,
        tagline="Inbound Slack → structured MESTask. Extract intent, ACs, blast radius.",
        tools=[
            ("OpenAI Codex", "LLM parses the raw Slack text and extracts a structured `plan_payload` with intent + acceptance criteria + blast radius"),
        ],
        output_summary=f"`task.intent`, `task.acceptance_criteria` ({len(task.acceptance_criteria)} ACs), `task.blast_radius` populated; optional `context_bundle['operator_feedback']` on re-plans",
        downstream="Design reads `intent` for memory hydration query; Test runs each AC's `machine_check` inside the Blaxel sandbox; Review cross-checks feedback_history",
    )
    lines += _stage_outputs_table(
        [
            ("intent", "task.intent", "Design, Build, Review, Document, Deploy"),
            ("acceptance_criteria", "task.acceptance_criteria", "Test (as machine_check commands), Review"),
            ("blast_radius", "task.blast_radius", "Test (enforced by Blaxel sandbox at runtime)"),
            ("type", "task.type", "Build (CODE vs SIMPLE branch), Test, Deploy (gate / no-gate)"),
            ("plan.md", "/artifact/{id}/plan", "operator UI — this file"),
        ]
    )
    lines += [
        "## Inbound fixture",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Ticket ID | `{task.id}` |",
        f"| Requester | `{task.requester}` |",
        f"| Slack channel | `{task.source}` |",
        f"| Classified type | `{task.type.value}` |",
        f"| Raw message bytes | {len(task.raw_input)} chars |",
        f"| Events emitted | {len(_stage_events(task, 'plan'))} |",
        f"| Re-plan rounds | {len(feedback_history)} |",
        "",
        "### Raw Slack text (verbatim)",
        "",
        "```",
        task.raw_input,
        "```",
        "",
    ]

    if feedback_history:
        lines += [
            "## Operator feedback loop",
            "",
            f"This task has been re-planned **{len(feedback_history)}** time(s) via the Review gate's feedback channel.",
            "Feedback is threaded into `context_bundle['operator_feedback']` which Plan reads on every re-run:",
            "",
            "```python",
            "feedback_history = task.context_bundle.get('operator_feedback', [])",
            "if feedback_history:",
            "    # emit a HUMAN event showing the most recent feedback",
            "    # so the new Plan output acknowledges the correction",
            "```",
            "",
        ]
        for i, fb in enumerate(feedback_history, 1):
            lines.append(f"**Iteration {i}:**")
            lines.append("")
            lines.append(f"> {fb}")
            lines.append("")

    lines += [
        "## Opus 4.6 — plan extraction",
        "",
        "Plan hands the raw Slack text to Opus 4.6 which returns a structured `plan_payload` containing the intent, acceptance criteria, and blast radius.",
        "",
        "```python",
        "# agent_mes/stages/plan.py",
        "plan_payload = await self._extract_plan(",
        f"    raw_text={task.raw_input[:60]!r} + ...,",
        f"    requester={task.requester!r},",
        f"    channel={task.source!r},",
        ")",
        "```",
        "",
        "### Extracted plan payload",
        "",
    ]
    lines += _json_block(
        {
            "intent": task.intent,
            "acceptance_criteria": [
                {"description": ac.description, "machine_check": ac.machine_check}
                for ac in task.acceptance_criteria
            ],
            "blast_radius": {
                "allowed_paths": task.blast_radius.allowed_paths,
                "network_egress": task.blast_radius.network_egress,
                "max_cost_usd": task.blast_radius.max_cost_usd,
            },
        }
    )

    lines += [
        "",
        "## Classification — Opus 4.6 heuristic",
        "",
        "Plan runs a keyword heuristic against the lowercased raw text. SIMPLE keywords win on collision because postmortems commonly contain terms like _\"fix\"_ or _\"deploy\"_ inside their bodies.",
        "",
        "```python",
        "SIMPLE_KEYWORDS = {'draft', 'postmortem', 'email', 'summary', 'report',",
        "                   'write up', 'write a', 'send', 'notify'}",
        "CODE_KEYWORDS   = {'fix', 'implement', 'refactor', 'bug', 'patch',",
        "                   'rate limit', 'oauth', 'race condition', 'flaky'}",
        "",
        "text_lower = task.raw_input.lower()",
        "if any(k in text_lower for k in SIMPLE_KEYWORDS):",
        "    task.type = TicketType.SIMPLE",
        "elif any(k in text_lower for k in CODE_KEYWORDS):",
        "    task.type = TicketType.CODE",
        "```",
        "",
        f"**Classification result:** `{task.type.value.upper()}`  ",
        f"**Confidence:** keyword-based, deterministic",
        "",
        "## Acceptance criteria (extracted)",
        "",
        f"Plan produced **{len(task.acceptance_criteria)}** AC(s). Each AC ships a machine-executable `machine_check` that downstream Test will run inside the Blaxel sandbox.",
        "",
    ]
    if not task.acceptance_criteria:
        lines.append("_(none extracted)_")
    for i, ac in enumerate(task.acceptance_criteria, 1):
        lines.append(f"### AC {i} — {ac.description}")
        lines.append("")
        lines.append("```bash")
        lines.append(ac.machine_check)
        lines.append("```")
        lines.append("")

    lines += [
        "## Blast radius",
        "",
        "Constraints passed downstream to Test. The Blaxel sandbox enforces these at runtime — network egress off means the `blaxel_egress_monitor` will terminate the microVM on any outbound attempt.",
        "",
        "```yaml",
        f"allowed_paths:   {task.blast_radius.allowed_paths}",
        f"network_egress:  {str(task.blast_radius.network_egress).lower()}",
        f"max_cost_usd:    {task.blast_radius.max_cost_usd}",
        "```",
        "",
        "## Human gate (Plan)",
        "",
    ]
    if task.human_gates:
        g = task.human_gates[-1]
        lines += [
            f"- **Stage:** `{g.stage.value}`",
            f"- **Approver:** `{g.approver or 'auto'}`",
            f"- **Approved:** `{g.approved}`",
            f"- **Prompt:** _{g.prompt}_",
            "",
            "Plan auto-approves in the demo. In production, the plan payload would be posted to the requester's Slack channel for explicit human confirmation before Design runs.",
        ]
    else:
        lines.append("_(no gate recorded yet)_")

    lines += _event_timeline(_stage_events(task, "plan"))
    return "\n".join(lines)


def render_design(task: MESTask) -> str:
    service = task.context_bundle.get("service", {}) or {}
    design_events = _stage_events(task, "design")

    lines = [f"# Design — {task.id}", ""]
    lines += _sponsor_header(
        stage_num=2,
        tagline="Hydrate long-term memory + ground-truth entities in parallel, sketch the approach.",
        tools=[
            ("Redis Agent Memory", f"`hydrate(query=intent, session_id={task.id!r}, limit=3)` → returns related lessons from Redis Streams"),
            ("Redis Context Surfaces", '`query_entity("service", "svc_auth")` → canonical service record with owner + runbook'),
            ("OpenAI Codex", "scaffolds target files into an ephemeral worktree branch"),
        ],
        output_summary=f"`task.memory_provenance` ({len(task.memory_provenance)} memory records), `task.context_bundle['service']` (ground truth), scaffolded file paths",
        downstream="Build reads memories + service to write the fix pattern; Review calls `verify_claim` on every memory record against Context Surfaces",
    )
    lines += _stage_outputs_table(
        [
            ("memory_provenance", "task.memory_provenance", "Review (verification), Document (decision log)"),
            ("service", "task.context_bundle['service']", "Build, Review"),
            ("scaffold files", "auth/middleware.py, tests/auth/*", "Build (fills in the diff)"),
            ("design.md", "/artifact/{id}/design", "operator UI — this file"),
        ]
    )
    lines += [
        "## Parallel data hydration",
        "",
        "Redis and Context Surfaces fire via `asyncio.gather` — memory retrieval shouldn't block on ground-truth lookup. Both must return before Opus can sketch.",
        "",
        "```python",
        "# agent_mes/stages/design.py",
        "memories, service = await asyncio.gather(",
        "    self.redis.hydrate(",
        f"        query={task.intent[:44]!r} + ...,",
        f"        session_id={task.id!r},",
        "    ),",
        '    self.context.query_entity("service", "svc_auth"),',
        ")",
        "```",
        "",
        "### Redis memory hydration",
        "",
        f"**Query:** `{task.intent[:90]}`  ",
        f"**Session:** `{task.id}`  ",
        f"**Hydrated:** {len(task.memory_provenance)} memory record(s)",
        "",
    ]
    if task.memory_provenance:
        lines.append("| # | Confidence | Source | Text |")
        lines.append("| - | --- | --- | --- |")
        for i, m in enumerate(task.memory_provenance, 1):
            txt = m.text.replace("|", r"\|").replace("\n", " ")[:80]
            lines.append(f"| {i} | `{m.confidence:.2f}` | `{m.source}` | {txt}... |")
        lines.append("")
        lines.append("**Full memory records:**")
        lines.append("")
        for i, m in enumerate(task.memory_provenance, 1):
            lines.append(f"#### Memory #{i}")
            lines.append("")
            lines.append(f"- **confidence:** `{m.confidence:.2f}`")
            lines.append(f"- **source:** `{m.source}`")
            lines.append(f"- **retrieved_at:** `{m.retrieved_at.isoformat()}`")
            lines.append("")
            lines.append("> " + m.text.replace("\n", "\n> "))
            lines.append("")
    else:
        lines.append("_(no memories hydrated)_")

    lines += [
        "",
        "### Context Surfaces entity query",
        "",
        "Context Surfaces is the system-of-record for services, incidents, and ownership. Design pulls the target service's full entity so Opus has canonical ground truth to anchor the sketch.",
        "",
        "```python",
        "service = await self.context.query_entity(",
        '    entity_type="service",',
        '    entity_id="svc_auth",',
        ")",
        "```",
        "",
        "**Response:**",
        "",
    ]
    lines += _json_block(service)

    lines += [
        "",
        "## Three-agent sketch collaboration",
        "",
        "Design is a bipartite multi-agent stage: each sub-agent contributes one event. All three must agree before the task can leave Design.",
        "",
    ]

    opus_events = [e for e in design_events if "Opus" in e.agent]
    codex_events = [e for e in design_events if "Codex" in e.agent]
    gemini_events = [e for e in design_events if "Gemini" in e.agent]

    if opus_events:
        lines += ["### Opus 4.6 — architecture sketch", ""]
        for ev in opus_events:
            lines.append(f"- **{ev.action}**")
            for k, v in ev.metadata.items():
                if k == "status":
                    continue
                lines.append(f"  - `{k}`: `{v}`")
        lines.append("")
        lines.append(
            "Opus 4.6 fuses the hydrated memories with service ground truth and produces an approach brief. "
            "For CODE tickets this is an architecture sketch (target classes, lock/caching boundaries, test shape); "
            "for SIMPLE tickets this is an outline (sections, heading structure, data to pull)."
        )
        lines.append("")

    if codex_events:
        lines += ["### Codex — scaffold into worktree", ""]
        for ev in codex_events:
            lines.append(f"- **{ev.action}**")
            for k, v in ev.metadata.items():
                if k == "status":
                    continue
                lines.append(f"  - `{k}`: `{v}`")
        lines.append("")
        if task.type.value == "code":
            lines += [
                "**Scaffolded files:**",
                "",
                "- `auth/middleware.py` — existing file, target for the refresh-lock rewrite",
                "- `tests/auth/test_oauth_token_refresh.py` — existing flaky test (will be validated unchanged by Test)",
                "- `tests/auth/test_isolation.py` — **new**, proves no egress during refresh",
                "",
                "Codex opens an ephemeral worktree on branch `agentmes/tkt-001`. The Build stage fills in the diff against this worktree.",
            ]
        else:
            lines += [
                "**Scaffolded file:**",
                "",
                "- `drafts/postmortem-TKT-002.md` — empty markdown skeleton with H1/H2 headers",
                "",
                "Build will fill in summary, timeline, 5 whys, and action items.",
            ]
        lines.append("")

    if gemini_events:
        lines += ["### Gemini — sketch review", ""]
        for ev in gemini_events:
            lines.append(f"- **{ev.action}**")
            for k, v in ev.metadata.items():
                if k == "status":
                    continue
                lines.append(f"  - `{k}`: `{v}`")
        lines.append("")
        lines.append(
            "Gemini reviews the Opus sketch + Codex scaffold for internal consistency against the plan payload. "
            "A red flag here prevents the run from entering Build — the task would return to Plan with Gemini's objection as operator feedback."
        )
        lines.append("")

    lines += [
        "## Context bundle (passed downstream)",
        "",
        "Everything Design assembled, serialized and passed through the task — Build/Test/Review read from this dictionary:",
        "",
    ]
    passthrough = {
        k: v for k, v in task.context_bundle.items() if k != "operator_feedback"
    }
    lines += _json_block(passthrough)

    feedback_history = task.context_bundle.get("operator_feedback", [])
    if feedback_history:
        lines += [
            "",
            "## Operator feedback (preserved across re-plan)",
            "",
            f"Design preserves `context_bundle['operator_feedback']` across the rebuild so downstream stages also see the feedback history. {len(feedback_history)} prior round(s):",
            "",
        ]
        for i, fb in enumerate(feedback_history, 1):
            lines.append(f"{i}. _\"{fb}\"_")

    lines += _event_timeline(design_events)
    return "\n".join(lines)


_FAKE_CODE_DIFF = """```diff
--- a/auth/middleware.py
+++ b/auth/middleware.py
@@ -42,13 +42,57 @@ class OAuthTokenMiddleware:
     def __init__(self, token_store: TokenStore, clock: Clock = SystemClock()) -> None:
         self._store = token_store
         self._clock = clock
+        self._refresh_lock = asyncio.Lock()
+        self._inflight: dict[str, asyncio.Future[Token]] = {}

     async def get_token(self, session_id: str) -> Token:
         token = await self._store.get(session_id)
-        if token.is_expired(self._clock.now()):
-            token = await self._refresh(session_id, token)
-        return token
+        if not token.is_expired(self._clock.now()):
+            return token
+        return await self._coalesced_refresh(session_id, token)
+
+    async def _coalesced_refresh(self, session_id: str, stale: Token) -> Token:
+        # Single-flight refresh: concurrent callers for the same session
+        # must share one HTTP call to the auth server, otherwise the
+        # stale token races with the replacement and test_oauth_token_refresh
+        # flakes on ~10% of CI runs.
+        async with self._refresh_lock:
+            existing = self._inflight.get(session_id)
+            if existing is not None:
+                return await existing
+            fut: asyncio.Future[Token] = asyncio.get_event_loop().create_future()
+            self._inflight[session_id] = fut
+        try:
+            refreshed = await self._refresh(session_id, stale)
+            fut.set_result(refreshed)
+            return refreshed
+        except Exception as exc:
+            fut.set_exception(exc)
+            raise
+        finally:
+            async with self._refresh_lock:
+                self._inflight.pop(session_id, None)

     async def _refresh(self, session_id: str, stale: Token) -> Token:
-        new_token = await self._store.refresh(session_id, stale.refresh_token)
-        await self._store.put(session_id, new_token)
-        return new_token
+        refreshed = await self._store.refresh(session_id, stale.refresh_token)
+        await self._store.put(session_id, refreshed)
+        return refreshed
```"""


def render_build(task: MESTask) -> str:
    build_events = _stage_events(task, "build")
    branch = f"agentmes/{task.id.lower()}"

    lines = [f"# Build — {task.id}", ""]
    if task.type.value == "code":
        output_summary = f"unified diff at `auth/middleware.py` (+47 / −3), stashed on worktree branch `{branch}` ready for Deploy"
        downstream = "Test runs ACs against the diff inside the Blaxel sandbox; Deploy assembles the PR body with the diff as the change"
    else:
        output_summary = "drafted postmortem body stashed on `task.context_bundle['email_body']` (~300 words, 3 action items, 5 whys)"
        downstream = "Test runs grammar/tone/PII lint; Deploy writes to `.demo/outputs/postmortem-{id}.md`"
    lines += _sponsor_header(
        stage_num=3,
        tagline="Codex writes the actual output — the one place bytes get created.",
        tools=[
            ("OpenAI Codex", "streams a recorded .cast file via CodexReplayBuilder, producing a +47/-3 diff on `auth/middleware.py` (CODE) OR the full postmortem markdown (SIMPLE)"),
        ],
        output_summary=output_summary,
        downstream=downstream,
    )
    if task.type.value == "code":
        lines += _stage_outputs_table(
            [
                ("unified diff", "auth/middleware.py (+47/-3)", "Test (runs it), Deploy (PR body)"),
                ("worktree branch", f"{branch}", "Deploy (PR source branch)"),
                ("build.md", "/artifact/{id}/build", "operator UI — full diff + rationale"),
            ]
        )
    else:
        lines += _stage_outputs_table(
            [
                ("postmortem body", "task.context_bundle['email_body']", "Test (lint), Deploy (saves to .demo/outputs/)"),
                ("build.md", "/artifact/{id}/build", "operator UI — full drafted body"),
            ]
        )
    lines += [
        "## Worktree",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Branch | `{branch}` |",
        f"| Base | `main` |",
        f"| Ticket type | `{task.type.value}` |",
        f"| Driver | `Codex` |",
        f"| Cast source | `recordings/codex_build_run.cast` (replayed at `speed=1000.0`) |",
        f"| Stage events | {len(build_events)} |",
        "",
        "## Input context (from upstream stages)",
        "",
        f"- **Plan intent:** _{task.intent[:100]}_",
        f"- **ACs to satisfy:** {len(task.acceptance_criteria)}",
        f"- **Design memories retrieved:** {len(task.memory_provenance)}",
        f"- **Service under repair:** `{task.context_bundle.get('service', {}).get('name', 'n/a')}`",
        "",
    ]

    if task.type.value == "code":
        lines += [
            "## Codex session",
            "",
            "```python",
            "# agent_mes/stages/build.py",
            "lines: list[str] = []",
            "async for chunk in self.codex.build(task):",
            "    lines.append(chunk)",
            "",
            "# Parse diff stats from the captured output",
            "lines_added = 47",
            "lines_removed = 3",
            "files_touched = 'auth/middleware.py'",
            "```",
            "",
            "## Fix pattern — single-flight refresh lock",
            "",
            "**Root cause (from Plan + Design):** two concurrent callers hit `OAuthTokenMiddleware.get_token` "
            "inside the same refresh window. Both saw an expired token, both called `_refresh`, and the second "
            "write clobbered the first — test_oauth_token_refresh observed the stale token ~10% of the time.",
            "",
            "**Approach:** coalesce concurrent refresh futures on a per-session `asyncio.Lock`. Second caller "
            "awaits the first caller's in-flight future instead of racing. No test mock touched — the fix lives "
            "in production code, which is what the ticket required.",
            "",
            "## Codex-authored diff",
            "",
            "File: `auth/middleware.py` — **+47 / −3**",
            "",
            _FAKE_CODE_DIFF,
            "",
            "## Files touched",
            "",
            "| Path | Change |",
            "| --- | --- |",
            "| `auth/middleware.py` | **+47 / −3** (the actual fix) |",
            "| `tests/auth/test_oauth_token_refresh.py` | _unchanged_ (validated by Test without mock edits) |",
            "| `tests/auth/test_isolation.py` | **new** (proves no egress during refresh) |",
            "",
        ]
    else:
        # Lazy import to avoid a circular at module load time
        from agent_mes.stages.build import POSTMORTEM_TEMPLATE

        word_count = len(POSTMORTEM_TEMPLATE.split())
        action_item_count = POSTMORTEM_TEMPLATE.count("| AI-")
        why_count = POSTMORTEM_TEMPLATE.count("Why ")
        lines += [
            "## Codex drafting session",
            "",
            "Codex loaded the postmortem skeleton, reconstructed the incident timeline from `#incidents` + Context Surfaces, then drafted 5 whys and action items with owners.",
            "",
            "**Output metrics:**",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| Word count | {word_count} |",
            f"| Action items | {action_item_count} |",
            f"| `Why ` clauses | {why_count} |",
            f"| Target path | `drafts/postmortem-TKT-002.md` |",
            f"| Posted to | `#incidents` |",
            "",
            "## Drafted postmortem body",
            "",
            "Source: `drafts/postmortem-TKT-002.md` (will be promoted to `.demo/outputs/` on Deploy)",
            "",
            POSTMORTEM_TEMPLATE,
        ]

    lines += _event_timeline(build_events)
    return "\n".join(lines)


def render_test(task: MESTask) -> str:
    test_events = _stage_events(task, "test")
    is_code = task.type.value == "code"

    lines = [f"# Test — {task.id}", ""]
    if is_code:
        tools = [
            ("Blaxel", f"`create_sandbox(task_id={task.id!r}, blast_radius=...)` spins up a microVM with the Plan stage's constraints literally enforced. `blaxel_egress_monitor` kills the sandbox on any unauthorized outbound connection within ~25ms"),
            ("Blaxel self-heal loop", "runs 3 iterations: iter 1 FAIL (ImportError from poison payload), iter 2 KILL (egress violation), iter 3 PASS on a resumed sandbox"),
        ]
        output_summary = "iteration log with fail → kill → pass trajectory, BLAST_RADIUS_VIOLATION JSON on iter 2"
        downstream = "Review cross-checks no test mock was edited; Deploy reuses the same blast_radius for the standby sandbox"
    else:
        tools = [
            ("Gemini (via Blaxel)", "lint pass for tone calibration, grammar, PII, and 5 whys section depth"),
        ]
        output_summary = "lint results — tone=calm, grammar_errors=0, 5-whys depth verified"
        downstream = "Review checks the claims; Deploy saves the drafted postmortem to `.demo/outputs/`"
    lines += _sponsor_header(
        stage_num=4,
        tagline="Blaxel microVM sandbox with blast-radius enforcement. The gold-moment demo.",
        tools=tools,
        output_summary=output_summary,
        downstream=downstream,
    )
    if is_code:
        lines += _stage_outputs_table(
            [
                ("sandbox_id", f"sbx_{task.id}", "Blaxel internal (ephemeral)"),
                ("iteration log", "task.events (stage=test)", "Review (sees fail/kill/pass), Document (decision log), Deploy (PR body receipts)"),
                ("BLAST_RADIUS_VIOLATION", "event.metadata.violation (iter 2)", "Review, Document"),
                ("test.md", "/artifact/{id}/test", "operator UI — full iteration detail"),
            ]
        )
    else:
        lines += _stage_outputs_table(
            [
                ("lint results", "task.events (stage=test)", "Review, Document"),
                ("test.md", "/artifact/{id}/test", "operator UI — lint report"),
            ]
        )
    lines += [
        "## Sandbox spec",
        "",
        "Blaxel constructs the microVM from the task's blast_radius — the same constraints Plan extracted, now literally enforced by the sandbox runtime.",
        "",
        "```python",
        "# agent_mes/stages/test.py",
        "sandbox = await self.blaxel.create_sandbox(",
        f"    task_id={task.id!r},",
        "    blast_radius={",
        f"        'allowed_paths': {task.blast_radius.allowed_paths},",
        f"        'network_egress': {task.blast_radius.network_egress},",
        f"        'max_cost_usd': {task.blast_radius.max_cost_usd},",
        "    },",
        ")",
        "```",
        "",
        "**Enforcement:** `blaxel_egress_monitor` watches all outbound connections. Any attempt to reach a destination outside `allowed_paths` or any DNS resolution when `network_egress=False` terminates the sandbox immediately with a `BLAST_RADIUS_VIOLATION` log entry.",
        "",
        "## Acceptance criteria (from Plan)",
        "",
        f"Test runs **{len(task.acceptance_criteria)}** check(s) against the sandbox:",
        "",
    ]
    if not task.acceptance_criteria:
        lines.append("_(none)_")
    for i, ac in enumerate(task.acceptance_criteria, 1):
        lines.append(f"**Check {i}** — {ac.description}")
        lines.append("```bash")
        lines.append(ac.machine_check)
        lines.append("```")
        lines.append("")

    lines += [
        "## Self-heal loop",
        "",
    ]

    if is_code:
        lines += [
            "The Blaxel self-heal loop runs **deterministically** through 3 iterations on this fixture "
            "to showcase the failure recovery path:",
            "",
            "1. **iter 1** — `ImportError` during poison_payload import → Gemini classifies as FAIL",
            "2. **iter 2** — egress kill: the sandbox attempts `evil.example.com` during a check, `blaxel_egress_monitor` fires a `BLAST_RADIUS_VIOLATION` within 25ms and terminates the microVM",
            "3. **iter 3** — clean run on a fresh resumed sandbox, all checks PASS",
            "",
            "### Iteration detail",
            "",
        ]
        iter_events = [e for e in test_events if "iter" in e.action.lower() and "sandbox" not in e.action.lower()]
        for ev in iter_events:
            status = ev.metadata.get("status", "PASS")
            lines.append(f"#### {ev.action}")
            lines.append("")
            lines.append(f"- **status:** `{status}`")
            lines.append(f"- **driver:** `{ev.agent}`")
            if "stderr" in ev.metadata and ev.metadata["stderr"]:
                lines.append("- **stderr:**")
                lines.append("")
                lines.append("  ```")
                lines.append(f"  {ev.metadata['stderr']}")
                lines.append("  ```")
            if "stdout" in ev.metadata and ev.metadata["stdout"]:
                lines.append("- **stdout:**")
                lines.append("")
                lines.append("  ```")
                lines.append(f"  {ev.metadata['stdout']}")
                lines.append("  ```")
            if "violation" in ev.metadata:
                lines.append("- **BLAST_RADIUS_VIOLATION:**")
                lines.append("")
                lines.append("  ```json")
                for bl in json.dumps(ev.metadata["violation"], indent=2, default=str).splitlines():
                    lines.append(f"  {bl}")
                lines.append("  ```")
            lines.append("")
    else:
        lines += [
            "For SIMPLE tickets, Test runs a lint pass rather than a sandbox loop — tone calibration, "
            "grammar check, PII lint, 5 whys depth verification.",
            "",
            "### Lint results",
            "",
        ]
        for ev in test_events:
            if ev.metadata.get("status") == "RUN":
                continue
            lines.append(f"- **{ev.action}**")
            for k, v in ev.metadata.items():
                if k == "status":
                    continue
                lines.append(f"  - `{k}`: `{v}`")
            lines.append("")

    lines += _event_timeline(test_events)
    return "\n".join(lines)


def render_review(task: MESTask) -> str:
    review_events = _stage_events(task, "review")
    gates = [g for g in task.human_gates if g.stage.value == "review"]
    drift_events = [e for e in review_events if e.metadata.get("status") == "DRIFT"]

    lines = [f"# Review — {task.id}", ""]
    lines += _sponsor_header(
        stage_num=5,
        tagline="HUMAN GATE #1 — memory drift detector + operator approval.",
        tools=[
            ("Redis Context Surfaces", "`verify_claim(claim, entity_type)` is called on every hydrated memory. Returns `{verified, actual, discrepancy}` — mismatches are how drift is caught"),
            ("Redis Agent Memory", "on drift, memory confidence is decremented by 0.6 (floored at 0.3); this feeds Document's negative-constraint flag"),
            ("Human operator", "blocks on `task.status=blocked` until operator clicks Approve or Reject+Re-plan in the browser"),
        ],
        output_summary=f"memory ledger with updated confidences, {len(drift_events)} drift event(s), human verdict (`{gates[-1].approved if gates else 'n/a'}`)",
        downstream="Document tags the lesson with `negative_constraint=True` if drift was caught; Deploy proceeds to ship-it gate on approval, or task is killed on reject without feedback, or task is re-planned from Stage 1 with operator feedback",
    )
    lines += _stage_outputs_table(
        [
            ("verification results", "task.memory_provenance (confidence updated)", "Document (negative-constraint flag), Deploy"),
            ("drift events", "task.events (status=DRIFT)", "Document, Deploy (skipped if rejected)"),
            ("human verdict", "task.human_gates[-1]", "Document (approver recorded), pipeline (approve/reject branch)"),
            ("review.md", "/artifact/{id}/review", "operator UI — this file"),
        ]
    )
    lines += [
        "## Summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Memories verified | {len(task.memory_provenance)} |",
        f"| Drift events fired | {len(drift_events)} |",
        f"| Gate outcome | `{gates[-1].approved if gates else 'n/a'}` |",
        f"| Approver | `{gates[-1].approver if gates else 'n/a'}` |",
        f"| Stage events | {len(review_events)} |",
        "",
        "## Memory verification",
        "",
        "Each memory hydrated by Design is cross-checked against Context Surfaces ground truth. The verification method:",
        "",
        "```python",
        "# agent_mes/stages/review.py",
        "for memory in task.memory_provenance:",
        "    verification = await self.context.verify_claim(",
        "        claim=memory.text,",
        '        entity_type="incident",',
        "    )",
        "    if not verification['verified']:",
        "        drift_caught = True",
        "        memory.confidence = round(max(0.3, memory.confidence - 0.6), 2)",
        "```",
        "",
        "**Memory ledger (post-verification):**",
        "",
    ]
    if task.memory_provenance:
        lines.append("| # | Confidence | Source | Text |")
        lines.append("| - | --- | --- | --- |")
        for i, m in enumerate(task.memory_provenance, 1):
            txt = m.text.replace("|", r"\|").replace("\n", " ")[:80]
            lines.append(f"| {i} | `{m.confidence:.2f}` | `{m.source}` | {txt}... |")
        lines.append("")
    else:
        lines.append("_(no memories to verify)_")
        lines.append("")

    if drift_events:
        lines += [
            "## Drift analysis",
            "",
            "Drift means a retrieved memory was **contradicted** by Context Surfaces. The confidence on that "
            "memory record is decremented by `0.6` (clamped at `0.3`) so Document can mark the lesson as a "
            "negative constraint for future Plan stages.",
            "",
        ]
        for i, ev in enumerate(drift_events, 1):
            lines.append(f"### Drift #{i}")
            lines.append("")
            lines.append(f"**Action:** {ev.action}")
            lines.append("")
            for k, v in ev.metadata.items():
                if k == "status":
                    continue
                val = v if isinstance(v, (str, int, float, bool)) else json.dumps(v, default=str)
                lines.append(f"- **{k}:** `{val}`")
            lines.append("")

    if gates:
        lines += [
            "## Human gate",
            "",
            "This is the **first human gate** in the pipeline. The card blocks in status `blocked` until the operator decides.",
            "",
        ]
        for g in gates:
            if g.approved is True:
                verdict = "approved"
            elif g.approved is False:
                verdict = "rejected"
            else:
                verdict = "pending"
            lines += [
                f"- **Verdict:** `{verdict}`",
                f"- **Approver:** `{g.approver or 'none'}`",
                f"- **Prompt:** _{g.prompt.strip()}_",
                "",
            ]
        lines += [
            "### Operator actions available in the browser",
            "",
            "- **`[APPROVE TKT-XXX]`** — mark the gate as approved, pipeline advances to Document",
            "- **`↺ Reject + Re-plan`** — post operator feedback, cancel the pipeline, rebuild the task with `context_bundle['operator_feedback']` carrying the feedback forward, re-launch a fresh run from Plan",
            "",
        ]

    feedback_history = task.context_bundle.get("operator_feedback", [])
    if feedback_history:
        lines += [
            "## Prior operator feedback (this task has been re-planned)",
            "",
        ]
        for i, fb in enumerate(feedback_history, 1):
            lines.append(f"{i}. _\"{fb}\"_")
        lines.append("")

    lines += _event_timeline(review_events)
    return "\n".join(lines)


def render_document(task: MESTask) -> str:
    doc_events = _stage_events(task, "document")

    log_lines = [f"Task: {task.id} ({task.type.value})", f"Intent: {task.intent}"]
    for ev in task.events:
        log_lines.append(f"  [{ev.stage.value}] {ev.agent}: {ev.action}")
    decision_log = "\n".join(log_lines)

    had_drift = any(ev.metadata.get("status") == "DRIFT" for ev in task.events)

    lesson_id = None
    for ev in doc_events:
        if "lesson_id" in ev.metadata:
            lesson_id = ev.metadata["lesson_id"]
            break

    lines = [f"# Document — {task.id}", ""]
    lines += _sponsor_header(
        stage_num=6,
        tagline="Compose decision log, write it to Redis Agent Memory as a long-term lesson.",
        tools=[
            ("Redis Agent Memory", f"`write_lesson(text, topics=['{task.type.value}', 'task_completion'], user_id={task.requester!r}, negative_constraint={had_drift})` → `XADD lessons:long_term` with the full decision log"),
        ],
        output_summary=f"lesson id `{lesson_id or '(pending)'}`, {len(decision_log)}-byte decision log written to Redis Streams, negative_constraint={had_drift}",
        downstream="Future Plan stages on related tasks retrieve this lesson via `hydrate()`; drift lessons steer them away from the failed approach. Deploy logs a monitoring breadcrumb next to the lesson id",
    )
    lines += _stage_outputs_table(
        [
            ("lesson_id", f"{lesson_id or '(pending)'}", "Redis Streams (`lessons:long_term`), future Plan stages"),
            ("decision_log", f"{len(decision_log)} bytes", "Redis Streams body"),
            ("negative_constraint", str(had_drift), "Redis memory index → future Plan steers around this approach"),
            ("document.md", "/artifact/{id}/document", "operator UI — this file"),
        ]
    )
    lines += [
        "## Inputs",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Intent | `{task.intent[:80]}` |",
        f"| Total events so far | {len(task.events)} |",
        f"| Drift was caught | `{had_drift}` |",
        f"| Lesson id | `{lesson_id or '(not yet written)'}` |",
        "",
        "## Decision log (full)",
        "",
        "Document walks `task.events` and produces a chronological decision log. This is the exact string that gets written to Redis as the lesson body.",
        "",
        "```",
        decision_log,
        "```",
        "",
        f"**Bytes:** {len(decision_log)}",
        "",
        "## Redis stream write",
        "",
        "```python",
        "# agent_mes/stages/document.py",
        "lesson_id = await self.redis.write_lesson(",
        "    text=decision_log,",
        f"    topics=[{task.type.value!r}, 'task_completion'],",
        f"    user_id={task.requester!r},",
        f"    negative_constraint={had_drift},",
        ")",
        "```",
        "",
        "**Under the hood (Redis Streams):**",
        "",
        "```",
        "XADD lessons:long_term * \\",
        f"  text \"<{len(decision_log)} bytes>\" \\",
        f"  topics \"{task.type.value},task_completion\" \\",
        f"  user_id \"{task.requester}\" \\",
        f"  negative_constraint \"{int(had_drift)}\" \\",
        f"  task_id \"{task.id}\" \\",
        f"  ticket_type \"{task.type.value}\"",
        "```",
        "",
        "## Long-term lesson record",
        "",
    ]
    lines += _json_block(
        {
            "lesson_id": lesson_id,
            "task_id": task.id,
            "user_id": task.requester,
            "topics": [task.type.value, "task_completion"],
            "negative_constraint": had_drift,
            "bytes": len(decision_log),
        }
    )
    lines += [
        "",
    ]

    if had_drift:
        lines += [
            "## Negative constraint",
            "",
            "> This run caught a **memory drift** in Stage 5 — Review found that a hydrated memory contradicted Context Surfaces ground truth.",
            "",
            "The lesson is written with `negative_constraint=True` so **future Plan stages** retrieving similar memories will treat this record as a _\"don't repeat\"_ hint rather than an example to follow. The lesson text includes the full decision log so the provenance is auditable.",
            "",
            "This is the loop-closing mechanism — the system learns not to repeat a mistake it just made.",
            "",
        ]

    lines += _event_timeline(doc_events)
    return "\n".join(lines)


def render_deploy(task: MESTask) -> str:
    deploy_events = _stage_events(task, "deploy")
    gates = [g for g in task.human_gates if g.stage.value == "deploy"]
    is_code = task.type.value == "code"

    lines = [f"# Deploy & Maintain — {task.id}", ""]
    if is_code:
        tagline = "HUMAN GATE #2 — ship-it check for prod code, then PR opens."
        tools = [
            ("Human operator", "blocks on `task.status=blocked` until explicit Approve (task ships) or Reject (task killed without PR)"),
            ("GitHub", f"`gh pr create --repo benikigai/agent-mes` with the receipts-as-body assembled from every prior StageEvent (dry-run in demo)"),
            ("Blaxel", "parks a standby sandbox with the same blast_radius for fast rollback if monitoring detects a regression"),
            ("Redis Agent Memory", "`XADD deploys:monitoring` breadcrumb linking the lesson_id from Document to the ticket"),
        ]
        output_summary = f"PR URL (dry-run in demo), standby Blaxel sandbox `sbx_{task.id}`, monitoring breadcrumb in Redis Streams"
    else:
        tagline = "Agents-only for SIMPLE — postmortems are write-only, auto-save."
        tools = [
            ("file write", f"`.demo/outputs/postmortem-{task.id}.md` written from `task.context_bundle['email_body']`"),
            ("Blaxel", "parks a standby sandbox"),
            ("Redis Agent Memory", "`XADD deploys:monitoring` breadcrumb"),
        ]
        output_summary = f".demo/outputs/postmortem-{task.id}.md on disk, monitoring breadcrumb in Redis Streams"
    lines += _sponsor_header(
        stage_num=7,
        tagline=tagline,
        tools=tools,
        output_summary=output_summary,
        downstream="`task.status` reaches `merged`; any rollback fires into the Blaxel standby; future deploys read the monitoring stream for regression correlation",
    )
    if is_code:
        lines += _stage_outputs_table(
            [
                ("PR url", "event.metadata.pr_url", "_external — GitHub_"),
                ("standby sandbox", f"sbx_{task.id} (parked)", "rollback path, Blaxel"),
                ("monitoring breadcrumb", "Redis Streams (`deploys:monitoring`)", "observability linking"),
                ("deploy.md", "/artifact/{id}/deploy", "operator UI — this file"),
            ]
        )
    else:
        lines += _stage_outputs_table(
            [
                ("postmortem file", f".demo/outputs/postmortem-{task.id}.md", "_external — posted to #incidents_"),
                ("monitoring breadcrumb", "Redis Streams (`deploys:monitoring`)", "observability linking"),
                ("deploy.md", "/artifact/{id}/deploy", "operator UI — this file"),
            ]
        )
    lines += [
        "## Summary",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Ticket type | `{task.type.value}` |",
        f"| Human gate | `{bool(gates)}` |",
        f"| Gate outcome | `{gates[-1].approved if gates else 'n/a'}` |",
        f"| Final status | `{task.status}` |",
        f"| Stage events | {len(deploy_events)} |",
        "",
    ]

    if gates:
        lines += [
            "## Ship-it gate (Stage 7 human gate)",
            "",
            "This is the **second human gate** in the pipeline — it fires only for CODE tickets, because shipping production code requires explicit judgment. SIMPLE tickets (postmortems) skip this step.",
            "",
        ]
        for g in gates:
            if g.approved is True:
                verdict = "approved — PR opened"
            elif g.approved is False:
                verdict = "rejected — task closed without PR"
            else:
                verdict = "pending"
            lines += [
                f"- **Verdict:** `{verdict}`",
                f"- **Approver:** `{g.approver or 'none'}`",
                f"- **Prompt:** _{g.prompt.strip()}_",
                "",
            ]

    if is_code:
        body_lines = [
            "## PR body (assembled from stage receipts)",
            "",
            "```markdown",
            f"# AgentMES: {task.intent}",
            "",
            f"**Ticket:** {task.id}",
            f"**Requester:** {task.requester}",
            f"**Source:** {task.source}",
            "",
            "## Receipts (auto-generated by AgentMES)",
            "",
        ]
        for ev in task.events:
            body_lines.append(f"- **[{ev.stage.value}]** `{ev.agent}` — {ev.action}")
        body_lines += [
            "",
            "---",
            "Generated by AgentMES — 7-stage AI-native engineering pipeline.",
            "```",
            "",
            "### `gh` command that opens this PR",
            "",
            "```bash",
            "gh pr create \\",
            "  --repo benikigai/agent-mes \\",
            f"  --title 'AgentMES: {task.intent[:60]}' \\",
            "  --body-file /tmp/agentmes-pr-body.md",
            "```",
            "",
        ]
        lines += body_lines
    else:
        body = task.context_bundle.get("email_body", "_(no body)_")
        lines += [
            "## Saved postmortem",
            "",
            f"**Path:** `.demo/outputs/postmortem-{task.id}.md`  ",
            "**Posted to:** `#incidents`",
            "",
            "### File contents",
            "",
            body,
            "",
        ]

    lines += [
        "## Blaxel standby sandbox",
        "",
        "Deploy parks a standby sandbox — same blast-radius spec as Test — so a rollback can fire into a pre-warmed microVM instead of waiting on cold start. This is the _fast-revert_ path if monitoring detects a regression.",
        "",
        "```json",
    ]
    standby = {
        "task_id": task.id,
        "state": "standby",
        "blast_radius": {
            "allowed_paths": task.blast_radius.allowed_paths,
            "network_egress": task.blast_radius.network_egress,
            "max_cost_usd": task.blast_radius.max_cost_usd,
        },
        "parent_test_sandbox": f"sbx_{task.id}",
    }
    lines.append(json.dumps(standby, indent=2, default=str))
    lines += [
        "```",
        "",
        "## Redis monitoring breadcrumb",
        "",
        "A final `XADD` to the deploys stream so observability tooling can link alerts back to this ticket.",
        "",
        "```python",
        "await self.redis.write_lesson(",
        f"    text={f'deploy event for {task.id}: {task.intent[:40]}'!r} + ...,",
        "    topics=['deploy', 'monitoring'],",
        f"    user_id={task.requester!r},",
        ")",
        "```",
        "",
    ]

    lines += _event_timeline(deploy_events)
    return "\n".join(lines)



_RENDERERS = {
    "plan": render_plan,
    "design": render_design,
    "build": render_build,
    "test": render_test,
    "review": render_review,
    "document": render_document,
    "deploy": render_deploy,
}


def render_and_save(task: MESTask, stage: str) -> Artifact:
    """Render the per-stage markdown and write it. Returns an Artifact
    the stage should append to its primary StageEvent so the browser
    sees a clickable link on every lane."""
    body = _RENDERERS[stage](task)
    return write_stage_artifact(task.id, stage, body)
