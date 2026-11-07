# -*- coding: utf-8 -*-
"""unit test (รันนอก Revit): python test_manage_calc.py"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "..", "lib", "revotech"))
import managecalc as mc  # noqa: E402


ITEMS = [(u"Rebar", u"PKRevit:column"), (u"Rebar", None), (u"Rebar", u"  PKRevit:beam"),
         (u"FabricSheet", u"PKRevit:slab:mesh"), (u"AreaReinforcement", u"manual"),
         (u"Rebar", u"my PKRevit:x")]


class T(unittest.TestCase):
    def test_is_pk(self):
        self.assertTrue(mc.is_pk(u"PKRevit:slab"))
        self.assertTrue(mc.is_pk(u" PKRevit:slab"))
        self.assertFalse(mc.is_pk(u"pkrevit:slab"))
        self.assertFalse(mc.is_pk(u""))
        self.assertFalse(mc.is_pk(None))
        self.assertFalse(mc.is_pk(u"my PKRevit:x"))

    def test_count_order(self):
        c = mc.count_kinds([u"RebarInSystem", u"Rebar", u"Rebar", u"FabricSheet", u"Zed"])
        self.assertEqual(c, [(u"Rebar", 2), (u"FabricSheet", 1),
                             (u"RebarInSystem", 1), (u"Zed", 1)])
        self.assertEqual(mc.count_kinds([]), [])

    def test_delete_pk_only(self):
        self.assertEqual(mc.delete_indices(ITEMS, True), [0, 2, 3])
        self.assertEqual(mc.delete_counts(ITEMS, True),
                         [(u"Rebar", 2), (u"FabricSheet", 1)])

    def test_delete_all(self):
        self.assertEqual(mc.delete_indices(ITEMS, False), list(range(6)))
        self.assertEqual(dict(mc.delete_counts(ITEMS, False))[u"Rebar"], 4)

    def test_warning(self):
        self.assertIsNone(mc.system_warning(mc.delete_counts(ITEMS, True)))
        w = mc.system_warning(mc.delete_counts(ITEMS, False))
        self.assertIn(u"1 ชุด", w)
        self.assertIsNone(mc.system_warning([]))

    def test_lines(self):
        self.assertEqual(mc.count_lines([(u"Rebar", 3)], u""),
                         [u"เหล็กเส้น (Rebar): 3 รายการ"])

    def test_skipped(self):
        self.assertEqual(mc.skipped_summary(5, 3), u"ข้าม 2 ตัวที่ไม่พบเหล็ก")
        self.assertIsNone(mc.skipped_summary(3, 3))

    def test_obscured(self):
        self.assertEqual(mc.obscured_types(True, False, True), [u"rebar", u"fabric"])
        self.assertTrue(mc.obscured_needs_area_path_hosts([u"OST_Floors"], [u"areapath"]))
        self.assertFalse(mc.obscured_needs_area_path_hosts([u"OST_StructuralColumns"], [u"areapath"]))
        self.assertFalse(mc.obscured_needs_area_path_hosts([u"OST_Floors"], [u"rebar"]))
        self.assertIsNotNone(mc.validate_obscured([], [u"rebar"]))
        self.assertIsNotNone(mc.validate_obscured([u"OST_Floors"], []))
        self.assertIsNotNone(mc.validate_obscured([u"OST_StructuralColumns"], [u"areapath"]))
        self.assertIsNone(mc.validate_obscured([u"OST_StructuralColumns"], [u"areapath", u"rebar"]))
        self.assertIsNone(mc.validate_obscured([u"OST_Walls"], [u"areapath"]))

    def test_split(self):
        self.assertEqual(mc.split_by_cat([(1, u"a"), (2, u"b"), (3, u"a")], [u"a"]), [1, 3])


if __name__ == "__main__":
    unittest.main()
