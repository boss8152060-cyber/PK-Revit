# -*- coding: utf-8 -*-
"""Valley Gen — สร้าง "ตะเข้ราง" + "รางน้ำ" อัตโนมัติทุกแนวรางหลังคา

ทำตามขั้นตอนมือของทู 4 เฟส:
  Phase 1  หาแนวรางหลังคา (Valley Line) = แนวพับที่ผืนสองข้าง "ยกขึ้น"
           ออกจากแนว (พับเว้า/concave — น้ำไหลลงราง) ต่างจากตะเข้สัน/สัน
           ที่ผืนสองข้างกดลง (พับนูน/convex)
  Phase 2  วางรางน้ำ: คานเหล็กตัวซี type "รางน้ำ" ตามแนวราง คาลิเบรตระดับ
           แล้วดรอปลงตาม GUTTER_DROP_MM (+หมุนหน้าตัดได้ตาม config)
  Phase 3  วางตะเข้ราง: type "ตะเข้ราง" (แยก type ชัดเจนเพื่อ BOQ)
           คาลิเบรตระดับยอดแนบผิวหลังคา — รับจันทัน/แปที่วิ่งมาพาดพอดี
           (ไม่เจอ type → Duplicate จาก type ตะเข้สันแล้ว rename ให้อัตโนมัติ)
  Phase 4  จุดต่อ: ตะเข้ราง type ชื่อมีคำว่า "ตะเข้" → กด Rafter Gen ซ้ำ
           หัวจันทันจะถูกเล็ม+ตัดด้วยใบมีด void ที่หน้าข้างตะเข้รางให้เอง
           (กลไก CUT_RAFTER_AT_HIP เดิม) / แนวรางเดิมที่ Hip Ridge Gen
           เคยวางเป็น "ตะเข้สัน" ผิดประเภทไว้ จะถูกล้างแทนที่ให้

ลำดับกดปุ่มที่ถูก: Hip Ridge Gen → Valley Gen → Rafter Gen → Purlin Gen
ย้อนกลับได้ด้วย Ctrl+Z ครั้งเดียว
"""

import math
import os
from System.Collections.Generic import List
from pyrevit import revit, DB, forms, script

doc = revit.doc
out = script.get_output()

# ===================== CONFIG =====================
VALLEY_TYPE_KEYWORDS = [u"ตะเข้ราง"]   # type ตะเข้ราง (ไม่เจอ → duplicate จากตะเข้สัน)
GUTTER_TYPE_KEYWORDS = [u"รางน้ำ"]     # type รางน้ำ (ไม่เจอ → duplicate จากตะเข้สัน)
BASE_TYPE_KEYWORDS = [u"ตะเข้สัน"]     # type ต้นทางเวลา duplicate
BASE_FALLBACK_KEYWORDS = [u"จันทัน"]   # ต้นทางสำรองถ้าไม่มีตะเข้สัน

CREATE_VALLEY = True         # Phase 3: สร้างตะเข้ราง
CREATE_GUTTER = True         # Phase 2: สร้างรางน้ำ

VALLEY_OFFSET_MM = 0.0       # จมเพิ่มของตะเข้รางจากระดับ "ยอดแนบระนาบผืน" (มม.)
                             # 0 = ยอดเสมอผิวเหมือนจันทัน (อยู่ในตัวหลังคา)
VALLEY_SIDE_OFFSET_MM = 100.0  # ตะเข้รางวาง "คู่ขนาบสองข้าง" แนวราง ห่างจากแกน
                             # ข้างละเท่านี้ (มม.) — แต่ละตัวเอียงตามลาดผืนฝั่งตัวเอง
                             # และจมในหลังคาเสมอระดับจันทัน / 0 = ตัวเดียวบนแกนราง
VALLEY_ROTATE_WITH_SLOPE = True  # หมุนหน้าตัดตะเข้รางแนบลาดผืนฝั่งตัวเอง
VALLEY_OPEN_INWARD = True    # หันปากหน้าตัด C ของคู่ตะเข้รางเข้าหากัน
                             # (วัดจากเนื้อจริง: centroid อยู่ฝั่งหลัง C —
                             # ถ้าปากหันออก กลับทิศแกนให้เอง) False = ตามเดิม
GUTTER_RISE_MM = 110.0       # รางน้ำ "ยกขึ้น" จากแนวราง (มม.) ให้ปีกสองข้าง
                             # พาดปิดหลังแปพอดี — ทูจูนเอง 11 ก.ค.:
                             # z Offset +10 จากรุ่นยก 100 → 110
GUTTER_CS_ANGLE_DEG = 0.0    # หมุนหน้าตัดรางน้ำรอบแกน (องศา — ปรับตามหน้างาน)
TRIM_PURLIN_AT_GUTTER = True  # ตัดปลายแปที่โผล่เข้าเขตรางน้ำ ให้จบที่ขอบราง
                              # พอดี (วัดครึ่งกว้างรางจากเนื้อจริง + ใบมีด void)
PURLIN_TRIM_EXTRA_MM = 0.0    # ร่นปลายแปจากขอบรางเพิ่มอีก (มม.)
VOID_FAM_NAME = u"REVOTECH_MiterVoidXXS"   # family ใบมีดตัวเดียวกับ Purlin Gen

MIN_LEN_MM = 150.0           # แนวสั้นกว่านี้ไม่สร้าง
MIN_FOLD_DEG = 8.0           # มุมระหว่างผืนสองข้างต้องเกินนี้ = แนวพับจริง
MAX_SLOPE_DEG = 60.0         # แนวพับที่ชันกว่านี้ไม่ใช่ราง (ขอบรอยต่อระดับหลังคา
                             # เกือบดิ่ง — กันคานโด่ขึ้นฟ้า)
SIDE_PROBE_MM = 200.0        # ระยะจิ้มสองข้างแนวพับ เพื่อเช็คว่าผืนยกขึ้น (ราง)
                             # หรือกดลง (ตะเข้สัน)
CLEAN_HIP_ON_VALLEY = True   # ล้าง "ตะเข้สัน" ที่ Hip Ridge Gen เคยวางผิดบนแนวราง
Z_JUSTIFY = u"top"           # จุดอ้างอิงหน้าตัด
DELETE_OLD = True            # ลบตะเข้ราง/รางน้ำเดิมก่อนสร้างใหม่
AUTO_ROOF_JOIN = True        # จอยตะเข้ราง↔ผืนหลังคา กันปริมาตรนับซ้ำ
MATERIAL_NAME = u""          # ตั้ง Structural Material (ว่าง = ค่าเดิมของ family)
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
SIDE_PROBE = mm_to_ft(SIDE_PROBE_MM)


def is_roof(e):
    return cat_id(e) == int(DB.BuiltInCategory.OST_Roofs)


def match_kw(name, kws):
    low = name.lower()
    return all(kw.lower() in low for kw in kws)


# ---------- Phase 1: ผืนหลังคา (เก็บทั้ง normal และเส้นขอบ polygon) ----------
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
            if loops:
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


def key_pt(p):
    return (int(round(p.X * FT_TO_MM)),
            int(round(p.Y * FT_TO_MM)),
            int(round(p.Z * FT_TO_MM)))


def edge_key(a, b):
    ka, kb = key_pt(a), key_pt(b)
    return (ka, kb) if ka <= kb else (kb, ka)


DIAG = {"shared": 0, "flat_pair": 0, "fold": 0, "steep_edge": 0,
        "not_concave": 0, "concave": 0, "clip_in": 0, "clip_out": 0}


def collect_valley_edges(faces):
    """คืนท่อนแนวราง (พับเว้า): list ของ (a, b, roof)
    วิธี: ขอบร่วม ≥2 ผืน + มุมพับจริง แล้วเช็คสองข้างแนวพับ —
    ผืนสองข้าง "ยกขึ้น" ออกจากแนว = ราง (น้ำไหลเข้า) / กดลง = ตะเข้สัน (ข้าม)"""
    edges = {}
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
                    edges[k] = [a, b, [fi]]
    valley = []
    for k, v in edges.items():
        fis = v[2]
        if len(fis) < 2:
            continue                       # ขอบผืนเดียว = ชายคา
        DIAG["shared"] += 1
        a, b = v[0], v[1]
        # มุมพับจริง (กันชิ้นย่อยผิวเรียบจากรอยจอย) — จับคู่เฉพาะ "ผืนลาด
        # ปกติ" เท่านั้น: คัดผืนชันเกิน MAX_SLOPE_DEG (แถบรอยต่อระดับหลังคา
        # เกือบดิ่ง) ออกก่อนจับคู่ ไม่ใช่คัดทีหลัง (ขอบเดียวอาจมีทั้งแถบชัน
        # และผืนลาดจริงมาแชร์ — อย่าให้แถบชันพาทั้งขอบโดนทิ้ง)
        cos_max = math.cos(math.radians(MAX_SLOPE_DEG))
        flats = [fi for fi in fis if faces[fi]["n"].Z >= cos_max]
        if len(flats) < 2:
            DIAG["flat_pair"] += 1
            continue
        max_ang, pair = 0.0, None
        for i in range(len(flats)):
            for j in range(i + 1, len(flats)):
                ni, nj = faces[flats[i]]["n"], faces[flats[j]]["n"]
                dot = max(-1.0, min(1.0, ni.X * nj.X + ni.Y * nj.Y
                                    + ni.Z * nj.Z))
                ang = math.degrees(math.acos(dot))
                if ang > max_ang:
                    max_ang = ang
                    pair = (flats[i], flats[j])
        if max_ang < MIN_FOLD_DEG or pair is None:
            DIAG["fold"] += 1
            continue
        # ขอบรอยต่อระดับหลังคาเกือบดิ่งไม่ใช่ราง (กันคานโด่ขึ้นฟ้า)
        dzs = abs(a.Z - b.Z)
        dxys = math.sqrt((a.X - b.X) ** 2 + (a.Y - b.Y) ** 2)
        slope_deg = math.degrees(math.atan2(dzs, dxys)) if dxys > 1e-9 else 90.0
        if slope_deg > MAX_SLOPE_DEG:
            DIAG["steep_edge"] += 1
            continue
        if _is_concave(a, b, pair[0], pair[1], faces):
            DIAG["concave"] += 1
            valley.append((a, b, faces[pair[0]]["roof"], pair[0], pair[1]))
        else:
            DIAG["not_concave"] += 1
    return merge_collinear(valley)


def _is_concave(a, b, fiA, fiB, faces):
    """True ถ้าแนวพับนี้เป็น "ราง": ผืนทั้งสองข้างยกขึ้นออกจากแนวพับ"""
    mx, my, mz = (a.X + b.X) / 2.0, (a.Y + b.Y) / 2.0, (a.Z + b.Z) / 2.0
    dx, dy = b.X - a.X, b.Y - a.Y
    dl = math.sqrt(dx * dx + dy * dy)
    if dl < 1e-9:
        return False                       # แนวดิ่ง — ไม่ใช่ราง
    vx, vy = -dy / dl, dx / dl             # ตั้งฉากแนวพับใน plan

    def side_of(fd):
        if point_in_face(fd, mx + vx * SIDE_PROBE, my + vy * SIDE_PROBE):
            return 1
        if point_in_face(fd, mx - vx * SIDE_PROBE, my - vy * SIDE_PROBE):
            return -1
        return 0

    def rise(fd, s):
        # ระนาบผืนผ่านแนวพับ: z ที่จุดจิ้มฝั่งตัวเอง เทียบ z แนวพับ
        n = fd["n"]
        px, py = mx + vx * SIDE_PROBE * s, my + vy * SIDE_PROBE * s
        z = mz - (n.X * (px - mx) + n.Y * (py - my)) / n.Z
        return z - mz

    sA = side_of(faces[fiA])
    sB = side_of(faces[fiB])
    if sA == 0 or sB == 0 or sA == sB:
        return False                       # ระบุฝั่งไม่ได้/ซ้อนฝั่งเดียว
    thr = mm_to_ft(10.0)
    return rise(faces[fiA], sA) > thr and rise(faces[fiB], sB) > thr


def merge_collinear(pieces):
    """รวมท่อนที่อยู่บนเส้นตรงเดียวกันเป็นเส้นเดียว (ขอบโดนรอยบากตัดเป็นท่อน)
    พกดัชนีผืนสองข้าง (fiA, fiB) ติดไปด้วยไว้ใช้เอียง/ตั้งระดับรายฝั่ง"""
    groups = {}
    for a, b, roof, fiA, fiB in pieces:
        d = b - a
        L = d.GetLength()
        if L < 1e-9:
            continue
        d = d.Normalize()
        if (d.X < -1e-9 or (abs(d.X) <= 1e-9 and d.Y < -1e-9)
                or (abs(d.X) <= 1e-9 and abs(d.Y) <= 1e-9 and d.Z < 0)):
            d = d.Negate()
        mom = a.CrossProduct(d)
        key = (int(round(d.X * 1000)), int(round(d.Y * 1000)),
               int(round(d.Z * 1000)),
               int(round(mom.X * FT_TO_MM)), int(round(mom.Y * FT_TO_MM)),
               int(round(mom.Z * FT_TO_MM)))
        g = groups.get(key)
        if g is None:
            groups[key] = {"a0": a, "d": d, "roof": roof,
                           "fiA": fiA, "fiB": fiB,
                           "tmin": 0.0, "tmax": L}
        else:
            a0, dd = g["a0"], g["d"]
            for p in (a, b):
                t = dd.DotProduct(p - a0)
                if t < g["tmin"]:
                    g["tmin"] = t
                if t > g["tmax"]:
                    g["tmax"] = t
    lines = []
    for g in groups.values():
        p0 = g["a0"] + g["d"] * g["tmin"]
        p1 = g["a0"] + g["d"] * g["tmax"]
        if p0.DistanceTo(p1) >= MIN_LEN:
            lines.append((p0, p1, g["roof"], g["fiA"], g["fiB"]))
    return lines


def _plane_key(fd):
    """คีย์ระนาบของผืน (normal + ระยะระนาบ) — ผืนที่ถูกจอยแตกเป็นชิ้นย่อย
    หลายชิ้นแต่อยู่ระนาบเดียวกัน จะได้คีย์เดียวกัน"""
    n = fd["n"]
    v0 = fd["loops"][0][0]
    d = n.X * v0[0] + n.Y * v0[1] + n.Z * v0[2]
    return (int(round(n.X * 100)), int(round(n.Y * 100)),
            int(round(n.Z * 100)), int(round(d * FT_TO_MM / 10.0)))


def clip_valley_lines(lines, faces):
    """เก็บเฉพาะช่วงของแนวรางที่มี "เนื้อผืนทั้งสองข้างจริง" — กันเส้นผี:
    แนวตัดระนาบของหลังคาสองตัวที่ join กันวิ่งยาวเลยขอบหลังคาจริงออกไป
    (โซนชายคา overlap) → คานพุ่งออกนอกหลังคา — สแกนตามเส้นทีละ ~200มม.
    จุดไหนหาผืนสองฝั่งไม่ครบ ตัดช่วงนั้นทิ้ง (เส้นเดียวแตกได้หลายท่อน)
    ⚠ ผืนที่ถูกจอยแตกเป็นชิ้นย่อย — ต้องเช็คกับ "ทุกชิ้นบนระนาบเดียวกัน"
    ไม่ใช่เฉพาะชิ้นที่บังเอิญแชร์ขอบ (ไม่งั้นรางที่พาดผ่านหลายชิ้นโดนตัดทิ้งหมด)"""
    probe = mm_to_ft(100.0)
    DIAG["clip_in"] = len(lines)
    # จัดกลุ่มผืนตามระนาบ
    plane_members = {}
    for fi in range(len(faces)):
        plane_members.setdefault(_plane_key(faces[fi]), []).append(fi)
    out_lines = []
    for p0, p1, roof, fiA, fiB in lines:
        L = p0.DistanceTo(p1)
        nseg = max(int(math.ceil(L / mm_to_ft(200.0))), 4)
        dx, dy = p1.X - p0.X, p1.Y - p0.Y
        dl = math.sqrt(dx * dx + dy * dy)
        if dl < 1e-9:
            continue
        vx, vy = -dy / dl, dx / dl
        candA = plane_members.get(_plane_key(faces[fiA]), [fiA])
        candB = plane_members.get(_plane_key(faces[fiB]), [fiB])
        good = []
        for i in range(nseg + 1):
            t = float(i) / nseg
            mx, my = p0.X + dx * t, p0.Y + dy * t
            ok = 0
            for cand in (candA, candB):
                hit = False
                for fi in cand:
                    fd = faces[fi]
                    if (point_in_face(fd, mx + vx * probe, my + vy * probe)
                            or point_in_face(fd, mx - vx * probe,
                                             my - vy * probe)):
                        hit = True
                        break
                if hit:
                    ok += 1
            good.append(ok == 2)
        i = 0
        while i <= nseg:
            if not good[i]:
                i += 1
                continue
            j = i
            while j + 1 <= nseg and good[j + 1]:
                j += 1
            t0, t1 = float(i) / nseg, float(j) / nseg
            q0 = DB.XYZ(p0.X + (p1.X - p0.X) * t0,
                        p0.Y + (p1.Y - p0.Y) * t0,
                        p0.Z + (p1.Z - p0.Z) * t0)
            q1 = DB.XYZ(p0.X + (p1.X - p0.X) * t1,
                        p0.Y + (p1.Y - p0.Y) * t1,
                        p0.Z + (p1.Z - p0.Z) * t1)
            if q0.DistanceTo(q1) >= MIN_LEN:
                out_lines.append((q0, q1, roof, fiA, fiB))
            i = j + 1
    DIAG["clip_out"] = len(out_lines)
    return out_lines


# ---------- Phase 1 (วิธีหลัก): แนวราง = เส้นตัดของระนาบหลังคาสองผืน ----------
# ตามสเปคทูตรงตัว — ไม่พึ่ง "ขอบร่วม" เลย เพราะร่องตรงรอยต่อระดับหลังคา
# (คนละ Roof วางชิดกัน) ผืนสองข้างไม่แชร์ขอบกันจริง ขอบร่วมมีแต่เศษ ghost
def collect_valley_lines(faces):
    """คืน list ของ (a, b, roof, fiA, fiB, sideA):
    1) จัดกลุ่มผืนตามระนาบ (ผืนโดนจอยแตกชิ้น = กลุ่มเดียวกัน)
    2) จับคู่ระนาบลาดปกติทุกคู่ → คำนวณเส้นตัดระนาบ
    3) ราง = แต่ละผืนอยู่ "ฝั่งที่ระนาบตัวเองสูงกว่า" (เว้า น้ำไหลลง)
    4) เดินสแกนตามเส้นทีละ ~200มม. เก็บช่วงที่มีเนื้อผืนจริงทั้งสองฝั่ง"""
    cosmax = math.cos(math.radians(MAX_SLOPE_DEG))
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
    DIAG["planes"] = len(keys)
    probe = mm_to_ft(150.0)
    zthr = mm_to_ft(10.0)
    step = mm_to_ft(200.0)
    out = []

    def zon(P, x, y):
        return (P["d"] - P["n"].X * x - P["n"].Y * y) / P["n"].Z

    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            A, B = planes[keys[i]], planes[keys[j]]
            nA, nB = A["n"], B["n"]
            kk = max(-1.0, min(1.0, nA.DotProduct(nB)))
            if math.degrees(math.acos(kk)) < MIN_FOLD_DEG:
                continue                # เกือบขนานกัน ไม่มีรอยพับจริง
            u = nA.CrossProduct(nB)
            if u.GetLength() < 1e-6:
                continue
            u = u.Normalize()
            uh = math.sqrt(u.X * u.X + u.Y * u.Y)
            if uh < 1e-9:
                continue                # เส้นตัดดิ่ง
            if math.degrees(math.atan2(abs(u.Z), uh)) > MAX_SLOPE_DEG:
                continue                # เส้นตัดชันผิดปกติ
            den = 1.0 - kk * kk
            al = (A["d"] - B["d"] * kk) / den
            be = (B["d"] - A["d"] * kk) / den
            x0 = DB.XYZ(nA.X * al + nB.X * be, nA.Y * al + nB.Y * be,
                        nA.Z * al + nB.Z * be)
            # ช่วงบนเส้นที่สองกลุ่มผืนครอบคลุมร่วมกัน (ฉายจุดยอดลงแกนเส้น)
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
            vx, vy = -u.Y / uh, u.X / uh    # ตั้งฉากเส้นใน plan
            # ฝั่งของ A = ฝั่งที่ระนาบ A "สูงกว่า" (คงที่ตลอดเส้น) — เว้า =
            # ผืนอยู่ฝั่งระนาบตัวเองสูงกว่า แล้วให้เนื้อผืนจริงเป็นตัวตัดสิน
            mx0 = x0.X + u.X * (t0 + t1) / 2.0
            my0 = x0.Y + u.Y * (t0 + t1) / 2.0
            zAp = zon(A, mx0 + vx * probe, my0 + vy * probe)
            zBp = zon(B, mx0 + vx * probe, my0 + vy * probe)
            if zAp > zBp + zthr:
                sA = 1
            elif zBp > zAp + zthr:
                sA = -1
            else:
                continue
            nseg = max(int(math.ceil((t1 - t0) / step)), 4)
            good = []
            for s in range(nseg + 1):
                t = t0 + (t1 - t0) * s / nseg
                mx = x0.X + u.X * t
                my = x0.Y + u.Y * t
                okA = False
                for fi in A["members"]:
                    if point_in_face(faces[fi], mx + vx * probe * sA,
                                     my + vy * probe * sA):
                        okA = True
                        break
                okB = False
                if okA:
                    for fi in B["members"]:
                        if point_in_face(faces[fi], mx - vx * probe * sA,
                                         my - vy * probe * sA):
                            okB = True
                            break
                good.append(okA and okB)
            s = 0
            fiA, fiB = A["members"][0], B["members"][0]
            roof = faces[fiA]["roof"]
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
                    out.append((pa, pb, roof, fiA, fiB, sA))
                s = e + 1
    DIAG["lines"] = len(out)
    return out


# ---------- คาลิเบรตระดับ: เนื้อคานโผล่เหนือ "ระนาบผืน" เท่าไหร่ ----------
def max_above_plane(g, n, px, py, pz):
    """ระยะ (ตามแนว normal) ที่จุดเนื้อสูงสุดอยู่เหนือระนาบผ่าน (px,py,pz)"""
    best = [None]

    def walk(geo):
        for obj in geo:
            if isinstance(obj, DB.GeometryInstance):
                walk(obj.GetInstanceGeometry())
            elif isinstance(obj, DB.Solid) and obj.Volume > 1e-9:
                for e in obj.Edges:
                    for p in e.Tessellate():
                        d = (n.X * (p.X - px) + n.Y * (p.Y - py)
                             + n.Z * (p.Z - pz))
                        if best[0] is None or d > best[0]:
                            best[0] = d
    walk(g)
    return best[0]


def rotate_to_face(inst, axis_u, n):
    """หมุนหน้าตัดรอบแกนคานให้แกนตั้งหน้าตัดทับ normal ผืน (แนบลาดฝั่งตัวเอง)
    — ทิศหมุนของ Revit เดาไม่ได้ ลองทั้ง ± แล้ววัดจริงจาก BasisZ"""
    z0 = DB.XYZ(0.0, 0.0, 1.0) - axis_u * axis_u.Z
    if z0.GetLength() < 1e-9:
        return
    z0 = z0.Normalize()
    cosang = max(-1.0, min(1.0, z0.DotProduct(n)))
    ang = math.acos(cosang)
    if ang < 1e-4:
        return
    try:
        pr = inst.get_Parameter(DB.BuiltInParameter.STRUCTURAL_BEND_DIR_ANGLE)
        if pr is None or pr.IsReadOnly:
            return
        pr.Set(ang)
        doc.Regenerate()
        dplus = inst.GetTransform().BasisZ.DotProduct(n)
        pr.Set(-ang)
        doc.Regenerate()
        dminus = inst.GetTransform().BasisZ.DotProduct(n)
        if dplus >= dminus:
            pr.Set(ang)
    except Exception:
        pass


def _pt_to_seg(p, a, b):
    dx, dy, dz = b.X - a.X, b.Y - a.Y, b.Z - a.Z
    L2 = dx * dx + dy * dy + dz * dz
    if L2 < 1e-12:
        return p.DistanceTo(a)
    t = ((p.X - a.X) * dx + (p.Y - a.Y) * dy + (p.Z - a.Z) * dz) / L2
    t = max(0.0, min(1.0, t))
    return p.DistanceTo(DB.XYZ(a.X + dx * t, a.Y + dy * t, a.Z + dz * t))


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


def _solid_centroid(g):
    """centroid ของ solid ก้อนใหญ่สุดใน geometry (คืน XYZ หรือ None)"""
    best = [None, 0.0]

    def walk(geo):
        for obj in geo:
            if isinstance(obj, DB.GeometryInstance):
                walk(obj.GetInstanceGeometry())
            elif isinstance(obj, DB.Solid) and obj.Volume > best[1]:
                best[0] = obj
                best[1] = obj.Volume
    walk(g)
    if best[0] is None:
        return None
    try:
        return best[0].ComputeCentroid()
    except Exception:
        return None


def ensure_opening_inward(inst, a2, b2, out_x, out_y, n):
    """หันปากหน้าตัด C เข้าหาแกนราง — วิธีไม่พึ่งตำแหน่ง origin ของ family:
    ดูการกระจายเนื้อจริงตามแนวขวาง — centroid ของ C อยู่ "ใกล้ขอบฝั่ง web"
    (หลัง) มากกว่าฝั่งปากเสมอ → ต้องการปากหันเข้าราง = web อยู่ฝั่งนอก
    = centroid ใกล้ขอบนอก / ถ้า centroid ใกล้ขอบใน = ปากหันออก →
    หมุนหน้าตัดเพิ่ม 180° (C สมมาตรบน-ล่าง หมุนครึ่งรอบ = กระจก
    ซ้าย-ขวาของปากพอดี — ห้ามใช้วิธีกลับทิศแกน+คาลิเบรตซ้ำ มันหักล้างกัน)"""
    ol = math.sqrt(out_x * out_x + out_y * out_y)
    if ol < 1e-9:
        return
    ux, uy = out_x / ol, out_y / ol
    mx, my = (a2.X + b2.X) / 2.0, (a2.Y + b2.Y) / 2.0
    try:
        doc.Regenerate()
        geo = inst.get_Geometry(DB.Options())
        c = _solid_centroid(geo)
        if c is None:
            return
        vals = []

        def walk(g):
            for obj in g:
                if isinstance(obj, DB.GeometryInstance):
                    walk(obj.GetInstanceGeometry())
                elif isinstance(obj, DB.Solid) and obj.Volume > 1e-9:
                    for e in obj.Edges:
                        for p in e.Tessellate():
                            vals.append((p.X - mx) * ux + (p.Y - my) * uy)
        walk(geo)
        if not vals:
            return
        lmin, lmax = min(vals), max(vals)
        lc = (c.X - mx) * ux + (c.Y - my) * uy
        if (lc - lmin) < (lmax - lc):    # centroid ใกล้ขอบใน = web อยู่ใน
            pr = inst.get_Parameter(       # = ปากหันออก → หมุนกลับ
                DB.BuiltInParameter.STRUCTURAL_BEND_DIR_ANGLE)
            if pr is None or pr.IsReadOnly:
                return
            pr.Set(pr.AsDouble() + math.pi)
            doc.Regenerate()
    except Exception:
        pass


def set_cs_rotation(inst, deg):
    if abs(deg) < 1e-6:
        return
    try:
        pr = inst.get_Parameter(DB.BuiltInParameter.STRUCTURAL_BEND_DIR_ANGLE)
        if pr is not None and not pr.IsReadOnly:
            pr.Set(math.radians(deg))
    except Exception:
        pass


def _halfwidth_along(elem, px, py):
    """ครึ่งความกว้าง (แนวราบ) ของ solid ตามทิศ (px,py) — วัดจากเนื้อจริง"""
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


def find_void_symbol():
    for f in DB.FilteredElementCollector(doc).OfClass(DB.Family):
        if ename(f) == VOID_FAM_NAME:
            for sid in f.GetFamilySymbolIds():
                return doc.GetElement(sid)
    return None


# ---------- หา/สร้าง type (Duplicate & Rename ตามขั้นตอนมือ) ----------
def find_type(kw_list):
    for t in DB.FilteredElementCollector(doc) \
              .OfCategory(DB.BuiltInCategory.OST_StructuralFraming) \
              .WhereElementIsElementType():
        if match_kw(ename(t), kw_list):
            return t
    return None


def dup_type(base_sym, want_word):
    """Duplicate type ต้นทางแล้วตั้งชื่อใหม่ให้มีคำว่า want_word (ทำใน Transaction)"""
    nm = ename(base_sym)
    if u"ตะเข้สัน" in nm:
        new_name = nm.replace(u"ตะเข้สัน", want_word)
    elif u"จันทัน" in nm:
        new_name = nm.replace(u"จันทัน", want_word)
    else:
        new_name = nm + u" " + want_word
    for suffix in [u""] + [u" {}".format(i) for i in range(2, 10)]:
        try:
            return doc.GetElement(base_sym.Duplicate(new_name + suffix).Id)
        except Exception:
            continue
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

all_framing = list(DB.FilteredElementCollector(doc)
                   .OfCategory(DB.BuiltInCategory.OST_StructuralFraming)
                   .WhereElementIsNotElementType()
                   .ToElements())
old_own = [e for e in all_framing
           if match_kw(type_name(e), VALLEY_TYPE_KEYWORDS)
           or match_kw(type_name(e), GUTTER_TYPE_KEYWORDS)]

# level สำรอง
fb_level = None
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

tg = DB.TransactionGroup(doc, "REVOTECH - Valley Gen")
tg.Start()

# ลบตะเข้ราง/รางน้ำเดิมก่อนอ่านผืน (กันรอยจอยเก่าทำขอบผืนเพี้ยน)
with revit.Transaction("REVOTECH - Valley Gen (ลบของเดิม)",
                       swallow_errors=True):
    if DELETE_OLD and old_own:
        doc.Delete(List[DB.ElementId]([e.Id for e in old_own]))
    # ลบใบมีดตัดแปของรอบก่อน (มาร์ก [แป-ราง]) กันซ้อนสะสม
    stale_b = []
    for gm in DB.FilteredElementCollector(doc) \
               .OfCategory(DB.BuiltInCategory.OST_GenericModel) \
               .WhereElementIsNotElementType():
        try:
            if not gm.Symbol.Family.Name.startswith(u"REVOTECH_MiterVoid"):
                continue
            cmv = gm.get_Parameter(
                DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if cmv is not None and u"[แป-ราง]" in (cmv.AsString() or u""):
                gm.Pinned = False
                stale_b.append(gm.Id)
        except Exception:
            pass
    if stale_b:
        doc.Delete(List[DB.ElementId](stale_b))

# Phase 1: หาแนวราง
faces = collect_roof_faces(roofs)
if not faces:
    tg.RollBack()
    forms.alert(u"หาผืนหลังคา (top face) ไม่เจอ", exitscript=True)
valleys = collect_valley_lines(faces)
out.print_md(u"พบผืนหลังคา **{} ผืน** / แนวราง (พับเว้า) **{} เส้น** / "
             u"ตะเข้ราง+รางน้ำเดิม {} ตัว".format(
                 len(faces), len(valleys), len(old_own)))
out.print_md(u"วินิจฉัย: ระนาบผืนลาด **{} กลุ่ม** → สแกนเส้นตัดระนาบทุกคู่ "
             u"(เว้า+มีเนื้อผืนสองฝั่ง) → แนวราง **{} เส้น**".format(
                 DIAG.get("planes", 0), DIAG.get("lines", 0)))
if not valleys:
    tg.RollBack()
    forms.alert(u"ไม่พบแนวรางหลังคา (แนวพับเว้าที่น้ำไหลลง) — "
                u"หลังคานี้อาจไม่มีราง (ทรงปั้นหยาเดี่ยวไม่มีมุมหักเข้า)",
                exitscript=True)

# ล้าง "ตะเข้สัน" ที่เคยถูกวางผิดบนแนวราง (จาก Hip Ridge Gen รุ่นที่ไม่แยกราง)
cleaned = 0
if CLEAN_HIP_ON_VALLEY:
    with revit.Transaction("REVOTECH - Valley Gen (ล้างตะเข้สันบนราง)",
                           swallow_errors=True):
        tol = mm_to_ft(100.0)
        doomed = []
        for e in all_framing:
            tn = type_name(e)
            if not match_kw(tn, [u"ตะเข้"]):
                continue
            if match_kw(tn, VALLEY_TYPE_KEYWORDS):
                continue                    # ตะเข้รางของเราเอง (ลบไปแล้ว)
            try:
                crv = e.Location.Curve
                e0, e1 = crv.GetEndPoint(0), crv.GetEndPoint(1)
            except Exception:
                continue
            for a, b, roof, fiA, fiB, sA in valleys:
                if _pt_to_seg(e0, a, b) < tol and _pt_to_seg(e1, a, b) < tol:
                    doomed.append(e.Id)
                    break
        if doomed:
            doc.Delete(List[DB.ElementId](doomed))
            cleaned = len(doomed)

# เตรียม type (Duplicate & Rename อัตโนมัติถ้ายังไม่มี)
valley_sym, gutter_sym = None, None
valley_dup, gutter_dup = False, False
with revit.Transaction("REVOTECH - Valley Gen (เตรียม type)",
                       swallow_errors=True):
    base = find_type(BASE_TYPE_KEYWORDS) or find_type(BASE_FALLBACK_KEYWORDS)
    if CREATE_VALLEY:
        valley_sym = find_type(VALLEY_TYPE_KEYWORDS)
        if valley_sym is None and base is not None:
            valley_sym = dup_type(base, u"ตะเข้ราง")
            valley_dup = valley_sym is not None
    if CREATE_GUTTER:
        gutter_sym = find_type(GUTTER_TYPE_KEYWORDS)
        if gutter_sym is None and base is not None:
            gutter_sym = dup_type(base, u"รางน้ำ")
            gutter_dup = gutter_sym is not None

if CREATE_VALLEY and valley_sym is None:
    tg.RollBack()
    forms.alert(u"หา/สร้าง type ตะเข้ราง ไม่ได้ — โหลด family เหล็กตัวซี "
                u"แล้วตั้งชื่อ type ให้มีคำว่า \"ตะเข้ราง\" ก่อน", exitscript=True)

# Phase 2+3: วางตะเข้ราง + รางน้ำ
created_v, created_g, err = 0, 0, 0
total_len = 0.0
recs_v = []      # (inst, a, b)  — อ้างอิงแนวรางไว้คาลิเบรตระดับ
recs_g = []
inst_roofs = []

with revit.Transaction("REVOTECH - Valley Gen (สร้าง)", swallow_errors=True):
    for _s in (valley_sym, gutter_sym):
        if _s is not None and not _s.IsActive:
            _s.Activate()
    doc.Regenerate()
    side_off = mm_to_ft(VALLEY_SIDE_OFFSET_MM)
    rise_g = mm_to_ft(GUTTER_RISE_MM)
    for a, b, roof, fiA, fiB, sA in valleys:
        lvl = level_for(roof)
        dx, dy = b.X - a.X, b.Y - a.Y
        dl = math.sqrt(dx * dx + dy * dy)
        vx, vy = (-dy / dl, dx / dl) if dl > 1e-9 else (0.0, 0.0)
        # ตะเข้ราง: คู่ขนาบสองข้างแนวราง — แต่ละตัวยกขึ้นบนระนาบผืนฝั่งตัวเอง
        # แล้วเอียงหน้าตัดตามลาด (= จันทันที่วิ่งเลียบราง) — ฝั่งของแต่ละผืน
        # (sA) มาจากตัวหาแนวรางแล้ว / side_off=0 → ตัวเดียวบนแกนราง
        if CREATE_VALLEY and valley_sym is not None:
            if side_off > 1e-9 and dl > 1e-9 and sA != 0:
                sides = [(fiA, sA), (fiB, -sA)]
            else:
                sides = [(fiA, 0)]
            for fi, s in sides:
                n = faces[fi]["n"]
                ox, oy = vx * side_off * s, vy * side_off * s
                # ยกตามระนาบผืน: แนวรางอยู่บนระนาบ เลื่อนข้างต้องไต่ขึ้นตามลาด
                rise = -(n.X * ox + n.Y * oy) / n.Z if s else 0.0
                try:
                    a2 = DB.XYZ(a.X + ox, a.Y + oy, a.Z + rise)
                    b2 = DB.XYZ(b.X + ox, b.Y + oy, b.Z + rise)
                    line = DB.Line.CreateBound(a2, b2)
                    inst = doc.Create.NewFamilyInstance(
                        line, valley_sym, lvl,
                        DB.Structure.StructuralType.Beam)
                    try:
                        DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(inst, 0)
                        DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(inst, 1)
                    except Exception:
                        pass
                    set_zjust(inst)
                    set_material(inst)
                    zero_extensions(inst)
                    if VALLEY_ROTATE_WITH_SLOPE and s:
                        rotate_to_face(inst, (b2 - a2).Normalize(), n)
                    if VALLEY_OPEN_INWARD and s:
                        ensure_opening_inward(inst, a2, b2, ox, oy, n)
                    recs_v.append((inst, a2, b2, n))
                    inst_roofs.append((inst, roof))
                    created_v += 1
                    total_len += a.DistanceTo(b)
                except Exception:
                    err += 1
        # รางน้ำ: บนแนวราง ยกขึ้น GUTTER_RISE_MM ให้ปีกพาดบนหลังแป
        if CREATE_GUTTER and gutter_sym is not None:
            try:
                line = DB.Line.CreateBound(
                    DB.XYZ(a.X, a.Y, a.Z + rise_g),
                    DB.XYZ(b.X, b.Y, b.Z + rise_g))
                inst = doc.Create.NewFamilyInstance(
                    line, gutter_sym, lvl, DB.Structure.StructuralType.Beam)
                try:
                    DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(inst, 0)
                    DB.Structure.StructuralFramingUtils.DisallowJoinAtEnd(inst, 1)
                except Exception:
                    pass
                set_zjust(inst)
                set_material(inst)
                zero_extensions(inst)
                set_cs_rotation(inst, GUTTER_CS_ANGLE_DEG)
                recs_g.append((inst, a, b))
                created_g += 1
            except Exception:
                err += 1

# ตั้งระดับตะเข้ราง: วัดเนื้อจริงที่โผล่เหนือ "ระนาบผืนฝั่งตัวเอง" แล้วกดจม
# ให้ยอดเสมอผิวเหมือนจันทัน (อยู่ในตัวหลังคา) — รางน้ำวางตามระดับที่ยกไว้แล้ว
low_v = 0.0
if recs_v:
    with revit.Transaction("REVOTECH - Valley Gen (ตั้งระดับ)",
                           swallow_errors=True):
        doc.Regenerate()
        for inst, a2, b2, n in recs_v:
            dz = mm_to_ft(VALLEY_OFFSET_MM)
            try:
                pr = max_above_plane(inst.get_Geometry(DB.Options()),
                                     n, a2.X, a2.Y, a2.Z)
            except Exception:
                pr = None
            if pr is not None and pr > mm_to_ft(0.5):
                dz += pr / max(n.Z, 0.05)     # ระยะ normal → แนวดิ่ง
            if abs(dz) > mm_to_ft(0.5):
                try:
                    DB.ElementTransformUtils.MoveElement(
                        doc, inst.Id, DB.XYZ(0.0, 0.0, -dz))
                    if dz * FT_TO_MM > low_v:
                        low_v = dz * FT_TO_MM
                except Exception:
                    pass

# ---------- ตัดปลายแปที่โผล่เข้าเขตรางน้ำ ให้จบที่ขอบรางพอดี ----------
# วางใบมีด void ระนาบดิ่ง "ขนานแนวราง" ที่ระยะครึ่งกว้างราง (วัดจากเนื้อจริง)
# แล้วสั่งตัดเฉพาะปลายแปที่ยื่นข้ามเข้าไป (กลไกเดียวกับตัดหัวจันทันที่ตะเข้)
trim_cut, trim_fail = 0, 0
if TRIM_PURLIN_AT_GUTTER and recs_g:
    void_sym = find_void_symbol()
    if void_sym is None:
        _here = os.path.dirname(__file__)
        _rfa = os.path.join(os.path.dirname(_here), u"PurlinGen.pushbutton",
                            VOID_FAM_NAME + u".rfa")
        if os.path.isfile(_rfa):
            try:
                with revit.Transaction("REVOTECH - โหลด MiterVoid"):
                    doc.LoadFamily(_rfa)
            except Exception:
                pass
            void_sym = find_void_symbol()
    if void_sym is not None:
        with revit.Transaction("REVOTECH - Valley Gen (ตัดแปพ้นรางน้ำ)",
                               swallow_errors=True):
            if not void_sym.IsActive:
                void_sym.Activate()
            doc.Regenerate()
            purlins = [e for e in DB.FilteredElementCollector(doc)
                       .OfCategory(DB.BuiltInCategory.OST_StructuralFraming)
                       .WhereElementIsNotElementType()
                       if u"แป" in type_name(e)]
            margin = mm_to_ft(400.0)
            sttol = mm_to_ft(200.0)
            ztol2 = mm_to_ft(600.0)
            pend = []
            for ginst, ga, gb in recs_g:
                gux, guy = gb.X - ga.X, gb.Y - ga.Y
                gl = math.sqrt(gux * gux + guy * guy)
                if gl < 1e-9:
                    continue
                gux, guy = gux / gl, guy / gl
                gvx, gvy = -guy, gux              # ตั้งฉากแนวราง (plan)
                hw = _halfwidth_along(ginst, gvx, gvy)
                if hw is None or hw < mm_to_ft(20.0):
                    hw = mm_to_ft(150.0)
                hw += mm_to_ft(PURLIN_TRIM_EXTRA_MM)
                for e in purlins:
                    try:
                        crv = e.Location.Curve
                        e0, e1 = crv.GetEndPoint(0), crv.GetEndPoint(1)
                    except Exception:
                        continue
                    for p, q in ((e0, e1), (e1, e0)):
                        sd_p = gvx * (p.X - ga.X) + gvy * (p.Y - ga.Y)
                        sd_q = gvx * (q.X - ga.X) + gvy * (q.Y - ga.Y)
                        if abs(sd_p) > hw + margin:
                            continue          # ปลายนี้ไม่ได้อยู่แถวราง
                        if abs(sd_q) <= hw:
                            continue          # อีกปลายก็อยู่ในราง — ผิดปกติ ข้าม
                        st = gux * (p.X - ga.X) + guy * (p.Y - ga.Y)
                        if st < -sttol or st > gl + sttol:
                            continue          # นอกช่วงความยาวรางเส้นนี้
                        gz = ga.Z + (gb.Z - ga.Z) * max(0.0, min(1.0, st / gl))
                        if abs(p.Z - gz) > ztol2:
                            continue          # คนละระดับ (รางหลังอื่น)
                        s = 1.0 if sd_q >= 0 else -1.0   # ฝั่งเนื้อแป
                        off = sd_p - hw * s   # ระยะปลายจากระนาบขอบราง
                        # กล่อง void (+Y) ต้องยื่นเข้าหาแกนราง = ฝั่งทิ้ง
                        Dx, Dy = -gvx * s, -gvy * s
                        theta = math.atan2(Dy, Dx) - math.pi / 2.0
                        # ใบมีดจิ๋ว XXS ลึกแค่ 15ซม. — เนื้อที่ต้องกินอาจลึกถึง
                        # กึ่งกลางราง → วางซ้อนเป็นชั้นเข้าไปจนคลุมครบ
                        blade_w = mm_to_ft(150.0)   # = ความหนา W ของ family XXS
                        need = max(0.0, (-off) * s) + mm_to_ft(50.0)
                        nlay = max(1, min(4, int(math.ceil(need / blade_w))))
                        for kk in range(nlay):
                            origin = DB.XYZ(
                                p.X - gvx * off + Dx * blade_w * kk,
                                p.Y - gvy * off + Dy * blade_w * kk, p.Z)
                            try:
                                vi = doc.Create.NewFamilyInstance(
                                    origin, void_sym,
                                    DB.Structure.StructuralType.NonStructural)
                                DB.ElementTransformUtils.RotateElement(
                                    doc, vi.Id,
                                    DB.Line.CreateBound(
                                        origin, origin + DB.XYZ(0, 0, 1.0)),
                                    theta)
                                cm = vi.get_Parameter(
                                    DB.BuiltInParameter
                                      .ALL_MODEL_INSTANCE_COMMENTS)
                                if cm is not None and not cm.IsReadOnly:
                                    cm.Set(u"REVOTECH MiterVoid [แป-ราง] - "
                                           u"ตัดปลายแปที่ขอบรางน้ำ (ย้าย/"
                                           u"คัดลอกไปพร้อมแปเสมอ)")
                                pend.append((vi, e))
                            except Exception:
                                trim_fail += 1
            doc.Regenerate()
            for vi, bm in pend:
                try:
                    DB.InstanceVoidCutUtils.AddInstanceVoidCut(doc, bm, vi)
                    trim_cut += 1
                except Exception:
                    trim_fail += 1

# จอยตะเข้ราง↔ผืนหลังคา (ตะเข้รางคงเนื้อเต็ม) กันปริมาตรนับซ้ำ
rj_done, rj_switch, rj_fail = 0, 0, 0
if AUTO_ROOF_JOIN and inst_roofs:
    with revit.Transaction("REVOTECH - Valley Gen (จอยหลังคา)",
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

out.print_md(u"## Valley Gen เสร็จแล้ว")
if cleaned:
    out.print_md(u"- ล้างตะเข้สันที่วางผิดบนแนวราง: **{} ตัว**".format(cleaned))
if CREATE_VALLEY:
    out.print_md(u"- ตะเข้ราง: **{} ตัว** / type `{}`{}{}".format(
        created_v, ename(valley_sym) if valley_sym else u"-",
        u" (Duplicate จากตะเข้สันให้ใหม่)" if valley_dup else u"",
        u" — คู่ขนาบข้างละ {:.0f} มม. เอียงตามลาดผืนฝั่งตัวเอง".format(
            VALLEY_SIDE_OFFSET_MM) if VALLEY_SIDE_OFFSET_MM > 0 else u""))
    out.print_md(u"- ตั้งระดับตะเข้ราง (คาลิเบรตจากเนื้อจริง): กดจมสูงสุด "
                 u"**{:.1f} มม.** → ยอดเสมอผิวเหมือนจันทัน อยู่ในตัวหลังคา{}".format(
                     low_v, u" + จม {:.0f} มม.".format(VALLEY_OFFSET_MM)
                     if VALLEY_OFFSET_MM else u""))
if CREATE_GUTTER:
    out.print_md(u"- รางน้ำ: **{} ตัว** / type `{}`{}".format(
        created_g, ename(gutter_sym) if gutter_sym else u"-",
        u" (Duplicate ให้ใหม่ — ถ้ามี family รางน้ำแผ่นพับจริง "
        u"ตั้งชื่อ type ให้มีคำว่า \"รางน้ำ\" แล้วรันซ้ำ)" if gutter_dup else u""))
    out.print_md(u"- ระดับรางน้ำ: ยกขึ้นจากแนวราง **{:.0f} มม.** ให้ปีกพาด"
                 u"บนหลังแป (ปรับได้ที่ GUTTER_RISE_MM)".format(GUTTER_RISE_MM))
    if TRIM_PURLIN_AT_GUTTER:
        out.print_md(u"- ตัดปลายแปที่โผล่เข้าเขตรางน้ำ (จบที่ขอบรางพอดี): "
                     u"**{} ปลาย** / พลาด {}".format(trim_cut, trim_fail))
if AUTO_ROOF_JOIN:
    out.print_md(u"- จอยตะเข้ราง↔ผืนหลังคา: **{} คู่** / สลับฝ่ายตัด {} / "
                 u"พลาด {}".format(rj_done, rj_switch, rj_fail))
if err:
    out.print_md(u"- สร้างไม่สำเร็จ: {} ตัว".format(err))
out.print_md(u"")
out.print_md(u"**ขั้นต่อไป (Phase 4): กด Rafter Gen ซ้ำ** — หัวจันทันที่พุ่ง"
             u"เข้าแนวรางจะถูกเล็ม+ตัดแนบหน้าข้างตะเข้รางให้เอง "
             u"(type มีคำว่า \"ตะเข้\" เข้าเงื่อนไข CUT_RAFTER_AT_HIP อยู่แล้ว) "
             u"แล้วตามด้วย Purlin Gen ถ้าต้องวางแปใหม่")
out.print_md(u"ไม่พอใจผลลัพธ์ → **Ctrl+Z** ครั้งเดียวย้อนได้ทั้งหมด")
