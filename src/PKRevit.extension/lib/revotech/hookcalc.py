# -*- coding: utf-8 -*-
"""คำนวณตะขอ/ระยะทาบ/ความยาวตัดของเหล็ก — ตรรกะล้วน ไม่พึ่ง Revit ทดสอบนอก Revit ได้

หน่วย มม. ทั้งหมด ค่าตั้งต้นทุกตัว **รอวิศวกรยืนยัน** (ดู docs/accept-rebar-shapes-hooks.md)

ตะขอ = มุม (45/90/135/180°) + ช่วงตรงปลาย (ext = ตัวคูณ × d) ตรงกับ RebarHookType ของ Revit
ความยาวตะขอที่เพิ่มเข้าความยาวตัด = ส่วนโค้ง (มุม × รัศมีกึ่งกลางเหล็ก) + ช่วงตรงปลาย
เป็น "ค่าประมาณ" — ตัวเลขจริงขึ้นกับ Bend Diameter ของ Bar Type ในโปรเจกต์
BarCut ไม่ใช้ไฟล์นี้: อ่านความยาวจากเส้นกึ่งกลางที่ Revit คืนมา (รวมตะขอแล้ว)
"""
from __future__ import division
import math

# --- ค่าตั้งต้น (รอยืนยัน) ---
DEFAULT_MULT = {45: 6.0, 90: 12.0, 135: 6.0, 180: 4.0}
MIN_EXT_MM = {135: 75.0}          # 135°: ไม่น้อยกว่า 75 มม. (ที่ผู้ใช้กำหนด)
ANGLES = (45, 90, 135, 180)
STAGGER_FACTOR = 1.3              # ระยะเหลื่อมของจุดต่อ = 1.3 × ระยะทาบ (ค่าสมมติ)

# ตัวเลือกใน dropdown ตะขอ: ค่าเดิมของโมดูล / ไม่มี / มุมต่างๆ
HOOK_KEEP = u"ค่าเดิมของโมดูล"
HOOK_NONE = u"ไม่มี"
HOOK_ITEMS = [HOOK_KEEP, HOOK_NONE, u"45°", u"90°", u"135°", u"180°"]
_ANGLE_OF = {u"45°": 45, u"90°": 90, u"135°": 135, u"180°": 180}

STAGGER_OFF = u"ไม่สลับ (ค่าเดิม)"
STAGGER_ALT = u"สลับเส้นเว้นเส้น"
STAGGER_ITEMS = [STAGGER_OFF, STAGGER_ALT]


def parse_hook(item):
    """ข้อความ dropdown → ('keep'|'none'|angle int)"""
    if item is None or item == HOOK_KEEP:
        return "keep"
    if item == HOOK_NONE:
        return "none"
    return _ANGLE_OF.get(item, "keep")


def default_mult(angle):
    return DEFAULT_MULT.get(int(angle), 12.0)


def hook_ext_mm(angle, mult, dia):
    """ความยาวช่วงตรงปลายตะขอ (มม.) = mult × d แต่ไม่น้อยกว่าขั้นต่ำของมุมนั้น"""
    return max(float(mult) * float(dia), MIN_EXT_MM.get(int(angle), 0.0))


def effective_mult(angle, mult, dia):
    """ตัวคูณจริงหลังคิดขั้นต่ำ (ใช้สร้าง RebarHookType) — เช่น 135°, d=9, 6× → 75/9"""
    if dia <= 0:
        return float(mult)
    return hook_ext_mm(angle, mult, dia) / float(dia)


def bend_radius_mm(dia):
    """รัศมีในของการงอ (ประมาณ) = 3d (d ≤ 25) หรือ 4d (d > 25) — ไม่ได้อ่านจาก Bar Type"""
    return (3.0 if dia <= 25 else 4.0) * dia


def hook_developed_mm(angle, mult, dia, bend_dia=None):
    """ความยาวที่ตะขอ 1 ข้างเพิ่มให้เหล็ก = ส่วนโค้งตามแกนกลาง + ช่วงตรงปลาย (มม.)
    bend_dia = เส้นผ่านศูนย์กลางในของการงอ (ถ้ารู้จาก Bar Type) ไม่งั้นประมาณจาก bend_radius_mm"""
    r_in = (bend_dia / 2.0) if bend_dia else bend_radius_mm(dia)
    arc = math.radians(angle) * (r_in + dia / 2.0)
    return arc + hook_ext_mm(angle, mult, dia)


def cut_length_mm(straight_mm, dia, hook_a=None, hook_b=None, bend_dia=None):
    """ความยาวตัดรวมตะขอ: straight_mm = ความยาวเส้นตรง (ปลายทางเรขาคณิต) ; hook_x = (มุม, ตัวคูณ) หรือ None"""
    total = float(straight_mm)
    for h in (hook_a, hook_b):
        if h:
            total += hook_developed_mm(h[0], h[1], dia, bend_dia)
    return total


def lap_mm(dia, lap_d):
    return float(dia) * float(lap_d)


def spliced_cut_length_mm(span_mm, dia, lap_d, n_splices, hook_a=None, hook_b=None):
    """ความยาวตัดรวมของเหล็กหนึ่งแนวที่ต่อทาบ n_splices จุด: ความยาวแนว + ทาบจุดละ lap + ตะขอปลาย"""
    return cut_length_mm(span_mm + max(int(n_splices), 0) * lap_mm(dia, lap_d), dia,
                         hook_a, hook_b)


def stagger_extra_mm(index, lap, mode):
    """ระยะต่อเพิ่มของเหล็กเส้นลำดับ index เมื่อสลับจุดต่อ (เส้นคี่ยื่นเพิ่ม STAGGER_FACTOR × lap)"""
    if mode == STAGGER_ALT and index % 2 == 1:
        return STAGGER_FACTOR * lap
    return 0.0


def stagger_offsets(n, lap, mode):
    return [stagger_extra_mm(i, lap, mode) for i in range(int(n))]
