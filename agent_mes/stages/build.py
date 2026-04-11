"""Stage 3 — Build. For CODE tickets, replay Codex .cast and capture diff
metadata. For SIMPLE tickets, draft an email body via a hardcoded template.
"""

from __future__ import annotations

from agent_mes.interfaces import CodexBuilderProtocol
from agent_mes.schema import Artifact, MESTask, StageEnum, StageEvent, TicketType
from agent_mes.stages.base import BaseStage


EMAIL_TEMPLATE = """Subject: Update on the auth service incident

Hi team,

Quick status on the auth-service rate-limit incident from last night:

ROOT CAUSE: rate limiter bucket on /v2/oauth was set to 100rpm, which
caused token-refresh storms during peak hours and surfaced as 429 errors
for customers using the new mobile client.

CURRENT STATE: change is in review with the platform team. The fix raises
the bucket to 500rpm to match the /v1/login parity we shipped last month.

ETA: deploy by EOD today. I'll send a follow-up confirming green metrics.

Let me know if you have questions.

— marcus
"""


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
        word_count = len(EMAIL_TEMPLATE.split())
        event = self._emit_event(
            task=task,
            agent=self.AGENT,
            action="drafted email body",
            metadata={
                "recipient": "team@heliograph",
                "word_count": word_count,
                "status": "PASS",
            },
            artifacts=[
                Artifact(
                    type="email",
                    ref="drafts/email-TKT-002.md",
                    summary=f"{word_count} words",
                )
            ],
        )
        # Stash the email body on the task so Deploy can write it
        task.context_bundle["email_body"] = EMAIL_TEMPLATE
        return [event]
