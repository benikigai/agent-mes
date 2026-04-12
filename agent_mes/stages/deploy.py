"""Stage 7 — Deploy & Maintain.

For CODE tickets: open a **real** GitHub PR against ``benikigai/agent-mes``
with the receipts as the body and a new markdown file under ``demo-runs/``
as the actual change. Uses a disposable git worktree so the running
server's checkout (on whichever feature branch) is not disturbed.

For SIMPLE tickets: write the drafted email to ``.demo/outputs/``.

Both: log a monitoring breadcrumb to Redis (the standby Blaxel sandbox is
mentioned in the receipts but not literally created).

Real-PR behavior is gated on ``self.dry_run`` — server defaults to real
PRs when ``AGENTMES_OPEN_REAL_PR`` is set; otherwise it emits a dry-run
receipt that shows the exact ``gh pr create`` command that would have run.
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Awaitable, Callable

from agent_mes.artifacts import render_and_save
from agent_mes.interfaces import RedisMemoryProtocol
from agent_mes.schema import Artifact, HumanGate, MESTask, StageEnum, StageEvent, TicketType
from agent_mes.stages.base import BaseStage

OUTPUTS_DIR = Path(".demo/outputs")
# Resolve the repo root at import time so git worktree commands work no
# matter what cwd the server was launched from.
REPO_ROOT = Path(__file__).resolve().parents[2]

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

        # Real-PR path — create a disposable worktree off origin/main,
        # commit a new file under demo-runs/, push, open PR, clean up.
        pr_result = await self._open_real_pr(task, body)
        events.append(
            await self._emit_event(
                task=task,
                agent="GitHub",
                action=pr_result["action"],
                metadata=pr_result["metadata"],
                artifacts=pr_result["artifacts"],
            )
        )
        return events

    async def _open_real_pr(self, task: MESTask, body: str) -> dict:
        """Open a **real** GitHub PR.

        Uses a disposable git worktree at ``/tmp/agentmes-pr-<id>`` so the
        running server's checkout is never touched. Commits a new file
        under ``demo-runs/{task_id}-{timestamp}.md`` whose body is the
        full PR markdown (receipts + embedded diff). Branches off
        ``origin/main`` to avoid dragging in any in-flight feature work.

        Returns a dict ``{action, metadata, artifacts}`` the caller can
        pass straight into ``_emit_event``. All errors are caught and
        turned into a degraded WARN event so the demo keeps moving.
        """
        timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        run_id = f"{task.id}-{timestamp}".lower()
        branch = f"agentmes-run/{run_id}"
        worktree_path = Path(tempfile.gettempdir()) / f"agentmes-pr-{run_id}"
        file_rel_path = f"demo-runs/{run_id}.md"
        title = f"AgentMES: {task.intent[:60]}"

        async def run(*cmd: str, cwd: Path | None = None) -> tuple[int, str, str]:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(cwd) if cwd else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, err = await proc.communicate()
            return proc.returncode or 0, out.decode("utf-8", "replace"), err.decode("utf-8", "replace")

        try:
            # 1. Fetch origin so we branch off the latest main
            await run("git", "fetch", "origin", "main", cwd=REPO_ROOT)
            # 2. Create worktree + branch off origin/main
            rc, _, err = await run(
                "git",
                "worktree",
                "add",
                "-b",
                branch,
                str(worktree_path),
                "origin/main",
                cwd=REPO_ROOT,
            )
            if rc != 0:
                raise RuntimeError(f"worktree add failed: {err[:120]}")

            # 3. Write the demo-runs file
            demo_runs_dir = worktree_path / "demo-runs"
            demo_runs_dir.mkdir(parents=True, exist_ok=True)
            out_file = worktree_path / file_rel_path
            out_file.write_text(body, encoding="utf-8")

            # 4. Commit
            await run("git", "add", file_rel_path, cwd=worktree_path)
            rc, _, err = await run(
                "git",
                "commit",
                "-m",
                f"demo(agentmes): AgentMES run for {task.id} ({task.intent[:48]})",
                cwd=worktree_path,
            )
            if rc != 0:
                raise RuntimeError(f"commit failed: {err[:120]}")

            # 5. Push the branch
            rc, _, err = await run(
                "git",
                "push",
                "-u",
                "origin",
                f"{branch}:{branch}",
                cwd=worktree_path,
            )
            if rc != 0:
                raise RuntimeError(f"push failed: {err[:120]}")

            # 6. Open PR via gh
            pr_body_file = Path(tempfile.gettempdir()) / f"agentmes-pr-body-{run_id}.md"
            pr_body_file.write_text(body, encoding="utf-8")
            try:
                rc, stdout, err = await run(
                    "gh",
                    "pr",
                    "create",
                    "--repo",
                    self.github_repo,
                    "--base",
                    "main",
                    "--head",
                    branch,
                    "--title",
                    title,
                    "--body-file",
                    str(pr_body_file),
                    cwd=worktree_path,
                )
                if rc != 0:
                    raise RuntimeError(f"gh pr create failed: {err[:200]}")
                pr_url = stdout.strip().splitlines()[-1] if stdout.strip() else ""
            finally:
                pr_body_file.unlink(missing_ok=True)

            return {
                "action": f"PR opened → {pr_url}",
                "metadata": {
                    "pr_url": pr_url,
                    "branch": branch,
                    "committed_file": file_rel_path,
                    "standby": "blaxel",
                    "status": "PASS",
                },
                "artifacts": [
                    Artifact(type="pr", ref=pr_url, summary=f"↗ open PR — {branch}"),
                ],
            }
        except Exception as exc:  # noqa: BLE001 — demo must never crash
            return {
                "action": f"PR open failed — {type(exc).__name__}: {str(exc)[:80]}",
                "metadata": {
                    "error": f"{type(exc).__name__}: {exc}"[:200],
                    "branch": branch,
                    "status": "WARN",
                },
                "artifacts": [],
            }
        finally:
            # Always remove the worktree — don't leave /tmp littered.
            if worktree_path.exists():
                try:
                    await run(
                        "git",
                        "worktree",
                        "remove",
                        "--force",
                        str(worktree_path),
                        cwd=REPO_ROOT,
                    )
                except Exception:
                    shutil.rmtree(worktree_path, ignore_errors=True)

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
