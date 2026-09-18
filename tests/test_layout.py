import copy
import unittest
from pathlib import Path
from tooling.layout.geometry import load, to_house, nodes_in_house, validate
from tooling.layout.emit_companion import companion
from tooling.layout.build_layout_page import build

ROOT = Path(__file__).resolve().parents[1]

class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.g = load(ROOT / 'examples/geometry.example.yaml')

    def test_transform_and_absolute_node_height(self):
        f = self.g['floors'][1]
        f['place'].update(flip_h=True, flip_v=True, dx=2, dy=-1)
        self.assertEqual(to_house(f, 1, 2), (7, 1))
        self.assertEqual(nodes_in_house(f)['studio'], (7, 1, 4.2))

    def test_companion_schema_uses_transformed_rooms_and_floor_bounds(self):
        self.g['floors'][1]['place']['dx'] = 2
        result = companion(self.g)
        self.assertEqual(result['floors'][1]['bounds'], [[0, 0, 3], [10, 8, 6]])
        self.assertEqual(result['floors'][1]['rooms'][0]['points'][0], [2, 0])
        self.assertEqual(result['nodes'][-1]['point'], [3, 2, 4.2])
        self.assertEqual(result['nodes'][-1]['floors'], ['upper'])

    def test_bounds_expand_for_shifted_floor_and_outlying_room(self):
        self.g['floors'][1]['place']['dx'] = 12
        self.g['floors'][1]['rooms']['annex'] = [[0, 0], [9, 0], [9, 1]]
        result = companion(self.g)
        self.assertEqual(result['floors'][1]['bounds'], [[0, 0, 3], [21, 8, 6]])

    def test_invalid_geometry_rejected(self):
        for mutate in [lambda g: g['floors'][0]['nodes'].update(bad=[0, 1, float('nan')]),
                       lambda g: g['floors'][1]['nodes'].update(entry=[1, 1, 1]),
                       lambda g: g['floors'][0]['local'].update(w=0)]:
            g = copy.deepcopy(self.g)
            mutate(g)
            with self.assertRaises(ValueError):
                validate(g)

    def test_html_is_self_contained_and_cannot_close_script(self):
        self.g['floors'][0]['name'] = '</script><script>alert(1)</script>'
        html = build(self.g)
        self.assertNotIn('</script><script>alert(1)', html)
        self.assertNotIn('<script src=', html)
        self.assertIn('Download geometry.yaml', html)
        self.assertIn('Copy Companion YAML', html)

    def test_only_local_png_images_are_embedded(self):
        self.g['floors'][0]['image'] = {'file': 'https://bad.invalid/plan.png', 'px_per_m': 10, 'origin_px': [0, 0]}
        with self.assertRaises(ValueError):
            build(self.g)

if __name__ == '__main__':
    unittest.main()
