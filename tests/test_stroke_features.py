"""New glyph repairs must fail their old flattened or disconnected forms."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from build_stroke_font import build_font, flatten_path
from verify_glyph_invariants import verify


class StrokeFeatureTests(unittest.TestCase):
    def verify_paths(self, paths, criterion, requirements):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font = root / 'feature.ttf'
            build_font([{'codepoint': 0x3D045, 'width': 30,
                         'strokes': [flatten_path(path) for path in paths]}], font)
            spec = root / 'spec.json'
            spec.write_text(json.dumps({'glyphs': [{'codepoint': 'U+3D045',
                'criterion': criterion, 'source_criteria': {'purpose': 'semantic negative control'},
                'requirements': requirements}]}))
            return verify(font, spec)

    def test_inner_return_curve_passes_but_flat_bar_fails(self):
        requirements = {'regions': [{'name': 'return', 'roi_width_fractions': [0.2, 0.8],
                                    'roi_height_fractions': [0.2, 0.8]}],
                        'minimum_height_to_width_ratio': 0.5}
        curve = 'M 300 300 L 500 300 C 600 300 600 500 500 500 L 300 500'
        for paths, expected in (([curve], True), (['M 300 400 L 600 400'], False)):
            with self.subTest(expected=expected):
                anchors = ['M 100 100 L 101 100', 'M 900 900 L 901 900']
                report = self.verify_paths(paths+anchors, 'roi_return_curves', requirements)
                self.assertEqual(report['passed'], expected, report['errors'])

    def test_topology_rejects_missing_connection_and_extra_counter(self):
        bars = [f'M 150 {100+index*100} L 250 {100+index*100}' for index in range(6)]
        loop = 'M 450 200 L 750 200 L 750 600 L 450 600 Z'
        opened = 'M 450 200 L 750 200 L 750 600 L 450 600'
        for paths, expected in ((bars+[loop], True), (bars+[opened], False),
                                (bars+[loop, 'M 450 400 L 750 400'], False),
                                (bars+[loop, 'M 250 100 L 450 200'], False)):
            with self.subTest(paths=paths):
                report = self.verify_paths(paths, 'ink_topology',
                    {'expected_components': 7, 'expected_counters': 1})
                self.assertEqual(report['passed'], expected, report['errors'])


if __name__ == '__main__':
    unittest.main()
