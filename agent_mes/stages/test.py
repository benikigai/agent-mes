"""Stage 4 — Test. For CODE tickets, run the Blaxel self-heal loop (the
demo gold moment with the egress kill). For SIMPLE tickets, run a stubbed
Gemini grammar/tone check.
"""

from __future__ import annotations

import asyncio

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
        sandbox = await self.blaxel.create_sandbox(
            task_id=task.id,
            blast_radius=task.blast_radius.model_dump(),
        )

        loop_result = await self.blaxel.self_heal_loop(
            sandbox=sandbox,
            code_diff="(stubbed diff)",
            checks=[ac.machine_check for ac in task.acceptance_criteria],
            max_iterations=3,
        )

        events: list[StageEvent] = []
        for iter_result in loop_result["iterations"]:
            i = iter_result["iteration"]
            status = iter_result["status"]

            if status == "killed":
                violation = iter_result["violation"]
                event = self._emit_event(
                    task=task,
                    agent="Blaxel",
                    action=f"iter {i}: KILLED — egress to {violation['destination']} ({violation['killed_in_ms']}ms)",
                    metadata={
                        "violation": violation,
                        "status": "KILLED",
                    },
                )
            elif status == "fail":
                event = self._emit_event(
                    task=task,
                    agent="Gemini",
                    action=f"iter {i}: FAIL — {iter_result['stderr'][:50]}",
                    metadata={
                        "stderr": iter_result["stderr"],
                        "status": "FAIL",
                    },
                )
            else:  # pass
                event = self._emit_event(
                    task=task,
                    agent="Gemini",
                    action=f"iter {i}: PASS — {iter_result['stdout'][:40]}",
                    metadata={
                        "stdout": iter_result["stdout"],
                        "status": "PASS",
                    },
                )
            events.append(event)

        return events

    async def _test_email(self, task: MESTask) -> list[StageEvent]:
        await asyncio.sleep(0.3)  # simulated review pass
        event = self._emit_event(
            task=task,
            agent=self.AGENT,
            action="grammar+tone OK",
            metadata={
                "tone": "calm",
                "grammar_errors": 0,
                "status": "PASS",
            },
        )
        return [event]
