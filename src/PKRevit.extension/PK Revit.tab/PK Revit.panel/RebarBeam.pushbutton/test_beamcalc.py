# -*- coding: utf-8 -*-
"""unit test ของ revotech.beamcalc (รันนอก Revit): python test_beamcalc.py"""
import os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "lib"))
from revotech import beamcalc as bc


def spec(**kw):
    s = {"cover": 25.0, "d_tie": 9.0, "max_len": 10000.0, "lap_d": 40.0,
         "hook_mult": 12.0, "top": [(3, 16.0, "DB16"), (0, 16.0, "DB16")],
         "bot": [(3, 16.0, "DB16"), (0, 16.0, "DB16")], "xtop": None,
         "xbot": None, "side": None, "end_len": 800.0, "sp_end": 100.0,
         "sp_mid": 200.0}
    s.update(kw)
    return s


class T(unittest.TestCase):
    def test_short_no_cut(self):
        self.assertEqual(bc.splice_n(8000, 10000, 640), 1)
        self.assertEqual(bc.splice_cuts(8000, 1, 'top'), [])

    def test_long_cuts_not_same_point(self):
        for L in (10500, 12000, 18000, 25000, 40000):
            lap = 640.0
            n = bc.splice_n(L, 10000, lap)
            t = bc.splice_cuts(L, n, 'top')
            b = bc.splice_cuts(L, n, 'bottom')
            self.assertEqual(len(t), len(b))
            self.assertGreaterEqual(bc.min_splice_separation(t, b), lap)
            for ps in (bc.pieces(L, t, lap), bc.pieces(L, b, lap)):
                for (x, y) in ps:
                    self.assertLessEqual(y - x, 10000 + 1e-6)
                self.assertAlmostEqual(ps[0][0], 0)
                self.assertAlmostEqual(ps[-1][1], L)
                for i in range(len(ps) - 1):   # ทาบกันเท่า lap
                    self.assertAlmostEqual(ps[i][1] - ps[i + 1][0], lap)

    def test_plan_long_beam(self):
        bars, errs, warns, info = bc.plan_longitudinal(
            0, 12000, -150, 150, -500, 0, spec())
        self.assertEqual(errs, [])
        tops = [x for x in bars if x["role"] == "top1"]
        self.assertEqual(len(tops), 3 * 2)
        self.assertEqual(len(set(info["top_cuts"]) & set(info["bot_cuts"])), 0)
        hooks = [x for x in tops if x["hook_a"] or x["hook_b"]]
        self.assertEqual(len(hooks), 3 * 2)   # ปลายคานเท่านั้น ไม่งอตรงรอยต่อ
        for x in bars:
            self.assertGreaterEqual(x["s_a"], 25 - 1e-6 - 1e-9 - 320)

    def test_two_layers_and_extras(self):
        sp = spec(top=[(3, 20.0, "DB20"), (2, 20.0, "DB20")],
                  xtop=(2, 16.0, "DB16", 'ends', 4),
                  xbot=(2, 16.0, "DB16", 'mid', 4),
                  side=(2, 12.0, "DB12"))
        bars, errs, _, _ = bc.plan_longitudinal(0, 6000, -150, 150, -600, 0, sp)
        self.assertEqual(errs, [])
        roles = {}
        for x in bars:
            roles[x["role"]] = roles.get(x["role"], 0) + 1
        self.assertEqual(roles["top1"], 3)
        self.assertEqual(roles["top2"], 2)
        self.assertEqual(roles["xtop"], 4)    # 2 เส้น x 2 ปลาย
        self.assertEqual(roles["xbot"], 2)
        self.assertEqual(roles["side"], 4)
        v1 = [x["v"] for x in bars if x["role"] == "top1"][0]
        v2 = [x["v"] for x in bars if x["role"] == "top2"][0]
        self.assertGreater(v1 - v2, 20.0 + 25.0 - 1e-6)

    def test_too_many_bars(self):
        sp = spec(top=[(8, 25.0, "DB25"), (0, 25.0, "DB25")])
        _, errs, _, _ = bc.plan_longitudinal(0, 6000, -100, 100, -500, 0, sp)
        self.assertTrue(errs)

    def test_shallow_clash(self):
        sp = spec(top=[(2, 25.0, "DB25"), (2, 25.0, "DB25")],
                  bot=[(2, 25.0, "DB25"), (2, 25.0, "DB25")])
        _, errs, _, _ = bc.plan_longitudinal(0, 6000, -150, 150, -200, 0, sp)
        self.assertTrue(errs)

    def test_stirrup_zones(self):
        z = bc.stirrup_zones(25, 5975, 800, 100, 200)
        self.assertEqual(len(z), 3)
        self.assertAlmostEqual(z[0][0] + z[0][1], 825)
        self.assertAlmostEqual(z[2][0] + z[2][1], 5975)
        self.assertLessEqual(z[2][0] - (z[1][0] + z[1][1]), 200 + 1e-6)
        self.assertEqual(len(bc.stirrup_zones(0, 1500, 800, 100, 200)), 1)
        self.assertEqual(bc.stirrup_count(800, 100), 9)
        self.assertEqual(bc.stirrup_count(0, 100), 1)

    def test_extra_segments(self):
        self.assertEqual(bc.extra_segments(8000, 'mid', 4), [(2000.0, 6000.0, False, False)])
        e = bc.extra_segments(8000, 'ends', 4)
        self.assertEqual(e[0][:2], (0.0, 2000.0))
        self.assertEqual(e[1][:2], (6000.0, 8000.0))


if __name__ == "__main__":
    unittest.main()
