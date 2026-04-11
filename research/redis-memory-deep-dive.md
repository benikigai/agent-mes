# AgentMES — Redis Agent Memory Server Deep Dive

**Sponsor role:** Long-term semantic memory. Powers four stages.
- Stage 2 (Design) — `memory_prompt(query=intent)` for semantic recall
- Stage 3 (Build) — working memory writes during execution
- Stage 5 (Review) — adversary side, the memory whose claims get cross-checked
- Stage 6 (Document) — `create_long_term_memory()` to persist the decision log
- Stage 7 (Deploy) — log monitoring breadcrumb into long-term memory

**Tech:** `redislabs/agent-memory-server:0.13.1-standalone` (Docker)
**Build budget:** 45 min total for both Redis integrations (Memory + Context Retriever)
**Judge to optimize for:** Adam Chan (Weaviate DevRel, organizes Agentic RAG hackathons). Will punish naive prompt-stuffing. Wants vector primitives + advanced semantic memory framing.

---

## ⚠️ Tech stack tension to resolve with Ben

The original outline says: use **Redis Agent Memory Server** + **Redis Context Retriever** (two separate products).

The new judge-intel research says: use **Redis 8 Vector Sets** as an active semantic cache, with negative-constraint injection for hallucinated execution paths.

These could be reconciled (Vector Sets is an underlying primitive that Agent Memory Server is built on) OR they could be alternative implementations. **Ben needs to pick:**

| Option | Pros | Cons |
|---|---|---|
| Original — Agent Memory Server + Context Retriever | Two products = double sponsor coverage; Memory API is high-level | Context Retriever is early-access (Simba blocker); both are heavier integrations |
| Alt — Redis 8 Vector Sets directly | Adam Chan (Weaviate judge) recognizes Vector Sets immediately; no early-access blocker | Lower-level API, more code to write; loses the "two Redis products" sponsor narrative |
| **Hybrid** ⭐ | Use Agent Memory Server (which is built on Vector Sets under the hood) AND mention Vector Sets explicitly when Adam Chan looks up | Best of both — sponsor coverage + judge vocabulary | Slightly verbose narration |

**Recommended:** hybrid. Build with Agent Memory Server (high-level API saves time), narrate with Vector Sets vocabulary when Adam Chan is in earshot.

---

## What we need

1. Standalone Docker container running locally
2. 10 pre-seeded fake past task outcomes (so semantic recall has something to retrieve from H4 onward)
3. Two Python integration calls:
   - `memory_prompt(query=intent)` → top-K relevant past memories
   - `create_long_term_memory(text, topics, user_id)` → write a new memory

---

## Research TODO

- [ ] Confirm exact Docker run command for `redislabs/agent-memory-server:0.13.1-standalone`
- [ ] Required env vars (Redis backend? embedded? OpenAI key for embeddings?)
- [ ] Default port + how to override
- [ ] Python client — official package or HTTP API?
- [ ] `memory_prompt` API — params, return shape, top-K control
- [ ] `create_long_term_memory` API — required fields, optional metadata
- [ ] Memory tagging — `topics` taxonomy, `user_id` semantics
- [ ] Confidence scoring — does the server return confidence with each retrieval?
- [ ] How to bulk-seed memories at startup (we need 10 fake ones in H3)
- [ ] Working memory vs long-term memory — when does working memory promote to LT?
- [ ] How to query/inspect raw memories for the dashboard view
- [ ] Reset / clear API — if demo run #1 dirties state, how to reset for run #2?

---

## Key links (fill in)

- GitHub repo: TBD (likely `redis/agent-memory-server`?)
- Docker Hub: TBD
- API docs: TBD
- Python client: TBD
- Examples: TBD

---

## Pre-seeded memory pool (H3 task)

Need 10 fake past task outcomes that vary in topic, recency, and verdict. Mix should include:
- 3 successful past tasks (high confidence)
- 3 failed past tasks (medium confidence, lessons learned)
- 2 ambiguous past tasks (low confidence)
- 2 false-positive past tasks (the "we already fixed this" kind that the Stage 5 demo will refute)

Each memory should have:
- `text` — 1-3 sentences describing the task + outcome
- `topics` — `[task_completion, <service_name>]`
- `user_id` — fake requester id
- `created_at` — backdated 3 days to 2 months

The Stage 5 demo specifically requires a memory like:
> "Fixed the auth rate limiter on the login service last month — bumped from 100rpm to 500rpm. Confidence: 0.9."

…which the Context Retriever will refute (it was actually `/v1/login`, the new task is `/v2/oauth`).

---

## Integration sketch

```python
# agent_mes/integrations/redis_memory.py
from agent_memory_server import AgentMemoryClient

client = AgentMemoryClient(host="localhost", port=8000)

async def hydrate_memories(task: MESTask) -> list[Memory]:
    memories = await client.memory_prompt(query=task.intent, top_k=3)
    return [Memory.from_server(m) for m in memories]

async def write_decision_log(task: MESTask, log_text: str) -> None:
    await client.create_long_term_memory(
        text=log_text,
        topics=["task_completion", task.target_service],
        user_id=task.requester,
    )
```

---

## Risks / gotchas

- Docker image size — pull early in H1, not when Wi-Fi is sketchy at H4
- Embedding model — does the server bring its own, or do we need an OpenAI key?
- Memory cold start — top-K retrieval against an empty pool returns nothing → demo flop. Pre-seed BEFORE H4 starts.
- Persistence — does `--standalone` persist to disk or RAM only? If RAM, every container restart wipes the seed. Mount a volume if needed.

---

## Judge trigger script (Adam Chan — 15s)

> *"Adam, we aren't just dumping chat logs into a prompt. We use Redis 8's Vector Sets as an active semantic cache. When Codex fails, we inject that failure state into Redis as a negative constraint. Next time, the hybrid search mathematically prevents Codex from traversing that same hallucinated execution path."*

**Vocabulary to use on stage:** Vector Sets, semantic cache, negative constraint, hybrid search, hallucinated execution path, embedding-aware retrieval.

---

## Bonus angle: Distributed state locks (for Dr. Max)

Redis 8 also gives us **distributed state locks** so parallel Codex swarm workers don't trigger race conditions. Even if we only run one Codex worker in the demo, mention this for Dr. Max:

> *"Because Codex operates asynchronously, we use Redis 8 to enforce strict distributed state locks so parallel swarm workers never trigger race conditions."*

Implementation: simple `SET key value NX EX 30` with the MESTask's task_id as the key. One line of code, one extra sentence in the pitch, two judges happier.
