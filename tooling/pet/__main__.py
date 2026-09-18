"""Offline preparation commands. Inputs and reports remain private."""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .replay import read_config, read_events, replay

ROOT = Path(__file__).resolve().parents[2]


class Parser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "Invalid arguments; use --help. Arguments are not echoed.\n")


def external_output(value, inputs):
    path = Path(value).resolve()
    if path == ROOT or ROOT in path.parents or not path.parent.is_dir():
        raise ValueError("Choose an existing private output directory outside this repository")
    if path in {Path(value).resolve() for value in inputs}:
        raise ValueError("Output cannot replace input evidence")
    return path


def write_report(path, report):
    descriptor, temporary = tempfile.mkstemp(prefix=".pet-replay-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(report, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None):
    parser = Parser(description="Replay private pet advisory evidence without contacting devices.")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("replay")
    command.add_argument("--config", required=True)
    command.add_argument("--events", required=True)
    command.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        output = external_output(args.output, [args.config, args.events])
        report = replay(read_config(args.config), read_events(args.events))
        write_report(output, report)
        count = sum(len(row["intents"]) for row in report["snapshots"])
        print(f"Replayed {len(report['snapshots'])} events; {count} advisory intents. No actions were delivered. Keep the report private.")
        return 0
    except (ValueError, OSError, UnicodeError, TypeError, KeyError, RecursionError):
        print("Pet replay failed: invalid input or inaccessible private output. Input data is not echoed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
