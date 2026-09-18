"""Validate the entire external inventory before resolving selected nodes."""
from dataclasses import dataclass
import ipaddress
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

import yaml

from tooling.provision.espresense_set import sensitive


ENDPOINTS = ("main", "hardware", "extras")


class InventoryError(ValueError):
    """An input contract violation with a safe, value-free description."""


@dataclass(frozen=True)
class Node:
    id: str
    address: str | None
    desired: dict


def mapping(value, allowed):
    if not isinstance(value, dict) or any(not isinstance(k, str) or k not in allowed for k in value):
        raise InventoryError("invalid object or unknown inventory key")
    return value


def text(value):
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise InventoryError("expected nonempty text without control characters")
    if "irk:" in value.lower():
        raise InventoryError("enrollment credentials are forbidden")
    utf8(value)
    return value


def utf8(value):
    try:
        value.encode("utf-8")
    except UnicodeError:
        raise InventoryError("inventory text must be UTF-8 encodable") from None


def port(value):
    if type(value) is not int or not 1 <= value <= 65535:
        raise InventoryError("port must be an integer from 1 to 65535")
    return value


def address(value, allow_port=True):
    value = text(value)
    if not allow_port:
        try:
            return ipaddress.ip_address(value).compressed
        except ValueError:
            pass
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.:-]*|\[[0-9a-fA-F:]+\](?::[0-9]+)?", value):
        raise InventoryError("address must be a hostname or IP with optional port")
    try:
        parsed = urlsplit("http://" + value)
        hostname = parsed.hostname
        if not hostname or parsed.path or parsed.query or parsed.fragment or parsed.username:
            raise ValueError()
        explicit_port = parsed.port
        if value.endswith(":") or (explicit_port is not None and not allow_port):
            raise ValueError()
        if explicit_port is not None:
            port(explicit_port)
        try:
            normalized = ipaddress.ip_address(hostname).compressed
        except ValueError:
            if re.fullmatch(r"[0-9.]+", hostname) or ":" in hostname:
                raise ValueError() from None
            normalized = hostname.rstrip(".").lower()
            if len(normalized) > 253 or any(not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                                            for label in normalized.split(".")):
                raise ValueError()
        if ":" in normalized and allow_port:
            normalized = f"[{normalized}]"
        return normalized + (f":{explicit_port}" if explicit_port not in (None, 80) else "")
    except ValueError:
        raise InventoryError("invalid address or port") from None


def settings(value):
    result = {}
    for endpoint, fields in mapping(value, ENDPOINTS).items():
        if not isinstance(fields, dict):
            raise InventoryError("endpoint settings must be objects")
        result[endpoint] = {}
        for key, desired in fields.items():
            if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", key):
                raise InventoryError("invalid setting name")
            if sensitive(key) or key in ("wifi-ssid", "mqtt_user"):
                raise InventoryError("credentials and Wi-Fi configuration require human provisioning")
            if type(desired) not in (str, bool, int, float) or (isinstance(desired, float) and not math.isfinite(desired)):
                raise InventoryError("settings must be finite scalar values")
            if isinstance(desired, str):
                utf8(desired)
                if "irk:" in desired.lower() or any(ord(c) < 32 or ord(c) == 127 for c in desired):
                    raise InventoryError("credentials or control characters in setting values are forbidden")
            if key == "mqtt_port":
                port(desired)
            if key == "mqtt_host":
                desired = address(desired, allow_port=False)
            result[endpoint][key] = desired
    return result


def resolve(document, selected=()):
    root = mapping(document, {"site", "broker", "defaults", "nodes"})
    if "site" in root:
        text(root["site"])
    defaults = settings(root.get("defaults", {}))
    if "broker" in root:
        broker = mapping(root["broker"], {"host", "port"})
        if "host" not in broker:
            raise InventoryError("broker requires a host")
        desired_broker = {"mqtt_host": address(broker["host"], allow_port=False)}
        if "port" in broker:
            desired_broker["mqtt_port"] = port(broker["port"])
        main = defaults.setdefault("main", {})
        if any(key in main and main[key] != value for key, value in desired_broker.items()):
            raise InventoryError("broker conflicts with defaults")
        main.update(desired_broker)
    entries = root.get("nodes")
    if not isinstance(entries, list) or not entries:
        raise InventoryError("inventory requires a nonempty nodes list")
    nodes, ids, addresses = [], set(), set()
    for entry in entries:
        row = mapping(entry, {"id", "address", "room", "settings", "target", "mac", "status"})
        node_id = text(row.get("id"))
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", node_id) or node_id in ids:
            raise InventoryError("node IDs must be unique and use letters, digits, dots, underscores or hyphens")
        ids.add(node_id)
        for key in ("target", "mac", "status"):
            if row.get(key) is not None:
                text(row[key])
        host = address(row["address"]) if row.get("address") is not None else None
        if host and host in addresses:
            raise InventoryError("duplicate node address")
        addresses.add(host)
        overrides = settings(row.get("settings", {}))
        desired = {endpoint: dict(fields) for endpoint, fields in defaults.items()}
        if row.get("room") is not None:
            room = text(row["room"])
            if "room" in overrides.get("main", {}) and overrides["main"]["room"] != room:
                raise InventoryError("node room conflicts with settings")
            desired.setdefault("main", {})["room"] = room
        for endpoint, fields in overrides.items():
            desired.setdefault(endpoint, {}).update(fields)
        nodes.append(Node(node_id, host, {endpoint: desired[endpoint] for endpoint in ENDPOINTS if desired.get(endpoint)}))
    if len(set(selected)) != len(selected) or set(selected) - ids:
        raise InventoryError("selection contains duplicate or unknown node IDs")
    return [node for node in nodes if not selected or node.id in selected]


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys instead of silently replacing desired state."""


def unique_mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if not isinstance(key, str) or key in result:
            raise InventoryError("YAML keys must be unique strings")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load(path, selected=()):
    try:
        document = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=UniqueLoader)
        return resolve(document, selected)
    except (OSError, UnicodeError, yaml.YAMLError, RecursionError):
        raise InventoryError("cannot read inventory or invalid YAML") from None
