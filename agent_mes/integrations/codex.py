"""Codex builder — async generator that streams a recorded asciinema cast.

The Build stage uses this in REPLAY mode for the live demo (no real Codex
calls during the pitch — too slow + flaky). The hand-crafted .cast file at
recordings/codex_build_run.cast ships with the repo as a deterministic
fallback. A real H7 run would replace it with a captured live session.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, AsyncIterator


class CodexReplayBuilder:
    """Implements CodexBuilderProtocol — streams a .cast file at scaled speed."""

    def __init__(
        self,
        cast_path: Path | str = Path("recordings/codex_build_run.cast"),
        speed: float = 8.0,
    ) -> None:
        self.cast_path = Path(cast_path)
        self.speed = speed

    async def build(self, task: Any) -> AsyncIterator[str]:
        """Async generator yielding output lines from the cast at scaled timing.

        The first line of an asciinema v2 cast is the header (a JSON object),
        followed by event lines of the form `[timestamp, "o", "text"]`.
        """
        if not self.cast_path.exists():
            yield f"[CodexReplayBuilder] cast file not found: {self.cast_path}\n"
            return

        prev_ts = 0.0
        with self.cast_path.open() as f:
            for line_no, raw_line in enumerate(f):
                raw_line = raw_line.strip()
                if not raw_line:
                    continue

                # First non-empty line is the header — skip it
                if line_no == 0:
                    try:
                        header = json.loads(raw_line)
                        if isinstance(header, dict) and "version" in header:
                            continue
                    except json.JSONDecodeError:
                        pass

                try:
                    event = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue

                if not isinstance(event, list) or len(event) < 3:
                    continue

                ts, kind, text = event[0], event[1], event[2]
                if kind != "o":
                    continue

                # Sleep the scaled delta so the playback feels live
                delta = max(0.0, (float(ts) - prev_ts) / self.speed)
                if delta > 0:
                    await asyncio.sleep(delta)
                prev_ts = float(ts)

                yield text
