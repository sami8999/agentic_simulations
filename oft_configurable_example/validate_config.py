"""CLI: validate an OFT case config and emit an effective config.

Usage:
  python validate_config.py --config path/to/config.yaml [--defaults defaults.yaml] [--effective effective.yaml]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from oft_config_validator import validate_config, dump_effective_config


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True)
    ap.add_argument("--defaults", default=None)
    ap.add_argument("--effective", default=None, help="Write resolved/effective config YAML")
    args = ap.parse_args(argv)

    res = validate_config(args.config, args.defaults)
    if not res.ok:
        print("CONFIG INVALID:\n", file=sys.stderr)
        for e in res.errors:
            print(f"- {e}", file=sys.stderr)
        return 2

    print("CONFIG OK")
    if args.effective:
        dump_effective_config(res.config, args.effective)
        print(f"Wrote effective config to: {args.effective}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
