# Config → OpenFUSIONToolkit/TokaMaker mapping

This document is a **concrete mapping artifact** for the planned config-driven equilibrium example.
It enumerates intended config keys and maps them to **specific OpenFUSIONToolkit (OFT) / TokaMaker**
Python API objects and calls.

Notes/assumptions:
- The equilibrium solver is **TokaMaker** (Grad–Shafranov family). Different “equations” below refer to
  different TokaMaker solve modes (e.g., plasma solve vs vacuum solve) and different profile parameterizations.
- Mesh is built via **`OpenFUSIONToolkit.TokaMaker.meshing.gs_Domain`** and then passed to
  **`TokaMaker.setup_mesh(r, lc, reg, ...)`**.
- Region convention used by TokaMaker (from `setup_mesh` docstring):
  - `reg==1`: plasma region
  - `reg==2`: vacuum/air region
  - `reg>=3`: conductors / coils / other non-plasma regions

---

## 1) Runtime / environment

| Config key path | Type | OFT API target | How it’s used | Defaults / notes |
|---|---:|---|---|---|
| `runtime.debug_level` | int | `OpenFUSIONToolkit._core.OFT_env(debug_level=...)` | Create OFT environment | Optional; higher = more verbose |
| `runtime.nthreads` | int | `OFT_env(nthreads=...)` | Parallel threads | Optional |
| `runtime.unique_tempfiles` | bool | `OFT_env(unique_tempfiles=...)` | Avoid filename collisions | Optional |

**Implementation**: `env = OFT_env(debug_level=cfg['runtime'].get('debug_level',0), nthreads=..., unique_tempfiles=...)`

---

## 2) Model / equation selection

| Config key path | Type | OFT API target | How it’s used | Defaults / notes |
|---|---:|---|---|---|
| `model.solver` | str | `OpenFUSIONToolkit.TokaMaker.TokaMaker(env)` | Select solver class | For this example, expect `'tokamaker'` |
| `model.equation` | str | `TokaMaker.solve()` vs `TokaMaker.vac_solve()` | Select solution mode | Proposed values: `'grad_shafranov'` (plasma), `'vacuum'` |
| `model.full_domain` | bool | `TokaMaker.setup(full_domain=...)` | Whether mesh includes private flux region, etc. | Passed straight through |

**Derived/branching behavior**:
- If `model.equation == 'vacuum'`: call `gs.vac_solve()` and ignore plasma profiles/Ip target.
- Else: call `gs.solve()`.

---

## 3) Discretization (FE order) and solver settings

| Config key path | Type | OFT API target | How it’s used | Defaults / notes |
|---|---:|---|---|---|
| `discretization.fe_order` | int | `TokaMaker.setup(order=...)` | FE polynomial order | Typical 1 or 2 |
| `discretization.F0` | float | `TokaMaker.setup(F0=...)` | Toroidal field scale (if used) | Optional; TokaMaker default may exist |
| `solver_settings.*` | mixed | `gs.settings.<name> = value` then `gs.update_settings()` | Nonlinear/linear solver control | Keys depend on `tokamaker_default_settings(env)` |

**Implementation**:
```py
from OpenFUSIONToolkit.TokaMaker import tokamaker_default_settings
...
gs = TokaMaker(env)
gs.settings = tokamaker_default_settings(env)
for k,v in cfg.get('solver_settings',{}).items():
    setattr(gs.settings, k, v)
gs.update_settings()
gs.setup(order=cfg['discretization']['fe_order'], F0=cfg['discretization'].get('F0',0.0), full_domain=cfg['model'].get('full_domain',False))
```

**Notes**:
- `solver_settings` keys must match attributes on the settings object (e.g., `maxits`, `urf`, `nl_tol`).

---

## 4) Geometry → meshing (gs_Domain)

Top-level approach:
1. Create a `gs_Domain()`.
2. Define regions (plasma, vacuum, boundary, conductors) via `add_polygon`, `add_rectangle`, `add_annulus`, etc.
3. Define vacuum/boundary extents if needed.
4. Call `domain.build_mesh(...)` → returns `(r, lc, reg)`.
5. Provide to solver via `gs.setup_mesh(r=r, lc=lc, reg=reg, ...)`.

### 4.1 Domain construction

| Config key path | Type | OFT API target | How it’s used | Defaults / notes |
|---|---:|---|---|---|
| `geometry.domain.json` | str | `gs_Domain(json_filename=...)` | Load domain from JSON | Optional alternative to explicit shapes |
| `geometry.domain.save_json` | str | `domain.save_json(filename)` | Save domain definition | Optional |

### 4.2 Region definitions (shapes)

Each region item contains:
- `name` (str)
- `id` (int) → maps to `reg` values
- `kind` (str) one of `plasma`, `vacuum`, `boundary`, `conductor`
- `shape.type` plus shape parameters
- `mesh.dx` and optional `mesh.dx_curve`

| Config key path | Example | OFT API target | How it’s used | Notes |
|---|---|---|---|---|
| `geometry.regions[].shape.type` | `polygon` | `domain.add_polygon(...)` | Add region geometry | Points must be closed or will be closed by Region logic |
| `geometry.regions[].shape.points` | `[[R,Z],...]` | `add_polygon(name, points, ...)` | Boundary points | Units: meters |
| `geometry.regions[].shape.type` | `rectangle` | `domain.add_rectangle(...)` | Add rectangle | Provide `x1,x2,z1,z2` in meters |
| `geometry.regions[].shape.type` | `annulus` | `domain.add_annulus(...)` | Add annulus | Provide `center`, `r1`, `r2` |
| `geometry.regions[].mesh.dx` | float | Region `dx` | Mesh size target | **Required** for vacuum/boundary if auto boundary is used |
| `geometry.regions[].mesh.dx_curve` | float | Region `dx_curve` | Boundary mesh size | Optional |
| `geometry.regions[].include_in_grid` | bool | `... include_in_grid=...` | Whether region is meshed | Usually True |

**Implementation sketch**:
- For each region entry:
  - call matching `domain.add_*` to create a `Region`.
  - call `domain.define_region(name, reg_id, parent_name)` when needed (for non-root regions).

### 4.3 Automatic boundary (extent/padding)

`gs_Domain.build_mesh()` can require a boundary if vacuum/coil regions exist.

| Config key path | Type | OFT API target | How it’s used | Notes |
|---|---:|---|---|---|
| `geometry.boundary.auto` | bool | `domain.build_mesh(...)` | If true, allow auto boundary | Implement by passing `rextent`, `zextents`, `rpad`, `zpad` |
| `geometry.boundary.rextent` | float | `build_mesh(rextent=...)` | Outer R extent | meters |
| `geometry.boundary.zextents` | `[zmin,zmax]` | `build_mesh(zextents=...)` | Vertical extents | meters |
| `geometry.boundary.rpad` | float | `build_mesh(rpad=...)` | Padding around defined shapes | meters |
| `geometry.boundary.zpad` | float | `build_mesh(zpad=...)` | Padding around defined shapes | meters |

### 4.4 Meshing controls

| Config key path | Type | OFT API target | How it’s used | Notes |
|---|---:|---|---|---|
| `mesh.merge_thresh` | float | `build_mesh(merge_thresh=...)` | Triangle point merge threshold | Default: `1e-4` in OFT |
| `mesh.require_boundary` | bool | `build_mesh(require_boundary=...)` | Enforce boundary rules | Default True |
| `mesh.quality_limit` | float | `build_mesh(quality_limit=...)` | Triangle quality filter | Default 25.0 |
| `mesh.verbose` | int | `build_mesh(verbose=...)` | Triangle verbosity | Default 0 |

### 4.5 Pass mesh to solver

| Config key path | Type | OFT API target | How it’s used | Notes |
|---|---:|---|---|---|
| `mesh.setup_mesh.plasma_region_id` | int | `TokaMaker.setup_mesh(reg=...)` | Region tagging | Implement by ensuring reg array uses 1 for plasma |
| `mesh.setup_mesh.vacuum_region_id` | int | `setup_mesh(reg=...)` | Region tagging | Use 2 for vacuum |
| `mesh.setup_mesh.conductor_region_ids` | list[int] | `setup_mesh(reg=...)` | Coils/conductors | 3+ |

**Important**: `setup_mesh` receives the **final per-triangle region ID array** `reg`.
So config region IDs must map to correct TokaMaker expectations.

---

## 5) Plasma profiles (FF′ and P′)

TokaMaker expects profiles as sampled arrays in normalized flux (0..1).

| Config key path | Type | OFT API target | How it’s used | Notes |
|---|---:|---|---|---|
| `profiles.ffprime.x` | list[float] | `gs.set_profiles(ffp_prof={'x':x,'y':y}, ...)` | Sample locations | `x` in [0,1] |
| `profiles.ffprime.y` | list[float] | `set_profiles(...)` | FF′ values | Units consistent with GS solver conventions |
| `profiles.pprime.x` | list[float] | `gs.set_profiles(pp_prof=...)` | Sample locations | `x` in [0,1] |
| `profiles.pprime.y` | list[float] | `set_profiles(...)` | P′ values | |
| `profiles.foffset` | float | `set_profiles(foffset=...)` | Constant F offset | Optional |
| `profiles.ffprime_NI` | dict | `set_profiles(ffp_NI_prof=...)` | Non-inductive FF′ | Optional |
| `profiles.pprime_NI` | dict | `set_profiles(pp_NI_prof=...)` | Non-inductive P′ | Optional |
| `profiles.use_kinetic` | bool | `set_profiles(kin_prof=..., ...)` | Kinetic profiles | Advanced; likely omit |

**Derived checks**:
- Validate `x` monotonic increasing and same length as `y`.
- `x` bounds should be within `[0,1]`; clamp or error.

---

## 6) Targets / constraints

| Config key path | Type | OFT API target | How it’s used | Notes |
|---|---:|---|---|---|
| `targets.Ip` | float | `gs.set_targets(Ip=...)` | Plasma current target | Amps |
| `targets.Ip_ratio` | float | `set_targets(Ip_ratio=...)` | How strongly to enforce | Optional |
| `targets.pax` | float | `set_targets(pax=...)` | On-axis pressure | Optional |
| `targets.estore` | float | `set_targets(estore=...)` | Stored energy | Optional |
| `targets.R0` | float | `set_targets(R0=...)` | Major radius target | Optional |
| `targets.V0` | float | `set_targets(V0=...)` | Volume target | Optional |
| `targets.retain_previous` | bool | `set_targets(..., retain_previous=...)` | Keep prior targets | Optional |

**Notes**:
- Provide only the keys present; the script should pass `None` for absent entries or omit them.

---

## 7) Solve

| Config key path | Type | OFT API target | How it’s used | Notes |
|---|---:|---|---|---|
| `solve.mode` | str | `gs.solve()` / `gs.vac_solve()` | Primary solve call | `plasma` or `vacuum` |
| `solve.vacuum` | bool | `gs.vac_solve()` | Alternative boolean form | Prefer `solve.mode` |

---

## 8) Postprocessing / output

| Config key path | Type | OFT API target | How it’s used | Notes |
|---|---:|---|---|---|
| `output.dir` | str | filesystem | Where to write outputs | Ensure directory exists |
| `output.save_eqdsk` | dict | `gs.save_eqdsk(filename, name=..., time=..., label=...)` | Write EQDSK | In docstring: `shot` not used; has `name`, `time`, `label` |
| `output.save_ifile` | str | `gs.save_ifile(filename)` | Write inverse file | Optional |
| `output.save_mug` | str | `gs.save_mug(filename)` | Write MUG file | Optional |
| `output.save_python_npz` | str | numpy | Save arrays from getters | Use `np.savez` on `get_psi`, `get_q`, `get_globals`, etc. |

**Common getters to serialize**:
- `gs.get_globals()` → scalar summary
- `gs.get_targets()` → applied targets
- `gs.get_profiles()` → resulting profiles
- `gs.get_psi(normalized=True/False)`
- `gs.get_q()`

---

## 9) Transformations / derived parameters

| Derived item | Source keys | Transformation | Used in |
|---|---|---|---|
| Triangle connectivity base | mesh builder | `lc` returned by `build_mesh` is 0-based | Safe to pass directly to `setup_mesh`; wrapper adds +1 internally |
| Region IDs | `geometry.regions[].id` | Must match TokaMaker convention (1 plasma, 2 vacuum, >=3 conductors) | `setup_mesh(reg=...)` |
| Profile dict → file | `profiles.*` | OFT writes temporary `.prof` files internally | `set_profiles` |

---

## 10) Minimal config skeleton (illustrative)

```yaml
runtime:
  debug_level: 0
  nthreads: 1

model:
  solver: tokamaker
  equation: grad_shafranov
  full_domain: false

discretization:
  fe_order: 2

geometry:
  regions:
    - name: plasma
      id: 1
      kind: plasma
      shape:
        type: polygon
        points: [[1.0,0.0],[1.2,0.2],[1.4,0.0],[1.2,-0.2]]
      mesh: {dx: 0.03}
    - name: vacuum
      id: 2
      kind: vacuum
      shape:
        type: rectangle
        x1: 0.6
        x2: 2.0
        z1: -1.0
        z2: 1.0
      mesh: {dx: 0.08}

mesh:
  merge_thresh: 1.0e-4
  require_boundary: false

profiles:
  ffprime: {x: [0,1], y: [0,0]}
  pprime:  {x: [0,1], y: [-1e5,0]}

targets:
  Ip: 5e5

output:
  dir: outputs
  save_eqdsk:
    filename: eqdsk.geqdsk
    name: TEST
    time: 0.0
    label: config-driven
```
