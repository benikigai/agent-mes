# Context: AgentMES Web UI
**Last updated:** 2026-04-11
**Phase:** Spec approved
**Approved option:** Option A — Modular FastAPI + vanilla JS
**Branch:** feat/agentmes-web (off main b47a357)
**Tasks:** 10 (Simple: 8, Moderate: 2, Complex: 0)
**Estimated build time:** ~2 hours via /yolo
**Critic verdict:** APPROVE with 8 addressed concerns — no critical flaws

## Top risks
1. SSE drops on flaky wifi mid-demo — mitigated via push-full-state-on-reconnect
2. ReviewStage extension breaks existing tests — mitigated via backward-compat default (60 tests stay green)
3. macOS firewall first-launch prompt — Ben clicks Allow once

## Architecture summary
- New `agent_mes/web/` package (server.py, events.py, gates.py)
- One surgical extension: `ReviewStage.__init__(..., gate_provider=None)` — backward compatible
- Frontend: vanilla HTML/CSS/JS at `web/{index.html, style.css, app.js}` — no React, no build step
- Asciinema fallback moves to `web/replay.html` accessible at `/replay`
- New CLI command `agent-mes web` (terminal `agent-mes demo` unchanged)
- Bound to 0.0.0.0:8000 → reachable from MBP at http://100.85.105.99:8000 via Tailscale
- Inline [APPROVE] buttons for human gates (visible click on stage)
- Re-launchable pipeline (each /api/launch resets state)

## Reuse from PR #1 (terminal MVP)
- agent_mes/{schema, interfaces, pipeline, stages/*, integrations/*, demo/*} — UNCHANGED
- All 60 existing tests stay green
- Demo fixtures (TKT-001 flaky test, TKT-002 postmortem) reused verbatim

## Research
N/A — research gated OUT (well-known FastAPI/SSE patterns; no new external sponsor APIs)
