"""Per-node preflight, single saves and bounded stored-state verification."""
import math
import re
import time

from tooling.fleet.transport import NodeError, Transport
from tooling.provision.espresense_set import build_form, current_values


def sanitized(value):
    if isinstance(value, str):
        value = re.sub(r"irk:[^\s,;]*", "irk:***", value, flags=re.IGNORECASE)
        return "".join(c if ord(c) >= 32 and ord(c) != 127 else "?" for c in value)
    return value


def compare(cfg, desired, endpoint):
    try:
        live = current_values(cfg)
        for key, value in live.items():
            key.encode("utf-8")
            if isinstance(value, str):
                value.encode("utf-8")
        if any(isinstance(value, float) and not math.isfinite(value) for value in live.values()):
            raise ValueError()
        # Use precisely the provisioner's supported omitted string fields.
        fields = dict(build_form(cfg, {}, endpoint))
        for key in fields.keys() - live.keys():
            live[key] = ""
    except (ValueError, TypeError, OverflowError):
        raise NodeError("unsupported live settings") from None
    names = {str: "a string", int: "an integer", float: "a number", bool: "a boolean"}
    for key, value in desired.items():
        if key not in live:
            raise NodeError(f"unknown managed field {endpoint}.{key}")
        original = live[key]
        valid = (type(value) is type(original) or
                 (type(original) is float and type(value) is int))
        if not valid:
            raise NodeError(f"{endpoint}.{key} requires {names[type(original)]}")
    try:
        form = build_form(cfg, desired, endpoint)
    except (ValueError, TypeError, OverflowError):
        raise NodeError("cannot construct settings form") from None
    changes = {key: {"before": sanitized(live[key]), "after": sanitized(value)}
               for key, value in desired.items() if live[key] != value}
    return changes, form


def inspect(node, transport):
    result = {"id": node.id, "status": "converged", "changes": {}, "saved": [],
              "restart": "not_requested", "verification": "not_attempted", "error": None}
    if node.address is None:
        result["status"] = "skipped"
        return result
    if not node.desired:
        result.update(status="error", error="node has no managed settings")
        return result
    try:
        for endpoint, desired in node.desired.items():
            changes, _ = compare(transport.read(endpoint), desired, endpoint)
            if changes:
                result["changes"][endpoint] = changes
        result["status"] = "drift" if result["changes"] else "converged"
        result["verification"] = "stored" if not result["changes"] else "not_attempted"
    except NodeError as error:
        result.update(status="error", error=str(error))
    return result


def verify(node, transport, duration, interval):
    deadline = time.monotonic() + duration
    while time.monotonic() < deadline:
        converged = True
        try:
            for endpoint, desired in node.desired.items():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                cfg = transport.read(endpoint, timeout=min(transport.timeout, remaining))
                changes, _ = compare(cfg, desired, endpoint)
                converged = converged and not changes
            if converged:
                return True
        except NodeError:
            pass  # Reads only: a restarting node may be temporarily unavailable.
        time.sleep(max(0, min(interval, deadline - time.monotonic())))
    return False


def apply(node, transport, result, no_restart, verify_timeout, poll_interval):
    if result["status"] != "drift":
        return
    for endpoint in list(result["changes"]):
        try:
            changes, form = compare(transport.read(endpoint), node.desired[endpoint], endpoint)
            if not changes:
                del result["changes"][endpoint]
                continue
            result["changes"][endpoint] = changes
        except NodeError as error:
            result.update(status="partial" if result["saved"] else "error", error=str(error))
            return
        try:
            transport.save(endpoint, form)
            result["saved"].append(endpoint)
            result["restart"] = "pending"
        except NodeError as error:
            result.update(status="partial" if result["saved"] else "unconfirmed", error=str(error))
            return
    restart_failed = False
    if result["saved"]:
        result["restart"] = "pending" if no_restart else "acknowledged"
        if not no_restart:
            try:
                transport.restart()
            except NodeError:
                result["restart"] = "unconfirmed"
                restart_failed = True
    if verify(node, transport, verify_timeout, poll_interval):
        result["verification"] = "stored"
        result["status"] = "unconfirmed" if restart_failed else "converged"
        result["error"] = "restart response unconfirmed; operational validation required" if restart_failed else None
    else:
        result.update(status="unconfirmed", verification="failed", error="managed settings verification timed out")


def run(nodes, *, command, yes=False, no_restart=False, timeout=5, verify_timeout=30, poll_interval=1):
    transports = {node.id: Transport(node.address, timeout) for node in nodes if node.address}
    results = [inspect(node, transports.get(node.id)) for node in nodes]
    if command == "apply" and yes:
        for node, result in zip(nodes, results):
            apply(node, transports.get(node.id), result, no_restart, verify_timeout, poll_interval)
    counts = {status: sum(result["status"] == status for result in results)
              for status in ("converged", "drift", "skipped", "error", "partial", "unconfirmed")}
    eligible = any(node.address and node.desired for node in nodes)
    failed = not eligible or any(counts[status] for status in ("error", "partial", "unconfirmed"))
    return {"schema_version": 1, "command": command, "preview": command == "apply" and not yes,
            "nodes": results, "counts": counts, "error": None if eligible else "no eligible nodes selected",
            "exit_code": 2 if failed else 1 if counts["drift"] else 0,
            "scope": "stored settings only; MQTT, identity, coverage and room accuracy require operator validation"}
