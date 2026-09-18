"""Run with python -m tooling.fleet diff|apply INVENTORY."""
import argparse
import json
import math

from tooling.fleet.inventory import InventoryError, load
from tooling.fleet.reconcile import run


def positive(value):
    number = float(value)
    if not math.isfinite(number) or not 0 < number <= 300:
        raise argparse.ArgumentTypeError("duration must be finite, positive and at most 300 seconds")
    return number


def report_text(report):
    if report["preview"]:
        print("PREVIEW: no settings will be written. Use apply --yes to save.")
    print("NODE\tSTATUS\tSAVED\tRESTART\tVERIFICATION")
    for node in report["nodes"]:
        print(f'{node["id"]}\t{node["status"]}\t{",".join(node["saved"]) or "-"}\t{node["restart"]}\t{node["verification"]}')
        for endpoint, changes in node["changes"].items():
            for key, values in changes.items():
                print(f'  {endpoint}.{key}: {json.dumps(values["before"])} -> {json.dumps(values["after"])}')
        if node["error"]:
            print(f'  {node["error"]}')
    print("Counts: " + ", ".join(f"{key}={value}" for key, value in report["counts"].items()))
    if report["error"]:
        print(report["error"])
    print(report["scope"])


def main(argv=None):
    parser = argparse.ArgumentParser(description="Inspect or reconcile external private fleet inventory.")
    parser.add_argument("command", choices=("diff", "apply"))
    parser.add_argument("inventory")
    parser.add_argument("--node", action="append", default=[], help="select a stable ID; repeat for several")
    parser.add_argument("--yes", action="store_true", help="authorize writes for apply")
    parser.add_argument("--no-restart", action="store_true", help="verify stored settings, leaving restart pending")
    parser.add_argument("--json", action="store_true", help="emit one structured report")
    parser.add_argument("--timeout", type=positive, default=5, help="per-request timeout in seconds")
    parser.add_argument("--verify-timeout", type=positive, default=30, help="readback polling budget in seconds")
    parser.add_argument("--poll-interval", type=positive, default=1, help="delay between verification reads")
    args = parser.parse_args(argv)
    try:
        nodes = load(args.inventory, args.node)
        report = run(nodes, command=args.command, yes=args.yes, no_restart=args.no_restart,
                     timeout=args.timeout, verify_timeout=args.verify_timeout, poll_interval=args.poll_interval)
    except InventoryError as error:
        report = {"schema_version": 1, "command": args.command, "preview": args.command == "apply" and not args.yes,
                  "nodes": [], "counts": {}, "error": str(error), "exit_code": 2,
                  "scope": "inventory rejected before network access"}
    if args.json:
        print(json.dumps(report, indent=2, allow_nan=False))
    else:
        report_text(report)
    return report["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
