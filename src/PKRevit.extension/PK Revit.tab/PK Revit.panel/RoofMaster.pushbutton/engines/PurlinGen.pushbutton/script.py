# -*- coding: utf-8 -*-
"""Purlin Gen — สร้างแปใหม่เรียงเต็มทุกผืนหลังคาอัตโนมัติ

สิ่งที่สคริปต์ทำ (คลิกเดียว, Transaction เดียว → Ctrl+Z ครั้งเดียวย้อนได้หมด):

1) หา "ผืนหลังคา" (top face) ของ Roof ทุกตัว
   - เลือก Roof ก่อนรัน = ทำเฉพาะหลังที่เลือก / ไม่เลือก = ทำทุกหลังในโมเดล
2) ลบแปเดิมทั้งหมด (Structural Framing ที่ชื่อ type มีทุกคำใน TYPE_KEYWORDS)
   - ปิดได้ที่ DELETE_OLD = False
3) แต่ละผืน: วางแปขนานแนวเชิงชาย (แนวระดับของผืน) ไต่ตามลาดขึ้นไปถึงสัน
   - ระยะแปปรับเฉลี่ยให้เท่ากันทุกช่วง ไม่เกิน MAX_SPACING_MM
   - แถวแรกห่างขอบล่าง (เชิงชาย) EAVE_OFFSET_MM
   - แถวสุดท้ายห่างสัน/จุดยอด RIDGE_OFFSET_MM
   - ปลายแปตัดชนแนวตะเข้/ขอบผืนพอดี (ร่นเข้ามาได้ด้วย END_SETBACK_MM)
   - หมุนหน้าตัดแปตามลาดหลังคา (Cross-Section Rotation) — ปิดได้ที่ ROTATE_WITH_SLOPE
4) DisallowJoinAtEnd ปลายแปทุกตัว กัน error "Elements do not intersect"
5) MITER_CUT_AT_HIP: ตัดปลายแปด้วย "ระนาบดิ่งตามแนวตะเข้" ให้เป็นรอยตัดเฉียง
   (miter) แท้ — เทียบเท่าวิธีทำมือ Reference Plane + Cut Geometry
   (API ไม่มีคำสั่ง cut ด้วย ref plane ตรงๆ เลยใช้ void ล่องหนวางแนบระนาบแทน)
6) AUTO_ROOF_JOIN: จอยแป↔ผืนหลังคา (Join Geometry, แปคงเนื้อเต็ม) ปิดท้าย
   กันปริมาตรนับซ้ำ — ปุ่มเดียวจบ ไม่ต้องกด RoofJoin ตามอีก
"""

import math
import os
from System.Collections.Generic import List
from pyrevit import revit, DB, forms, script

doc = revit.doc
out = script.get_output()

# ===================== CONFIG =====================
TYPE_KEYWORDS = [u"แป"]      # หา type แป (ทั้งลบตัวเดิม และใช้เป็น type ตัวใหม่)

MAX_SPACING_MM = 340.0       # ระยะแป (วัดตามลาด)
UNIFORM_SPACING = True       # True = ทุกผืนใช้ระยะ MAX_SPACING_MM เท่ากันเป๊ะ
                             #        (เศษที่เหลือเก็บเป็นแถวชิดสัน → แถวชนกันพอดีที่ตะเข้)
                             # False = ปรับเฉลี่ยรายผืนให้ลงตัว (ระยะแต่ละผืนไม่เท่ากัน)
EAVE_OFFSET_MM = 340.0       # แถวแรกห่างขอบเชิงชาย (วัดตามลาด)
RIDGE_OFFSET_MM = 50.0       # แถวสุดท้ายห่างสัน/จุดยอด (วัดตามลาด ถึง "ขอบบน" ของแป)
RIDGE_EDGE_COMP_MM = 12.4    # ชดเชยครึ่งความกว้างฐานแป: เลื่อนแนวแกนแถวบนสุดลงตามลาด
                             # เพื่อให้ขอบบนของแป (ไม่ใช่กึ่งกลาง) ห่างสัน = RIDGE_OFFSET_MM
END_SETBACK_MM = 0.0         # ปลายแปร่นจากแนวตะเข้/ขอบผืน (มม.) เช่น ตะเข้กว้าง 50 → ใส่ 25
MIN_SEG_MM = 80.0            # ท่อนที่สั้นกว่านี้ไม่สร้าง (กันเศษจิ๋วใกล้จุดยอดปั้นหยา)
VERTICAL_OFFSET_MM = 0.0     # เลื่อนแนวแปลงจากผิวบนหลังคา (มม., ค่าบวก = ลงล่าง)
SINK_INTO_ROOF = False       # กดแปทั้งชุดจมเข้าเนื้อหลังคา (คาลิเบรตจากเนื้อจริง
                             # แบบ Rafter Gen: วัดยอดแปที่โผล่เหนือระนาบผืน → กดลง
                             # ให้ยอดแนบผิวบน แล้วจมเพิ่มอีก SINK_EXTRA_MM)
SINK_EXTRA_MM = 10.0         # จมเพิ่มจากระดับ "ยอดแปเสมอผิว" (กันจอยแล้วกรีดผิวบน
                             # เป็นร่อง — ใส่ค่าลบได้ถ้าอยากให้โผล่)

MITER_AT_ENDS = False        # จอยปลายของ Revit — ใช้กับแปหมุนหน้าตัดไม่ได้ (จะ cutback
                             # ถอยหนีมุมเป็นช่องว่าง) ปิดไว้ ใช้ MITER_CUT_AT_HIP แทน
CORNER_SNAP_MM = 500.0       # Trim/Extend to Corner อัตโนมัติ: คู่ปลายแปที่ห่างกันไม่เกินนี้ (มม.)
                             # จะถูกยืด/หดไปชนกันที่จุดมุมตะเข้ — 0 = ปิด
CORNER_Z_TOL_MM = 100.0      # จับคู่ได้ถ้าปลายต่างระดับกันไม่เกินนี้ (มม.)
CORNER_OVERLAP_MM = 60.0     # ยื่นปลายเลยจุดมุมตะเข้ (มม.) ให้มีเนื้อทะลุแนวตะเข้พอให้ตัดเฉียง
                             # (ลดจาก 100 ให้พอดีใบมีดจิ๋ว XXS — ผลตัดเท่าเดิม
                             #  เพราะรอยตัดอยู่ที่ระนาบ ไม่ใช่ที่ปลายเกย)
MITER_CUT_AT_HIP = True      # ตัดปลายแปด้วย "ระนาบดิ่งตามแนวตะเข้" = วิธีทำมือ
                             # Reference Plane + Cut Geometry (ได้ miter cut แท้)
                             # ใช้ void ล่องหนเป็นใบมีด (family สร้าง/โหลดอัตโนมัติ)
VOID_FAM_NAME = u"REVOTECH_MiterVoidXXS"   # เวอร์ชันใบมีดจิ๋ว (ตัวเก่ากล่องยักษ์ถูกล้างทิ้ง)
ROTATE_WITH_SLOPE = True     # หมุนหน้าตัดแปให้แนบตามลาดผืนหลังคา (แบบแปวางบนจันทันจริง)
AUTO_ROOF_JOIN = True        # ปิดท้ายด้วยจอยแป↔ผืนหลังคาให้เลย (= กด RoofJoin ให้ในตัว)
Z_JUSTIFY = u"origin"        # จุดอ้างอิงหน้าตัดบนแนวแป: origin / bottom / center / top / asis
DELETE_OLD = True            # ลบแปเดิมก่อนสร้างใหม่

# ตั้งวัสดุ (Structural Material) ให้แปใหม่ — ใส่ชื่อวัสดุ (พิมพ์แค่บางส่วนก็ได้)
# เช่น u"กัลวาไนซ์"  /  ปล่อยว่าง u"" = ใช้ค่าเดิมของ family (ตอนนี้ได้ "สีกันสนิมแดง")
MATERIAL_NAME = u""
# ==================================================
# รับค่า override จากปุ่ม Roof Master (กดรันเดี่ยวไม่มีตัวแปรนี้ = ใช้ค่าข้างบน)
try:
    globals().update(CONFIG_OVERRIDE)
except NameError:
    pass


# ---------- helpers (Revit 2026 + IronPython 2.7.12) ----------
def ename(e):
    try:
        return e.Name
    except Exception:
        try:
            return DB.Element.Name.__get__(e)
        except Exception:
            return u"(ไม่ทราบชื่อ)"


def cat_id(e):
    try:
        c = e.Category
        if c is None:
            return None
        try:
            return c.Id.Value
        except Exception:
            return c.Id.IntegerValue
    except Exception:
        return None


def type_name(e):
    try:
        t = doc.GetElement(e.GetTypeId())
        if t is not None:
            return ename(t)
    except Exception:
        pass
    return u""


def mm_to_ft(v):
    return DB.UnitUtils.ConvertToInternalUnits(float(v), DB.UnitTypeId.Millimeters)


FT_TO_MM = 304.8
MAX_SP = mm_to_ft(MAX_SPACING_MM)
EAVE_OFF = mm_to_ft(EAVE_OFFSET_MM)
RIDGE_OFF = mm_to_ft(RIDGE_OFFSET_MM) + mm_to_ft(RIDGE_EDGE_COMP_MM)
SETBACK = mm_to_ft(END_SETBACK_MM)
MIN_SEG = mm_to_ft(MIN_SEG_MM)
VOFF = mm_to_ft(VERTICAL_OFFSET_MM)
SINK_EXTRA = mm_to_ft(SINK_EXTRA_MM)
TOL = mm_to_ft(1.0)


def is_framing(e):
    return cat_id(e) == int(DB.BuiltInCategory.OST_StructuralFraming)


def is_roof(e):
    return cat_id(e) == int(DB.BuiltInCategory.OST_Roofs)


def match_keywords(name):
    low = name.lower()
    return all(kw.lower() in low for kw in TYPE_KEYWORDS)


# ---------- เก็บผืนหลังคา (top face) ----------
def collect_roof_faces(roofs):
    faces = []
    for roof in roofs:
        try:
            refs = DB.HostObjectUtils.GetTopFaces(roof)
        except Exception:
            continue
        for r in refs:
            try:
                f = roof.GetGeometryObjectFromReference(r)
            except Exception:
                continue
            if not isinstance(f, DB.PlanarFace):
                continue
            n = f.FaceNormal
            if n.Z < 0:
                n = n.Negate()
            if n.Z < 0.05:          # ผืนเกือบดิ่ง ใช้ไม่ได้
                continue
            loops = []
            try:
                for cl in f.GetEdgesAsCurveLoops():
                    pts = []
                    for c in cl:
                        tess = list(c.Tessellate())
                        for p in tess[:-1]:
                            pts.append((p.X, p.Y, p.Z))
                    if len(pts) >= 3:
                        loops.append(pts)
            except Exception:
                continue
            if loops:
                faces.append({"loops": loops, "n": n, "roof": roof})
    return faces


def point_in_face(fd, x, y):
    inside = False
    for pts in fd["loops"]:
        m = len(pts)
        j = m - 1
        for i in range(m):
            x1, y1 = pts[i][0], pts[i][1]
            x2, y2 = pts[j][0], pts[j][1]
            if (y1 > y) != (y2 > y):
                xin = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
                if x < xin:
                    inside = not inside
            j = i
    return inside


def ray_hits(fd, mx, my, ux, uy):
    ts = []
    for pts in fd["loops"]:
        m = len(pts)
        j = m - 1
        for i in range(m):
            px, py = pts[j][0], pts[j][1]
            qx, qy = pts[i][0], pts[i][1]
            vx, vy = qx - px, qy - py
            denom = ux * vy - uy * vx
            if abs(denom) < 1e-12:
                j = i
                continue
            wx, wy = px - mx, py - my
            t = (wx * vy - wy * vx) / denom
            s = (wx * uy - wy * ux) / denom
            if -1e-9 <= s <= 1.0 + 1e-9:
                ts.append(t)
            j = i
    return ts


# ---------- วางแผนแถวแปของแต่ละผืน ----------
def plan_face(fd):
    """คืน (plan, err_msg) — plan = dict(h, s, base, rows, step_mm)"""
    n = fd["n"]
    nh = math.sqrt(n.X * n.X + n.Y * n.Y)
    if nh < 1e-6:
        return None, u"ผืนราบ (ไม่มีทิศลาด)"
    h = DB.XYZ(-n.Y, n.X, 0.0).Normalize()   # แนวเชิงชาย/แนวระดับของผืน
    s = n.CrossProduct(h)                     # แนวไต่ลาดในระนาบผืน
    if s.Z < 0:
        s = s.Negate()

    verts = []
    for pts in fd["loops"]:
        for p in pts:
            verts.append(DB.XYZ(p[0], p[1], p[2]))
    v0 = verts[0]
    dmin, dmax = 0.0, 0.0
    for v in verts:
        d = s.DotProduct(v - v0)
        if d < dmin:
            dmin = d
        if d > dmax:
            dmax = d
    slope_len = dmax - dmin
    base = v0 + s * dmin                      # จุดอ้างอิงที่แนวขอบล่างสุด (เชิงชาย)

    usable = slope_len - EAVE_OFF - RIDGE_OFF
    if usable < MIN_SEG:
        return None, u"ผืนเล็กเกิน (ลาดยาว {:.0f} มม.)".format(slope_len * FT_TO_MM)

    top = slope_len - RIDGE_OFF
    if UNIFORM_SPACING:
        # ระยะเท่ากันทุกผืน เศษที่เหลือเก็บเป็นแถวชิดสัน
        step = MAX_SP
        rows = []
        d = EAVE_OFF
        while d < top - TOL:
            rows.append(d)
            d += step
        if rows and (top - rows[-1]) < MIN_SEG:
            rows[-1] = top      # แถวสุดท้ายใกล้สันมาก → ขยับไปชิดสันแทน
        else:
            rows.append(top)    # เพิ่มแถวเก็บสัน
    else:
        # ปรับเฉลี่ยรายผืนให้ลงตัวพอดี (ระยะแต่ละผืนไม่เท่ากัน)
        n_gaps = int(math.ceil(usable / MAX_SP))
        if n_gaps < 1:
            n_gaps = 1
        step = usable / n_gaps
        rows = [EAVE_OFF + i * step for i in range(n_gaps + 1)]
    return {"h": h, "s": s, "base": base, "rows": rows,
            "step_mm": step * FT_TO_MM}, None


def row_segments(fd, plan, d):
    """ตัดแนวแถวแปที่ระยะลาด d ให้เป็นท่อนๆ ภายในผืน คืน [(p0, p1), ...]"""
    h, s, base = plan["h"], plan["s"], plan["base"]
    q = base + s * d
    ts = ray_hits(fd, q.X, q.Y, h.X, h.Y)
    ts.sort()
    dedup = []
    for t in ts:
        if not dedup or t - dedup[-1] > TOL:
            dedup.append(t)
    segs = []
    for k in range(len(dedup) - 1):
        t0, t1 = dedup[k], dedup[k + 1]
        tm = (t0 + t1) / 2.0
        if not point_in_face(fd, q.X + h.X * tm, q.Y + h.Y * tm):
            continue
        t0 += SETBACK
        t1 -= SETBACK
        if (t1 - t0) < MIN_SEG:
            continue
        z = q.Z - VOFF
        segs.append((DB.XYZ(q.X + h.X * t0, q.Y + h.Y * t0, z),
                     DB.XYZ(q.X + h.X * t1, q.Y + h.Y * t1, z)))
    return segs


# ---------- ปรับหน้าตัดแปให้แนบระนาบผืน ----------
ZJUST_MAP = {u"top": 0, u"center": 1, u"origin": 2, u"bottom": 3}


def set_zjust(inst):
    v = ZJUST_MAP.get(Z_JUSTIFY.lower())
    if v is None:
        return
    try:
        pr = inst.get_Parameter(DB.BuiltInParameter.Z_JUSTIFICATION)
        if pr is not None and not pr.IsReadOnly:
            pr.Set(v)
    except Exception:
        pass


# ทิศหมุนหน้าตัด (convention ของ Revit เดาไม่ได้ → วัดจริงจากแปตัวแรก)
# 0 = ยังไม่คาลิเบรต, +1/-1 = ทิศที่วัดแล้วว่าหลังแปหันตาม normal ของผืน
_rot_sign = [0.0]


def set_material(inst):
    """ตั้ง Structural Material ตาม MATERIAL_NAME (ถ้าหาเจอ)"""
    if target_mat is None:
        return
    try:
        pr = inst.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
        if pr is not None and not pr.IsReadOnly:
            pr.Set(target_mat.Id)
    except Exception:
        pass


def zero_extensions(inst):
    """ล้างค่า Start/End Extension ที่ฝังมากับ family (เช่น -110.8 มม.)
    — ถ้าไม่ล้าง เนื้อแปจะหดจากปลายเส้นแกน ทำให้มุมตะเข้มีช่องว่าง
    ล้าง y/z Offset Value ด้วย — family แปของเทมเพลตแข่งฝัง z Offset
    +0.07 ม. มาเป็น default ทำให้แปทุกตัวลอยเหนือผิวหลังคา 70 มม.
    (พิสูจน์ในเครื่องทู 12 ก.ค.: เซ็ต 0 แล้วแปหล่นลงแนบผิวพอดี)"""
    for bip in (DB.BuiltInParameter.START_EXTENSION,
                DB.BuiltInParameter.END_EXTENSION,
                DB.BuiltInParameter.Y_OFFSET_VALUE,
                DB.BuiltInParameter.Z_OFFSET_VALUE):
        try:
            pr = inst.get_Parameter(bip)
            if pr is not None and not pr.IsReadOnly:
                pr.Set(0.0)
        except Exception:
            pass


def set_usage_purlin(inst):
    """ตั้ง Structural Usage = Purlin (กัน view filter ระบายสีผิดกลุ่ม)"""
    try:
        pu = inst.get_Parameter(DB.BuiltInParameter.INSTANCE_STRUCT_USAGE_PARAM)
        if pu is not None and not pu.IsReadOnly:
            pu.Set(int(DB.Structure.StructuralInstanceUsage.Purlin))
    except Exception:
        pass


def set_rotation(inst, rot, n):
    """หมุนหน้าตัดรอบแกนแปให้แนบลาดผืน (Cross-Section Rotation)"""
    if not ROTATE_WITH_SLOPE or rot < 1e-6:
        return
    try:
        pr = inst.get_Parameter(DB.BuiltInParameter.STRUCTURAL_BEND_DIR_ANGLE)
        if pr is None or pr.IsReadOnly:
            return
        if _rot_sign[0] == 0.0:
            # คาลิเบรตครั้งเดียว: ลองทั้ง +/- แล้ววัดว่าแกนตั้งของหน้าตัด
            # (BasisZ) ชี้ตาม normal ของผืนมากกว่าทางไหน
            pr.Set(rot)
            doc.Regenerate()
            dplus = inst.GetTransform().BasisZ.DotProduct(n)
            pr.Set(-rot)
            doc.Regenerate()
            dminus = inst.GetTransform().BasisZ.DotProduct(n)
            _rot_sign[0] = 1.0 if dplus >= dminus else -1.0
            if _rot_sign[0] > 0:
                pr.Set(rot)
        else:
            pr.Set(_rot_sign[0] * rot)
    except Exception:
        pass


# ---------- Trim/Extend to Corner อัตโนมัติ ----------
def snap_corners(insts):
    """จับคู่ปลายแปที่ใกล้กัน (ต่างตัว ระดับเดียวกัน แนวไม่ขนาน)
    แล้วยืด/หดปลายทั้งคู่ไปจบที่จุดตัดของสองแนว — เทียบเท่าคำสั่ง TR
    คืน (จำนวนคู่, probe, รายการคู่มุมไว้ใช้ตัดเฉียง)"""
    snap_r = mm_to_ft(CORNER_SNAP_MM)
    z_tol = mm_to_ft(CORNER_Z_TOL_MM)
    ends = []
    for e in insts:
        try:
            crv = e.Location.Curve
        except Exception:
            continue
        ends.append((e, 0, crv.GetEndPoint(0)))
        ends.append((e, 1, crv.GetEndPoint(1)))
    used = set()
    snapped = 0
    pairs_out = []   # (beamA, beamB, จุดมุม, ทิศเข้าเนื้อ A, ทิศเข้าเนื้อ B)
    probe = [None]   # (dxy, dz) คู่ปลายต่างตัวที่ใกล้กันสุดที่สแกนเจอ — ไว้วินิจฉัย
    m = len(ends)
    for i in range(m):
        if i in used:
            continue
        ei, end_i, pi = ends[i]
        best_j, best_d = -1, snap_r
        for j in range(i + 1, m):
            if j in used:
                continue
            ej, end_j, pj = ends[j]
            if ej.Id == ei.Id:
                continue
            dxy = math.sqrt((pi.X - pj.X) ** 2 + (pi.Y - pj.Y) ** 2)
            dz = abs(pi.Z - pj.Z)
            if probe[0] is None or dxy < probe[0][0]:
                probe[0] = (dxy, dz)
            if dz > z_tol:
                continue
            if dxy < best_d:
                best_d = dxy
                best_j = j
        if best_j < 0:
            continue
        ej, end_j, pj = ends[best_j]
        try:
            la = ei.Location.Curve
            lb = ej.Location.Curve
        except Exception:
            continue
        a0, a1 = la.GetEndPoint(0), la.GetEndPoint(1)
        b0, b1 = lb.GetEndPoint(0), lb.GetEndPoint(1)
        ua, ub = a1 - a0, b1 - b0
        la2 = math.sqrt(ua.X * ua.X + ua.Y * ua.Y)
        lb2 = math.sqrt(ub.X * ub.X + ub.Y * ub.Y)
        if la2 < 1e-9 or lb2 < 1e-9:
            continue
        ax, ay = ua.X / la2, ua.Y / la2
        bx, by = ub.X / lb2, ub.Y / lb2
        denom = ax * by - ay * bx
        if abs(denom) < 0.17:      # เกือบขนาน = ไม่ใช่มุมตะเข้ ข้าม
            continue
        wx, wy = b0.X - a0.X, b0.Y - a0.Y
        t = (wx * by - wy * bx) / denom
        ix, iy = a0.X + ax * t, a0.Y + ay * t
        if math.sqrt((ix - pi.X) ** 2 + (iy - pi.Y) ** 2) > snap_r * 3:
            continue                # จุดตัดไกลผิดปกติ ข้าม
        zc = (pi.Z + pj.Z) / 2.0
        over = mm_to_ft(CORNER_OVERLAP_MM)
        # ทิศยื่นปลายของแต่ละเส้น (จากปลายฝั่งอยู่กับที่ ชี้มาทางปลายที่ขยับ)
        if end_i == 0:
            dax, day = a0.X - a1.X, a0.Y - a1.Y
        else:
            dax, day = a1.X - a0.X, a1.Y - a0.Y
        dl = math.sqrt(dax * dax + day * day)
        dax, day = dax / dl, day / dl
        if end_j == 0:
            dbx, dby = b0.X - b1.X, b0.Y - b1.Y
        else:
            dbx, dby = b1.X - b0.X, b1.Y - b0.Y
        dl = math.sqrt(dbx * dbx + dby * dby)
        dbx, dby = dbx / dl, dby / dl
        newa = DB.XYZ(ix + dax * over, iy + day * over, zc)
        newb = DB.XYZ(ix + dbx * over, iy + dby * over, zc)
        try:
            if end_i == 0:
                ei.Location.Curve = DB.Line.CreateBound(newa, a1)
            else:
                ei.Location.Curve = DB.Line.CreateBound(a0, newa)
            if end_j == 0:
                ej.Location.Curve = DB.Line.CreateBound(newb, b1)
            else:
                ej.Location.Curve = DB.Line.CreateBound(b0, newb)
            used.add(i)
            used.add(best_j)
            snapped += 1
            # ทิศ "เข้าเนื้อแป" (จากจุดมุมชี้กลับเข้าตัวแป) ไว้คำนวณระนาบตะเข้
            pairs_out.append((ei, ej, DB.XYZ(ix, iy, zc),
                              DB.XYZ(-dax, -day, 0.0),
                              DB.XYZ(-dbx, -dby, 0.0)))
        except Exception:
            pass
    return snapped, probe[0], pairs_out


def _nearest_edge(fd, x, y):
    """หาขอบผืน (segment) ที่ใกล้จุดสุด — คืน (ระยะ², ทิศขอบ fx, fy)"""
    best = None
    for pts in fd["loops"]:
        m = len(pts)
        j = m - 1
        for i in range(m):
            x1, y1 = pts[j][0], pts[j][1]
            x2, y2 = pts[i][0], pts[i][1]
            vx, vy = x2 - x1, y2 - y1
            l2 = vx * vx + vy * vy
            if l2 < 1e-12:
                j = i
                continue
            t = ((x - x1) * vx + (y - y1) * vy) / l2
            if t < 0.0:
                t = 0.0
            elif t > 1.0:
                t = 1.0
            cx, cy = x1 + vx * t, y1 + vy * t
            d2 = (x - cx) ** 2 + (y - cy) ** 2
            if best is None or d2 < best[0]:
                ll = math.sqrt(l2)
                best = (d2, vx / ll, vy / ll)
            j = i
    return best


# ---------- คาลิเบรตระดับ: วัดว่าเนื้อแปโผล่เหนือระนาบผืนเท่าไหร่ ----------
# (วิธีเดียวกับ Rafter Gen — วัดจาก solid จริง ไม่เดาจากขนาดหน้าตัด)
def _solid_max_above(g, n, vx, vy, vz):
    """ระยะ (ตามแนว normal ผืน) ที่จุดเนื้อสูงสุดของ geometry อยู่เหนือระนาบ"""
    best = None
    for obj in g:
        if isinstance(obj, DB.GeometryInstance):
            b = _solid_max_above(obj.GetInstanceGeometry(), n, vx, vy, vz)
            if b is not None and (best is None or b > best):
                best = b
        elif isinstance(obj, DB.Solid) and obj.Volume > 1e-9:
            for e in obj.Edges:
                for p in e.Tessellate():
                    d = (n.X * (p.X - vx) + n.Y * (p.Y - vy)
                         + n.Z * (p.Z - vz))
                    if best is None or d > best:
                        best = d
    return best


# ---------- ใบมีดตัดเฉียง: family กล่อง void (มองไม่เห็น ใช้ตัดอย่างเดียว) ----------
# กล่องจิ๋ว XXS: ยาว ±15ซม. ตามแกน X, หนา 15ซม. ฝั่ง +Y (หน้าที่ Y=0 คือ "ระนาบใบมีด"),
# สูง ±15ซม. (ทูขอเล็กสุด — CORNER_OVERLAP ต้องไม่เกิน ~60 ให้เนื้อเกยอยู่ในใบมีด)
# — วาง 2 ตัวประกบที่จุดมุมแต่ละจุด ให้หน้า Y=0 แนบระนาบดิ่งแนวตะเข้
# แล้วสั่งตัดเฉพาะปลายแปที่ยื่นข้าม (จิ๋ว+ไม่ pin = ลากคลุมย้ายไปพร้อมงานได้ทั้งชุด)
def build_void_family(rfa_path):
    """สร้างไฟล์ .rfa กล่อง void — คืน None ถ้าสำเร็จ / ข้อความ error ถ้าพลาด"""
    app = doc.Application
    tpl = None
    try:
        tdir = app.FamilyTemplatePath
        best = None
        for root, dirs, files in os.walk(tdir):
            for fn in files:
                low = fn.lower()
                if not low.endswith(".rft"):
                    continue
                if "generic model" not in low:
                    continue
                bad = ("adaptive", "line", "face", "wall", "ceiling", "floor",
                       "roof", "pattern", "two", "level", "curtain", "site")
                if any(b in low for b in bad):
                    continue
                if best is None or len(fn) < len(best[0]):
                    best = (fn, os.path.join(root, fn))
        if best:
            tpl = best[1]
    except Exception:
        pass
    if tpl is None:
        return u"หา template 'Generic Model.rft' ไม่เจอ (FamilyTemplatePath)"
    fdoc = None
    try:
        fdoc = app.NewFamilyDocument(tpl)
        t = DB.Transaction(fdoc, "REVOTECH void box")
        t.Start()
        try:
            fam = fdoc.OwnerFamily
            pv = fam.get_Parameter(DB.BuiltInParameter.FAMILY_ALLOW_CUT_WITH_VOIDS)
            if pv is not None and not pv.IsReadOnly:
                pv.Set(1)      # "Cut with Voids When Loaded" = Yes
            sp = DB.SketchPlane.Create(
                fdoc, DB.Plane.CreateByNormalAndOrigin(DB.XYZ.BasisZ, DB.XYZ.Zero))
            L, W, H = 0.49, 0.49, 0.49     # ครึ่งยาว 15ซม. / หนา 15ซม. / ครึ่งสูง 15ซม. (ft)
                                           # (รุ่น XXS — ทูขอเล็กสุด: จุดที่ต้อง
                                           #  ตัดลึก/ยาวกว่านี้ใช้วิธีวางหลายใบแทน)
            pts = [DB.XYZ(-L, 0, 0), DB.XYZ(L, 0, 0),
                   DB.XYZ(L, W, 0), DB.XYZ(-L, W, 0)]
            ca = DB.CurveArray()
            for k in range(4):
                ca.Append(DB.Line.CreateBound(pts[k], pts[(k + 1) % 4]))
            caa = DB.CurveArrArray()
            caa.Append(ca)
            ext = fdoc.FamilyCreate.NewExtrusion(False, caa, sp, H)
            ps = ext.get_Parameter(DB.BuiltInParameter.EXTRUSION_START_PARAM)
            if ps is not None:
                ps.Set(-H)
            t.Commit()
        except Exception as ex:
            t.RollBack()
            return u"สร้าง void ใน family ไม่สำเร็จ: {}".format(ex)
        so = DB.SaveAsOptions()
        so.OverwriteExistingFile = True
        fdoc.SaveAs(rfa_path, so)
        return None
    except Exception as ex:
        return u"สร้าง family ไม่สำเร็จ: {}".format(ex)
    finally:
        if fdoc is not None:
            try:
                fdoc.Close(False)
            except Exception:
                pass


def find_void_symbol():
    for f in DB.FilteredElementCollector(doc).OfClass(DB.Family):
        if ename(f) == VOID_FAM_NAME:
            for sid in f.GetFamilySymbolIds():
                return doc.GetElement(sid)
    return None


# ---------- main ----------
sel_roofs = [e for e in revit.get_selection().elements if is_roof(e)]
if sel_roofs:
    roofs = sel_roofs
    out.print_md(u"ทำเฉพาะหลังคาที่เลือก **{} ตัว**".format(len(roofs)))
else:
    roofs = list(DB.FilteredElementCollector(doc)
                 .OfCategory(DB.BuiltInCategory.OST_Roofs)
                 .WhereElementIsNotElementType()
                 .ToElements())
if not roofs:
    forms.alert(u"ไม่พบ Roof ในโมเดล", exitscript=True)

# แปเดิม (จะลบ + ใช้เป็นต้นแบบ type/level)
all_framing = list(DB.FilteredElementCollector(doc)
                   .OfCategory(DB.BuiltInCategory.OST_StructuralFraming)
                   .WhereElementIsNotElementType()
                   .ToElements())
old_purlins = [e for e in all_framing if match_keywords(type_name(e))]

# type แปที่จะใช้สร้าง
sym = None
if old_purlins:
    sym = doc.GetElement(old_purlins[0].GetTypeId())
if sym is None:
    for t in DB.FilteredElementCollector(doc) \
              .OfCategory(DB.BuiltInCategory.OST_StructuralFraming) \
              .WhereElementIsElementType():
        if match_keywords(ename(t)):
            sym = t
            break
if sym is None:
    forms.alert(u"หา type แป (ชื่อมีคำว่า {}) ไม่เจอในโปรเจกต์".format(
        u", ".join(TYPE_KEYWORDS)), exitscript=True)

# level สำรอง (จากแปเดิม หรือ level ล่างสุด)
fb_level = None
if old_purlins:
    try:
        p = old_purlins[0].get_Parameter(
            DB.BuiltInParameter.INSTANCE_REFERENCE_LEVEL_PARAM)
        if p is not None:
            lv = doc.GetElement(p.AsElementId())
            if isinstance(lv, DB.Level):
                fb_level = lv
    except Exception:
        pass
if fb_level is None:
    lvls = list(DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements())
    if not lvls:
        forms.alert(u"ไม่พบ Level ในโปรเจกต์", exitscript=True)
    fb_level = sorted(lvls, key=lambda l: l.Elevation)[0]


def level_for(roof):
    try:
        lid = roof.LevelId
        if lid is not None and lid != DB.ElementId.InvalidElementId:
            lv = doc.GetElement(lid)
            if isinstance(lv, DB.Level):
                return lv
    except Exception:
        pass
    return fb_level


# วัสดุที่จะตั้งให้แปใหม่ (ถ้ากำหนดชื่อไว้)
target_mat = None
if MATERIAL_NAME:
    _mlow = MATERIAL_NAME.lower()
    for _m in DB.FilteredElementCollector(doc).OfClass(DB.Material):
        if _mlow in _m.Name.lower():
            target_mat = _m
            break

# เตรียมใบมีดตัดเฉียง (โหลด/สร้าง family void) — ต้องทำก่อนเปิด TransactionGroup
void_sym = None
miter_msg = None
if MITER_CUT_AT_HIP:
    void_sym = find_void_symbol()
    if void_sym is None:
        rfa = os.path.join(os.path.dirname(__file__), VOID_FAM_NAME + u".rfa")
        if not os.path.isfile(rfa):
            miter_msg = build_void_family(rfa)
        if miter_msg is None:
            try:
                with revit.Transaction("REVOTECH - โหลด MiterVoid"):
                    doc.LoadFamily(rfa)
            except Exception as ex:
                miter_msg = u"โหลด family ไม่สำเร็จ: {}".format(ex)
            void_sym = find_void_symbol()
    if void_sym is None and miter_msg is None:
        miter_msg = u"หา family {} ไม่เจอหลังโหลด".format(VOID_FAM_NAME)

faces = collect_roof_faces(roofs)
if not faces:
    forms.alert(u"หาผืนหลังคา (top face) ไม่เจอ", exitscript=True)
out.print_md(u"พบผืนหลังคา **{} ผืน** / แปเดิม {} ตัว / type: `{}`".format(
    len(faces), len(old_purlins), ename(sym)))

created, err = 0, 0
total_len = 0.0
skipped = []
face_report = []
created_insts = []
created_recs = []    # (แป, ผืนเจ้าของ) ไว้ตัดปลายที่ขอบผืน
inst_roofs = []      # (แป, roof เจ้าของผืน) ไว้จอยปิดท้าย
unjoined = 0

# ห่อ 2 Transaction (สร้าง → ปลด join) ให้ Ctrl+Z ย้อนครั้งเดียว
tg = DB.TransactionGroup(doc, "REVOTECH - Purlin Gen")
tg.Start()

with revit.Transaction("REVOTECH - Purlin Gen (สร้าง)", swallow_errors=True):
    if DELETE_OLD and old_purlins:
        doc.Delete(List[DB.ElementId]([e.Id for e in old_purlins]))
    # ลบใบมีด void รอบก่อน (ถ้ามี) กันซ้อนสะสม
    stale_voids = []
    for gm in DB.FilteredElementCollector(doc) \
               .OfCategory(DB.BuiltInCategory.OST_GenericModel) \
               .WhereElementIsNotElementType():
        try:
            if gm.Symbol.Family.Name.startswith(u"REVOTECH_MiterVoid"):
                cmv = gm.get_Parameter(
                    DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                _cs = (cmv.AsString() or u"") if cmv is not None else u""
                if u"[จันทัน]" in _cs or u"[ตะเข้]" in _cs:
                    continue         # ใบมีดของ Rafter/HipRidge Gen — ไม่ใช่ของเรา
                gm.Pinned = False    # ปลด pin ก่อน ไม่งั้นลบไม่ออก
                stale_voids.append(gm.Id)
        except Exception:
            pass
    if stale_voids:
        doc.Delete(List[DB.ElementId](stale_voids))
    # ล้าง family ใบมีดรุ่นเก่า (เช่นกล่องยักษ์รุ่นแรก) ออกจากโปรเจกต์
    old_fams = [f.Id for f in
                DB.FilteredElementCollector(doc).OfClass(DB.Family)
                if ename(f).startswith(u"REVOTECH_MiterVoid")
                and ename(f) != VOID_FAM_NAME]
    if old_fams:
        doc.Delete(List[DB.ElementId](old_fams))
    if not sym.IsActive:
        sym.Activate()
        doc.Regenerate()

    for idx, fd in enumerate(faces):
        plan, why = plan_face(fd)
        if plan is None:
            skipped.append((idx + 1, fd["roof"], why))
            continue
        lvl = level_for(fd["roof"])
        n = fd["n"]
        rot = math.atan2(math.sqrt(n.X * n.X + n.Y * n.Y), n.Z)
        cnt_face = 0
        for d in plan["rows"]:
            for p0, p1 in row_segments(fd, plan, d):
                try:
                    line = DB.Line.CreateBound(p0, p1)
                    inst = doc.Create.NewFamilyInstance(
                        line, sym, lvl, DB.Structure.StructuralType.Beam)
                    try:
                        if MITER_AT_ENDS:
                            DB.Structure.StructuralFramingUtils.AllowJoinAtEnd(inst, 0)
                            DB.Structure.StructuralFramingUtils.AllowJoinAtEnd(inst, 1)
                        else:
                            DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(inst, 0)
                            DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(inst, 1)
                    except Exception:
                        pass
                    set_zjust(inst)
                    set_rotation(inst, rot, n)
                    set_usage_purlin(inst)
                    set_material(inst)
                    zero_extensions(inst)
                    created_insts.append(inst)
                    created_recs.append((inst, fd))
                    inst_roofs.append((inst, fd["roof"]))
                    created += 1
                    cnt_face += 1
                    total_len += p0.DistanceTo(p1)
                except Exception:
                    err += 1
        face_report.append((idx + 1, fd["roof"], len(plan["rows"]),
                            cnt_face, plan["step_mm"]))

# ตั้งระดับ: วัดเนื้อจริงแล้วกดทั้งชุดจมลง ให้ยอดแปแนบผิวบนหลังคา (+จมเพิ่มตาม config)
# — กดจม "ตั้งฉากกับผืน" (ตาม normal) ไม่ใช่แนวดิ่ง: ตำแหน่งแถวบนผืนคงเดิมเป๊ะ
#   (EAVE/RIDGE_OFFSET ไม่เพี้ยน) ปลายที่แยกกันเล็กน้อยที่ตะเข้ snap corners เก็บต่อ
# — ต้องทำ "ก่อน" snap corners เพื่อให้จุดมุม/ใบมีดตัดเฉียง/จอย เห็นตำแหน่งสุดท้าย
lowered_mm = 0.0
if SINK_INTO_ROOF and created_recs:
    with revit.Transaction("REVOTECH - Purlin Gen (ตั้งระดับ)",
                           swallow_errors=True):
        doc.Regenerate()
        s_probe, s_pfd = None, None
        best_len = 0.0
        for _i2, _f2 in created_recs:      # ใช้ตัวยาวสุดเป็นตัววัด
            try:
                _l = _i2.Location.Curve.Length
            except Exception:
                continue
            if _l > best_len:
                best_len = _l
                s_probe, s_pfd = _i2, _f2
        dn = SINK_EXTRA                    # ระยะจมวัดตั้งฉากกับผืน
        if s_probe is not None:
            try:
                dmax = _solid_max_above(
                    s_probe.get_Geometry(DB.Options()), s_pfd["n"],
                    s_pfd["loops"][0][0][0], s_pfd["loops"][0][0][1],
                    s_pfd["loops"][0][0][2])
            except Exception:
                dmax = None
            if dmax is not None and dmax > mm_to_ft(1.0):
                dn += dmax
        if abs(dn) > mm_to_ft(0.5):
            for _i2, _f2 in created_recs:
                n2 = _f2["n"]              # จมตาม normal ของผืนเจ้าของแต่ละตัว
                try:
                    DB.ElementTransformUtils.MoveElement(
                        doc, _i2.Id,
                        DB.XYZ(-n2.X * dn, -n2.Y * dn, -n2.Z * dn))
                except Exception:
                    pass
            lowered_mm = dn * FT_TO_MM

# Trim/Extend to Corner อัตโนมัติ: ต่อปลายแปเข้ามุมที่ตะเข้ (แบบคำสั่ง TR)
# ปลายชนกันเป๊ะ + AllowJoinAtEnd → Revit จอยเข้ามุม (miter) เองตอนปิด Transaction
snapped = 0
snap_probe = None
corner_pairs = []
if CORNER_SNAP_MM > 0 and created_insts:
    with revit.Transaction("REVOTECH - Purlin Gen (ต่อปลายเข้ามุม)",
                           swallow_errors=True):
        snapped, snap_probe, corner_pairs = snap_corners(created_insts)

# Revit สร้าง auto-join ตอน "ปิด" Transaction แรก → ต้องกวาดปลดใน
# Transaction ที่สอง (รอบก่อนกวาดก่อน join เกิด เลยไม่เจออะไร)
with revit.Transaction("REVOTECH - Purlin Gen (ปลด join)", swallow_errors=True):
    _cats = List[DB.BuiltInCategory]([
        DB.BuiltInCategory.OST_StructuralFraming,
        DB.BuiltInCategory.OST_StructuralColumns])
    _catfilter = DB.ElementMulticategoryFilter(_cats)
    for inst in created_insts:
        bb = inst.get_BoundingBox(None)
        if bb is None:
            continue
        bbf = DB.BoundingBoxIntersectsFilter(
            DB.Outline(bb.Min, bb.Max), mm_to_ft(10.0))
        near = DB.FilteredElementCollector(doc) \
                 .WherePasses(_catfilter) \
                 .WhereElementIsNotElementType() \
                 .WherePasses(bbf)
        for c in near:
            if c.Id == inst.Id:
                continue
            try:
                if DB.JoinGeometryUtils.AreElementsJoined(doc, inst, c):
                    DB.JoinGeometryUtils.UnjoinGeometry(doc, inst, c)
                    unjoined += 1
            except Exception:
                pass

# ---------- ตัดเฉียงปลายที่ตะเข้ (= Reference Plane + Cut Geometry) ----------
# วางใบมีดจิ๋ว 2 ตัวประกบระนาบดิ่งแนวตะเข้ที่จุดมุมแต่ละจุด
# → สั่งตัดเฉพาะปลายแปที่ยื่นข้ามแนว (InstanceVoidCutUtils)
miter_report = None
if MITER_CUT_AT_HIP and corner_pairs and void_sym is not None:
    with revit.Transaction("REVOTECH - Purlin Gen (ตัดเฉียงที่ตะเข้)",
                           swallow_errors=True):
        if not void_sym.IsActive:
            void_sym.Activate()
            doc.Regenerate()
        placed, cuts, cut_fail = 0, 0, 0
        pend = []
        for ea, eb, cpt, a_in, b_in in corner_pairs:
            hx, hy = a_in.X + b_in.X, a_in.Y + b_in.Y
            hl = math.sqrt(hx * hx + hy * hy)
            if hl < 1e-6:
                continue
            hx, hy = hx / hl, hy / hl        # ทิศแนวตะเข้ (แบ่งครึ่งมุมสองแกนแป)
            nx, ny = -hy, hx                 # normal ของระนาบดิ่งแนวตะเข้
            ang = math.atan2(hy, hx)
            # ใบมีด 2 ตัวประกบจุดมุม: กล่องอยู่ฝั่งตรงข้ามเนื้อแป = ฝั่งปลายที่ยื่นข้าม
            for bm, din in ((ea, a_in), (eb, b_in)):
                side = din.X * nx + din.Y * ny
                theta = ang + (math.pi if side > 0 else 0.0)
                try:
                    vi = doc.Create.NewFamilyInstance(
                        cpt, void_sym, DB.Structure.StructuralType.NonStructural)
                    DB.ElementTransformUtils.RotateElement(
                        doc, vi.Id,
                        DB.Line.CreateBound(cpt, cpt + DB.XYZ(0, 0, 1.0)), theta)
                    cm = vi.get_Parameter(
                        DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    if cm is not None and not cm.IsReadOnly:
                        cm.Set(u"REVOTECH MiterVoid - ใบมีดตัดเฉียงแป "
                               u"(ย้าย/คัดลอกไปพร้อมแปเสมอ)")
                    placed += 1
                    pend.append((vi, bm))
                except Exception:
                    cut_fail += 1
        doc.Regenerate()
        for vi, bm in pend:
            try:
                DB.InstanceVoidCutUtils.AddInstanceVoidCut(doc, bm, vi)
                cuts += 1
            except Exception:
                cut_fail += 1
        miter_report = (len(corner_pairs), placed, cuts, cut_fail)

# ---------- เก็บปลายที่ไม่มีคู่ (ชนตะเข้ราง/ขอบขั้น): ตัดดิ่งตามแนวขอบผืน ----------
edge_cuts, edge_fail = 0, 0
if MITER_CUT_AT_HIP and void_sym is not None and created_recs:
    cpts = [c[2] for c in corner_pairs]
    with revit.Transaction("REVOTECH - Purlin Gen (ตัดปลายที่ขอบผืน)",
                           swallow_errors=True):
        doc.Regenerate()
        near_r2 = mm_to_ft(100.0) ** 2
        edge_r2 = mm_to_ft(300.0) ** 2
        probe = mm_to_ft(150.0)
        pend2 = []
        for inst, fd in created_recs:
            try:
                crv = inst.Location.Curve
            except Exception:
                continue
            for p in (crv.GetEndPoint(0), crv.GetEndPoint(1)):
                paired = False
                for c in cpts:
                    if (p.X - c.X) ** 2 + (p.Y - c.Y) ** 2 < near_r2:
                        paired = True    # ปลายนี้มีใบมีดคู่มุมแล้ว
                        break
                if paired:
                    continue
                near = _nearest_edge(fd, p.X, p.Y)
                if near is None or near[0] > edge_r2:
                    continue             # ปลายไม่ได้จบที่ขอบผืน
                fx, fy = near[1], near[2]
                nx2, ny2 = -fy, fx
                if point_in_face(fd, p.X + nx2 * probe, p.Y + ny2 * probe):
                    nx2, ny2 = -nx2, -ny2
                theta = math.atan2(fy, fx)
                if (-math.sin(theta)) * nx2 + math.cos(theta) * ny2 < 0:
                    theta += math.pi     # กล่อง (+Y) อยู่ฝั่งนอกผืน
                try:
                    vi = doc.Create.NewFamilyInstance(
                        p, void_sym, DB.Structure.StructuralType.NonStructural)
                    DB.ElementTransformUtils.RotateElement(
                        doc, vi.Id,
                        DB.Line.CreateBound(p, p + DB.XYZ(0, 0, 1.0)), theta)
                    cm = vi.get_Parameter(
                        DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    if cm is not None and not cm.IsReadOnly:
                        cm.Set(u"REVOTECH MiterVoid - ใบมีดตัดปลายแปที่ขอบผืน "
                               u"(ย้าย/คัดลอกไปพร้อมแปเสมอ)")
                    pend2.append((vi, inst))
                except Exception:
                    edge_fail += 1
        doc.Regenerate()
        for vi, bm in pend2:
            try:
                DB.InstanceVoidCutUtils.AddInstanceVoidCut(doc, bm, vi)
                edge_cuts += 1
            except Exception:
                edge_fail += 1

# ---------- จอยแป↔ผืนหลังคา (= ปุ่ม RoofJoin ในตัว กันปริมาตรนับซ้ำ) ----------
# แปเป็นฝ่ายตัด (คงเนื้อเต็ม) ผืนหลังคาโดนหักตรงรอยทับ
rj_done, rj_switch, rj_fail = 0, 0, 0
if AUTO_ROOF_JOIN and inst_roofs:
    with revit.Transaction("REVOTECH - Purlin Gen (จอยแป-หลังคา)",
                           swallow_errors=True):
        for inst, rf in inst_roofs:
            try:
                if not DB.JoinGeometryUtils.AreElementsJoined(doc, inst, rf):
                    DB.JoinGeometryUtils.JoinGeometry(doc, inst, rf)
                    rj_done += 1
                if not DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, inst, rf):
                    DB.JoinGeometryUtils.SwitchJoinOrder(doc, inst, rf)
                    rj_switch += 1
            except Exception:
                rj_fail += 1

tg.Assimilate()

out.print_md(u"## Purlin Gen เสร็จแล้ว")
if DELETE_OLD and old_purlins:
    out.print_md(u"- ลบแปเดิม: **{} ตัว**".format(len(old_purlins)))
out.print_md(u"- สร้างแปใหม่: **{} ตัว** / ความยาวรวม **{:.1f} ม.**".format(
    created, total_len * 0.3048))
if ROTATE_WITH_SLOPE and _rot_sign[0] != 0.0:
    out.print_md(u"- ทิศหมุนหน้าตัด (คาลิเบรตจากตัวแรก): **{}มุมลาด**".format(
        u"+" if _rot_sign[0] > 0 else u"−"))
out.print_md(u"- ต่อปลายเข้ามุมที่ตะเข้ (trim to corner): **{} คู่**".format(snapped))
if snap_probe is not None:
    out.print_md(u"  - คู่ปลายที่ใกล้กันสุดที่สแกนเจอ: ห่างแนวราบ **{:.0f} มม.** / "
                 u"ต่างระดับ **{:.0f} มม.** (เกณฑ์จับคู่: ≤{:.0f} และ ≤{:.0f})".format(
                     snap_probe[0] * FT_TO_MM, snap_probe[1] * FT_TO_MM,
                     CORNER_SNAP_MM, CORNER_Z_TOL_MM))
out.print_md(u"- ปลด auto-join แป↔โครงอื่น: **{} คู่**".format(unjoined))
if SINK_INTO_ROOF:
    if lowered_mm:
        out.print_md(u"- ตั้งระดับ (คาลิเบรตจากเนื้อจริง): กดจมตั้งฉากผืน **{:.1f} มม.** → "
                     u"ยอดแปแนบผิวบนหลังคา{}".format(
                         lowered_mm,
                         u" + จมเพิ่ม {:.0f} มม.".format(SINK_EXTRA_MM)
                         if SINK_EXTRA_MM else u""))
    else:
        out.print_md(u"- ⚠ ตั้งระดับ: วัดเนื้อโผล่ไม่ได้ — แปยังอยู่ระดับเดิม")
if MITER_CUT_AT_HIP:
    if miter_report is not None:
        out.print_md(u"- ตัดเฉียงปลายที่ตะเข้ (miter cut): จุดมุม **{}** จุด / "
                     u"ใบมีดจิ๋ว {} ตัว / **ตัดสำเร็จ {} ปลาย** / พลาด {}".format(
                         miter_report[0], miter_report[1],
                         miter_report[2], miter_report[3]))
    if miter_msg:
        out.print_md(u"- ⚠ ตัดเฉียงไม่ได้ทำ: {}".format(miter_msg))
    else:
        out.print_md(u"- ตัดปลายไร้คู่ที่ขอบผืน (ตะเข้ราง/ขอบขั้น): **{} ปลาย** "
                     u"/ พลาด {}".format(edge_cuts, edge_fail))
if AUTO_ROOF_JOIN:
    out.print_md(u"- จอยแป↔ผืนหลังคากันปริมาตรนับซ้ำ (RoofJoin ในตัว): "
                 u"**{} คู่** / สลับให้แปเป็นฝ่ายตัด {} / พลาด {}".format(
                     rj_done, rj_switch, rj_fail))
if MATERIAL_NAME:
    if target_mat is not None:
        out.print_md(u"- ตั้งวัสดุแป: `{}`".format(target_mat.Name))
    else:
        out.print_md(u"- ⚠ หา Material ชื่อมีคำว่า `{}` ไม่เจอ — "
                     u"วัสดุที่มีในโปรเจกต์ (บางส่วน):".format(MATERIAL_NAME))
        _names = sorted(set(m.Name for m in
                            DB.FilteredElementCollector(doc).OfClass(DB.Material)))
        for _nm in _names[:30]:
            out.print_md(u"  - `{}`".format(_nm))
out.print_md(u"### รายผืน:")
for no, roof, nrows, cnt, step_mm in face_report:
    out.print_md(u"- ผืน {} ({}): {} แถว → {} ท่อน @ {:.0f} มม.".format(
        no, out.linkify(roof.Id), nrows, cnt, step_mm))
if skipped:
    out.print_md(u"### ข้ามผืน:")
    for no, roof, why in skipped:
        out.print_md(u"- ผืน {} ({}): {}".format(no, out.linkify(roof.Id), why))
if err:
    out.print_md(u"- สร้างไม่สำเร็จ: {} ท่อน".format(err))
out.print_md(u"")
out.print_md(u"ไม่พอใจผลลัพธ์ → **Ctrl+Z** ครั้งเดียวย้อนได้ทั้งหมด "
             u"(ลบ+สร้าง+ตัด+จอยอยู่ใน Transaction เดียว)")
out.print_md(u"ปุ่มเดียวจบ: สร้างแป → ตัดเฉียงตะเข้ → จอยกันปริมาตรนับซ้ำ แล้วทั้งหมด")
