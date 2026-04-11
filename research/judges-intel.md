# AgentMES — Judges Intel & Demo Triggers

**Panel composition:** Bifurcated. Half are hardcore distributed-systems / hardware / robotics engineers who will reject "wrapper" apps. Half are commercial operators who want GTM narrative + enterprise workflow. Different demo triggers per camp.

---

## 1. Dr. Michael Maximilien ("Dr. Max") — Distributed Systems Heavyweight

**Background:**
- Distinguished Engineer at IBM, CTO of Cloud Advocacy
- PhD in CS
- Foundational pioneer of **Serverless** and **Knative**
- Lives in Kubernetes and Cloud Foundry

**What he's grading:** Knows exactly how brittle async agents are. Looking for concurrency, state locking, container execution models.

**The demo trigger script (15s):**
> *"Dr. Max, coming from your work on Knative, you know container cold-starts destroy agent reasoning loops. We bypass that entirely using Blaxel's hardware-enforced microVMs for sub-25ms hot resumes. And because Codex operates asynchronously, we use Redis 8 to enforce strict distributed state locks so parallel swarm workers never trigger race conditions."*

**Words to say on stage:** Knative, microVM, hot resume, distributed state locks, race conditions, async swarm workers.

---

## 2. Adam Chan — Vector & Context Purist

**Background:**
- Developer Relations at **Weaviate** (enterprise vector database)
- Founder of Developer Events
- Actively organizes "Agentic RAG" hackathons in SF

**⚠️ CORRECTION:** Adam Chan is **NOT** the Codex sponsor face. The original project outline said "Adam Chan's Codex slide" — Adam Chan is actually a **judge from Weaviate**. The 7-stage Plan→Build→Review→Deploy slide may have come from a Codex source, but Adam Chan is here as a judge, not as Codex DevRel. **Verify with Ben before referencing him in the pitch.**

**What he's grading:** Will instantly punish naive prompt-stuffing. Wants advanced semantic memory + context retrieval.

**The demo trigger script (15s):**
> *"Adam, we aren't just dumping chat logs into a prompt. We use Redis 8's Vector Sets as an active semantic cache. When Codex fails, we inject that failure state into Redis as a negative constraint. Next time, the hybrid search mathematically prevents Codex from traversing that same hallucinated execution path."*

**Words to say on stage:** Vector Sets, semantic cache, negative constraint, hybrid search, hallucinated execution path.

---

## 3. Sri Kalimani — Hardware & Control Systems Mind

**Background:**
- Software Engineer at **Agility Robotics** (the bipedal warehouse robot Digit)
- Robotics Engineering at Worcester Polytechnic Institute (WPI)
- Focus: real-time embedded systems

**What she's grading:** Blast radius mitigation, sandbox safety. To a roboticist, an LLM is a highly unpredictable actuator that requires physical guardrails.

**The demo trigger script (15s):**
> *"Sri, from a robotics perspective, you never put an unconstrained actuator on an assembly line. Codex is our robotic arm, but it only moves within the strict kinematic constraints of our JSON schema. If it attempts an out-of-bounds network call, Blaxel acts as a hardware e-stop — instantly killing the microVM and zero-retaining the state."*

**Words to say on stage:** Actuator, kinematic constraints, hardware e-stop, zero data retention, blast radius, assembly line.

---

## 4. Guillaume Roux-Romestaing — Commercial Pragmatist

**Background:**
- Head of Growth at **Wordware**
- a16z Scout
- Previously led commercial strategy at **11x.ai** (autonomous digital sales workers, raised $50M from a16z)

**What he's grading:** Go-to-market. Does this eliminate the enterprise "Coordination Tax"? Does it make Wordware look like the brain?

**The demo trigger script (15s):**
> *"Guillaume, having seen 11x deploy digital workers, you know the friction is bridging human ambiguity and machine execution. We use Wordware to completely eliminate the coordination tax — compiling messy PM Slack threads into our strict, deterministic execution protocol."*

**Words to say on stage:** Coordination tax, digital workers, ambiguity-to-execution, deterministic protocol, Wordware as the brain.

---

## 5. Vishal Dani — Enterprise Platform Exec

**Background:**
- SVP of Cloud Platforms at **HurixDigital**
- Previously Head of Product & Tech at **Hirezy.ai** (AI platform for automated software engineering assessments)

**What he's grading:** Enterprise readiness, compliance, Human-In-The-Loop (HITL) verification gates.

**The demo trigger script (15s):**
> *"Vishal, enterprises won't merge code from a rogue agent without an assessment. Our pipeline natively forces a HITL gate. Codex executes the labor in a Blaxel simulator, but Wordware stages the verified test results and PR diff in a dashboard for final human authorization."*

**Words to say on stage:** HITL gate, enterprise compliance, assessment, simulator, verified test results, human authorization.

---

## Cross-cutting strategy

| Camp | Judges | What lands |
|---|---|---|
| **Engineers** | Dr. Max, Adam Chan, Sri | Hardware isolation, distributed state, vector primitives, kinematic constraints, race-condition control |
| **Commercial** | Guillaume, Vishal | Coordination tax, HITL, enterprise readiness, GTM narrative, "the brain" framing |

The pitch must hit **both camps in 3 minutes** without sounding like two pitches glued together. Solution: lead with the MES analogy (a factory metaphor that lands for both — engineers think about real assembly lines, operators think about throughput), then split the live demo so each beat explicitly hits one camp's trigger:

- Plan stage (Wordware) → Guillaume hears "coordination tax eliminated"
- Test stage (Blaxel kill) → Sri hears "hardware e-stop", Dr. Max hears "microVM resume"
- Review stage (memory drift catch) → Adam hears "semantic cache + negative constraint", Vishal hears "HITL gate"

If you remember nothing else: **say each judge's loaded trigger word at least once during the demo.** They will remember the moment you spoke their language.

---

## Pre-pitch preparation

- [ ] Print this doc and tape it inside the laptop lid
- [ ] Memorize all 5 trigger scripts (60 sec each rep × 5 = 5 min total)
- [ ] Practice eye contact rotation: glance at each judge once during their trigger beat
- [ ] If a judge asks a follow-up, redirect to the trigger script's vocabulary — don't improvise away from their bias
- [ ] **Verify the Adam Chan / Codex slide attribution with Ben before referencing it on stage** — could be an embarrassment if wrong
