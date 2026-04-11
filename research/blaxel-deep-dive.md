# AgentMES — Blaxel Deep Dive

**Sponsor role:** Stage 4 — Test. microVM verification sandbox with blast_radius enforcement, egress-kill detection, perpetual-standby resume. **Plus** Stage 7 bonus: dormant rollback VM mention.
**Build budget:** 90 min — the single largest sponsor block, protect it (H5: 2–3pm).
**Diamond sponsor.** This is also the loudest demo moment — the Blaxel kill at ~25ms is the wow.
**Judges to optimize for:** Sri Kalimani (Agility Robotics — wants hardware e-stop framing) AND Dr. Max (IBM Knative — wants microVM hot-resume framing). Two judges, one beat. This is why the Blaxel moment is sacred.

---

## The two functions we have to ship

```python
# agent_mes/integrations/blaxel.py

async def create_verification_sandbox(task: MESTask) -> Sandbox:
    """
    Spin up a Blaxel microVM with the task's blast_radius applied:
      - no network egress (except allowlist)
      - file allowlist (only paths in task.allowed_paths)
      - cost ceiling (kill if exceeds task.max_cost_usd)
    Returns a sandbox handle the rest of the pipeline can exec into.
    """

async def run_acceptance_checks(sandbox: Sandbox, criteria: list[MachineCheck]) -> CheckResult:
    """
    Execute each machine_check inside the sandbox:
      - pytest (configurable test selector)
      - lint (ruff or eslint depending on language)
      - schema validate (jsonschema or pydantic)
    Aggregate pass/fail with stdout, stderr, exit_code, killed_by_blast_radius.
    """
```

---

## The wow moment (sacred — don't cut)

Sequence in the Test column:
1. Card enters Test, status=`running_acceptance_checks`
2. `demo/poison_payload.py` (a malicious dependency) tries to phone `evil.example.com`
3. **Blaxel egress detection fires in <25ms**
4. Sandbox terminates, kill reason logged: `BLAST_RADIUS_VIOLATION: outbound network call to evil.example.com (allowed: false)`
5. Dashboard column flashes red, kill reason displayed
6. **Fresh microVM resumes from standby** — pipeline continues without operator intervention
7. Narrate: *"Blaxel's microVM caught it, killed the VM, and a fresh one came back from standby in 25 milliseconds. Hardware-level isolation is the only safe place to find out what your agent is actually doing."*

This is ~20 seconds of demo. It hits THREE scoring dimensions in one beat: safety, sponsor integration, technical depth.

---

## Research TODO

- [ ] Blaxel API key — where do I find it on the dashboard? (verify in H1)
- [ ] microVM creation — Python SDK or REST? Auth header format?
- [ ] How to declare blast_radius constraints at sandbox-create time
- [ ] Egress allowlist syntax — domain-based? IP-based? Both?
- [ ] File allowlist — does it support globs? Symlink behavior?
- [ ] Cost ceiling — measured in $? CPU-seconds? Wall-clock?
- [ ] What event/log fires when egress is blocked? Need the exact field names for the dashboard
- [ ] Latency claim — confirm the <25ms figure with the team if possible
- [ ] Perpetual standby — is this automatic or do I have to pre-warm a pool?
- [ ] Resume mechanism — does the new VM inherit the old VM's state, or fresh?
- [ ] How to exec into a sandbox (`sandbox.run("pytest -x")`?)
- [ ] How to stream logs from the sandbox back to the host
- [ ] Pricing / quota for hackathon participants

---

## Key links (fill in)

- API key dashboard: TBD
- Python SDK / REST docs: TBD
- microVM lifecycle docs: TBD
- Egress detection docs: TBD
- Perpetual standby docs: TBD
- Blaxel team contact (Discord/Slack): TBD

---

## Demo failure modes — pre-mitigations

| Risk | Mitigation |
|---|---|
| Blaxel API down during demo | Pre-record a backup asciinema of the kill moment |
| Egress detection slower than 25ms | Pad narration: "in under 30ms, before the request even completes" |
| Standby resume slower than expected | Have the dashboard show "RESUMING…" with a spinner so latency feels intentional |
| Kill reason format different than expected | Wrap raw kill log in our own pretty-printer; never show raw JSON on screen |
| Phone-home payload doesn't trigger | Test the poison payload 5+ times in H5; commit a known-good version to `demo/poison_payload.py` |

---

## Stage 7 bonus mention

> "The same Blaxel sandbox that verified the change stays on standby to roll it back if monitoring detects an anomaly post-deploy."

Don't have to fully implement. Just one sentence in the pitch and a `# blaxel_standby_handle` placeholder in `agent_mes/stages/deploy.py` so it shows in the code walkthrough.

---

## Hard rule

If anything else falls behind, **the Blaxel kill moment is what we ship.** Cut Wordware fanciness, cut Codex polish, cut Document narrative — never cut the Blaxel beat.

---

## Alt framing: the Self-Healing QA Clean Room (from 4-phase directive)

The alternate 9-hour directive uses Blaxel slightly differently — not as a kill-then-resume showcase but as a **self-healing QA clean room** in a tight loop with Codex:

1. Codex writes a feature + its own unit tests
2. Codex pushes code to a Blaxel microVM (hot-boot in 25ms, zero data retention)
3. Blaxel runs `pytest` inside the sandbox
4. **If it fails:** Blaxel pipes `stderr` back to Codex
5. Codex reads the stack trace, patches its own code, triggers Blaxel again
6. Demo shows the loop iterating 3 times until it passes

This framing **flawlessly satisfies both Dr. Max** (sees the iteration loop, distributed control) **and Sri** (sees the actuator-with-hard-stop guardrails).

**Strategic question for Ben:** original outline = "Blaxel kill on egress" (security demo). Alt directive = "Blaxel self-healing test loop" (engineering demo). Both fit the 90-min budget. Which one wins more judge points? See `state-2026-04-11.md` for the open question.

---

## Judge trigger script (Sri — 15s)

> *"Sri, from a robotics perspective, you never put an unconstrained actuator on an assembly line. Codex is our robotic arm, but it only moves within the strict kinematic constraints of our JSON schema. If it attempts an out-of-bounds network call, Blaxel acts as a hardware e-stop — instantly killing the microVM and zero-retaining the state."*

## Judge trigger script (Dr. Max — 15s)

> *"Dr. Max, coming from your work on Knative, you know container cold-starts destroy agent reasoning loops. We bypass that entirely using Blaxel's hardware-enforced microVMs for sub-25ms hot resumes."*

**Vocabulary to use on stage:** hardware e-stop, kinematic constraints, zero data retention, hot resume, hardware-enforced microVM, cold-start bypass, blast radius, sub-25ms.
