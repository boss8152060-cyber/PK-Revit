# -*- coding: utf-8 -*-
"""ค่ามาตรฐานเหล็กเสริม + helper สร้าง Rebar ที่โมดูลเหล็กทุกตัวใช้ร่วมกัน

ค่าตั้งต้นด้านล่างอ้างจากที่เห็นในคลิป ("ขางอ 90° = 12db", มาตรฐาน มยผ. 1103-64)
และค่าทั่วไปของตะขอปลอก 135° — **ต้องให้วิศวกร/ผู้ใช้ยืนยัน** ก่อนใช้งานจริง
ทุกค่าปรับได้จากฟอร์มของแต่ละโมดูล
"""

import re
import math
from pyrevit import DB
from Autodesk.Revit.DB.Structure import (
    Rebar, RebarStyle, RebarBarType, RebarHookType, RebarHookOrientation)

from revotech.units import mm_to_ft
from revotech.rvt import ename

# ชื่อ bar type ที่ฟอร์มในคลิปให้เลือก (ต้องมี RebarBarType ชื่อเดียวกันในโปรเจกต์)
BAR_NAMES = [u"RB6", u"RB9", u"DB10", u"DB12", u"DB16", u"DB20",
             u"DB25", u"DB28", u"DB32"]
MAIN_BAR_NAMES = [n for n in BAR_NAMES if n.startswith(u"DB")]
TIE_BAR_NAMES = [u"RB6", u"RB9", u"DB10", u"DB12"]

# --- ค่าตั้งต้น (ยืนยันก่อนใช้จริง) ---
HOOK90_EXT_D = 12.0        # ปลายงอ 90° = 12 d (เห็นในคลิป: "12db")
HOOK135_EXT_D = 6.0        # ปลายปลอก 135° = 6 d
HOOK135_MIN_MM = 75.0      # และไม่น้อยกว่า 75 มม.
DEFAULT_COVER_MM = 25.0    # ระยะหุ้ม (คลิปแสดง 0.02–0.025 ม.)
LAP_D = 40.0               # ระยะทาบ ในหน่วย d — ค่าสมมติ รอยืนยัน


def bar_dia_mm(name):
    """เส้นผ่านศูนย์กลางจากชื่อ เช่น DB12 -> 12.0, RB9 -> 9.0"""
    m = re.search(r"(\d+)", name or u"")
    return float(m.group(1)) if m else 0.0


def hook135_ext_mm(dia_mm):
    return max(HOOK135_EXT_D * dia_mm, HOOK135_MIN_MM)


def bar_types(doc):
    """{ชื่อ: RebarBarType} ในโปรเจกต์"""
    d = {}
    for t in DB.FilteredElementCollector(doc).OfClass(RebarBarType):
        d[ename(t)] = t
    return d


def names_in_project(types_dict):
    """ชื่อ Rebar Bar Type ทั้งหมดที่มีในโปรเจกต์ เรียงตามขนาด (ตัวเลขในชื่อ) แล้วตามชื่อ
    — ให้ dropdown แสดงของจริงในโปรเจกต์ ไม่จำกัดที่ชื่อ DB/RB ตายตัว"""
    return sorted(types_dict.keys(), key=lambda n: (bar_dia_mm(n), n))


def hook_type(doc, angle_deg, ext_mult):
    """หา/สร้าง RebarHookType มุม angle_deg (ปลายเหยียด = ext_mult × d)
    คืน (hook, สร้างใหม่ไหม)"""
    want = math.radians(angle_deg)
    for h in DB.FilteredElementCollector(doc).OfClass(RebarHookType):
        try:
            if abs(h.HookAngle - want) < 1e-3 or \
               abs(h.HookAngle - math.degrees(want)) < 0.5:
                return h, False
        except Exception:
            continue
    h = RebarHookType.Create(doc, want, float(ext_mult))
    try:
        h.Name = u"PKRevit_Hook{}_{}d".format(int(angle_deg), ext_mult)
    except Exception:
        pass
    return h, True


def line(p0, p1):
    return DB.Line.CreateBound(p0, p1)


def create(doc, host, bar_type, curves, normal, style=RebarStyle.Standard,
           hook_start=None, hook_end=None):
    """สร้างเหล็กจากเส้น curves ในระนาบที่ตั้งฉาก normal — คืน Rebar หรือ None"""
    from System.Collections.Generic import List
    crvs = List[DB.Curve]()
    for c in curves:
        crvs.Add(c)
    try:
        return Rebar.CreateFromCurves(
            doc, style, bar_type, hook_start, hook_end, host, normal, crvs,
            RebarHookOrientation.Left, RebarHookOrientation.Left, True, True)
    except Exception:
        return None


def layout_max_spacing(rb, spacing_mm, length_mm):
    """เรียงเหล็กซ้ำตามแนว normal ระยะห่างไม่เกิน spacing_mm ตลอดความยาว length_mm"""
    try:
        acc = rb.GetShapeDrivenAccessor()
        acc.SetLayoutAsMaximumSpacing(mm_to_ft(spacing_mm), mm_to_ft(length_mm),
                                      True, True, True)
        return True
    except Exception:
        return False


def layout_fixed_number(rb, count, array_len_mm):
    """เรียงเหล็กจำนวน count เส้นกระจายตลอด array_len_mm"""
    try:
        acc = rb.GetShapeDrivenAccessor()
        acc.SetLayoutAsFixedNumber(int(count), mm_to_ft(array_len_mm),
                                   True, True, True)
        return True
    except Exception:
        return False
