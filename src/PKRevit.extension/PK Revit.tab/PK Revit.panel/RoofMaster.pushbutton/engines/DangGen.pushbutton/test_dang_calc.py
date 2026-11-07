# -*- coding: utf-8 -*-
"""unit test ฟังก์ชันคำนวณดั้ง (รันนอก Revit): python test_dang_calc.py"""
import unittest
import dang_calc as dc


def hip(i, bot, top):
    return {"id": i, "kind": "hip", "p0": bot, "p1": top}


def ridge(i, a, b):
    return {"id": i, "kind": "ridge", "p0": a, "p1": b}


# หลังคาปั้นหยา: อกไก่ยาว 4000 ที่ z=3000, ตะเข้สัน 4 เส้นลงมุม
HIP_ROOF = [
    ridge(1, (1500, 2000, 3000), (5500, 2000, 3000)),
    hip(2, (0, 0, 1500), (1500, 2000, 3000)),
    hip(3, (0, 4000, 1500), (1500, 2000, 3000)),
    hip(4, (7000, 0, 1500), (5500, 2000, 3000)),
    hip(5, (7000, 4000, 1500), (5500, 2000, 3000)),
]


class TestNodes(unittest.TestCase):
    def test_hip_roof_two_nodes(self):
        ns = dc.find_nodes(HIP_ROOF, member_depth=100)
        self.assertEqual(len(ns), 2)
        for n in ns:
            self.assertAlmostEqual(n["top_z"], 2900.0)
            self.assertEqual(n["count"], 3)
        xs = sorted(round(n["x"]) for n in ns)
        self.assertEqual(xs, [1500, 5500])

    def test_hip_lower_ends_ignored(self):
        ns = dc.find_nodes(HIP_ROOF)
        for n in ns:
            self.assertEqual(n["y"], 2000)   # ไม่มีที่ชายคา (y=0/4000)

    def test_gable_ridge_ends(self):
        g = [ridge(1, (0, 2000, 3000), (6000, 2000, 3000))]
        self.assertEqual(len(dc.find_nodes(g)), 2)
        self.assertEqual(len(dc.find_nodes(g, ridge_ends_always=False)), 0)

    def test_lone_hips_without_junction(self):
        h = [hip(1, (0, 0, 0), (1000, 1000, 1000)),
             hip(2, (9000, 0, 0), (8000, 1000, 1000))]
        self.assertEqual(dc.find_nodes(h), [])

    def test_pyramid_four_hips(self):
        h = [hip(1, (0, 0, 0), (2000, 2000, 2000)),
             hip(2, (4000, 0, 0), (2000, 2000, 2000)),
             hip(3, (0, 4000, 0), (2001, 2001, 1990)),
             hip(4, (4000, 4000, 0), (2000, 1999, 2000))]
        ns = dc.find_nodes(h)
        self.assertEqual(len(ns), 1)
        self.assertEqual(ns[0]["count"], 4)
        self.assertAlmostEqual(ns[0]["top_z"], 1990 - 100)

    def test_z_tolerance_separates_levels(self):
        h = [ridge(1, (0, 0, 3000), (0, 0, 3000)),
             ridge(2, (0, 0, 6000), (0, 0, 6000))]
        ns = dc.find_nodes(h, min_members=2, ridge_ends_always=False)
        self.assertEqual(len(ns), 0)


class TestMid(unittest.TestCase):
    def test_disabled(self):
        self.assertEqual(dc.ridge_mid_nodes(HIP_ROOF, 0), [])

    def test_split(self):
        ms = dc.ridge_mid_nodes(HIP_ROOF, 1500, member_depth=0)
        self.assertEqual(len(ms), 2)          # 4000/1500 -> 3 ช่วง -> 2 จุดกลาง
        self.assertAlmostEqual(ms[0]["x"], 1500 + 4000 / 3.0)

    def test_short_ridge_no_mid(self):
        self.assertEqual(dc.ridge_mid_nodes(HIP_ROOF, 4000), [])

    def test_merge_drops_close(self):
        a = [{"x": 0, "y": 0, "top_z": 1}]
        b = [{"x": 100, "y": 0, "top_z": 1}, {"x": 2000, "y": 0, "top_z": 1}]
        self.assertEqual(len(dc.merge_nodes(a, b, 300)), 2)


class TestBottom(unittest.TestCase):
    def test_nearest_support(self):
        b, s = dc.choose_bottom(2900, [100, 0, 1500, 2850], 1000)
        self.assertEqual((b, s), (1500, "support"))   # 2850 ใกล้เกิน (<200)

    def test_fallback_when_none(self):
        self.assertEqual(dc.choose_bottom(2900, [], 1000),
                         (1900, "fallback"))

    def test_too_far_is_fallback(self):
        self.assertEqual(dc.choose_bottom(9000, [0], 1000, max_len=4000),
                         (8000, "fallback"))

    def test_plan_skips_short(self):
        nodes = [{"x": 0, "y": 0, "top_z": 2900, "kinds": ["ridge"]},
                 {"x": 5, "y": 5, "top_z": 100, "kinds": ["ridge"]}]
        p = dc.plan_dang(nodes, [[1900], []], 150)
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["source"], "support")
        self.assertEqual(p[0]["length"], 1000)

    def test_plan_fallback_length(self):
        p = dc.plan_dang([{"x": 0, "y": 0, "top_z": 3000}], [[]], 1200)
        self.assertEqual(p[0]["bottom_z"], 1800)
        self.assertEqual(p[0]["source"], "fallback")


if __name__ == "__main__":
    unittest.main()
