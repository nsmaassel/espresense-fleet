"""Build one self-contained offline HTML layout editor from geometry.yaml."""
import argparse
import base64
import copy
import hashlib
import json
import struct
from pathlib import Path

import yaml
try:
    from .geometry import load, validate
except ImportError:
    from geometry import load, validate

ASSETS = Path(__file__).parent / 'assets'


def build(geometry: dict) -> str:
    g = copy.deepcopy(geometry)
    directory = Path(g.pop('_dir', '.'))
    validate(g)
    images = {}
    for floor in g['floors']:
        if 'image' not in floor:
            continue
        name = floor['image']['file']
        if '://' in name:
            raise ValueError('plan images must be local PNG files')
        path = directory / name
        data = path.read_bytes()
        if data[:8] != b'\x89PNG\r\n\x1a\n' or len(data) < 24:
            raise ValueError(f'{path}: expected a PNG image')
        width, height = struct.unpack('>II', data[16:24])
        images[floor['id']] = {'width': width, 'height': height,
                              'url': 'data:image/png;base64,' + base64.b64encode(data).decode('ascii')}
    source = json.dumps(g, ensure_ascii=False, allow_nan=False)
    payload = {'geometry': g, 'images': images, 'key': hashlib.sha256(source.encode()).hexdigest()}
    # A YAML label containing </script> must remain data, never become HTML.
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False).replace('<', '\\u003c')
    template = (ASSETS / 'editor.html').read_text(encoding='utf-8')
    return (template.replace('/* EDITOR_CSS */', (ASSETS / 'editor.css').read_text())
            .replace('/* YAML_LIBRARY */', (ASSETS / 'js-yaml.min.js').read_text())
            .replace('/* EDITOR_JS */', (ASSETS / 'editor.js').read_text())
            .replace('/* MODEL_JS */', (ASSETS / 'model.js').read_text())
            .replace('"PAYLOAD_JSON"', 'JSON.parse(' + json.dumps(encoded) + ')'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('geometry', type=Path)
    parser.add_argument('--out', type=Path, default=Path('layout-editor.html'))
    args = parser.parse_args()
    try:
        html = build(load(args.geometry))
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(html, encoding='utf-8')
    except (ValueError, TypeError, OSError, yaml.YAMLError) as error:
        parser.exit(2, f'Error: {error}\n')
    print(f'Done: wrote offline editor to {args.out}; open it in your browser')


if __name__ == '__main__':
    main()
