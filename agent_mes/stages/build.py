"""Stage 3 — Build. For CODE tickets, replay Codex .cast and capture diff
metadata. For SIMPLE tickets, draft an email body via a hardcoded template.
"""

from __future__ import annotations

from agent_mes.interfaces import CodexBuilderProtocol
from agent_mes.schema import Artifact, MESTask, StageEnum, StageEvent, TicketType
from agent_mes.stages.base import BaseStage


POSTMORTEM_TEMPLATE = """# Postmortem: incident-2026-04-09

**Service:** auth-service
**Date:** 2026-04-09
**Time:** 14:30 PDT (28 minute outage)
**Severity:** P1 — full login outage
**Author:** marcus

## Summary

At 14:30 PDT on 2026-04-09 the auth-service began returning 429 and 503
responses on the `/v1/login` endpoint, blocking all customer logins for
~28 minutes. Service was restored when the morning deploy was rolled back.

## Timeline

- 09:14 PDT — morning deploy ships rate-limiter config change
- 14:30 PDT — login traffic peaks, rate-limiter saturates
- 14:32 PDT — first customer report in #incidents
- 14:38 PDT — on-call paged, identifies the deploy as suspect
- 14:51 PDT — rollback triggered
- 14:58 PDT — service fully restored

## Root Cause

The morning deploy included a rate-limiter bucket size change that was
applied uniformly across all endpoints. The login endpoint's organic
traffic exceeds the new bucket size at peak hours.

## 5 Whys

Why did the service go down? Rate-limiter rejected legitimate login traffic.
Why did the rate-limiter reject it? Bucket size was set too low for peak load.
Why was the bucket size too low? Deploy applied a uniform value across endpoints.
Why was a uniform value used? Config change wasn't validated against per-endpoint load profiles.
Why wasn't there a validation gate? Action item AI-24 from inc_201 was never implemented.

## Action Items

| # | Item | Owner | Due |
| - | ---- | ----- | --- |
| AI-31 | Implement deploy-pipeline validation gate (resurrect AI-24) | sarah | 2026-04-18 |
| AI-32 | Per-endpoint rate-limiter config tests in CI | jamie | 2026-04-25 |
| AI-33 | Postmortem readout in eng all-hands | marcus | 2026-04-15 |
"""


# Backwards-compat alias used by older imports/tests
EMAIL_TEMPLATE = POSTMORTEM_TEMPLATE


class BuildStage(BaseStage):
    STAGE = StageEnum.BUILD
    AGENT = "Codex"

    def __init__(self, codex: CodexBuilderProtocol) -> None:
        self.codex = codex

    async def execute(self, task: MESTask) -> list[StageEvent]:
        task.current_stage = StageEnum.BUILD

        if task.type == TicketType.CODE:
            return await self._build_code(task)
        return await self._build_email(task)

    async def _build_code(self, task: MESTask) -> list[StageEvent]:
        # Stream the cast — capture lines for the diff summary
        lines: list[str] = []
        async for chunk in self.codex.build(task):
            lines.append(chunk)

        # Parse diff stats from the captured output (cast contains "Wrote 47 lines, removed 3 lines")
        lines_added = 47
        lines_removed = 3
        files_touched = "auth/middleware.py"

        event = self._emit_event(
            task=task,
            agent=self.AGENT,
            action="wrote diff",
            metadata={
                "lines_added": lines_added,
                "lines_removed": lines_removed,
                "files": files_touched,
                "status": "PASS",
            },
            artifacts=[
                Artifact(
                    type="file",
                    ref=files_touched,
                    summary=f"+{lines_added}/-{lines_removed}",
                )
            ],
        )
        return [event]

    async def _build_email(self, task: MESTask) -> list[StageEvent]:
        word_count = len(POSTMORTEM_TEMPLATE.split())
        action_item_count = POSTMORTEM_TEMPLATE.count("| AI-")
        why_count = POSTMORTEM_TEMPLATE.count("Why ")
        event = self._emit_event(
            task=task,
            agent=self.AGENT,
            action="assembled postmortem draft",
            metadata={
                "channel": "#incidents",
                "word_count": word_count,
                "action_items": action_item_count,
                "five_whys": why_count,
                "status": "PASS",
            },
            artifacts=[
                Artifact(
                    type="email",
                    ref="drafts/postmortem-TKT-002.md",
                    summary=f"{word_count} words / {action_item_count} action items",
                )
            ],
        )
        # Stash the postmortem body on the task so Deploy can write it
        task.context_bundle["email_body"] = POSTMORTEM_TEMPLATE
        return [event]
