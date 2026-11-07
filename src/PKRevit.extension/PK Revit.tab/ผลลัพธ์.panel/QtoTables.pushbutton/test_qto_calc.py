# -*- coding: utf-8 -*-
"""unit test ฟังก์ชันคำนวณ (รันนอก Revit): python test_qto_calc.py"""
from __future__ import unicode_literals
import io
import os
import tempfile
import unittest
import qto_calc as q


def F(t, L, w=None):
    return {"type": t, "length_m": L, "kg_per_m": w}


class T(unittest.TestCase):
    def test_classify(self):
        c = q.classify_framing
        self.assertEqual(c("แป C75x45"), "purlin")
        self.assertEqual(c("จันทัน 50x100"), "rafter")
        self.assertEqual(c("ตะเข้สัน 50x150"), "hip")
        self.assertEqual(c("ตะเฆ่สัน"), "hip")
        self.assertEqual(c("อกไก่ 75x150"), "ridge")
        self.assertEqual(c("รางน้ำ"), "gutter")
        self.assertEqual(c("ตะเฆ่ราง"), "valley_hip")
        self.assertEqual(c("ตะเข้ ราง"), "valley_hip")   # ช่องว่างไม่สำคัญ
        self.assertEqual(c("ดั้ง 50x100"), "king")
        self.assertIsNone(c("คานเหล็ก H200"))

    def test_framing_sum(self):
        items = [F("แป C75", 4.0, 5.0), F("แป C75", 6.0, 5.0),
                 F("จันทัน 50x100", 3.0), F("จันทัน 50x100", 3.5),
                 F("คาน", 9.0)]
        kinds, types, unk = q.summarize_framing(items)
        self.assertEqual(kinds["purlin"]["pieces"], 2)
        self.assertAlmostEqual(kinds["purlin"]["length_m"], 10.0)
        self.assertAlmostEqual(kinds["purlin"]["weight_kg"], 50.0)
        self.assertEqual(kinds["rafter"]["pieces"], 2)
        self.assertEqual(kinds["rafter"]["no_weight_pieces"], 2)
        self.assertEqual(unk, {"คาน": 1})
        rf = [t for t in types if t["kind"] == "rafter"][0]
        self.assertIsNone(rf["weight_kg"])

    def test_rows_and_note(self):
        kinds, types, _ = q.summarize_framing(
            [F("แป", 4.0, 5.0), F("จันทัน", 3.0)])
        rows = q.frame_rows(kinds, types)
        self.assertEqual(rows[-1][0], "รวมโครงหลังคา")
        self.assertEqual(rows[-1][2], 2)
        self.assertTrue(rows[-1][5].endswith("*"))
        self.assertEqual([r[5] for r in rows if r[0] == "จันทัน"][0], "")
        self.assertIn("1 ท่อน", q.weight_note(kinds))
        k2, t2, _ = q.summarize_framing([F("แป", 4.0, 5.0)])
        self.assertEqual(q.weight_note(k2), "")

    def test_empty(self):
        k, t, u = q.summarize_framing([])
        self.assertEqual(q.frame_rows(k, t), [])

    def test_cover(self):
        c = q.classify_cover
        self.assertEqual(c("Monier Elabana"), "sheet")
        self.assertEqual(c("Ridge cap"), "ridge_cap")
        self.assertEqual(c("ครอบสัน"), "ridge_cap")
        self.assertEqual(c("Fascia board"), "fascia")
        self.assertEqual(c("ปั้นลม"), "verge")
        self.assertEqual(c(""), q.COVER_UNKNOWN)
        self.assertEqual(c(None), q.COVER_UNKNOWN)
        s = q.summarize_cover([{"material": "Monier", "area_m2": 10.5},
                               {"material": "Monier", "area_m2": 4.5},
                               {"material": "", "area_m2": 1.0}])
        self.assertEqual(s["sheet"]["pieces"], 2)
        self.assertAlmostEqual(s["sheet"]["area_m2"], 15.0)
        rows = q.cover_rows(s)
        self.assertEqual(rows[0][1], 2)
        self.assertEqual(rows[0][2], "15.00")

    def test_weight_param(self):
        self.assertTrue(q.is_weight_param("Weight per Meter"))
        self.assertTrue(q.is_weight_param("น้ำหนัก ต่อ เมตร".replace(" ", "")))
        self.assertFalse(q.is_weight_param("Weight"))

    def test_csv_bom(self):
        k, t, u = q.summarize_framing([F("แป, C", 4.0, 5.0), F("x", 1)])
        p = os.path.join(tempfile.mkdtemp(), "q.csv")
        q.write_csv(p, q.csv_tables(k, t, {}, u))
        raw = open(p, "rb").read()
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"))
        txt = io.open(p, encoding="utf-8-sig").read()
        self.assertIn('"แป, C"', txt)
        self.assertIn("ไม่นับ", txt)


if __name__ == "__main__":
    unittest.main()
