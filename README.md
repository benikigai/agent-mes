# AgentMES

**A manufacturing execution system for autonomous agents.** AgentMES implements OpenAI's 7-stage AI-native engineering workflow — Plan → Design → Build → Test → Review → Document → Deploy/Maintain — as a bipartite state machine where **agents do the throughput work and humans own the judgment gates**.

Built for **Blaxel × Codex × Redis AI Hack Day**, Wordware HQ SF, 2026-04-11.

---

## What it does

Two demo tickets flow through seven stage columns in parallel:

- **⚙ TKT-001 (CODE):** an OAuth rate-limit fix that triggers a Stage 5 memory-drift catch and ends with a **real GitHub PR** at Deploy
- **✉ TKT-002 (SIMPLE):** a status-update email about a recent incident

Both tickets ride the same 7-stage pipeline. **Receipts are embedded inside the card body** — every stage event appends a line, so by the time a card lands in DEPLOY it contains its complete audit trail. Cards on the left are short, cards on the right are tall. **The card *is* the receipt.**

```
┌──────┬────────┬───────┬──────┬────────┬──────────┬─────────────────┐
│ PLAN │ DESIGN │ BUILD │ TEST │ REVIEW │ DOCUMENT │ DEPLOY/MAINTAIN │
├──────┼────────┼───────┼──────┼────────┼──────────┼─────────────────┤
│      │        │       │      │        │          │ ┌[⚙ TKT-001]┐  │
│      │        │       │      │        │          │ │ OAuth fix  │  │
│      │        │       │      │        │          │ │ ✓ PLAN     │  │
│      │        │       │      │        │          │ │ ✓ DSGN ×3  │  │
│      │        │       │      │        │          │ │ ✓ BLD Codex│  │
│      │        │       │      │        │          │ │ ✗ TST i2 K │  │
│      │        │       │      │        │          │ │ ⚠ REV DRIFT│  │
│      │        │       │      │        │          │ │ ✓ HUMAN OK │  │
│      │        │       │      │        │          │ │ ✓ DEP PR#12│  │
│      │        │       │      │        │          │ └────────────┘  │
└──────┴────────┴───────┴──────┴────────┴──────────┴─────────────────┘
```

## Architecture

Rich `Live + Layout` TUI, refreshing 10/s, with seven vertical columns. Cards stack vertically inside the current column and grow as events accumulate.

The whole system is **interface-driven** (`agent_mes/interfaces.py` Protocol classes). Default DI wires choreographed stubs in `agent_mes/integrations/stubs/`; real Redis + Blaxel implementations swap in additively at H6+ via a single-line import change. Stubs are deterministic so the demo runs identically every rehearsal.

**Context data lives in a separate package** — [`benikigai/plushpalace-world`](https://github.com/benikigai/plushpalace-world) — a fictional DTC plushie e-commerce company (PlushPalace Co., CEO Mark Chen, viral Atticus the Axolotl, Shenzhen factory partner). Ships two `ContextStore` backends that share semantics: `StubStore` (in-memory) and `RedisStore` (Redis Stack: RedisJSON + RediSearch). The two smoking-gun postmortems (`pm-2026-02-14` rate limit, `pm-2025-11-22` mocked flaky test) are what Stage 5 Review catches as structural drift.

## Multi-model agent assignments

| Stage | Agent(s) |
|---|---|
| Plan | Opus 4.6 |
| Design | Opus 4.6 + Codex + Gemini reviewer |
| Build | Codex (replay from `.cast` recording) |
| Test | Gemini in Blaxel sandbox |
| Review | Opus 4.6 + human gate |
| Document | Redis (semantic write) |
| Deploy | GitHub PR (code) / email (simple) |

## Sponsor coverage

| Sponsor | Stage(s) | Role |
|---|---|---|
| **Wordware** | 1 (Plan) | Stub by default; real flow by H7 if built |
| **Codex** | 3 (Build) | Replay mode via parsed `.cast` recording |
| **Blaxel** | 4 (Test) | Choreographed kill-and-self-heal loop |
| **Redis Memory** | 2, 5, 6, 7 | Semantic recall + drift catch + lesson writes |
| **Redis Context Surfaces** | 2, 5 | Schema-typed verification, structural contradictions |

## Stack

Python · Rich · Pydantic v2 · Typer · httpx · pytest · Redis · Blaxel · Codex · Wordware · GitHub CLI

## Quickstart

```bash
# 1. Context data lives in a sibling repo — clone + install first
git clone git@github.com:benikigai/plushpalace-world.git ../plushpalace-world
pip install -e ../plushpalace-world

# 2. Install AgentMES
pip install -e .

# 3. Run the two-ticket demo against the in-memory stub
python -m agent_mes

# 4. Or run against real Redis Stack
(cd ../plushpalace-world && docker compose up -d && python -m plushpalace.seed)
AGENTMES_USE_REDIS=1 REDIS_URL=redis://localhost:6379 python -m agent_mes

# 5. Smoke test
make test
```

## Status

- **Spec:** Approved (Option C — stub-first, swap-later, two-lane kanban)
- **Tasks:** 23 across 6 hours of autonomous build (`/yolo`)
- **Demo display:** localhost terminal projected, asciinema recording as backup

## Docs

- Spec: [`docs/specs/agentmes.md`](docs/specs/agentmes.md)
- Context snapshot: [`docs/specs/agentmes-context.md`](docs/specs/agentmes-context.md)
- Research: [`docs/specs/agentmes-research.md`](docs/specs/agentmes-research.md)
- Task list: [`docs/specs/agentmes-yolo.md`](docs/specs/agentmes-yolo.md)

## Team

- **Ben** ([@benikigai](https://github.com/benikigai)) — orchestration, UI, Wordware, Codex
- **Vish** — Redis, Blaxel
