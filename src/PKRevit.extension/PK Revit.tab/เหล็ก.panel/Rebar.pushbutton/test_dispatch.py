# -*- coding: utf-8 -*-
"""unit test ตรรกะปุ่มรวม Rebar/Roof (รันนอก Revit): python test_dispatch.py

ครอบคลุม: จัดชนิด/จัดกลุ่ม, หาสคริปต์ทั้ง script.py และ <ชื่อ>.py, รันด้วย execfile
(__file__, import ไฟล์ข้างๆ, SystemExit) และตรวจโครงโฟลเดอร์จริงของ ribbon
"""
import io
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
EXT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, os.path.join(EXT, "lib"))
from revotech import dispatch as dp  # noqa: E402
from revotech import hostconfig  # noqa: E402

TAB = os.path.join(EXT, "PK Revit.tab")
MODULES = os.path.join(HERE, "modules")
ROOF = os.path.join(TAB, u"หลังคา.panel", "Roof.pushbutton")
PANEL = os.path.join(TAB, u"เหล็ก.panel")
COL_A = os.path.join(PANEL, "ManageA.stack3")
COL_B = os.path.join(PANEL, "ManageB.stack3")
OUTPUT = os.path.join(TAB, u"ผลลัพธ์.panel")


def _write(path, text):
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


class Classify(unittest.TestCase):
    def test_categories(self):
        self.assertEqual(dp.classify("OST_StructuralColumns"), "column")
        self.assertEqual(dp.classify("OST_StructuralFoundation"), "footing")
        self.assertEqual(dp.classify("OST_Floors"), "slab")
        self.assertEqual(dp.classify("OST_Stairs"), "stair")

    def test_framing_only_beam(self):
        self.assertEqual(dp.classify("OST_StructuralFraming", True), "beam")
        self.assertIsNone(dp.classify("OST_StructuralFraming", False))

    def test_unsupported(self):
        self.assertIsNone(dp.classify("OST_Walls"))
        self.assertIsNone(dp.classify(None))

    def test_group_order_and_skip(self):
        pairs = [("slab", 1), ("column", 2), (None, 3), ("slab", 4),
                 ("stair", 5), ("beam", 6)]
        self.assertEqual(dp.group_by_kind(pairs),
                         [("column", [2]), ("beam", [6]), ("slab", [1, 4]),
                          ("stair", [5])])

    def test_group_empty(self):
        self.assertEqual(dp.group_by_kind([]), [])
        self.assertEqual(dp.group_by_kind([(None, 1)]), [])

    def test_plan_text(self):
        t = dp.plan_text([("column", [1, 2]), ("slab", [3])])
        self.assertIn(u"เสา 2 ตัว", t)
        self.assertIn(u"พื้น 1 ตัว", t)
        self.assertIn(u"เสา → พื้น", t)


class FindScript(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def _make(self, folder, fname):
        d = os.path.join(self.tmp, folder)
        os.makedirs(d)
        p = os.path.join(d, fname)
        _write(p, u"x = 1\n")
        return p

    def test_script_py(self):
        p = self._make(u"RebarColumn.pushbutton", "script.py")
        self.assertEqual(dp.find_script(self.tmp, u"RebarColumn.pushbutton"), p)

    def test_renamed(self):
        p = self._make(u"RebarSlab.pushbutton", "RebarSlab.py")
        self.assertEqual(dp.find_script(self.tmp, u"RebarSlab.pushbutton"), p)

    def test_script_py_wins(self):
        d = os.path.join(self.tmp, u"RebarBeam.pushbutton")
        os.makedirs(d)
        for n in ("script.py", "RebarBeam.py"):
            _write(os.path.join(d, n), u"")
        self.assertTrue(dp.find_script(self.tmp, u"RebarBeam.pushbutton")
                        .endswith("script.py"))

    def test_missing(self):
        os.makedirs(os.path.join(self.tmp, u"RebarStair.pushbutton"))
        self.assertIsNone(dp.find_script(self.tmp, u"RebarStair.pushbutton"))
        self.assertIsNone(dp.find_script(self.tmp, u"Nope.pushbutton"))

    def test_find_in_dirs_order(self):
        a = os.path.join(self.tmp, "a")
        b = os.path.join(self.tmp, "b")
        for d in (a, b):
            os.makedirs(os.path.join(d, u"X.pushbutton"))
            _write(os.path.join(d, u"X.pushbutton", "script.py"), u"")
        self.assertEqual(dp.find_in_dirs([a, b], u"X.pushbutton"),
                         os.path.join(a, u"X.pushbutton", "script.py"))
        self.assertEqual(dp.find_in_dirs([os.path.join(self.tmp, "z"), b],
                                         u"X.pushbutton"),
                         os.path.join(b, u"X.pushbutton", "script.py"))


class RunScript(unittest.TestCase):
    """จำลองโมดูลแบบ footing: import ไฟล์ข้างๆ, อ่าน body ผ่าน __file__, จบด้วย SystemExit"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.saved_path = list(sys.path)

    def tearDown(self):
        sys.path[:] = self.saved_path
        sys.modules.pop("pk_sibling_calc", None)
        shutil.rmtree(self.tmp)

    def test_sibling_import_file_and_exit(self):
        _write(os.path.join(self.tmp, "pk_sibling_calc.py"), u"VALUE = 42\n")
        _write(os.path.join(self.tmp, "body.xaml"), u"<x/>")
        script = os.path.join(self.tmp, "Mod.py")     # ชื่อแบบเปลี่ยนชื่อแล้ว
        _write(script, u"\n".join([
            u"import os, sys",
            u"import pk_sibling_calc as c",
            u"body = os.path.join(os.path.dirname(__file__), 'body.xaml')",
            u"try:",
            u"    CONFIG_OVERRIDE",
            u"    has_ovr = True",
            u"except NameError:",
            u"    has_ovr = False",
            u"SINK['ok'] = os.path.isfile(body) and c.VALUE == 42 and __name__ == '__main__'",
            u"SINK['ovr'] = has_ovr",
            u"sys.exit()",
            u""]))
        sink = {}
        with self.assertRaises(SystemExit):
            dp.run_script(script, {"SINK": sink})
        self.assertTrue(sink["ok"])
        self.assertFalse(sink["ovr"])   # dispatcher ไม่ส่ง CONFIG_OVERRIDE → ฟอร์มปกติ
        self.assertIn(self.tmp, sys.path)


class RealLayout(unittest.TestCase):
    def test_every_kind_has_module(self):
        for kind in dp.KIND_ORDER:
            folder = dp.KIND_FOLDERS[kind]
            self.assertIsNotNone(dp.find_script(MODULES, folder), kind)
            self.assertTrue(os.path.isfile(os.path.join(MODULES, folder, "body.xaml")))

    def test_matches_hostconfig(self):
        self.assertEqual(dp.KIND_FOLDERS, hostconfig.KINDS)
        self.assertEqual(dp.KIND_LABELS, hostconfig.KIND_LABELS)

    def test_propagate_finds_modules(self):
        # สูตรเดียวกับ PropagateRebar._module_path
        pb = os.path.join(COL_A, "PropagateRebar.pushbutton")
        here = os.path.dirname(pb)
        panel = os.path.dirname(here)
        for kind in dp.KIND_ORDER:
            p = dp.find_in_dirs([os.path.join(panel, "Rebar.pushbutton", "modules"),
                                 here], hostconfig.KINDS[kind])
            self.assertIsNotNone(p, kind)

    def test_roof_modules_and_engines(self):
        mods = os.path.join(ROOF, "modules")
        master = dp.find_script(mods, u"RoofMaster.pushbutton")
        self.assertIsNotNone(master)
        self.assertIsNotNone(dp.find_script(mods, u"RoofCover.pushbutton"))
        self.assertTrue(os.path.isfile(os.path.join(os.path.dirname(master), "ui.xaml")))
        # สูตรเดียวกับ step_path ของ Roof Master: HERE/engines/<ปุ่ม>/script.py
        engines = os.path.join(os.path.dirname(master), "engines")
        for eng in ("HipRidgeGen", "PurlinGen", "ValleyGen", "RafterGen", "DangGen"):
            self.assertIsNotNone(dp.find_script(engines, eng + ".pushbutton"), eng)

    def test_ribbon_structure(self):
        def has(*parts):
            return os.path.isdir(os.path.join(TAB, *parts))
        self.assertTrue(has(u"เหล็ก.panel", "Rebar.pushbutton"))
        self.assertTrue(has(u"หลังคา.panel", "Roof.pushbutton"))
        self.assertTrue(has(u"ผลลัพธ์.panel", "BarCut.pushbutton"))
        self.assertTrue(has(u"ผลลัพธ์.panel", "QtoTables.pushbutton"))
        self.assertFalse(has(u"ผลลัพธ์.panel", u"ถอดปริมาณ.pulldown"))
        self.assertFalse(has(u"เหล็ก.panel", u"จัดการเหล็ก.pulldown"))
        self.assertTrue(has(u"ตั้งค่า.panel", "License.pushbutton"))
        self.assertFalse(has("PK Revit.panel"))
        def btns(d):
            return sorted(n for n in os.listdir(d) if n.endswith(".pushbutton"))
        self.assertEqual(btns(COL_A), sorted([
            "Select.pushbutton", "DeleteRebar.pushbutton", "PropagateRebar.pushbutton"]))
        self.assertEqual(btns(COL_B), sorted([
            "ObscuredRebar.pushbutton", "RebarCollision.pushbutton",
            "ColorByParameter.pushbutton"]))
        # ชื่อใน layout ต้องมีโฟลเดอร์จริง
        for panel in (PANEL, OUTPUT):
            with io.open(os.path.join(panel, "bundle.yaml"), encoding="utf-8") as f:
                names = [l.strip()[2:].strip() for l in f if l.strip().startswith("- ")]
            for n in names:
                self.assertTrue(any(e.rsplit(".", 1)[0] == n for e in os.listdir(panel)), n)

    def test_icons_96(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("no PIL")
        dirs = [HERE, ROOF] + [os.path.join(c, b) for c in (COL_A, COL_B) for b in os.listdir(c)
                               if b.endswith(".pushbutton")]
        dirs += [os.path.join(OUTPUT, b) for b in ("BarCut.pushbutton", "QtoTables.pushbutton")]
        for d in dirs:
            for n in ("icon.png", "icon.dark.png"):
                self.assertEqual(Image.open(os.path.join(d, n)).size, (96, 96))

    def test_no_old_brand_in_new_ui(self):
        for d in (HERE, ROOF):
            for n in ("script.py", "body.xaml", "bundle.yaml"):
                with io.open(os.path.join(d, n), encoding="utf-8") as f:
                    text = f.read()
                # ชื่อแพ็กเกจไลบรารี (from revotech ... / lib/revotech) ใช้ได้ — ห้ามอยู่ในข้อความ UI
                for ok in ("from revotech", "lib/revotech", "import revotech"):
                    text = text.replace(ok, "")
                self.assertNotIn("REVOTECH", text.upper())


if __name__ == "__main__":
    unittest.main()
