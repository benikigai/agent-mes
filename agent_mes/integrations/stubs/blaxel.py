"""Choreographed stub of BlaxelVerifierProtocol — the demo gold moment.

The self-heal loop runs DETERMINISTICALLY through 3 iterations:
  iter 1 → fail on import (the poison payload module is "imported")
  iter 2 → fail on egress kill (BLAST_RADIUS_VIOLATION at <25ms)
  iter 3 → pass (clean run, all checks green)

Each iteration emits a result dict the orchestrator turns into a StageEvent.
The Stage 4 column visibly cycles through these three states during the demo.

When Vish's real Blaxel impl lands, the import in cli.py swaps over and the
exact same orchestration code drives the real microVMs.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from agent_mes.demo.poison_payload import attempt_phone_home


@dataclass
class StubSandbox:
    """Opaque handle returned by create_sandbox."""

    id: str
    iteration: int = 0
    state: str = "running"
    blast_radius: dict[str, Any] = field(default_factory=dict)


class StubBlaxelVerifier:
    """Implements BlaxelVerifierProtocol with a choreographed self-heal loop."""

    async def create_sandbox(
        self, task_id: str, blast_radius: dict[str, Any]
    ) -> StubSandbox:
        """Spin up a fake microVM. ~50ms simulated boot time so the demo
        feels live."""
        await asyncio.sleep(0.05)
        return StubSandbox(id=f"sbx_{task_id}", iteration=0, blast_radius=blast_radius)

    async def run_check(self, sandbox: StubSandbox, machine_check: str) -> dict[str, Any]:
        """Execute a single acceptance criterion. The result is determined
        by the sandbox's current iteration counter so the demo is reliable."""
        await asyncio.sleep(0.55)  # each iter visibly cycles fail → kill → pass

        if sandbox.iteration == 1:
            return {
                "passed": False,
                "stdout": "",
                "stderr": (
                    "ImportError: cannot import name 'safe_handler' from "
                    "'agent_mes.demo.poison_payload' — module attempted "
                    "outbound network call during import"
                ),
            }

        if sandbox.iteration == 2:
            # The kill iteration — egress violation triggered during the
            # check. The orchestrator polls detect_egress_violation right
            # after this returns and gets the BLAST_RADIUS_VIOLATION log.
            return {
                "passed": False,
                "stdout": "",
                "stderr": "sandbox terminated by blaxel_egress_monitor",
            }

        # iter 3 (and any subsequent) → green
        return {
            "passed": True,
            "stdout": "pytest 5 passed in 0.42s",
            "stderr": "",
        }

    async def detect_egress_violation(
        self, sandbox: StubSandbox
    ) -> dict[str, Any] | None:
        """Returns the BLAST_RADIUS_VIOLATION log if the current iteration
        is the egress-kill iteration; None otherwise."""
        if sandbox.iteration != 2:
            return None
        report = attempt_phone_home()
        return {
            "violated_at": datetime.now().isoformat(),
            "destination": report["destination"],
            "killed_in_ms": 23,
            "reason": report["reason"],
            "blocked_by": report["blocked_by"],
        }

    async def self_heal_loop(
        self,
        sandbox: StubSandbox,
        code_diff: str,
        checks: list[str],
        max_iterations: int = 3,
    ) -> dict[str, Any]:
        """Orchestrate the choreographed 3-iteration self-heal sequence.

        Returns a structured result with one entry per iteration. The Test
        stage uses this to emit one StageEvent per iteration so the card
        visibly cycles through the states.
        """
        iterations: list[dict[str, Any]] = []
        for i in range(1, max_iterations + 1):
            sandbox.iteration = i

            check_result = await self.run_check(sandbox, checks[0] if checks else "pytest")

            if i == 2:
                # Egress kill iteration — surface the violation
                violation = await self.detect_egress_violation(sandbox)
                iterations.append(
                    {
                        "iteration": i,
                        "status": "killed",
                        "violation": violation,
                        "stderr": check_result["stderr"],
                    }
                )
                # New sandbox resumes from standby for the next iteration
                sandbox.state = "resumed"
                continue

            if check_result["passed"]:
                iterations.append(
                    {
                        "iteration": i,
                        "status": "pass",
                        "stdout": check_result["stdout"],
                    }
                )
                return {"iterations": iterations, "final_status": "pass"}

            iterations.append(
                {
                    "iteration": i,
                    "status": "fail",
                    "stderr": check_result["stderr"],
                }
            )

        return {"iterations": iterations, "final_status": "fail"}
