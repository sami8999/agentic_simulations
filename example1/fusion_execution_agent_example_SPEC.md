# Fusion ExecutionAgent Example — Spec (Toy Model + Contracts)

This document locks the *scenario*, *equations*, *constraints*, and *I/O/tool contracts* for a new URSA `ExecutionAgent` example.

The goal is a deterministic, fast, “fusion-like” simulation/optimization workflow that the agent can implement and run end-to-end.

---

## Scenario

**Title:** *Toy D-T Fusion “Performance Explorer”*

We simulate a simplified deuterium–tritium (D–T) plasma core and compute:

- Fusion power density and total fusion power
- Alpha heating power
- Bremsstrahlung radiation loss
- A crude conduction/transport loss
- Net power balance and a simple ignition margin

We then scan a bounded parameter space to find a point with **positive net heating** under “engineering-like” constraints.

This is not tokamak-realistic; it is intentionally a plausible **toy** with explicit equations and units.

---

## Deterministic Toy Model

### Inputs (design variables)
All variables are scalars.

| Symbol | Meaning | Units | Range |
|---|---|---:|---:|
| `T_keV` | ion/electron temperature | keV | [5, 30] |
| `n20` | density in 1e20 m^-3 | 1 | [0.2, 3.0] |
| `B_T` | toroidal magnetic field | T | [2, 10] |
| `a_m` | minor radius | m | [0.5, 3.0] |
| `R_m` | major radius | m | [1.5, 10.0] |
| `tauE_s` | energy confinement time | s | [0.1, 5.0] |
| `f_He` | helium ash fraction (dilution) | 1 | [0.0, 0.2] |

### Fixed constants

- `E_fus_MeV = 17.6` (total D–T fusion energy per reaction)
- `E_alpha_MeV = 3.5` (alpha heating energy per reaction)
- `MeV_to_J = 1.602176634e-13`

Plasma geometry:

- Plasma volume (simple torus):
  - `V = 2 * pi**2 * R_m * a_m**2`  [m^3]

Effective charge and species:

- For toy brem: `Z_eff = 1.5`

### Core formulas

#### 1) Convert density

- `n = n20 * 1e20` [m^-3]

#### 2) Dilution by helium ash

Assume 50/50 D/T fuel ions, reduced by ash fraction:

- `n_fuel = n * (1 - f_He)`
- `n_D = n_T = 0.5 * n_fuel`

Assume quasi-neutral electrons roughly track ions (toy):

- `n_e = n` (keep simple; dilution affects fusion via `n_D*n_T`)

#### 3) D–T reactivity approximation

Use a smooth, deterministic, bounded function of temperature (keV) that peaks ~15–20 keV:

- `theta = T_keV / 15.0`
- `sigma_v = 1e-22 * (theta**2) * exp(-1/theta)`  [m^3/s]

This is *not* a real fit; it is a convenient bell-shaped curve.

#### 4) Fusion reaction rate density

- `R_fus = n_D * n_T * sigma_v`  [1/(m^3 s)]

#### 5) Fusion power density and total power

- `P_fus_density = R_fus * E_fus_MeV * MeV_to_J`  [W/m^3]
- `P_fus = P_fus_density * V`  [W]

#### 6) Alpha heating

- `P_alpha = (E_alpha_MeV / E_fus_MeV) * P_fus`  [W]

#### 7) Bremsstrahlung (toy)

Use a common scaling-like form (not rigorous):

- `P_brem_density = C_brem * Z_eff * (n_e/1e20)**2 * sqrt(T_keV)`  [MW/m^3]

Choose `C_brem = 0.2` so that values are in a reasonable toy range.

Convert to W/m^3:

- `P_brem_density_W = P_brem_density * 1e6`
- `P_brem = P_brem_density_W * V`  [W]

#### 8) Transport / conduction loss (toy)

Assume thermal energy content is proportional to `n*T` and is lost over `tauE_s`.

Let thermal energy density:

- `W_th_density = 3 * n * (T_keV * 1e3 * eV_to_J)`  [J/m^3]

Where `eV_to_J = 1.602176634e-19`.

Total thermal energy:

- `W_th = W_th_density * V`  [J]

Transport loss power:

- `P_loss = W_th / tauE_s`  [W]

#### 9) Simple pressure and beta constraint

Toy pressure:

- `p = 2 * n * (T_keV * 1e3 * eV_to_J)`  [Pa]

Magnetic pressure:

- `p_mag = B_T**2 / (2 * mu0)`  [Pa]

Beta:

- `beta = p / p_mag`  [1]

Hard constraint:

- `beta <= 0.06` (6%)

#### 10) Net heating and ignition metric

Net heating:

- `P_net = P_alpha - P_brem - P_loss`  [W]

Ignition margin (dimensionless):

- `M_ign = P_alpha / (P_brem + P_loss + 1e-30)`

We target `P_net > 0` and/or `M_ign > 1`.

---

## Hard Constraints (must be enforced)

1. **Determinism**
   - No randomness.
   - If any pseudo-random search is used, it must be seeded and produce identical results run-to-run.

2. **Runtime**
   - Typical run should finish in **< 10 seconds** on a laptop.
   - Use coarse grid search or a small bounded scan.

3. **Dependencies**
   - Pure Python standard library + `numpy` allowed.
   - Prefer minimal dependencies; do *not* install packages.

4. **Safety / Resource**
   - No file downloads unless explicitly justified.
   - No huge memory allocations.

5. **Output format**
   - Must produce:
     1) a **JSON summary file** with a fixed schema (see below)
     2) a **Rich** console report with tables/panels and clear progress logging.

---

## Fixed Outputs (file contracts)

### 1) `outputs/fusion_summary.json`

**Type:** JSON object

```json
{
  "metadata": {
    "model_name": "string",
    "timestamp_utc": "YYYY-MM-DDTHH:MM:SSZ",
    "deterministic": true,
    "runtime_s": 0.0
  },
  "best_point": {
    "inputs": {
      "T_keV": 0.0,
      "n20": 0.0,
      "B_T": 0.0,
      "a_m": 0.0,
      "R_m": 0.0,
      "tauE_s": 0.0,
      "f_He": 0.0
    },
    "derived": {
      "V_m3": 0.0,
      "sigma_v_m3_s": 0.0,
      "beta": 0.0,
      "P_fus_W": 0.0,
      "P_alpha_W": 0.0,
      "P_brem_W": 0.0,
      "P_loss_W": 0.0,
      "P_net_W": 0.0,
      "M_ign": 0.0
    },
    "constraints": {
      "beta_ok": true,
      "within_bounds": true
    }
  },
  "top_candidates": [
    {
      "rank": 1,
      "inputs": {"T_keV": 0.0, "n20": 0.0, "B_T": 0.0, "a_m": 0.0, "R_m": 0.0, "tauE_s": 0.0, "f_He": 0.0},
      "P_net_W": 0.0,
      "M_ign": 0.0,
      "beta": 0.0
    }
  ],
  "scan": {
    "grid": {
      "T_keV": [5, 10],
      "n20": [0.2, 0.5],
      "B_T": [2, 5],
      "a_m": [1.0],
      "R_m": [3.0],
      "tauE_s": [0.5, 1.0],
      "f_He": [0.0, 0.1]
    },
    "evaluated_points": 0,
    "feasible_points": 0
  },
  "units": {
    "T_keV": "keV",
    "n20": "1e20 m^-3",
    "B_T": "T",
    "a_m": "m",
    "R_m": "m",
    "tauE_s": "s",
    "P_*": "W"
  }
}
```

**Rules**
- All numeric fields must be JSON numbers.
- `top_candidates` must include at least 5 entries if feasible points exist; otherwise it may be empty.
- `within_bounds` must reflect the declared variable ranges.

### 2) `outputs/fusion_report.txt`

Plain text capture of the run (stdout) is optional, but recommended.

---

## Tool / Function Contracts (for implementation)

These are internal function contracts that the agent must implement. They are not LangChain tools; they are plain Python functions within the example code.

### `simulate_point(inputs: dict) -> dict`

**Input keys:** `T_keV, n20, B_T, a_m, R_m, tauE_s, f_He`

**Return dict:**

```json
{
  "inputs": {"T_keV": 0.0, "n20": 0.0, "B_T": 0.0, "a_m": 0.0, "R_m": 0.0, "tauE_s": 0.0, "f_He": 0.0},
  "derived": {
    "V_m3": 0.0,
    "sigma_v_m3_s": 0.0,
    "beta": 0.0,
    "P_fus_W": 0.0,
    "P_alpha_W": 0.0,
    "P_brem_W": 0.0,
    "P_loss_W": 0.0,
    "P_net_W": 0.0,
    "M_ign": 0.0
  },
  "constraints": {"beta_ok": true, "within_bounds": true}
}
```

**Error schema**
- Never raise for typical numeric inputs; clamp/validate.
- If NaN/Inf occurs, return `P_net_W = -inf`, `M_ign=0`, `constraints.beta_ok=false` and add an optional string field `error`.

### `make_grid() -> dict[str, list[float]]`

Returns the scan grid used. Must match `scan.grid` in the JSON summary.

### `run_scan(grid: dict[str, list[float]]) -> dict`

Evaluates every combination deterministically in sorted key order.

Returns:

```json
{
  "results": [ ...simulate_point outputs... ],
  "evaluated_points": 0,
  "feasible_points": 0
}
```

Feasible means `constraints.beta_ok && constraints.within_bounds`.

### `select_best(results: list[dict]) -> dict`

Select the best feasible point by:

1) highest `P_net_W`
2) tie-breaker: highest `M_ign`
3) tie-breaker: lowest `beta`

If no feasible points, select the overall best by `M_ign` (still record constraints).

---

## Rich Console Requirements

The final example run must show:

- A banner panel describing the scenario
- A progress indicator while scanning (coarse updates are OK)
- A table of top candidates (rank, T, n20, B, tauE, beta, P_net, M_ign)
- A final panel summarizing the chosen best point and whether it is “ignited” (`M_ign > 1`)

---

## Suggested Scan Grid (fits <10s)

Default (example):

- `T_keV`: [8, 10, 12, 15, 18, 22]
- `n20`: [0.3, 0.6, 1.0, 1.5, 2.0]
- `B_T`: [3, 5, 7, 9]
- `a_m`: [1.0, 1.5]
- `R_m`: [3.0, 5.0]
- `tauE_s`: [0.3, 0.6, 1.0, 1.6]
- `f_He`: [0.0, 0.05, 0.1]

Total points: 6*5*4*2*2*4*3 = 5760 (fast in numpy/pure python).

---

## Acceptance Criteria

- Example runs to completion without user input.
- Produces `outputs/fusion_summary.json` matching schema.
- Uses Rich for visible, meaningful progress and tables.
- Deterministic: two runs produce identical `best_point.inputs`.
