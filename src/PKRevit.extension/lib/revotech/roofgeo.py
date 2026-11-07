# -*- coding: utf-8 -*-
"""เรขาคณิตหลังคาสำหรับ Roof Cover: หาผืน (top face), จำแนกขอบ, สร้างตัวแข็ง

ไม่เรียก Transaction เอง — ผู้เรียกจัดการ
จำแนกขอบของทุกผืน (เฉพาะเส้นตรง):
  - ขอบที่มีผืนอื่นระนาบต่างกันใช้ร่วม = แนวพับ: นูน (สัน/ตะเฆ่สัน) หรือเว้า (ราง)
  - ขอบที่ไม่มีผืนใดใช้ร่วม และเกือบราบ + ผืนยกขึ้นเข้าด้านใน = ชายคา (เชิงชาย)
  - ขอบที่ไม่มีผืนใดใช้ร่วม และลาด = ขอบข้าง (ปั้นลม)
  - ขอบที่ใช้ร่วมกับผืนระนาบเดียวกัน = รอยต่อชิ้นย่อย (ข้าม)
ตรรกะนี้อ่านแนวคิดจาก HipRidgeGen (collect_top_faces / point_in_face) แล้วเขียนใหม่
IronPython 2.7 — ห้ามใช้ f-string
"""

import math
from System.Collections.Generic import List
from pyrevit import DB

from revotech.units import mm_to_ft

FLAT_DEG = 5.0          # ขอบที่ชันน้อยกว่านี้ = ราบ
SHARE_TOL_MM = 30.0     # ระยะที่ถือว่าขอบทับกัน
MIN_LEN_MM = 150.0      # ขอบสั้นกว่านี้ไม่ทำ


# ---------------------------------------------------------------- vectors
def _len(v):
    return math.sqrt(v.X * v.X + v.Y * v.Y + v.Z * v.Z)


def _unit(v):
    L = _len(v)
    if L < 1e-12:
        return None
    return DB.XYZ(v.X / L, v.Y / L, v.Z / L)


def _dist_pt_seg(p, a, b):
    ab = b - a
    L2 = ab.DotProduct(ab)
    if L2 < 1e-12:
        return _len(p - a)
    t = max(0.0, min(1.0, (p - a).DotProduct(ab) / L2))
    return _len(p - (a + ab.Multiply(t)))


# ---------------------------------------------------------------- faces
def top_faces(roofs):
    """ผืนบนของ Roof: [{face, n, roof, polys(list of [(x,y)]), segs(list of (a,b))}]"""
    out = []
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
            if n.Z < 0.05:
                continue
            polys, segs, arcs = [], [], 0
            try:
                for cl in f.GetEdgesAsCurveLoops():
                    pts = []
                    for c in cl:
                        tp = c.Tessellate()
                        for p in tp[:-1]:
                            pts.append((p.X, p.Y))
                        if isinstance(c, DB.Line):
                            segs.append((c.GetEndPoint(0), c.GetEndPoint(1)))
                        else:
                            arcs += 1
                    if len(pts) >= 3:
                        polys.append(pts)
            except Exception:
                continue
            if polys:
                out.append({"face": f, "n": n, "roof": roof, "polys": polys,
                            "segs": segs, "arcs": arcs})
    return out


def point_in_face(fd, x, y):
    inside = False
    for pts in fd["polys"]:
        m = len(pts)
        j = m - 1
        for i in range(m):
            x1, y1 = pts[i]
            x2, y2 = pts[j]
            if (y1 > y) != (y2 > y):
                if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                    inside = not inside
            j = i
    return inside


def _inward(fd, a, b):
    """เวกเตอร์หน่วยในระนาบผืน ตั้งฉากกับขอบ ชี้เข้าเนื้อผืน (None ถ้าหาไม่ได้)"""
    u = _unit(b - a)
    if u is None:
        return None, None
    p = _unit(fd["n"].CrossProduct(u))
    if p is None:
        return None, None
    probe = mm_to_ft(150.0)
    m = (a + b).Multiply(0.5)
    if point_in_face(fd, m.X + p.X * probe, m.Y + p.Y * probe):
        return u, p
    if point_in_face(fd, m.X - p.X * probe, m.Y - p.Y * probe):
        return u, p.Negate()
    return u, None


def _shared_with(faces, i, a, b):
    """index ผืนอื่นที่ใช้ขอบนี้ร่วม (ขนานและทับ) หรือ None"""
    tol = mm_to_ft(SHARE_TOL_MM)
    u = _unit(b - a)
    samples = [a + (b - a).Multiply(t) for t in (0.25, 0.5, 0.75)]
    for j in range(len(faces)):
        if j == i:
            continue
        for (c, d) in faces[j]["segs"]:
            uj = _unit(d - c)
            if uj is None or abs(u.DotProduct(uj)) < 0.99:
                continue
            for s in samples:
                if _dist_pt_seg(s, c, d) < tol:
                    return j
    return None


def classify(faces):
    """คืน dict: folds [(a,b,convex,flat,roof)], eaves/verges [(a,b,out,roof)], notes [str]"""
    res = {"folds": [], "eaves": [], "verges": [], "notes": []}
    minlen = mm_to_ft(MIN_LEN_MM)
    flat_sin = math.sin(math.radians(FLAT_DEG))
    seen = []
    arcs = sum(f["arcs"] for f in faces)
    if arcs:
        res["notes"].append(u"ข้ามขอบโค้ง {} เส้น (ยังรองรับเฉพาะเส้นตรง)".format(arcs))
    for i, fd in enumerate(faces):
        for (a, b) in fd["segs"]:
            if _len(b - a) < minlen:
                continue
            u, p = _inward(fd, a, b)
            if u is None or p is None:
                continue
            j = _shared_with(faces, i, a, b)
            slope_sin = abs(u.Z)
            flat = slope_sin <= flat_sin
            if j is not None:
                nB = faces[j]["n"]
                if abs(fd["n"].DotProduct(nB)) > 0.9995:
                    continue                      # รอยต่อชิ้นย่อยระนาบเดียวกัน
                if j < i:
                    continue                      # นับครั้งเดียวจากผืนที่ index ต่ำกว่า
                m = (a + b).Multiply(0.5)
                dup = False
                for (m2, u2, L2) in seen:
                    if (_len(m - m2) < mm_to_ft(150.0)
                            and abs(u.DotProduct(u2)) > 0.99
                            and abs(L2 - _len(b - a)) < mm_to_ft(400.0)):
                        dup = True
                        break
                if dup:
                    continue
                seen.append((m, u, _len(b - a)))
                convex = nB.DotProduct(p) < -1e-3
                res["folds"].append((a, b, convex, flat, fd["roof"]))
            else:
                out = _unit(DB.XYZ(-p.X, -p.Y, 0.0))
                if out is None:
                    res["notes"].append(u"ข้ามขอบดิ่ง/ตั้งฉากแปลน 1 เส้น")
                    continue
                if flat:
                    if p.Z > 0.05:
                        res["eaves"].append((a, b, out, fd["roof"]))
                    else:
                        res["notes"].append(u"ข้ามขอบบนราบ (ผืนลาดลงเข้าด้านใน) 1 เส้น")
                elif abs(u.Z) < 0.999:
                    res["verges"].append((a, b, out, fd["roof"]))
    return res


# ---------------------------------------------------------------- solids
def sheet_solid(fd, thickness_ft):
    """แผ่นมุงเต็มผืน: ดันขอบผืนขึ้นตามแนวฉากหน้าผืนหนา thickness"""
    loops = List[DB.CurveLoop]()
    for cl in fd["face"].GetEdgesAsCurveLoops():
        loops.Add(cl)
    return DB.GeometryCreationUtilities.CreateExtrusionGeometry(
        loops, fd["n"], thickness_ft)


def _frame(u, out=None):
    """แกนหน้าตัด: w = 'ขึ้น' ตั้งฉาก u ในระนาบดิ่ง, s = ด้านข้าง (หันไป out ถ้าให้)"""
    z = DB.XYZ(0, 0, 1)
    w = _unit(z - u.Multiply(z.DotProduct(u)))
    if w is None:
        return None, None
    s = _unit(u.CrossProduct(w))
    if s is None:
        return None, None
    if out is not None and s.DotProduct(out) < 0:
        s = s.Negate()
    return s, w


def prism(a, b, profile, out=None):
    """ตัวแข็งหน้าตัด profile [(x,y)...] (x = ด้านข้าง s, y = ขึ้น w ฟุต)
    ดันตามแนว a→b — คืน None ถ้าสร้างไม่ได้"""
    d = b - a
    L = _len(d)
    u = _unit(d)
    if u is None or L < 1e-6:
        return None
    s, w = _frame(u, out)
    if s is None:
        return None
    pts = [a + s.Multiply(x) + w.Multiply(y) for (x, y) in profile]
    loop = DB.CurveLoop()
    n = len(pts)
    for k in range(n):
        loop.Append(DB.Line.CreateBound(pts[k], pts[(k + 1) % n]))
    ls = List[DB.CurveLoop]()
    ls.Add(loop)
    return DB.GeometryCreationUtilities.CreateExtrusionGeometry(ls, u, L)


def cap_profile(width_ft, rise_ft, drop_ft):
    """ครอบสัน: หลังคาจั่วหน้าตัด (ขึ้นเป็นยอดตรงเส้นสัน ลงข้างละ drop)"""
    h = width_ft / 2.0
    return [(-h, -drop_ft), (h, -drop_ft), (h, 0.0), (0.0, rise_ft), (-h, 0.0)]


def board_profile(thick_ft, height_ft, above_ft):
    """เชิงชาย/ปั้นลม: แผ่นตั้ง หนา thick ห้อยลง height จากเส้นขอบ ยื่นขึ้น above"""
    return [(0.0, -height_ft), (thick_ft, -height_ft),
            (thick_ft, above_ft), (0.0, above_ft)]


# ---------------------------------------------------------------- types / material
def material_id(t):
    """material ของ type: ชั้นหนาสุดของ compound structure หรือ parameter ที่ชื่อมี Material/วัสดุ
    คืน ElementId ที่ใช้ได้ หรือ None"""
    inv = DB.ElementId.InvalidElementId
    try:
        cs = t.GetCompoundStructure()
        if cs is not None:
            best, bw = None, -1.0
            for k in range(cs.LayerCount):
                mid = cs.GetMaterialId(k)
                if mid != inv and cs.GetLayerWidth(k) > bw:
                    best, bw = mid, cs.GetLayerWidth(k)
            if best is not None:
                return best
    except Exception:
        pass
    try:
        for p in t.Parameters:
            try:
                if p.StorageType != DB.StorageType.ElementId:
                    continue
                nm = p.Definition.Name.lower()
                if (u"material" in nm or u"วัสดุ" in nm) and p.AsElementId() != inv:
                    return p.AsElementId()
            except Exception:
                continue
    except Exception:
        pass
    return None


def type_thickness_ft(t):
    """ความหนา compound structure (ฟุต) หรือ None"""
    try:
        cs = t.GetCompoundStructure()
        if cs is not None:
            w = cs.GetWidth()
            if w > 0:
                return w
    except Exception:
        pass
    return None
