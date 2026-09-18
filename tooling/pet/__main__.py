"""Offline preparation commands. Inputs and reports remain private."""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from .replay import parse_json, read_config, read_events, replay

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


def write_text(path, content):
    descriptor, temporary = tempfile.mkstemp(prefix=".pet-replay-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        Path(temporary).replace(path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main(argv=None):
    parser = Parser(description="Prepare private pet advisories without contacting devices.")
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("replay")
    command.add_argument("--config", required=True)
    command.add_argument("--events", required=True)
    command.add_argument("--output", required=True)
    command = commands.add_parser("package")
    command.add_argument("--config", required=True)
    command.add_argument("--bindings", required=True)
    command.add_argument("--output", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "package":
            import yaml
            from .package import build_package
            output = external_output(args.output, [args.config, args.bindings])
            bindings = Path(args.bindings)
            if bindings.stat().st_size > 1024 * 1024:
                raise ValueError("Bindings too large")
            package = build_package(read_config(args.config), parse_json(bindings.read_text(encoding="utf-8")))
            write_text(output, yaml.safe_dump(package, sort_keys=False, allow_unicode=True))
            print("Private package generated with outputs disabled. No actions were delivered.")
            return 0
        output = external_output(args.output, [args.config, args.events])
        report = replay(read_config(args.config), read_events(args.events))
        write_text(output, json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n")
        count = sum(len(row["intents"]) for row in report["snapshots"])
        print(f"Replayed {len(report['snapshots'])} events; {count} advisory intents. No actions were delivered. Keep the report private.")
        return 0
    except (ValueError, OSError, UnicodeError, TypeError, KeyError, RecursionError):
        print("Pet preparation failed: invalid input or inaccessible private output. Input data is not echoed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
