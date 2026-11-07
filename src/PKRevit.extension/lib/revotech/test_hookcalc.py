# -*- coding: utf-8 -*-
"""unit test ของ revotech.hookcalc: python test_hookcalc.py"""
import os, sys, math, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from revotech import hookcalc as hc


class T(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(hc.parse_hook(hc.HOOK_KEEP), "keep")
        self.assertEqual(hc.parse_hook(None), "keep")
        self.assertEqual(hc.parse_hook(hc.HOOK_NONE), "none")
        self.assertEqual([hc.parse_hook(x) for x in hc.HOOK_ITEMS[2:]], [45, 90, 135, 180])

    def test_defaults(self):
        self.assertEqual(hc.default_mult(90), 12.0)
        self.assertEqual(hc.default_mult(135), 6.0)

    def test_ext_min_75_on_135(self):
        self.assertEqual(hc.hook_ext_mm(135, 6, 9), 75.0)     # 54 < 75
        self.assertEqual(hc.hook_ext_mm(135, 6, 16), 96.0)
        self.assertEqual(hc.hook_ext_mm(90, 12, 6), 72.0)      # 90° ไม่มีขั้นต่ำ
        self.assertAlmostEqual(hc.effective_mult(135, 6, 9), 75.0 / 9.0)
        self.assertEqual(hc.effective_mult(90, 12, 16), 12.0)

    def test_developed(self):
        d = 16.0
        arc = math.radians(90) * (3 * d + d / 2)
        self.assertAlmostEqual(hc.hook_developed_mm(90, 12, d), arc + 12 * d)
        self.assertAlmostEqual(hc.hook_developed_mm(90, 12, d, bend_dia=96.0),
                               math.radians(90) * (48 + 8) + 192)
        self.assertGreater(hc.hook_developed_mm(180, 4, d), hc.hook_developed_mm(90, 4, d))
        self.assertEqual(hc.bend_radius_mm(28), 112.0)

    def test_cut_length(self):
        self.assertEqual(hc.cut_length_mm(3000, 16), 3000.0)
        one = hc.cut_length_mm(3000, 16, (90, 12), None)
        two = hc.cut_length_mm(3000, 16, (90, 12), (90, 12))
        self.assertAlmostEqual(two - 3000, 2 * (one - 3000))
        self.assertGreater(one, 3000.0)

    def test_lap_and_splice(self):
        self.assertEqual(hc.lap_mm(16, 40), 640.0)
        self.assertEqual(hc.spliced_cut_length_mm(12000, 16, 40, 1), 12640.0)
        self.assertEqual(hc.spliced_cut_length_mm(12000, 16, 40, 0), 12000.0)

    def test_stagger(self):
        self.assertEqual(hc.stagger_offsets(4, 640, hc.STAGGER_OFF), [0, 0, 0, 0])
        o = hc.stagger_offsets(4, 640, hc.STAGGER_ALT)
        self.assertEqual(o[0], 0.0)
        self.assertAlmostEqual(o[1], 1.3 * 640)
        self.assertEqual(o[2], 0.0)


if __name__ == "__main__":
    unittest.main()
