"""Stage 4 — Test. For CODE tickets, run the Blaxel self-heal loop (the
demo gold moment with the egress kill). For SIMPLE tickets, run a stubbed
Gemini grammar/tone check.
"""

from __future__ import annotations

import asyncio

from agent_mes.artifacts import render_and_save
from agent_mes.interfaces import BlaxelVerifierProtocol
from agent_mes.schema import Artifact, MESTask, StageEnum, StageEvent, TicketType
from agent_mes.stages.base import BaseStage


class TestStage(BaseStage):
    __test__ = False  # tell pytest this is not a test class

    STAGE = StageEnum.TEST
    AGENT = "Gemini"

    def __init__(self, blaxel: BlaxelVerifierProtocol) -> None:
        self.blaxel = blaxel

    async def execute(self, task: MESTask) -> list[StageEvent]:
        task.current_stage = StageEnum.TEST
        if task.type == TicketType.CODE:
            return await self._test_code(task)
        return await self._test_email(task)

    async def _test_code(self, task: MESTask) -> list[StageEvent]:
        events: list[StageEvent] = []

        events.append(
            await self._emit_event(
                task=task,
                agent="Blaxel",
                action="spinning up sandbox microVM",
                metadata={
                    "blast_radius": task.blast_radius.model_dump(mode="json"),
                    "status": "RUN",
                },
            )
        )

        # Real Blaxel call — create (or reuse) a per-ticket sandbox with a
        # public preview URL. If anything goes wrong (credits, network, auth),
        # fall back to the choreographed stub so the demo keeps moving.
        sandbox = None
        sandbox_err: str | None = None
        try:
            sandbox = await self.blaxel.create_sandbox(
                task_id=task.id,
                blast_radius=task.blast_radius.model_dump(),
            )
        except Exception as exc:  # noqa: BLE001
            sandbox_err = f"{type(exc).__name__}: {exc}"[:140]
            # Fall back to the stub instance so the rest of the pipeline
            # still runs. Emit a WARN event so the operator sees it.
            from agent_mes.integrations.stubs.blaxel import StubBlaxelVerifier
            self.blaxel = StubBlaxelVerifier()
            sandbox = await self.blaxel.create_sandbox(
                task_id=task.id,
                blast_radius=task.blast_radius.model_dump(),
            )
            events.append(
                await self._emit_event(
                    task=task,
                    agent="Blaxel",
                    action=f"live API failed — fell back to local stub ({sandbox_err})",
                    metadata={"error": sandbox_err, "status": "WARN"},
                )
            )

        # If we got a real LiveSandbox, surface the URLs as artifacts so the
        # card shows clickable links to the actual sandbox + console.
        preview_url = getattr(sandbox, "preview_url", None)
        dashboard_url = getattr(sandbox, "dashboard_url", None)
        if preview_url or dashboard_url:
            live_artifacts: list[Artifact] = []
            if preview_url:
                live_artifacts.append(
                    Artifact(
                        type="sandbox",
                        ref=preview_url,
                        summary=f"↗ live Blaxel sandbox — {sandbox.sandbox_name}",
                    )
                )
            if dashboard_url:
                live_artifacts.append(
                    Artifact(
                        type="sandbox",
                        ref=dashboard_url,
                        summary="↗ Blaxel console dashboard",
                    )
                )
            events.append(
                await self._emit_event(
                    task=task,
                    agent="Blaxel",
                    action=f"LIVE sandbox deployed: {sandbox.sandbox_name}",
                    metadata={
                        "sandbox_id": sandbox.sandbox_name,
                        "region": getattr(sandbox, "region", ""),
                        "preview_url": preview_url or "",
                        "dashboard_url": dashboard_url or "",
                        "bl_status": getattr(sandbox, "bl_status", ""),
                        "status": "PASS",
                    },
                    artifacts=live_artifacts,
                )
            )
            # Stash the preview URL on the task so other stages / artifacts
            # can reference it.
            task.context_bundle["blaxel_preview_url"] = preview_url or ""
            task.context_bundle["blaxel_sandbox_name"] = sandbox.sandbox_name

        await asyncio.sleep(0.75)

        events.append(
            await self._emit_event(
                task=task,
                agent="Blaxel",
                action=f"copying diff into sandbox {sandbox.id}",
                metadata={"files": "auth/middleware.py", "status": "RUN"},
            )
        )
        await asyncio.sleep(0.7)

        events.append(
            await self._emit_event(
                task=task,
                agent="Blaxel",
                action=f"installing deps + running {len(task.acceptance_criteria)} checks",
                metadata={
                    "checks": [ac.machine_check[:40] for ac in task.acceptance_criteria],
                    "status": "RUN",
                },
            )
        )
        await asyncio.sleep(0.75)

        loop_result = await self.blaxel.self_heal_loop(
            sandbox=sandbox,
            code_diff="(stubbed diff)",
            checks=[ac.machine_check for ac in task.acceptance_criteria],
            max_iterations=3,
        )

        for iter_result in loop_result["iterations"]:
            i = iter_result["iteration"]
            status = iter_result["status"]

            if status == "killed":
                violation = iter_result["violation"]
                events.append(
                    await self._emit_event(
                        task=task,
                        agent="Blaxel",
                        action=(
                            f"iter {i}: KILLED — egress to "
                            f"{violation['destination']} ({violation['killed_in_ms']}ms)"
                        ),
                        metadata={"violation": violation, "status": "KILLED"},
                    )
                )
            elif status == "fail":
                events.append(
                    await self._emit_event(
                        task=task,
                        agent="Gemini",
                        action=f"iter {i}: FAIL — {iter_result['stderr'][:50]}",
                        metadata={"stderr": iter_result["stderr"], "status": "FAIL"},
                    )
                )
            else:  # pass
                events.append(
                    await self._emit_event(
                        task=task,
                        agent="Gemini",
                        action=f"iter {i}: PASS — {iter_result['stdout'][:40]}",
                        metadata={"stdout": iter_result["stdout"], "status": "PASS"},
                    )
                )
            # Let each iteration breathe so the audience sees the loop cycle
            await asyncio.sleep(0.85)

        events.append(
            await self._emit_event(
                task=task,
                agent="Blaxel",
                action="sandbox torn down — results captured",
                metadata={
                    "iterations": len(loop_result["iterations"]),
                    "final_status": loop_result.get("final_status", "pass"),
                    "status": "PASS",
                },
            )
        )
        events[-1].artifacts.append(render_and_save(task, "test"))
        await asyncio.sleep(0.55)
        return events

    async def _test_email(self, task: MESTask) -> list[StageEvent]:
        events: list[StageEvent] = []
        events.append(
            await self._emit_event(
                task=task,
                agent=self.AGENT,
                action="checking tone calibration against brand voice",
                metadata={"status": "RUN"},
            )
        )
        await asyncio.sleep(0.85)

        events.append(
            await self._emit_event(
                task=task,
                agent=self.AGENT,
                action="running grammar + PII lint",
                metadata={"status": "RUN"},
            )
        )
        await asyncio.sleep(0.85)

        events.append(
            await self._emit_event(
                task=task,
                agent=self.AGENT,
                action="verifying 5 whys section depth",
                metadata={"status": "RUN"},
            )
        )
        await asyncio.sleep(0.75)

        events.append(
            await self._emit_event(
                task=task,
                agent=self.AGENT,
                action="grammar+tone OK — 0 lint errors",
                metadata={
                    "tone": "calm",
                    "grammar_errors": 0,
                    "status": "PASS",
                },
            )
        )
        events[-1].artifacts.append(render_and_save(task, "test"))
        await asyncio.sleep(0.55)
        return events
