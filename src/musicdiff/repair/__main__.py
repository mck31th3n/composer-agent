"""CLI for repair planning and application."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .applier import apply_patch_plan
from .planner import generate_patch_plan


def main() -> None:
    parser = argparse.ArgumentParser(
        description="MusicDiff Repair - generate and apply patch plans",
        prog="musicdiff.repair",
    )
    parser.add_argument("--diff", required=True, help="Path to diff.json")
    parser.add_argument("--xml", required=True, help="Path to MusicXML file")
    parser.add_argument("--out", required=True, help="Path to output patch plan JSON")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate plan only (default)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply patch plan to MusicXML",
    )
    parser.add_argument(
        "--patched-out",
        default=None,
        help="Path to patched MusicXML output",
    )

    args = parser.parse_args()

    try:
        plan = generate_patch_plan(args.diff, args.xml)
        out_path = Path(args.out)
        with open(out_path, "w") as f:
            json.dump(plan.model_dump(exclude_none=True), f, indent=2)

        if args.apply:
            apply_patch_plan(args.xml, args.out, args.patched_out)
        elif not args.dry_run:
            pass

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
