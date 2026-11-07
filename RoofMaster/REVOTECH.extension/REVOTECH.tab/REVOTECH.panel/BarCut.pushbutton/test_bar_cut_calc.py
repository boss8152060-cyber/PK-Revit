# -*- coding: utf-8 -*-
"""unit test (รันนอก Revit): python test_bar_cut_calc.py"""
import os
import tempfile
import unittest
import zipfile
import xml.dom.minidom as md
import bar_cut_calc as bc
import bar_cut_export as ex


def rec(size, ln, n, kind=u"beam", host=1, shape=None):
    return {"size": size, "length_mm": ln, "count": n, "kind": kind,
            "host": host, "shape": shape or ((ln, 0),)}


class T(unittest.TestCase):
    def test_kind(self):
        self.assertEqual(bc.parse_kind(u"REVOTECH:column"), u"column")
        self.assertEqual(bc.parse_kind(u"REVOTECH:roofcover:x"), u"roofcover")
        self.assertIsNone(bc.parse_kind(u"abc"))
        self.assertIsNone(bc.parse_kind(None))

    def test_weight(self):
        self.assertAlmostEqual(bc.unit_weight(u"DB12"), 0.888)
        self.assertAlmostEqual(bc.unit_weight(u"DB40"), 1600 / 162.2)
        self.assertAlmostEqual(bc.unit_weight(u"DB12", {u"DB12": 1.0}), 1.0)

    def test_group(self):
        rows = bc.group_bars([rec(u"DB16", 3000, 2, shape=((3000, 0),)), rec(u"DB16", 3002, 3, host=2, shape=((3000, 0),)),
                              rec(u"DB12", 5000, 4), rec(u"DB16", 6000, 1)])
        self.assertEqual([r["no"] for r in rows], [1, 2, 3])
        self.assertEqual(rows[0]["size"], u"DB12")
        self.assertEqual(rows[1]["length_mm"], 6000)
        self.assertEqual(rows[2]["count"], 5)
        self.assertAlmostEqual(rows[2]["total_m"], 15.0)
        self.assertAlmostEqual(rows[0]["weight_kg"], 20 * 0.888)

    def test_shape_differs(self):
        a = bc.shape_signature([(300, 90), (3000, 90), (300, 0)])
        b = bc.shape_signature([(3600, 0)])
        rows = bc.group_bars([rec(u"DB12", 3600, 1, shape=a),
                              rec(u"DB12", 3600, 1, shape=b)])
        self.assertEqual(len(rows), 2)
        self.assertEqual(bc.shape_label(b), u"ตรง 3600")
        self.assertIn(u"300 + 3000 + 300", bc.shape_label(a))

    def test_shape_canonical(self):
        a = bc.shape_signature([(300, 90), (3000, 90), (500, 0)])
        b = bc.shape_signature([(500, 90), (3000, 90), (300, 0)])
        self.assertEqual(a, b)

    def test_ffd_basic(self):
        bins, over = bc.ffd_plan([6000, 4000, 6000, 4000], 10000, 0)
        self.assertEqual(len(bins), 2)
        self.assertEqual(over, [])
        self.assertAlmostEqual(bins[0]["waste_mm"], 0)

    def test_ffd_kerf(self):
        bins, _ = bc.ffd_plan([5000, 5000], 10000, 3)
        self.assertEqual(len(bins), 2)
        bins, _ = bc.ffd_plan([4990, 5000], 10000, 3)
        self.assertEqual(len(bins), 1)
        self.assertAlmostEqual(bins[0]["waste_mm"], 10000 - 4990 - 5000 - 3)

    def test_ffd_oversize_and_order(self):
        bins, over = bc.ffd_plan([12500, 3000, 9000, 1000], 10000, 0)
        self.assertEqual(over, [12500])
        self.assertEqual(len(bins), 2)
        self.assertEqual(bins[0]["pieces"], [9000, 1000])

    def test_plan_totals(self):
        rows = bc.group_bars([rec(u"DB12", 4000, 5), rec(u"DB16", 7000, 3)])
        plan = bc.cutting_plan(rows, 10, 0)
        t = plan["total"]
        # DB12 4000x5 -> 3 ท่อน, DB16 7000x3 -> 3 ท่อน
        self.assertEqual(t["stock"], 6)
        self.assertAlmostEqual(t["use_len_m"], 20 + 21)
        self.assertAlmostEqual(t["waste_len_m"], 60 - 41)
        self.assertAlmostEqual(t["waste_pct_len"], 19 / 60.0 * 100)
        self.assertAlmostEqual(plan["by_size"][0]["waste_kg"], 10 * 0.888)
        self.assertEqual(plan["patterns"][0]["name"], u"A")
        self.assertEqual(sum(p["n"] for p in plan["patterns"]), 6)

    def test_pattern_name(self):
        self.assertEqual(bc.pattern_name(0), u"A")
        self.assertEqual(bc.pattern_name(25), u"Z")
        self.assertEqual(bc.pattern_name(26), u"AA")

    def test_summary(self):
        s = {"hosts": 32, "marks": 207, "weight_kg": 7407.2, "stock_m": 10.0,
             "stock_n": 615}
        self.assertEqual(bc.summary_text(s),
                         u"32 แนว · 207 เลข · 7,407 กก. · 10 ม. 615 ท่อน")

    def test_sheet_numbers(self):
        n = bc.sheet_numbers([u"footing", u"beam"], existing=[u"FT-01"])
        self.assertEqual(n[u"footing"], u"FT-02")
        self.assertEqual(n[u"beam"], u"BC-01")
        self.assertEqual(n["all"], u"BC-00")

    def test_export(self):
        rows = bc.group_bars([rec(u"DB12", 4000, 5), rec(u"DB16", 7000, 3)])
        plan = bc.cutting_plan(rows, 12, 3)
        tabs = ex.build_tables(rows, plan, u"x & <y>")
        d = tempfile.mkdtemp()
        p = os.path.join(d, "a.xlsx")
        ex.write_xlsx(p, tabs)
        z = zipfile.ZipFile(p)
        self.assertIsNone(z.testzip())
        for n in z.namelist():
            md.parseString(z.read(n))
        self.assertIn("xl/worksheets/sheet3.xml", z.namelist())
        self.assertIn("x &amp; &lt;y&gt;",
                      z.read("xl/worksheets/sheet3.xml").decode("utf-8"))
        z.close()
        c = os.path.join(d, "a.csv")
        ex.write_csv(c, tabs)
        raw = open(c, "rb").read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        self.assertIn(u"เลข".encode("utf-8"), raw)

    def test_col(self):
        self.assertEqual(ex._col(0), "A")
        self.assertEqual(ex._col(26), "AA")


if __name__ == "__main__":
    unittest.main()
