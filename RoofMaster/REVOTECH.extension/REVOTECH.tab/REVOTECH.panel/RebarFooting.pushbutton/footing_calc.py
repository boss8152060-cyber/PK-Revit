# -*- coding: utf-8 -*-
"""ฟังก์ชันคำนวณล้วนๆ ของ Rebar ฐานราก — ไม่ import Revit/pyRevit ทดสอบนอก Revit ได้

หน่วยทั้งหมดเป็น มม. พิกัด 2D อยู่ใน local frame ของฐานราก (x,y แนวนอน)
ค่า z เป็น "ระยะเหนือผิวล่างฐาน" (มม.)
"""

import math

EPS = 1e-9

PLACEHOLDER = u"— เลือก —"

# รูปแบบตะขอ (ตีความเอง ไม่ได้ระบุชื่อชัดในคลิป — รอยืนยัน)
HOOK_90 = 1        # งอขึ้น 90° ทั้งสองปลาย ยาว 12d
HOOK_FULL = 2      # งอขึ้น 90° ทั้งสองปลาย ยาวถึงใต้ระยะหุ้มบน
HOOK_NONE = 3      # เหล็กตรง ไม่งอ
HOOK_LABELS = {
    HOOK_90: u"งอขึ้น 90° ปลายยาว 12d",
    HOOK_FULL: u"งอขึ้น 90° ยาวถึงใต้ระยะหุ้มบน",
    HOOK_NONE: u"เหล็กตรง ไม่งอ",
}


# ------------------------------------------------------------ polygon
def signed_area(poly):
    a = 0.0
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def clean_polygon(pts, tol=1.0):
    """ตัดจุดซ้ำ/จุดร่วมเส้นตรงออก และบังคับให้วนทวนเข็ม (CCW)"""
    out = []
    for p in pts:
        if not out or math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) > tol:
            out.append((float(p[0]), float(p[1])))
    if len(out) > 1 and math.hypot(out[0][0] - out[-1][0],
                                   out[0][1] - out[-1][1]) <= tol:
        out.pop()
    changed = True
    while changed and len(out) > 3:
        changed = False
        n = len(out)
        for i in range(n):
            a, b, c = out[i - 1], out[i], out[(i + 1) % n]
            cr = (b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0])
            if abs(cr) <= tol:
                del out[i]
                changed = True
                break
    if len(out) >= 3 and signed_area(out) < 0:
        out.reverse()
    return out


def _edges(poly):
    n = len(poly)
    for i in range(n):
        a = poly[i]
        b = poly[(i + 1) % n]
        ex, ey = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(ex, ey)
        # จุด, ทิศ, นอร์มัลชี้เข้าด้านใน
        yield a, (ex / ln, ey / ln), (-ey / ln, ex / ln)


def offset_polygon(poly, dist):
    """หดรูปหลายเหลี่ยมนูน (CCW) เข้าด้านใน dist มม. — None ถ้าหดจนหมด"""
    if dist == 0:
        return list(poly)
    edges = list(_edges(poly))
    lines = []
    for a, u, m in edges:
        lines.append(((a[0] + m[0] * dist, a[1] + m[1] * dist), u))
    n = len(lines)
    out = []
    for i in range(n):
        p0, u0 = lines[i - 1]
        p1, u1 = lines[i]
        den = u0[0] * u1[1] - u0[1] * u1[0]
        if abs(den) < EPS:
            return None
        t = ((p1[0] - p0[0]) * u1[1] - (p1[1] - p0[1]) * u1[0]) / den
        out.append((p0[0] + u0[0] * t, p0[1] + u0[1] * t))
    if signed_area(out) <= 0:
        return None
    # ขอบที่ทิศกลับ = หดจนพลิก
    for i in range(n):
        a, b = out[i], out[(i + 1) % n]
        if (b[0] - a[0]) * edges[i][1][0] + (b[1] - a[1]) * edges[i][1][1] <= 0:
            return None
    return out


def clip_line(poly, point, u):
    """ช่วงพารามิเตอร์ t ที่เส้น point + t*u อยู่ในรูปนูน CCW — None ถ้าไม่ตัด"""
    lo, hi = -1e12, 1e12
    for a, _eu, m in _edges(poly):
        const = m[0] * (point[0] - a[0]) + m[1] * (point[1] - a[1])
        slope = m[0] * u[0] + m[1] * u[1]
        if abs(slope) < EPS:
            if const < -EPS:
                return None
        else:
            t = -const / slope
            if slope > 0:
                lo = max(lo, t)
            else:
                hi = min(hi, t)
    if hi - lo < 1e-6:
        return None
    return lo, hi


def spread(n, lo, hi, edge=True):
    """ตำแหน่ง n จุดกระจายสม่ำเสมอบน [lo,hi]
    edge=True: จุดแรก/สุดท้ายอยู่ที่ขอบ; edge=False: เว้นขอบ (i+1)/(n+1)"""
    n = int(n)
    if n <= 0:
        return []
    if n == 1:
        return [(lo + hi) / 2.0]
    if edge:
        return [lo + (hi - lo) * i / (n - 1.0) for i in range(n)]
    return [lo + (hi - lo) * (i + 1.0) / (n + 1.0) for i in range(n)]


def classify(poly):
    """3 จุด = สามเหลี่ยม, 4 จุดฉาก = สี่เหลี่ยม, อื่นๆ = None (ยังไม่รองรับ)"""
    if poly is None:
        return None
    n = len(poly)
    if n == 3:
        return "tri"
    if n == 4:
        for i in range(4):
            a, b, c = poly[i - 1], poly[i], poly[(i + 1) % 4]
            d = (b[0] - a[0]) * (c[0] - b[0]) + (b[1] - a[1]) * (c[1] - b[1])
            la = math.hypot(b[0] - a[0], b[1] - a[1])
            lb = math.hypot(c[0] - b[0], c[1] - b[1])
            if la * lb < EPS or abs(d) / (la * lb) > 0.02:
                return None
        return "rect"
    return None


def rect_axes(poly):
    """สี่เหลี่ยม: คืน (ทิศแกนยาว (ux,uy), ยาว, สั้น) มม."""
    a, b, c = poly[0], poly[1], poly[2]
    l1 = math.hypot(b[0] - a[0], b[1] - a[1])
    l2 = math.hypot(c[0] - b[0], c[1] - b[1])
    if l1 >= l2:
        u = ((b[0] - a[0]) / l1, (b[1] - a[1]) / l1)
        return u, l1, l2
    u = ((c[0] - b[0]) / l2, (c[1] - b[1]) / l2)
    return u, l2, l1


def name_hint(type_name):
    """ชื่อ type -> (รหัส, จำนวนเสาเข็ม) เช่น F2 -> (F2, 2) — ใช้แสดงผลเท่านั้น"""
    s = (type_name or u"").upper()
    for code, piles in ((u"F1P", 1), (u"F2", 2), (u"F3", 3), (u"F4", 4)):
        if code in s:
            return code, piles
    return u"", 0


# ------------------------------------------------------------ hook / levels
def hook_leg(pattern, dia, z_bar, height, cover, ext_mult=12.0):
    """ความยาวขางอขึ้น (มม.) วัดจากแกนเหล็กนอน; 0 = ไม่งอ"""
    if pattern == HOOK_NONE:
        return 0.0
    top = height - cover - dia / 2.0
    room = max(top - z_bar, 0.0)
    if pattern == HOOK_FULL:
        return room
    return min(ext_mult * dia, room)


def ring_levels(height, cover, mat_thick, d_tie, count, spacing):
    """ระดับ z (เหนือผิวล่าง) ของเหล็กรัดรอบ เริ่มเหนือตะแกรง ตัดอันที่เกินระยะหุ้มบนทิ้ง"""
    z = cover + mat_thick + d_tie / 2.0
    out = []
    for i in range(int(count)):
        zi = z + i * spacing
        if zi > height - cover - d_tie / 2.0 + 1e-6:
            break
        out.append(zi)
    return out


# ------------------------------------------------------------ bar plans
def plan_mat(poly, kind, groups, cover, d_ring, height, dia_of):
    """วางตะแกรงล่าง

    poly   : ผังฐาน CCW (มม.)
    kind   : "rect" | "tri"
    groups : rect -> {"long": (size, n), "short": (size, n)}
             tri  -> {0: (size, n), 60: (...), 120: (...)}
    d_ring : เส้นผ่านศูนย์กลางเหล็กรัดรอบ (0 ถ้าไม่มี) เพื่อเว้นไม่ชน
    dia_of : ฟังก์ชัน ชื่อ -> dia มม.
    คืน list ของ dict {group,size,a,b,z,dia} โดย a,b = ปลายแนวนอน (x,y)
    (ชั้นล่างสุดวางก่อน: rect -> long ก่อน short; tri -> 0°,60°,120°)"""
    if kind == "rect":
        u_long, _L, _S = rect_axes(poly)
        v_long = (-u_long[1], u_long[0])
        order = [("long", u_long), ("short", v_long)]
    else:
        order = []
        for ang in (0, 60, 120):
            r = math.radians(ang)
            order.append((ang, (math.cos(r), math.sin(r))))
    bars = []
    z_cursor = float(cover)
    for key, u in order:
        size, n = groups[key]
        if not size or n <= 0:
            continue
        d = dia_of(size)
        z = z_cursor + d / 2.0
        z_cursor += d
        inset = cover + d_ring + d / 2.0
        ip = offset_polygon(poly, inset)
        if ip is None:
            continue
        nrm = (-u[1], u[0])
        projs = [p[0] * nrm[0] + p[1] * nrm[1] for p in ip]
        lo, hi = min(projs), max(projs)
        for s in spread(n, lo, hi, edge=(kind == "rect")):
            pt = (nrm[0] * s, nrm[1] * s)
            r = clip_line(ip, pt, u)
            if r is None or r[1] - r[0] < 50.0:
                continue
            a = (pt[0] + u[0] * r[0], pt[1] + u[1] * r[0])
            b = (pt[0] + u[0] * r[1], pt[1] + u[1] * r[1])
            bars.append({"group": key, "size": size, "a": a, "b": b,
                         "z": z, "dia": d})
    return bars


# ------------------------------------------------------------ gate
def gate(v, has_rect, has_tri, available):
    """ด่านตรวจก่อนสร้าง -> list ของ (ok, ข้อความ); ok ทั้งหมด = สร้างได้

    v: dict {"long":(size,n),"short":(..),"tri":{0:(..),60:(..),120:(..)},
             "hook":int|None,"ring":(on,size,n,spacing_mm),"cover":mm}"""
    out = []

    def size_ok(label, size, n):
        if not size or size == PLACEHOLDER:
            out.append((False, u"✗ {}: ยังไม่เลือกขนาด".format(label)))
        elif size not in available:
            out.append((False, u"✗ {}: ไม่พบ Bar Type {} ในโปรเจกต์".format(label, size)))
        elif n < 1:
            out.append((False, u"✗ {}: จำนวนต้อง ≥ 1".format(label)))
        else:
            out.append((True, u"✓ {}: {} × {}".format(label, size, n)))

    if has_rect:
        size_ok(u"ตะแกรงล่างตามด้านยาว", v["long"][0], v["long"][1])
        size_ok(u"ตะแกรงล่างตามด้านสั้น", v["short"][0], v["short"][1])
    if has_tri:
        for ang in (0, 60, 120):
            size_ok(u"ฐานสามเหลี่ยม ทิศ {}°".format(ang), v["tri"][ang][0],
                    v["tri"][ang][1])
    if v.get("hook") in HOOK_LABELS:
        out.append((True, u"✓ ตะขอ: " + HOOK_LABELS[v["hook"]]))
    else:
        out.append((False, u"✗ ตะขอ: ยังไม่เลือกรูปแบบ"))
    on, size, n, sp = v["ring"]
    if on:
        if not size or size == PLACEHOLDER:
            out.append((False, u"✗ เหล็กรัดรอบ: ยังไม่เลือกขนาด"))
        elif size not in available:
            out.append((False, u"✗ เหล็กรัดรอบ: ไม่พบ Bar Type {}".format(size)))
        elif n < 1 or sp <= 0:
            out.append((False, u"✗ เหล็กรัดรอบ: จำนวน ≥ 1 และระยะ > 0"))
        else:
            out.append((True, u"✓ เหล็กรัดรอบ: {} × {} @ {:.0f} มม.".format(size, n, sp)))
    else:
        out.append((True, u"– เหล็กรัดรอบ: ไม่ใส่"))
    if v["cover"] <= 0:
        out.append((False, u"✗ ระยะหุ้ม ต้องมากกว่า 0"))
    else:
        out.append((True, u"✓ ระยะหุ้ม {:.0f} มม.".format(v["cover"])))
    return out


def gate_ok(items):
    return all(ok for ok, _ in items)
