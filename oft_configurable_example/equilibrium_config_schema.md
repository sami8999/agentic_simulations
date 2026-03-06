# Config schema (minimal runnable + extensible)

This document defines a **minimal runnable** configuration schema for running an OpenFUSIONToolkit (OFT) / TokaMaker Grad–Shafranov equilibrium case **without hardcoding** physics parameters or discretization in the Python runner.

The schema is designed to map directly onto the OFT/TokaMaker API calls (see `CONFIG_TO_OFT_MAPPING.md`). It is also extensible: optional blocks can be added without breaking existing configs.

---

## 0) File format

- YAML (preferred) or JSON.
- Top-level key: `oft_case`.

---

## 1) Reproducibility & run controls

### Required

```yaml
oft_case:
  run:
    name: "demo_gs"
    output_dir: "outputs"
```

### Optional (recommended)

```yaml
oft_case:
  run:
    description: "Short human description"
    overwrite: false           # if false, error if output exists
    deterministic_naming: true # if true, use a stable folder name based on `name`
    log_level: "INFO"         # DEBUG|INFO|WARNING|ERROR
    random_seed: null          # integer or null; currently only used if any stochastic mesher features are enabled in future

  reproducibility:
    # These are *inputs* if you want to annotate; the runner may also auto-populate a metadata file.
    author: ""
    notes: ""
```

### Auto-populated metadata (runner writes)

The runner should write `run_metadata.yaml/json` with:

- timestamp (UTC)
- platform (os, python version)
- OFT package version (if available)
- OFT install path
- full resolved config (after defaults)

These fields are **not required in the config**.

---

## 2) Model / equation selection

### Required

```yaml
oft_case:
  model:
    # Supported modes (explicit, no placeholders):
    # - "gs_plasma": solves plasma Grad–Shafranov equilibrium (calls `solve()`)
    # - "gs_vacuum": solves vacuum field only (calls `vac_solve()`)
    mode: "gs_plasma"
```

Notes:
- Both modes use the same mesh + boundary description.
- `gs_plasma` additionally requires targets and profiles.

---

## 3) Runtime / OFT environment

### Minimal runnable (defaults may be applied by runner)

```yaml
oft_case:
  env:
    nthreads: 1
    with_mpi: false
```

### Optional

```yaml
oft_case:
  env:
    # depends on OFT build; runner should pass through if supported.
    device: "cpu"  # if supported; otherwise ignore
```

---

## 4) Units / normalization conventions

All quantities are in **SI-derived engineering units** unless stated otherwise.

- Lengths: meters (m)
- Current: amperes (A)
- Pressure: pascals (Pa)
- Magnetic field: tesla (T)
- Poloidal flux `psi`: Webers per radian (Wb/rad) in common tokamak conventions; in practice TokaMaker uses its own internal normalization. The runner should treat `psi` as a solver variable and avoid converting unless OFT requires.

### Normalized profile coordinate

Profiles in `profiles.*` use `x ∈ [0,1]` representing **normalized poloidal flux** coordinate:

- `x = 0` axis
- `x = 1` LCFS

The values `y` correspond to the profile quantity in the units expected by TokaMaker for:

- `ffprime`: F F′(psi)
- `pprime`: p′(psi)

Because OFT/TokaMaker may use a specific normalization for these profile functions, the config may include an annotation:

```yaml
oft_case:
  units:
    profile_convention: "tokamaker_default"  # annotation only
```

The runner should not assume additional scaling.

---

## 5) Geometry + meshing (array-based mesh via `gs_Domain`)

This is the **primary discretization control block**.

### Minimal runnable

```yaml
oft_case:
  mesh:
    domain:
      boundary:
        # Outer vacuum boundary polygon (closed). Coordinates in meters.
        polygon:
          - [1.0, -1.0]
          - [3.0, -1.0]
          - [3.0,  1.0]
          - [1.0,  1.0]

    regions:
      - name: plasma
        id: 1
        type: polygon
        polygon:
          - [1.4, -0.5]
          - [2.2, -0.5]
          - [2.2,  0.5]
          - [1.4,  0.5]
        mesh:
          dx: 0.05

      - name: vacuum
        id: 2
        type: fill
        mesh:
          dx: 0.10

    build:
      merge_thresh: 1.0e-6
      require_boundary: true
      quality_limit: 20.0
```

### Supported region types

Each entry in `mesh.regions[]` supports:

- `type: polygon` + `polygon: [[R,Z], ...]`
- `type: rectangle` + `r0, z0, w, h`
- `type: annulus` + `r0, z0, r1, r2`
- `type: ellipse` + `r0, z0, a, b`
- `type: fill` (no shape): indicates a background region (commonly vacuum id=2)

### Per-region mesh sizing

`mesh.dx` sets a target element size for that region.
Optional curvature control:

```yaml
mesh:
  regions:
    - ...
      mesh:
        dx: 0.05
        dx_curve: 0.02
```

### Optional global meshing controls

```yaml
oft_case:
  mesh:
    build:
      # forwarded to gs_Domain.build_mesh
      merge_thresh: 1.0e-6
      quality_limit: 20.0
      require_boundary: true
      debug: false
```

---

## 6) Discretization / solver setup (TokaMaker `setup`)

### Required (minimal)

```yaml
oft_case:
  discretization:
    fe_order: 2
    full_domain: false
```

### Optional

```yaml
oft_case:
  discretization:
    F0: 0.0  # pass-through to `setup(F0=...)` if used
```

Meaning:
- `fe_order` maps to `TokaMaker.setup(order=...)`
- `full_domain` maps to `TokaMaker.setup(full_domain=...)`

---

## 7) Physics: profiles and targets (plasma mode)

Only required for `model.mode: gs_plasma`.

### Required minimal

```yaml
oft_case:
  physics:
    targets:
      Ip: 1.0e6    # plasma current [A]

    profiles:
      # Piecewise-linear tables with x in [0,1]
      ffprime:
        x: [0.0, 1.0]
        y: [0.0, 0.0]
      pprime:
        x: [0.0, 1.0]
        y: [-1.0e5, 0.0]
```

### Optional targets (any subset supported by TokaMaker)

```yaml
oft_case:
  physics:
    targets:
      Ip: 1.0e6
      pax: 0.0
      estore: 0.0
      R0: 1.7
      V0: 0.0
      # additional supported keys may be passed through if TokaMaker accepts them
```

Validation rules (runner should enforce):
- `profiles.*.x` monotone nondecreasing
- first x=0 and last x=1 (or runner can auto-extend with endpoints if configured)
- x and y arrays same length >= 2

---

## 8) Conductors/coils (optional)

If supported by the chosen OFT/TokaMaker workflow, conductors can be represented as additional regions (id>=3) and/or via coil definitions.

This block is optional and may be ignored by a minimal runner until coil APIs are finalized.

```yaml
oft_case:
  conductors:
    regions:
      - name: shell
        id: 3
        type: annulus
        r0: 1.7
        z0: 0.0
        r1: 2.4
        r2: 2.5
        mesh:
          dx: 0.05
```

---

## 9) Solver settings (optional pass-through)

The runner can start from `tokamaker_default_settings(env)` and then override with this block.

```yaml
oft_case:
  solver:
    settings:
      # keys must correspond to tokamaker settings; runner passes through
      maxits: 50
      rtol: 1.0e-10
      atol: 1.0e-12
```

If unknown keys are provided, runner should error (strict mode) or warn and ignore (per `run.log_level`).

---

## 10) Output controls

### Required

```yaml
oft_case:
  outputs:
    formats:
      eqdsk: true
```

### Optional

```yaml
oft_case:
  outputs:
    formats:
      eqdsk: true
      ifile: false
      mug: false

    # file basenames (no extension) or null to use run.name
    basename: null

    # what to write additionally
    write_psi_on_mesh: true
    write_summary: true
```

---

## 11) Minimal complete example (plasma)

```yaml
oft_case:
  run:
    name: "demo_gs_plasma"
    output_dir: "outputs"

  model:
    mode: "gs_plasma"

  env:
    nthreads: 1
    with_mpi: false

  discretization:
    fe_order: 2
    full_domain: false

  mesh:
    domain:
      boundary:
        polygon:
          - [1.0, -1.0]
          - [3.0, -1.0]
          - [3.0,  1.0]
          - [1.0,  1.0]

    regions:
      - name: plasma
        id: 1
        type: polygon
        polygon:
          - [1.4, -0.5]
          - [2.2, -0.5]
          - [2.2,  0.5]
          - [1.4,  0.5]
        mesh:
          dx: 0.05

      - name: vacuum
        id: 2
        type: fill
        mesh:
          dx: 0.10

    build:
      merge_thresh: 1.0e-6
      require_boundary: true
      quality_limit: 20.0

  physics:
    targets:
      Ip: 1.0e6

    profiles:
      ffprime:
        x: [0.0, 1.0]
        y: [0.0, 0.0]
      pprime:
        x: [0.0, 1.0]
        y: [-1.0e5, 0.0]

  solver:
    settings:
      maxits: 50

  outputs:
    formats:
      eqdsk: true
      ifile: false
      mug: false
```
