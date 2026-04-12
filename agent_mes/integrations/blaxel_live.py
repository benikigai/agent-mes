"""Real Blaxel sandbox integration.

Implements the BlaxelVerifierProtocol by calling the real Blaxel Python
SDK against the workspace configured in ``~/.blaxel/config.yaml``. Each
task gets its own per-ticket sandbox (``agentmes-tkt-001``) with a
public preview URL on port 8080 — clicking the link in the kanban card
opens a live Next.js instance running in a real Blaxel microVM.

The choreographed self-heal loop (iter 1 fail → iter 2 egress kill →
iter 3 pass) is still driven by the stub's deterministic iteration
counter because the fixtures don't actually attempt to phone home.
The win is: the **sandbox is real**, the **preview URL is real**, and
the operator can click through to the Blaxel dashboard during the demo.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from agent_mes.integrations.stubs.blaxel import StubBlaxelVerifier, StubSandbox

# Blaxel workspace derived from ~/.blaxel/config.yaml at runtime, but we
# hardcode it here too so the dashboard URL resolves even if the runtime
# config isn't available.
BLAXEL_WORKSPACE = "ai-hackday"
BLAXEL_CONSOLE_BASE = "https://app.blaxel.ai"


@dataclass
class LiveSandbox(StubSandbox):
    """StubSandbox shape plus the real Blaxel URLs we surface in the UI."""

    preview_url: str = ""
    dashboard_url: str = ""
    sandbox_name: str = ""
    region: str = ""
    bl_status: str = ""


class BlaxelLiveVerifier(StubBlaxelVerifier):
    """Real Blaxel wrapper that inherits the stub's choreographed loop.

    ``create_sandbox`` is the only overridden method — it hits the real
    Blaxel API, creates a sandbox + public preview, and returns a
    ``LiveSandbox`` handle carrying the URLs. The rest of the protocol
    (run_check, self_heal_loop, detect_egress_violation) falls through
    to ``StubBlaxelVerifier`` so the demo's deterministic fail → kill →
    pass trajectory still fires.
    """

    def __init__(self, image: str = "blaxel/nextjs:latest", memory_mb: int = 2048) -> None:
        self.image = image
        self.memory_mb = memory_mb

    async def create_sandbox(
        self, task_id: str, blast_radius: dict[str, Any]
    ) -> LiveSandbox:
        # Blaxel names must be lowercase dns-label compatible
        sandbox_name = f"agentmes-{task_id.lower()}"

        # Import lazily so the pipeline still loads if the SDK is missing.
        from blaxel.core import SandboxInstance

        sb = await SandboxInstance.create_if_not_exists(
            {
                "name": sandbox_name,
                "image": self.image,
                "memory": self.memory_mb,
                # Next.js auto-starts on port 3000 in blaxel/nextjs:latest;
                # expose it so the preview URL actually serves the app.
                "ports": [{"target": 3000, "protocol": "HTTP"}],
            }
        )

        # Public preview URL — THIS is the demo click-through.
        preview = await sb.previews.create_if_not_exists(
            {
                "metadata": {"name": "public-web"},
                "spec": {"port": 3000, "public": True},
            }
        )
        preview_url = getattr(preview.spec, "url", "") or ""

        region = getattr(sb.spec, "region", "") or ""
        dashboard_url = (
            f"{BLAXEL_CONSOLE_BASE}/{BLAXEL_WORKSPACE}/global-inference-network/sandbox/{sandbox_name}"
        )

        return LiveSandbox(
            id=sandbox_name,
            iteration=0,
            blast_radius=blast_radius,
            preview_url=preview_url,
            dashboard_url=dashboard_url,
            sandbox_name=sandbox_name,
            region=region,
            bl_status=str(sb.status or ""),
        )
