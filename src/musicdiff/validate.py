"""Schema validation CLI."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema

from .exceptions import ValidationError


def validate_diff_json(diff_path: str | Path) -> bool:
    """
    Validate diff.json against the schema.

    Args:
        diff_path: Path to diff.json file

    Returns:
        True if valid

    Raises:
        ValidationError: If validation fails
    """
    diff_path = Path(diff_path)
    if not diff_path.exists():
        raise ValidationError(f"File not found: {diff_path}")

    # Load schema from contracts
    schema_path = Path(__file__).parent.parent.parent.parent / "contracts" / "schema.json"
    if not schema_path.exists():
        # Try alternate location
        schema_path = Path(__file__).parent.parent.parent / "contracts" / "schema.json"
    if not schema_path.exists():
        # Fallback: look relative to cwd
        schema_path = Path("contracts/schema.json")

    if not schema_path.exists():
        raise ValidationError(f"Schema file not found. Tried: {schema_path}")

    try:
        with open(schema_path) as f:
            schema = json.load(f)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid schema JSON: {e}") from e

    try:
        with open(diff_path) as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ValidationError(f"Invalid diff JSON: {e}") from e

    try:
        jsonschema.validate(instance=data, schema=schema)
    except jsonschema.ValidationError as e:
        raise ValidationError(f"Schema validation failed: {e.message}") from e

    return True


def main() -> None:
    """CLI entrypoint for validation."""
    if len(sys.argv) != 2:
        print("Usage: python -m musicdiff.validate <diff.json>", file=sys.stderr)
        sys.exit(1)

    diff_path = sys.argv[1]

    try:
        validate_diff_json(diff_path)
        print("Valid")
        sys.exit(0)
    except ValidationError as e:
        print(f"Invalid: {e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
