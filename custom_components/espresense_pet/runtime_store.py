"""Private adapter envelope; camera references never enter entity attributes."""
import copy
from pathlib import Path
import re

from .config import fields
from .engine import Engine


def storage_expected(path):
    """Run in HA's executor before load: HA may quarantine corruption as None.

    Retain the pinned HA quarantine evidence across later restarts. A valid
    restored file may coexist with quarantined files; only missing data is fatal.
    """
    path = Path(path)
    return path.exists() or next(path.parent.glob(path.name + ".corrupt.*"), None) is not None


def restore(config, stored):
    if stored is None:
        return Engine(config), {}
    fields(stored, ("schema", "engine", "camera_sources"))
    if type(stored["schema"]) is not int or stored["schema"] != 1:
        raise ValueError("Unsupported private storage schema")
    engine = Engine(config, restored=stored["engine"])
    sources = stored["camera_sources"]
    if not isinstance(sources, dict) or sources.keys() - set(engine.alert["doors"]):
        raise ValueError("Invalid incident camera sources")
    for door, source in sources.items():
        fields(source, ("camera", "event_id"))
        if (source["camera"] != config["doors"][door]["camera"] or source["camera"] is None
                or not isinstance(source["event_id"], str)
                or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", source["event_id"])):
            raise ValueError("Invalid incident camera source")
    return engine, copy.deepcopy(sources)


def envelope(engine, sources):
    return {"schema": 1, "engine": engine.dump(), "camera_sources": copy.deepcopy(sources)}
