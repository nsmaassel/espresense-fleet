"""CLI entry point: all output paths are private and outside this repository."""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .records import load_log, read_json, validate_schedule
from .scoring import coverage, score

ROOT = Path(__file__).resolve().parents[2]


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid command arguments; use --help. Arguments are not echoed.\n")


def external_output(value):
    path = Path(value).resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError("Reports and captures must be written outside this repository")
    if not path.parent.is_dir():
        raise ValueError("Output directory must already exist")
    return path


def write_report(path, report):
    descriptor, temporary = tempfile.mkstemp(prefix=".calibration-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None):
    parser = Parser(description="Private nearest-node and radio evidence; no device settings are changed.")
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("score", "coverage"):
        command = commands.add_parser(name)
        command.add_argument("--schedule", required=True)
        command.add_argument("--output", required=True, help="Explicit private path outside this repository")
        command.add_argument("--log", required=True)
    args = parser.parse_args(argv)
    try:
        schedule = validate_schedule(read_json(args.schedule))
        output = external_output(args.output)
        inputs = [args.schedule, args.log]
        if output in [Path(path).resolve() for path in inputs]:
            raise ValueError("Output cannot overwrite input evidence")
        log = load_log(args.log)
        report = score(log, schedule) if args.command == "score" else coverage(log, schedule)
        write_report(output, report)
        print(f"Capture {'complete' if log['capture']['complete'] else 'incomplete'}; {len(log['records'])} usable observations.")
        if args.command == "score":
            summary = report["summary"]
            print(f"Matched {summary['matched_windows']}/{summary['total_windows']} windows; {summary['mismatches']} mismatches; {summary['false_flips']} stationary flips.")
        else:
            print(f"Missing {report['missing_pairs']}/{len(report['pairs'])} directional pairs.")
        print("Diagnostics only; no whole-home or pet-safety claim. Keep all evidence private.")
        return 0
    except (ValueError, OSError, UnicodeError, TypeError, KeyError):
        print("Calibration failed: invalid input, unavailable transport, incomplete file, or inaccessible private output. No input data is echoed.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Capture interrupted; any partial file is incomplete evidence.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
