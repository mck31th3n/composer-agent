"""Main CLI entrypoint."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .align import align_from_metadata
from .diff import generate_diffs, generate_report
from .exceptions import MusicDiffError, ParseError
from .parser_midi import parse_midi
from .parser_xml import (
    get_last_parse_warnings,
    get_last_unsupported_features,
    parse_musicxml,
)
from .repair.applier import apply_patch_plan
from .repair.planner import generate_patch_plan


def main() -> None:
    """Main CLI entrypoint."""
    if len(sys.argv) > 1 and sys.argv[1] in ("patch", "apply"):
        _main_patch_commands()
        return
    _main_diff()


def _main_patch_commands() -> None:
    subcommand = sys.argv[1]
    if subcommand == "patch":
        parser = argparse.ArgumentParser(
            description="MusicDiff - Patch plan generator",
            prog="musicdiff patch",
        )
        parser.add_argument("--diff", required=True, help="Path to diff.json")
        parser.add_argument("--xml", required=True, help="Path to MusicXML file")
        parser.add_argument("--out", required=True, help="Path to output patch plan JSON")
        args = parser.parse_args(sys.argv[2:])

        try:
            plan = generate_patch_plan(args.diff, args.xml)
            out_path = Path(args.out)
            with open(out_path, "w") as f:
                f.write(plan.model_dump_json(indent=2))
            print(f"Wrote patch plan to {out_path}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        return

    if subcommand == "apply":
        parser = argparse.ArgumentParser(
            description="MusicDiff - Patch plan applier",
            prog="musicdiff apply",
        )
        parser.add_argument("--xml", required=True, help="Path to MusicXML file")
        parser.add_argument("--patch", required=True, help="Path to patch plan JSON")
        parser.add_argument(
            "--out",
            required=False,
            default=None,
            help="Path to output MusicXML (default: patched.musicxml)",
        )
        args = parser.parse_args(sys.argv[2:])

        try:
            out_path = apply_patch_plan(args.xml, args.patch, args.out)
            print(f"Wrote patched MusicXML to {out_path}")
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)


def _main_diff() -> None:
    parser = argparse.ArgumentParser(
        description="MusicDiff - Notation↔MIDI measure-aware diff tool",
        prog="musicdiff",
    )
    parser.add_argument(
        "--xml",
        required=True,
        help="Path to MusicXML file",
    )
    parser.add_argument(
        "--midi",
        required=True,
        help="Path to MIDI file",
    )
    parser.add_argument(
        "--out",
        required=True,
        help="Path to output JSON file",
    )
    parser.add_argument(
        "--tempo",
        type=float,
        default=None,
        help="Override tempo (BPM). Default: infer from MusicXML or 120",
    )

    args = parser.parse_args()

    warnings: list[str] = []

    try:
        # Parse MusicXML - single pass returns events, metadata, AND unsupported features
        xml_path = Path(args.xml)
        score_events, score_metadata = parse_musicxml(xml_path)
        unsupported_features = get_last_unsupported_features()

        # Add warnings for missing tempo/time sig
        tempo_missing, time_sig_missing = get_last_parse_warnings()
        if tempo_missing:
            warnings.append(
                "E_TEMPO_MISSING: No tempo found in MusicXML, using default 120 BPM"
            )
        if time_sig_missing:
            warnings.append(
                "E_TIMESIG_MISSING: No time signature found in MusicXML, using default 4/4"
            )

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ParseError as e:
        print(f"Error [{e.code}]: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        # Parse MIDI
        midi_path = Path(args.midi)
        midi_events, midi_metadata = parse_midi(midi_path)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except ParseError as e:
        print(f"Error [{e.code}]: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        # Align events - now returns tempo_bpm_used as third element
        aligned_pairs, alignment_summary, tempo_bpm_used = align_from_metadata(
            score_events=score_events,
            midi_events=midi_events,
            score_metadata=score_metadata,
            midi_metadata=midi_metadata,
            tempo_override=args.tempo,
        )

        if tempo_missing and args.tempo is None and not midi_metadata.has_tempo_map:
            alignment_summary = alignment_summary.model_copy(
                update={"tempo_source": "default_120"}
            )

        # Lower confidence if unsupported features are present
        if unsupported_features:
            new_confidence = alignment_summary.alignment_confidence
            significant = {"time_sig_change", "key_sig_change"}
            if any(f.feature in significant for f in unsupported_features):
                new_confidence = "low"
            elif alignment_summary.alignment_confidence == "high":
                new_confidence = "medium"
            if new_confidence != alignment_summary.alignment_confidence:
                alignment_summary = alignment_summary.model_copy(
                    update={"alignment_confidence": new_confidence}
                )

        # Warn on unsupported features
        for feature in unsupported_features:
            warnings.append(
                f"UNSUPPORTED_FEATURE: {feature.feature} at measure {feature.measure}"
            )

        # Generate diffs using the ACTUAL tempo used in alignment
        diffs = generate_diffs(
            aligned_pairs=aligned_pairs,
            unsupported_features=unsupported_features,
        )

        # Generate report with correct tempo
        report = generate_report(
            xml_path=str(xml_path),
            midi_path=str(midi_path),
            diffs=diffs,
            metadata=score_metadata,
            alignment_summary=alignment_summary,
            unsupported_features=unsupported_features,
            warnings=warnings,
            tempo_bpm_used=tempo_bpm_used,
        )

        # Write output
        out_path = Path(args.out)
        with open(out_path, "w") as f:
            json.dump(report.model_dump(), f, indent=2)

        print(f"Wrote diff report to {out_path}")
        print(f"  Total measures: {report.total_measures}")
        print(f"  Diffs found: {len(report.diffs)}")
        print(f"  Alignment confidence: {alignment_summary.alignment_confidence}")

    except MusicDiffError as e:
        print(f"Error [{e.code}]: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
