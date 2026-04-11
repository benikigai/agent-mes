# AgentMES — OpenAI Codex Deep Dive

**Sponsor role:** Stage 3 — Build. Pull the hydrated MESTask and execute it inside a parallel cloud worktree. Writes code, runs self-review loop, opens a PR.
**Build budget:** 30 min validation call + 15 min asciinema record + 10 min replay player = 55 min (H7).
**Demo mode (original directive):** Replay only. **No live Codex during the demo.** (Hard rule #2.)
**Demo mode (alt 4-phase directive):** Live Codex inside the Blaxel self-healing loop, hardcoded failure → 3-iteration self-heal. See "Strategic Question" below.

---

## ⚠️ Adam Chan correction

The original outline references "Adam Chan's Codex slide" — but per the new judge intel, **Adam Chan is a judge from Weaviate, not the Codex sponsor face.** The 7-stage Plan→Build→Review→Deploy slide may have come from a Codex/OpenAI source, but DO NOT credit it to Adam Chan on stage. Verify the actual slide author with Ben before referencing in the pitch.

---

## What we need

1. **One real Codex CLI call** during build (H7) to validate the integration path works end-to-end.
2. **Asciinema recording** of that one call, committed to `recordings/codex_build_run.cast`.
3. **Replay player** that plays the recording in the Build column when the demo card lands there.
4. **`prompts/codex_agents.md` plan file** that tells Codex how to operate inside the MESTask constraint envelope.

---

## Research TODO

- [ ] Codex CLI install command (`npm i -g @openai/codex` or similar)
- [ ] Auth model — OPENAI_API_KEY env var? separate token?
- [ ] AGENTS.md / `prompts/codex_agents.md` plan file format
- [ ] How to constrain Codex by `blast_radius` (does it respect the file allowlist?)
- [ ] How to enforce `max_cost_usd` (token budget? wall-clock timeout?)
- [ ] Self-review loop semantics — does Codex run pytest internally or do we?
- [ ] PR opening — does Codex open the PR or just push the branch?
- [ ] Cloud worktree — what does "parallel cloud worktree" mean operationally?
- [ ] asciinema install + record command (`asciinema rec recordings/codex_build_run.cast`)
- [ ] Replay player options:
  - asciinema-player (web)
  - `agg` (asciinema → gif)
  - terminal-native replay we control programmatically
- [ ] How to scrub timestamps in the cast file so the demo replay finishes in ~15 seconds even if the real call took 2 minutes

---

## Key links (fill in)

- Codex CLI install docs: TBD
- AGENTS.md spec / examples: TBD
- Codex API reference: TBD
- asciinema docs: https://asciinema.org/docs/
- Adam Chan's Codex slide (the 7-stage framework that AgentMES implements): get from venue

---

## The plan file (`prompts/codex_agents.md`) sketch

```markdown
# AgentMES Build Stage — Codex Operating Constraints

You are executing inside Stage 3 of the AgentMES pipeline. The MESTask schema bound to this run includes:

- `intent` — what the requester wants
- `acceptance_criteria` — machine_checks you must satisfy
- `blast_radius`:
  - `allowed_paths` — only files inside this list may be modified
  - `network_egress` — `false` unless allowlist matches
  - `max_cost_usd` — hard ceiling, fail fast if approached
- `context_bundle` — ground-truth entities from Redis Context Retriever
- `memory_provenance` — past lessons from Redis Agent Memory Server (treat as advisory, verify before acting)

Hard rules:
1. Never modify files outside `blast_radius.allowed_paths`.
2. Never make outbound network calls unless explicitly allowlisted.
3. If you would exceed `max_cost_usd`, stop and emit `STATUS=BLOCK_FOR_HUMAN`.
4. If any acceptance_criterion fails, fix it before opening a PR.
5. Run the full pytest suite locally before declaring done.

Output: a PR with all changes, the diff summary, and a `decision_log.md` capturing what was attempted and why.
```

---

## The replay flow

```python
# agent_mes/stages/build.py (sketch)

def execute_build_stage(task: MESTask, ui: TerminalUI) -> BuildResult:
    if DEMO_MODE:
        # Replay the pre-recorded Codex run inside the Build column
        ui.set_column_state("build", "running")
        replay_asciinema("recordings/codex_build_run.cast", target=ui.build_pane, speed=8.0)
        ui.set_column_state("build", "complete")
        return BuildResult.from_replay()
    else:
        # The real call — used in H7 to GENERATE the recording, never in demo
        return run_codex_cli_real(task)
```

---

## Risks / gotchas

- **Codex latency** — a real call can take minutes. Do not let this eat your sprint. The H7 budget says "30 minutes for the validation call" — if at 30 min it's still running, kill it and retry with a smaller scope.
- Recording timing — asciinema captures real-time. Use playback `--speed=8` or scrub timestamps so the replay fits inside the demo's 15-second build beat.
- AGENTS.md format may diverge between Codex CLI versions — pin to one version for the build, document it in the plan file.
- Replay must look LIVE — no "REPLAY MODE" banner on screen. Narrate honestly: *"This is a recording from earlier today. The integration is real; we're not running it live during the pitch because Codex latency would eat our time slot."*

---

## Hard rule reminder (original directive)

> "No live Codex during the demo. Replay mode only. The asciinema fallback IS the demo."

---

## Alt framing: AST-Aware Constraint Execution + Self-Healing Loop

The alternate 9-hour directive uses Codex more aggressively — live during the demo, inside the Blaxel loop:

### AST-aware constraint execution

Once the Plan stage's MESTask JSON is approved, Codex receives it. Before writing any feature code, **Codex parses the Abstract Syntax Tree (AST) of the existing repo to map every function that depends on the code it's about to mutate.** It then executes generation strictly within the physical bounds of the AWP / MESTask schema — `allowed_paths`, `max_cost_usd`, `network_egress=false`, etc.

This is the framing that lands for **Dr. Max** (he sees real concurrency control, not vibes) and **Sri** (kinematic constraints on an actuator).

### Self-healing test loop with Blaxel

After Codex writes the feature + tests, the loop runs:

1. Codex pushes code to Blaxel microVM (hot-boot 25ms, zero data retention)
2. Blaxel runs `pytest`
3. **If failing:** Blaxel pipes `stderr` back to Codex
4. Codex reads stack trace, patches its own code, triggers Blaxel again
5. Loop iterates 3 times until passing
6. **Demo gold:** terminal visibly cycles through the iterations

For H9 in the alt directive: hardcode a failure. Intentionally feed Codex a prompt that produces a failing test so the demo visibly shows Blaxel catching it and Codex self-healing. The hardcoded failure is the sacred moment in the alt framing (vs. the Blaxel egress kill in the original).

### Strategic question

The two directives differ on whether Codex runs **live** or **replayed** during the demo:

| Directive | Codex demo mode | Risk | Demo gold |
|---|---|---|---|
| **Original (7-stage)** | Replay (asciinema) | Low — pre-recorded | Blaxel egress kill |
| **Alt (4-phase)** | Live, inside Blaxel loop | High — Codex latency / network | Self-healing loop iterations |

Original is safer. Alt is more impressive if it works. Ben should pick before H7 starts.

---

## Judge trigger angle

The Codex stage doesn't have a single "Codex judge" — Adam Chan (Weaviate) is the closest analog but his bias is vector/RAG, not codegen. Use the Codex stage to set up the **judge-trigger words** for adjacent moments:

- "AST-aware constraint execution" → Dr. Max's ears perk
- "kinematic envelope" → Sri's ears perk
- "self-healing loop" → both perk
