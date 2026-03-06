#!/usr/bin/env python
"""Config-driven OpenFUSIONToolkit (TokaMaker) equilibrium runner.

This script:
  - Validates a YAML/JSON case config (using oft_config_validator.py)
  - Creates a deterministic run directory
  - Captures console output to a log file
  - Builds a simple 2D triangular mesh from config-defined geometry
  - Configures and runs TokaMaker (plasma GS solve or vacuum solve)
  - Writes outputs (gEQDSK, plots if enabled) and a manifest

No physics/discretization parameters are hardcoded: they are read from the config.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import hashlib
import json
import os
from pathlib import Path
import sys
import traceback
from typing import Any, Dict, List, Tuple

import numpy as np
import yaml

from oft_config_validator import validate_config, dump_effective_config


def _stable_run_id(effective_cfg: Dict[str, Any]) -> str:
    """Create a stable short hash from the effective config."""
    blob = yaml.safe_dump(effective_cfg, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:10]


@contextlib.contextmanager
def _tee_stdout_stderr(log_path: Path):
    """Tee stdout/stderr to a log file while preserving terminal output."""

    class _Tee:
        def __init__(self, *streams):
            self.streams = streams

        def write(self, data):
            for s in self.streams:
                s.write(data)
                s.flush()

        def flush(self):
            for s in self.streams:
                s.flush()

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as f:
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = _Tee(old_out, f)
        sys.stderr = _Tee(old_err, f)
        try:
            yield
        finally:
            sys.stdout, sys.stderr = old_out, old_err


def _polygon_area(poly: np.ndarray) -> float:
    x = poly[:, 0]
    y = poly[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _ensure_ccw(poly: np.ndarray) -> np.ndarray:
    if _polygon_area(poly) < 0:
        return poly[::-1].copy()
    return poly


def _point_in_poly(p: Tuple[float, float], poly: np.ndarray) -> bool:
    # ray casting
    x, y = p
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cond = (y0 > y) != (y1 > y)
        if cond:
            xinters = (x1 - x0) * (y - y0) / (y1 - y0 + 1e-30) + x0
            if x < xinters:
                inside = not inside
    return inside


def _generate_uniform_tri_mesh_in_polygon(poly: np.ndarray, dx: float) -> Tuple[np.ndarray, np.ndarray]:
    """Generate a coarse uniform triangular mesh by gridding and clipping.

    Returns:
      r2: (np,2) nodes
      lc: (nc,3) connectivity (1-based)

    Notes:
      - This is a simple mesher intended for examples; it is not quality-optimized.
      - Triangles are kept if their centroid lies inside the polygon.
    """
    poly = _ensure_ccw(poly)
    xmin, ymin = poly.min(axis=0)
    xmax, ymax = poly.max(axis=0)

    xs = np.arange(xmin, xmax + 0.5 * dx, dx)
    ys = np.arange(ymin, ymax + 0.5 * dx, dx)

    # node grid
    node_index: Dict[Tuple[int, int], int] = {}
    nodes: List[Tuple[float, float]] = []

    def add_node(ix, iy):
        key = (ix, iy)
        if key in node_index:
            return node_index[key]
        node_index[key] = len(nodes)
        nodes.append((float(xs[ix]), float(ys[iy])))
        return node_index[key]

    tris: List[Tuple[int, int, int]] = []
    for ix in range(len(xs) - 1):
        for iy in range(len(ys) - 1):
            # two triangles per cell
            n00 = add_node(ix, iy)
            n10 = add_node(ix + 1, iy)
            n01 = add_node(ix, iy + 1)
            n11 = add_node(ix + 1, iy + 1)

            t1 = (n00, n10, n11)
            t2 = (n00, n11, n01)

            for t in (t1, t2):
                cx = (nodes[t[0]][0] + nodes[t[1]][0] + nodes[t[2]][0]) / 3.0
                cy = (nodes[t[0]][1] + nodes[t[1]][1] + nodes[t[2]][1]) / 3.0
                if _point_in_poly((cx, cy), poly):
                    tris.append(t)

    # compress nodes to those actually referenced by triangles to avoid
    # unreferenced ("floating") vertices which OFT rejects.
    lc0 = np.asarray(tris, dtype=int)
    used = np.unique(lc0.reshape(-1))
    remap = -np.ones((len(nodes),), dtype=int)
    remap[used] = np.arange(len(used), dtype=int)
    nodes_used = [nodes[i] for i in used.tolist()]
    r2 = np.asarray(nodes_used, dtype=float)
    lc0 = remap[lc0]
    if lc0.size == 0:
        raise RuntimeError("Mesher produced no triangles; check polygon or dx")

    lc = lc0 + 1  # base-1
    return r2, lc


def _build_mesh_from_config(mesh_cfg: Dict[str, Any]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Build r (np,2), lc (nc,3), reg (nc,) from config."""
    if mesh_cfg["boundary"]["type"] != "polygon":
        raise ValueError("Only polygon boundary supported in this example runner")

    poly = np.asarray(mesh_cfg["boundary"]["points"], dtype=float)
    dx = float(mesh_cfg["meshing"]["dx"])

    r2, lc = _generate_uniform_tri_mesh_in_polygon(poly, dx)

    # assign region IDs by testing triangle centroids against region shapes.
    regions = mesh_cfg["regions"]
    reg = np.zeros((lc.shape[0],), dtype=int)

    def tri_centroid(t):
        pts = r2[(np.asarray(t) - 1)]
        return pts.mean(axis=0)

    # sort regions by priority (higher wins)
    regions_sorted = sorted(regions, key=lambda d: int(d.get("priority", 0)))

    for ic in range(lc.shape[0]):
        c = tri_centroid(lc[ic])
        assigned = None
        for rr in regions_sorted:
            shape = rr["shape"]
            if shape["type"] == "circle":
                dx0 = c[0] - float(shape["center"][0])
                dy0 = c[1] - float(shape["center"][1])
                if dx0 * dx0 + dy0 * dy0 <= float(shape["radius"]) ** 2:
                    assigned = int(rr["id"])
            elif shape["type"] == "annulus":
                dx0 = c[0] - float(shape["center"][0])
                dy0 = c[1] - float(shape["center"][1])
                rr2 = dx0 * dx0 + dy0 * dy0
                if float(shape["r_inner"]) ** 2 <= rr2 <= float(shape["r_outer"]) ** 2:
                    assigned = int(rr["id"])
            elif shape["type"] == "rectangle":
                cx, cy = float(shape["r0"]), float(shape["z0"])
                w, h = float(shape["width"]), float(shape["height"])
                if (cx - w / 2) <= c[0] <= (cx + w / 2) and (cy - h / 2) <= c[1] <= (cy + h / 2):
                    assigned = int(rr["id"])
            elif shape["type"] == "ellipse":
                cx, cy = float(shape["r0"]), float(shape["z0"])
                a, b = float(shape["a"]), float(shape["b"])
                dx0 = (c[0] - cx) / (a + 1e-30)
                dy0 = (c[1] - cy) / (b + 1e-30)
                if dx0 * dx0 + dy0 * dy0 <= 1.0:
                    assigned = int(rr["id"])
            else:
                raise ValueError(f"Unsupported region shape type: {shape['type']}")

        if assigned is None:
            # default to the lowest-numbered region (usually vacuum)
            assigned = int(regions_sorted[0]["id"])
        reg[ic] = assigned

    return r2, lc, reg


def _configure_tokamaker(case: Dict[str, Any], run_dir: Path):
    from OpenFUSIONToolkit._core import OFT_env
    from OpenFUSIONToolkit.TokaMaker import TokaMaker

    oft_case = case["oft_case"]
    model = oft_case["model"]
    mesh_cfg = oft_case["mesh"]
    disc = oft_case["discretization"]
    physics = oft_case["physics"]

    env = OFT_env(
        debug_level=int(oft_case.get("log_level", 0)),
        nthreads=int(oft_case.get("nthreads", 2)),
        unique_tempfiles=str(oft_case.get("unique_tempfiles", "global")),
        abort_callback=bool(oft_case.get("abort_callback", True)),
    )

    eq = TokaMaker(env)

    r2, lc, reg = _build_mesh_from_config(mesh_cfg)

    # Write a native mesh and load it (more robust than passing arrays directly).
    from OpenFUSIONToolkit.util import write_native_mesh

    # Native mesh file expects 3D points in general, but TokaMaker is 2D.
    # Use 2D points here.
    mesh_path = run_dir / "mesh.h5"
    write_native_mesh(str(mesh_path), r2, lc, reg)

    eq.setup_mesh(mesh_file=str(mesh_path))

    # Regions (conductors/coils) are optional here; keep empty.
    eq.setup_regions(cond_dict={}, coil_dict={})

    eq.setup(
        order=int(disc["fe_order"]),
        F0=float(physics.get("F0", 0.0)),
        full_domain=bool(disc.get("full_domain", False)),
    )

    if model["type"] == "gs_plasma":
        # profiles
        prof = physics["profiles"]
        ffp_prof = {"type": "linterp", "x": prof["ffprime"]["x"], "y": prof["ffprime"]["y"]}
        pp_prof = {"type": "linterp", "x": prof["pprime"]["x"], "y": prof["pprime"]["y"]}
        eq.set_profiles(ffp_prof=ffp_prof, pp_prof=pp_prof, foffset=float(physics.get("F0", 0.0)))

        targets = physics["targets"]
        eq.set_targets(
            Ip=float(targets.get("Ip")) if targets.get("Ip") is not None else None,
            R0=float(targets.get("R0")) if targets.get("R0") is not None else None,
            V0=float(targets.get("V0")) if targets.get("V0") is not None else None,
            pax=float(targets.get("pax")) if targets.get("pax") is not None else None,
            estore=float(targets.get("estore")) if targets.get("estore") is not None else None,
            retain_previous=bool(targets.get("retain_previous", False)),
        )

    elif model["type"] == "gs_vacuum":
        # Minimal vacuum: no coils implemented in this example runner.
        # (Coils/conductors can be added by extending config->setup_regions mapping.)
        pass
    else:
        raise ValueError(f"Unknown model.type: {model['type']}")

    return eq, env


def _safe_json_dump(obj: Any) -> Any:
    """Convert common non-JSON types (numpy) into JSON-serializable objects."""
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    if isinstance(obj, (Path,)):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): _safe_json_dump(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_safe_json_dump(v) for v in obj]
    return obj


def _write_json(path: Path, info: Dict[str, Any]):
    path.write_text(
        json.dumps(_safe_json_dump(info), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_manifest(run_dir: Path, info: Dict[str, Any]):
    _write_json(run_dir / "manifest.json", info)


def _get_repro_metadata() -> Dict[str, Any]:
    import platform
    import subprocess

    meta: Dict[str, Any] = {
        "python": {
            "version": sys.version,
            "executable": sys.executable,
        },
        "platform": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_compiler": platform.python_compiler(),
        },
        "oft": {
            "doc_version_guess": None,
            "python_package_path": None,
            "toka_python_package_path": None,
            "liboftpy_path": None,
        },
        "runner_git": {
            "git_commit": None,
            "git_describe": None,
        },
    }

    # OFT install info (best-effort)
    try:
        import OpenFUSIONToolkit as oft
        meta["oft"]["python_package_path"] = getattr(oft, "__file__", None)
        # OFT docs often include a version string; try to parse it.
        try:
            from pathlib import Path as _Path
            doc_index = _Path("/Applications/OpenFUSIONToolkit/doc/html/index.html")
            if doc_index.exists():
                txt = doc_index.read_text(errors="ignore")
                import re

                m = re.search(r"Open FUSION Toolkit[^<]*([0-9]+\.[0-9]+\.[0-9]+)", txt)
                if m:
                    meta["oft"]["doc_version_guess"] = m.group(1)
        except Exception:
            pass
    except Exception:
        pass

    try:
        import OpenFUSIONToolkit.TokaMaker as tm
        meta["oft"]["toka_python_package_path"] = getattr(tm, "__file__", None)
    except Exception:
        pass

    try:
        import OpenFUSIONToolkit.TokaMaker._core as c
        meta["oft"]["liboftpy_path"] = getattr(getattr(c, "oftpy_lib", None), "_name", None)
    except Exception:
        pass

    # Runner repo git commit (best-effort) WITHOUT invoking `git`.
    # Constraint: do not use the 'git' command.
    try:
        head = Path(".git/HEAD")
        if head.exists():
            ref = head.read_text().strip()
            if ref.startswith("ref:"):
                ref_path = Path(".git") / ref.split(None, 1)[1]
                if ref_path.exists():
                    meta["runner_git"]["git_commit"] = ref_path.read_text().strip()
            else:
                meta["runner_git"]["git_commit"] = ref
        # `git describe` is not available without invoking git; omit.
    except Exception:
        pass

    return meta


def _write_summary(run_dir: Path, info: Dict[str, Any]):
    _write_json(run_dir / "summary.json", info)


def main(argv: List[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, help="Path to YAML/JSON config")
    ap.add_argument("--defaults", default=None, help="Optional defaults YAML/JSON merged under the case config")
    ap.add_argument("--output-dir", default="outputs", help="Base output directory")
    ap.add_argument("--force", action="store_true", help="Overwrite existing run directory")
    ap.add_argument("--no-force", dest="force", action="store_false")
    ap.set_defaults(force=None)
    args = ap.parse_args(argv)

    cfg_path = Path(args.config).resolve()
    defaults_path = Path(args.defaults).resolve() if args.defaults else None

    vres = validate_config(cfg_path, defaults_path)
    if not vres.ok:
        for e in vres.errors:
            print(f"- {e}", file=sys.stderr)
        return 2
    effective_cfg = vres.config

    oft_case = effective_cfg["oft_case"]
    name = oft_case["name"]
    base_out = Path(args.output_dir).resolve()

    # overwrite policy: CLI overrides config.outputs.overwrite
    overwrite_cfg = bool(oft_case["outputs"].get("overwrite", False))
    if args.force is None:
        overwrite = overwrite_cfg
    else:
        overwrite = bool(args.force)

    run_id = _stable_run_id(effective_cfg)
    run_dir = base_out / name / f"run_{run_id}"

    if run_dir.exists():
        if not overwrite:
            print(f"ERROR: run directory exists: {run_dir} (use --force or outputs.overwrite: true)", file=sys.stderr)
            return 3
        # remove previous contents
        for p in sorted(run_dir.rglob("*"), reverse=True):
            if p.is_file() or p.is_symlink():
                p.unlink()
            elif p.is_dir():
                p.rmdir()

    run_dir.mkdir(parents=True, exist_ok=True)

    # persist effective config
    eff_cfg_path = run_dir / "effective_config.yaml"
    dump_effective_config(effective_cfg, eff_cfg_path)

    log_path = run_dir / "run.log"

    repro = _get_repro_metadata()

    manifest: Dict[str, Any] = {
        "case_name": name,
        "run_id": run_id,
        "timestamp": _dt.datetime.now().isoformat(timespec="seconds"),
        "config": str(cfg_path),
        "defaults": str(defaults_path) if defaults_path else None,
        "run_dir": str(run_dir),
        "files": {},
        "status": "started",
        "reproducibility": repro,
    }

    summary: Dict[str, Any] = {
        "case_name": name,
        "run_id": run_id,
        "timestamp": manifest["timestamp"],
        "status": "started",
        "model_type": effective_cfg["oft_case"]["model"]["type"],
        "settings": {
            "solver": effective_cfg["oft_case"].get("solver", {}),
            "discretization": effective_cfg["oft_case"].get("discretization", {}),
            "physics": effective_cfg["oft_case"].get("physics", {}),
            "mesh": {
                "meshing": effective_cfg["oft_case"]["mesh"].get("meshing", {}),
                "boundary": effective_cfg["oft_case"]["mesh"].get("boundary", {}),
                "regions": effective_cfg["oft_case"]["mesh"].get("regions", {}),
            },
            "outputs": effective_cfg["oft_case"].get("outputs", {}),
        },
        "reproducibility": repro,
        "diagnostics": {},
        "files": {},
    }

    with _tee_stdout_stderr(log_path):
        try:
            eq, env = _configure_tokamaker(effective_cfg, run_dir)

            model_type = effective_cfg["oft_case"]["model"]["type"]
            if model_type == "gs_vacuum":
                # Provide a well-defined boundary condition to avoid internal
                # target/BC solvers encountering singular systems.
                # Allow override from config: oft_case.physics.vacuum_bc.psi
                vac_bc = effective_cfg["oft_case"].get("physics", {}).get("vacuum_bc", {})
                psi_bc = vac_bc.get("psi", 0.0)
                if psi_bc is None:
                    psi_arg = None
                else:
                    # TokaMaker expects a per-vertex array for boundary psi.
                    psi_arg = np.full((eq.np,), float(psi_bc), dtype=float)
                eq.vac_solve(psi=psi_arg)
            else:
                eq.solve(vacuum=False)

            # outputs
            out_cfg = effective_cfg["oft_case"]["outputs"]
            if bool(out_cfg.get("write_eqdsk", True)):
                eqdsk_path = run_dir / out_cfg.get("eqdsk_filename", "equilibrium.geqdsk")
                # For vacuum-only runs, TokaMaker may not have a limiter contour;
                # provide explicit bounds if configured.
                save_kwargs = {
                    "nr": int(out_cfg.get("eqdsk_nr", 65)),
                    "nz": int(out_cfg.get("eqdsk_nz", 65)),
                    "run_info": str(out_cfg.get("run_info", name))[:40],
                }
                rb = out_cfg.get("eqdsk_rbounds", None)
                zb = out_cfg.get("eqdsk_zbounds", None)
                if rb is not None:
                    save_kwargs["rbounds"] = np.asarray(rb, dtype=float)
                if zb is not None:
                    save_kwargs["zbounds"] = np.asarray(zb, dtype=float)
                eq.save_eqdsk(str(eqdsk_path), **save_kwargs)
                manifest["files"]["geqdsk"] = str(eqdsk_path)

            if bool(out_cfg.get("write_plots", False)):
                # relies on matplotlib; if unavailable, this will raise and be caught.
                eq.plot_psi(show=False, filename=str(run_dir / "psi.png"))
                manifest["files"]["psi_plot"] = str(run_dir / "psi.png")

            # Stats/diagnostics (best-effort)
            try:
                stats = eq.get_stats()
                manifest["stats"] = stats
                summary["diagnostics"]["stats"] = stats
                print("Stats:", stats)
            except Exception as e_stats:
                manifest["stats_error"] = repr(e_stats)
                summary["diagnostics"]["stats_error"] = repr(e_stats)
                print(f"WARNING: get_stats failed: {e_stats}")

            # Basic scalar diagnostics if available via attributes
            for attr in ("Ip", "R0", "V0", "pax", "estore"):
                try:
                    if hasattr(eq, attr):
                        summary["diagnostics"][attr] = getattr(eq, attr)
                except Exception:
                    pass

            summary["status"] = "ok"
            manifest["status"] = "ok"
            print("Run completed successfully")
            rc = 0

        except Exception as e:
            manifest["status"] = "failed"
            manifest["error"] = repr(e)
            manifest["traceback"] = traceback.format_exc()

            summary["status"] = "failed"
            summary["diagnostics"]["error"] = repr(e)
            summary["diagnostics"]["traceback"] = manifest["traceback"]

            print("ERROR: run failed")
            print(manifest["traceback"], file=sys.stderr)
            rc = 4

        finally:
            # record file outputs
            manifest["files"]["log"] = str(log_path)
            summary["files"].update(manifest.get("files", {}))

            # Always include the generated mesh and effective config in the manifest
            mesh_path = run_dir / "mesh.h5"
            if mesh_path.exists():
                manifest["files"].setdefault("mesh", str(mesh_path))
                summary["files"].setdefault("mesh", str(mesh_path))
            manifest["files"].setdefault("effective_config", str(eff_cfg_path))
            summary["files"].setdefault("effective_config", str(eff_cfg_path))

            _write_summary(run_dir, summary)
            _write_manifest(run_dir, manifest)

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
