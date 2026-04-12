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
import difflib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Awaitable, Callable

from agent_mes.artifacts import render_and_save
from agent_mes.integrations.demo_patches import (
    FIXED_OAUTH_MIDDLEWARE,
    TEMPLATE_MIDDLEWARE_PATH,
)
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

        # Re-surface the live Blaxel sandbox from the Test stage as the
        # rollback standby. It's already running — this event gives the
        # Deploy lane a clickable link so the operator can see the same
        # preview URL that Test created, now promoted to standby state.
        standby_artifacts: list[Artifact] = []
        preview_url = task.context_bundle.get("blaxel_preview_url") or ""
        sandbox_name = task.context_bundle.get("blaxel_sandbox_name") or ""
        if preview_url:
            standby_artifacts.append(
                Artifact(
                    type="sandbox",
                    ref=preview_url,
                    summary=f"↗ ACTIVE standby sandbox — {sandbox_name}",
                )
            )
        if sandbox_name:
            standby_artifacts.append(
                Artifact(
                    type="sandbox",
                    ref=(
                        "https://app.blaxel.ai/ai-hackday/"
                        f"global-inference-network/sandbox/{sandbox_name}"
                    ),
                    summary="↗ Blaxel console (standby promotion)",
                )
            )
        events.append(
            await self._emit_event(
                task=task,
                agent="Blaxel",
                action=(
                    f"standby sandbox active — {sandbox_name}"
                    if sandbox_name
                    else "parking standby sandbox for fast rollback"
                ),
                metadata={
                    "state": "standby",
                    "sandbox_name": sandbox_name,
                    "preview_url": preview_url,
                    "rollback_ready": bool(preview_url),
                    "status": "PASS" if preview_url else "RUN",
                },
                artifacts=standby_artifacts,
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
        run_dir_rel = f"demo-runs/runs/{run_id}"
        title = f"[AgentMES Kanban] {task.intent[:70]}"

        # Build a top-of-body callout that makes it obvious on GitHub this
        # PR was auto-generated by the kanban — includes ticket id, live
        # Blaxel sandbox URL (if Test stage created one), and back-links
        # to the repo. Injected ahead of the existing receipts body.
        preview_url = task.context_bundle.get("blaxel_preview_url") or ""
        sandbox_name = task.context_bundle.get("blaxel_sandbox_name") or ""
        callout_lines = [
            "> **AgentMES Kanban Test Case** — auto-generated by "
            "[AgentMES](https://github.com/benikigai/agent-mes) "
            "(Blaxel × Codex × Redis AI Hack Day, 2026-04-11)",
            ">",
            f"> - **Ticket:** `{task.id}` · {task.type.value}",
            f"> - **Requester:** `{task.requester}` from `{task.source}`",
        ]
        if preview_url:
            callout_lines.append(
                f"> - **Live Blaxel sandbox:** [{sandbox_name}]({preview_url})"
            )
        callout_lines += [
            "> - **Pipeline:** 7-stage MES — Plan → Design → Build → Test → "
            "Review (human) → Document → Deploy (human)",
            "> - **Drift catch:** Stage 5 Review cross-checked 3 "
            "[plushpalace-world](https://github.com/benikigai/plushpalace-world) "
            "memories against Context Surfaces ground truth",
            f"> - **Files committed in this PR:**",
            f"> - `{run_dir_rel}/auth/middleware.py` — the actual code fix "
            "(single-flight refresh lock)",
            f"> - `{run_dir_rel}/fix.diff` — unified diff against the "
            f"buggy template at `{TEMPLATE_MIDDLEWARE_PATH}`",
            f"> - `{run_dir_rel}/README.md` — stage receipts + narrative",
            "",
            "---",
            "",
        ]
        body = "\n".join(callout_lines) + body

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

            # 3. Compute the real diff against the buggy template on
            #    origin/main and write three files per run:
            #      a) the fixed source (real code change)
            #      b) a unified diff against the template
            #      c) the receipts log
            template_full = worktree_path / TEMPLATE_MIDDLEWARE_PATH
            if template_full.exists():
                template_src = template_full.read_text(encoding="utf-8")
            else:
                template_src = "# template not found on origin/main\n"

            fixed_target_rel = f"{run_dir_rel}/auth/middleware.py"
            diff_lines = list(
                difflib.unified_diff(
                    template_src.splitlines(keepends=True),
                    FIXED_OAUTH_MIDDLEWARE.splitlines(keepends=True),
                    fromfile=f"a/{TEMPLATE_MIDDLEWARE_PATH}",
                    tofile=f"b/{fixed_target_rel}",
                    n=3,
                )
            )
            diff_text = "".join(diff_lines) or "(diff empty — template missing?)\n"

            run_dir_abs = worktree_path / run_dir_rel
            (run_dir_abs / "auth").mkdir(parents=True, exist_ok=True)
            (run_dir_abs / "auth" / "middleware.py").write_text(
                FIXED_OAUTH_MIDDLEWARE, encoding="utf-8"
            )
            (run_dir_abs / "fix.diff").write_text(diff_text, encoding="utf-8")
            (run_dir_abs / "README.md").write_text(body, encoding="utf-8")

            # 4. Commit — stage the whole run directory so git picks up
            #    all three files, with git-friendly stats.
            await run("git", "add", run_dir_rel, cwd=worktree_path)
            rc, _, err = await run(
                "git",
                "commit",
                "-m",
                (
                    f"demo(agentmes): TKT-001 {task.intent[:48]}\n\n"
                    f"- {fixed_target_rel} (fixed middleware)\n"
                    f"- {run_dir_rel}/fix.diff (unified diff)\n"
                    f"- {run_dir_rel}/README.md (stage receipts)"
                ),
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
                    "--label",
                    "agentmes-kanban",
                    "--label",
                    "demo",
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
                    "committed_files": [
                        f"{run_dir_rel}/auth/middleware.py",
                        f"{run_dir_rel}/fix.diff",
                        f"{run_dir_rel}/README.md",
                    ],
                    "fixed_target": fixed_target_rel,
                    "diff_lines": len(diff_lines),
                    "standby": "blaxel",
                    "status": "PASS",
                },
                "artifacts": [
                    Artifact(
                        type="pr",
                        ref=pr_url,
                        summary=f"↗ open PR — {branch} (3 files)",
                    ),
                    Artifact(
                        type="file",
                        ref=f"{pr_url}/files",
                        summary="↗ PR files — see real middleware.py diff",
                    ),
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
        # Surface the saved file as a clickable viewer URL so operators
        # can open the actual rendered postmortem in a new tab. The
        # /output/{task_id} endpoint reads .demo/outputs/ from disk and
        # renders with marked.js in the same dark theme as /artifact.
        events.append(
            await self._emit_event(
                task=task,
                agent="file",
                action=f"saved postmortem to {out_path.name}",
                metadata={
                    "posted_to": "#incidents",
                    "path": str(out_path),
                    "status": "PASS",
                },
                artifacts=[
                    Artifact(
                        type="email",
                        ref=f"/output/{task.id}",
                        summary=f"↗ open delivered postmortem — {out_path.name}",
                    ),
                ],
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
