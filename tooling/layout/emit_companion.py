"""Emit Companion's floors/nodes fragment from local geometry."""
import argparse
from pathlib import Path
import yaml

try:
    from .geometry import house_bounds, load, nodes_in_house, rooms_in_house
except ImportError:
    from geometry import house_bounds, load, nodes_in_house, rooms_in_house


def companion(g: dict) -> dict:
    result = {'floors': [], 'nodes': []}
    bounds = house_bounds(g)
    for floor in g['floors']:
        floor_id = floor['id']
        result['floors'].append({
            'id': floor_id, 'name': floor.get('name', floor_id),
            'bounds': [[*bounds[0], floor['z'][0]], [*bounds[1], floor['z'][1]]],
            'rooms': [{'id': name, 'name': name.replace('-', ' ').title(), 'points': [[round(v, 10) for v in point] for point in points]}
                      for name, points in rooms_in_house(floor).items()],
        })
        for name, point in nodes_in_house(floor).items():
            node = {'id': name, 'name': name.replace('-', ' ').title(), 'point': [round(v, 10) for v in point], 'floors': [floor_id]}
            if name in floor['rooms']:
                node['room'] = name
            result['nodes'].append(node)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('geometry', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    try:
        data = companion(load(args.geometry))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(yaml.safe_dump(data, sort_keys=False), encoding='utf-8')
    except (ValueError, OSError, yaml.YAMLError) as error:
        parser.exit(2, f'Error: {error}\n')
    print(f"Done: wrote {len(data['floors'])} floors and {len(data['nodes'])} nodes to {args.out}")


if __name__ == '__main__':
    main()
