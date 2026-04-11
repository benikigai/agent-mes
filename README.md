# AgentMES

> A manufacturing execution system for autonomous agents.
> Built at the Blaxel × Codex × Redis AI Hack Day, Wordware HQ, San Francisco — 2026-04-11.

AgentMES implements OpenAI's 7-stage AI-Native Engineering Workflow as a bipartite state machine where agents do throughput work and humans own the judgment gates. Tickets flow left to right through 7 columns in a terminal kanban; receipts accumulate inside each card so the final card body IS the audit trail.

The demo runs **two tickets in parallel** through the same pipeline:
- ⚙ **TKT-001 (CODE):** an OAuth `/v2` rate-limit fix that triggers the Stage 5 memory-drift catch
- ✉ **TKT-002 (SIMPLE):** a status-update email about a recent incident

Both finish in `merged` state in under 10 seconds, demonstrating that AgentMES handles knowledge work and code work with the same orchestrator.

## Install

```bash
cd ~/code/blaxel-codex-redis-hackathon
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Run the demo

```bash
agent-mes demo                          # full pipeline, dry-run friendly
agent-mes demo --dry-run                # don't open real GitHub PRs
agent-mes demo --speed 1000             # fast Codex replay (for tests)
make demo                               # via Makefile
make smoke                              # run the end-to-end gate test
```

When the live integrations land (`vish/redis-blaxel` branch), wire 1Password secrets:

```bash
op run --env-file=.env.tpl -- agent-mes demo
```

## Architecture

```
┌─ AgentMES TUI (Rich Live, refresh 10/s) ───────────────────────────────────┐
├──────────┬─────────┬────────┬───────┬────────┬──────────┬─────────────────┤
│   PLAN   │ DESIGN  │ BUILD  │  TEST │ REVIEW │ DOCUMENT │ DEPLOY/MAINTAIN │
├──────────┼─────────┼────────┼───────┼────────┼──────────┼─────────────────┤
│          │         │        │       │        │          │ ┌[⚙ TKT-001]┐  │
│          │         │        │       │        │          │ │OAuth fix   │  │
│          │         │        │       │        │          │ │━ PLAN ━    │  │
│          │         │        │       │        │          │ │✓ classified│  │
│          │         │        │       │        │          │ │━ DESIGN ━  │  │
│          │         │        │       │        │          │ │✓ Opus      │  │
│          │         │        │       │        │          │ │✓ Codex     │  │
│          │         │        │       │        │          │ │✓ Gemini    │  │
│          │         │        │       │        │          │ │━ BUILD ━   │  │
│          │         │        │       │        │          │ │✓ +47/-3    │  │
│          │         │        │       │        │          │ │━ TEST ━    │  │
│          │         │        │       │        │          │ │✗ iter1 FAIL│  │
│          │         │        │       │        │          │ │✗ iter2 KILL│  │
│          │         │        │       │        │          │ │  evil.com  │  │
│          │         │        │       │        │          │ │✓ iter3 PASS│  │
│          │         │        │       │        │          │ │━ REVIEW ━  │  │
│          │         │        │       │        │          │ │⚠ DRIFT     │  │
│          │         │        │       │        │          │ │✓ HUMAN ✓   │  │
│          │         │        │       │        │          │ │━ DOCUMENT ━│  │
│          │         │        │       │        │          │ │✓ Redis     │  │
│          │         │        │       │        │          │ │━ DEPLOY ━  │  │
│          │         │        │       │        │          │ │✓ PR opened │  │
│          │         │        │       │        │          │ └────────────┘  │
└──────────┴─────────┴────────┴───────┴────────┴──────────┴─────────────────┘
```

Cards on the left start short. As they progress through the columns, more lines accumulate inside the card body. By the time a card lands in DEPLOY it contains its complete structured changelog — every stage's agent, action, metadata fields, and artifact references.

See `docs/demo-screenshot.txt` for a real captured render from the dashboard.

## The 7 stages

| # | Stage | Agent(s) | Sponsor | Demo beat |
|---|---|---|---|---|
| 1 | Plan | Opus 4.6 | **Wordware** (Natural Language Compiler) | Slack rant → typed AWP JSON in 200ms |
| 2 | Design | Opus 4.6 + Codex + Gemini | **Redis Memory** + **Redis Context Surfaces** | Hydrates `memory_provenance` and `context_bundle` in parallel |
| 3 | Build | Codex | **OpenAI Codex** (replay) | asciinema replay of a real Codex worktree run |
| 4 | Test | Gemini (in Blaxel sandbox) | **Blaxel** | Self-heal loop: iter1 FAIL → iter2 BLAST_RADIUS_VIOLATION egress kill at 23ms → iter3 PASS |
| 5 | Review | Opus 4.6 + HUMAN gate | **Redis** (adversary side) | Memory drift catch: memory says `/v1/login`, ticket says `/v2/oauth` — structural contradiction |
| 6 | Document | (data sink) | **Redis Memory** | Decision log written as `negative_constraint=True` lesson |
| 7 | Deploy & Maintain | (data sink) | **Blaxel** standby + **Redis** breadcrumb + **GitHub** PR | Real PR opened with full receipts as PR body |

## Sponsor credits

Built with **Wordware**, **Blaxel**, **OpenAI Codex**, **Redis Agent Memory Server**, and **Redis Context Surfaces**.

## Spec & runtime

- Full spec: [`docs/specs/agentmes.md`](docs/specs/agentmes.md)
- Research notes: [`docs/specs/agentmes-research.md`](docs/specs/agentmes-research.md)
- Judge intel: [`research/judges-intel.md`](research/judges-intel.md)
- Demo screenshot: [`docs/demo-screenshot.txt`](docs/demo-screenshot.txt)

## Submission checklist

- [x] Project name `AgentMES` claimed
- [x] GitHub repo public: https://github.com/benikigai/agent-mes
- [x] README has elevator pitch
- [x] Sponsor credit line in README
- [x] End-to-end smoke test passing (`make smoke`)
- [x] 57/57 tests green
- [ ] Asciinema recording committed to `recordings/full-demo.cast` (capture during H8 polish)
- [ ] 3 timed pitch rehearsals completed
- [ ] Demo requested in the dashboard

## Status

Built autonomously via `/yolo` against `docs/specs/agentmes-yolo.md`. 23 tasks, 57 tests, single feature branch `feat/agentmes`.
