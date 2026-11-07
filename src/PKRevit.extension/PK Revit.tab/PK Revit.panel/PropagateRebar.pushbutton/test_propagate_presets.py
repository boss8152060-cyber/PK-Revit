# -*- coding: utf-8 -*-
"""unit test ของ hostconfig / presetlogic / presetstore (ส่วนตรรกะล้วน รันนอก Revit)
python test_propagate_presets.py"""
import os
import sys
import json
import shutil
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "..", "..", "lib"))
from revotech import hostconfig as hc
from revotech import presetlogic as pl
from revotech import presetstore as ps

BARS = [u"RB6", u"RB9", u"DB10", u"DB12", u"DB16", u"DB20"]


class HostConfigTest(unittest.TestCase):
    VALUES = {"n": 8, "main": u"DB16", "tie": u"RB9", "cover": 25.0,
              "g": {"top1": (2, u"DB20"), "bot1": (3, u"DB16")},
              "replace": True, "ชื่อ": u"ไทย"}

    def test_roundtrip(self):
        txt = hc.dumps("column", self.VALUES)
        kind, v = hc.loads(txt)
        self.assertEqual(kind, "column")
        self.assertEqual(v["main"], u"DB16")
        self.assertEqual(v["g"]["top1"], [2, u"DB20"])   # tuple -> list
        self.assertEqual(v[u"ชื่อ"], u"ไทย")

    def test_loads_bad(self):
        for bad in (None, u"", u"not json", u"[]", u'{"kind":"x","values":{}}',
                    u'{"kind":"beam","values":5}'):
            self.assertIsNone(hc.loads(bad))

    def test_all_kinds_known(self):
        self.assertEqual(sorted(hc.KINDS), ["beam", "column", "footing", "slab", "stair"])
        for k in hc.KINDS:
            self.assertIn(k, hc.KIND_LABELS)

    def test_guid_differs_from_pktool(self):
        pktool = ["8C3E2A1F-4D6B-4A9C-B1E7-2F5A8D3C6B9E", "1B7F4E2A-9C3D-4F8B-A6E1-5D2C9A7B4F3E",
                  "5A2E8C1F-3B7D-4E9A-9C6F-1D8B4A2E7C3F", "B3272456-F82F-49D2-9E21-F2303A89B9BF",
                  "6E3B2E3A-6C1F-4B8E-9D3D-2A6F1B0C7E42"]
        mine = [hc.SCHEMA_GUID, ps.PROJECT_SCHEMA_GUID]
        self.assertEqual(len(set(mine)), 2)
        for g in mine:
            self.assertNotIn(g.upper(), pktool)

    def test_missing_bar_names(self):
        have = {u"DB16": 1, u"RB9": 1}
        self.assertEqual(hc.missing_bar_names(self.VALUES, BARS, have), [u"DB20"])
        self.assertEqual(hc.missing_bar_names({"a": u"xyz"}, BARS, have), [])

    def test_override_values(self):
        v, miss = hc.override_values({"values": {"same": True, "main": u"DB16"}},
                                     BARS, [u"DB16"])
        self.assertFalse(v["same"])
        self.assertEqual(miss, [])
        self.assertIsNotNone(hc.override_problem([], []))
        self.assertIn(u"DB20", hc.override_problem([1], [u"DB20"]))
        self.assertIsNone(hc.override_problem([1], []))


class PresetLogicTest(unittest.TestCase):
    def test_safe_name(self):
        self.assertEqual(pl.safe_name(u"เสา C1"), u"เสา C1")
        self.assertEqual(pl.safe_name(u'a/b\\c:d*e?f"g<h>i|j'), u"a_b_c_d_e_f_g_h_i_j")
        self.assertIsNone(pl.safe_name(u"   "))
        self.assertIsNone(pl.safe_name(u"..."))
        self.assertIsNone(pl.safe_name(None))
        self.assertEqual(pl.safe_name(u"CON"), u"_CON")
        self.assertEqual(pl.safe_name(u"nul.txt"), u"_nul.txt")
        self.assertEqual(pl.safe_name(u"x. "), u"x")
        self.assertEqual(len(pl.safe_name(u"ก" * 200)), pl.MAX_NAME)
        self.assertEqual(pl.safe_name(u"a   b"), u"a b")
        self.assertEqual(pl.safe_name(b"abc"), u"abc")

    def controls(self):
        return {"tb_lap": {"k": "text", "v": u"40"},
                "cmb_main": {"k": "combo", "v": u"DB16"},
                "cmb_n": {"k": "combo", "v": 6},
                "cb_same": {"k": "check", "v": False},
                "cb_replace": {"k": "check", "v": True}}

    def test_serialize_roundtrip(self):
        p = pl.make_preset("RebarColumn", self.controls())
        q = pl.loads(pl.dumps(p))
        self.assertEqual(q["controls"], json.loads(json.dumps(self.controls())))
        self.assertEqual(q["module"], "RebarColumn")
        self.assertIsNone(pl.loads(u"{"))
        self.assertIsNone(pl.loads(u'{"controls": {"a": {"k": "zzz", "v": 1}}}'))

    def test_plan_restore_full(self):
        cur = {"tb_lap": {"k": "text"},
               "cmb_main": {"k": "combo", "items": [u"DB12", u"DB16"]},
               "cmb_n": {"k": "combo", "items": [4, 6, 8]},
               "cb_same": {"k": "check"}, "cb_replace": {"k": "check"}}
        actions, skipped = pl.plan_restore(self.controls(), cur)
        self.assertEqual(skipped, [])
        d = dict((a[0], a) for a in actions)
        self.assertEqual(d["cmb_main"][2], 1)
        self.assertEqual(d["cmb_n"][2], 1)        # int 6 -> index 1
        self.assertEqual(d["tb_lap"][2], u"40")
        names = [a[0] for a in actions]
        self.assertLess(names.index("cb_same"), names.index("cb_replace"))  # False ก่อน True

    def test_plan_restore_skips_politely(self):
        cur = {"tb_lap": {"k": "check"},                       # ชนิดไม่ตรง
               "cmb_main": {"k": "combo", "items": [u"DB12"]},  # ไม่มี DB16
               "cmb_n": {"k": "combo", "items": [4, 6]}}        # cb_* หายไป
        actions, skipped = pl.plan_restore(self.controls(), cur)
        self.assertEqual([a[0] for a in actions], ["cmb_n"])
        self.assertEqual(len(skipped), 4)
        self.assertTrue(any(u"DB16" in s for s in skipped))
        msg = pl.skipped_text(skipped, limit=2)
        self.assertIn(u"อีก 2 รายการ", msg)
        self.assertEqual(pl.skipped_text([]), u"")


class PresetStoreTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_local_crud(self):
        p = pl.make_preset("RebarColumn", {"tb": {"k": "text", "v": u"ไทย"}})
        self.assertEqual(ps.local_list("RebarColumn", self.root), [])
        path = ps.local_save("RebarColumn", u"เสา:C1/ชั้น", p, self.root)
        self.assertTrue(path.endswith(u"เสา_C1_ชั้น.json"))
        self.assertTrue(os.path.isfile(path))
        self.assertEqual(ps.local_list("RebarColumn", self.root), [u"เสา_C1_ชั้น"])
        self.assertEqual(ps.local_list("RebarBeam", self.root), [])
        q = ps.local_load("RebarColumn", u"เสา:C1/ชั้น", self.root)
        self.assertEqual(q["controls"]["tb"]["v"], u"ไทย")
        self.assertIsNone(ps.local_load("RebarColumn", u"ไม่มี", self.root))
        self.assertTrue(ps.local_delete("RebarColumn", u"เสา_C1_ชั้น", self.root))
        self.assertFalse(ps.local_delete("RebarColumn", u"เสา_C1_ชั้น", self.root))
        self.assertEqual(ps.local_list("RebarColumn", self.root), [])

    def test_local_bad_name_and_file(self):
        with self.assertRaises(ValueError):
            ps.local_save("RebarColumn", u"   ", {}, self.root)
        d = os.path.join(self.root, "RebarColumn")
        os.makedirs(d)
        with open(os.path.join(d, "bad.json"), "w") as f:
            f.write("{oops")
        self.assertIsNone(ps.local_load("RebarColumn", "bad", self.root))

    def test_module_name_cannot_escape_root(self):
        p = ps.local_save("../evil", u"x", pl.make_preset("m", {}), self.root)
        self.assertTrue(os.path.abspath(p).startswith(os.path.abspath(self.root)))

    def test_project_dict_logic(self):
        allp = {}
        p = pl.make_preset("RebarBeam", {"a": {"k": "check", "v": True}})
        ps.project_put(allp, "RebarBeam", u"คาน B1", p)
        txt = ps.project_dumps(allp)
        back = ps.project_loads(txt)
        self.assertEqual(ps.project_names(back, "RebarBeam"), [u"คาน B1"])
        self.assertEqual(ps.project_names(back, "RebarColumn"), [])
        self.assertTrue(ps.project_remove(back, "RebarBeam", u"คาน B1"))
        self.assertFalse(ps.project_remove(back, "RebarBeam", u"คาน B1"))
        self.assertEqual(back, {})
        self.assertEqual(ps.project_loads(u"{bad"), {})
        self.assertEqual(ps.project_loads(u""), {})
        junk = json.dumps({"m": {"ok": p, "bad": {"controls": 3}}, "x": 5})
        self.assertEqual(sorted(ps.project_loads(junk)["m"]), ["ok"])


if __name__ == "__main__":
    unittest.main()
