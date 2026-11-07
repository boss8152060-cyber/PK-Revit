# -*- coding: utf-8 -*-
"""unit test ของ revotech.colorcalc (รันนอก Revit): python test_colorcalc.py"""
import os
import sys
import tempfile
import unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "..", "lib"))
from revotech import colorcalc as cl


class Colors(unittest.TestCase):
    def test_hsv(self):
        self.assertEqual(cl.hsv_to_rgb(0, 1, 1), (255, 0, 0))
        self.assertEqual(cl.hsv_to_rgb(120, 1, 1), (0, 255, 0))
        self.assertEqual(cl.hsv_to_rgb(240, 1, 1), (0, 0, 255))
        self.assertEqual(cl.hsv_to_rgb(0, 0, 1), (255, 255, 255))

    def test_generate(self):
        for scheme in (cl.SCHEME_GRADIENT, cl.SCHEME_CONTRAST):
            for n in (0, 1, 2, 15):
                cs = cl.generate_colors(n, scheme)
                self.assertEqual(len(cs), n)
                for c in cs:
                    self.assertTrue(all(0 <= x <= 255 for x in c))
        cs = cl.generate_colors(20, cl.SCHEME_CONTRAST)
        self.assertEqual(len(set(cs)), 20)             # ไม่ซ้ำ
        self.assertNotEqual(cl.generate_colors(5, cl.SCHEME_CONTRAST, 0),
                            cl.generate_colors(5, cl.SCHEME_CONTRAST, 1))
        self.assertEqual(cl.generate_colors(5, cl.SCHEME_CONTRAST, 3),
                         cl.generate_colors(5, cl.SCHEME_CONTRAST, 3))

    def test_contrast_adjacent_differ(self):
        cs = cl.generate_colors(12, cl.SCHEME_CONTRAST)
        for a, b in zip(cs, cs[1:]):
            self.assertGreater(sum(abs(x - y) for x, y in zip(a, b)), 120)

    def test_hex(self):
        self.assertEqual(cl.to_hex((255, 0, 16)), u"#FF0010")
        self.assertEqual(cl.from_hex(u"#ff0010"), (255, 0, 16))
        self.assertIsNone(cl.from_hex(u"xyz"))
        self.assertIsNone(cl.from_hex(None))


class Values(unittest.TestCase):
    def test_natural_sort(self):
        v = [u"B10", u"B2", cl.NONE_VALUE, u"a1", u"B1"]
        self.assertEqual(cl.sorted_values(v),
                         [u"a1", u"B1", u"B2", u"B10", cl.NONE_VALUE])

    def test_norm_and_group(self):
        self.assertEqual(cl.norm_value(None), cl.NONE_VALUE)
        self.assertEqual(cl.norm_value(u"  "), cl.NONE_VALUE)
        g = cl.group_values([(1, 10, u"A"), (1, 11, u"A"), (2, 10, u"A"),
                             (1, 12, None), (2, 13, u" B ")])
        self.assertEqual(g[u"A"], {1: [10, 11], 2: [10]})
        self.assertEqual(cl.count_of(g[u"A"]), 3)
        self.assertIn(u"B", g)
        self.assertIn(cl.NONE_VALUE, g)

    def test_assign_remembered(self):
        rem = {u"A": u"#010203"}
        c = cl.assign_colors([u"B", u"A", u"C"], cl.SCHEME_CONTRAST, rem)
        self.assertEqual(c[u"A"], (1, 2, 3))
        self.assertEqual(len(set(c.values())), 3)
        first = cl.generate_colors(3, cl.SCHEME_CONTRAST)[0]
        c = cl.assign_colors([u"A", u"B"], cl.SCHEME_CONTRAST, {u"A": cl.to_hex(first)})
        self.assertNotEqual(c[u"B"], c[u"A"])


class State(unittest.TestCase):
    def setUp(self):
        self.path = os.path.join(tempfile.mkdtemp(), "sub", "c.json")

    def test_roundtrip_thai(self):
        st = cl.load_state(self.path)
        self.assertEqual(st["colors"], {})
        k = cl.param_key("rebar", u"Mark")
        cl.remember_colors(st, k, {u"ก-1": (1, 2, 3)})
        cl.record_applied(st, u"D:/x.rvt", 7, {100: (1, 2, 3), 101: (4, 5, 6)})
        cl.save_state(st, self.path)
        st2 = cl.load_state(self.path)
        self.assertEqual(cl.remembered_for(st2, k), {u"ก-1": u"#010203"})
        self.assertEqual(cl.applied_for(st2, u"D:/x.rvt", 7),
                         {u"7": {100: u"#010203", 101: u"#040506"}})

    def test_corrupt_file(self):
        os.makedirs(os.path.dirname(self.path))
        with open(self.path, "w") as f:
            f.write("{not json")
        self.assertEqual(cl.load_state(self.path)["applied"], {})

    def test_applied_scoped_per_doc_and_view(self):
        st = cl.load_state(self.path)
        cl.record_applied(st, u"A", 1, {1: (0, 0, 0)})
        cl.record_applied(st, u"A", 2, {2: (0, 0, 0)})
        cl.record_applied(st, u"B", 1, {3: (0, 0, 0)})
        self.assertEqual(sorted(cl.applied_for(st, u"A")), [u"1", u"2"])
        self.assertEqual(cl.applied_for(st, u"B", 1)[u"1"], {3: u"#000000"})
        cl.forget_applied(st, u"A", 1)
        self.assertEqual(sorted(cl.applied_for(st, u"A")), [u"2"])
        cl.forget_applied(st, u"A", 2, [2])
        self.assertEqual(cl.applied_for(st, u"A"), {})
        self.assertNotIn(u"A", st["applied"])
        self.assertIn(u"B", st["applied"])        # ไม่แตะเอกสารอื่น

    def test_should_reset_only_ours(self):
        self.assertTrue(cl.should_reset((1, 2, 3), u"#010203"))
        self.assertFalse(cl.should_reset((9, 9, 9), u"#010203"))   # คนอื่นเปลี่ยนแล้ว
        self.assertFalse(cl.should_reset(None, u"#010203"))


if __name__ == "__main__":
    unittest.main()
