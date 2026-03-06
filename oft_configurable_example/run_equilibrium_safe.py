#!/usr/bin/env python
"""Safer launcher for run_equilibrium.py.

Why this exists:
- In this workspace we observed intermittent segfaults (RC=139) when invoking
  `python run_equilibrium.py ...` directly.
- Invoking the same entrypoint via `python -c "import run_equilibrium; ..."`
  completed successfully.

This wrapper keeps the main example runner unchanged, but provides a stable
command for downstream agents.

Usage:
  python run_equilibrium_safe.py --config discretization_config.yaml [--force]

Exit code:
  Propagates the exit code from the underlying run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--defaults", default=None)
    ap.add_argument("--output-dir", default=None)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    cmd = [sys.executable, "-c", "import run_equilibrium,sys; sys.exit(run_equilibrium.main(sys.argv[1:]))"]
    cmd += ["--config", args.config]
    if args.defaults:
        cmd += ["--defaults", args.defaults]
    if args.output_dir:
        cmd += ["--output-dir", args.output_dir]
    if args.force:
        cmd += ["--force"]

    return subprocess.call(cmd)


if __name__ == "__main__":
    raise SystemExit(main())
