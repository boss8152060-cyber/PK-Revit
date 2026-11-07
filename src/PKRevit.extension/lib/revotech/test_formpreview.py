# -*- coding: utf-8 -*-
"""unit test ของ revotech.formpreview / previewfit.fit_distance (รันนอก Revit): python test_formpreview.py"""
import os, sys, glob, math, types, unittest
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))
MODS = glob.glob(os.path.join(HERE, "..", "..", "PK Revit.tab", "*", "Rebar.pushbutton", "modules"))[0]
for m in ("RebarFooting", "RebarSlab", "RebarStair"):
    sys.path.insert(0, os.path.join(MODS, m + ".pushbutton"))
import footing_calc as fc
import slab_calc as sl
import stair_calc as st
from revotech import formpreview as fpv
from revotech import scene3d


def _load_fit():
    """previewfit ต้องใช้ WPF — โหลดเฉพาะส่วนฟังก์ชันล้วน (ก่อน class)"""
    src = open(os.path.join(HERE, "previewfit.py"), encoding="utf-8").read()
    head = src.split("class FitPreview3D")[0]
    head = head.replace("from revotech import preview3d as _p", "").replace(
        "from revotech.preview3d import Preview3D", "")
    mod = types.ModuleType("fit")
    exec(compile(head, "previewfit_head", "exec"), mod.__dict__)
    return mod


fit = _load_fit()
COL = dict(n=8, d_main=16.0, d_tie=9.0, cover=25.0, end_len=600.0, sp_mid=150.0, sp_end=100.0, lap_d=40.0)


class TestColumn(unittest.TestCase):
    def test_full(self):
        s = fpv.column_preview((400, 400, 3000), COL)
        self.assertEqual(len(s.groups[0].polys), 8)
        self.assertEqual(s.notes, [])

    def test_matches_builder(self):
        a = fpv.column_preview((400, 500, 3200), COL)
        b = scene3d.column_scene(400, 500, 3200, 8, 16.0, 9.0, 25.0, 600.0, 150.0, 100.0, 40.0)
        self.assertEqual(a.bar_count(), b.bar_count())

    def test_no_extent(self):
        s = fpv.column_preview(None, COL)
        self.assertTrue(any(u"อ่านรูปทรง" in n for n in s.notes))
        self.assertGreater(s.bar_count(), 0)

    def test_missing_size(self):
        s = fpv.column_preview((400, 400, 3000), dict(COL, d_main=None))
        self.assertEqual(s.bar_count(), 0)
        self.assertEqual(len(s.hosts), 1)

    def test_multi(self):
        s = fpv.column_preview((400, 400, 3000), COL, 5)
        self.assertEqual(s.notes[0], u"แสดงตัวอย่างชิ้นที่ 1 จาก 5")

    def test_tiny_spacing(self):
        s = fpv.column_preview((400, 400, 3000), dict(COL, sp_mid=0.0))
        self.assertEqual(s.bar_count(), 0)


class TestBeam(unittest.TestCase):
    def test_default_spec(self):
        s = fpv.beam_preview((5000, 250, 500), scene3d.default_beam_spec(), 2)
        self.assertGreater(s.bar_count(), 0)
        self.assertEqual(s.notes[0], u"แสดงตัวอย่างชิ้นที่ 1 จาก 2")

    def test_none_spec(self):
        s = fpv.beam_preview(None, None)
        self.assertEqual(s.bar_count(), 0)
        self.assertTrue(s.notes)

    def test_empty_bars(self):
        sp = scene3d.default_beam_spec()
        sp["top"] = [(0, 16.0, "DB16")] * 2
        sp["bot"] = [(0, 16.0, "DB16")] * 2
        s = fpv.beam_preview((5000, 250, 500), sp)
        self.assertEqual(s.bar_count(), 0)


FV = {"long": ("DB12", 5), "short": ("DB12", 5),
      "tri": {0: ("DB12", 3), 60: ("DB12", 3), 120: ("DB12", 3)},
      "hook": fc.HOOK_90, "ring": (True, "RB9", 2, 150.0), "cover": 75.0}


class TestFooting(unittest.TestCase):
    rect = {"poly": [(-1000, -750), (1000, -750), (1000, 750), (-1000, 750)], "kind": "rect", "height": 500}
    tri = {"poly": [(0, 0), (2000, 0), (1000, 1732)], "kind": "tri", "height": 600}

    def test_rect(self):
        s = fpv.footing_preview(fc, self.rect, FV)
        keys = [g.key for g in s.groups]
        self.assertEqual(keys[:2], ["long", "short"])
        self.assertIn("ring", keys)

    def test_tri(self):
        s = fpv.footing_preview(fc, self.tri, FV)
        self.assertEqual(sorted(g.key for g in s.groups if g.key != "ring"), [0, 60, 120])

    def test_placeholder(self):
        v = dict(FV, long=(fc.PLACEHOLDER, 4), short=(fc.PLACEHOLDER, 4))
        self.assertEqual(fpv.footing_preview(fc, self.rect, v).bar_count(), 0)

    def test_partial(self):
        v = dict(FV, short=(fc.PLACEHOLDER, 4), ring=(False, None, 0, 0))
        s = fpv.footing_preview(fc, self.rect, v)
        self.assertEqual([g.key for g in s.groups], ["long"])

    def test_unreadable_and_unsupported(self):
        self.assertTrue(any(u"อ่านรูปทรง" in n for n in fpv.footing_preview(fc, None, FV).notes))
        s = fpv.footing_preview(fc, {"poly": self.rect["poly"], "kind": None, "height": 500}, FV)
        self.assertEqual(s.bar_count(), 0)


class TestSlab(unittest.TestCase):
    shape = {"outer": [(0, 0), (4000, 0), (4000, 3000), (0, 3000)], "holes": [], "H": 150.0}
    V = {"mode": sl.MODE_BAR, "cover": 20.0, "edge": (False, None, 0, 0),
         "layers": {"TX": ("DB12", 200.0), "TY": (sl.PLACEHOLDER, 0.0),
                    "BX": ("DB12", 200.0), "BY": ("DB12", 200.0)}}

    def test_layers(self):
        s = fpv.slab_preview(sl, self.shape, self.V)
        self.assertEqual(sorted(g.key for g in s.groups), ["BX", "BY", "TX"])

    def test_matches_plan(self):
        layers = {"TX": ("DB12", 200.0), "BX": ("DB12", 200.0), "BY": ("DB12", 200.0)}
        bars, _ = sl.plan_layers(self.shape["outer"], [], 150.0, 20.0, layers, fpv.dia_mm)
        self.assertEqual(fpv.slab_preview(sl, self.shape, self.V).bar_count(), len(bars))

    def test_mesh_and_error(self):
        s = fpv.slab_preview(sl, self.shape, dict(self.V, mode=sl.MODE_MESH))
        self.assertEqual(s.bar_count(), 0)
        s = fpv.slab_preview(sl, {"error": u"พื้นเอียง"}, self.V)
        self.assertTrue(any(u"พื้นเอียง" in n for n in s.notes))
        self.assertGreater(s.bar_count(), 0)


class TestStair(unittest.TestCase):
    RUN = {"geo": st.Geo(3000.0, 17, 16, 250.0), "W": 1200.0}
    G = dict((k, {"on": True, "size": "DB12", "sp": 200.0}) for k in st.GROUP_ORDER)
    V = {"groups": G, "cover": 25.0, "tw": 150.0, "tl": 150.0, "anchor": 300.0,
         "ext_len": 400.0, "ext_run": 600.0, "ext_lower": False}

    def test_full(self):
        s = fpv.stair_preview(st, self.RUN, self.V, 3, u"หมายเหตุ")
        self.assertGreater(s.bar_count(), 0)
        self.assertEqual(s.notes[0], u"แสดงตัวอย่างชิ้นที่ 1 จาก 3")
        self.assertIn(u"หมายเหตุ", s.notes)

    def test_none_selected(self):
        G = dict((k, {"on": True, "size": st.PLACEHOLDER, "sp": 200.0}) for k in st.GROUP_ORDER)
        s = fpv.stair_preview(st, self.RUN, dict(self.V, groups=G))
        self.assertEqual(s.bar_count(), 0)
        self.assertEqual(len(s.hosts), 1)

    def test_no_run(self):
        s = fpv.stair_preview(st, None, self.V)
        self.assertTrue(s.notes)
        self.assertGreater(s.bar_count(), 0)


class TestFit(unittest.TestCase):
    def _worst(self, lo, hi, aspect, yaw=-52.0, pit=24.0, fov=38.0):
        c = tuple((a + b) / 2.0 for a, b in zip(lo, hi))
        d = fit.fit_distance((lo, hi), c, yaw, pit, aspect, fov, margin=1.0)
        y, p = math.radians(yaw), math.radians(pit)
        cd = (math.cos(p) * math.sin(y), -math.cos(p) * math.cos(y), math.sin(p))
        f = tuple(-x for x in cd)
        r = (f[1], -f[0], 0.0)
        n = math.hypot(r[0], r[1])
        r = (r[0] / n, r[1] / n, 0.0)
        u = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])
        tx = math.tan(math.radians(fov) / 2.0)
        ty = tx / aspect
        worst = 0.0
        for X in (lo[0], hi[0]):
            for Y in (lo[1], hi[1]):
                for Z in (lo[2], hi[2]):
                    v = (X - c[0], Y - c[1], Z - c[2])
                    dep = d - sum(a * b for a, b in zip(v, cd))
                    worst = max(worst, abs(sum(a * b for a, b in zip(v, r))) / dep / tx,
                                abs(sum(a * b for a, b in zip(v, u))) / dep / ty)
        return worst

    def test_tight(self):
        for aspect in (0.66, 1.0, 1.5):
            for box in (((-200, -200, 0), (200, 200, 3000)), ((0, -125, 0), (5000, 125, 500))):
                self.assertAlmostEqual(self._worst(box[0], box[1], aspect), 1.0, places=6)

    def test_tall_closer_than_sphere(self):
        lo, hi = (-200, -200, 0), (200, 200, 3000)
        sphere = 0.5 * math.sqrt(400 ** 2 * 2 + 3000 ** 2) / math.sin(math.radians(19)) * 1.2
        self.assertLess(fit.fit_distance((lo, hi), (0, 0, 1500), -52, 24, 0.66, 38.0), sphere)


if __name__ == "__main__":
    unittest.main()
