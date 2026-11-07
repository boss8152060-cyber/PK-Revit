# -*- coding: utf-8 -*-
"""Rafter Gen — สร้างจันทันเรียงเต็มทุกผืนหลังคาอัตโนมัติ

ทำแบบเดียวกับขั้นตอนมือในคลิป (Set Work Plane → Beam System → Fixed Distance
→ Justification: Center → Mirror ไปทีละผืน) แต่จบในคลิกเดียวทุกผืน และไม่มี
ปัญหา "Work Plane จำระนาบผืนเก่า" เพราะคำนวณระนาบจากผืนหลังคาแต่ละผืนตรงๆ

1) หา "ผืนหลังคา" (top face) ของ Roof ทุกตัว
   - เลือก Roof ก่อนรัน = ทำเฉพาะหลังที่เลือก / ไม่เลือก = ทำทุกหลังในโมเดล
2) ลบจันทันเดิม (Structural Framing ที่ชื่อ type มีทุกคำใน TYPE_KEYWORDS)
3) แต่ละผืน: วางจันทันตามแนวลาด (เชิงชาย → สัน) ระยะ FIXED_SPACING_MM
   นับระยะจาก "มุมผืน (มุมตะเข้)" ทั้งสองข้างเข้าหากลางผืน — ผืนข้างเคียง
   นับจากมุมตะเข้เดียวกัน → จันทันวิ่งมา "หัวชนกัน" เป็นคู่ที่ตะเข้/สันพอดี
   เศษระยะเก็บช่วงกลางผืน (คู่กลางชิดกันเกิน MERGE_MM จะรวบเป็นตัวเดียว)
   ปลายตัดชนขอบผืน/แนวตะเข้พอดี (ray-cast ในขอบเขตผืนแบบเดียวกับ Purlin Gen)
   หน้าตัดแนบระนาบผืนเองโดยธรรมชาติ (แกนจันทันคือแนวลาด → local-Z ของคาน
   ชี้ตาม normal ของผืนอยู่แล้ว ไม่ต้องหมุน Cross-Section Rotation)
4) DisallowJoinAtEnd ปลายทุกตัว + กวาดปลด auto-join จันทัน↔โครงอื่น (กัน cutback)
5) AUTO_ROOF_JOIN: จอยจันทัน↔ผืนหลังคา (จันทันคงเนื้อเต็ม) กันปริมาตรนับซ้ำ
"""

import math
from System.Collections.Generic import List
from pyrevit import revit, DB, forms, script

doc = revit.doc
out = script.get_output()

# ===================== CONFIG =====================
TYPE_KEYWORDS = [u"จันทัน"]  # หา type จันทัน (ทั้งลบตัวเดิม และใช้เป็น type ตัวใหม่)

FIXED_SPACING_MM = 1000.0    # ระยะห่างจันทัน (Layout Rule: Fixed Distance)
                             # นับจากมุมตะเข้สองข้างของผืนเข้าหากลาง → หัวชนกันที่ตะเข้
MERGE_MM = 250.0             # คู่กลางผืนที่ชิดกันเกินกว่านี้ รวบเป็นตัวเดียวตรงกึ่งกลาง
SNAP_MM = 600.0              # รอบเก็บงาน: หัวคู่ที่เหลื่อมกันไม่เกินนี้ (เช่นโซนสัน/
                             # ตะเข้รางที่ผืนสองฝั่งระยะไม่เท่ากัน) ขยับเข้าหากัน
                             # ข้างละครึ่งให้ชนพอดี — 0 = ปิด
MIN_SEG_MM = 300.0           # ท่อนที่สั้นกว่านี้ไม่สร้าง (กันเศษจิ๋วใกล้จุดยอด)
MIRROR_LAYOUT = True         # จัดแถวแบบ "กึ่งกลางผืนแรก + สะท้อน (mirror) ข้าม
                             # แนวพับ" ตามวิธีทำมือของทู: ตำแหน่งแถวของผืนข้างเคียง
                             # ได้จากการ mirror ข้ามแนวตะเข้/อกไก่/ตะเข้ราง
                             # → หัวชนเป็นคู่ + ทุกช่องเท่ากันทั้งหลังโดยเรขาคณิต
                             # (ต้องมีตะเข้สัน/อกไก่ในโมเดล = กด Hip Ridge Gen ก่อน)
                             # False = นับจากมุมผืนแบบเดิม
END_SETBACK_MM = 0.0         # ปลายร่นจากขอบผืน/ตะเข้ (มม.)
VERTICAL_OFFSET_MM = 0.0     # จมเพิ่มจากระดับ "หลังจันทันเสมอผิวหลังคา" (มม.)
                             # สคริปต์วัดเนื้อจริงแล้วคาลิเบรตให้เอง — 0 = หลังจันทัน
                             # แนบผิวบนพอดี (ทูสั่ง 10 ก.ค.: ยกขึ้นให้พอดีเนื้อหลังคา
                             # แบบเดียวกับแป) / ค่าบวก = จมลงเพิ่ม เช่น 10 กันกรีดผิว
Z_JUSTIFY = u"top"           # จุดอ้างอิงหน้าตัด: top = หลังจันทันแตะแนวที่วาง
                             # (top / center / origin / bottom / asis)
DELETE_OLD = True            # ลบจันทันเดิมก่อนสร้างใหม่
AUTO_ROOF_JOIN = True        # ปิดท้ายด้วยจอยจันทัน↔ผืนหลังคา กันปริมาตรนับซ้ำ
PLUMB_CUT_AT_TOP = False     # ตัดดิ่ง (plumb cut) ปลายบนที่สัน/ตะเข้ด้วยใบมีด void
                             # — กันหน้าตัดปลายเอียงยื่นทะลุแนวพับโผล่เหนือผืนข้างเคียง
                             # ทูสั่งปิดไว้ก่อน (8 ก.ค.): ค่อยเปิดตอนใส่ตัวติดหัวจันทัน
VOID_FAM_NAME = u"REVOTECH_MiterVoidXXS"   # ใช้ family ใบมีดตัวเดียวกับ Purlin Gen

# ตัดหัวจันทันให้เข้าเฟรมกับตะเข้สัน/อกไก่ (ต้องมีตะเข้สันในโมเดลก่อน = กด HipRidge)
CUT_RAFTER_AT_HIP = True     # เก็บปลายบนจันทันให้ตะเข้สันตัดถึงหน้าพอดี (framing)
HIP_TYPE_KEYWORDS = [u"ตะเข้", u"อกไก่"]  # type ของตัวที่หัวจันทันไปชน
HIP_HEAD_TOL_MM = 350.0      # ปลายบนจันทันห่างแนวตะเข้สันไม่เกินนี้ = ถือว่าชน → ตัด
HEAD_PAIR_SNAP_MM = 600.0    # จัดหัวชนเป็นคู่ "บนแนวตะเข้/อกไก่": หัวสองฝั่งของ
                             # แนวเดียวกันที่สถานีเหลื่อมกันไม่เกินนี้ เลื่อนทางข้าง
                             # มาชนที่จุดเดียวกันบนแกน (แก้หัวเหลื่อมบนหลังคา
                             # ผืนซับซ้อน เช่นทรง L/กากบาท) — 0 = ปิด

# ตั้งวัสดุ (Structural Material) — ใส่ชื่อบางส่วนได้ / ว่าง = ใช้ค่าเดิมของ family
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
SPACING = mm_to_ft(FIXED_SPACING_MM)
MERGE = mm_to_ft(MERGE_MM)
SNAP_R = mm_to_ft(SNAP_MM)
MIN_SEG = mm_to_ft(MIN_SEG_MM)
SETBACK = mm_to_ft(END_SETBACK_MM)
VOFF = mm_to_ft(VERTICAL_OFFSET_MM)
TOL = mm_to_ft(1.0)


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


# ---------- วางแผนแถวจันทันของแต่ละผืน ----------
def plan_face(fd):
    """คืน (plan, err) — plan = dict(h, s, v0, hmin, hmax)"""
    n = fd["n"]
    nh = math.sqrt(n.X * n.X + n.Y * n.Y)
    if nh < 1e-6:
        return None, u"ผืนราบ (ไม่มีทิศลาด)"
    h = DB.XYZ(-n.Y, n.X, 0.0).Normalize()   # แนวระดับของผืน (ขนานเชิงชาย)
    s = n.CrossProduct(h)                     # แนวไต่ลาดในระนาบผืน
    if s.Z < 0:
        s = s.Negate()
    verts = []
    for pts in fd["loops"]:
        for p in pts:
            verts.append(DB.XYZ(p[0], p[1], p[2]))
    v0 = verts[0]
    hmin, hmax = None, None
    for v in verts:
        d = h.DotProduct(v)          # ค่าพิกัดโลกตามแนวระดับของผืน
        if hmin is None or d < hmin:
            hmin = d
        if hmax is None or d > hmax:
            hmax = d
    if (hmax - hmin) < MIN_SEG:
        return None, u"ผืนแคบเกิน (กว้าง {:.0f} มม.)".format(
            (hmax - hmin) * FT_TO_MM)
    minz = None
    for v in verts:
        if minz is None or v.Z < minz:
            minz = v.Z
    return {"h": h, "s": s, "v0": v0, "hmin": hmin, "hmax": hmax,
            "v0h": h.DotProduct(v0), "minz": minz}, None


def row_positions(plan):
    """ตำแหน่งแถว — นับระยะ SPACING จาก "มุมผืน" ทั้งสองข้างเข้าหากลาง
    ผืนข้างเคียงนับจากมุมตะเข้เดียวกัน → หัวชนกันที่ตะเข้/สันเป็นคู่
    เศษระยะเหลือช่วงกลางผืน (คู่กลางชิดเกิน MERGE รวบเป็นตัวเดียว)"""
    lo, hi = plan["hmin"], plan["hmax"]
    mid = (lo + hi) / 2.0
    left, right = [], []
    k = 1
    while True:
        d = lo + k * SPACING
        if d > mid + TOL:
            break
        left.append(d)
        k += 1
    k = 1
    while True:
        d = hi - k * SPACING
        if d < mid - TOL:
            break
        right.append(d)
        k += 1
    right.reverse()
    if left and right:
        gap = right[0] - left[-1]
        if abs(gap) < TOL:            # ตำแหน่งซ้ำกันพอดี (ช่วงลงตัว)
            right = right[1:]
        elif gap < MERGE:             # คู่กลางชิดกันเกิน → รวบเป็นกึ่งกลาง
            left[-1] = (left[-1] + right[0]) / 2.0
            right = right[1:]
    return left + right


def z_on_plane(fd, v0, x, y):
    n = fd["n"]
    return v0.Z - (n.X * (x - v0.X) + n.Y * (y - v0.Y)) / n.Z


def row_segments(fd, plan, d):
    """ตัดแนวจันทันที่ค่าแนวระดับ d เป็นท่อนๆ ภายในผืน คืน [(p0, p1), ...]"""
    h, s, v0 = plan["h"], plan["s"], plan["v0"]
    bx = v0.X + h.X * (d - plan["v0h"])
    by = v0.Y + h.Y * (d - plan["v0h"])
    ul = math.sqrt(s.X * s.X + s.Y * s.Y)
    if ul < 1e-9:
        return []
    ux, uy = s.X / ul, s.Y / ul
    ts = ray_hits(fd, bx, by, ux, uy)
    ts.sort()
    dedup = []
    for t in ts:
        if not dedup or t - dedup[-1] > TOL:
            dedup.append(t)
    segs = []
    for k in range(len(dedup) - 1):
        t0, t1 = dedup[k], dedup[k + 1]
        tm = (t0 + t1) / 2.0
        if not point_in_face(fd, bx + ux * tm, by + uy * tm):
            continue
        t0 += SETBACK
        t1 -= SETBACK
        if (t1 - t0) < TOL:
            continue
        x0, y0 = bx + ux * t0, by + uy * t0
        x1, y1 = bx + ux * t1, by + uy * t1
        p0 = DB.XYZ(x0, y0, z_on_plane(fd, v0, x0, y0))
        p1 = DB.XYZ(x1, y1, z_on_plane(fd, v0, x1, y1))
        if p0.DistanceTo(p1) < MIN_SEG:
            continue
        segs.append((p0, p1))
    return segs


# ---------- ตัดหัวจันทันให้เข้าเฟรมกับตะเข้สัน ----------
def cut_rafter_at_hip(rafter, hip, doc):
    """เก็บปลาย (หัว) จันทันให้ตะเข้สัน/อกไก่ตัดถึงหน้าพอดี — เข้าเฟรมเรียบสนิท

    วิธี: JoinGeometryUtils.JoinGeometry() แล้วบังคับให้ 'ตะเข้สัน (hip)' เป็น
    ฝ่ายตัด (cutting element) ด้วย SwitchJoinOrder → เนื้อจันทันตรงที่ทับตะเข้สัน
    ถูกหักออก ปลายจันทันเลยไปจบที่หน้าตะเข้สันพอดี (พฤติกรรม framing ของ Revit)

    ทำไมไม่ใช้ SolidSolidCutUtils.AddCutBetweenSolids:
      - AddCutBetweenSolids เข้มงวด (ต้องผ่าน CanElementCutElement, มักโยน
        InvalidOperationException กับคานที่ทับกันแค่บางส่วน) และให้ผลเป็น 'รูตัด'
        ไม่ใช่การเก็บปลายแบบ framing → รอยต่อไม่เนียนเท่า
      - JoinGeometry เป็นพฤติกรรม framing โดยตรง เก็บปลายถึงหน้าเมมเบอร์ +
        รวมวัสดุ/ซ่อนเส้นรอยต่อให้ + ยัง unjoin ย้อนได้

    คืน True ถ้าจอย+ตัดสำเร็จ / False ถ้าไม่แตะกันจริงหรือ Revit ปฏิเสธ
    """
    try:
        if not DB.JoinGeometryUtils.AreElementsJoined(doc, rafter, hip):
            # ถ้าสองตัวไม่ทับกันจริง JoinGeometry จะโยน exception → ถูกจับด้านล่าง
            DB.JoinGeometryUtils.JoinGeometry(doc, rafter, hip)
        # ให้ตะเข้สันเป็นฝ่ายตัด: IsCuttingElementInJoin(doc, cutter, cuttee)
        if not DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, hip, rafter):
            DB.JoinGeometryUtils.SwitchJoinOrder(doc, hip, rafter)
        return True
    except Exception:
        # ไม่ intersect / self-join / คู่ที่ Revit ปฏิเสธ → ข้ามเงียบๆ
        return False


def _pt_to_seg(p, a, b):
    """ระยะจากจุด p ถึงเซกเมนต์ a-b (ฟุต)"""
    dx, dy, dz = b.X - a.X, b.Y - a.Y, b.Z - a.Z
    L2 = dx * dx + dy * dy + dz * dz
    if L2 < 1e-12:
        return p.DistanceTo(a)
    t = ((p.X - a.X) * dx + (p.Y - a.Y) * dy + (p.Z - a.Z) * dz) / L2
    t = max(0.0, min(1.0, t))
    c = DB.XYZ(a.X + dx * t, a.Y + dy * t, a.Z + dz * t)
    return p.DistanceTo(c)


def _halfwidth_along(elem, px, py):
    """ครึ่งความกว้าง (แนวราบ) ของ solid ตะเข้สันตามทิศ (px,py) — วัดจากเนื้อจริง
    ใช้หาระยะจากแกนตะเข้ถึง 'หน้าข้าง' เพื่อวางระนาบตัดให้ทาบขอบข้างพอดี"""
    vals = []

    def walk(geo):
        for obj in geo:
            if isinstance(obj, DB.GeometryInstance):
                walk(obj.GetInstanceGeometry())
            elif isinstance(obj, DB.Solid) and obj.Volume > 1e-9:
                for e in obj.Edges:
                    for p in e.Tessellate():
                        vals.append(p.X * px + p.Y * py)
    try:
        walk(elem.get_Geometry(DB.Options()))
    except Exception:
        return None
    if not vals:
        return None
    return (max(vals) - min(vals)) / 2.0


def _closest_on_line(pa, ua, pb, ub):
    """จุดบนเส้น A (ผ่าน pa ทิศ ua) ที่ใกล้เส้น B (ผ่าน pb ทิศ ub) ที่สุด
    ua, ub เป็น unit vector — คืนจุด XYZ บนเส้น A (= จุดตัดในเชิงระยะใกล้สุด)"""
    b = ua.DotProduct(ub)
    denom = 1.0 - b * b
    if abs(denom) < 1e-9:
        return None                      # เกือบขนาน หาจุดตัดไม่ได้
    w0 = pa - pb
    d = ua.DotProduct(w0)
    e = ub.DotProduct(w0)
    sc = (b * e - d) / denom             # พารามิเตอร์บนเส้น A
    return pa + ua.Multiply(sc)


# ---------- ตั้งค่าตัวจันทัน ----------
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


def zero_extensions(inst):
    """ล้าง Start/End Extension ที่ฝังมากับ family — กันเนื้อหด/ยื่นจากปลาย"""
    for bip in (DB.BuiltInParameter.START_EXTENSION,
                DB.BuiltInParameter.END_EXTENSION):
        try:
            pr = inst.get_Parameter(bip)
            if pr is not None and not pr.IsReadOnly:
                pr.Set(0.0)
        except Exception:
            pass


def set_usage_joist(inst):
    try:
        pu = inst.get_Parameter(DB.BuiltInParameter.INSTANCE_STRUCT_USAGE_PARAM)
        if pu is not None and not pu.IsReadOnly:
            pu.Set(int(DB.Structure.StructuralInstanceUsage.Joist))
    except Exception:
        pass


def set_material(inst):
    if target_mat is None:
        return
    try:
        pr = inst.get_Parameter(DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM)
        if pr is not None and not pr.IsReadOnly:
            pr.Set(target_mat.Id)
    except Exception:
        pass


# ---------- รอบเก็บงาน: จัดหัวจันทันที่เกือบชนกันให้ชนพอดี ----------
def _shift_line(inst, vx, vy):
    """เลื่อนแนวจันทันทางข้าง (ตามแนวระดับของผืน — z ไม่เปลี่ยน)"""
    crv = inst.Location.Curve
    e0, e1 = crv.GetEndPoint(0), crv.GetEndPoint(1)
    v = DB.XYZ(vx, vy, 0.0)
    inst.Location.Curve = DB.Line.CreateBound(e0 + v, e1 + v)


def _trim_to(inst, endi, tx, ty, fd, plan):
    """เลื่อนแนวให้ผ่านจุดเป้า แล้วเล็ม/ยืดปลาย endi ไปจบที่จุดเป้าพอดี"""
    crv = inst.Location.Curve
    e0, e1 = crv.GetEndPoint(0), crv.GetEndPoint(1)
    p = e0 if endi == 0 else e1
    q = e1 if endi == 0 else e0
    dx, dy = e1.X - e0.X, e1.Y - e0.Y
    dl = math.sqrt(dx * dx + dy * dy)
    if dl < 1e-9:
        return
    ux, uy = dx / dl, dy / dl
    wx, wy = tx - p.X, ty - p.Y
    ax = wx * ux + wy * uy
    lx, ly = wx - ax * ux, wy - ax * uy      # ส่วนเลื่อนข้าง (ตามแนวระดับ)
    q2 = DB.XYZ(q.X + lx, q.Y + ly, q.Z)
    tz = z_on_plane(fd, plan["v0"], tx, ty)
    t3 = DB.XYZ(tx, ty, tz)
    if endi == 0:
        inst.Location.Curve = DB.Line.CreateBound(t3, q2)
    else:
        inst.Location.Curve = DB.Line.CreateBound(q2, t3)


def _trim_to_keepz(inst, endi, tx, ty):
    """เหมือน _trim_to แต่คิด z จาก "แนวแกนเดิมของจันทัน" ไม่ใช่ระนาบผืน
    — ใช้หลังขั้นตั้งระดับ (จันทันถูกกดจมใต้ระนาบแล้ว ห้ามดีดกลับขึ้นผิว)"""
    crv = inst.Location.Curve
    e0, e1 = crv.GetEndPoint(0), crv.GetEndPoint(1)
    p = e0 if endi == 0 else e1
    q = e1 if endi == 0 else e0
    dx, dy, dz = p.X - q.X, p.Y - q.Y, p.Z - q.Z
    dl2 = dx * dx + dy * dy
    if dl2 < 1e-12:
        return
    wx, wy = tx - p.X, ty - p.Y
    ax = (wx * dx + wy * dy) / dl2           # สัดส่วนเลื่อนตามแกน (plan)
    lx, ly = wx - ax * dx, wy - ax * dy      # ส่วนเลื่อนข้าง (z ไม่เปลี่ยน)
    q2 = DB.XYZ(q.X + lx, q.Y + ly, q.Z)
    t3 = DB.XYZ(tx, ty, p.Z + ax * dz)       # z ไต่ตามแนวแกนเดิม
    if endi == 0:
        inst.Location.Curve = DB.Line.CreateBound(t3, q2)
    else:
        inst.Location.Curve = DB.Line.CreateBound(q2, t3)


def snap_heads(recs):
    """จับคู่หัวจันทัน (ต่างตัว) ที่ห่างกันไม่เกิน SNAP_MM แล้วจัดให้ชนพอดี
    - คู่ขนานสวนทาง (ชนที่สัน): เลื่อนเข้าแนวเดียวกันข้างละครึ่ง
    - คู่ตั้งฉาก (ชนที่ตะเข้/ตะเข้ราง): เล็มปลายทั้งคู่ไปจบจุดกึ่งกลางร่วม
    ปลายฝั่งเชิงชาย (z ต่ำสุดของผืน) ไม่ยุ่ง — คืนจำนวนคู่ที่จัดสำเร็จ"""
    ztol = mm_to_ft(300.0)
    ends = []
    for ri in range(len(recs)):
        inst, fd, plan = recs[ri]
        try:
            crv = inst.Location.Curve
        except Exception:
            continue
        e0, e1 = crv.GetEndPoint(0), crv.GetEndPoint(1)
        dx, dy = e1.X - e0.X, e1.Y - e0.Y
        dl = math.sqrt(dx * dx + dy * dy)
        if dl < 1e-9:
            continue
        ux, uy = dx / dl, dy / dl
        for endi, p in ((0, e0), (1, e1)):
            if p.Z < plan["minz"] + mm_to_ft(100.0):
                continue                      # ปลายชายคา ไม่จับคู่
            ends.append((ri, endi, p, ux, uy))
    cand = []
    m = len(ends)
    for i in range(m):
        ri, ei, pi, uxi, uyi = ends[i]
        for j in range(i + 1, m):
            rj, ej, pj, uxj, uyj = ends[j]
            if rj == ri:
                continue
            dxy = math.sqrt((pi.X - pj.X) ** 2 + (pi.Y - pj.Y) ** 2)
            if dxy > SNAP_R or dxy < mm_to_ft(5.0):
                continue
            if abs(pi.Z - pj.Z) > ztol:
                continue
            cand.append((dxy, i, j))
    cand.sort()
    used = set()
    done = 0
    for dxy, i, j in cand:
        if i in used or j in used:
            continue
        ri, ei, pi, uxi, uyi = ends[i]
        rj, ej, pj, uxj, uyj = ends[j]
        insti, fdi, plani = recs[ri]
        instj, fdj, planj = recs[rj]
        dot = uxi * uxj + uyi * uyj
        try:
            if abs(dot) > 0.9:
                # ชนที่สัน: เลื่อนเข้าแนวเดียวกันข้างละครึ่ง
                wx, wy = pj.X - pi.X, pj.Y - pi.Y
                ax = wx * uxi + wy * uyi
                lx, ly = wx - ax * uxi, wy - ax * uyi
                _shift_line(insti, lx / 2.0, ly / 2.0)
                _shift_line(instj, -lx / 2.0, -ly / 2.0)
            elif abs(dot) < 0.3:
                # ชนที่ตะเข้/ตะเข้ราง: เล็มไปจบ "จุดตัดของสองแนว" (แบบคำสั่ง TR)
                # — จุดตัดอยู่บนแนวพับหลังคาพอดี ไม่ทะลุผืนข้างเคียง
                denom = uxi * uyj - uyi * uxj
                if abs(denom) > 0.2:
                    t = ((pj.X - pi.X) * uyj
                         - (pj.Y - pi.Y) * uxj) / denom
                    tx, ty = pi.X + uxi * t, pi.Y + uyi * t
                    far_i = math.sqrt((tx - pi.X) ** 2 + (ty - pi.Y) ** 2)
                    far_j = math.sqrt((tx - pj.X) ** 2 + (ty - pj.Y) ** 2)
                    if far_i > SNAP_R or far_j > SNAP_R:
                        tx = (pi.X + pj.X) / 2.0   # จุดตัดไกลผิดปกติ → ใช้กึ่งกลาง
                        ty = (pi.Y + pj.Y) / 2.0
                else:
                    tx, ty = (pi.X + pj.X) / 2.0, (pi.Y + pj.Y) / 2.0
                # จุดเป้าต้องอยู่ในผืนของฝ่ายใดฝ่ายหนึ่งจริง (จุดชนบนแนวพับจะ
                # อยู่ขอบผืนพอดี เลยขอแค่ฝั่งเดียวผ่าน) — กันยืดหัวทะลุแนวพับ
                # ขึ้นกลางอากาศที่โซนยอดแหลม
                if not (point_in_face(fdi, tx, ty)
                        or point_in_face(fdj, tx, ty)):
                    tx = (pi.X + pj.X) / 2.0
                    ty = (pi.Y + pj.Y) / 2.0
                    if not (point_in_face(fdi, tx, ty)
                            or point_in_face(fdj, tx, ty)):
                        continue
                _trim_to(insti, ei, tx, ty, fdi, plani)
                _trim_to(instj, ej, tx, ty, fdj, planj)
            else:
                continue
            used.add(i)
            used.add(j)
            done += 1
        except Exception:
            pass
    return done


# ---------- ใบมีดตัดดิ่ง (ใช้ family เดียวกับ Purlin Gen) ----------
def find_void_symbol():
    for f in DB.FilteredElementCollector(doc).OfClass(DB.Family):
        if ename(f) == VOID_FAM_NAME:
            for sid in f.GetFamilySymbolIds():
                return doc.GetElement(sid)
    return None


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


# ---------- MIRROR_LAYOUT: จัดแถวแบบ "กึ่งกลาง + สะท้อนข้ามแนวพับ" ----------
# (= วิธีทำมือของทู: วางจันทันผืนที่ง่ายสุดยึดกึ่งกลาง แล้ว mirror ข้ามตะเข้
#    ไปผืนข้างเคียงต่อกันเป็นทอดๆ — หัวชนกันเป็นคู่ + ทุกช่องเท่ากันโดยเรขาคณิต
#    เพราะการสะท้อนข้ามระนาบตะเข้คงระยะช่องไว้ และจุดบนแนวตะเข้ไม่ขยับ)
def _reflect_pt(x, y, ax, ay, ux, uy):
    """สะท้อนจุด (x,y) ข้ามเส้น plan ที่ผ่าน (ax,ay) ทิศ (ux,uy) — unit"""
    wx, wy = x - ax, y - ay
    al = wx * ux + wy * uy
    px, py = wx - al * ux, wy - al * uy
    return ax + al * ux - px, ay + al * uy - py


def row_positions_phase(plan, phase):
    """ตำแหน่งแถวแบบกริดเฟสเดียว: h = phase + k*SPACING คลุมทั้งผืน
    (ช่องเท่ากันหมด — เศษท่อนสั้นใกล้มุมโดน MIN_SEG กรองเองใน row_segments)"""
    lo, hi = plan["hmin"], plan["hmax"]
    out = []
    k = int(math.floor((lo - phase) / SPACING)) + 1
    while True:
        d = phase + k * SPACING
        if d > hi - TOL:
            break
        if d > lo + TOL:
            out.append(d)
        k += 1
    return out


def compute_phases(faces, plans, hips):
    """เฟสแถว (ค่าอ้างอิงบนแกน h) รายผืน — เริ่มผืนกว้างสุดยึดกึ่งกลางผืน
    แล้วสะท้อนตำแหน่งแถวข้ามแนวตะเข้/อกไก่/ตะเข้รางไปผืนข้างเคียง (BFS)
    คืน dict {face_idx: phase}"""
    ztol = mm_to_ft(400.0)
    etol2 = mm_to_ft(400.0) ** 2
    # ผืนไหนติดแนวพับเส้นไหน: เช็คจุดกลางแนวพับ แนบระนาบผืน + ติดตัวผืนใน plan
    hip_faces = {}
    for hi in range(len(hips)):
        he, ha, hb = hips[hi]
        mx = (ha.X + hb.X) / 2.0
        my = (ha.Y + hb.Y) / 2.0
        mz = (ha.Z + hb.Z) / 2.0
        for fi in range(len(faces)):
            plan = plans[fi]
            if plan is None:
                continue
            fd = faces[fi]
            try:
                if abs(z_on_plane(fd, plan["v0"], mx, my) - mz) > ztol:
                    continue
            except Exception:
                continue
            if not point_in_face(fd, mx, my):
                near = _nearest_edge(fd, mx, my)
                if near is None or near[0] > etol2:
                    continue
            hip_faces.setdefault(hi, []).append(fi)
    # adjacency ผืน↔ผืน ผ่านแนวพับ
    neigh = {}
    for hi in hip_faces:
        fl = hip_faces[hi]
        for a in fl:
            for b in fl:
                if a != b:
                    neigh.setdefault(a, []).append((hi, b))
    phases = {}
    order = sorted([fi for fi in range(len(faces)) if plans[fi] is not None],
                   key=lambda fi: -(plans[fi]["hmax"] - plans[fi]["hmin"]))
    for seed in order:
        if seed in phases:
            continue
        sp = plans[seed]
        phases[seed] = (sp["hmin"] + sp["hmax"]) / 2.0   # ยึดกึ่งกลางผืนแรก
        queue = [seed]
        while queue:
            a = queue.pop(0)
            pa = plans[a]
            # จุดฐานของแถวอ้างอิงผืน a + ทิศแถว (plan ของแนวไต่ลาด)
            bx = pa["v0"].X + pa["h"].X * (phases[a] - pa["v0h"])
            by = pa["v0"].Y + pa["h"].Y * (phases[a] - pa["v0h"])
            sl = math.sqrt(pa["s"].X ** 2 + pa["s"].Y ** 2)
            if sl < 1e-9:
                continue
            sux, suy = pa["s"].X / sl, pa["s"].Y / sl
            for hi, b in neigh.get(a, []):
                if b in phases:
                    continue
                he, ha, hb = hips[hi]
                hux, huy = hb.X - ha.X, hb.Y - ha.Y
                hl = math.sqrt(hux * hux + huy * huy)
                if hl < 1e-9:
                    continue
                hux, huy = hux / hl, huy / hl
                # สะท้อนแถวอ้างอิงของ a ข้ามแนวพับ → ต้องได้แนวขนานแถวของ b
                # (ถ้าลาดสองผืนไม่สมมาตรจะไม่ขนาน — ข้าม ให้ b ตั้งเฟสเองทีหลัง)
                dd = sux * hux + suy * huy
                rdx, rdy = 2 * dd * hux - sux, 2 * dd * huy - suy
                pb = plans[b]
                if abs(rdx * pb["h"].X + rdy * pb["h"].Y) > 0.15:
                    continue
                rx, ry = _reflect_pt(bx, by, ha.X, ha.Y, hux, huy)
                phases[b] = pb["h"].X * rx + pb["h"].Y * ry
                queue.append(b)
    return phases


# ---------- คาลิเบรตระดับ: วัดว่าเนื้อจันทันโผล่เหนือระนาบผืนเท่าไหร่ ----------
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

all_framing = list(DB.FilteredElementCollector(doc)
                   .OfCategory(DB.BuiltInCategory.OST_StructuralFraming)
                   .WhereElementIsNotElementType()
                   .ToElements())
old_rafters = [e for e in all_framing if match_keywords(type_name(e))]

# type จันทันที่จะใช้สร้าง
sym = None
if old_rafters:
    sym = doc.GetElement(old_rafters[0].GetTypeId())
if sym is None:
    for t in DB.FilteredElementCollector(doc) \
              .OfCategory(DB.BuiltInCategory.OST_StructuralFraming) \
              .WhereElementIsElementType():
        if match_keywords(ename(t)):
            sym = t
            break
if sym is None:
    names = sorted(set(type_name(e) for e in all_framing if type_name(e)))
    out.print_md(u"## หา type จันทัน (ชื่อมีคำว่า `{}`) ไม่เจอ".format(
        u", ".join(TYPE_KEYWORDS)))
    out.print_md(u"### ชื่อ type framing ที่มีในโปรเจกต์:")
    for nm in names[:40]:
        out.print_md(u"- `{}`".format(nm))
    forms.alert(u"หา type จันทันไม่เจอ — โหลด family จันทันเข้าโปรเจกต์ก่อน "
                u"(ชื่อ type ต้องมีคำว่า \"จันทัน\")", exitscript=True)

# level สำรอง
fb_level = None
if old_rafters:
    try:
        p = old_rafters[0].get_Parameter(
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


target_mat = None
if MATERIAL_NAME:
    _mlow = MATERIAL_NAME.lower()
    for _m in DB.FilteredElementCollector(doc).OfClass(DB.Material):
        if _mlow in _m.Name.lower():
            target_mat = _m
            break


created, err = 0, 0
total_len = 0.0
skipped = []
face_report = []
created_insts = []
created_recs = []
inst_roofs = []
unjoined = 0

# เตรียมใบมีด void (family เดียวกับ Purlin Gen — โหลดจากโฟลเดอร์ปุ่มถ้ายังไม่มี)
# ใช้ทั้ง plumb cut และตัดหัวเข้าตะเข้สัน (CUT_RAFTER_AT_HIP)
void_sym = None
plumb_msg = None
if PLUMB_CUT_AT_TOP or CUT_RAFTER_AT_HIP:
    void_sym = find_void_symbol()
    if void_sym is None:
        _here = os.path.dirname(__file__)
        for _rfa in (os.path.join(_here, VOID_FAM_NAME + u".rfa"),
                     os.path.join(os.path.dirname(_here),
                                  u"PurlinGen.pushbutton",
                                  VOID_FAM_NAME + u".rfa")):
            if os.path.isfile(_rfa):
                try:
                    with revit.Transaction("REVOTECH - โหลด MiterVoid"):
                        doc.LoadFamily(_rfa)
                except Exception as ex:
                    plumb_msg = u"โหลด family ใบมีดไม่สำเร็จ: {}".format(ex)
                break
        void_sym = find_void_symbol()
    if void_sym is None and plumb_msg is None:
        plumb_msg = (u"หา family {} ไม่เจอ — กดปุ่ม Purlin Gen หนึ่งครั้ง"
                     u"เพื่อสร้าง family ใบมีดก่อน".format(VOID_FAM_NAME))

tg = DB.TransactionGroup(doc, "REVOTECH - Rafter Gen")
tg.Start()

# ลบจันทันเดิม "ก่อนอ่านผืนหลังคา" — จันทันรุ่นเสมอผิวที่จอยไว้จะกรีดผิวเป็นร่อง
# ถ้าอ่านผืนทั้งที่ยังมีร่อง ขอบผืนจะยับเป็นช่อง ทำให้ ray-cast วางแนวเพี้ยน
with revit.Transaction("REVOTECH - Rafter Gen (ลบของเดิม)",
                       swallow_errors=True):
    if DELETE_OLD and old_rafters:
        doc.Delete(List[DB.ElementId]([e.Id for e in old_rafters]))
    # ลบใบมีดของจันทันรอบก่อน (เฉพาะที่มาร์ก [จันทัน] — ไม่แตะใบมีดของแป)
    stale = []
    for gm in DB.FilteredElementCollector(doc) \
               .OfCategory(DB.BuiltInCategory.OST_GenericModel) \
               .WhereElementIsNotElementType():
        try:
            if not gm.Symbol.Family.Name.startswith(u"REVOTECH_MiterVoid"):
                continue
            cm = gm.get_Parameter(
                DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if cm is not None and u"[จันทัน]" in (cm.AsString() or u""):
                stale.append(gm.Id)
        except Exception:
            pass
    if stale:
        doc.Delete(List[DB.ElementId](stale))

faces = collect_roof_faces(roofs)
if not faces:
    tg.RollBack()
    forms.alert(u"หาผืนหลังคา (top face) ไม่เจอ", exitscript=True)
out.print_md(u"พบผืนหลังคา **{} ผืน** / จันทันเดิม {} ตัว / type: `{}`".format(
    len(faces), len(old_rafters), ename(sym)))

# เก็บเส้นตะเข้สัน/อกไก่/ตะเข้รางจากโมเดล (ใช้ทั้ง MIRROR_LAYOUT และตัดหัว)
hips = []
ridge_ids = set()   # id ของอกไก่ — ใช้จัดหัวชนได้ แต่ห้ามเล็ม/ตัดหัวใส่
if CUT_RAFTER_AT_HIP or MIRROR_LAYOUT:
    for e in DB.FilteredElementCollector(doc) \
              .OfCategory(DB.BuiltInCategory.OST_StructuralFraming) \
              .WhereElementIsNotElementType():
        tn = type_name(e).lower()
        if any(kw.lower() in tn for kw in HIP_TYPE_KEYWORDS):
            try:
                crv = e.Location.Curve
                hips.append((e, crv.GetEndPoint(0), crv.GetEndPoint(1)))
                # อกไก่ = แค่แกนอ้างอิงจัดหัวชน — "ห้ามเล็ม/ตัดหัวจันทันใส่"
                # (อกไก่จมอยู่ใต้จันทันคอยรับ ไม่ใช่ตัวขวาง — หัวจันทันที่สัน
                # ต้องวิ่งมาชนกันเอง)
                if u"อกไก่" in tn:
                    ridge_ids.add(e.Id)
            except Exception:
                pass
hips_found = len(hips)

# วางแผนทุกผืนก่อน แล้วคำนวณ "เฟสแถว" แบบสะท้อนข้ามแนวพับ (วิธี mirror ของทู)
plans_all = []
for fd in faces:
    plan, why = plan_face(fd)
    plans_all.append((plan, why))
phases = {}
if MIRROR_LAYOUT and hips:
    try:
        phases = compute_phases(faces, [p for p, w in plans_all], hips)
    except Exception:
        phases = {}

with revit.Transaction("REVOTECH - Rafter Gen (สร้าง)", swallow_errors=True):
    if not sym.IsActive:
        sym.Activate()
        doc.Regenerate()

    for idx, fd in enumerate(faces):
        plan, why = plans_all[idx]
        if plan is None:
            skipped.append((idx + 1, fd["roof"], why))
            continue
        lvl = level_for(fd["roof"])
        if idx in phases:
            rows = row_positions_phase(plan, phases[idx])
            if not rows:                 # ผืนแคบจนกริดเฟสไม่ตกลงมาเลย
                rows = [(plan["hmin"] + plan["hmax"]) / 2.0]
        else:
            rows = row_positions(plan)
        cnt_face = 0
        for d in rows:
            for p0, p1 in row_segments(fd, plan, d):
                try:
                    line = DB.Line.CreateBound(p0, p1)
                    inst = doc.Create.NewFamilyInstance(
                        line, sym, lvl, DB.Structure.StructuralType.Beam)
                    try:
                        DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(inst, 0)
                        DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(inst, 1)
                    except Exception:
                        pass
                    set_zjust(inst)
                    set_usage_joist(inst)
                    set_material(inst)
                    zero_extensions(inst)
                    created_insts.append(inst)
                    created_recs.append((inst, fd, plan))
                    inst_roofs.append((inst, fd["roof"]))
                    created += 1
                    cnt_face += 1
                    total_len += p0.DistanceTo(p1)
                except Exception:
                    err += 1
        face_report.append((idx + 1, fd["roof"], len(rows), cnt_face))

# รอบเก็บงาน: จัดหัวคู่ที่ยังเหลื่อมกัน (โซนสัน/ตะเข้รางที่ผืนสองฝั่งไม่เท่ากัน)
snap_done = 0
if SNAP_MM > 0 and created_recs:
    with revit.Transaction("REVOTECH - Rafter Gen (จัดหัวชน)",
                           swallow_errors=True):
        snap_done = snap_heads(created_recs)

# ตั้งระดับ: วัดของจริงแล้วกดทั้งชุดลง ให้หลังจันทันแนบระนาบผืนพอดี (+จมเพิ่มตาม config)
lowered_mm = 0.0
if created_recs:
    with revit.Transaction("REVOTECH - Rafter Gen (ตั้งระดับ)",
                           swallow_errors=True):
        doc.Regenerate()
        probe, pfd = None, None
        best_len = 0.0
        for _i2, _f2, _p2 in created_recs:      # ใช้ตัวยาวสุดเป็นตัววัด
            try:
                _l = _i2.Location.Curve.Length
            except Exception:
                continue
            if _l > best_len:
                best_len = _l
                probe, pfd = _i2, _f2
        dz = VOFF
        if probe is not None:
            try:
                dmax = _solid_max_above(
                    probe.get_Geometry(DB.Options()), pfd["n"],
                    pfd["loops"][0][0][0], pfd["loops"][0][0][1],
                    pfd["loops"][0][0][2])
            except Exception:
                dmax = None
            if dmax is not None and dmax > mm_to_ft(1.0):
                dz += dmax / max(pfd["n"].Z, 0.05)   # แปลงระยะ normal → แนวดิ่ง
        if dz > mm_to_ft(0.5):
            mv = DB.XYZ(0.0, 0.0, -dz)
            for _i2, _f2, _p2 in created_recs:
                try:
                    DB.ElementTransformUtils.MoveElement(doc, _i2.Id, mv)
                except Exception:
                    pass
            lowered_mm = dz * FT_TO_MM

# ตัดดิ่ง (plumb cut) ปลายบน: ใบมีดแนบระนาบดิ่งของขอบผืน (สัน/ตะเข้/ราง) ที่ปลายจบ
# ตัดเนื้อที่หน้าตัดเอียงยื่นข้ามแนวพับทิ้ง — เนื้อจันทันไม่โผล่เหนือผืนข้างเคียง
plumb_cuts, plumb_fail = 0, 0
if PLUMB_CUT_AT_TOP and void_sym is not None and created_recs:
    with revit.Transaction("REVOTECH - Rafter Gen (ตัดดิ่งปลายบน)",
                           swallow_errors=True):
        if not void_sym.IsActive:
            void_sym.Activate()
        doc.Regenerate()
        pend = []
        for inst, fd, plan in created_recs:
            try:
                crv = inst.Location.Curve
            except Exception:
                continue
            e0, e1 = crv.GetEndPoint(0), crv.GetEndPoint(1)
            top = e0 if e0.Z >= e1.Z else e1
            if top.Z < plan["minz"] + mm_to_ft(100.0):
                continue                       # จบที่ชายคา ไม่ต้องตัด
            near = _nearest_edge(fd, top.X, top.Y)
            if near is None or near[0] > mm_to_ft(300.0) ** 2:
                continue                       # ปลายไม่ได้จบที่ขอบผืน
            fx, fy = near[1], near[2]          # ทิศแนวพับ (ขอบผืน)
            nx, ny = -fy, fx
            probe = mm_to_ft(150.0)
            if point_in_face(fd, top.X + nx * probe, top.Y + ny * probe):
                nx, ny = -nx, -ny              # ให้ n ชี้ "ออกนอกผืน" เสมอ
            theta = math.atan2(fy, fx)
            if (-math.sin(theta)) * nx + math.cos(theta) * ny < 0:
                theta += math.pi               # ให้กล่อง (+Y) อยู่ฝั่งนอกผืน
            try:
                vi = doc.Create.NewFamilyInstance(
                    top, void_sym, DB.Structure.StructuralType.NonStructural)
                DB.ElementTransformUtils.RotateElement(
                    doc, vi.Id,
                    DB.Line.CreateBound(top, top + DB.XYZ(0, 0, 1.0)), theta)
                cm = vi.get_Parameter(
                    DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                if cm is not None and not cm.IsReadOnly:
                    cm.Set(u"REVOTECH MiterVoid [จันทัน] - ใบมีดตัดดิ่งปลายบน "
                           u"(ย้าย/คัดลอกไปพร้อมจันทันเสมอ)")
                pend.append((vi, inst))
            except Exception:
                plumb_fail += 1
        doc.Regenerate()
        for vi, bm in pend:
            try:
                DB.InstanceVoidCutUtils.AddInstanceVoidCut(doc, bm, vi)
                plumb_cuts += 1
            except Exception:
                plumb_fail += 1

# กวาดปลด auto-join จันทัน↔โครงอื่น (Revit จอยเองตอนปิด Transaction แรก)
with revit.Transaction("REVOTECH - Rafter Gen (ปลด join)", swallow_errors=True):
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

# ตัดหัวจันทันให้เข้าเฟรมกับตะเข้สัน/อกไก่ (ต้องมีตะเข้สันในโมเดลก่อน)
# ทำหลังปลด auto-join แล้ว (ไม่งั้นการจอยที่เราตั้งใจจะโดนปลดทิ้ง)
hip_cut_done, pair_done = 0, 0
if CUT_RAFTER_AT_HIP:
    # ใช้ hips ที่เก็บไว้ตอนต้น (ก่อนสร้าง — ใช้ร่วมกับ MIRROR_LAYOUT)
    if hips:
        tolh = mm_to_ft(HIP_HEAD_TOL_MM)

        # (0) จัดหัวชนเป็นคู่ "บนแนวตะเข้/อกไก่": บนหลังคาผืนซับซ้อน (L/กากบาท)
        #     มุมอ้างอิงการนับระยะของสองผืนข้างเคียงไม่ใช่จุดเดียวกัน → หัวเหลื่อม
        #     แก้โดยอิงเส้นตะเข้จริง: หัวที่จบใกล้แนวเดียวกันจากคนละฝั่ง สถานี
        #     เหลื่อมไม่เกิน HEAD_PAIR_SNAP_MM → เลื่อนทางข้าง (ทิศเดิม) มาชนกัน
        #     ที่จุดกึ่งกลางสถานีบนแกน — แม่นกว่า snap กลางอากาศเพราะรู้จักแนวพับ
        if HEAD_PAIR_SNAP_MM > 0:
            psnap = mm_to_ft(HEAD_PAIR_SNAP_MM)
            sttol = mm_to_ft(200.0)
            with revit.Transaction("REVOTECH - Rafter Gen (จัดหัวชนบนแนวพับ)",
                                   swallow_errors=True):
                groups = {}   # hip_idx -> {+1: [...], -1: [...]} ตามฝั่งของแกน
                for ridx in range(len(created_recs)):
                    inst, fd, plan = created_recs[ridx]
                    try:
                        crv = inst.Location.Curve
                    except Exception:
                        continue
                    e0, e1 = crv.GetEndPoint(0), crv.GetEndPoint(1)
                    for endi, p, q in ((0, e0, e1), (1, e1, e0)):
                        if p.Z < plan["minz"] + mm_to_ft(100.0):
                            continue              # ปลายชายคา ไม่ยุ่ง
                        best_hi, best_d = -1, tolh
                        for hi in range(len(hips)):
                            dd = _pt_to_seg(p, hips[hi][1], hips[hi][2])
                            if dd < best_d:
                                best_d = dd
                                best_hi = hi
                        if best_hi < 0:
                            continue
                        he, ha, hb = hips[best_hi]
                        hux, huy = hb.X - ha.X, hb.Y - ha.Y
                        hl = math.sqrt(hux * hux + huy * huy)
                        if hl < 1e-9:
                            continue
                        hux, huy = hux / hl, huy / hl
                        st = hux * (p.X - ha.X) + huy * (p.Y - ha.Y)
                        if st < -sttol or st > hl + sttol:
                            continue              # เลยช่วงตัวตะเข้จริง (จับผิดเส้น)
                        # ฝั่งของ "ตัวจันทัน" เทียบแกน (ดูจากปลายอีกข้าง)
                        ppx, ppy = -huy, hux
                        sd = ppx * (q.X - ha.X) + ppy * (q.Y - ha.Y)
                        if abs(sd) < mm_to_ft(30.0):
                            continue              # ก้ำกึ่ง ระบุฝั่งไม่ได้
                        side = 1 if sd > 0 else -1
                        groups.setdefault(best_hi, {1: [], -1: []})[side] \
                              .append((st, ridx, endi))
                for hi in groups:
                    he, ha, hb = hips[hi]
                    hux, huy = hb.X - ha.X, hb.Y - ha.Y
                    hl = math.sqrt(hux * hux + huy * huy)
                    if hl < 1e-9:
                        continue
                    hux, huy = hux / hl, huy / hl
                    la = sorted(groups[hi][1], key=lambda r: r[0])
                    lb = sorted(groups[hi][-1], key=lambda r: r[0])
                    cand2 = []
                    for ia in range(len(la)):
                        for ib in range(len(lb)):
                            dt = abs(la[ia][0] - lb[ib][0])
                            if dt < psnap:
                                cand2.append((dt, ia, ib))
                    cand2.sort()
                    ua, ub = set(), set()
                    for dt, ia, ib in cand2:
                        if ia in ua or ib in ub:
                            continue
                        ua.add(ia)
                        ub.add(ib)
                        tm = (la[ia][0] + lb[ib][0]) / 2.0
                        tx, ty = ha.X + hux * tm, ha.Y + huy * tm
                        try:
                            _trim_to_keepz(created_recs[la[ia][1]][0],
                                           la[ia][2], tx, ty)
                            _trim_to_keepz(created_recs[lb[ib][1]][0],
                                           lb[ib][2], tx, ty)
                            pair_done += 1
                        except Exception:
                            pass

        # (1) เล็มหัวจันทันมาจบที่แนวแกนตะเข้สัน (ตัด overshoot ที่พุ่งเลยทิ้ง)
        with revit.Transaction("REVOTECH - Rafter Gen (เล็มหัวถึงตะเข้สัน)",
                               swallow_errors=True):
            for inst, fd, plan in created_recs:
                try:
                    crv = inst.Location.Curve
                except Exception:
                    continue
                e0, e1 = crv.GetEndPoint(0), crv.GetEndPoint(1)
                if e0.Z >= e1.Z:
                    top, bot = e0, e1
                else:
                    top, bot = e1, e0
                # หาตะเข้สันที่หัวชิดที่สุด (ข้ามอกไก่ — มันจมอยู่ใต้จันทัน
                # เล็มหาแกนมันจะดึงหัวถอยร่นจากสัน ทำหัวคู่ไม่ชนกัน)
                best, best_d = None, tolh
                for he, ha, hb in hips:
                    if he.Id == inst.Id or he.Id in ridge_ids:
                        continue
                    dd = _pt_to_seg(top, ha, hb)
                    if dd < best_d:
                        best_d = dd
                        best = (he, ha, hb)
                if best is None:
                    continue
                he, ha, hb = best
                u = (top - bot).Normalize()          # ทิศจันทัน (ล่าง→หัว)
                hv = (hb - ha)
                hvlen = hv.GetLength()
                if hvlen < 1e-9:
                    continue
                hv = hv.Normalize()
                cross = _closest_on_line(bot, u, ha, hv)   # จุดที่แกนจันทันพบแกนตะเข้
                if cross is None:
                    continue
                # จุดตัดต้องอยู่ "ในช่วงตัวตะเข้จริง" — _closest_on_line คิดแบบ
                # เส้นตรงอนันต์ ที่จุดรวมยอด (ตะเข้หลายเส้นชุมกัน) จับผิดเส้นแล้ว
                # จะยืดหัวเลยยอดขึ้นกลางอากาศ
                tst = hv.DotProduct(cross - ha)
                if tst < -mm_to_ft(200.0) or tst > hvlen + mm_to_ft(200.0):
                    continue
                new_len = u.DotProduct(cross - bot)
                old_len = bot.DistanceTo(top)
                # กันเพี้ยน: หัวใหม่ต้องอยู่หน้าตัวจันทัน และไม่สั้น/ยาวผิดปกติ
                if new_len < old_len * 0.4 or new_len > old_len + tolh:
                    continue
                try:
                    inst.Location.Curve = DB.Line.CreateBound(bot, cross)
                except Exception:
                    pass
        # (การ commit ทรานแซกชันข้างบน regenerate ให้เองแล้ว — อย่าเรียก
        #  doc.Regenerate() นอก transaction เด็ดขาด Revit จะโยน error)

        # (2) ตัดหัวจันทันด้วย "ระนาบหน้าข้างตะเข้สัน" = เทียบเท่า Ref Plane + Cut
        #     (คลิป): ระนาบตัดทิ้งทุกอย่างที่เลยหน้าข้างตะเข้ → ปลายจันทันจบเรียบ
        #     ที่หน้าข้างตะเข้พอดี รวมทั้ง overshoot ที่พุ่งทะลุอีกฝั่ง (Join ทำไม่ได้)
        if void_sym is not None:
            # เตรียมเรขาคณิตตะเข้แต่ละเส้น: ทิศแกน(plan)+แนวหนา+ครึ่งกว้าง(วัดจริง)
            # — ข้ามอกไก่ (ใบมีดตัดแนบหน้าอกไก่จะเฉือนหัวถอยข้างละครึ่งกว้าง
            #   เกิดช่องว่างที่สัน — หัวจันทันที่สันต้องชนกันเอง)
            hip_geo = []
            for he, ha, hb in hips:
                if he.Id in ridge_ids:
                    continue
                ux, uy = hb.X - ha.X, hb.Y - ha.Y
                ul = math.sqrt(ux * ux + uy * uy)
                if ul < 1e-9:
                    continue
                ux, uy = ux / ul, uy / ul            # ทิศแกนตะเข้ (plan)
                px, py = -uy, ux                     # แนวตั้งฉาก = ทิศ "หนา" ของตะเข้
                hw = _halfwidth_along(he, px, py)    # ครึ่งความกว้าง (แกน→หน้าข้าง)
                if hw is None or hw < mm_to_ft(5.0):
                    hw = mm_to_ft(30.0)
                cx, cy = (ha.X + hb.X) / 2.0, (ha.Y + hb.Y) / 2.0
                hip_geo.append((ha, hb, ux, uy, px, py, hw, cx, cy))
            with revit.Transaction("REVOTECH - Rafter Gen (ตัดหัวที่ขอบตะเข้สัน)",
                                   swallow_errors=True):
                if not void_sym.IsActive:
                    void_sym.Activate()
                doc.Regenerate()
                pend = []
                for inst, fd, plan in created_recs:
                    try:
                        crv = inst.Location.Curve
                    except Exception:
                        continue
                    e0, e1 = crv.GetEndPoint(0), crv.GetEndPoint(1)
                    if e0.Z >= e1.Z:
                        top, bot = e0, e1
                    else:
                        top, bot = e1, e0
                    best, best_d = None, mm_to_ft(HIP_HEAD_TOL_MM)
                    for hg in hip_geo:
                        dd = _pt_to_seg(top, hg[0], hg[1])
                        if dd < best_d:
                            best_d = dd
                            best = hg
                    if best is None:
                        continue
                    ha, hb, ux, uy, px, py, hw, cx, cy = best
                    # หัวต้องอยู่ในช่วงตัวตะเข้จริง (กันจับผิดเส้นที่จุดรวมยอด)
                    hl2 = math.sqrt((hb.X - ha.X) ** 2 + (hb.Y - ha.Y) ** 2)
                    tst = ux * (top.X - ha.X) + uy * (top.Y - ha.Y)
                    if tst < -mm_to_ft(200.0) or tst > hl2 + mm_to_ft(200.0):
                        continue
                    # จันทันมาจากฝั่งไหนของแกนตะเข้ (เทียบตัวจันทัน = ปลายล่าง)
                    sd = px * (bot.X - cx) + py * (bot.Y - cy)
                    # ปลายล่างก้ำกึ่งกับแกน (จันทันสั้นๆ ที่จุดรวมยอด) → ระบุฝั่ง
                    # ไม่ได้ชัวร์ เสี่ยงใบมีดหันผิดข้างกลืนทั้งท่อน — ข้ามดีกว่า
                    if abs(sd) < hw + mm_to_ft(50.0):
                        continue
                    s = 1.0 if sd >= 0 else -1.0
                    # ระนาบตัด = หน้าข้างตะเข้ฝั่งเดียวกับจันทัน (ห่างแกน hw*s)
                    q0x, q0y = cx + px * hw * s, cy + py * hw * s
                    # ทิศ "เข้าเนื้อตะเข้ (เอาไปทิ้ง)" = -s*perp → กล่อง void ยื่นไปทางนี้
                    Dx, Dy = -px * s, -py * s
                    theta = math.atan2(Dy, Dx) - math.pi / 2.0   # ให้ +Y ของ blade = D
                    off = px * (top.X - q0x) + py * (top.Y - q0y)
                    origin = DB.XYZ(top.X - px * off, top.Y - py * off, top.Z)
                    try:
                        vi = doc.Create.NewFamilyInstance(
                            origin, void_sym,
                            DB.Structure.StructuralType.NonStructural)
                        DB.ElementTransformUtils.RotateElement(
                            doc, vi.Id,
                            DB.Line.CreateBound(origin, origin + DB.XYZ(0, 0, 1.0)),
                            theta)
                        cm = vi.get_Parameter(
                            DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                        if cm is not None and not cm.IsReadOnly:
                            cm.Set(u"REVOTECH MiterVoid [จันทัน] - ตัดหัวชนขอบตะเข้สัน "
                                   u"(ย้าย/คัดลอกไปพร้อมจันทันเสมอ)")
                        pend.append((vi, inst))
                    except Exception:
                        pass
                doc.Regenerate()
                for vi, bm in pend:
                    try:
                        DB.InstanceVoidCutUtils.AddInstanceVoidCut(doc, bm, vi)
                        hip_cut_done += 1
                    except Exception:
                        pass

# จอยจันทัน↔ผืนหลังคา (จันทันคงเนื้อเต็ม) กันปริมาตรนับซ้ำ
rj_done, rj_switch, rj_fail = 0, 0, 0
if AUTO_ROOF_JOIN and inst_roofs:
    with revit.Transaction("REVOTECH - Rafter Gen (จอยหลังคา)",
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

out.print_md(u"## Rafter Gen เสร็จแล้ว")
if DELETE_OLD and old_rafters:
    out.print_md(u"- ลบจันทันเดิม: **{} ตัว**".format(len(old_rafters)))
out.print_md(u"- สร้างจันทันใหม่: **{} ตัว** / ความยาวรวม **{:.1f} ม.**".format(
    created, total_len * 0.3048))
if phases:
    out.print_md(u"- ระยะจัดวาง: Fixed Distance **{:.0f} มม.** แบบ **mirror ข้าม"
                 u"แนวพับ** (วิธีทำมือของทู: ยึดกึ่งกลางผืนแรก แล้วสะท้อนตำแหน่ง"
                 u"ข้ามตะเข้/อกไก่ → หัวชนเป็นคู่ + ทุกช่องเท่ากัน) — ซิงก์เฟสได้ "
                 u"**{}/{} ผืน**".format(
                     FIXED_SPACING_MM, len(phases),
                     len([p for p, w in plans_all if p is not None])))
else:
    out.print_md(u"- ระยะจัดวาง: Fixed Distance **{:.0f} มม.** นับจากมุมตะเข้สองข้าง"
                 u"เข้าหากลาง (หัวชนกันที่ตะเข้/สัน เศษเก็บกลางผืน){}".format(
                     FIXED_SPACING_MM,
                     u" — ⚠ MIRROR_LAYOUT เปิดอยู่แต่ไม่มีตะเข้ในโมเดล "
                     u"(กด Hip Ridge Gen ก่อน)" if MIRROR_LAYOUT else u""))
out.print_md(u"- ตั้งระดับ (คาลิเบรตจากเนื้อจริง): กดลง **{:.1f} มม.** → "
             u"หลังจันทันแนบระนาบผืนพอดี{}".format(
                 lowered_mm,
                 u" + จมเพิ่ม {:.0f} มม.".format(VERTICAL_OFFSET_MM)
                 if VERTICAL_OFFSET_MM else u""))
out.print_md(u"- จัดหัวคู่ที่เหลื่อมให้ชนพอดี (snap): **{} คู่**".format(snap_done))
if PLUMB_CUT_AT_TOP:
    if plumb_msg:
        out.print_md(u"- ⚠ ตัดดิ่งปลายบนไม่ได้ทำ: {}".format(plumb_msg))
    else:
        out.print_md(u"- ตัดดิ่งปลายบนที่สัน/ตะเข้ (plumb cut): **{} ปลาย** "
                     u"/ พลาด {}".format(plumb_cuts, plumb_fail))
out.print_md(u"- ปลด auto-join จันทัน↔โครงอื่น: **{} คู่**".format(unjoined))
if CUT_RAFTER_AT_HIP:
    if hips_found == 0:
        out.print_md(u"- ⚠ ตัดหัวเข้าตะเข้สัน: **ยังไม่มีตะเข้สัน/อกไก่ในโมเดล** — "
                     u"กด **Hip Ridge Gen** ก่อน แล้วรัน Rafter Gen ซ้ำ")
    elif void_sym is None:
        out.print_md(u"- ⚠ ตัดหัวเข้าตะเข้สัน: หา family ใบมีด `{}` ไม่เจอ — "
                     u"กด **Purlin Gen** หนึ่งครั้งเพื่อสร้าง family ก่อน".format(
                         VOID_FAM_NAME))
    else:
        if HEAD_PAIR_SNAP_MM > 0:
            out.print_md(u"- จัดหัวชนเป็นคู่บนแนวตะเข้/อกไก่ (อิงเส้นจริง): "
                         u"**{} คู่**".format(pair_done))
        out.print_md(u"- ตัดหัวจันทันที่ขอบข้างตะเข้สัน/อกไก่ (Ref Plane + Cut ด้วย "
                     u"void): **{} หัว** (พบตะเข้สัน/อกไก่ {} เส้น)".format(
                         hip_cut_done, hips_found))
if AUTO_ROOF_JOIN:
    out.print_md(u"- จอยจันทัน↔ผืนหลังคากันปริมาตรนับซ้ำ: **{} คู่** / "
                 u"สลับให้จันทันเป็นฝ่ายตัด {} / พลาด {}".format(
                     rj_done, rj_switch, rj_fail))
out.print_md(u"### รายผืน:")
for no, roof, nrows, cnt in face_report:
    out.print_md(u"- ผืน {} ({}): {} แนว → {} ท่อน".format(
        no, out.linkify(roof.Id), nrows, cnt))
if skipped:
    out.print_md(u"### ข้ามผืน:")
    for no, roof, why in skipped:
        out.print_md(u"- ผืน {} ({}): {}".format(no, out.linkify(roof.Id), why))
if err:
    out.print_md(u"- สร้างไม่สำเร็จ: {} ท่อน".format(err))
out.print_md(u"")
out.print_md(u"ไม่พอใจผลลัพธ์ → **Ctrl+Z** ครั้งเดียวย้อนได้ทั้งหมด")
out.print_md(u"ปรับระยะ/ความลึกได้ที่ CONFIG: FIXED_SPACING_MM / VERTICAL_OFFSET_MM")
