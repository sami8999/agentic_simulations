from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from diagnostics import ToolTracer, maybe_print_env_diagnostics, tool_trace_enabled

from fusion_simulation import ScanConfig, run_scan


def _format_float(x: float, fmt: str = ".3g") -> str:
    try:
        return format(float(x), fmt)
    except Exception:
        return str(x)


def run_offline_demo(example_dir: Path) -> Path:
    """Run the fusion scan with no LLM/agent involvement.

    This is a deterministic fallback so the example remains runnable even when
    no API key is present or the user is offline.

    Returns
    -------
    Path
        Path to the written outputs/fusion_summary.json file.
    """

    console = Console()

    maybe_print_env_diagnostics()

    console.print(
        Panel.fit(
            "[bold yellow]Offline mode[/bold yellow]\n"
            "Running a deterministic D–T tokamak parameter sweep (no LLM calls).\n"
            "[dim]Tip: set OPENAI_API_KEY (or URSA_MODEL) to run the full ExecutionAgent demo.[/dim]",
            title="URSA Fusion Example",
            border_style="yellow",
        )
    )

    outputs_dir = example_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    # A moderately sized scan that runs quickly on CPU.
    cfg = ScanConfig(
        R_m=3.0,
        a_m=1.0,
        kappa=1.8,
        T_keV_values=tuple(__import__("numpy").linspace(8.0, 22.0, 13)),
        n20_values=tuple(__import__("numpy").linspace(0.7, 1.4, 13)),
        tau_E_values=tuple(__import__("numpy").linspace(0.6, 1.8, 11)),
        top_k=8,
    )

    console.print(
        Panel.fit(
            "[bold]Scan grid[/bold]\n"
            f"R: {cfg.R_m} m, a: {cfg.a_m} m, κ: {cfg.kappa}\n"
            f"n20 axis: {min(cfg.n20_values):.3g}–{max(cfg.n20_values):.3g} (10^20 m^-3), steps={len(cfg.n20_values)}\n"
            f"T axis: {min(cfg.T_keV_values):.3g}–{max(cfg.T_keV_values):.3g} keV, steps={len(cfg.T_keV_values)}\n"
            f"tau_E axis: {min(cfg.tau_E_values):.3g}–{max(cfg.tau_E_values):.3g} s, steps={len(cfg.tau_E_values)}\n"
            f"total points: {len(cfg.n20_values) * len(cfg.T_keV_values) * len(cfg.tau_E_values)}",
            border_style="cyan",
            title="Configuration",
        )
    )

    console.print("[cyan]Running scan...[/cyan]")

    tracer = ToolTracer(out_dir=outputs_dir)
    scan_fn = tracer.wrap("run_scan", run_scan) if tool_trace_enabled() else run_scan
    result = scan_fn(cfg)

    trace_path = tracer.dump()
    if trace_path is not None:
        console.print(
            Panel.fit(
                f"[bold]Tool trace written:[/bold] {trace_path}",
                title="Diagnostics",
                border_style="magenta",
            )
        )

    top = result["top_candidates"]

    table = Table(title="Top candidates (offline sweep)")
    table.add_column("rank", justify="right")
    table.add_column("n20", justify="right")
    table.add_column("T [keV]", justify="right")
    table.add_column("tau_E [s]", justify="right")
    table.add_column("P_net [MW]", justify="right")
    table.add_column("Ignition margin", justify="right")

    for i, row in enumerate(top, start=1):
        inp = row["inputs"]
        d = row["derived"]
        pnet_mw = d["P_net_W"] / 1e6
        table.add_row(
            str(i),
            _format_float(inp["n20"]),
            _format_float(inp["T_keV"]),
            _format_float(inp["tau_E_s"]),
            _format_float(pnet_mw, ".4g"),
            _format_float(d["ignition_margin"], ".4g"),
        )

    console.print(table)

    summary_path = outputs_dir / "fusion_summary.json"
    summary = {
        "mode": "offline",
        "note": "Deterministic fallback run without any LLM/agent.",
        "result": result,
    }
    summary_path.write_text(json.dumps(summary, indent=2))

    console.print(
        Panel.fit(
            f"[bold green]Wrote:[/bold green] {summary_path}\n"
            "[dim]This file matches the expected output path for the agent version.[/dim]",
            title="Outputs",
            border_style="green",
        )
    )

    return summary_path
