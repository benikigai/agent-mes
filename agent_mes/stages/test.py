"""Stage 4 — Test. For CODE tickets, run the Blaxel self-heal loop (the
demo gold moment with the egress kill). For SIMPLE tickets, run a stubbed
Gemini grammar/tone check.
"""

from __future__ import annotations

import asyncio

from agent_mes.artifacts import render_and_save
from agent_mes.interfaces import BlaxelVerifierProtocol
from agent_mes.schema import MESTask, StageEnum, StageEvent, TicketType
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
        sandbox = await self.blaxel.create_sandbox(
            task_id=task.id,
            blast_radius=task.blast_radius.model_dump(),
        )
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
