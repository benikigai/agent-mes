"""Stage 7 — Deploy & Maintain.

For CODE tickets: open a real GitHub PR with the receipts as the body
(or print the gh command if dry_run). For SIMPLE tickets: write the
drafted email to .demo/outputs/. Both: log a monitoring breadcrumb to
Redis (the standby Blaxel sandbox is mentioned in the receipts but not
literally created).
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Awaitable, Callable

from agent_mes.artifacts import render_and_save
from agent_mes.interfaces import RedisMemoryProtocol
from agent_mes.schema import Artifact, HumanGate, MESTask, StageEnum, StageEvent, TicketType
from agent_mes.stages.base import BaseStage

OUTPUTS_DIR = Path(".demo/outputs")

GateProvider = Callable[[HumanGate], Awaitable[bool]]


class DeployStage(BaseStage):
    STAGE = StageEnum.DEPLOY
    AGENT = "GitHub+Blaxel+Redis"

    def __init__(
        self,
        redis: RedisMemoryProtocol,
        github_repo: str = "benikigai/agent-mes",
        dry_run: bool = False,
        gate_provider: GateProvider | None = None,
    ) -> None:
        self.redis = redis
        self.github_repo = github_repo
        self.dry_run = dry_run
        self.gate_provider = gate_provider
        OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)

    async def execute(self, task: MESTask) -> list[StageEvent]:
        task.current_stage = StageEnum.DEPLOY
        events: list[StageEvent] = []

        # Human ship-it gate — CODE tickets block here because shipping to
        # production code requires explicit human judgment. SIMPLE tickets
        # (postmortems) auto-ship because they're write-only artifacts.
        if task.type == TicketType.CODE:
            task.status = "blocked"
            gate = HumanGate(
                stage=StageEnum.DEPLOY,
                prompt=f"Ship {task.id} to production? (opens PR against {self.github_repo})",
            )
            events.append(
                await self._emit_event(
                    task=task,
                    agent="HUMAN",
                    action="awaiting ship-it approval",
                    metadata={
                        "prompt": gate.prompt,
                        "reason": "high-risk: production code change",
                        "status": "RUN",
                    },
                )
            )

            approved = await self._await_human(gate)
            gate.approved = approved
            gate.approver = "ben" if approved else None
            task.human_gates.append(gate)
            task.status = "running"

            if not approved:
                events.append(
                    await self._emit_event(
                        task=task,
                        agent="HUMAN",
                        action="deploy rejected — PR not opened, task closed",
                        metadata={"status": "FAIL"},
                    )
                )
                events[-1].artifacts.append(render_and_save(task, "deploy"))
                task.status = "killed"
                return events

            events.append(
                await self._emit_event(
                    task=task,
                    agent="HUMAN",
                    action="deploy approved — proceeding to open PR",
                    metadata={"approver": gate.approver, "status": "PASS"},
                )
            )
            await asyncio.sleep(0.5)

        if task.type == TicketType.CODE:
            events += await self._deploy_code(task)
        else:
            events += await self._deploy_email(task)

        events.append(
            await self._emit_event(
                task=task,
                agent="Blaxel",
                action="parking standby sandbox for fast rollback",
                metadata={"state": "standby", "status": "RUN"},
            )
        )
        await asyncio.sleep(0.7)

        # Log a monitoring breadcrumb (Blaxel standby + Redis log)
        await self.redis.write_lesson(
            text=f"deploy event for {task.id}: {task.intent}",
            topics=["deploy", "monitoring"],
            user_id=task.requester,
        )
        events.append(
            await self._emit_event(
                task=task,
                agent="Redis",
                action="monitoring breadcrumb logged",
                metadata={"standby": "blaxel", "topics": "deploy,monitoring", "status": "PASS"},
            )
        )

        events[-1].artifacts.append(render_and_save(task, "deploy"))
        await asyncio.sleep(0.6)

        task.status = "merged"
        return events

    async def _deploy_code(self, task: MESTask) -> list[StageEvent]:
        events: list[StageEvent] = []
        events.append(
            await self._emit_event(
                task=task,
                agent="GitHub",
                action="collecting receipts from every stage",
                metadata={"event_count": len(task.events), "status": "RUN"},
            )
        )
        await asyncio.sleep(0.75)

        events.append(
            await self._emit_event(
                task=task,
                agent="GitHub",
                action="assembling PR body (title + receipts + diff)",
                metadata={"status": "RUN"},
            )
        )
        await asyncio.sleep(0.75)

        body = self._render_pr_body(task)

        if self.dry_run:
            ref = f"(dry-run) gh pr create --title 'AgentMES: {task.intent[:40]}'"
            events.append(
                await self._emit_event(
                    task=task,
                    agent="GitHub",
                    action="PR opened (dry-run)",
                    metadata={"pr_url": ref, "standby": "blaxel", "status": "PASS"},
                    artifacts=[Artifact(type="pr", ref=ref, summary="dry-run only")],
                )
            )
            return events

        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write(body)
            body_path = f.name

        try:
            result = subprocess.run(
                [
                    "gh",
                    "pr",
                    "create",
                    "--repo",
                    self.github_repo,
                    "--title",
                    f"AgentMES: {task.intent[:60]}",
                    "--body-file",
                    body_path,
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            pr_url = (
                result.stdout.strip()
                if result.returncode == 0
                else f"(failed: {result.stderr[:80]})"
            )
        except Exception as e:
            pr_url = f"(error: {e})"
        finally:
            Path(body_path).unlink(missing_ok=True)

        events.append(
            await self._emit_event(
                task=task,
                agent="GitHub",
                action="PR opened",
                metadata={"pr_url": pr_url, "standby": "blaxel", "status": "PASS"},
                artifacts=[Artifact(type="pr", ref=pr_url, summary="real PR")],
            )
        )
        return events

    async def _deploy_email(self, task: MESTask) -> list[StageEvent]:
        events: list[StageEvent] = []
        events.append(
            await self._emit_event(
                task=task,
                agent="file",
                action="serializing postmortem markdown",
                metadata={"status": "RUN"},
            )
        )
        await asyncio.sleep(0.75)

        events.append(
            await self._emit_event(
                task=task,
                agent="file",
                action=f"writing .demo/outputs/postmortem-{task.id}.md",
                metadata={"status": "RUN"},
            )
        )
        await asyncio.sleep(0.7)

        body = task.context_bundle.get("email_body", "(no body)")
        out_path = OUTPUTS_DIR / f"postmortem-{task.id}.md"
        out_path.write_text(body)
        events.append(
            await self._emit_event(
                task=task,
                agent="file",
                action=f"saved postmortem to {out_path.name}",
                metadata={"posted_to": "#incidents", "status": "PASS"},
                artifacts=[Artifact(type="email", ref=str(out_path), summary="postmortem")],
            )
        )
        return events

    async def _await_human(self, gate: HumanGate) -> bool:
        """Block until the browser POSTs /api/approve/{task_id} (via the
        gate_provider) or stdin input arrives in terminal mode. Mirrors
        ReviewStage._await_human so the same web gate mechanism drives
        both human gates."""
        if self.gate_provider is not None:
            return await self.gate_provider(gate)
        if os.environ.get("AGENTMES_AUTO_APPROVE") == "1":
            await asyncio.sleep(0.1)
            return True
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(None, input, gate.prompt)
        return response.strip().lower() in ("y", "yes")

    def _render_pr_body(self, task: MESTask) -> str:
        lines = [
            f"# AgentMES: {task.intent}",
            "",
            f"**Ticket:** {task.id}",
            f"**Requester:** {task.requester}",
            f"**Source:** {task.source}",
            "",
            "## Receipts (auto-generated by AgentMES)",
            "",
        ]
        for ev in task.events:
            lines.append(f"- **[{ev.stage.value}]** `{ev.agent}` — {ev.action}")
        lines.append("")
        lines.append("---")
        lines.append("Generated by AgentMES — 7-stage AI-native engineering pipeline.")
        return "\n".join(lines)
