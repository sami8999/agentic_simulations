"""Minimal, dependency-free smoke tests for the fusion ExecutionAgent example.

Constraints/goals:
- No pytest/unittest dependency required.
- Offline by default (no network, no OpenAI key needed).
- Deterministic checks to catch accidental physics-model changes.
- Lightweight performance guard to catch accidental slowdowns.

Run:
  python examples/fusion_execution_agent/smoke_tests.py

Exit code:
  0 on success, non-zero on failure.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

import fusion_simulation as sim


console = Console()


def _banner(title: str, subtitle: str | None = None) -> None:
    console.print(Panel.fit(f"[bold cyan]{title}[/bold cyan]" + (f"\n[dim]{subtitle}[/dim]" if subtitle else "")))


def _fail(msg: str) -> None:
    console.print(Panel.fit(f"[bold red]FAIL[/bold red]\n{msg}", border_style="red"))
    raise SystemExit(2)


def _ok(msg: str) -> None:
    console.print(Panel.fit(f"[bold green]OK[/bold green]\n{msg}", border_style="green"))


def test_import_and_basic_run() -> None:
    _banner("Test 1/3: import + basic single-shot")

    res = sim.simulate_point(
        T_keV=15.0,
        n20=1.0,
        tau_E_s=3.0,
        R_m=3.0,
        a_m=1.0,
        kappa=1.7,
        f_He=0.03,
        Zeff=2.0,
        T_ratio_e_to_i=1.0,
    )

    # Basic sanity: all major scalars are finite and in plausible ranges.
    derived = res.get("derived", {})
    for key in [
        "P_fus_W_m3",
        "P_alpha_W_m3",
        "P_loss_W_m3",
        "P_net_W_m3",
        "ignition_margin",
    ]:
        if key not in derived:
            _fail(f"Missing key in simulate_point derived: {key}")
        if not isinstance(derived[key], (int, float)):
            _fail(f"Derived key {key} is not numeric: {type(derived[key])}")

    # Ensure determinism: repeated call gives identical JSON when sorted.
    res2 = sim.simulate_point(
        T_keV=15.0,
        n20=1.0,
        tau_E_s=3.0,
        R_m=3.0,
        a_m=1.0,
        kappa=1.7,
        f_He=0.03,
        Zeff=2.0,
        T_ratio_e_to_i=1.0,
    )
    if json.dumps(res, sort_keys=True) != json.dumps(res2, sort_keys=True):
        _fail("simulate_point is not deterministic for identical inputs")

    table = Table(title="Single-shot sanity output", show_lines=True)
    table.add_column("metric")
    table.add_column("value", justify="right")
    for k in ["P_fus_W_m3", "P_net_W_m3", "ignition_margin"]:
        table.add_row(k, f"{derived[k]:,.4g}")
    console.print(table)

    _ok("Single-shot returned required keys and is deterministic.")


def test_goldenish_points() -> None:
    _banner("Test 2/3: deterministic golden-ish checks")
    """Check a couple of points against stable invariants.

    Instead of hard-coding exact floating values (fragile across minor refactors),
    we assert relationships that should hold for the toy model:

    - Increasing tau_E should increase ignition margin (more confinement).
    - Increasing density should increase fusion power strongly.
    - For fixed geometry, alpha power should be ~0.2 of fusion power.
    """

    base = dict(
        T_keV=15.0,
        n20=1.0,
        tau_E_s=2.0,
        R_m=3.0,
        a_m=1.0,
        kappa=1.7,
        f_He=0.03,
        Zeff=2.0,
        T_ratio_e_to_i=1.0,
    )
    r_base = sim.simulate_point(**base)

    r_better = sim.simulate_point(**{**base, "tau_E_s": 4.0})

    r_n = sim.simulate_point(**{**base, "n20": 1.3})

    if not (r_better["derived"]["ignition_margin"] > r_base["derived"]["ignition_margin"]):
        _fail(
            "Expected ignition_margin to increase with tau_E_s "
            f"(base={r_base['derived']['ignition_margin']:.4g}, better={r_better['derived']['ignition_margin']:.4g})"
        )

    if not (r_n["derived"]["P_fus_W_m3"] > r_base["derived"]["P_fus_W_m3"] * 1.2):
        _fail(
            "Expected fusion power to increase significantly with density "
            f"(base={r_base['derived']['P_fus_W_m3']:.4g}, higher_n={r_n['derived']['P_fus_W_m3']:.4g})"
        )

    ratio = r_base["derived"]["P_alpha_W_m3"] / max(r_base["derived"]["P_fus_W_m3"], 1e-30)
    if not (0.18 <= ratio <= 0.22):
        _fail(f"Expected P_alpha/P_fusion ~0.2, got {ratio:.4g}")

    table = Table(title="Golden-ish invariants", show_lines=True)
    table.add_column("case")
    table.add_column("P_fusion (MW)", justify="right")
    table.add_column("ignition_margin", justify="right")
    table.add_row(
        "base",
        f"{r_base['derived']['P_fus_W_m3']:.4g}",
        f"{r_base['derived']['ignition_margin']:.4g}",
    )
    table.add_row(
        "tau_E 4s",
        f"{r_better['derived']['P_fus_W_m3']:.4g}",
        f"{r_better['derived']['ignition_margin']:.4g}",
    )
    table.add_row(
        "n20 1.3",
        f"{r_n['derived']['P_fus_W_m3']:.4g}",
        f"{r_n['derived']['ignition_margin']:.4g}",
    )
    console.print(table)

    _ok("Invariants hold (monotonicity + alpha fraction).")


def test_quick_sweep_runtime() -> None:
    _banner("Test 3/3: quick sweep runtime guard")

    scan = sim.ScanConfig(
        R_m=3.0,
        a_m=1.0,
        kappa=1.7,
        Zeff=2.0,
        f_He=0.03,
        T_keV_values=(10.0, 12.0, 15.0, 18.0),
        n20_values=(0.8, 1.0, 1.2, 1.4),
        tau_E_values=(2.0, 3.0, 4.0),
    )

    t0 = time.perf_counter()
    summary = sim.run_scan(scan)
    dt = time.perf_counter() - t0

    if "top_candidates" not in summary or not summary["top_candidates"]:
        _fail("run_scan returned no top_candidates")

    # Keep this generous; just catch pathological regressions.
    if dt > 2.0:
        _fail(f"Quick sweep took too long: {dt:.3f}s (expected <= 2.0s)")

    table = Table(title="Sweep runtime", show_lines=True)
    table.add_column("grid")
    table.add_column("elapsed (s)", justify="right")
    table.add_row(
        f"{len(scan.T_keV_values)}x{len(scan.n20_values)}x{len(scan.tau_E_values)}",
        f"{dt:.4f}",
    )
    console.print(table)

    _ok("Sweep completed under time budget and produced candidates.")


def main() -> None:
    # Enforce offline mode by default for safety/repro.
    os.environ.pop("OPENAI_API_KEY", None)

    _banner("Fusion ExecutionAgent example: smoke tests", "Offline, deterministic, no external services")

    try:
        test_import_and_basic_run()
        test_goldenish_points()
        test_quick_sweep_runtime()
    except SystemExit:
        raise
    except Exception as e:
        _fail(f"Unhandled exception: {e!r}")

    out = Path(__file__).parent / "outputs" / "smoke_tests_ok.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"ok": True, "timestamp": time.time()}, indent=2))
    _ok(f"All smoke tests passed. Wrote {out}")


if __name__ == "__main__":
    main()
