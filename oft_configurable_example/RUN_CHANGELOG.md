# Changelog (debug iterations)

## 2026-03-06
- Updated `run_equilibrium.py` to always include `mesh.h5` and `effective_config.yaml` in `manifest.json`/`summary.json`.
- Observed intermittent segmentation fault (exit code 139) when running `python run_equilibrium.py ...` as a standalone process. Same run succeeds when calling `run_equilibrium.main()` from within Python.
- Added a new wrapper script `run_equilibrium_safe.py` that executes the runner in a subprocess using the `python -c "import run_equilibrium; ..."` pattern, which avoided the segfault during debugging.
