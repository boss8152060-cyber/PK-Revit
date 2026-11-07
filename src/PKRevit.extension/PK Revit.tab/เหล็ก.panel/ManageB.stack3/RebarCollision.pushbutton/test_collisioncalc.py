# -*- coding: utf-8 -*-
"""unit test ของ revotech.collisioncalc (รันนอก Revit): python test_collisioncalc.py"""
import os
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "..", "lib"))
from revotech import collisioncalc as cc


def box(x0, y0, z0, x1, y1, z1):
    return (x0, y0, z0, x1, y1, z1)


class Boxes(unittest.TestCase):
    def test_overlap_and_touch(self):
        a = box(0, 0, 0, 1, 1, 1)
        self.assertTrue(cc.boxes_overlap(a, box(0.5, 0.5, 0.5, 2, 2, 2)))
        self.assertFalse(cc.boxes_overlap(a, box(1, 0, 0, 2, 1, 1)))   # แค่แตะ
        self.assertTrue(cc.boxes_overlap(a, box(1.05, 0, 0, 2, 1, 1), 0.1))
        self.assertFalse(cc.boxes_overlap(a, box(1.2, 0, 0, 2, 1, 1), 0.1))

    def test_candidates_match_bruteforce(self):
        import random
        rnd = random.Random(7)
        items = []
        for k in range(120):
            x, y, z = rnd.random() * 10, rnd.random() * 10, rnd.random() * 10
            items.append((k, rnd.choice([1, 2, 3, None]),
                          box(x, y, z, x + rnd.random() * 2, y + rnd.random() * 2,
                              z + rnd.random() * 2)))
        for m in (0.0, 0.3):
            pairs, total, trunc = cc.candidate_pairs(items, m)
            got = set((i, j) for i, j, _ in pairs)
            exp = set()
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    hi, hj = items[i][1], items[j][1]
                    if hi is not None and hi == hj:
                        continue
                    if cc.boxes_overlap(items[i][2], items[j][2], m):
                        exp.add((i, j))
            self.assertEqual(got, exp)
            self.assertEqual(total, len(exp))
            self.assertFalse(trunc)

    def test_same_host_skipped_unknown_not(self):
        b = box(0, 0, 0, 1, 1, 1)
        items = [(0, 5, b), (1, 5, b), (2, None, b), (3, None, b)]
        pairs, total, _ = cc.candidate_pairs(items)
        got = set((i, j) for i, j, _ in pairs)
        self.assertNotIn((0, 1), got)
        self.assertIn((2, 3), got)
        self.assertIn((0, 2), got)

    def test_truncation_keeps_deepest(self):
        items = [(0, 1, box(0, 0, 0, 1, 1, 1)),
                 (1, 2, box(0.9, 0, 0, 2, 1, 1)),     # ซ้อนตื้น 0.1
                 (2, 3, box(0, 0, 0, 1, 1, 1))]        # ซ้อนลึกกับ 0
        pairs, total, trunc = cc.candidate_pairs(items, 0.0, max_pairs=1)
        self.assertTrue(trunc)
        self.assertEqual(total, 3)
        self.assertEqual((pairs[0][0], pairs[0][1]), (0, 2))


class Geometry(unittest.TestCase):
    def test_segment_distance(self):
        d, _, _ = cc.segment_distance((0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0))
        self.assertAlmostEqual(d, 1.0)
        d, _, _ = cc.segment_distance((0, 0, 0), (1, 0, 0), (0.5, -1, 1), (0.5, 1, 1))
        self.assertAlmostEqual(d, 1.0)                       # ไขว้กัน ห่างแนวดิ่ง 1
        d, _, _ = cc.segment_distance((0, 0, 0), (1, 0, 0), (3, 0, 0), (4, 0, 0))
        self.assertAlmostEqual(d, 2.0)                       # เส้นตรงเดียวกัน ต่อปลาย
        d, _, _ = cc.segment_distance((0, 0, 0), (0, 0, 0), (3, 4, 0), (3, 4, 0))
        self.assertAlmostEqual(d, 5.0)                       # จุดต่อจุด

    def test_gap_hit_near_none(self):
        a = [[(0, 0, 0), (10, 0, 0)]]
        b = [[(5, 0.5, -3), (5, 0.5, 3)]]       # ไขว้ ห่างเส้นศูนย์กลาง 0.5
        r = cc.centerline_gap(a, b, 0.2, 0.2, 0.0)   # gap = 0.1 ไม่ชน → กรองทิ้งตั้งแต่ bbox
        self.assertIsNone(cc.classify(r["min_gap"], 0.0))
        r = cc.centerline_gap(a, b, 0.2, 0.2, 0.2)
        self.assertAlmostEqual(r["min_gap"], 0.1)
        self.assertEqual(cc.classify(r["min_gap"], 0.2), cc.STATUS_NEAR)
        self.assertEqual(r["nears"], 1)
        r = cc.centerline_gap(a, b, 0.3, 0.3, 0.0)   # gap = -0.1
        self.assertEqual(cc.classify(r["min_gap"], 0.0), cc.STATUS_HIT)
        self.assertEqual(r["hits"], 1)
        self.assertAlmostEqual(r["loc"][0], 5.0)

    def test_gap_counts_points_in_set(self):
        a = [[(0, 0, 0), (10, 0, 0)]]
        b = [[(x, 0, -2), (x, 0, 2)] for x in (1, 3, 5, 99)]   # 3 เส้นตัด 1 เส้นไกล
        r = cc.centerline_gap(a, b, 0.1, 0.1, 0.0)
        self.assertEqual(r["hits"], 3)
        self.assertEqual(r["pairs_checked"], 3)   # เส้นไกลถูกกรองด้วย bbox

    def test_no_polylines(self):
        r = cc.centerline_gap([], [[(0, 0, 0), (1, 0, 0)]], 0.1, 0.1)
        self.assertIsNone(r["min_gap"])
        self.assertIsNone(cc.classify(None))


def rec(ha, hb, status, gap, pts=1):
    return {"host_a": ha, "host_b": hb, "status": status, "gap": gap, "points": pts}


class Report(unittest.TestCase):
    def test_group(self):
        recs = [rec(1, 2, cc.STATUS_HIT, -0.1, 3), rec(2, 1, cc.STATUS_NEAR, 0.05, 1),
                rec(1, 3, cc.STATUS_HIT, -0.2, 2), rec(None, 3, cc.STATUS_HIT, 0.0, 1),
                rec(3, None, cc.STATUS_NEAR, 0.01, 1)]
        g = cc.group_by_host_pair(recs)
        self.assertEqual(len(g), 3)
        self.assertEqual(g[0]["key"], (1, 2))
        self.assertEqual(g[0]["points"], 4)
        self.assertEqual((g[0]["hits"], g[0]["nears"]), (1, 1))
        self.assertEqual(g[0]["records"][0]["gap"], -0.1)    # gap น้อยสุดก่อน
        none_g = [x for x in g if x["key"] == (-1, 3)][0]
        self.assertEqual(len(none_g["records"]), 2)
        self.assertIsNone(none_g["host_a"])

    def test_csv(self):
        t = cc.to_csv_text([u"ก", u"b"], [[u'x,"y"', 1], [None, u"ไทย\nบรรทัด"]])
        self.assertEqual(t.split(u"\r\n")[0], u"ก,b")
        self.assertIn(u'"x,""y""",1', t)
        self.assertIn(u'"ไทย\nบรรทัด"', t)
        p = os.path.join(tempfile.mkdtemp(), "o.csv")
        cc.write_csv(p, [u"ก"], [[u"ข"]])
        with open(p, "rb") as f:
            raw = f.read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertEqual(raw[3:].decode("utf-8"), u"ก\r\nข\r\n")


if __name__ == "__main__":
    unittest.main()
