"""Read-only MQTT normalization and injectable bounded capture state machine."""
import json
import time

from .records import (MAX_MS, MAX_RECORDS, alias, fields, integer, number,
                      parse_json, validate_record, validate_schedule)


def validate_config(config, schedule):
    validate_schedule(schedule)
    fields(config, ("schema", "device_alias", "node_map"))
    alias(config["device_alias"])
    mapping = config["node_map"]
    if not isinstance(mapping, dict) or not mapping:
        raise ValueError("Capture requires an explicit node map")
    for slug, node in mapping.items():
        alias(slug)
        alias(node)
    if len(set(mapping.values())) != len(mapping) or set(mapping.values()) != set(schedule["nodes"]):
        raise ValueError("Capture node map must match every schedule node exactly once")
    return config


def topics(config):
    result = []
    for receiver in config["node_map"]:
        result.append((f'espresense/devices/{config["device_alias"]}/{receiver}', 0))
        result.append((f"espresense/rooms/{receiver}/telemetry", 0))
        for peer in config["node_map"]:
            if peer != receiver:
                result.append((f"espresense/devices/node:{peer}/{receiver}", 0))
    return result


def normalize(topic, payload, retained, elapsed_ms, config):
    if not isinstance(topic, str) or len(topic) > 512:
        return None, "ignored"
    parts = topic.split("/")
    mapping = config["node_map"]
    if len(parts) != 4 or parts[0] != "espresense":
        return None, "ignored"
    kind, peer = None, None
    if parts[1] == "rooms" and parts[2] in mapping and parts[3] == "telemetry":
        kind, node = "wifi", mapping[parts[2]]
    elif parts[1] == "devices" and parts[3] in mapping:
        node = mapping[parts[3]]
        if parts[2] == config["device_alias"]:
            kind = "device"
        elif parts[2].startswith("node:") and parts[2][5:] in mapping:
            kind, peer = "node_distance", mapping[parts[2][5:]]
    if kind is None:
        return None, "ignored"
    if retained:
        return None, "retained"
    try:
        if len(payload) > 16_384:
            return None, "invalid"
        data = parse_json(payload)
        if not isinstance(data, dict):
            return None, "invalid"
        result = {"schema": 1, "kind": kind, "elapsed_ms": elapsed_ms, "node": node}
        if kind != "wifi":
            result["distance_m"] = data["distance"]
        if kind == "wifi" or (kind == "device" and "rssi" in data):
            result["rssi_dbm"] = data["rssi"]
        if peer is not None:
            result["peer"] = peer
        return validate_record(result), None
    except (ValueError, TypeError, KeyError, UnicodeError):
        return None, "invalid"


def capture(stream, config, schedule, duration_ms, client, clock=time.monotonic,
            *, host, port=1883, connect_timeout=10, on_started=None):
    """The caller supplies an outer process deadline for DNS/socket/shutdown hangs."""
    validate_config(config, schedule)
    integer(duration_ms, 1, MAX_MS)
    number(connect_timeout, 0.1, 30)
    integer(port, 1, 65535)
    if duration_ms < schedule["stops"][-1]["end_ms"]:
        raise ValueError("Capture duration must cover the schedule")

    def write(row):
        stream.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        stream.flush()

    write({"schema": 1, "kind": "capture_start", "source": "mqtt", "duration_ms": duration_ms})
    state = {"start": None, "reason": None, "mid": None}
    counts = {"records": 0, "retained": 0, "ignored": 0, "invalid": 0}
    subscriptions = topics(config)
    connecting_since = clock()

    def on_connect(connected, userdata, flags, reason, properties):
        if reason.is_failure:
            state["reason"] = "connection"
            return
        code, state["mid"] = connected.subscribe(subscriptions)
        if code != 0:
            state["reason"] = "subscription"

    def on_subscribe(connected, userdata, mid, reasons, properties):
        if mid != state["mid"] or len(reasons) != len(subscriptions) or any(r.is_failure for r in reasons):
            state["reason"] = "subscription"
        elif state["start"] is None:
            state["start"] = clock()
            if on_started is not None:
                on_started()

    def on_disconnect(connected, userdata, flags, reason, properties):
        state["reason"] = "disconnect"

    def on_message(connected, userdata, message):
        if state["start"] is None or state["reason"] is not None:
            counts["ignored"] += 1
            return
        elapsed_ms = int((clock() - state["start"]) * 1000)
        if elapsed_ms >= duration_ms:
            return
        row, reason = normalize(message.topic, message.payload, message.retain, elapsed_ms, config)
        if reason:
            counts[reason] += 1
        elif counts["records"] >= MAX_RECORDS:
            state["reason"] = "limit"
        else:
            write(row)
            counts["records"] += 1
        if sum(counts.values()) >= 1_000_000:
            state["reason"] = "limit"

    client.on_connect, client.on_subscribe = on_connect, on_subscribe
    client.on_message, client.on_disconnect = on_message, on_disconnect
    client.connect_timeout = connect_timeout
    try:
        if client.connect(host, port, keepalive=30) != 0:
            state["reason"] = "connection"
        while state["reason"] is None:
            now = clock()
            if state["start"] is None:
                remaining = connect_timeout - (now - connecting_since)
                if remaining <= 0:
                    state["reason"] = "connection"
                    break
            else:
                remaining = duration_ms / 1000 - (now - state["start"])
                if remaining <= 0:
                    state["reason"] = "duration"
                    break
            if client.loop(timeout=min(0.25, remaining)) != 0:
                state["reason"] = "transport"
    except KeyboardInterrupt:
        state["reason"] = "interrupted"
    except Exception:
        # Network libraries can include broker/user details in their exceptions.
        state["reason"] = "transport"
    elapsed_ms = min(duration_ms, int((clock() - state["start"]) * 1000)) if state["start"] is not None else 0
    try:
        client.on_disconnect = None
        if client.disconnect() != 0:
            state["reason"] = "transport"
    except Exception:
        state["reason"] = "transport"
    if state["reason"] == "duration":
        # The deadline was reached; float-to-integer truncation must not subtract
        # a millisecond from a completed capture's exact requested duration.
        elapsed_ms = duration_ms
    footer = {"schema": 1, "kind": "capture_end", "elapsed_ms": elapsed_ms,
              "complete": state["reason"] == "duration", "reason": state["reason"], **counts}
    write(footer)
    return footer
