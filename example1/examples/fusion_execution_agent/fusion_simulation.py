from __future__ import annotations

import json
import math
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

import numpy as np


@dataclass(frozen=True)
class ScanConfig:
    # Geometry
    R_m: float = 3.0
    a_m: float = 1.0
    kappa: float = 1.7

    # Scan ranges
    T_keV_values: Tuple[float, ...] = tuple(np.linspace(5.0, 25.0, 21))
    n20_values: Tuple[float, ...] = tuple(np.linspace(0.3, 2.0, 18))
    tau_E_values: Tuple[float, ...] = tuple(np.linspace(0.5, 3.0, 12))

    # Fixed parameters
    f_He: float = 0.03
    Zeff: float = 2.0
    T_ratio_e_to_i: float = 1.0

    # Selection / reporting
    top_k: int = 10


def _require_finite(name: str, value: float) -> float:
    """Validate a float is finite and return it.

    Error strategy: raise ValueError with a clear message.
    """

    if not isinstance(value, (int, float, np.floating)):
        raise ValueError(f"{name} must be a number, got {type(value)}")
    value_f = float(value)
    if not math.isfinite(value_f):
        raise ValueError(f"{name} must be finite, got {value_f}")
    return value_f


def _require_positive(name: str, value: float) -> float:
    value_f = _require_finite(name, value)
    if value_f <= 0:
        raise ValueError(f"{name} must be > 0, got {value_f}")
    return value_f


def _require_nonnegative(name: str, value: float) -> float:
    value_f = _require_finite(name, value)
    if value_f < 0:
        raise ValueError(f"{name} must be >= 0, got {value_f}")
    return value_f


def _torus_volume_m3(R_m: float, a_m: float, kappa: float) -> float:
    R_m = _require_positive("R_m", R_m)
    a_m = _require_positive("a_m", a_m)
    kappa = _require_positive("kappa", kappa)
    return 2.0 * math.pi**2 * R_m * a_m**2 * kappa


def _reactivity_dt_m3_per_s(T_keV: float) -> float:
    """Smooth toy approximation for <σv> for D–T.

    Not physics-grade. Designed for a peaked curve around ~14 keV.

    Returns:
      <σv> in m^3/s.
    """

    T_keV = _require_positive("T_keV", T_keV)

    # Peak-like behavior: rises ~T^2 at low T, then decays gently at high T.
    return 1e-24 * (T_keV**2) * math.exp(-T_keV / 14.0)


def simulate_point(
    *,
    T_keV: float,
    n20: float,
    tau_E_s: float,
    R_m: float,
    a_m: float,
    kappa: float,
    f_He: float,
    Zeff: float,
    T_ratio_e_to_i: float,
) -> Dict[str, Any]:
    """Compute derived quantities for a single operating point.

    This is a *toy* D–T tokamak steady-state power balance model.

    Error strategy: raise ValueError for invalid/unphysical inputs.
    """

    T_keV = _require_positive("T_keV", T_keV)
    n20 = _require_positive("n20", n20)
    tau_E_s = _require_positive("tau_E_s", tau_E_s)

    # Geometry inputs are validated in _torus_volume_m3, but validate here too
    # since this function can be used independently.
    _require_positive("R_m", R_m)
    _require_positive("a_m", a_m)
    _require_positive("kappa", kappa)

    f_He = _require_nonnegative("f_He", f_He)
    if f_He >= 0.5:
        raise ValueError(f"f_He must be < 0.5 for this toy model, got {f_He}")

    Zeff = _require_positive("Zeff", Zeff)
    if Zeff > 10:
        raise ValueError(f"Zeff unusually large for this toy model, got {Zeff}")

    T_ratio_e_to_i = _require_positive("T_ratio_e_to_i", T_ratio_e_to_i)

    # D–T mixture: assume equal D and T, diluted by helium ash fraction f_He.
    n_m3 = n20 * 1e20
    n_fuel = n_m3 * (1.0 - f_He)
    nD = 0.5 * n_fuel
    nT = 0.5 * n_fuel

    reactivity = _reactivity_dt_m3_per_s(T_keV)

    # Reaction rate density (reactions / m^3 / s)
    R_dt = nD * nT * reactivity

    # Energies
    eV_to_J = 1.602176634e-19
    E_fus_J = 17.6e6 * eV_to_J
    E_alpha_J = 3.5e6 * eV_to_J

    P_fus_W_m3 = R_dt * E_fus_J
    P_alpha_W_m3 = R_dt * E_alpha_J

    # Toy bremsstrahlung scaling: ~ C * Zeff * n^2 * sqrt(T_e)
    # (arbitrary coefficient tuned for reasonable magnitudes in this toy model)
    T_e_keV = T_keV * T_ratio_e_to_i
    P_brem_W_m3 = 5e-38 * Zeff * (n_m3**2) * math.sqrt(T_e_keV)

    # Thermal energy density ~ (3/2) n k_B (T_i + T_e).
    kB = 1.380649e-23
    keV_to_K = 1e3 * 11604.51812
    T_i_K = T_keV * keV_to_K
    T_e_K = T_e_keV * keV_to_K
    Wth_J_m3 = 1.5 * n_m3 * kB * (T_i_K + T_e_K)

    P_transport_W_m3 = Wth_J_m3 / tau_E_s

    P_loss_W_m3 = P_brem_W_m3 + P_transport_W_m3
    P_net_W_m3 = P_alpha_W_m3 - P_loss_W_m3

    ignition_margin = P_alpha_W_m3 / max(P_loss_W_m3, 1e-30)

    return {
        "inputs": {
            "T_keV": float(T_keV),
            "n20": float(n20),
            "tau_E_s": float(tau_E_s),
            "geometry": {"R_m": float(R_m), "a_m": float(a_m), "kappa": float(kappa)},
            "assumptions": {
                "f_He": float(f_He),
                "Zeff": float(Zeff),
                "T_ratio_e_to_i": float(T_ratio_e_to_i),
            },
        },
        "derived": {
            "reactivity_m3_s": float(reactivity),
            "R_dt_m3_s": float(R_dt),
            "P_fus_W_m3": float(P_fus_W_m3),
            "P_alpha_W_m3": float(P_alpha_W_m3),
            "P_brem_W_m3": float(P_brem_W_m3),
            "P_transport_W_m3": float(P_transport_W_m3),
            "P_loss_W_m3": float(P_loss_W_m3),
            "P_net_W_m3": float(P_net_W_m3),
            "ignition_margin": float(ignition_margin),
            "Wth_J_m3": float(Wth_J_m3),
        },
    }


def make_grid(cfg: ScanConfig) -> List[Tuple[float, float, float]]:
    grid: List[Tuple[float, float, float]] = []
    for T in cfg.T_keV_values:
        for n20 in cfg.n20_values:
            for tau in cfg.tau_E_values:
                grid.append((float(T), float(n20), float(tau)))
    return grid


def _score(point: Dict[str, Any]) -> float:
    # Prefer high ignition margin; mild penalty for very low net power.
    ign = point["derived"]["ignition_margin"]
    pnet = point["derived"]["P_net_W_m3"]
    return float(ign + 1e-20 * pnet)


def run_scan(cfg: ScanConfig | None = None) -> Dict[str, Any]:
    """Run the full scan and return a JSON-serializable summary.

    NOTE: This function is intentionally pure + deterministic.
    Rich output / progress is handled by the ExecutionAgent script.
    """

    cfg = cfg or ScanConfig()
    V_m3 = _torus_volume_m3(cfg.R_m, cfg.a_m, cfg.kappa)
    grid = make_grid(cfg)

    results: List[Dict[str, Any]] = []
    for (T, n20, tau) in grid:
        results.append(
            simulate_point(
                T_keV=T,
                n20=n20,
                tau_E_s=tau,
                R_m=cfg.R_m,
                a_m=cfg.a_m,
                kappa=cfg.kappa,
                f_He=cfg.f_He,
                Zeff=cfg.Zeff,
                T_ratio_e_to_i=cfg.T_ratio_e_to_i,
            )
        )

    # Sort by score descending
    scored = sorted((( _score(p), p) for p in results), key=lambda x: x[0], reverse=True)
    top = [p for _, p in scored[: cfg.top_k]]
    best = top[0]

    # Add a couple of integral/total powers using volume
    for p in top:
        d = p["derived"]
        d["P_fus_W"] = float(d["P_fus_W_m3"] * V_m3)
        d["P_alpha_W"] = float(d["P_alpha_W_m3"] * V_m3)
        d["P_loss_W"] = float(d["P_loss_W_m3"] * V_m3)
        d["P_net_W"] = float(d["P_net_W_m3"] * V_m3)

    summary: Dict[str, Any] = {
        "metadata": {
            "title": "Toy D–T Fusion Performance Explorer",
            "deterministic": True,
            "grid_points": int(len(grid)),
        },
        "units": {
            "T_keV": "keV",
            "n20": "1e20 m^-3",
            "tau_E_s": "s",
            "P_*_W_m3": "W/m^3",
            "P_*_W": "W",
        },
        "config": asdict(cfg) | {"torus_volume_m3": float(V_m3)},
        "best": best,
        "top_candidates": top,
    }
    return summary


def write_summary_json(summary: Dict[str, Any], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2, sort_keys=True))
    return path
