"""Config validation + defaults resolution for OFT/TokaMaker config-driven examples.

This module is intentionally standalone (no OFT imports) so it can validate configs
before heavy libraries are loaded.

Design goals:
- Explicit required keys: missing -> error (no silent defaults).
- Defaults may be applied ONLY when:
    a) provided by a user-specified defaults file, OR
    b) explicitly encoded in the JSON Schema (small, unambiguous defaults like booleans).
  In both cases, the resolved/effective config is emitted.
- Clear, actionable error messages with dotted paths.

Supported config formats: YAML, JSON.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import yaml
import jsonschema


# -----------------------------
# JSON schema (minimal, strict)
# -----------------------------

# Notes:
# - Use additionalProperties=False for strictness.
# - Provide only safe defaults (e.g., overwrite=false). Avoid physics/discretization defaults.
# - Some constraints are enforced in semantic validation because they depend on cross-fields.

OFT_CASE_SCHEMA: Dict[str, Any] = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "additionalProperties": False,
    "required": ["oft_case"],
    "properties": {
        "oft_case": {
            "type": "object",
            "additionalProperties": False,
            "required": ["name", "model", "outputs", "mesh", "discretization", "physics"],
            "properties": {
                "name": {"type": "string", "minLength": 1},
                "model": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["type"],
                    "properties": {
                        "type": {
                            "type": "string",
                            "enum": ["gs_plasma", "gs_vacuum"],
                        }
                    },
                },
                "outputs": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["output_dir"],
                    "properties": {
                        "output_dir": {"type": "string", "minLength": 1},
                        "overwrite": {"type": "boolean", "default": False},
                        "write_eqdsk": {"type": "boolean", "default": True},
                        "eqdsk_filename": {"type": "string", "default": "equilibrium.geqdsk"},
                        "eqdsk_nr": {"type": "integer", "minimum": 16, "default": 65},
                        "eqdsk_nz": {"type": "integer", "minimum": 16, "default": 65},
                        "run_info": {"type": "string", "default": ""},
                        "eqdsk_rbounds": {
                            "type": ["array", "null"],
                            "minItems": 2,
                            "maxItems": 2,
                            "items": {"type": "number"},
                            "default": None,
                        },
                        "eqdsk_zbounds": {
                            "type": ["array", "null"],
                            "minItems": 2,
                            "maxItems": 2,
                            "items": {"type": "number"},
                            "default": None,
                        },
                        "write_ifile": {"type": "boolean", "default": False},
                        "write_mug": {"type": "boolean", "default": False},
                        "log_level": {
                            "type": "string",
                            "enum": ["debug", "info", "warning", "error"],
                            "default": "info",
                        },
                    },
                },
                "mesh": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["boundary", "regions", "meshing"],
                    "properties": {
                        "boundary": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["type", "points"],
                            "properties": {
                                "type": {"type": "string", "enum": ["polygon"]},
                                "points": {
                                    "type": "array",
                                    "minItems": 3,
                                    "items": {
                                        "type": "array",
                                        "minItems": 2,
                                        "maxItems": 2,
                                        "items": {"type": "number"},
                                    },
                                },
                            },
                        },
                        "regions": {
                            "type": "array",
                            "minItems": 1,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["id", "name", "type", "shape"],
                                "properties": {
                                    "id": {"type": "integer", "minimum": 1},
                                    "name": {"type": "string", "minLength": 1},
                                    "type": {
                                        "type": "string",
                                        "enum": ["plasma", "vacuum", "conductor", "coil"],
                                    },
                                    "shape": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["type"],
                                        "properties": {
                                            "type": {
                                                "type": "string",
                                                "enum": ["polygon", "rectangle", "ellipse", "annulus"],
                                            },
                                            "points": {
                                                "type": "array",
                                                "minItems": 3,
                                                "items": {
                                                    "type": "array",
                                                    "minItems": 2,
                                                    "maxItems": 2,
                                                    "items": {"type": "number"},
                                                },
                                            },
                                            "r0": {"type": "number"},
                                            "z0": {"type": "number"},
                                            "width": {"type": "number", "exclusiveMinimum": 0},
                                            "height": {"type": "number", "exclusiveMinimum": 0},
                                            "a": {"type": "number", "exclusiveMinimum": 0},
                                            "b": {"type": "number", "exclusiveMinimum": 0},
                                            "r_inner": {"type": "number", "minimum": 0},
                                            "r_outer": {"type": "number", "exclusiveMinimum": 0},
                                        },
                                    },
                                    "material": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "mu_r": {"type": "number", "exclusiveMinimum": 0},
                                        },
                                    },
                                },
                            },
                        },
                        "meshing": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["dx"],
                            "properties": {
                                "dx": {"type": "number", "exclusiveMinimum": 0},
                                "dx_curve": {"type": "number", "exclusiveMinimum": 0},
                                "merge_thresh": {"type": "number", "minimum": 0},
                                "quality_limit": {"type": "number", "minimum": 0},
                                "require_boundary": {"type": "boolean", "default": True},
                            },
                        },
                    },
                },
                "discretization": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["fe_order", "full_domain"],
                    "properties": {
                        "fe_order": {"type": "integer", "minimum": 1, "maximum": 6},
                        "full_domain": {"type": "boolean"},
                        "F0": {"type": "number"},
                    },
                },
                "physics": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["units"],
                    "properties": {
                        "F0": {"type": "number"},
                        "units": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["length", "current", "pressure"],
                            "properties": {
                                "length": {"type": "string", "enum": ["m"]},
                                "current": {"type": "string", "enum": ["A"]},
                                "pressure": {"type": "string", "enum": ["Pa"]},
                            },
                        },
                        "targets": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "Ip": {"type": ["number", "null"]},
                                "Ip_ratio": {"type": ["number", "null"]},
                                "pax": {"type": ["number", "null"]},
                                "estore": {"type": ["number", "null"]},
                                "R0": {"type": ["number", "null"]},
                                "V0": {"type": ["number", "null"]},
                                "retain_previous": {"type": "boolean", "default": False},
                            },
                        },
                        "profiles": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "ffprime": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["x", "y"],
                                    "properties": {
                                        "x": {"type": "array", "minItems": 2, "items": {"type": "number"}},
                                        "y": {"type": "array", "minItems": 2, "items": {"type": "number"}},
                                    },
                                },
                                "pprime": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": ["x", "y"],
                                    "properties": {
                                        "x": {"type": "array", "minItems": 2, "items": {"type": "number"}},
                                        "y": {"type": "array", "minItems": 2, "items": {"type": "number"}},
                                    },
                                },
                            },
                        },
                        "vacuum_bc": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "psi": {"type": ["number", "null"], "default": 0.0},
                            },
                        },
                        "vacuum": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "coil_currents": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "required": ["region_id", "current"],
                                        "properties": {
                                            "region_id": {"type": "integer", "minimum": 1},
                                            "current": {"type": "number"},
                                        },
                                    },
                                }
                            },
                        },
                    },
                },
                "solver": {
                    "type": "object",
                    "additionalProperties": True,
                },
                "metadata": {
                    "type": "object",
                    "additionalProperties": True,
                },
            },
        }
    },
}


# -----------------------------
# Helpers
# -----------------------------

def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge dictionaries. override wins. Does not mutate inputs."""
    out = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _apply_schema_defaults(instance: Any, schema: Dict[str, Any]) -> Any:
    """Recursively apply JSON Schema 'default' values into instance.

    Only uses explicit 'default' fields present in the schema.
    """
    if isinstance(instance, dict) and isinstance(schema, dict):
        props = schema.get("properties", {})
        for key, prop_schema in props.items():
            if key not in instance and "default" in prop_schema:
                instance[key] = prop_schema["default"]
            if key in instance:
                instance[key] = _apply_schema_defaults(instance[key], prop_schema)
        return instance
    if isinstance(instance, list) and isinstance(schema, dict):
        item_schema = schema.get("items")
        if item_schema is not None:
            for i in range(len(instance)):
                instance[i] = _apply_schema_defaults(instance[i], item_schema)
        return instance
    return instance


def _format_validation_error(e: jsonschema.ValidationError) -> str:
    path = ".".join([str(p) for p in e.absolute_path])
    loc = path if path else "<root>"
    msg = e.message
    if e.validator == "required":
        # e.message already indicates which property is required
        return f"{loc}: {msg}"
    return f"{loc}: {msg}"


def _ensure(cond: bool, path: str, message: str, errors: List[str]):
    if not cond:
        errors.append(f"{path}: {message}")


# -----------------------------
# Semantic validation
# -----------------------------

def _validate_profiles_block(profiles: Dict[str, Any], errors: List[str], base_path: str):
    for pname in ("ffprime", "pprime"):
        if pname not in profiles:
            errors.append(f"{base_path}.{pname}: missing required profile block")
            continue
        x = profiles[pname].get("x")
        y = profiles[pname].get("y")
        if not isinstance(x, list) or not isinstance(y, list):
            errors.append(f"{base_path}.{pname}: x and y must be lists")
            continue
        _ensure(len(x) == len(y), f"{base_path}.{pname}", "x and y must have same length", errors)
        _ensure(len(x) >= 2, f"{base_path}.{pname}", "x/y must have at least 2 points", errors)
        if len(x) >= 2:
            _ensure(abs(x[0] - 0.0) < 1e-12, f"{base_path}.{pname}.x", "first x must be 0.0 (normalized flux)", errors)
            _ensure(abs(x[-1] - 1.0) < 1e-12, f"{base_path}.{pname}.x", "last x must be 1.0 (normalized flux)", errors)
            # monotone nondecreasing
            for i in range(1, len(x)):
                _ensure(x[i] >= x[i - 1], f"{base_path}.{pname}.x", f"x must be nondecreasing; x[{i}] < x[{i-1}]", errors)


def _validate_mesh(mesh: Dict[str, Any], errors: List[str]):
    # boundary polygon closure check (optional): allow either closed or open, but if closed last==first.
    pts = mesh["boundary"]["points"]
    if len(pts) >= 3 and pts[0] == pts[-1]:
        pass

    ids = [r["id"] for r in mesh["regions"]]
    _ensure(len(ids) == len(set(ids)), "oft_case.mesh.regions", "region ids must be unique", errors)

    # shape parameter requirements
    for i, r in enumerate(mesh["regions"]):
        shape = r["shape"]
        stype = shape["type"]
        pfx = f"oft_case.mesh.regions[{i}].shape"
        if stype == "polygon":
            _ensure("points" in shape, pfx, "polygon requires points", errors)
        elif stype == "rectangle":
            for k in ("r0", "z0", "width", "height"):
                _ensure(k in shape, pfx, f"rectangle requires {k}", errors)
        elif stype == "ellipse":
            for k in ("r0", "z0", "a", "b"):
                _ensure(k in shape, pfx, f"ellipse requires {k}", errors)
        elif stype == "annulus":
            for k in ("r0", "z0", "r_inner", "r_outer"):
                _ensure(k in shape, pfx, f"annulus requires {k}", errors)
            if all(k in shape for k in ("r_inner", "r_outer")):
                _ensure(shape["r_outer"] > shape["r_inner"], pfx, "r_outer must be > r_inner", errors)


def semantic_validate(cfg: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    case = cfg["oft_case"]

    model_type = case["model"]["type"]

    # mesh checks
    _validate_mesh(case["mesh"], errors)

    # discretization checks
    disc = case["discretization"]
    if "F0" in disc:
        _ensure(isinstance(disc["F0"], (int, float)), "oft_case.discretization.F0", "must be a number", errors)

    # model-specific requirements
    physics = case["physics"]
    if model_type == "gs_plasma":
        _ensure("targets" in physics and isinstance(physics["targets"], dict), "oft_case.physics.targets", "required for gs_plasma", errors)
        if isinstance(physics.get("targets"), dict):
            _ensure("Ip" in physics["targets"], "oft_case.physics.targets.Ip", "required for gs_plasma", errors)
        _ensure("profiles" in physics and isinstance(physics["profiles"], dict), "oft_case.physics.profiles", "required for gs_plasma", errors)
        if isinstance(physics.get("profiles"), dict):
            _validate_profiles_block(physics["profiles"], errors, "oft_case.physics.profiles")
        # vacuum-only block must be absent or empty
        if "vacuum" in physics and physics["vacuum"]:
            errors.append("oft_case.physics.vacuum: must be omitted or empty for gs_plasma")

    elif model_type == "gs_vacuum":
        # vacuum solve should not specify plasma profiles/targets
        if "profiles" in physics and physics["profiles"]:
            errors.append("oft_case.physics.profiles: must be omitted or empty for gs_vacuum")
        if "targets" in physics and physics["targets"]:
            errors.append("oft_case.physics.targets: must be omitted or empty for gs_vacuum")
        _ensure("vacuum" in physics and isinstance(physics["vacuum"], dict), "oft_case.physics.vacuum", "required for gs_vacuum", errors)
        vac = physics.get("vacuum", {}) if isinstance(physics.get("vacuum"), dict) else {}
        _ensure("coil_currents" in vac, "oft_case.physics.vacuum.coil_currents", "required for gs_vacuum", errors)

    # outputs dir existence not required (runner can create), but must be relative or absolute string
    outdir = case["outputs"]["output_dir"]
    _ensure(isinstance(outdir, str) and len(outdir) > 0, "oft_case.outputs.output_dir", "must be a non-empty string", errors)

    return errors


# -----------------------------
# Public API
# -----------------------------

@dataclass
class ValidationResult:
    config: Dict[str, Any]
    errors: List[str]

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0


def load_config(path: Union[str, Path]) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(str(path))
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".yaml", ".yml"):
        return yaml.safe_load(text)
    if path.suffix.lower() == ".json":
        return json.loads(text)
    raise ValueError(f"Unsupported config extension: {path.suffix}")


def validate_config(
    config_path: Union[str, Path],
    defaults_path: Optional[Union[str, Path]] = None,
) -> ValidationResult:
    """Load + validate + resolve defaults.

    If defaults_path is provided, it is deep-merged into the user config:
    effective = deep_merge(defaults, user)

    Then JSON Schema validation is run, schema defaults are applied, and
    semantic validation is performed.
    """
    user_cfg = load_config(config_path)

    cfg = user_cfg
    if defaults_path is not None:
        defaults_cfg = load_config(defaults_path)
        cfg = _deep_merge(defaults_cfg, user_cfg)

    # JSON schema validate
    errors: List[str] = []
    validator = jsonschema.Draft202012Validator(OFT_CASE_SCHEMA)
    for e in sorted(validator.iter_errors(cfg), key=lambda e: list(e.absolute_path)):
        errors.append(_format_validation_error(e))

    # Apply schema defaults even if there were schema errors? Do it only if schema ok.
    if not errors:
        cfg = _apply_schema_defaults(cfg, OFT_CASE_SCHEMA)
        errors.extend(semantic_validate(cfg))

    return ValidationResult(config=cfg, errors=errors)


def dump_effective_config(cfg: Dict[str, Any], path: Union[str, Path]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, sort_keys=False)
