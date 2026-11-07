# -*- coding: utf-8 -*-
"""Render ฟอร์มเหล็กทั้ง 5 (เสา/คาน/ฐานราก/พื้น/บันได) พร้อม 3D preview ด้วย WPF จริง

โหลด "คลาสฟอร์มจริง" จาก script.py ของแต่ละโมดูล (ช่วงระหว่างหัว '# --- form' ถึง '# --- main')
โดยจำลอง pyrevit/Revit แบบจิ๋ว — จึงทดสอบการต่อ preview, การอ่านค่าฟอร์ม, layout ได้โดยไม่ต้องมี Revit
ผล: out/form_<module>.png (+ _gen = อ่านรูปทรงไม่ได้, _multi = เลือกหลายชิ้น, _empty = ยังไม่เลือกขนาดเหล็ก)
ใช้: powershell -STA -File tools\\preview_demo\\run_demo.ps1 -Script demo_forms.py
ไม่ได้ทดสอบใน Revit
"""
import os
import sys
import re
import clr
clr.AddReference('PresentationCore')
clr.AddReference('PresentationFramework')
clr.AddReference('WindowsBase')
import System
from System.Windows import Size, Rect
from System.Windows.Markup import XamlReader
from System.Windows.Media.Imaging import RenderTargetBitmap, PngBitmapEncoder, BitmapFrame


class _WPFWindow(object):
    def __init__(self, xaml, literal_string=False):
        self.__dict__["_w"] = XamlReader.Parse(xaml)

    def __getattr__(self, name):
        n = self.__dict__["_w"].FindName(name)
        if n is not None:
            return n
        return getattr(self.__dict__["_w"], name)

    def __setattr__(self, name, value):
        self.__dict__[name] = value


def _mod(name, **kw):
    m = type(sys)(name)
    for k, v in kw.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


class _Stub(object):
    def __getattr__(self, n):
        return lambda *a, **k: ([] if n in ("local_list", "project_names") else {})


forms = _Stub()
forms.WPFWindow = _WPFWindow
_mod("pyrevit", forms=forms, DB=_Stub())
import revotech
revotech.presetlogic = _mod("revotech.presetlogic", safe_name=lambda t: t or None)
revotech.presetstore = _mod("revotech.presetstore", local_list=lambda m: [],
                            project_names=lambda a, m: [], project_read=lambda d: {})
from revotech import ui, scene3d, formpreview, rebaropts, hookcalc

# --- rebar แบบจิ๋ว (rebar.py จริง import Autodesk)
rb = type(sys)("rb")
rb.BAR_NAMES = [u"RB6", u"RB9", u"DB10", u"DB12", u"DB16", u"DB20", u"DB25", u"DB28", u"DB32"]
rb.MAIN_BAR_NAMES = [n for n in rb.BAR_NAMES if n.startswith(u"DB")]
rb.TIE_BAR_NAMES = [u"RB6", u"RB9", u"DB10", u"DB12"]
rb.LAP_D = 40.0
rb.HOOK90_EXT_D = 12.0
rb.names_in_project = lambda bt: [n for n in rb.BAR_NAMES if n in bt]
rb.bar_dia_mm = formpreview.dia_mm

MODS = {}
for root, dirs, files in os.walk(EXT_ROOT):
    b = os.path.basename(root)
    if b.startswith("Reb") and b.endswith(".pushbutton") and "script.py" in files and \
            os.path.basename(os.path.dirname(root)) == "modules":
        MODS[b[:-len(".pushbutton")]] = root
        sys.path.insert(0, root)
import footing_calc as fc
import slab_calc as sc_slab
import stair_calc as sc_stair

BAR_TYPES = dict((n, None) for n in rb.BAR_NAMES)


def load_form_class(module, cls, extra):
    """exec ส่วน form ของ script.py จริง -> คลาสฟอร์ม"""
    path = os.path.join(MODS[module], "script.py")
    src = System.IO.File.ReadAllText(path, System.Text.Encoding.UTF8)
    a = src.index("# ---------------------------------------------------------------- form")
    b = src.index("# ---------------------------------------------------------------- main")
    ns = {"__file__": path, "os": os, "rb": rb, "ui": ui, "fpv": formpreview, "math": __import__("math"),
          "ro": rebaropts, "hk": hookcalc, "fc": fc, "sc": (sc_slab if module == "RebarSlab" else sc_stair)}
    ns.update(extra)
    exec(compile(src[a:b], path, "exec"), ns)
    return ns[cls]


def shot(win):
    root = win._w.Content
    root.Measure(Size(win._w.Width, 3000))
    root.Arrange(Rect(0, 0, root.DesiredSize.Width, root.DesiredSize.Height))
    root.UpdateLayout()
    return root, int(root.DesiredSize.Width), int(root.DesiredSize.Height)


def save(win, name):
    root, w, h = shot(win)
    root.UpdateLayout()
    rtb = RenderTargetBitmap(w, h, 96.0, 96.0, System.Windows.Media.PixelFormats.Pbgra32)
    rtb.Render(root)
    enc = PngBitmapEncoder()
    enc.Frames.Add(BitmapFrame.Create(rtb))
    p = os.path.join(OUT_DIR, name + ".png")
    fs = System.IO.File.Create(p)
    enc.Save(fs)
    fs.Close()
    print("%s %dx%d bars=%d notes=%d" % (name, w, h, win.preview.scene.bar_count(),
                                         len(win.preview.scene.notes)))


def finalize(win):
    """ให้ preview วาดตามขนาดกรอบจริง (จัดกรอบกล้องใหม่หลัง layout) แล้วคืน"""
    shot(win)
    win.preview.reset_view()
    shot(win)
    win.preview.reset_view()


def sel(cmb, item):
    for i in range(cmb.Items.Count):
        if cmb.Items[i] == item:
            cmb.SelectedIndex = i
            return
    raise Exception("no item " + item)


# ------------------------------------------------------------ เสา
Col = load_form_class("RebarColumn", "ColumnForm", {})
w = Col(1, BAR_TYPES, (400.0, 400.0, 3000.0))
finalize(w)
save(w, "form_column")
w.cmb_n.SelectedIndex = 4                        # 12 เส้น (ตรงทาง SelectionChanged)
w.tb_sp_end.Text = "0.075"
sel(w.cmb_main, u"DB20")
w.preview.update(w._scene(), keep_view=True)     # แทน timer (ไม่มี dispatcher วิ่ง)
assert w.preview.scene.groups[0].polys.__len__() == 12, "form->scene ไม่ตามค่าที่กรอก"
finalize(w)
save(w, "form_column_edited")
# ตะขอ + สลับจุดต่อ + รายการ Rebar Shape จากโปรเจกต์ (ตัวอย่าง)
w = Col(1, BAR_TYPES, (400.0, 400.0, 3000.0), ([u"M_00", u"M_L"], [u"M_T1", u"M_T2"]))
sel(w.cmb_hk_a, u"90°")
sel(w.cmb_hk_b, u"135°")
w.tb_hk_b.Text = "8"
sel(w.cmb_stagger, hookcalc.STAGGER_ALT)
w.preview.update(w._scene(), keep_view=False)
v = w.collect()
assert v["hk_a"] == u"90°" and v["hk_b_mult"] == 8.0 and v["shape_main"] == rebaropts.AUTO_SHAPE, v
assert rebaropts.hook_spec(v, "a") == (90, 12.0) and rebaropts.hook_spec(v, "b") == (135, 8.0)
assert [len(p) for p in w.preview.scene.groups[0].polys][0] == 4, "preview ไม่แสดงตะขอ"
sel(w.cmb_shape_main, u"M_L")
assert w.collect()["shape_main"] == u"M_L"
sel(w.cmb_shape_main, rebaropts.AUTO_SHAPE)
finalize(w)
save(w, "form_column_hooks")
w = Col(3, BAR_TYPES, None)
finalize(w)
save(w, "form_column_gen_multi")                 # อ่านรูปทรงไม่ได้ + เลือก 3 ต้น
w = Col(1, {}, (500.0, 350.0, 3600.0))
finalize(w)
save(w, "form_column_empty")                     # ไม่มี Bar Type ในโปรเจกต์ -> combo ยังเป็นรายการตัวอย่าง

# ------------------------------------------------------------ คาน
_POS = [u"ปลายทั้งสองข้าง", u"กลางช่วง"]
_HOOK = [u"12d (มยผ. 1103-64)", u"กำหนดเอง (× d)"]
Beam = load_form_class("RebarBeam", "BeamForm", {"POS_ITEMS": _POS, "HOOK_ITEMS": _HOOK,
                                                 "POS_MODE": {_POS[0]: 'ends', _POS[1]: 'mid'}})
w = Beam(1, BAR_TYPES, (6000.0, 300.0, 600.0))
w.cmb_top1_n.SelectedIndex = 3
w.cmb_xtop_n.SelectedIndex = 2
w.cmb_side_n.SelectedIndex = 2
w.preview.update(w._scene(), keep_view=False)
finalize(w)
save(w, "form_beam")
w = Beam(1, BAR_TYPES, (6000.0, 300.0, 600.0), ([u"M_00"], [u"M_T1"]))
sel(w.cmb_hk_a, u"45°")
sel(w.cmb_hk_b, hookcalc.HOOK_NONE)
w.cmb_top1_n.SelectedIndex = 3
w.preview.update(w._scene(), keep_view=False)
assert w.collect() is not None
finalize(w)
save(w, "form_beam_hooks")
w = Beam(4, BAR_TYPES, None)
finalize(w)
save(w, "form_beam_gen_multi")

# ------------------------------------------------------------ ฐานราก
Foot = load_form_class("RebarFooting", "FootingForm", {})
rect = {"poly": [(-1000.0, -750.0), (1000.0, -750.0), (1000.0, 750.0), (-1000.0, 750.0)],
        "kind": "rect", "height": 500.0}
tri = {"poly": [(0.0, 0.0), (2400.0, 0.0), (1200.0, 2078.0)], "kind": "tri", "height": 600.0}
w = Foot(1, 1, 0, 0, BAR_TYPES, rect)
finalize(w)
save(w, "form_footing_empty")                    # ยังไม่เลือกขนาด -> เฉพาะฐานราก
sel(w.cmb_long, u"DB16")
sel(w.cmb_short, u"DB16")
sel(w.cmb_ring, u"RB9")
w.cb_ring.IsChecked = True
w.rb_h1.IsChecked = True
w.preview.update(w._scene(), keep_view=False)
finalize(w)
save(w, "form_footing")
w = Foot(1, 1, 0, 0, BAR_TYPES, rect, ([u"M_00", u"M_L"], [u"M_T1"]))
sel(w.cmb_long, u"DB16"); sel(w.cmb_short, u"DB16"); w.rb_h1.IsChecked = True
sel(w.cmb_shape_main, u"M_L")
vv = w.collect()
assert vv is not None and vv["shape_main"] == u"M_L" and "hk_a" not in vv, vv
finalize(w)
save(w, "form_footing_shapes")
w = Foot(2, 0, 2, 0, BAR_TYPES, tri)
for c in (w.cmb_t0, w.cmb_t60, w.cmb_t120):
    sel(c, u"DB16")
w.rb_h3.IsChecked = True
w.preview.update(w._scene(), keep_view=False)
finalize(w)
save(w, "form_footing_tri_multi")

# ------------------------------------------------------------ พื้น
Slab = load_form_class("RebarSlab", "SlabForm", {})
shape = {"outer": [(0.0, 0.0), (5000.0, 0.0), (5000.0, 3500.0), (2500.0, 3500.0), (2500.0, 2000.0), (0.0, 2000.0)],
         "holes": [], "H": 150.0}
w = Slab(1, 0, BAR_TYPES, {}, shape)
for k in ("tx", "bx", "by"):
    sel(getattr(w, "cmb_" + k), u"DB12")
    getattr(w, "tb_" + k).Text = "0.2"
w.tb_cover.Text = "0.02"
w.preview.update(w._scene(), keep_view=False)
finalize(w)
save(w, "form_slab")
w = Slab(3, 1, BAR_TYPES, {}, {"error": u"พื้นเอียง/ผิวโค้ง ยังไม่รองรับ"})
w.preview.update(w._scene(), keep_view=False)
finalize(w)
save(w, "form_slab_gen_multi")

# ------------------------------------------------------------ บันได
Stair = load_form_class("RebarStair", "StairForm", {})
run = {"geo": sc_stair.Geo(3000.0, 17, 16, 250.0), "W": 1200.0}
w = Stair(u"บันไดที่เลือก: 1 ตัว", BAR_TYPES, [{"label": "x", "W": 1200.0}], 150.0, 150.0, run, 1, None)
for k in ("waist", "ext", "tread", "crack"):
    sel(getattr(w, "cmb_" + k), u"DB12")
    getattr(w, "cb_" + k).IsChecked = True
    getattr(w, "tb_%s_sp" % k).Text = "0.2"
w.preview.update(w._scene(), keep_view=False)
finalize(w)
save(w, "form_stair")
w = Stair(u"บันได", BAR_TYPES, [], 150.0, 150.0, None, 2, None)
finalize(w)
save(w, "form_stair_gen_multi")
print("DONE")
