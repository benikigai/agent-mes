"""AgentMES CLI — `agent-mes demo` runs the full pipeline with both fixture tickets."""

from __future__ import annotations

import asyncio

import typer

from agent_mes.demo.fake_slack import FAKE_SLACK
from agent_mes.integrations.codex import CodexReplayBuilder
from agent_mes.integrations.stubs.blaxel import StubBlaxelVerifier
from agent_mes.integrations.stubs.context_retriever import StubContextRetriever
from agent_mes.integrations.stubs.redis_memory import StubRedisMemory
from agent_mes.integrations.wordware import WordwarePlanner
from agent_mes.pipeline import Pipeline
from agent_mes.schema import MESTask, TicketType
from agent_mes.stages.build import BuildStage
from agent_mes.stages.deploy import DeployStage
from agent_mes.stages.design import DesignStage
from agent_mes.stages.document import DocumentStage
from agent_mes.stages.plan import PlanStage
from agent_mes.stages.review import ReviewStage
from agent_mes.stages.test import TestStage
from agent_mes.ui.dashboard import Dashboard

app = typer.Typer(no_args_is_help=True, help="AgentMES — autonomous agent MES with terminal kanban")


_SIMPLE_HINTS = ("draft", "postmortem", "email", "summary", "report", "send", "notify")


def _pre_classify(raw_text: str) -> TicketType:
    """Pre-classify the ticket so the initial card shows the right icon
    BEFORE Plan stage runs. PlanStage re-classifies idempotently.
    """
    text_lower = raw_text.lower()
    if any(k in text_lower for k in _SIMPLE_HINTS):
        return TicketType.SIMPLE
    return TicketType.CODE


def _new_task(ticket_id: str) -> MESTask:
    f = FAKE_SLACK[ticket_id]
    return MESTask(
        id=ticket_id,
        type=_pre_classify(f["raw_text"]),
        intent="",
        raw_input=f["raw_text"],
        requester=f["requester"],
        source=f["channel"],
    )


def _build_pipeline(speed: float, dry_run: bool) -> Pipeline:
    redis = StubRedisMemory()
    context = StubContextRetriever()
    blaxel = StubBlaxelVerifier()
    return Pipeline(
        plan=PlanStage(wordware=WordwarePlanner(mode="stub")),
        design=DesignStage(redis=redis, context=context),
        build=BuildStage(codex=CodexReplayBuilder(speed=speed)),
        test=TestStage(blaxel=blaxel),
        review=ReviewStage(redis=redis, context=context),
        document=DocumentStage(redis=redis),
        deploy=DeployStage(redis=redis, dry_run=dry_run),
    )


@app.command()
def version() -> None:
    """Print the AgentMES version."""
    from agent_mes import __version__
    typer.echo(f"agent-mes {__version__}")


@app.command()
def web(
    host: str = typer.Option("0.0.0.0", "--host", help="Bind address (0.0.0.0 for Tailnet)"),
    port: int = typer.Option(8000, "--port", help="Port to bind"),
) -> None:
    """Boot the AgentMES live web kanban — alternative to the terminal demo.

    URLs:
      http://localhost:8000          (local browser on the Mini)
      http://100.85.105.99:8000      (MBP via Tailscale)
    """
    import uvicorn

    typer.echo("\n  AgentMES live kanban\n")
    typer.echo(f"  → http://localhost:{port}")
    typer.echo(f"  → http://100.85.105.99:{port}   (Tailscale)")
    typer.echo("\n  Press Ctrl+C to stop.\n")
    uvicorn.run(
        "agent_mes.web.server:app",
        host=host,
        port=port,
        log_level="info",
    )


@app.command()
def demo(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Don't actually open GitHub PRs (rehearsal mode)"
    ),
    speed: float = typer.Option(
        8.0, "--speed", help="Codex replay playback speed multiplier"
    ),
    real_redis: bool = typer.Option(
        False, "--real-redis", help="Swap stub Redis for Vish's real impl (placeholder)"
    ),
) -> None:
    """Run the AgentMES demo pipeline with TKT-001 (CODE) and TKT-002 (SIMPLE)."""
    if real_redis:
        typer.echo("--real-redis: vish/redis-blaxel branch not yet merged, falling back to stub")

    tasks = [_new_task("TKT-001"), _new_task("TKT-002")]
    pipeline = _build_pipeline(speed=speed, dry_run=dry_run)
    dashboard = Dashboard(tasks=tasks)

    asyncio.run(dashboard.run(pipeline))


if __name__ == "__main__":
    app()
