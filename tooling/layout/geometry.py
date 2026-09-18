"""Validated local geometry and coordinate transforms (all dimensions in metres)."""
import math
from pathlib import Path

import yaml


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _point(value, size):
    return isinstance(value, list) and len(value) == size and all(_number(v) for v in value)


def validate(g: dict) -> dict:
    """Validate and fill optional fields; retain unknown source metadata."""
    if not isinstance(g, dict) or not isinstance(g.get('floors'), list) or not g['floors']:
        raise ValueError('geometry requires a nonempty floors list')
    bounds = g.get('bounds')
    if not (isinstance(bounds, list) and len(bounds) == 2 and all(_point(p, 2) for p in bounds)
            and all(bounds[1][i] > bounds[0][i] for i in range(2))):
        raise ValueError('bounds must be two increasing [x, y] points')
    ids, node_ids = set(), set()
    for f in g['floors']:
        if not isinstance(f, dict) or not isinstance(f.get('id'), str) or not f['id'] or f['id'] in ids:
            raise ValueError('each floor needs a unique string id')
        ids.add(f['id'])
        if 'name' in f and not isinstance(f['name'], str):
            raise ValueError('floor name must be a string')
        if not _point(f.get('z'), 2) or f['z'][1] <= f['z'][0]:
            raise ValueError(f"{f['id']}: z must be increasing [base, ceiling]")
        local = f.get('local', {})
        if not isinstance(local, dict) or not all(_number(local.get(k)) and local[k] > 0 for k in ('w', 'h')):
            raise ValueError(f"{f['id']}: local w and h must be positive")
        p = f.setdefault('place', {})
        if not isinstance(p, dict):
            raise ValueError('place must be a mapping')
        for k, default in [('flip_h', False), ('flip_v', False), ('dx', 0), ('dy', 0)]:
            p.setdefault(k, default)
            if (k.startswith('flip') and not isinstance(p[k], bool)) or (k in ('dx', 'dy') and not _number(p[k])):
                raise ValueError(f'invalid placement {k}')
        f.setdefault('rooms', {})
        f.setdefault('nodes', {})
        if not isinstance(f['rooms'], dict) or not isinstance(f['nodes'], dict):
            raise ValueError('rooms and nodes must be mappings')
        for name, points in f['rooms'].items():
            if not isinstance(name, str) or not name or not isinstance(points, list) or len(points) < 3 or not all(_point(pt, 2) for pt in points):
                raise ValueError('room polygons require a string id and at least three [x, y] points')
        for name, point in f['nodes'].items():
            if not isinstance(name, str) or not name or name in node_ids or not _point(point, 3):
                raise ValueError('nodes require globally unique string ids and finite [x, y, relative_z] points')
            if not 0 <= point[2] <= f['z'][1] - f['z'][0]:
                raise ValueError(f'{name}: node height is outside floor z bounds')
            node_ids.add(name)
        if 'image' in f:
            img = f['image']
            if not isinstance(img, dict) or not isinstance(img.get('file'), str) or not _number(img.get('px_per_m')) or img['px_per_m'] <= 0 or not _point(img.get('origin_px'), 2):
                raise ValueError('image requires file, positive px_per_m and origin_px [x, y]')
    return g


def load(path: str | Path) -> dict:
    p = Path(path)
    g = validate(yaml.safe_load(p.read_text(encoding='utf-8')))
    g['_dir'] = p.resolve().parent
    return g


def to_house(floor: dict, x: float, y: float) -> tuple[float, float]:
    p, local = floor['place'], floor['local']
    return ((local['w'] - x if p['flip_h'] else x) + p['dx'],
            (local['h'] - y if p['flip_v'] else y) + p['dy'])


def rooms_in_house(floor: dict) -> dict:
    return {name: [list(to_house(floor, *pt)) for pt in pts] for name, pts in floor['rooms'].items()}


def nodes_in_house(floor: dict) -> dict:
    return {name: (*to_house(floor, x, y), floor['z'][0] + z) for name, (x, y, z) in floor['nodes'].items()}


def house_bounds(g: dict) -> list:
    """Enclose source bounds plus every transformed footprint, room and node."""
    points = list(g['bounds'])
    for f in g['floors']:
        local = [[0, 0], [f['local']['w'], f['local']['h']]]
        local.extend(pt for polygon in f['rooms'].values() for pt in polygon)
        local.extend(p[:2] for p in f['nodes'].values())
        points.extend(to_house(f, *p) for p in local)
    return [[round(min(p[i] for p in points), 10) for i in (0, 1)],
            [round(max(p[i] for p in points), 10) for i in (0, 1)]]
