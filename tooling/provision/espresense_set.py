"""Read or update a node over HTTP, preserving unmodified fields and masked passwords.

    python tooling/provision/espresense_set.py <host> <endpoint> [key=value ...]

Endpoints: main, hardware, extras. Use password=- to prompt locally without echo.
With no changes, prints current values with secrets redacted. Changes restart the
node unless --no-restart is given. Only use serial during initial flashing.
"""
import argparse
import getpass
import json
import math
import re
import urllib.error
import urllib.parse
import urllib.request


def get(base: str, endpoint: str) -> dict:
    with urllib.request.urlopen(f"{base}/wifi/{endpoint}", timeout=10) as response:
        return json.load(response)


def sensitive(key: str) -> bool:
    return any(word in key.lower() for word in ("password", "pass", "secret", "token", "irk", "key"))


def redact(value):
    if isinstance(value, dict):
        return {k: "***" if sensitive(k) else redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return re.sub(r"irk:[0-9a-fA-F]+", "irk:***", value)
    return value


def current_values(cfg: dict) -> dict:
    if not isinstance(cfg, dict) or any(not isinstance(cfg.get(k), dict) for k in ("defaults", "values")):
        raise ValueError("node response must contain defaults and values objects; refusing to replace settings")
    merged = {**cfg["defaults"], **cfg["values"]}
    if not merged or any(not isinstance(k, str) or not isinstance(v, (str, bool, int, float)) for k, v in merged.items()):
        raise ValueError("node returned empty or unsupported settings; refusing to replace settings")
    return merged


def build_form(cfg: dict, overrides: dict, endpoint: str | None = None) -> list[tuple[str, str]]:
    merged = current_values(cfg)
    # HeadlessWiFiSettings omits empty strings/passwords even from defaults.
    # These fields are declared in ESPresense v4.0.6 src/main.cpp.
    if endpoint == "main":
        for key in ("wifi-ssid", "wifi-password", "mqtt_host", "mqtt_user", "mqtt_pass"):
            merged.setdefault(key, "")
    unknown = overrides.keys() - merged.keys()
    if unknown:
        raise ValueError("unknown settings: " + ", ".join(sorted(unknown)))
    fields = []
    for key, original in merged.items():
        value = overrides.get(key, original)
        if isinstance(original, bool):
            normalized = str(value).lower()
            if normalized not in ("true", "false", "1", "0", "on", "off", "yes", "no"):
                raise ValueError(f"{key} requires true or false")
            if normalized in ("true", "1", "on", "yes"):
                fields.append((key, "1"))
        else:
            if key in overrides and isinstance(original, (int, float)):
                try:
                    number = int(value) if isinstance(original, int) else float(value)
                    if not math.isfinite(number):
                        raise ValueError()
                except (ValueError, TypeError, OverflowError):
                    raise ValueError(f"{key} requires a finite number") from None
            fields.append((key, str(value)))
    return fields


def host(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.-]*(?::[0-9]+)?|\[[0-9a-fA-F:]+\](?::[0-9]+)?", value):
        raise argparse.ArgumentTypeError("use a hostname or IP, optionally with port, without a URL scheme or path")
    return value


def assignment(value: str) -> tuple[str, str]:
    key, sep, text = value.partition("=")
    if not sep or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        raise argparse.ArgumentTypeError("settings must use key=value")
    return key, text


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("host", type=host)
    parser.add_argument("endpoint", choices=("main", "hardware", "extras"))
    parser.add_argument("changes", nargs="*", type=assignment)
    parser.add_argument("--no-restart", action="store_true")
    args = parser.parse_intermixed_args(argv)
    overrides = dict(args.changes)
    if len(overrides) != len(args.changes):
        parser.error("each setting may only be supplied once")
    for key, value in overrides.items():
        if sensitive(key) and value != "-":
            parser.error(f"use {key}=- to enter secrets locally without putting them in shell history")
    base = f"http://{args.host}"
    try:
        cfg = get(base, args.endpoint)
        current_values(cfg)
        if not overrides:
            print(json.dumps(redact(cfg["values"]), indent=2))
            return
        # Validate keys and ordinary values before prompting or sending anything.
        build_form(cfg, overrides, endpoint=args.endpoint)
        overrides = {k: getpass.getpass(f"{k}: ") if v == "-" else v for k, v in overrides.items()}
        body = urllib.parse.urlencode(build_form(cfg, overrides, endpoint=args.endpoint)).encode()
        print(f"Saving /wifi/{args.endpoint}: {redact(overrides)}")
        req = urllib.request.Request(f"{base}/wifi/{args.endpoint}", data=body, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as response:
            print(f"SAVED: HTTP {response.status}")
    except ValueError as error:
        parser.error(str(error))
    except (OSError, urllib.error.URLError):
        parser.exit(1, "Node request failed; settings may be unchanged or saved. Check the node before retrying.\n")

    if not args.no_restart:
        try:
            request = urllib.request.Request(f"{base}/restart", data=b"", method="POST")
            with urllib.request.urlopen(request, timeout=2):
                pass
        except (OSError, urllib.error.URLError):
            print("Restart response not confirmed; the node may already be reconnecting.")
    print("DONE when: espresense/rooms/<room>/status reports online and fresh telemetry arrives. Move the node to a wall adapter.")


if __name__ == "__main__":
    main()
