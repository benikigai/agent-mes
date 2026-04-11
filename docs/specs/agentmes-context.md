# Context: AgentMES
**Last updated:** 2026-04-11
**Phase:** Spec approved
**Approved option:** Option C — Stub-first, swap-later, two-lane kanban
**Tasks:** 23 (Simple: 11, Moderate: 9, Complex: 4)
**Key risks:**
1. Stubs drifting from Vish's locked function signatures (mitigated: copied verbatim from master doc into interfaces.py)
2. Rich Live race conditions on parallel ticket updates (mitigated: single asyncio.Lock around layout mutations)
3. Demo terminal too small for 100×30 layout (mitigated: H8 layout test on demo display)

**Critic verdict:** APPROVE with concerns — all concerns addressed in spec risks section. No critical flaws.

**Research:** docs/specs/agentmes-research.md

## Data layer — separate package
- Context data lives in [`benikigai/plushpalace-world`](https://github.com/benikigai/plushpalace-world) — 10 Pydantic entity types (Person, Product, Vendor, Repository, Incident, Postmortem, CodeChange, Customer, Email, Lesson), 53 seed entities in YAML
- Two backends share the same `ContextStore` Protocol: `StubStore` (in-memory) and `RedisStore` (Redis Stack)
- Parity test asserts stub and Redis return identical results for the same queries
- Fictional company: **PlushPalace Co.** — DTC plushies, CEO Mark Chen, viral hero SKU "Atticus the Axolotl", Shenzhen factory partner
- Two "smoking gun" postmortems (pm-2026-02-14 rate limit, pm-2025-11-22 mocked flaky test) have `status=open` action items — these are what Stage 5 Review catches as structural drift
- `AGENTMES_USE_REDIS=1` flips AgentMES from stub to real Redis Stack

## Architecture summary
- 7 vertical stage columns (Plan, Design, Build, Test, Review, Document, Deploy) — cards flow left to right
- **Receipts embedded INSIDE the card** — each StageEvent appends a line; the card body IS the audit trail
- Cards grow as they progress; on the right side cards are tall (~14 lines for CODE, ~7 for SIMPLE) showing complete history
- Two demo tickets in parallel: TKT-001 (⚙ OAuth code fix) and TKT-002 (✉ status email) — both share the same column flow
- Multi-model agent assignments per stage (Opus 4.6, Codex, Gemini, Redis, Blaxel, GitHub)
- Real GitHub PR opened at Deploy stage for code tickets
- All sponsor integrations stubbed by default; Vish's real impls swap in via single import line change
- Demo display: localhost terminal projected (NOT Vercel), with asciinema recording as backup

## Sponsor coverage
- Wordware: Stage 1 (Plan) — stub by default, real by H7 if flow built
- Codex: Stage 3 (Build) — replay mode via parsed .cast file
- Blaxel: Stage 4 (Test) — choreographed kill-and-self-heal loop, demo gold
- Redis Memory: Stages 2, 5, 6, 7 — semantic recall + drift catch + lesson writes
- Redis Context Surfaces: Stages 2, 5 — schema-typed verification, structural contradictions
