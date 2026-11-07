# -*- coding: utf-8 -*-
"""unit test ฟังก์ชันคำนวณ (รันนอก Revit): python test_stair_calc.py"""
import math
import unittest
import stair_calc as sc


def DIA(n):
    return sc.dia_from_name(n)


def groups(waist=True, ext=True, tread=True, crack=True):
    return {
        "waist": {"on": waist, "size": u"RB9", "sp": 150.0},
        "ext": {"on": ext, "size": u"RB9", "sp": 200.0},
        "tread": {"on": tread, "size": u"RB9", "sp": 200.0},
        "crack": {"on": crack, "size": u"RB9", "sp": 200.0},
    }


def V(**kw):
    v = {"groups": groups(), "cover": 25.0, "tw": 150.0, "tl": 150.0,
         "anchor": 300.0, "ext_len": 400.0, "ext_run": 600.0, "ext_lower": False}
    v.update(kw)
    return v


# 9 ขั้น: 10 ตั้ง 9 นอน, ลูกตั้ง 170, ลูกนอน 250
GEO = sc.Geo(1700.0, 10, 9, 250.0)
W = 1200.0


class T(unittest.TestCase):
    def test_count(self):
        self.assertEqual(sc.count_for(0, 150), 1)
        self.assertEqual(sc.count_for(1000, 150), 8)      # 1000/150=6.67 -> 7 ช่วง = 8 เส้น
        self.assertEqual(sc.count_for(300, 150), 3)
        self.assertEqual(sc.count_for(301, 150), 4)

    def test_geo(self):
        self.assertAlmostEqual(GEO.r, 170.0)
        self.assertAlmostEqual(GEO.Lh, 2250.0)
        self.assertAlmostEqual(GEO.nosing(0), 170.0)
        self.assertAlmostEqual(GEO.nosing(GEO.Lh), 1700.0)   # ปลายบน = ความสูงรวม

    def test_waist_inside_concrete(self):
        sets = sc.plan_run(GEO, W, V(), DIA)
        w = [s for s in sets if s["group"] == "waist"][0]
        # จุดตามความลาด (ไม่นับหางยื่น) อยู่เหนือท้องบันได ≥ หุ้ม และใต้เส้นจมูกขั้น
        for s, z in w["pts"][1:3]:
            self.assertGreaterEqual(z - GEO.soffit(s, 150.0), 25.0 / GEO.cos - 1e-6)
            self.assertLess(z, GEO.nosing(s))
        self.assertEqual(len(w["pts"]), 4)
        self.assertEqual(w["pts"][0][0], -300.0)

    def test_waist_no_anchor(self):
        sets = sc.plan_run(GEO, W, V(anchor=0.0), DIA)
        w = [s for s in sets if s["group"] == "waist"][0]
        self.assertEqual(len(w["pts"]), 2)

    def test_waist_count_and_t(self):
        w = [s for s in sc.plan_run(GEO, W, V(), DIA) if s["group"] == "waist"][0]
        span = w["t1"] - w["t0"]
        self.assertAlmostEqual(span, 1200 - 2 * 25 - 9)
        self.assertEqual(w["count"], sc.count_for(span, 150.0))

    def test_ext_top_only_by_default(self):
        sets = [s for s in sc.plan_run(GEO, W, V(), DIA) if s["group"] == "ext"]
        self.assertEqual(len(sets), 1)
        p = sets[0]["pts"]
        self.assertAlmostEqual(p[0][0], GEO.Lh + 400.0)
        self.assertAlmostEqual(p[1][1], p[0][1])          # ท่อนนอนระดับเดียว
        self.assertAlmostEqual(p[2][0], GEO.Lh - 600.0)
        self.assertLess(p[1][1], 1700.0)                  # ต่ำกว่าผิวบนชาน

    def test_ext_lower_option(self):
        sets = [s for s in sc.plan_run(GEO, W, V(ext_lower=True), DIA) if s["group"] == "ext"]
        self.assertEqual(len(sets), 2)

    def test_tread_one_set_per_step(self):
        sets = [s for s in sc.plan_run(GEO, W, V(), DIA) if s["group"] == "tread"]
        self.assertEqual(len(sets), GEO.n_t)
        for st in sets:
            (s0, za), (s1, zt), (s2, zt2) = st["pts"]
            self.assertAlmostEqual(s0, s1)
            self.assertAlmostEqual(zt, zt2)
            self.assertGreater(zt, za)
            self.assertLess(s2 - s0, GEO.g)

    def test_crack(self):
        c = [s for s in sc.plan_run(GEO, W, V(), DIA) if s["group"] == "crack"][0]
        self.assertEqual(c["kind"], "transverse")
        self.assertAlmostEqual(math.hypot(*c["dir"]), 1.0)
        # ปลายสุดของการเรียงยังอยู่ในคอนกรีต
        s_end = c["s"] + c["dir"][0] * c["arr_len"]
        z_end = c["z"] + c["dir"][1] * c["arr_len"]
        self.assertLess(z_end, GEO.nosing(s_end))
        self.assertGreater(z_end, GEO.soffit(s_end, 150.0))

    def test_z0_offset(self):
        a = sc.plan_run(GEO, W, V(), DIA, z0=0.0)
        b = sc.plan_run(GEO, W, V(), DIA, z0=3000.0)
        self.assertAlmostEqual(b[0]["pts"][0][1] - a[0]["pts"][0][1], 3000.0)

    def test_groups_off(self):
        v = V(groups=groups(waist=False, ext=False, tread=False, crack=True))
        sets = sc.plan_run(GEO, W, v, DIA)
        self.assertEqual([s["group"] for s in sets], ["crack"])

    def test_totals(self):
        sets = sc.plan_run(GEO, W, V(), DIA)
        n, b = sc.totals(sets)
        self.assertEqual(n, len(sets))
        self.assertEqual(b, sum(s["count"] for s in sets))
        bg = sc.by_group(sets)
        self.assertEqual(bg["tread"][0], 9)

    def test_landing(self):
        sets = sc.plan_landing(0, 1200, 0, 1200, 1700.0, V(), DIA)
        self.assertEqual(len(sets), 2)
        zs = sorted(s.get("z", s["pts"][0][1] if "pts" in s else 0) for s in sets)
        self.assertGreater(zs[0], 1700.0 - 150.0)
        self.assertLess(zs[1], 1700.0)

    def test_axis_rect(self):
        self.assertEqual(sc.is_axis_rect([(0, 0), (10, 0), (10, 5), (0, 5)]), (0, 10, 0, 5))
        self.assertIsNone(sc.is_axis_rect([(0, 0), (10, 0), (10, 5)]))
        self.assertIsNone(sc.is_axis_rect([(0, 0), (10, 0), (10, 5), (5, 5), (5, 10), (0, 10)]))

    def test_gate(self):
        runs = [{"label": u"ช่วง 1", "W": 1200.0}]
        avail = [u"RB9"]
        self.assertTrue(sc.gate_ok(sc.gate(V(), runs, avail)))
        self.assertFalse(sc.gate_ok(sc.gate(V(), [], avail)))
        self.assertFalse(sc.gate_ok(sc.gate(V(), runs, [u"DB12"])))       # ไม่มี bar type
        g = groups()
        g["waist"]["size"] = sc.PLACEHOLDER
        self.assertFalse(sc.gate_ok(sc.gate(V(groups=g), runs, avail)))
        self.assertFalse(sc.gate_ok(sc.gate(V(tw=40.0), runs, avail)))     # ท้องบางเกิน
        self.assertFalse(sc.gate_ok(sc.gate(V(cover=0.0), runs, avail)))
        self.assertFalse(sc.gate_ok(sc.gate(V(), [{"label": u"x", "W": 60.0}], avail)))
        g2 = groups(False, False, False, False)
        self.assertFalse(sc.gate_ok(sc.gate(V(groups=g2), runs, avail)))
        g3 = groups()
        g3["crack"]["sp"] = 10.0
        self.assertFalse(sc.gate_ok(sc.gate(V(groups=g3), runs, avail)))


if __name__ == "__main__":
    unittest.main()
