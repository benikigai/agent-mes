"""Tests for CodexReplayBuilder."""

import json
from pathlib import Path

import pytest

from agent_mes.integrations.codex import CodexReplayBuilder


def test_cast_file_is_valid_jsonl():
    cast_path = Path("recordings/codex_build_run.cast")
    assert cast_path.exists()
    lines = [l for l in cast_path.read_text().splitlines() if l.strip()]
    # First line is header
    header = json.loads(lines[0])
    assert header["version"] == 2
    # Remaining lines are event arrays
    for line in lines[1:]:
        event = json.loads(line)
        assert isinstance(event, list)
        assert len(event) == 3
        assert event[1] == "o"
        assert isinstance(event[2], str)


@pytest.mark.asyncio
async def test_replay_yields_output_lines_at_high_speed():
    # speed=1000 makes the test fast (no real waiting)
    builder = CodexReplayBuilder(speed=1000.0)
    lines: list[str] = []
    async for chunk in builder.build(task=None):
        lines.append(chunk)
        if len(lines) >= 5:
            break
    assert len(lines) >= 5
    # All chunks are non-empty strings
    assert all(isinstance(l, str) and l for l in lines)


@pytest.mark.asyncio
async def test_replay_handles_missing_cast_gracefully():
    builder = CodexReplayBuilder(cast_path=Path("recordings/does-not-exist.cast"))
    lines = [chunk async for chunk in builder.build(task=None)]
    assert len(lines) == 1
    assert "not found" in lines[0]
