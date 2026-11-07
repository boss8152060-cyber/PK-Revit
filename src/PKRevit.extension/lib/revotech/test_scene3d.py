# -*- coding: utf-8 -*-
"""unit test ของ revotech.scene3d (รันนอก Revit): python test_scene3d.py"""
import os, sys, math, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from revotech import scene3d as sc


def grp(scene, key):
    for g in scene.groups:
        if g.key == key:
            return g
    return None


class TestMesh(unittest.TestCase):
    def test_tube_counts(self):
        pos, idx = sc.tube_mesh([[(0, 0, 0), (0, 0, 10), (5, 0, 10)]], 1.0, 6)
        self.assertEqual(len(pos) % 3, 0)
        self.assertEqual(len(idx) % 3, 0)
        self.assertTrue(max(idx) < len(pos) // 3)
        # 2 ท่อน x (6 ด้าน x 2 + 2 ฝา x 6) สามเหลี่ยม
        self.assertEqual(len(idx) // 3, 2 * (12 + 12))

    def test_tube_radius(self):
        pos, _ = sc.tube_mesh([[(0, 0, 0), (100, 0, 0)]], 3.0, 6)
        for i in range(0, 12 * 3, 3):   # 12 จุดวงแหวน (ท่อวางตามแกน x)
            self.assertAlmostEqual(math.hypot(pos[i + 1], pos[i + 2]), 3.0, places=6)

    def test_zero_length_skipped(self):
        pos, idx = sc.tube_mesh([[(1, 1, 1), (1, 1, 1)]], 1.0)
        self.assertEqual((pos, idx), ([], []))

    def test_triangulate_area(self):
        poly = [(0, 0), (2, 0), (2, 1), (1, 1), (1, 2), (0, 2)]   # ตัวแอล พื้นที่ 3
        tris = sc.triangulate(poly)
        self.assertEqual(len(tris), 4)
        a = sum(abs(sc.signed_area2([poly[i], poly[j], poly[k]])) for i, j, k in tris)
        self.assertAlmostEqual(a, 3.0)

    def test_triangulate_cw_input(self):
        poly = [(0, 0), (0, 2), (2, 2), (2, 0)]
        tris = sc.triangulate(poly)
        a = sum(abs(sc.signed_area2([poly[i], poly[j], poly[k]])) for i, j, k in tris)
        self.assertAlmostEqual(a, 4.0)

    def test_host_mesh_indices(self):
        pos, idx = sc.host_mesh(sc.Host.box(0, 0, 0, 10, 20, 30))
        self.assertEqual(len(pos) // 3, 8)
        self.assertTrue(max(idx) < 8)
        self.assertEqual(len(idx) // 3, 12)


class TestColumn(unittest.TestCase):
    def test_eight_bars(self):
        s = sc.column_scene(400, 400, 3000, 8, 16.0, 9.0)
        self.assertEqual(len(grp(s, "main").polys), 8)
        lo, hi = s.bounds()
        self.assertGreater(hi[2], 3000)     # เหล็กยื่นต่อทาบเหนือเสา
        for p in grp(s, "main").polys:
            self.assertLess(abs(p[0][0]), 200)
            self.assertLess(abs(p[0][1]), 200)

    def test_ties(self):
        s = sc.column_scene(400, 400, 3000, 4, 16.0, 9.0, end_len=600, sp_mid=150, sp_end=100)
        self.assertGreater(len(grp(s, "stirrup").polys), 20)
        for p in grp(s, "stirrup").polys:
            self.assertEqual(len(p), 5)

    def test_tiny_column_note(self):
        s = sc.column_scene(60, 60, 3000, 4, 16.0, 9.0)
        self.assertTrue(s.notes)
        self.assertEqual(s.bar_count(), 0)

    def test_n_changes_count(self):
        s12 = sc.column_scene(500, 500, 3000, 12, 16.0, 9.0)
        self.assertEqual(len(grp(s12, "main").polys), 12)


class TestBeam(unittest.TestCase):
    def test_groups_and_hooks(self):
        spec = {"top": [(3, 16.0, "DB16")], "bot": [(3, 20.0, "DB20"), (2, 20.0, "DB20")],
                "side": (2, 12.0, "DB12")}
        s = sc.beam_scene(5000, 250, 500, spec)
        self.assertEqual(len(grp(s, "top1").polys), 3)
        self.assertEqual(len(grp(s, "bot1").polys), 3)
        self.assertEqual(len(grp(s, "bot2").polys), 2)
        self.assertEqual(len(grp(s, "side").polys), 4)
        self.assertGreater(len(grp(s, "stirrup").polys), 10)
        p = grp(s, "top1").polys[0]          # เหล็กบนงอลงที่ปลาย
        self.assertEqual(len(p), 4)
        self.assertLess(p[0][2], p[1][2])
        q = grp(s, "bot1").polys[0]          # เหล็กล่างงอขึ้น
        self.assertGreater(q[0][2], q[1][2])

    def test_too_wide_reports(self):
        s = sc.beam_scene(4000, 150, 400, {"top": [(8, 25.0, "DB25")]})
        self.assertTrue(s.notes)

    def test_default_spec_runs(self):
        self.assertGreater(sc.beam_scene(6000, 300, 600).bar_count(), 5)


class TestFooting(unittest.TestCase):
    def test_rect_mat(self):
        s = sc.footing_scene(1800, 1500, 600, (12.0, 7), (12.0, 6), cover=75.0)
        self.assertEqual(len(grp(s, "long").polys), 7)
        self.assertEqual(len(grp(s, "short").polys), 6)
        lo, hi = s.bounds()
        self.assertLessEqual(hi[0], 900 + 1e-6)
        self.assertLessEqual(hi[1], 750 + 1e-6)
        # ชั้น long (ล่างสุด) ต่ำกว่า short: เทียบที่จุดกลางเส้น (ไม่รวมขางอ)
        zl = grp(s, "long").polys[0]
        zs = grp(s, "short").polys[0]
        self.assertLess(sorted(p[2] for p in zl)[0], sorted(p[2] for p in zs)[0])

    def test_hook_none_is_straight(self):
        s = sc.footing_scene(1800, 1800, 600, (12.0, 5), (12.0, 5), hook=sc.HOOK_NONE)
        self.assertEqual(len(grp(s, "long").polys[0]), 2)

    def test_hook_12d(self):
        s = sc.footing_scene(1800, 1800, 600, (12.0, 5), (12.0, 5), hook=sc.HOOK_12D)
        p = grp(s, "long").polys[0]
        self.assertEqual(len(p), 4)
        self.assertAlmostEqual(p[0][2] - p[1][2], 144.0)

    def test_ring(self):
        s = sc.footing_scene(1800, 1800, 600, (12.0, 5), (12.0, 5), ring=(9.0, 4, 120.0))
        self.assertEqual(len(grp(s, "ring").polys), 4)

    def test_from_bars(self):
        bars = [{"group": 0, "size": "DB12", "a": (0, 0), "b": (100, 0), "z": 90.0, "dia": 12.0}]
        s = sc.footing_scene_from_bars([(0, 0), (100, 0), (0, 100)], 600, bars)
        self.assertEqual(s.bar_count(), 1)


class TestSlab(unittest.TestCase):
    LAYERS = {"TX": (12.0, 200.0), "TY": (12.0, 200.0), "BX": (12.0, 150.0), "BY": (12.0, 150.0)}

    def test_two_layers_two_dirs(self):
        s = sc.slab_scene(4000, 3000, 150, self.LAYERS)
        self.assertEqual([g.key for g in s.groups], ["TX", "TY", "BX", "BY"])
        zs = dict((g.key, g.polys[0][0][2]) for g in s.groups)
        self.assertGreater(zs["TX"], zs["TY"])
        self.assertGreater(zs["TY"], zs["BY"])
        self.assertGreater(zs["BY"], zs["BX"])
        for g in s.groups:
            p = g.polys[0]
            if g.key.endswith("X"):
                self.assertEqual(p[0][1], p[1][1])
            else:
                self.assertEqual(p[0][0], p[1][0])

    def test_too_thick(self):
        s = sc.slab_scene(4000, 3000, 40, self.LAYERS)
        self.assertTrue(s.notes)
        self.assertEqual(s.bar_count(), 0)

    def test_spacing_changes_count(self):
        a = sc.slab_scene(4000, 3000, 150, {"BX": (12.0, 200.0)}).bar_count()
        b = sc.slab_scene(4000, 3000, 150, {"BX": (12.0, 100.0)}).bar_count()
        self.assertGreater(b, a * 1.8)


class _Geo(object):
    """stair_calc.Geo แบบย่อสำหรับทดสอบ"""
    def __init__(self, H, nr, nt, g):
        self.n_t, self.n_r, self.g, self.H = nt, nr, g, H
        self.r = H / float(nr)
        self.Lh = nt * g
        self.cos = math.cos(math.atan2(self.r, g))

    def nosing(self, s):
        return self.r + s * self.r / self.g

    def soffit(self, s, tw):
        return self.nosing(s) - tw / self.cos


class TestStair(unittest.TestCase):
    def test_profile_triangulates(self):
        prof = sc.stair_profile(_Geo(1800.0, 12, 11, 250.0), 150.0)
        tris = sc.triangulate(prof)
        self.assertEqual(len(tris), len(prof) - 2)
        a = sum(abs(sc.signed_area2([prof[i], prof[j], prof[k]])) for i, j, k in tris)
        self.assertAlmostEqual(a, abs(sc.signed_area2(prof)), places=3)

    def test_sets_expand(self):
        sets = [
            {"group": "waist", "kind": "szplane", "size": "DB12",
             "pts": [(-300, 100), (0, 100), (2750, 1700)], "t0": -500.0, "t1": 500.0, "count": 6},
            {"group": "crack", "kind": "transverse", "size": "RB9", "s": 50.0, "z": 200.0,
             "t_lo": -550.0, "t_hi": 550.0, "dir": (0.8, 0.6), "arr_len": 1000.0, "count": 5},
        ]
        s = sc.stair_scene(_Geo(1800.0, 12, 11, 250.0), 1200.0, sets, 150.0)
        self.assertEqual(len(grp(s, "waist").polys), 6)
        self.assertEqual(len(grp(s, "crack").polys), 5)
        self.assertAlmostEqual(grp(s, "waist").radius, 6.0)
        self.assertAlmostEqual(grp(s, "crack").radius, 4.5)
        self.assertAlmostEqual(grp(s, "crack").polys[-1][0][0], 50.0 + 0.8 * 1000.0)

    def test_landing_host(self):
        s = sc.stair_scene(_Geo(1800.0, 12, 11, 250.0), 1200.0, [], 150.0,
                           landing=(2750, 3750, -600, 600, 1800, 150))
        self.assertEqual(len(s.hosts), 2)


class TestScene(unittest.TestCase):
    def test_empty_bounds(self):
        self.assertEqual(sc.Scene().bounds()[0], (0.0, 0.0, 0.0))

    def test_legend_skips_empty(self):
        s = sc.Scene(groups=[sc.BarGroup("a", u"x", sc.RED, 5.0),
                             sc.BarGroup("b", u"y", sc.BLUE, 5.0, [[(0, 0, 0), (1, 0, 0)]])])
        self.assertEqual([l[0] for l in s.legend()], [u"y"])

    def test_spread(self):
        self.assertEqual(sc.spread(1, 0, 10), [5.0])
        self.assertEqual(sc.spread(3, 0, 10), [0.0, 5.0, 10.0])
        self.assertEqual(sc.spread(0, 0, 10), [])


if __name__ == "__main__":
    unittest.main()
