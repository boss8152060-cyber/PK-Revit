# -*- coding: utf-8 -*-
"""Hip Ridge Gen — สร้างตะเข้สัน/สัน/ตะเข้ราง อัตโนมัติทุกแนว

ทำแบบเดียวกับขั้นตอนมือในคลิป (Beam → Pick Lines คลิกเส้นขอบมุมปั้นหยาทีละเส้น
→ ปรับ Z-Offset → CS ทำมุมที่เหลือ) แต่จบในคลิกเดียวทุกแนว และคาลิเบรตระดับ
ให้เองไม่ต้องลองปรับ Z-Offset ทีละตัว

หลักการ: "แนวสัน/ตะเข้" คือ ขอบที่ผืนหลังคาสองผืนมาชนกัน (ใช้ขอบร่วมกัน)
ส่วนขอบชายคาเป็นของผืนเดียว → คัดออกเอง เหลือเฉพาะแนวพับ

1) หาผืนหลังคา (top face) ของ Roof ทุกตัว → เก็บ "ขอบ" (เส้นตรง) ของทุกผืน
2) ขอบไหนที่มีผืนใช้ร่วม ≥2 ผืน = แนวพับ (สัน/ตะเข้สัน/ตะเข้ราง)
   - แนวเกือบราบ = สัน (ridge) / แนวลาด = ตะเข้ (hip/valley)
3) ลบตะเข้สันเดิม (ชื่อ type มีทุกคำใน TYPE_KEYWORDS) แล้ววางคานใหม่ตามแนวพับ
4) คาลิเบรตระดับ: กดคานลงให้ยอดแนบผิวหลังคาพอดี (ไม่โผล่เหนือหลังคา)
5) DisallowJoinAtEnd ทุกปลาย (แนวพับหลายเส้นชนที่ยอด — กัน error/auto-miter)
6) AUTO_ROOF_JOIN: จอยตะเข้สัน↔ผืนหลังคา กันปริมาตรนับซ้ำ
"""

import math
import os
from System.Collections.Generic import List
from pyrevit import revit, DB, forms, script

doc = revit.doc
out = script.get_output()

# ===================== CONFIG =====================
# แนวลาดลงมุม (ตะเข้สัน/ตะเข้ราง) ใช้ type นี้
TYPE_KEYWORDS = [u"ตะเข้"]
# แนวราบด้านบน (อกไก่) ใช้ type แยก — ไม่เจอค่อย fallback ไปใช้ type ตะเข้/จันทัน
RIDGE_TYPE_KEYWORDS = [u"อกไก่"]
FALLBACK_KEYWORDS = [u"จันทัน"]  # ถ้าไม่เจอทั้งคู่ ใช้ type นี้แทน (หน้าตัดเดียวกันในคลิป)

INCLUDE_RIDGE = True         # สร้างแนวสันบน/อกไก่ (ขอบร่วมที่เกือบราบ)
INCLUDE_HIP = True           # สร้างแนวตะเข้สัน (ขอบร่วมพับ "นูน" ที่ลาด)
INCLUDE_VALLEY = False       # แนวราง (พับ "เว้า" น้ำไหลลง) — ปิดไว้:
                             # เป็นงานของปุ่ม Valley Gen (ตะเข้ราง+รางน้ำ)
MIN_LEN_MM = 150.0           # แนวสั้นกว่านี้ไม่สร้าง (กันเศษจิ๋วที่ยอด)
MIN_FOLD_DEG = 8.0           # ผืนสองข้างต้องทำมุมกันเกินนี้ถึงนับเป็นแนวพับจริง
                             # (กันขอบชิ้นย่อยของผิวที่ถูกจอยกับแป/จันทัน = ผิวเรียบ)
RIDGE_MAX_SLOPE_DEG = 5.0    # ขอบที่เอียงน้อยกว่านี้นับเป็น "สัน" (นอกนั้นเป็นตะเข้)

VERTICAL_OFFSET_MM = 0.0     # จมเพิ่มทั้งชุดจากระดับตาม config ข้างล่าง (มม.)
                             # สคริปต์วัดเนื้อจริงแล้วคาลิเบรตให้เอง
HIP_TOP_ABOVE_MM = -15.0     # ตะเข้สัน: ยอดเทียบแนวพับ (มม.) — ค่าลบ = จมใต้แนวพับ
                             # ทูจูนเอง 11 ก.ค.: z Offset −40 จากรุ่นโผล่ 25
                             # → ยอดจมใต้แนวพับ 15มม. (ขอบข้างแนบเนื้อหลังคาพอดี)
RIDGE_TOP_BELOW_MM = 115.0   # อกไก่: ยอด "จม" ใต้แนวพับ (มม.) — ลงไปอยู่ข้างล่าง
                             # รับท้องจันทัน/ตะเข้สัน (~ความลึกจันทันตามแนวดิ่ง)
APEX_JOIN_MM = 500.0         # หัวตะเข้สันที่จบใกล้กันไม่เกินนี้ (จุดยอด/จุดรวม)
                             # ยืดตามแกนตัวเองมาชนติดกัน — 0 = ปิด
APEX_OVERLAP_MM = 60.0       # ยืดหัว "เลย" จุดรวมไปอีกเท่านี้ (มม.) ให้เนื้อ
                             # สองหัวเกยชนกันสนิท ไม่เหลือลิ่มช่องว่างด้านนอก
                             # (จบที่จุดรวมพอดี = ปลายตัดฉากจะแตะกันแค่มุมเดียว)
APEX_MITER = True            # ตัดส่วนเกินที่เกยข้ามทิ้งด้วยใบมีด void ตามระนาบ
                             # แบ่งครึ่งมุม (= Ref Plane + Cut Geometry แบบแป)
                             # → รอยต่อเฉียงเนียน — ทำเฉพาะจุดที่หัวชนกัน 2 หัว
VOID_FAM_NAME = u"REVOTECH_MiterVoidXXS"   # family ใบมีดตัวเดียวกับ Purlin Gen
Z_JUSTIFY = u"top"           # จุดอ้างอิงหน้าตัด (top / center / origin / bottom / asis)
DELETE_OLD = True            # ลบตะเข้สันเดิมก่อนสร้างใหม่
AUTO_ROOF_JOIN = True        # ปิดท้ายด้วยจอยตะเข้สัน↔ผืนหลังคา กันปริมาตรนับซ้ำ

MATERIAL_NAME = u""          # ตั้ง Structural Material (ใส่บางส่วนได้ / ว่าง = ค่าเดิม family)
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
MIN_LEN = mm_to_ft(MIN_LEN_MM)
VOFF = mm_to_ft(VERTICAL_OFFSET_MM)


def is_roof(e):
    return cat_id(e) == int(DB.BuiltInCategory.OST_Roofs)


def match_kw(name, kws):
    low = name.lower()
    return all(kw.lower() in low for kw in kws)


# ---------- เก็บ "ขอบ" ของผืนหลังคาทุกผืน ----------
def collect_top_faces(roofs):
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
            if n.Z < 0.05:
                continue
            loops = []
            try:
                for cl in f.GetEdgesAsCurveLoops():
                    pts = []
                    for c in cl:
                        for p in c.Tessellate()[:-1]:
                            pts.append((p.X, p.Y, p.Z))
                    if len(pts) >= 3:
                        loops.append(pts)
            except Exception:
                continue
            if not loops:
                continue
            faces.append({"face": f, "loops": loops, "n": n, "roof": roof})
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
                if x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                    inside = not inside
            j = i
    return inside


def _is_concave(a, b, fiA, fiB, faces):
    """True ถ้าแนวพับนี้เป็น "ราง": ผืนสองข้างยกขึ้นออกจากแนว (น้ำไหลลง)
    — แนวรางเป็นงานของปุ่ม Valley Gen ปุ่มนี้ต้องข้าม"""
    probe = mm_to_ft(200.0)
    mx, my, mz = (a.X + b.X) / 2.0, (a.Y + b.Y) / 2.0, (a.Z + b.Z) / 2.0
    dx, dy = b.X - a.X, b.Y - a.Y
    dl = math.sqrt(dx * dx + dy * dy)
    if dl < 1e-9:
        return False
    vx, vy = -dy / dl, dx / dl

    def side_of(fd):
        if point_in_face(fd, mx + vx * probe, my + vy * probe):
            return 1
        if point_in_face(fd, mx - vx * probe, my - vy * probe):
            return -1
        return 0

    def rise(fd, s):
        n = fd["n"]
        px, py = mx + vx * probe * s, my + vy * probe * s
        z = mz - (n.X * (px - mx) + n.Y * (py - my)) / n.Z
        return z - mz

    sA = side_of(faces[fiA])
    sB = side_of(faces[fiB])
    if sA == 0 or sB == 0 or sA == sB:
        return False
    thr = mm_to_ft(10.0)
    return rise(faces[fiA], sA) > thr and rise(faces[fiB], sB) > thr


def key_pt(p):
    return (int(round(p.X * FT_TO_MM)),
            int(round(p.Y * FT_TO_MM)),
            int(round(p.Z * FT_TO_MM)))


def edge_key(a, b):
    ka, kb = key_pt(a), key_pt(b)
    return (ka, kb) if ka <= kb else (kb, ka)


def _plane_key(fd):
    """คีย์ระนาบของผืน — ผืนที่ถูกจอยแตกชิ้นย่อยแต่ระนาบเดียวกัน ได้คีย์เดียว"""
    n = fd["n"]
    v0 = fd["loops"][0][0]
    d = n.X * v0[0] + n.Y * v0[1] + n.Z * v0[2]
    return (int(round(n.X * 100)), int(round(n.Y * 100)),
            int(round(n.Z * 100)), int(round(d * FT_TO_MM / 10.0)))


def collect_fold_lines(faces):
    """แนวพับนูน (ตะเข้สัน/อกไก่) แบบ "เส้นตัดระนาบ" — วิธีเดียวกับ Valley Gen
    ที่พิสูจน์แล้ว (แก้เส้นผีลอยกลางอากาศจากขอบ overlap ของหลังคาที่จอยกัน):
    1) จัดกลุ่มผืนตามระนาบ → จับคู่ระนาบลาดปกติทุกคู่ → เส้นตัดระนาบ
    2) พับนูน = แต่ละผืนอยู่ "ฝั่งที่ระนาบตัวเองต่ำกว่า" (สัน/ตะเข้ น้ำไหลออก)
       พับเว้า (ราง) ข้าม — งานของ Valley Gen (เปิดได้ด้วย INCLUDE_VALLEY)
    3) เดินสแกนตามเส้นทีละ ~200มม. เก็บเฉพาะช่วงที่มีเนื้อผืนจริงทั้งสองฝั่ง
    คืน list ของ (a, b, roof, is_ridge)"""
    cosmax = math.cos(math.radians(60.0))
    planes = {}
    for fi in range(len(faces)):
        fd = faces[fi]
        if fd["n"].Z < cosmax:
            continue                    # ผืนชัน (แถบรอยต่อระดับ) ไม่ร่วมวง
        k = _plane_key(fd)
        g = planes.get(k)
        if g is None:
            v0 = fd["loops"][0][0]
            planes[k] = {"n": fd["n"],
                         "d": (fd["n"].X * v0[0] + fd["n"].Y * v0[1]
                               + fd["n"].Z * v0[2]),
                         "members": [fi]}
        else:
            g["members"].append(fi)
    keys = list(planes.keys())
    probe = mm_to_ft(150.0)
    zthr = mm_to_ft(10.0)
    step = mm_to_ft(200.0)
    out_lines = []

    def zon(P, x, y):
        return (P["d"] - P["n"].X * x - P["n"].Y * y) / P["n"].Z

    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            A, B = planes[keys[i]], planes[keys[j]]
            nA, nB = A["n"], B["n"]
            kk = max(-1.0, min(1.0, nA.DotProduct(nB)))
            if math.degrees(math.acos(kk)) < MIN_FOLD_DEG:
                continue
            u = nA.CrossProduct(nB)
            if u.GetLength() < 1e-6:
                continue
            u = u.Normalize()
            uh = math.sqrt(u.X * u.X + u.Y * u.Y)
            if uh < 1e-9:
                continue                # เส้นตัดดิ่ง
            den = 1.0 - kk * kk
            al = (A["d"] - B["d"] * kk) / den
            be = (B["d"] - A["d"] * kk) / den
            x0 = DB.XYZ(nA.X * al + nB.X * be, nA.Y * al + nB.Y * be,
                        nA.Z * al + nB.Z * be)
            rngs = []
            for G in (A, B):
                tmin, tmax = None, None
                for fi in G["members"]:
                    for pts in faces[fi]["loops"]:
                        for p in pts:
                            t = (u.X * (p[0] - x0.X) + u.Y * (p[1] - x0.Y)
                                 + u.Z * (p[2] - x0.Z))
                            if tmin is None or t < tmin:
                                tmin = t
                            if tmax is None or t > tmax:
                                tmax = t
                rngs.append((tmin, tmax))
            if rngs[0][0] is None or rngs[1][0] is None:
                continue
            t0 = max(rngs[0][0], rngs[1][0])
            t1 = min(rngs[0][1], rngs[1][1])
            if t1 - t0 < MIN_LEN:
                continue
            vx, vy = -u.Y / uh, u.X / uh
            # ฝั่งที่ระนาบ A "สูงกว่า" (คงที่ตลอดเส้น)
            mx0 = x0.X + u.X * (t0 + t1) / 2.0
            my0 = x0.Y + u.Y * (t0 + t1) / 2.0
            zAp = zon(A, mx0 + vx * probe, my0 + vy * probe)
            zBp = zon(B, mx0 + vx * probe, my0 + vy * probe)
            if zAp > zBp + zthr:
                sHi = 1
            elif zBp > zAp + zthr:
                sHi = -1
            else:
                continue
            # นูน (สัน/ตะเข้): เนื้อ A อยู่ฝั่งที่ A ต่ำกว่า = -sHi, B อยู่ +sHi
            # เว้า (ราง): กลับกัน — เก็บเมื่อ INCLUDE_VALLEY เท่านั้น
            cfgs = [(-sHi,)]
            if INCLUDE_VALLEY:
                cfgs.append((sHi,))
            slope_deg = math.degrees(math.atan2(abs(u.Z), uh))
            is_ridge = slope_deg <= RIDGE_MAX_SLOPE_DEG
            roof = faces[A["members"][0]]["roof"]
            for (sgnA,) in cfgs:
                nseg = max(int(math.ceil((t1 - t0) / step)), 4)
                good = []
                for s in range(nseg + 1):
                    t = t0 + (t1 - t0) * s / nseg
                    mx = x0.X + u.X * t
                    my = x0.Y + u.Y * t
                    okA = False
                    for fi in A["members"]:
                        if point_in_face(faces[fi], mx + vx * probe * sgnA,
                                         my + vy * probe * sgnA):
                            okA = True
                            break
                    okB = False
                    if okA:
                        for fi in B["members"]:
                            if point_in_face(faces[fi],
                                             mx - vx * probe * sgnA,
                                             my - vy * probe * sgnA):
                                okB = True
                                break
                    good.append(okA and okB)
                s = 0
                while s <= nseg:
                    if not good[s]:
                        s += 1
                        continue
                    e = s
                    while e + 1 <= nseg and good[e + 1]:
                        e += 1
                    ta = t0 + (t1 - t0) * s / nseg
                    tb = t0 + (t1 - t0) * e / nseg
                    if tb - ta >= MIN_LEN:
                        pa = DB.XYZ(x0.X + u.X * ta, x0.Y + u.Y * ta,
                                    x0.Z + u.Z * ta)
                        pb = DB.XYZ(x0.X + u.X * tb, x0.Y + u.Y * tb,
                                    x0.Z + u.Z * tb)
                        out_lines.append((pa, pb, roof, is_ridge))
                    s = e + 1
    return out_lines


def collect_shared_edges(faces):
    """(วิธีเก่า — เลิกใช้: โดนเส้นผีจากขอบ overlap) คืนแนวพับจากขอบร่วม"""
    edges = {}   # key -> [a, b, [face_idx...], roof]
    for fi in range(len(faces)):
        fd = faces[fi]
        try:
            loops = fd["face"].GetEdgesAsCurveLoops()
        except Exception:
            continue
        for cl in loops:
            for c in cl:
                if not isinstance(c, DB.Line):
                    continue
                a, b = c.GetEndPoint(0), c.GetEndPoint(1)
                if a.DistanceTo(b) < MIN_LEN:
                    continue
                k = edge_key(a, b)
                if k in edges:
                    edges[k][2].append(fi)
                else:
                    edges[k] = [a, b, [fi], fd["roof"]]
    shared = []
    for k, v in edges.items():
        fis = v[2]
        if len(fis) < 2:
            continue                       # ขอบของผืนเดียว = ชายคา ข้าม
        # ต้องเป็น "รอยพับจริง": ผืนสองข้างทำมุมต่างกันเกิน MIN_FOLD_DEG
        # (ผิวหลังคาที่ถูกจอยกับแป/จันทันจะแตกเป็นชิ้นเรียบเสมอกัน normal เท่ากัน
        #  → มุม ~0 → ข้าม ไม่นับเป็นแนวพับปลอม)
        max_ang, pair = 0.0, None
        for i in range(len(fis)):
            for j in range(i + 1, len(fis)):
                ni, nj = faces[fis[i]]["n"], faces[fis[j]]["n"]
                dot = max(-1.0, min(1.0, ni.X * nj.X + ni.Y * nj.Y
                                    + ni.Z * nj.Z))
                ang = math.degrees(math.acos(dot))
                if ang > max_ang:
                    max_ang = ang
                    pair = (fis[i], fis[j])
        if max_ang < MIN_FOLD_DEG or pair is None:
            continue
        a, b = v[0], v[1]
        # พับเว้า = แนวราง → ของ Valley Gen ไม่ใช่ของเรา
        if not INCLUDE_VALLEY and _is_concave(a, b, pair[0], pair[1], faces):
            continue
        dz = abs(a.Z - b.Z)
        dxy = math.sqrt((a.X - b.X) ** 2 + (a.Y - b.Y) ** 2)
        slope_deg = math.degrees(math.atan2(dz, dxy)) if dxy > 1e-9 else 90.0
        is_ridge = slope_deg <= RIDGE_MAX_SLOPE_DEG
        shared.append((a, b, v[3], is_ridge))
    return merge_collinear(shared)


def merge_collinear(shared):
    """รวมท่อนแนวพับที่อยู่บน 'เส้นตรงเดียวกัน' ให้เป็นเส้นเดียว
    (ขอบตะเข้ถูกรอยบากจากแป/จันทันตัดเป็นหลายท่อนสั้นเรียงต่อกัน)"""
    groups = {}
    for a, b, roof, is_ridge in shared:
        d = b - a
        L = d.GetLength()
        if L < 1e-9:
            continue
        d = d.Normalize()
        # ทำทิศให้เป็นแบบฉบับ (องค์ประกอบแรกที่ไม่เป็นศูนย์เป็นบวก)
        if (d.X < -1e-9 or (abs(d.X) <= 1e-9 and d.Y < -1e-9)
                or (abs(d.X) <= 1e-9 and abs(d.Y) <= 1e-9 and d.Z < 0)):
            d = d.Negate()
        mom = a.CrossProduct(d)            # a×d เท่ากันทุกจุดบนเส้นเดียวกัน
        key = (int(round(d.X * 1000)), int(round(d.Y * 1000)),
               int(round(d.Z * 1000)),
               int(round(mom.X * FT_TO_MM)), int(round(mom.Y * FT_TO_MM)),
               int(round(mom.Z * FT_TO_MM)))
        g = groups.get(key)
        if g is None:
            groups[key] = {"a0": a, "d": d, "roof": roof,
                           "is_ridge": is_ridge, "tmin": 0.0, "tmax": L}
        else:
            a0, dd = g["a0"], g["d"]
            for p in (a, b):
                t = dd.DotProduct(p - a0)
                if t < g["tmin"]:
                    g["tmin"] = t
                if t > g["tmax"]:
                    g["tmax"] = t
    out_lines = []
    for g in groups.values():
        p0 = g["a0"] + g["d"] * g["tmin"]
        p1 = g["a0"] + g["d"] * g["tmax"]
        out_lines.append((p0, p1, g["roof"], g["is_ridge"]))
    return out_lines


# ---------- คาลิเบรตระดับ: วัดเนื้อคานที่โผล่เหนือแนวพับ ----------
def max_protrusion(g, a, b):
    ux, uy, uz = b.X - a.X, b.Y - a.Y, b.Z - a.Z
    L2 = ux * ux + uy * uy + uz * uz
    best = [None]

    def walk(geo):
        for obj in geo:
            if isinstance(obj, DB.GeometryInstance):
                walk(obj.GetInstanceGeometry())
            elif isinstance(obj, DB.Solid) and obj.Volume > 1e-9:
                for e in obj.Edges:
                    for p in e.Tessellate():
                        if L2 > 1e-9:
                            t = ((p.X - a.X) * ux + (p.Y - a.Y) * uy
                                 + (p.Z - a.Z) * uz) / L2
                        else:
                            t = 0.0
                        lz = a.Z + uz * t
                        d = p.Z - lz
                        if best[0] is None or d > best[0]:
                            best[0] = d
    walk(g)
    return best[0]


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
    for bip in (DB.BuiltInParameter.START_EXTENSION,
                DB.BuiltInParameter.END_EXTENSION):
        try:
            pr = inst.get_Parameter(bip)
            if pr is not None and not pr.IsReadOnly:
                pr.Set(0.0)
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
# ของเดิมที่ต้องลบ = ทั้งตะเข้สัน (ตะเข้) และอกไก่
# — ยกเว้น "ตะเข้ราง/รางน้ำ" (ของปุ่ม Valley Gen ไม่ใช่ของเรา อย่าลบ)
old_hips = [e for e in all_framing
            if (match_kw(type_name(e), TYPE_KEYWORDS)
                or match_kw(type_name(e), RIDGE_TYPE_KEYWORDS))
            and u"ราง" not in type_name(e)]


def find_type(kw_list):
    for t in DB.FilteredElementCollector(doc) \
              .OfCategory(DB.BuiltInCategory.OST_StructuralFraming) \
              .WhereElementIsElementType():
        if match_kw(ename(t), kw_list):
            return t
    return None


# type แนวลาด (ตะเข้สัน) → keyword → fallback จันทัน
hip_sym = find_type(TYPE_KEYWORDS)
hip_fallback = False
if hip_sym is None:
    hip_sym = find_type(FALLBACK_KEYWORDS)
    hip_fallback = hip_sym is not None

# type แนวราบ (อกไก่) → keyword อกไก่ → fallback ไปใช้ type ตะเข้สัน
ridge_sym = find_type(RIDGE_TYPE_KEYWORDS)
ridge_fallback = False
if ridge_sym is None:
    ridge_sym = hip_sym
    ridge_fallback = ridge_sym is not None

used_fallback = hip_fallback
if hip_sym is None and ridge_sym is None:
    names = sorted(set(type_name(e) for e in all_framing if type_name(e)))
    out.print_md(u"## หา type ตะเข้สัน/อกไก่ (ชื่อมีคำว่า `{}`, `{}` หรือ `{}`) ไม่เจอ".format(
        u", ".join(TYPE_KEYWORDS), u", ".join(RIDGE_TYPE_KEYWORDS),
        u", ".join(FALLBACK_KEYWORDS)))
    out.print_md(u"### ชื่อ type framing ที่มีในโปรเจกต์:")
    for nm in names[:40]:
        out.print_md(u"- `{}`".format(nm))
    forms.alert(u"หา type ไม่เจอ — ทำตามคลิป: Edit Type → Duplicate → "
                u"Rename ใส่คำว่า \"ตะเข้สัน\" / \"อกไก่\" แล้วรันใหม่", exitscript=True)
sym = hip_sym or ridge_sym    # ใช้เป็นตัวหลักสำรอง (level/รายงาน)

# level สำรอง
fb_level = None
if old_hips:
    try:
        p = old_hips[0].get_Parameter(
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


def _line_line_mid(p1, u1, p2, u2):
    """จุดกึ่งกลางของช่วงใกล้สุดระหว่างเส้นตรงสองเส้น (จุดตัดโดยประมาณ)
    — คืน None ถ้าเกือบขนานกัน"""
    b = u1.DotProduct(u2)
    den = 1.0 - b * b
    if abs(den) < 1e-9:
        return None
    w = p1 - p2
    d = u1.DotProduct(w)
    e = u2.DotProduct(w)
    s = (b * e - d) / den
    t = (e - b * d) / den
    q1 = p1 + u1.Multiply(s)
    q2 = p2 + u2.Multiply(t)
    return DB.XYZ((q1.X + q2.X) / 2.0, (q1.Y + q2.Y) / 2.0,
                  (q1.Z + q2.Z) / 2.0)


def find_void_symbol():
    for f in DB.FilteredElementCollector(doc).OfClass(DB.Family):
        if ename(f) == VOID_FAM_NAME:
            for sid in f.GetFamilySymbolIds():
                return doc.GetElement(sid)
    return None


def build_void_family(rfa_path):
    """สร้างไฟล์ .rfa กล่อง void ใบมีด (ก็อปกลไกจาก Purlin Gen)
    — คืน None ถ้าสำเร็จ / ข้อความ error ถ้าพลาด"""
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
        return u"หา template 'Generic Model.rft' ไม่เจอ"
    fdoc = None
    try:
        fdoc = app.NewFamilyDocument(tpl)
        t = DB.Transaction(fdoc, "REVOTECH void box")
        t.Start()
        try:
            fam = fdoc.OwnerFamily
            pv = fam.get_Parameter(DB.BuiltInParameter.FAMILY_ALLOW_CUT_WITH_VOIDS)
            if pv is not None and not pv.IsReadOnly:
                pv.Set(1)
            sp = DB.SketchPlane.Create(
                fdoc, DB.Plane.CreateByNormalAndOrigin(DB.XYZ.BasisZ, DB.XYZ.Zero))
            L, W, H = 0.49, 0.49, 0.49     # ครึ่งยาว 15 / หนา 15 / ครึ่งสูง 15 ซม. (XXS)
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


# เตรียมใบมีดตัดเฉียง (family เดียวกับ Purlin Gen) — ก่อนเปิด TransactionGroup
void_sym = None
if APEX_JOIN_MM > 0 and APEX_MITER:
    void_sym = find_void_symbol()
    if void_sym is None:
        _here = os.path.dirname(__file__)
        for _rfa in (os.path.join(_here, VOID_FAM_NAME + u".rfa"),
                     os.path.join(os.path.dirname(_here),
                                  u"PurlinGen.pushbutton",
                                  VOID_FAM_NAME + u".rfa")):
            if not os.path.isfile(_rfa):
                continue
            try:
                with revit.Transaction("REVOTECH - โหลด MiterVoid"):
                    doc.LoadFamily(_rfa)
            except Exception:
                pass
            void_sym = find_void_symbol()
            if void_sym is not None:
                break
    if void_sym is None:
        # ไม่มีทั้งในโปรเจกต์และบนดิสก์ — สร้าง family เองเลย
        # (ปุ่มนี้เป็นปุ่มแรกของ Roof Master ต้องยืนเองได้)
        _rfa = os.path.join(os.path.dirname(__file__), VOID_FAM_NAME + u".rfa")
        if build_void_family(_rfa) is None:
            try:
                with revit.Transaction("REVOTECH - โหลด MiterVoid"):
                    doc.LoadFamily(_rfa)
            except Exception:
                pass
            void_sym = find_void_symbol()

tg = DB.TransactionGroup(doc, "REVOTECH - Hip Ridge Gen")
tg.Start()

# ลบตะเข้สันเดิมก่อนอ่านผืน (กันร่องจากตัวที่จอยไว้ทำให้ขอบผืนเพี้ยน)
with revit.Transaction("REVOTECH - Hip Ridge Gen (ลบของเดิม)",
                       swallow_errors=True):
    if DELETE_OLD and old_hips:
        doc.Delete(List[DB.ElementId]([e.Id for e in old_hips]))
    # ลบใบมีดของตะเข้สันรอบก่อน (เฉพาะที่มาร์ก [ตะเข้] — ไม่แตะของแป/จันทัน)
    stale_v = []
    for gm in DB.FilteredElementCollector(doc) \
               .OfCategory(DB.BuiltInCategory.OST_GenericModel) \
               .WhereElementIsNotElementType():
        try:
            if not gm.Symbol.Family.Name.startswith(u"REVOTECH_MiterVoid"):
                continue
            cmv = gm.get_Parameter(
                DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if cmv is not None and u"[ตะเข้]" in (cmv.AsString() or u""):
                gm.Pinned = False
                stale_v.append(gm.Id)
        except Exception:
            pass
    if stale_v:
        doc.Delete(List[DB.ElementId](stale_v))

faces = collect_top_faces(roofs)
if not faces:
    tg.RollBack()
    forms.alert(u"หาผืนหลังคา (top face) ไม่เจอ", exitscript=True)

shared = collect_fold_lines(faces)
lines = []
for a, b, roof, is_ridge in shared:
    if is_ridge and not INCLUDE_RIDGE:
        continue
    if (not is_ridge) and not INCLUDE_HIP:
        continue
    lines.append((a, b, roof, is_ridge))

out.print_md(u"พบผืนหลังคา **{} ผืน** / แนวพับ **{}** เส้น / ของเดิม {} ตัว".format(
    len(faces), len(lines), len(old_hips)))
out.print_md(u"- อกไก่ (แนวราบ) ใช้ type: `{}`{}".format(
    ename(ridge_sym), u" ⚠fallback" if ridge_fallback else u""))
out.print_md(u"- ตะเข้สัน (แนวลาด) ใช้ type: `{}`{}".format(
    ename(hip_sym), u" ⚠fallback" if hip_fallback else u""))
if not lines:
    tg.RollBack()
    forms.alert(u"ไม่พบแนวพับ (ขอบที่ผืนสองผืนใช้ร่วมกัน) — "
                u"หลังคานี้อาจเป็นผืนเดียว/ไม่มีสัน", exitscript=True)

created, err = 0, 0
n_ridge, n_hip = 0, 0
total_len = 0.0
created_recs = []      # (inst, a, b)
inst_roofs = []

with revit.Transaction("REVOTECH - Hip Ridge Gen (สร้าง)", swallow_errors=True):
    for _s in set([ridge_sym, hip_sym]):
        if _s is not None and not _s.IsActive:
            _s.Activate()
    doc.Regenerate()
    for a, b, roof, is_ridge in lines:
        try:
            use_sym = ridge_sym if is_ridge else hip_sym   # อกไก่ vs ตะเข้สัน
            line = DB.Line.CreateBound(a, b)
            inst = doc.Create.NewFamilyInstance(
                line, use_sym, level_for(roof), DB.Structure.StructuralType.Beam)
            try:
                DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(inst, 0)
                DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(inst, 1)
            except Exception:
                pass
            set_zjust(inst)
            set_material(inst)
            zero_extensions(inst)
            created_recs.append((inst, a, b, is_ridge))
            inst_roofs.append((inst, roof))
            created += 1
            total_len += a.DistanceTo(b)
            if is_ridge:
                n_ridge += 1
            else:
                n_hip += 1
        except Exception:
            err += 1

# ตั้งระดับ: วัดของจริงแล้วขยับแต่ละตัว —
#   ตะเข้สัน: ยอดโผล่เหนือแนวพับ HIP_TOP_ABOVE_MM (รับแป/ครอบสัน)
#   อกไก่:   ยอดจมใต้แนวพับ RIDGE_TOP_BELOW_MM (ลงไปรับท้องจันทัน/ตะเข้สัน)
lowered_mm = 0.0
if created_recs:
    with revit.Transaction("REVOTECH - Hip Ridge Gen (ตั้งระดับ)",
                           swallow_errors=True):
        doc.Regenerate()
        drops = []
        for inst, a, b, is_ridge in created_recs:
            dz = VOFF + (mm_to_ft(RIDGE_TOP_BELOW_MM) if is_ridge
                         else -mm_to_ft(HIP_TOP_ABOVE_MM))
            try:
                pr = max_protrusion(inst.get_Geometry(DB.Options()), a, b)
            except Exception:
                pr = None
            if pr is not None and pr > mm_to_ft(0.5):
                dz += pr
            drops.append((inst, dz))
        mv_any = 0.0
        for inst, dz in drops:
            if abs(dz) > mm_to_ft(0.5):
                try:
                    DB.ElementTransformUtils.MoveElement(
                        doc, inst.Id, DB.XYZ(0.0, 0.0, -dz))
                    if abs(dz) > abs(mv_any):
                        mv_any = dz
                except Exception:
                    pass
        lowered_mm = mv_any * FT_TO_MM

# ชนหัวตะเข้สันที่ยอด: จับกลุ่มปลาย "บน" ที่อยู่ใกล้กัน (จุดยอด/จุดรวมตะเข้)
# แล้วยืดแต่ละหัวตามแกนตัวเองไปหาจุดรวม → หัวชนติดกัน (แบบที่ทูทำมือ)
apex_joined = 0
miter_jobs = []   # (instA, botA, instB, botB, จุดรวม) — ไว้ตัดเฉียงส่วนที่เกยเกิน
if APEX_JOIN_MM > 0 and created_recs:
    with revit.Transaction("REVOTECH - Hip Ridge Gen (ชนหัวที่ยอด)",
                           swallow_errors=True):
        tolj = mm_to_ft(APEX_JOIN_MM)
        heads = []
        for idx in range(len(created_recs)):
            inst, a, b, is_ridge = created_recs[idx]
            if is_ridge:
                continue                     # เฉพาะตะเข้สัน
            try:
                crv = inst.Location.Curve
            except Exception:
                continue
            e0, e1 = crv.GetEndPoint(0), crv.GetEndPoint(1)
            top, bot = (e0, e1) if e0.Z >= e1.Z else (e1, e0)
            heads.append((idx, top, bot))
        used = set()
        for i in range(len(heads)):
            if i in used:
                continue
            # จับกลุ่มแบบ BFS: หัวที่ "โยงถึงกันเป็นทอด" อยู่กลุ่มเดียวกัน
            # (แบบเดิมวัดจากหัวตัวแรกตัวเดียว จุดชุมทางหลายหัวตกหล่น)
            cluster = [i]
            used.add(i)
            qi = 0
            while qi < len(cluster):
                cur = cluster[qi]
                qi += 1
                for j in range(len(heads)):
                    if j in used:
                        continue
                    if heads[cur][1].DistanceTo(heads[j][1]) < tolj:
                        cluster.append(j)
                        used.add(j)
            if len(cluster) < 2:
                continue
            cx = sum(heads[k][1].X for k in cluster) / len(cluster)
            cy = sum(heads[k][1].Y for k in cluster) / len(cluster)
            cz = sum(heads[k][1].Z for k in cluster) / len(cluster)
            c = DB.XYZ(cx, cy, cz)
            # "จุดยอดจริง" อ้างอิงจากแนวแกน: แกนตะเข้สัน (เส้นตัดระนาบ) ทุกเส้น
            # วิ่งผ่านยอดจริงโดยเรขาคณิต → หาจุดตัดร่วมของแกนเป็นคู่ๆ แล้วเฉลี่ย
            # — ห้ามใช้ centroid ของหัวที่ถูกเล็มมาไม่เท่ากัน (ทำให้แต่ละเส้น
            # ยืดออกไปยาวไม่เท่ากัน ทูจับได้จาก System Length ต่างกัน)
            xs = []
            for ii in range(len(cluster)):
                for jj in range(ii + 1, len(cluster)):
                    i1, t1_, b1_ = heads[cluster[ii]]
                    i2, t2_, b2_ = heads[cluster[jj]]
                    u1 = (t1_ - b1_).Normalize()
                    u2 = (t2_ - b2_).Normalize()
                    px = _line_line_mid(b1_, u1, b2_, u2)
                    if px is not None and px.DistanceTo(c) < tolj * 2:
                        xs.append(px)
            if xs:
                c = DB.XYZ(sum(p.X for p in xs) / len(xs),
                           sum(p.Y for p in xs) / len(xs),
                           sum(p.Z for p in xs) / len(xs))
            cl_done = []
            for k in cluster:
                idx, top, bot = heads[k]
                inst = created_recs[idx][0]
                u = (top - bot).Normalize()
                t = u.DotProduct(c - bot)     # ฟุตตั้งฉากของจุดรวมบนแกนตัวเอง
                if t < bot.DistanceTo(top) * 0.5:
                    continue                  # จุดรวมย้อนหลังผิดปกติ — ข้าม
                t += mm_to_ft(APEX_OVERLAP_MM)   # ยืดเลยจุดรวม ให้เนื้อเกยชนสนิท
                try:
                    inst.Location.Curve = DB.Line.CreateBound(
                        bot, bot + u.Multiply(t))
                    apex_joined += 1
                    cl_done.append((inst, bot))
                except Exception:
                    pass
            # ตัดเฉียง "ทุกคู่" ในกลุ่ม (จุดชุมทาง 3-4 หัวก็ได้รอย miter ครบ
            # ทุกด้าน — คู่ที่เกือบสวนทางกันไปคัดออกตอนวางใบมีด)
            if APEX_MITER and len(cl_done) >= 2:
                for p1 in range(len(cl_done)):
                    for p2 in range(p1 + 1, len(cl_done)):
                        miter_jobs.append((cl_done[p1][0], cl_done[p1][1],
                                           cl_done[p2][0], cl_done[p2][1], c))
            # ยืดปลายอกไก่ (ที่จมอยู่ล่าง) ให้ทอดไปอยู่ใต้จุดรวม → รับหัวตะเข้สัน
            # เงื่อนไข: จุดรวมต้องอยู่บน "แนวต่อของแกนอกไก่" (ตั้งฉาก ≤300มม.)
            # — ปลายโดนตัวสแกนเนื้อผืนเล็มสั้นได้หลายร้อยมม. เลยยอมยืดถึง 1.5ม.
            for idx2 in range(len(created_recs)):
                inst2, ra, rb, isr2 = created_recs[idx2]
                if not isr2:
                    continue
                try:
                    crv2 = inst2.Location.Curve
                except Exception:
                    continue
                f0, f1 = crv2.GetEndPoint(0), crv2.GetEndPoint(1)
                dpx, dpy = f1.X - f0.X, f1.Y - f0.Y
                hm = math.sqrt(dpx * dpx + dpy * dpy)
                if hm < 1e-9:
                    continue
                wx, wy = dpx / hm, dpy / hm       # ทิศแกน (plan, f0→f1)
                # ปลายที่ใกล้จุดรวมกว่า
                d0 = math.sqrt((f0.X - c.X) ** 2 + (f0.Y - c.Y) ** 2)
                d1 = math.sqrt((f1.X - c.X) ** 2 + (f1.Y - c.Y) ** 2)
                endi = 0 if d0 <= d1 else 1
                p = f0 if endi == 0 else f1
                q = f1 if endi == 0 else f0
                # แกนจาก q → p (พลิกทิศให้ชี้ออกทางปลาย p)
                sx, sy = (wx, wy) if endi == 1 else (-wx, -wy)
                tq = sx * (c.X - q.X) + sy * (c.Y - q.Y)   # ระยะตามแกนถึง c
                perp = abs(-sy * (c.X - q.X) + sx * (c.Y - q.Y))
                if perp > mm_to_ft(300.0):
                    continue                       # จุดรวมไม่อยู่บนแนวอกไก่นี้
                ext = tq - hm                      # ระยะที่ต้องยืดพ้นปลายเดิม
                if ext < mm_to_ft(5.0) or ext > mm_to_ft(1500.0):
                    continue
                newp = DB.XYZ(q.X + sx * tq, q.Y + sy * tq, p.Z)
                try:
                    if endi == 0:
                        inst2.Location.Curve = DB.Line.CreateBound(newp, f1)
                    else:
                        inst2.Location.Curve = DB.Line.CreateBound(f0, newp)
                except Exception:
                    pass

# ตัดเฉียงส่วนที่เกยเกินจุดรวมทิ้ง: ใบมีด void 2 ตัวประกบ "ระนาบดิ่งแบ่งครึ่ง
# มุม" ที่จุดรวม แล้วตัดเฉพาะเนื้อฝั่งที่ข้ามระนาบ (= Ref Plane + Cut แบบแป)
apex_cut, apex_cut_fail = 0, 0
if miter_jobs and void_sym is not None:
    with revit.Transaction("REVOTECH - Hip Ridge Gen (ตัดเฉียงหัว)",
                           swallow_errors=True):
        if not void_sym.IsActive:
            void_sym.Activate()
        doc.Regenerate()
        pend = []
        for instA, botA, instB, botB, c in miter_jobs:
            ax, ay = botA.X - c.X, botA.Y - c.Y
            al = math.sqrt(ax * ax + ay * ay)
            bx2, by2 = botB.X - c.X, botB.Y - c.Y
            bl = math.sqrt(bx2 * bx2 + by2 * by2)
            if al < 1e-9 or bl < 1e-9:
                continue
            ax, ay = ax / al, ay / al          # ทิศเข้าเนื้อ A (plan)
            bx2, by2 = bx2 / bl, by2 / bl      # ทิศเข้าเนื้อ B
            if ax * bx2 + ay * by2 < -0.87:
                continue                       # เกือบสวนทาง (>~150°) — ระนาบ
                                               # แบ่งครึ่งเกือบขนานแกน จะเฉือน
                                               # ยาวตามตัว ข้ามคู่นี้
            hx, hy = ax + bx2, ay + by2
            hl = math.sqrt(hx * hx + hy * hy)
            if hl < 1e-6:
                continue                       # สวนทางพอดี แบ่งครึ่งมุมไม่ได้
            hx, hy = hx / hl, hy / hl          # ทิศระนาบแบ่งครึ่งมุม
            nx, ny = -hy, hx
            ang = math.atan2(hy, hx)
            for bm, dinx, diny in ((instA, ax, ay), (instB, bx2, by2)):
                side = dinx * nx + diny * ny
                theta = ang + (math.pi if side > 0 else 0.0)
                try:
                    vi = doc.Create.NewFamilyInstance(
                        c, void_sym, DB.Structure.StructuralType.NonStructural)
                    DB.ElementTransformUtils.RotateElement(
                        doc, vi.Id,
                        DB.Line.CreateBound(c, c + DB.XYZ(0, 0, 1.0)), theta)
                    cm = vi.get_Parameter(
                        DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                    if cm is not None and not cm.IsReadOnly:
                        cm.Set(u"REVOTECH MiterVoid [ตะเข้] - ใบมีดตัดเฉียง"
                               u"หัวตะเข้สัน (ย้าย/คัดลอกไปพร้อมตะเข้สันเสมอ)")
                    pend.append((vi, bm))
                except Exception:
                    apex_cut_fail += 1
        doc.Regenerate()
        for vi, bm in pend:
            try:
                DB.InstanceVoidCutUtils.AddInstanceVoidCut(doc, bm, vi)
                apex_cut += 1
            except Exception:
                apex_cut_fail += 1

# จอยตะเข้สัน↔ผืนหลังคา (ตะเข้สันคงเนื้อเต็ม) กันปริมาตรนับซ้ำ
rj_done, rj_switch, rj_fail = 0, 0, 0
if AUTO_ROOF_JOIN and inst_roofs:
    with revit.Transaction("REVOTECH - Hip Ridge Gen (จอยหลังคา)",
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

out.print_md(u"## Hip Ridge Gen เสร็จแล้ว")
if DELETE_OLD and old_hips:
    out.print_md(u"- ลบของเดิม (อกไก่+ตะเข้สัน): **{} ตัว**".format(len(old_hips)))
out.print_md(u"- สร้างใหม่: **{} เส้น** — อกไก่ (แนวราบ) {} / ตะเข้สัน (แนวลาด) {} "
             u"/ ยาวรวม **{:.1f} ม.**".format(
                 created, n_ridge, n_hip, total_len * 0.3048))
out.print_md(u"- ตั้งระดับ (คาลิเบรตจากเนื้อจริง): ตะเข้สันยอด**โผล่เหนือแนวพับ "
             u"{:.0f} มม.** / อกไก่ยอด**จมใต้แนวพับ {:.0f} มม.** (รับท้อง"
             u"จันทัน/ตะเข้สัน){}".format(
                 HIP_TOP_ABOVE_MM, RIDGE_TOP_BELOW_MM,
                 u" + จมเพิ่ม {:.0f} มม.".format(VERTICAL_OFFSET_MM)
                 if VERTICAL_OFFSET_MM else u""))
if APEX_JOIN_MM > 0:
    out.print_md(u"- ชนหัวตะเข้สันที่ยอด (ยืดเกยข้ามจุดรวม {:.0f} มม.): "
                 u"**{} หัว**".format(APEX_OVERLAP_MM, apex_joined))
    if APEX_MITER:
        if void_sym is None:
            out.print_md(u"- ⚠ ตัดเฉียงหัวไม่ได้: หา family ใบมีด `{}` ไม่เจอ — "
                         u"กด Purlin Gen หนึ่งครั้งเพื่อสร้างก่อน".format(
                             VOID_FAM_NAME))
        else:
            out.print_md(u"- ตัดส่วนเกยเกินทิ้งตามระนาบแบ่งครึ่งมุม (miter): "
                         u"**{} หัว** / พลาด {}".format(apex_cut, apex_cut_fail))
if AUTO_ROOF_JOIN:
    out.print_md(u"- จอย↔ผืนหลังคากันปริมาตรนับซ้ำ: **{} คู่** / "
                 u"สลับให้คานเป็นฝ่ายตัด {} / พลาด {}".format(
                     rj_done, rj_switch, rj_fail))
if ridge_fallback:
    out.print_md(u"- ⚠ ไม่เจอ type อกไก่ (ชื่อมีคำว่า `อกไก่`) — อกไก่ใช้ "
                 u"type ตะเข้สัน `{}` แทนไปก่อน (Duplicate+Rename ใส่ \"อกไก่\" "
                 u"เพื่อแยกหน้าตัด)".format(ename(ridge_sym)))
if hip_fallback:
    out.print_md(u"- ⚠ ไม่เจอ type ตะเข้สัน (ชื่อมีคำว่า `ตะเข้`) — ใช้ `{}` แทน".format(
                 ename(hip_sym)))
if err:
    out.print_md(u"- สร้างไม่สำเร็จ: {} เส้น".format(err))
out.print_md(u"")
out.print_md(u"ไม่พอใจผลลัพธ์ → **Ctrl+Z** ครั้งเดียวย้อนได้ทั้งหมด")
out.print_md(u"ปรับความลึกได้ที่ CONFIG: VERTICAL_OFFSET_MM / เปิด-ปิดสัน-ตะเข้: "
             u"INCLUDE_RIDGE / INCLUDE_HIP — แนวราง (พับเว้า) ข้ามให้อัตโนมัติ "
             u"ใช้ปุ่ม **Valley Gen** แทน")
