# AgentMES — Redis Context Surfaces Deep Dive

**Sponsor role:** Schema-typed, MCP-native ground-truth retrieval. Powers two stages.
- Stage 2 (Design) — populate `context_bundle` with structured ground-truth entities via auto-generated MCP tools
- Stage 5 (Review) — adversary verification side; refutes stale memory claims via the same MCP tool surface

**Access:** ✅ **GRANTED 2026-04-11** (was: early access via Marie / Simba)
**Product name:** Redis Context Surfaces
**CLI:** `ctxctl` (PyPI: `pip install context-surfaces`)
**Build budget:** ~30 min for schema definition + 30 min for surface provisioning + 30 min for MCP wiring = 90 min total. Significantly faster than mock-mode fallback.
**Judge to optimize for:** Adam Chan (Weaviate, organizes Agentic RAG hackathons). MCP-native + schema-typed retrieval is exactly his vocabulary.

---

## What Context Surfaces actually is

A declarative layer that turns a Pydantic-style data model into MCP tools backed by Redis indexes. The flow:

1. Define `ContextModel` classes (Pydantic-like — fields with `index="text"` / `index="numeric"` / `sortable=True`)
2. `ctxctl surface create --models ./models.py --redis-addr ...` provisions Redis indexes + generates MCP tools
3. `ctxctl agent create --surface-id <ID> --name "Codex"` issues a per-agent API key
4. The agent calls `ctxctl tools list --agent-key <KEY>` to enumerate tools
5. The agent calls tools via standard MCP — e.g. `ctxctl tools call search_item_by_text --agent-key <KEY> --query "auth rate limiter"`

**Net result:** zero handwritten retrieval code. The MCP tools (`search_*`, `get_*_by_id`, `filter_*_by_*`) are generated from the field index annotations. Redis just published a no-code queryable knowledge graph as MCP.

---

## Why this changes the AgentMES build

| Before (mock fallback) | After (real Context Surfaces) |
|---|---|
| Write `verify_memory_claim()` ourselves | Codex calls `search_incident_by_text` via MCP — no code |
| Hand-roll JSON return shapes | Typed `ContextModel` returns, MCP-spec'd |
| "Early access — might not work in time" risk | Live, documented, CLI-installable in 1 minute |
| Mock-mode narration: *"showing the integration shape"* | Real demo: *"Codex is querying Redis Context Surfaces live via MCP"* |

This eliminates the biggest risk in the original spec.

---

## Quick start (verbatim from the dashboard)

```bash
# 1. Install
pip install context-surfaces

# 2. Authenticate
ctxctl auth login --username "you@example.com" --password "$REDIS_CTX_PASSWORD"

# 3. Define models (./models.py — example)
cat <<'PY' > models.py
from context_surfaces.context_model import ContextField, ContextModel

class Item(ContextModel):
    __redis_key_template__ = "item:{id}"
    id: int = ContextField(description="Item ID", is_key_component=True)
    title: str = ContextField(description="Title", index="text")
    price: float = ContextField(description="Price", index="numeric", sortable=True)
PY

# 4. Create the surface
ctxctl surface create --name "AgentMES Heliograph" \
    --models ./models.py \
    --redis-addr "redis.example.com:6379" \
    --redis-password "$REDIS_PASSWORD"

# 5. Create an agent key
ctxctl agent create --surface-id "<SURFACE_ID>" --name "Codex"

# 6. Inspect + invoke tools
ctxctl tools list --agent-key "<AGENT_KEY>"
ctxctl tools call search_item_by_text --agent-key "<AGENT_KEY>" --query "coffee"
```

---

## The Heliograph schema (AgentMES models)

`agent_mes/schemas/heliograph_models.py`:

```python
from context_surfaces.context_model import ContextField, ContextModel

class Service(ContextModel):
    __redis_key_template__ = "service:{id}"
    id: str = ContextField(description="Service ID", is_key_component=True)
    name: str = ContextField(description="Service name", index="text")
    owner_team: str = ContextField(description="Owning team", index="text")
    repo_url: str = ContextField(description="GitHub repo URL")

class Incident(ContextModel):
    __redis_key_template__ = "incident:{id}"
    id: str = ContextField(description="Incident ID", is_key_component=True)
    service_id: str = ContextField(description="Affected service ID", index="text")
    endpoint: str = ContextField(description="Affected endpoint path", index="text")
    summary: str = ContextField(description="Incident summary", index="text")
    opened_at: float = ContextField(description="Opened timestamp", index="numeric", sortable=True)
    resolved_at: float = ContextField(description="Resolved timestamp", index="numeric", sortable=True)
    fix_pr_url: str = ContextField(description="Fix PR URL")

class User(ContextModel):
    __redis_key_template__ = "user:{id}"
    id: str = ContextField(description="User ID", is_key_component=True)
    name: str = ContextField(description="Full name", index="text")
    slack_handle: str = ContextField(description="Slack handle", index="text")
    team: str = ContextField(description="Team", index="text")

class Ticket(ContextModel):
    __redis_key_template__ = "ticket:{id}"
    id: str = ContextField(description="Ticket ID", is_key_component=True)
    requester_id: str = ContextField(description="Requester user ID", index="text")
    service_id: str = ContextField(description="Service under discussion", index="text")
    priority: str = ContextField(description="Priority", index="text")
    status: str = ContextField(description="Status", index="text")
    body: str = ContextField(description="Ticket body", index="text")
```

After `ctxctl surface create`, we get auto-generated MCP tools like:

- `search_service_by_text`, `get_service_by_id`, `filter_service_by_owner_team`
- `search_incident_by_text`, `get_incident_by_id`, `filter_incident_by_service_id`, `filter_incident_by_endpoint`, `filter_incident_by_resolved_at_range`
- `search_user_by_text`, `get_user_by_id`, `filter_user_by_team`
- `search_ticket_by_text`, `get_ticket_by_id`, `filter_ticket_by_requester_id`, `filter_ticket_by_status`

**Codex calls these natively via MCP.** No client wrapper needed.

---

## Demo seed data (Stage 5 contradiction)

To make the memory drift catch land, seed:

```python
# scripts/seed_heliograph.py
INCIDENTS = [
    Incident(
        id="inc_113",
        service_id="svc_auth",
        endpoint="/v1/login",
        summary="auth rate limiter bumped 100→500rpm",
        opened_at=four_weeks_ago_ts,
        resolved_at=four_weeks_ago_ts + 86400,
        fix_pr_url="https://github.com/heliograph/auth/pull/447",
    ),
    # ... 11 other incidents for narrative depth
]

TICKETS = [
    Ticket(
        id="tkt_982",
        requester_id="usr_sarah",
        service_id="svc_auth",
        priority="P2",
        status="open",
        body="rate-limiting on /v2/oauth too strict — customers reporting 429s on token refresh",
    ),
    # ... 5 other tickets
]
```

Pre-populate Redis Agent Memory Server with the **adversary memory**:

```
"We already fixed the auth rate limiter on the login service last month — bumped from 100 to 500 rpm. Confidence: 0.9"
```

The Stage 5 logic:

1. Agent receives Ticket `tkt_982` (about `/v2/oauth`)
2. Calls `memory_prompt(query="auth rate limiter")` → retrieves the adversary memory at confidence 0.9
3. Calls MCP tool `search_incident_by_text(query="auth rate limiter")` → gets back `inc_113` with `endpoint="/v1/login"`
4. Compares: memory said the fix was on the login service generally, but `inc_113.endpoint == "/v1/login"` while `tkt_982` is about `/v2/oauth` — **structural mismatch**
5. Drops confidence 0.9 → 0.3
6. Marks task `BLOCK_FOR_HUMAN`, escalates
7. Card pulses yellow, narrate the contradiction on screen

**The contradiction is structural (field-typed), not heuristic.** That is the part Adam Chan rewards.

---

## Integration in the AgentMES stack

Where Context Surfaces lives in the Ben Stack:

```
PLAN ──→ BUILD ──→ VERIFY ──→ REVIEW ──→ DOC/DEPLOY
                              ↓
                    Context Surfaces MCP tools
                    (Codex calls them natively)
```

For Contrabass: add the Context Surfaces MCP server as one of Codex's available MCP servers in the WORKFLOW.md / AGENTS.md plan file. Codex will discover the tools automatically and use them when the prompt directs it to verify memory claims.

For the `/forge` skill: Step 1 (Generate Build Prompt) injects a section like:

```markdown
## Memory Verification (Stage 5)

When you encounter a memory claim from `memory_prompt()`, you MUST verify it before
acting. Use the available MCP tools from the AgentMES Heliograph Context Surface:

- `search_incident_by_text` — find incidents matching natural-language query
- `filter_incident_by_endpoint` — find incidents on a specific endpoint
- `get_service_by_id`, `get_user_by_id`, `get_ticket_by_id`

If a memory claim and a Context Surface fact contradict, drop the memory's confidence
and emit `STATUS=BLOCK_FOR_HUMAN` with the contradiction summary.
```

Codex reads the plan file, sees the MCP tools, calls them. Done.

---

## Open questions

- [ ] Where does our Context Surfaces dashboard live? (URL for the admin UI)
- [ ] Auth credentials — did Redis give us a username/password, or just an agent key?
- [ ] Redis backend — do we need to provision our own Redis instance, or did they spin one up for us?
- [ ] Pricing / quota for hackathon participants
- [ ] Are the auto-generated tool names exactly `search_<model>_by_text`, or different patterns?
- [ ] Does Context Surfaces serve the MCP transport over HTTP, stdio, or both?
- [ ] How does an agent key relate to MCP server config (do we point Codex at `https://...?key=<AGENT_KEY>`)?

---

## Risks / gotchas

- The auto-generated tool naming needs to be confirmed before we hardcode it in `/forge` prompts
- Need to verify the Redis instance Context Surfaces uses is reachable from the Mac Mini (firewall, Tailscale, public TLS)
- MCP transport details matter — Codex CLI's MCP support may need a specific config format
- Don't seed the Heliograph data until the surface schema is confirmed working — otherwise the seed may be incompatible with the eventual schema

---

## Judge trigger script (Adam Chan — 15s, updated)

> *"Adam, we don't dump chat logs into a prompt. Redis Context Surfaces auto-generates MCP tools from our schema — Codex queries `search_incident_by_text` directly, gets a typed Incident back, and our Stage 5 memory drift catch compares the retrieved incident's endpoint field against the stale Agent Memory Server claim. The contradiction is structural, not heuristic."*

**Vocabulary on stage:** MCP-native, schema-typed retrieval, structural contradiction, Vector Sets (for the Memory Server side), negative constraint, hybrid search.
