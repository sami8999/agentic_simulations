# Config-driven OFT/TokaMaker equilibrium (vacuum) example

This example demonstrates a **configuration-driven** workflow using the **OpenFUSIONToolkit (OFT)** Python API (TokaMaker + meshing utilities).

Key property: the runner script **does not hardcode** the equation/physics parameters or discretization choices. Instead, it reads a single YAML config file and uses it to:

- build a 2D axisymmetric mesh/geometry
- configure a TokaMaker equilibrium object
- apply boundary conditions/targets specified in config
- run a (vacuum) solve
- write standard outputs, including machine-readable `summary.json` and `manifest.json`

> Note: This repository example is currently set up as a **vacuum Grad–Shafranov** solve (no plasma sources). A full converged plasma equilibrium configuration can be added by providing a different config.

---

## Contents

- `run_equilibrium.py` — main runner (config-driven)
- `discretization_config.yaml` — known-good config that runs end-to-end
- `oft_config_validator.py` — JSON-schema validator for config
- `run_new_discretizations.yaml` — prompt file for a downstream agent to create/run additional configs
- `runs/` — output directories (auto-created)

---

## Requirements / environment

Constraints assumed by this example:

- **Do not modify** `./OpenFUSIONToolkit/` or `./ursa/` (treated as read-only)
- OFT is already installed and available on `PYTHONPATH`
- OFT native binaries/shared libraries are already set up (no installation steps here)
- Use only Python packages already available in the provided environment (per `requirements.txt`)

The script captures reproducibility information (Python version/platform, OFT module paths, and best-effort OFT doc version guess) into `summary.json`.

---

## Quickstart

Run the known-good config:

```bash
python run_equilibrium.py --config discretization_config.yaml --force
```

- `--force` overwrites an existing run directory for the same `case.name`.
- Omit `--force` to keep prior results; the runner will create a new run id.

---

## What the example does

With the provided `discretization_config.yaml`, the runner performs a **vacuum** equilibrium solve:

- Equation/model: **Grad–Shafranov vacuum** (no pressure/current profiles)
- Geometry: simple tokamak-like cross-section defined in the config
- Discretization: mesh resolution/order chosen from config
- Boundary condition: fixed boundary poloidal flux `psi` specified by `oft_case.physics.vacuum_bc.psi`

The goal is to provide a robust, configurable template that downstream users/agents can adapt by editing/adding config files.

---

## Outputs and run directory layout

The runner writes outputs under:

```
runs/<case_name>/<run_id>/
```

Common files:

- `run.log` — captured stdout/stderr from the run
- `effective_config.yaml` — the fully-resolved config actually used (after defaults/normalization)
- `mesh.h5` — mesh written by the meshing step
- `summary.json` — **machine-readable** summary (status + settings + reproducibility + best-effort diagnostics)
- `manifest.json` — **machine-readable** listing of output files and run status

### Success/failure signals

- **Success**: `summary.json` contains:
  - `status: "success"`
  - a populated `outputs` section pointing to files created
- **Failure**: `status: "failed"` and `manifest.json` includes `traceback`.

### Interpreting `summary.json`

`summary.json` includes:

- `case_name`, `run_id`
- `status`
- `model` (e.g. `gs_vacuum`)
- `settings` (mesh/discretization/physics/solver blocks from the config)
- `diagnostics` (best-effort; may include `get_stats()` output if supported by the model)
- `reproducibility` (Python/platform/OFT paths, runner git hash if available)

---

## Config keys (high level)

See `discretization_config.yaml` for commented descriptions.

Key blocks:

- `case`: naming/output behavior
- `mesh`: geometry definition + meshing controls
- `oft_case`:
  - `model`: selects which TokaMaker model path to execute (e.g. vacuum GS)
  - `physics`: physical parameters and boundary conditions
  - `solver`: nonlinear/linear solver controls
  - `discretization`: polynomial order / FE settings
  - `outputs`: which files to write (plots disabled by default)

If you add new keys, also update the schema in `oft_config_validator.py`.

---

## Expected runtime / hardware

For the default config (moderate mesh resolution), runtime is typically **seconds to under a minute** on a laptop/CI VM.

Runtime depends strongly on:

- mesh resolution (`mesh.resolution.*`)
- discretization order (`oft_case.discretization.*`)
- solver tolerances/max iterations

---

## Troubleshooting

### 1) Config validation errors

If the script reports unknown keys or missing required keys:

- Check YAML indentation and spelling
- Update your config to match `oft_config_validator.py` schema
- Or update the schema if you intentionally added new capabilities

### 2) Missing mesh / geometry errors

Symptoms:
- runner fails before solve
- meshing library raises an exception

What to check:
- geometry parameters in `mesh.geometry` (e.g. negative radii)
- resolution values must be positive integers

### 3) Solver crashes/segfaults during `vac_solve`

Vacuum solves require a well-defined boundary condition.

- Ensure `oft_case.physics.vacuum_bc.psi` is present.
- The runner passes this to the solver as a per-vertex array to avoid API ambiguity.

### 4) Nonconvergence / NaNs

If you create plasma cases or stricter tolerances, you may hit nonconvergence.

Things to try in the config:

- relax tolerances / increase max iterations
- reduce mesh order/resolution
- ensure profiles/targets are physically consistent

### 5) Output files not produced

Check `manifest.json`:

- `files` lists which outputs were actually written
- `status` and `traceback` indicate why a file was skipped

---

## Creating new discretizations/configs

You can create new YAML configs by copying `discretization_config.yaml` and modifying:

- `mesh.resolution` (coarse/fine)
- `oft_case.discretization` (order)
- `oft_case.solver` (tolerances, iteration limits)

A downstream agent prompt is provided in `run_new_discretizations.yaml`.
