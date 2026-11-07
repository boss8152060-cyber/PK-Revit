# -*- coding: utf-8 -*-
"""unit test ฟังก์ชันคำนวณ (รันนอก Revit): python test_slab_calc.py"""
import math
import unittest
import slab_calc as sc


def DIA(n):
    return float(n[2:])


RECT = [(0, 0), (4000, 0), (4000, 3000), (0, 3000)]
# ตัว L: 4000x3000 เจาะมุมขวาบน 2000x1500
L = [(0, 0), (4000, 0), (4000, 1500), (2000, 1500), (2000, 3000), (0, 3000)]
# คางหมู: ฐานล่าง 4000 ฐานบน 2000 สูง 3000
TRAP = [(0, 0), (4000, 0), (3000, 3000), (1000, 3000)]
HOLE = [(1500, 1000), (2500, 1000), (2500, 2000), (1500, 2000)]


def dist_inside(p, poly):
    """ระยะตั้งฉากต่ำสุดจากจุดถึงขอบของ poly (CCW) — บวก = อยู่ด้านใน"""
    dmin = 1e9
    n = len(poly)
    for i in range(n):
        q0, q1 = poly[i], poly[(i + 1) % n]
        ex, ey = q1[0] - q0[0], q1[1] - q0[1]
        ln = math.hypot(ex, ey)
        d = ((p[0] - q0[0]) * ey * -1 + (p[1] - q0[1]) * ex) / ln * -1
        # cross(e, p-q0)/|e| เป็นบวกเมื่อ p อยู่ซ้ายของขอบ (ด้านในของ CCW)
        d = (ex * (p[1] - q0[1]) - ey * (p[0] - q0[0])) / ln
        dmin = min(dmin, d)
    return dmin


class T(unittest.TestCase):
    def test_area_clean(self):
        self.assertAlmostEqual(sc.signed_area(RECT), 12e6)
        c = sc.clean_polygon(RECT[::-1])
        self.assertGreater(sc.signed_area(c), 0)
        c2 = sc.clean_polygon([(0, 0), (2000, 0), (4000, 0), (4000, 3000), (0, 3000)])
        self.assertEqual(len(c2), 4)

    def test_split_loops(self):
        o, h = sc.split_loops([HOLE, RECT])
        self.assertEqual(len(o), 4)
        self.assertEqual(len(h), 1)
        self.assertEqual(sc.split_loops([[(0, 0), (1, 1)]]), (None, []))

    def test_point_in_region(self):
        self.assertTrue(sc.point_in_region((100, 100), RECT, [HOLE]))
        self.assertFalse(sc.point_in_region((2000, 1500), RECT, [HOLE]))
        self.assertFalse(sc.point_in_region((3000, 2500), L, []))

    def test_scan_rect(self):
        s = sc.scan_segments([RECT], 1000, 20)
        self.assertEqual(len(s), 1)
        self.assertAlmostEqual(s[0][0], 20)
        self.assertAlmostEqual(s[0][1], 3980)

    def test_scan_L(self):
        s = sc.scan_segments([L], 2000, 20)       # ส่วนบน x 0..2000
        self.assertEqual(len(s), 1)
        self.assertAlmostEqual(s[0][1], 1980)
        s = sc.scan_segments([L], 1000, 20)       # เต็มกว้าง
        self.assertAlmostEqual(s[0][1], 3980)

    def test_scan_trapezoid_slanted_cover(self):
        s = sc.scan_segments([TRAP], 1500, 20)
        sn = 3000 / math.hypot(1000, 3000)
        self.assertAlmostEqual(s[0][0], 500 + 20 / sn, places=3)
        self.assertAlmostEqual(s[0][1], 3500 - 20 / sn, places=3)
        self.assertAlmostEqual((s[0][0] - 500) * sn, 20, places=3)

    def test_scan_hole(self):
        s = sc.scan_segments([RECT, HOLE], 1500, 20)
        self.assertEqual(len(s), 2)
        self.assertAlmostEqual(s[0][1], 1500 - 20)
        self.assertAlmostEqual(s[1][0], 2500 + 20)
        self.assertEqual(len(sc.scan_segments([RECT, HOLE], 500, 20)), 1)

    def test_positions(self):
        p = sc.positions(30, 2970, 150)
        self.assertAlmostEqual(p[0], 30)
        self.assertAlmostEqual(p[-1], 2970)
        gaps = [b - a for a, b in zip(p, p[1:])]
        self.assertTrue(all(g <= 150 + 1e-6 for g in gaps))
        p = sc.positions(0, 1010, 100)     # ช่องท้ายเล็ก ไม่เติม
        self.assertAlmostEqual(p[-1], 1000)
        self.assertEqual(sc.positions(10, 5, 100), [])

    def test_levels(self):
        lay = {"BX": (u"RB9", 150), "BY": (u"RB9", 150),
               "TX": (u"RB9", 150), "TY": (u"RB9", 150)}
        lv, ok = sc.layer_levels(150, 20, lay, DIA)
        self.assertTrue(ok)
        self.assertAlmostEqual(lv["BX"], 24.5)
        self.assertAlmostEqual(lv["BY"], 33.5)
        self.assertAlmostEqual(lv["TX"], 125.5)
        self.assertAlmostEqual(lv["TY"], 116.5)
        lv, ok = sc.layer_levels(60, 20, lay, DIA)
        self.assertFalse(ok)

    def test_plan_rect_counts(self):
        lay = {"BX": (u"RB9", 150), "BY": (u"RB9", 150)}
        bars, notes = sc.plan_layers(RECT, [], 150, 20, lay, DIA)
        nx = [b for b in bars if b["group"] == "BX"]
        ny = [b for b in bars if b["group"] == "BY"]
        # y: 24.5..2975.5 -> 2951/150=19 ช่อง => 20 เส้น + เส้นท้าย(เหลือ 101>=37.5) = 21
        self.assertEqual(len(nx), 21)
        # x: 24.5..3975.5 -> 3951/150=26 ช่อง => 27 เส้น + เส้นท้าย(เหลือ 51>=37.5) = 28
        self.assertEqual(len(ny), 28)
        for b in nx:
            self.assertAlmostEqual(b["a"][0], 20)
            self.assertAlmostEqual(b["b"][0], 3980)
            self.assertEqual(b["a"][1], b["b"][1])
        self.assertEqual(sc.count_groups(bars), 2)
        self.assertEqual(notes, [])

    def test_plan_L_inside_region(self):
        lay = {"BX": (u"RB9", 200), "BY": (u"RB9", 200), "TX": (u"RB9", 200)}
        bars, _ = sc.plan_layers(L, [], 150, 20, lay, DIA)
        self.assertTrue(bars)
        for b in bars:
            mid = ((b["a"][0] + b["b"][0]) / 2.0, (b["a"][1] + b["b"][1]) / 2.0)
            self.assertTrue(sc.point_in_region(mid, L, []))
            if b["group"].endswith("X") and b["a"][1] > 1500:
                self.assertLessEqual(b["b"][0], 1980 + 1e-6)
            if b["group"].endswith("Y") and b["a"][0] > 2000:
                self.assertLessEqual(b["b"][1], 1480 + 1e-6)

    def test_plan_trap_cover(self):
        lay = {"BX": (u"RB9", 200), "BY": (u"RB9", 200)}
        bars, _ = sc.plan_layers(TRAP, [], 150, 20, lay, DIA)
        self.assertTrue(bars)
        for b in bars:
            for p in (b["a"], b["b"]):
                self.assertGreaterEqual(dist_inside(p, TRAP), 20 - 1e-6)

    def test_plan_hole(self):
        bars, _ = sc.plan_layers(RECT, [HOLE], 150, 20, {"BX": (u"RB9", 200)}, DIA)
        for b in bars:
            mid = ((b["a"][0] + b["b"][0]) / 2.0, b["a"][1])
            self.assertTrue(b["a"][0] < 1500 or b["a"][0] > 2500 or
                            not (1000 < b["a"][1] < 2000))
        # แถวที่ผ่านช่องเปิดต้องแตกเป็น 2 ท่อน
        ys = [b["a"][1] for b in bars if 1000 < b["a"][1] < 2000]
        self.assertTrue(ys)
        self.assertEqual(len(ys), 2 * len(set(ys)))

    def test_plan_too_thick(self):
        lay = {"BX": (u"DB32", 200), "BY": (u"DB32", 200),
               "TX": (u"DB32", 200), "TY": (u"DB32", 200)}
        bars, notes = sc.plan_layers(RECT, [], 100, 20, lay, DIA)
        self.assertEqual(bars, [])
        self.assertEqual(len(notes), 1)

    def test_edge_bars(self):
        lay = {"TX": (u"RB9", 150), "TY": (u"RB9", 150)}
        z = sc.edge_level(150, 20, lay, DIA, 9.0)
        self.assertAlmostEqual(z, 150 - 20 - 18 - 4.5)
        bars, skipped = sc.edge_bars(RECT, [], 150, 20, 9.0, 200, 1000, z)
        self.assertTrue(bars)
        for b in bars:
            self.assertTrue(sc.point_in_region(b["b"], RECT, []))
            ln = math.hypot(b["b"][0] - b["a"][0], b["b"][1] - b["a"][1])
            self.assertAlmostEqual(ln, 1000)
            self.assertLessEqual(b["leg"], 12 * 9.0 + 1e-9)
        # ยาว 3500 จากขอบใน L ส่วนใหญ่หลุดพื้น ต้องถูกข้าม
        _b2, sk2 = sc.edge_bars(L, [], 150, 20, 9.0, 200, 3500, z)
        self.assertGreater(sk2, 0)

    def test_gate(self):
        avail = [u"RB9", u"DB12"]
        lay = dict((k, (sc.PLACEHOLDER, 0)) for k in sc.LAYER_KEYS)
        v = {"mode": sc.MODE_BAR, "layers": dict(lay),
             "edge": (False, sc.PLACEHOLDER, 0, 0), "mesh": u"", "cover": 20}
        self.assertFalse(sc.gate_ok(sc.gate(v, avail, 0)))   # ไม่มีชั้นเหล็ก
        v["layers"]["BX"] = (u"RB9", 150)
        self.assertTrue(sc.gate_ok(sc.gate(v, avail, 0)))
        v["layers"]["BY"] = (u"RB12", 150)
        self.assertFalse(sc.gate_ok(sc.gate(v, avail, 0)))   # ไม่มี type
        v["layers"]["BY"] = (u"DB12", 0)
        self.assertFalse(sc.gate_ok(sc.gate(v, avail, 0)))   # ระยะ 0
        v["layers"]["BY"] = (sc.PLACEHOLDER, 0)
        v["edge"] = (True, u"RB9", 200, 0)
        self.assertFalse(sc.gate_ok(sc.gate(v, avail, 0)))
        v["edge"] = (True, u"RB9", 200, 800)
        self.assertTrue(sc.gate_ok(sc.gate(v, avail, 0)))
        v["cover"] = 0
        self.assertFalse(sc.gate_ok(sc.gate(v, avail, 0)))

    def test_gate_mesh(self):
        v = {"mode": sc.MODE_MESH,
             "layers": dict((k, (sc.PLACEHOLDER, 0)) for k in sc.LAYER_KEYS),
             "edge": (False, sc.PLACEHOLDER, 0, 0), "mesh": u"", "cover": 20}
        items = sc.gate(v, [], 0)
        self.assertFalse(sc.gate_ok(items))
        self.assertIn(u"ไม่พบ Fabric Sheet Type", items[0][1])
        self.assertFalse(sc.gate_ok(sc.gate(v, [], 2, [u"A", u"B"])))
        v["mesh"] = u"A"
        self.assertTrue(sc.gate_ok(sc.gate(v, [], 2, [u"A", u"B"])))

    def test_summary(self):
        self.assertEqual(sc.summary_text(0, 1), u"เหล็กเส้น 0 ชุด · ไวร์เมช 1 ผืน")


if __name__ == "__main__":
    unittest.main()
