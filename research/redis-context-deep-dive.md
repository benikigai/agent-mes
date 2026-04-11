# AgentMES — Redis Context Retriever Deep Dive

**Sponsor role:** Ground-truth structured retrieval. Powers two stages.
- Stage 2 (Design) — populate `context_bundle` with structured ground-truth entities
- Stage 5 (Review) — adversary verification side; refutes stale memory claims

**Access:** Early access via Marie / Simba — **DM Simba in H1**, this is on the critical path.
**Build budget:** Shared with Memory Server in the 45-min H4 block. If Context Retriever access doesn't land in time, fall back to mock mode and continue.
**Judge to optimize for:** Adam Chan (Weaviate) — same as Memory Server. The Stage 5 contradiction beat is what lands for him.

---

## See also

- `redis-memory-deep-dive.md` — has the **tech stack tension** between "two Redis products" (this doc + Memory Server) vs "Redis 8 Vector Sets directly". Read that resolution before sinking time into Context Retriever access if Vector Sets is the chosen path.

---

## What we need

The Context Retriever queries a fake company schema and returns structured entities. The fake schema has at least:
- `users` (id, name, slack_handle, team)
- `services` (id, name, owner_team, repo_url, runbook_url)
- `incidents` (id, service_id, opened_at, resolved_at, summary, fix_pr_url)
- `tickets` (id, requester, service_id, priority, status)

For Stage 2, given a task intent + Slack source, the retriever returns:
- Who is the requester (full user record)
- Which service they referenced (from message text or channel)
- Who owns the service (team + on-call)
- Recent incidents on that service

For Stage 5, given a memory claim like *"we fixed the auth rate limiter on `<service>` last month"*, the retriever verifies against current ground truth — and the demo turns on the **mismatch** between what the memory says and what the schema actually contains.

---

## Research TODO

- [ ] DM Simba for early access (CRITICAL — H1)
- [ ] Repo / package name once access is granted
- [ ] Auth model (API key? Redis connection string?)
- [ ] Schema definition format — how do we declare the fake company schema?
- [ ] Query API — natural language? SQL-like? Structured filters?
- [ ] Return shape — JSON entities? Embedded relations?
- [ ] How does it interact with Agent Memory Server (separate process? shared Redis?)
- [ ] Seed mode — how do we bulk-load the 4 fake tables?
- [ ] Mock mode — if access doesn't land, what's the cleanest fallback?
- [ ] Latency expectations — needs to feel snappy in demo (<500ms per query)

---

## Key links (fill in)

- Marie contact: TBD
- Simba contact: TBD (Slack handle? Discord?)
- Early-access docs / repo: TBD (gated)
- Schema declaration examples: TBD

---

## The fake company schema (we own this)

We define the fake company. Stick to one domain so it's narratable in 2 sentences.

**Proposed:** A fake B2B SaaS company called "Heliograph" with:
- 4 services: `auth-service`, `billing-service`, `notify-service`, `search-service`
- 8 users across 3 teams
- 12 historical incidents (some on `auth-service` so the Stage 5 contradiction has bite)
- 6 open tickets

The Stage 5 demo specifically needs:
- An old incident: "auth rate limiter bumped, fix on `/v1/login` endpoint, resolved 4 weeks ago"
- A new ticket: "rate-limiting on `/v2/oauth` is too strict, customers reporting 429s"

When the agent retrieves the memory ("we already fixed this last month") and the Context Retriever returns the actual incident record (different endpoint), the contradiction is clear and visible.

---

## Integration sketch

```python
# agent_mes/integrations/context_retriever.py
from redis_context_retriever import ContextClient  # or whatever the actual import is

client = ContextClient(connection_string=os.environ["REDIS_CONTEXT_URL"])

async def hydrate_context(task: MESTask) -> ContextBundle:
    # Stage 2 — pull ground-truth entities into the task
    return await client.query(
        intent=task.intent,
        source=task.source,
        return_types=["user", "service", "incident", "ticket"],
    )

async def verify_memory_claim(memory: Memory, service: str) -> VerificationResult:
    # Stage 5 — adversarial check against stored memory
    return await client.verify(
        claim=memory.text,
        scope={"service": service},
    )
```

---

## Risks / gotchas

- **Access risk** — if Simba doesn't reply in time, the entire Stage 2 + 5 narrative depends on mock mode. Have the mock ready by end of H4.
- The fake schema must be small enough to narrate in one breath ("Heliograph, 4 services, 8 users, 12 incidents") but rich enough that the contradiction in Stage 5 lands.
- Redis Context Retriever is **early-access** product — expect rough edges, undocumented quirks, and possibly missing API surface. Budget extra time and don't fight the tool.

---

## Mock mode fallback (write before H4 ends)

```python
# agent_mes/integrations/context_retriever_mock.py
def hydrate_context_mock(task):
    return ContextBundle(
        requester={"id": "u_07", "name": "Sarah Kim", "team": "platform"},
        service={"id": "svc_auth", "name": "auth-service", "owner_team": "platform"},
        recent_incidents=[
            {"id": "inc_113", "summary": "auth rate limiter bumped on /v1/login", "resolved_at": "2026-03-12"},
        ],
    )
```

Truthful narration if we end up in mock mode: *"Context Retriever is early-access — Marie's team is shipping it next week. We're showing the integration shape with seeded data."*
