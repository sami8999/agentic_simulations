"""Lightweight diagnostics helpers for the Fusion ExecutionAgent example.

Goals:
- Provide targeted debugging info when enabled, without spamming normal output.
- Keep this module dependency-light (only stdlib + Rich).

Enable diagnostics by setting environment variables:
- FUSION_EXAMPLE_DEBUG=1
- FUSION_EXAMPLE_TRACE_TOOLS=1

This file lives OUTSIDE ./ursa/ to respect the read-only constraint.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from rich.console import Console
from rich.panel import Panel


console = Console()


def debug_enabled() -> bool:
    return os.getenv("FUSION_EXAMPLE_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def tool_trace_enabled() -> bool:
    return os.getenv("FUSION_EXAMPLE_TRACE_TOOLS", "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, sort_keys=True, default=str)
    except Exception:
        return repr(obj)


@dataclass
class ToolCallTrace:
    name: str
    started_s: float
    ended_s: float
    ok: Optional[bool]
    args: Dict[str, Any]
    result_preview: str


class ToolTracer:
    """Wraps tool callables to record calls + duration.

    Usage:
        tracer = ToolTracer(out_dir=Path('outputs'))
        traced_tool = tracer.wrap('run_sweep', run_sweep)

    When enabled, writes outputs/tool_traces.json at end.
    """

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.traces: list[ToolCallTrace] = []

    def wrap(self, name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            started = time.time()
            ok = None
            result: Any = None
            err: Optional[str] = None
            try:
                result = fn(*args, **kwargs)
                if isinstance(result, dict) and "ok" in result:
                    ok = bool(result.get("ok"))
                return result
            except Exception as e:  # pragma: no cover
                err = f"{type(e).__name__}: {e}"
                raise
            finally:
                ended = time.time()
                preview_obj: Any
                if err is not None:
                    preview_obj = {"exception": err}
                else:
                    preview_obj = result
                preview = _safe_json(preview_obj)
                if len(preview) > 2000:
                    preview = preview[:2000] + "\n... (truncated)"
                self.traces.append(
                    ToolCallTrace(
                        name=name,
                        started_s=started,
                        ended_s=ended,
                        ok=ok,
                        args={"__args__": list(args), **dict(kwargs)},
                        result_preview=preview,
                    )
                )

        return _wrapped

    def dump(self) -> Optional[Path]:
        if not tool_trace_enabled():
            return None
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / "tool_traces.json"
        payload = [
            {
                "name": t.name,
                "duration_s": round(t.ended_s - t.started_s, 6),
                "ok": t.ok,
                "args": t.args,
                "result_preview": t.result_preview,
            }
            for t in self.traces
        ]
        path.write_text(
            json.dumps(payload, indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
        return path


def maybe_print_env_diagnostics() -> None:
    if not debug_enabled():
        return

    interesting = {
        "OPENAI_API_KEY_set": bool(os.getenv("OPENAI_API_KEY")),
        "URSA_MODEL": os.getenv("URSA_MODEL"),
        "FUSION_EXAMPLE_DEBUG": os.getenv("FUSION_EXAMPLE_DEBUG"),
        "FUSION_EXAMPLE_TRACE_TOOLS": os.getenv("FUSION_EXAMPLE_TRACE_TOOLS"),
    }

    console.print(
        Panel.fit(
            _safe_json(interesting),
            title="Diagnostics: environment",
            border_style="cyan",
        )
    )
