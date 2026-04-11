# AgentMES — Wordware Deep Dive

**Sponsor role:** Stage 1 — Plan. Convert raw Slack message → first-pass MESTask schema JSON.
**Build budget:** 30 min in IDE + 15 min API client = 45 min total.
**Tier:** Free.
**Venue context:** Wordware = the company that built Sauna; we're literally hacking inside their HQ.
**Judge to optimize for:** Guillaume Roux-Romestaing (Head of Growth at Wordware, ex-11x.ai, a16z Scout). Also Vishal Dani for the HITL gate framing.

---

## What Wordware actually is (the technical truth)

Despite the "AI workspace" marketing, under the hood **Wordware is a Natural Language Compiler.**

It treats English as source code. You build "WordApps" using a web IDE that combines plain-text prompts with strict control flow logic — Loops, If/Else branching, exact JSON structuring, and third-party API tools.

- **The primitive:** the second you finish writing a flow, Wordware instantly deploys it as a highly reliable REST API or an MCP server.
- **Your role for it:** Wordware is the **Intent Translation Layer** that solves the fuzziness of human communication. Instead of writing brittle Python regex to parse Jira tickets, you build a Wordware API that natively digests a chaotic PM Slack message, enriches it, and deterministically outputs your strict AWP / MESTask JSON schema.
- **Wordware is "the Engineer"** in the OpenAI 7-stage slide framing — the layer that reasons about what humans actually meant.

This framing matters for Guillaume's judge bias: position Wordware as **the brain** of the operation, the layer that eliminates the **enterprise coordination tax**.

---

## What we need from Wordware

A single deployed WordApp flow that:
- Takes raw Slack text as input (string)
- Outputs structured JSON matching the MESTask schema's first-stage fields
- Returns via a public API endpoint we can call from `agent_mes/integrations/wordware.py`

First-stage MESTask fields the flow must extract:
- `intent` — what the requester actually wants (1-2 sentences)
- `requester` — Slack user handle / id
- `source` — channel + permalink
- `suggested_constraints` — blast_radius hints from the request text
- `acceptance_criteria` — initial pass at "done" definition

---

## Research TODO

- [ ] Sign up for free tier — what's the URL, what's the quota?
- [ ] WordApp IDE walkthrough — natural-language prompt → flow building basics
- [ ] How to define a typed JSON output schema in Wordware
- [ ] How to wire system prompt + few-shot examples for Slack→JSON parsing
- [ ] Deploy mechanism — single click → API endpoint URL
- [ ] Auth model on the deployed endpoint (API key in header? Bearer token?)
- [ ] Rate limits / cost / quota on free tier (need ≥30 calls during build + ≥10 in demo)
- [ ] Examples of similar flows in the Wordware gallery
- [ ] Streaming vs single-shot response — pick whichever is faster for our case
- [ ] Error handling — what does Wordware return on malformed input?

---

## Key links (fill in)

- Free tier signup: TBD
- Docs root: TBD
- API reference: TBD
- WordApp IDE entry: TBD
- Gallery / examples: TBD
- Discord / community for help: TBD

---

## Integration sketch

```python
# agent_mes/integrations/wordware.py
import httpx
from agent_mes.schemas import MESTask

WORDWARE_FLOW_URL = "https://api.wordware.ai/v1/flows/<flow_id>/run"

async def plan_from_slack(raw_text: str, requester: str, channel: str) -> MESTask:
    payload = {"inputs": {"slack_text": raw_text, "requester": requester, "channel": channel}}
    headers = {"Authorization": f"Bearer {WORDWARE_API_KEY}"}
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(WORDWARE_FLOW_URL, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    return MESTask.from_plan_stage(data)
```

---

## Demo narration line

> "Slack rant comes in. Wordware — running in production at a real public URL — extracts the intent, the requester, the source, and the first-pass acceptance criteria. The same primitives Sauna is built on. 30 minutes of flow-building, one click to deploy."

---

## Judge trigger script (Guillaume — 15s)

> *"Guillaume, having seen 11x deploy digital workers, you know the friction is bridging human ambiguity and machine execution. We use Wordware to completely eliminate the coordination tax — compiling messy PM Slack threads into our strict, deterministic execution protocol."*

**Vocabulary to use on stage when his eye is on you:** coordination tax, digital workers, ambiguity-to-execution, deterministic protocol, Wordware as the brain.

---

## Bonus: the Reviewer WordApp (Phase 4 of the alt 4-phase directive)

Optional second WordApp for Stage 5/Review: ingests the `.diff` from the Codex PR, checks for **architectural drift** against a company style guide, drafts a release note, updates Redis semantic memory, pings the human gate. If we have spare time after H6, this doubles Wordware's footprint and gives Guillaume a second moment to point at.

---

## Risks / gotchas

- Free tier quota — could exhaust during build if we're not careful
- Wordware API latency — if >5s, demo feels slow; need a "thinking" animation
- JSON output reliability — need to test with 5+ different Slack messages to make sure schema extraction is stable
- API endpoint stability — if Wordware redeploys mid-demo, we're cooked. Cache the last good response as fallback.
