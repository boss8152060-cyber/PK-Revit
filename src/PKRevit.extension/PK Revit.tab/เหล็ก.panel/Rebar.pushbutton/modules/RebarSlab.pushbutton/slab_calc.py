# -*- coding: utf-8 -*-
"""ฟังก์ชันคำนวณล้วนๆ ของ Rebar พื้น — ไม่ import Revit/pyRevit ทดสอบนอก Revit ได้

หน่วยทั้งหมดเป็น มม. พิกัด 2D เป็นพิกัดผังแนวนอนของโมเดล (X,Y)
ค่า z เป็น "ระยะเหนือผิวล่างพื้น" (มม.)

รองรับพื้นรูปทรงใดก็ได้ที่เป็นรูปหลายเหลี่ยม (นูน/เว้า/ตัว L/คางหมู) และมีช่องเปิด (hole)
โดยใช้วิธี scanline: ลากเส้นตามทิศเหล็ก ตัดกับขอบทุกลูป (ขอบนอก+ขอบช่องเปิด)
จับคู่แบบ even-odd แล้วหดปลายเหล็กเข้าจากขอบด้วยระยะหุ้ม ÷ sin(มุมที่เส้นตัดขอบ)
"""

import math

EPS = 1e-9

PLACEHOLDER = u"— ไม่ใส่ —"

MODE_BAR = "bar"
MODE_MESH = "mesh"

# ชั้นเหล็ก: B=ล่าง T=บน, X/Y=ทิศเหล็กวิ่งตามแกน X/Y ของโมเดล
LAYER_KEYS = ("TX", "TY", "BX", "BY")
LAYER_LABELS = {
    "TX": u"ชั้นบน ทิศ X",
    "TY": u"ชั้นบน ทิศ Y",
    "BX": u"ชั้นล่าง ทิศ X",
    "BY": u"ชั้นล่าง ทิศ Y",
}

MIN_BAR_LEN = 100.0     # เหล็กสั้นกว่านี้ (มม.) ไม่สร้าง
MIN_SIN = 0.25          # กันการหารด้วย sin เล็กเกินเมื่อขอบเฉียงมาก
MIN_EDGE_LEN = 300.0    # ขอบสั้นกว่านี้ (มม.) ไม่ใส่เหล็กเสริมริม
HOOK_DOWN_D = 12.0      # ปลายงอลงของเหล็กเสริมริม = 12 d (ตามคลิป "12db") — รอยืนยัน


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


def split_loops(loops):
    """loops = list ของรายการจุด -> (outer, holes)
    ลูปพื้นที่ใหญ่สุดคือขอบนอก ที่เหลือคือช่องเปิด; ลูปที่เสื่อม (<3 จุด) ทิ้ง
    คืน (None, []) ถ้าไม่มีลูปใช้ได้"""
    cl = []
    for lp in loops:
        c = clean_polygon(lp)
        if len(c) >= 3 and abs(signed_area(c)) > 1.0:
            cl.append(c)
    if not cl:
        return None, []
    cl.sort(key=lambda p: -abs(signed_area(p)))
    return cl[0], cl[1:]


def point_in_poly(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        if (y0 > y) != (y1 > y):
            xi = x0 + (y - y0) * (x1 - x0) / (y1 - y0)
            if xi > x:
                inside = not inside
    return inside


def point_in_region(pt, outer, holes):
    if not point_in_poly(pt, outer):
        return False
    for h in holes:
        if point_in_poly(pt, h):
            return False
    return True


def bbox(poly):
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    return min(xs), min(ys), max(xs), max(ys)


# ------------------------------------------------------------ scanline
def scan_segments(loops, c, cover):
    """ช่วงของเส้นระดับ y = c (ทิศ +X) ที่อยู่ในพื้น หดปลายด้วยระยะหุ้ม

    loops: [outer] + holes (แต่ละอันคือรายการจุด)
    คืน list ของ (x0, x1) เรียงจากซ้ายไปขวา ความยาว >= MIN_BAR_LEN"""
    hits = []   # (x, sin)
    for poly in loops:
        n = len(poly)
        for i in range(n):
            x0, y0 = poly[i]
            x1, y1 = poly[(i + 1) % n]
            if (y0 <= c < y1) or (y1 <= c < y0):
                x = x0 + (c - y0) * (x1 - x0) / (y1 - y0)
                ln = math.hypot(x1 - x0, y1 - y0)
                s = abs(y1 - y0) / ln if ln > 0 else 1.0
                hits.append((x, max(s, MIN_SIN)))
    hits.sort(key=lambda h: h[0])
    out = []
    for i in range(0, len(hits) - 1, 2):
        (xa, sa), (xb, sb) = hits[i], hits[i + 1]
        a = xa + cover / sa
        b = xb - cover / sb
        if b - a >= MIN_BAR_LEN:
            out.append((a, b))
    return out


def positions(lo, hi, spacing):
    """ตำแหน่งเหล็กบน [lo,hi] ระยะห่างไม่เกิน spacing: เริ่มที่ lo ทุก spacing
    และเติมเส้นท้ายที่ hi ถ้าช่องสุดท้ายเหลือ >= 0.25 × spacing"""
    if hi < lo or spacing <= 0:
        return []
    n = int(math.floor((hi - lo) / spacing + 1e-9)) + 1
    ps = [lo + k * spacing for k in range(n)]
    gap = hi - ps[-1]
    if gap >= 0.25 * spacing:
        ps.append(hi)
    return ps


def _swap(poly):
    return [(p[1], p[0]) for p in poly]


# ------------------------------------------------------------ layers
def layer_levels(H, cover, layers, dia_of):
    """ระดับ z (มม. เหนือผิวล่าง) ของแกนเหล็กแต่ละชั้น
    ทิศ X อยู่ริมนอกสุดทั้งบนและล่าง (ตีความเอง รอยืนยัน)
    layers: {key: (size, spacing_mm)} เฉพาะชั้นที่ใช้
    คืน (levels, ok) — ok=False ถ้าชั้นเหล็กซ้อนกันเกินความหนาพื้น"""
    d = {}
    for k in LAYER_KEYS:
        d[k] = dia_of(layers[k][0]) if k in layers else 0.0
    lv = {}
    if "BX" in layers:
        lv["BX"] = cover + d["BX"] / 2.0
    if "BY" in layers:
        lv["BY"] = cover + d["BX"] + d["BY"] / 2.0
    if "TX" in layers:
        lv["TX"] = H - cover - d["TX"] / 2.0
    if "TY" in layers:
        lv["TY"] = H - cover - d["TX"] - d["TY"] / 2.0
    bot = cover + d["BX"] + d["BY"]
    top = H - cover - d["TX"] - d["TY"]
    return lv, bot <= top + EPS


def plan_layers(outer, holes, H, cover, layers, dia_of):
    """วางเหล็กเส้นตรงของชั้นที่เลือกทั้งหมด

    layers: {key: (size, spacing_mm)} ใส่เฉพาะชั้นที่ใช้ (ขนาดไม่ใช่ placeholder)
    คืน (bars, notes) — bar = dict(group,size,a,b,z,dia) a,b เป็น (x,y) มม.
    notes = ข้อความสำหรับ log (เช่น ชั้นเหล็กหนาเกินพื้น)"""
    notes = []
    if not layers:
        return [], notes
    lv, ok = layer_levels(H, cover, layers, dia_of)
    if not ok:
        notes.append(u"ชั้นเหล็กรวมหนากว่าพื้น {:.0f} มม. (หุ้ม {:.0f}) — ไม่ใส่".format(H, cover))
        return [], notes
    minx, miny, maxx, maxy = bbox(outer)
    bars = []
    for key in LAYER_KEYS:
        if key not in layers:
            continue
        size, sp = layers[key]
        d = dia_of(size)
        if key.endswith("X"):
            loops = [outer] + list(holes)
            lo, hi = miny + cover + d / 2.0, maxy - cover - d / 2.0
        else:
            loops = [_swap(outer)] + [_swap(h) for h in holes]
            lo, hi = minx + cover + d / 2.0, maxx - cover - d / 2.0
        n0 = len(bars)
        for c in positions(lo, hi, sp):
            for (s0, s1) in scan_segments(loops, c, cover):
                if key.endswith("X"):
                    a, b = (s0, c), (s1, c)
                else:
                    a, b = (c, s0), (c, s1)
                bars.append({"group": key, "size": size, "a": a, "b": b,
                             "z": lv[key], "dia": d})
        if len(bars) == n0:
            notes.append(u"{}: พื้นเล็กเกินระยะหุ้ม/ระยะเหล็ก ไม่มีเหล็กเลย".format(
                LAYER_LABELS[key]))
    return bars, notes


def count_groups(bars):
    """จำนวน "ชุด" = จำนวนกลุ่ม (key ชั้น) ที่มีเหล็กอย่างน้อย 1 เส้น (ต่อพื้น 1 ผืน)"""
    return len(set(b["group"] for b in bars))


# ------------------------------------------------------------ edge bars
def edge_bars(outer, holes, H, cover, size_dia, spacing, length, z):
    """เหล็กเสริมริม (ตีความ "หนวดกุ้ง" — รอยืนยัน): เหล็กบนเสริม ตั้งฉากขอบนอก
    ยาว length เข้าในพื้น ปลายริมงอลงยาว 12d (ไม่เกินความหนาที่เหลือ)

    คืน (bars, skipped) — bar = dict(a=จุดปลายริม, b=ปลายใน, leg=ความยาวงอลง, z, dia)
    skipped = จำนวนเส้นที่ปลายในหลุดนอกพื้น/ตกช่องเปิด หรือขอบที่สั้นเกิน"""
    bars = []
    skipped = 0
    n = len(outer)
    leg = min(HOOK_DOWN_D * size_dia, max(z - cover - size_dia / 2.0, 0.0))
    for i in range(n):
        p0, p1 = outer[i], outer[(i + 1) % n]
        ex, ey = p1[0] - p0[0], p1[1] - p0[1]
        ln = math.hypot(ex, ey)
        if ln < MIN_EDGE_LEN:
            skipped += 1
            continue
        ux, uy = ex / ln, ey / ln
        mx, my = -uy, ux            # นอร์มัลชี้เข้าใน (outer เป็น CCW)
        for t in positions(cover + size_dia / 2.0, ln - cover - size_dia / 2.0,
                           spacing):
            a = (p0[0] + ux * t + mx * cover, p0[1] + uy * t + my * cover)
            b = (a[0] + mx * length, a[1] + my * length)
            if point_in_region(b, outer, holes) and \
               point_in_region((a[0] + mx * 1.0, a[1] + my * 1.0), outer, holes):
                bars.append({"a": a, "b": b, "leg": leg, "z": z,
                             "dia": size_dia})
            else:
                skipped += 1
    return bars, skipped


def edge_level(H, cover, layers, dia_of, size_dia):
    """ระดับ z ของเหล็กเสริมริม: วางใต้ชั้นเหล็กบนที่มีอยู่"""
    top = 0.0
    for k in ("TX", "TY"):
        if k in layers:
            top += dia_of(layers[k][0])
    return H - cover - top - size_dia / 2.0


# ------------------------------------------------------------ gate
def gate(v, available, n_fabric, fabric_names=()):
    """ด่านตรวจก่อนสร้าง -> list ของ (ok, ข้อความ); ok ทั้งหมด = สร้างได้

    v: dict {"mode", "layers":{key:(size,spacing_mm)} (ทุก key, size อาจเป็น placeholder),
             "edge":(on,size,spacing_mm,length_mm), "mesh":ชื่อ type, "cover":mm}
    available: ชื่อ Bar Type ในโปรเจกต์; n_fabric: จำนวน Fabric Sheet Type"""
    out = []
    if v["mode"] == MODE_BAR:
        used = 0
        for k in LAYER_KEYS:
            size, sp = v["layers"][k]
            lab = LAYER_LABELS[k]
            if not size or size == PLACEHOLDER:
                out.append((True, u"– {}: ไม่ใส่".format(lab)))
                continue
            used += 1
            if size not in available:
                out.append((False, u"✗ {}: ไม่พบ Bar Type {} ในโปรเจกต์".format(lab, size)))
            elif sp <= 0:
                out.append((False, u"✗ {}: ระยะต้องมากกว่า 0".format(lab)))
            else:
                out.append((True, u"✓ {}: {} @ {:.3f} ม.".format(lab, size, sp / 1000.0)))
        if used == 0:
            out.append((False, u"✗ ยังไม่ได้เลือกเหล็กชั้นใดเลย"))
    else:
        if n_fabric <= 0:
            out.append((False, u"✗ ไวร์เมช: ไม่พบ Fabric Sheet Type ในโปรเจกต์ — "
                               u"โหลด/สร้าง Fabric Sheet Type ก่อน (จะไม่สร้างไวร์เมช)"))
        elif not v.get("mesh") or v["mesh"] not in fabric_names:
            out.append((False, u"✗ ไวร์เมช: ยังไม่เลือก Fabric Sheet Type"))
        else:
            out.append((True, u"✓ ไวร์เมช: {}".format(v["mesh"])))
    on, size, sp, ln = v["edge"]
    if on:
        if not size or size == PLACEHOLDER:
            out.append((False, u"✗ เหล็กเสริมริม: ยังไม่เลือกขนาด"))
        elif size not in available:
            out.append((False, u"✗ เหล็กเสริมริม: ไม่พบ Bar Type {}".format(size)))
        elif sp <= 0 or ln <= 0:
            out.append((False, u"✗ เหล็กเสริมริม: ระยะและความยาวต้องมากกว่า 0"))
        else:
            out.append((True, u"✓ เหล็กเสริมริม: {} @ {:.3f} ม. ยาว {:.2f} ม.".format(
                size, sp / 1000.0, ln / 1000.0)))
    else:
        out.append((True, u"– เหล็กเสริมริม/หนวดกุ้ง: ไม่ใส่"))
    if v["cover"] <= 0:
        out.append((False, u"✗ ระยะหุ้ม ต้องมากกว่า 0"))
    else:
        out.append((True, u"✓ ระยะหุ้ม {:.0f} มม.".format(v["cover"])))
    return out


def gate_ok(items):
    return all(ok for ok, _ in items)


def summary_text(n_bar_sets, n_mesh):
    return u"เหล็กเส้น {} ชุด · ไวร์เมช {} ผืน".format(n_bar_sets, n_mesh)
