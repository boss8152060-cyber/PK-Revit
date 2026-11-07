# -*- coding: utf-8 -*-
"""unit test ฟังก์ชันคำนวณ (รันนอก Revit): python test_footing_calc.py"""
import math
import unittest
import footing_calc as fc


def DIA(n):
    return float(n[2:])


RECT = [(0, 0), (1500, 0), (1500, 700), (0, 700)]
SQ = [(0, 0), (1500, 0), (1500, 1500), (0, 1500)]
# สามเหลี่ยมด้านเท่า ฐาน 900
TRI = [(0, 0), (900, 0), (450, 900 * math.sqrt(3) / 2)]


class T(unittest.TestCase):
    def test_area_orientation(self):
        self.assertAlmostEqual(fc.signed_area(RECT), 1500 * 700)
        self.assertGreater(fc.signed_area(fc.clean_polygon(RECT[::-1])), 0)

    def test_clean_collinear(self):
        p = fc.clean_polygon([(0, 0), (750, 0), (1500, 0), (1500, 700), (0, 700)])
        self.assertEqual(len(p), 4)

    def test_classify(self):
        self.assertEqual(fc.classify(RECT), "rect")
        self.assertEqual(fc.classify(TRI), "tri")
        self.assertIsNone(fc.classify([(0, 0), (10, 0), (12, 5), (0, 5)]))

    def test_offset(self):
        o = fc.offset_polygon(RECT, 75)
        xs = [p[0] for p in o]
        ys = [p[1] for p in o]
        self.assertAlmostEqual(min(xs), 75)
        self.assertAlmostEqual(max(xs), 1425)
        self.assertAlmostEqual(min(ys), 75)
        self.assertAlmostEqual(max(ys), 625)
        self.assertIsNone(fc.offset_polygon(RECT, 400))

    def test_offset_tri_inradius(self):
        r = 900 * math.sqrt(3) / 6      # inradius
        self.assertIsNotNone(fc.offset_polygon(TRI, r - 1))
        self.assertIsNone(fc.offset_polygon(TRI, r + 1))

    def test_clip(self):
        t = fc.clip_line(RECT, (0, 350), (1, 0))
        self.assertAlmostEqual(t[1] - t[0], 1500)
        self.assertIsNone(fc.clip_line(RECT, (0, 800), (1, 0)))

    def test_spread(self):
        self.assertEqual(fc.spread(3, 0, 10), [0, 5, 10])
        self.assertEqual(fc.spread(1, 0, 10), [5])
        self.assertEqual(fc.spread(0, 0, 10), [])
        self.assertEqual(fc.spread(3, 0, 8, edge=False), [2, 4, 6])

    def test_rect_axes(self):
        u, L, S = fc.rect_axes(RECT)
        self.assertEqual((L, S), (1500, 700))
        self.assertAlmostEqual(abs(u[0]), 1)
        u, L, S = fc.rect_axes([(0, 0), (700, 0), (700, 1500), (0, 1500)])
        self.assertEqual((L, S), (1500, 700))
        self.assertAlmostEqual(abs(u[1]), 1)

    def test_plan_rect_f2(self):
        g = {"long": (u"DB12", 4), "short": (u"DB16", 7)}
        bars = fc.plan_mat(RECT, "rect", g, 75, 0, 600, DIA)
        L = [b for b in bars if b["group"] == "long"]
        S = [b for b in bars if b["group"] == "short"]
        self.assertEqual((len(L), len(S)), (4, 7))
        # long ขนานแกน x ยาว 1500-2*(75+6)
        self.assertAlmostEqual(abs(L[0]["b"][0] - L[0]["a"][0]), 1500 - 2 * 81)
        # ชั้น: long ล่าง z=75+6, short ที่ 75+12+8
        self.assertAlmostEqual(L[0]["z"], 81)
        self.assertAlmostEqual(S[0]["z"], 95)
        # แถวนอกสุดอยู่ที่ 81 จากขอบ
        ys = sorted(b["a"][1] for b in L)
        self.assertAlmostEqual(ys[0], 81)
        self.assertAlmostEqual(ys[-1], 700 - 81)

    def test_ring_clearance(self):
        g = {"long": (u"DB12", 2), "short": (u"DB12", 2)}
        b0 = fc.plan_mat(SQ, "rect", g, 75, 0, 550, DIA)
        b1 = fc.plan_mat(SQ, "rect", g, 75, 9, 550, DIA)
        self.assertAlmostEqual(abs(b0[0]["b"][0] - b0[0]["a"][0]) - 18,
                               abs(b1[0]["b"][0] - b1[0]["a"][0]))

    def test_plan_tri(self):
        g = {0: (u"DB12", 3), 60: (u"DB12", 3), 120: (u"DB12", 3)}
        bars = fc.plan_mat(TRI, "tri", g, 75, 0, 600, DIA)
        self.assertEqual(len(bars), 9)
        ip = fc.offset_polygon(TRI, 81)
        for b in bars:
            for p in (b["a"], b["b"]):      # ปลายอยู่ในรูปที่หดแล้ว
                for a, _u, m in fc._edges(ip):
                    self.assertGreaterEqual(
                        m[0] * (p[0] - a[0]) + m[1] * (p[1] - a[1]), -1e-6)
        # ทิศ 60° จริง
        b = [x for x in bars if x["group"] == 60][0]
        ang = math.degrees(math.atan2(b["b"][1] - b["a"][1], b["b"][0] - b["a"][0]))
        self.assertAlmostEqual(ang % 180, 60, places=4)
        zs = sorted(set(round(x["z"], 3) for x in bars))
        self.assertEqual(len(zs), 3)

    def test_plan_skips_unset_group(self):
        g = {"long": (None, 4), "short": (u"DB12", 3)}
        bars = fc.plan_mat(RECT, "rect", g, 75, 0, 600, DIA)
        self.assertEqual(len(bars), 3)

    def test_hook_leg(self):
        self.assertEqual(fc.hook_leg(fc.HOOK_NONE, 12, 81, 600, 75), 0)
        self.assertEqual(fc.hook_leg(fc.HOOK_90, 12, 81, 600, 75), 144)
        self.assertAlmostEqual(fc.hook_leg(fc.HOOK_FULL, 12, 81, 600, 75),
                               600 - 75 - 6 - 81)
        # ฐานบาง: จำกัดไม่ให้ทะลุระยะหุ้มบน
        self.assertAlmostEqual(fc.hook_leg(fc.HOOK_90, 25, 87, 250, 75),
                               250 - 75 - 12.5 - 87)
        self.assertEqual(fc.hook_leg(fc.HOOK_90, 25, 87, 150, 75), 0)

    def test_ring_levels(self):
        z = fc.ring_levels(600, 75, 28, 9, 3, 150)
        self.assertEqual(len(z), 3)
        self.assertAlmostEqual(z[0], 75 + 28 + 4.5)
        self.assertAlmostEqual(z[1] - z[0], 150)
        self.assertEqual(len(fc.ring_levels(300, 75, 28, 9, 5, 150)), 1)

    def test_name_hint(self):
        self.assertEqual(fc.name_hint(u"F2 1500x700x600"), (u"F2", 2))
        self.assertEqual(fc.name_hint(u"F1P"), (u"F1P", 1))
        self.assertEqual(fc.name_hint(u"abc"), (u"", 0))

    def test_gate(self):
        avail = [u"DB12", u"DB16", u"RB9"]
        ph = fc.PLACEHOLDER
        v = {"long": (ph, 4), "short": (u"DB12", 4),
             "tri": {0: (ph, 3), 60: (ph, 3), 120: (ph, 3)},
             "hook": None, "ring": (False, ph, 1, 150), "cover": 75}
        g = fc.gate(v, True, False, avail)
        self.assertFalse(fc.gate_ok(g))
        self.assertTrue(g[0][1].startswith(u"✗"))
        self.assertTrue(g[1][1].startswith(u"✓"))
        v["long"] = (u"DB16", 4)
        v["hook"] = fc.HOOK_90
        self.assertTrue(fc.gate_ok(fc.gate(v, True, False, avail)))
        # tri ไม่ตรวจถ้าไม่มีฐานสามเหลี่ยม แต่ตรวจเมื่อมี
        self.assertFalse(fc.gate_ok(fc.gate(v, True, True, avail)))
        v["ring"] = (True, u"RB9", 0, 150)
        self.assertFalse(fc.gate_ok(fc.gate(v, True, False, avail)))
        v["ring"] = (True, u"RB9", 2, 150)
        self.assertTrue(fc.gate_ok(fc.gate(v, True, False, avail)))
        v["long"] = (u"DB99", 4)
        self.assertFalse(fc.gate_ok(fc.gate(v, True, False, avail)))


if __name__ == "__main__":
    unittest.main()
