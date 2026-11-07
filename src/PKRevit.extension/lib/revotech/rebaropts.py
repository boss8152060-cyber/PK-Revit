# -*- coding: utf-8 -*-
"""ช่อง "รูปเหล็ก / ตะขอ / ต่อทาบ" ที่ฟอร์มเหล็กใช้ร่วมกัน (เสา/คาน/ฐานราก)

control ที่ต้องมีใน body.xaml (ชื่อตายตัว เพื่อให้ระบบ Preset จำค่าได้อัตโนมัติ):
  cmb_shape_main, cmb_shape_tie            — Rebar Shape จากโปรเจกต์ (ตัวแรก = อัตโนมัติ)
  cmb_hk_a, tb_hk_a, cmb_hk_b, tb_hk_b     — ตะขอปลายซ้าย/ขวา + ตัวคูณ × d (ว่าง = ค่ามาตรฐานของมุม)
  cmb_stagger                              — สลับจุดต่อ (เฉพาะโมดูลที่ประกาศ)
ไม่ import Revit — ใช้ใน demo นอก Revit ได้
"""
from revotech import hookcalc as hc
from revotech import ui

AUTO_SHAPE = u"อัตโนมัติ (เส้นตรง + ตะขอตามที่เลือก)"


def fill(win, main_names=(), tie_names=(), hooks=True, stagger=False, tie_shape=True):
    """เติมรายการ dropdown ตามชุดที่ฟอร์มนั้นมี"""
    ui.combo_fill(win.cmb_shape_main, [AUTO_SHAPE] + sorted(main_names), AUTO_SHAPE)
    if tie_shape:
        ui.combo_fill(win.cmb_shape_tie, [AUTO_SHAPE] + sorted(tie_names), AUTO_SHAPE)
    if hooks:
        ui.combo_fill(win.cmb_hk_a, hc.HOOK_ITEMS, hc.HOOK_KEEP)
        ui.combo_fill(win.cmb_hk_b, hc.HOOK_ITEMS, hc.HOOK_KEEP)
    if stagger:
        ui.combo_fill(win.cmb_stagger, hc.STAGGER_ITEMS, hc.STAGGER_OFF)


def read(win, hooks=True, stagger=False, tie_shape=True):
    """ค่าจากฟอร์ม → dict ที่เก็บ JSON ได้ (ใช้กับ hostconfig/Propagate)"""
    v = {"shape_main": win.cmb_shape_main.SelectedItem or AUTO_SHAPE}
    if tie_shape:
        v["shape_tie"] = win.cmb_shape_tie.SelectedItem or AUTO_SHAPE
    if hooks:
        for k in ("a", "b"):
            v["hk_" + k] = getattr(win, "cmb_hk_" + k).SelectedItem or hc.HOOK_KEEP
            txt = (getattr(win, "tb_hk_" + k).Text or u"").strip()
            v["hk_%s_mult" % k] = ui.num(txt, 0) if txt else None
    if stagger:
        v["stagger"] = win.cmb_stagger.SelectedItem or hc.STAGGER_OFF
    return v


def hook_spec(v, end):
    """'keep' | 'none' | (มุม, ตัวคูณ×d) ของปลาย end='a'|'b' จากค่าฟอร์ม (ไม่มีคีย์ = keep)"""
    p = hc.parse_hook(v.get("hk_" + end))
    if p in ("keep", "none"):
        return p
    m = v.get("hk_%s_mult" % end)
    if not m or m <= 0:
        m = hc.default_mult(p)
    return (p, float(m))


def shape_choice(v, key, shapes):
    """RebarShape ที่เลือก หรือ None = อัตโนมัติ (ไม่มีคีย์/ชื่อไม่พบในโปรเจกต์ → None)
    shapes = {ชื่อ: RebarShape}"""
    name = v.get(key)
    if not name or name == AUTO_SHAPE:
        return None
    return shapes.get(name)


def missing_shape(v, key, shapes):
    """ชื่อ shape ที่ค่าที่จำไว้ใช้แต่โปรเจกต์ไม่มี (ไว้แจ้งใน log) หรือ None"""
    name = v.get(key)
    if name and name != AUTO_SHAPE and name not in shapes:
        return name
    return None


def stagger_mode(v):
    return v.get("stagger") or hc.STAGGER_OFF
