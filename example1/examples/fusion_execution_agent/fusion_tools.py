from __future__ import annotations

"""Fusion-specific tools for the URSA ExecutionAgent example.

These tools expose a small, agent-callable API over the deterministic toy
simulation in :mod:`fusion_simulation`.

Design notes
------------
- Tools are *computational only*: no Rich console output here.
- Tools return JSON-serializable dict/list payloads.
- Errors are returned in a structured way instead of raising, so the agent can
  recover and adjust parameters.

URSA tool interface
-------------------
URSA agents accept LangChain tools (BaseTool). We implement them using the
@tool decorator which yields a StructuredTool with an inferred input schema.
"""

from dataclasses import asdict
from typing import Any, Dict, List, Optional, Tuple

from langchain_core.tools import tool

from fusion_simulation import ScanConfig, run_scan, simulate_point


def _ok(payload: Any) -> Dict[str, Any]:
    return {"ok": True, "result": payload}


def _err(message: str, *, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": False, "error": message}
    if details:
        out["details"] = details
    return out


@tool("simulate_shot")
def simulate_shot(params: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate a single steady-state D–T tokamak operating point.

    Parameters
    ----------
    params:
        Dictionary containing the operating point and configuration. Expected keys:
        - n20: float (density in 1e20 m^-3)
        - T_keV: float (ion/electron temperature in keV)
        - B_T: float (toroidal field in Tesla)
        Optional keys:
        - R_m, a_m, kappa, Zeff, f_He, tau_E_s, P_aux_MW

    Returns
    -------
    dict
        {ok: bool, result: {...}} on success, or {ok: False, error: str, details?: {...}}.
    """

    try:
        metrics = simulate_point(**params)
        return _ok(metrics)
    except TypeError as e:
        # Typically missing/extra keys.
        return _err(
            "Invalid parameters for simulate_point (wrong keys or types).",
            details={"exception": str(e), "received_keys": sorted(list(params.keys()))},
        )
    except ValueError as e:
        # Unphysical inputs.
        return _err("Unphysical or invalid input.", details={"exception": str(e)})
    except Exception as e:
        return _err("Unexpected error.", details={"exception": str(e)})


@tool("run_sweep")
def run_sweep(grid_spec: Dict[str, Any]) -> Dict[str, Any]:
    """Run a parameter sweep over (n20, T_keV, tau_E_s).

    This tool is the *agent-friendly* entry point for exploring the toy fusion
    model.

    grid_spec keys
    --------------
    Required axes (3-item lists):
      - n20: [min, max, steps]
      - T_keV: [min, max, steps]
      - tau_E_s: [min, max, steps]

    Optional configuration overrides (scalars):
      - R_m, a_m, kappa, Zeff, f_He, T_ratio_e_to_i
      - top_k: int

    Returns
    -------
    dict
        ok/result wrapper. On success, result contains:
        - config: resolved ScanConfig (JSON friendly)
        - metadata/units/best/top_candidates: from run_scan
    """

    def _parse_axis(name: str) -> Tuple[float, float, int]:
        if name not in grid_spec:
            raise ValueError(f"Missing required axis '{name}'.")
        axis = grid_spec[name]
        if not (isinstance(axis, list) and len(axis) == 3):
            raise ValueError(f"Axis '{name}' must be a 3-item list: [min, max, steps].")
        lo, hi, steps = axis
        return float(lo), float(hi), int(steps)

    def _linspace(lo: float, hi: float, steps: int) -> Tuple[float, ...]:
        if steps <= 0:
            raise ValueError("steps must be >= 1")
        if steps == 1:
            return (float(lo),)
        return tuple(float(x) for x in np.linspace(lo, hi, steps))

    try:
        import numpy as np

        n20_min, n20_max, n20_steps = _parse_axis("n20")
        T_min, T_max, T_steps = _parse_axis("T_keV")
        tau_min, tau_max, tau_steps = _parse_axis("tau_E_s")

        top_k = int(grid_spec.get("top_k", 10))

        cfg = ScanConfig(
            R_m=float(grid_spec.get("R_m", 3.0)),
            a_m=float(grid_spec.get("a_m", 1.0)),
            kappa=float(grid_spec.get("kappa", 1.7)),
            T_keV_values=_linspace(T_min, T_max, T_steps),
            n20_values=_linspace(n20_min, n20_max, n20_steps),
            tau_E_values=_linspace(tau_min, tau_max, tau_steps),
            f_He=float(grid_spec.get("f_He", 0.03)),
            Zeff=float(grid_spec.get("Zeff", 2.0)),
            T_ratio_e_to_i=float(grid_spec.get("T_ratio_e_to_i", 1.0)),
            top_k=top_k,
        )

        summary = run_scan(cfg)
        return _ok(summary)
    except ValueError as e:
        return _err("Invalid sweep specification.", details={"exception": str(e)})
    except Exception as e:
        return _err("Unexpected error.", details={"exception": str(e)})
