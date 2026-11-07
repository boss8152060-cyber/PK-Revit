# -*- coding: utf-8 -*-
"""เดโมใน IronPython (เรียกจาก run_demo.ps1): สร้าง scene ทุกชนิด render เป็น PNG
ฟังก์ชันคำนวณของฟอร์มเหล็ก (footing_calc/slab_calc/stair_calc) หาจากโฟลเดอร์ pushbutton
ด้วยการค้นชื่อไฟล์ จึงไม่พังเมื่อมีการย้ายโฟลเดอร์โมดูล"""
import os
import sys
from revotech import scene3d
from revotech.preview3d import Preview3D, render_png


def load_calc(name):
    for root, dirs, files in os.walk(EXT_ROOT):
        if name + ".py" in files:
            m = type(sys)(name)
            m.__file__ = os.path.join(root, name + ".py")
            execfile(m.__file__, m.__dict__)
            return m
    raise Exception("ไม่พบ " + name + ".py")


footing_calc = load_calc("footing_calc")
slab_calc = load_calc("slab_calc")
stair_calc = load_calc("stair_calc")
dia_of = stair_calc.dia_from_name


def out(name):
    return os.path.join(OUT_DIR, name + ".png")


def snap(scene, name, w=460, h=420):
    pv = Preview3D()
    render_png(pv, out(name), w, h) if False else None
    pv.update(scene, keep_view=False)
    render_png(pv, out(name), w, h)
    print("%-10s bars=%-4d -> %s" % (name, scene.bar_count(), out(name)))


# 1) เสา 8 เส้น
snap(scene3d.column_scene(400, 400, 3000, 8, 16.0, 9.0), "column")

# 2) คาน: บน 3DB16, ล่าง 3+2 DB20, เสริมบนที่ปลาย, เหล็กข้าง 2, ปลอก
spec = {"top": [(3, 16.0, "DB16")], "bot": [(3, 20.0, "DB20"), (2, 20.0, "DB20")],
        "xtop": (2, 16.0, "DB16", "ends", 4), "side": (2, 12.0, "DB12"),
        "d_tie": 9.0, "cover": 30.0}
snap(scene3d.beam_scene(5000, 250, 500, spec), "beam")

# 3) ฐานรากสี่เหลี่ยม + เหล็กรัดรอบ + ตอม่อ
snap(scene3d.footing_scene(1800, 1800, 600, (12.0, 7), (12.0, 7), cover=75.0,
                           hook=scene3d.HOOK_12D, ring=(9.0, 4, 120.0),
                           column=(300, 300, 700)), "footing")

# 3b) ฐานรากสามเหลี่ยม (ผลจาก footing_calc.plan_mat จริง)
s = 1800.0
tri = [(-s / 2, -s * 0.2887), (s / 2, -s * 0.2887), (0.0, s * 0.5774)]
bars = footing_calc.plan_mat(tri, "tri", {0: ("DB12", 5), 60: ("DB12", 5), 120: ("DB12", 5)},
                             75.0, 0.0, 600.0, dia_of)
snap(scene3d.footing_scene_from_bars(tri, 600.0, bars, title=u"ฐานรากสามเหลี่ยม"), "footing_tri")

# 4) พื้น 2 ชั้น 2 ทิศ (สี่เหลี่ยม) และพื้นตัว L มีช่องเปิด (plan_layers จริง)
snap(scene3d.slab_scene(4000, 3000, 150, {"TX": (12.0, 200.0), "TY": (12.0, 200.0),
                                          "BX": (12.0, 150.0), "BY": (12.0, 150.0)},
                        cover=20.0), "slab")
outer = [(0, 0), (5000, 0), (5000, 2000), (2500, 2000), (2500, 4000), (0, 4000)]
hole = [(600, 600), (1400, 600), (1400, 1400), (600, 1400)]
lay = {"TX": ("DB12", 250.0), "BY": ("DB12", 250.0), "BX": ("DB12", 200.0)}
sb, _notes = slab_calc.plan_layers(slab_calc.clean_polygon(outer), [slab_calc.clean_polygon(hole)],
                                   150.0, 20.0, lay, dia_of)
snap(scene3d.slab_scene_from_bars(outer, [hole], 150.0, sb, title=u"พื้นตัว L"), "slab_L")

# 5) บันได (stair_calc.plan_run จริง)
geo = stair_calc.Geo(1800.0, 12, 11, 250.0)
G = {"waist": {"on": True, "size": "DB12", "sp": 150.0},
     "ext": {"on": True, "size": "DB12", "sp": 200.0},
     "tread": {"on": True, "size": "RB9", "sp": 200.0},
     "crack": {"on": True, "size": "RB9", "sp": 200.0}}
v = {"groups": G, "cover": 25.0, "tw": 150.0, "tl": 150.0, "anchor": 300.0,
     "ext_len": 400.0, "ext_run": 600.0, "ext_lower": True}
sets = stair_calc.plan_run(geo, 1200.0, v, dia_of)
snap(scene3d.stair_scene(geo, 1200.0, sets, 150.0), "stair")
