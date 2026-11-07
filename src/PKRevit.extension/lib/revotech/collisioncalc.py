# -*- coding: utf-8 -*-
"""ตรรกะล้วนของ Rebar Collision (ไม่พึ่ง Revit ทดสอบนอก Revit ได้) py2.7 / py3

ขั้นแรก  bounding box overlap (บวกระยะ clearance) — ไม่พลาดการชนจริงเพราะ solid ที่ชน
         ย่อมมี bbox ซ้อนกัน; ใช้ sweep-and-prune แกน X ไม่ต้องเทียบทุกคู่ O(n^2)
ขั้นสอง  ตรวจเฉพาะคู่ที่ผ่านขั้นแรก: ระยะระหว่างเส้นศูนย์กลางเหล็ก (polyline) ลบรัศมีสองเส้น
         = ช่องว่างผิวต่อผิว (gap) — gap <= 0 คือชน, 0 < gap < clearance คือใกล้เกิน
         (ส่วนเหล็กที่ไม่มีเส้นศูนย์กลาง เช่น FabricSheet ใช้ solid intersection ฝั่ง Revit)
หน่วยของพิกัด/รัศมี/clearance ต้องเป็นหน่วยเดียวกัน (สคริปต์ใช้ฟุตของ Revit)
box = (x0, y0, z0, x1, y1, z1)
"""

import io
import math

STATUS_HIT = u"ชน"
STATUS_NEAR = u"ใกล้เกิน"
STATUS_BOX = u"bbox ซ้อน (ยังไม่ยืนยัน)"
EPS = 1e-9


# ------------------------------------------------------------ bbox
def boxes_overlap(a, b, margin=0.0):
    """True เมื่อ box ซ้อนกัน (ขยาย a ด้วย margin รอบด้าน) — ไม่นับแค่แตะขอบเมื่อ margin=0"""
    return (a[0] - margin < b[3] and b[0] < a[3] + margin and
            a[1] - margin < b[4] and b[1] < a[4] + margin and
            a[2] - margin < b[5] and b[2] < a[5] + margin)


def overlap_depth(a, b, margin=0.0):
    """ความลึกซ้อนน้อยสุดของ 3 แกน (ใช้จัดลำดับความสำคัญ — มากกว่า = ซ้อนลึกกว่า)"""
    return min(min(a[3] + margin, b[3]) - max(a[0] - margin, b[0]),
               min(a[4] + margin, b[4]) - max(a[1] - margin, b[1]),
               min(a[5] + margin, b[5]) - max(a[2] - margin, b[2]))


def candidate_pairs(items, margin=0.0, max_pairs=1000000):
    """items: list ของ (key, host, box)  — host None = ไม่ทราบ (เทียบกับทุกตัว)
    คืน (pairs, total, truncated)
      pairs = [(i, j, depth)] i<j ดัชนีใน items เรียง depth มาก→น้อย (ซ้อนลึกก่อน)
      ข้ามคู่ที่ host เดียวกัน (และ host ไม่ใช่ None)
      total = จำนวนคู่ที่พบจริง (นับต่อได้แม้ pairs ถูกตัดที่ max_pairs → truncated=True)"""
    order = sorted(range(len(items)), key=lambda k: items[k][2][0])
    pairs = []
    total = 0
    active = []  # ดัชนีที่ x1 ยังยาวถึงตัวถัดไป
    for k in order:
        kb = items[k][2]
        limit = kb[0] - margin
        active = [a for a in active if items[a][2][3] > limit]
        for a in active:
            ha, hk = items[a][1], items[k][1]
            if ha is not None and ha == hk:
                continue
            if boxes_overlap(items[a][2], kb, margin):
                total += 1
                if len(pairs) < max_pairs:
                    i, j = (a, k) if a < k else (k, a)
                    pairs.append((i, j, overlap_depth(items[a][2], kb, margin)))
        active.append(k)
    pairs.sort(key=lambda p: (-p[2], p[0], p[1]))
    return pairs, total, total > len(pairs)


# ---------------------------------------------------- เรขาคณิตเส้น
def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def segment_distance(p1, q1, p2, q2):
    """ระยะสั้นสุดระหว่างเส้นตรงจำกัด p1q1 กับ p2q2 -> (dist, จุดบน 1, จุดบน 2)"""
    d1, d2, r = _sub(q1, p1), _sub(q2, p2), _sub(p1, p2)
    a, e, f = _dot(d1, d1), _dot(d2, d2), _dot(d2, r)
    if a <= EPS and e <= EPS:
        s = t = 0.0
    elif a <= EPS:
        s, t = 0.0, _clamp(f / e)
    else:
        c = _dot(d1, r)
        if e <= EPS:
            t, s = 0.0, _clamp(-c / a)
        else:
            b = _dot(d1, d2)
            den = a * e - b * b
            s = _clamp((b * f - c * e) / den) if den > EPS else 0.0
            t = (b * s + f) / e
            if t < 0.0:
                t, s = 0.0, _clamp(-c / a)
            elif t > 1.0:
                t, s = 1.0, _clamp((b - c) / a)
    c1 = (p1[0] + d1[0] * s, p1[1] + d1[1] * s, p1[2] + d1[2] * s)
    c2 = (p2[0] + d2[0] * t, p2[1] + d2[1] * t, p2[2] + d2[2] * t)
    dv = _sub(c1, c2)
    return math.sqrt(_dot(dv, dv)), c1, c2


def _poly_box(pts, pad):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    return (min(xs) - pad, min(ys) - pad, min(zs) - pad,
            max(xs) + pad, max(ys) + pad, max(zs) + pad)


def polyline_distance(pa, pb):
    """ระยะสั้นสุดระหว่าง polyline สองเส้น -> (dist, จุดบน a, จุดบน b); None ถ้าจุดไม่พอ"""
    best = None
    na = max(len(pa) - 1, 1)
    nb = max(len(pb) - 1, 1)
    for i in range(na):
        a0, a1 = pa[i], pa[min(i + 1, len(pa) - 1)]
        for j in range(nb):
            b0, b1 = pb[j], pb[min(j + 1, len(pb) - 1)]
            r = segment_distance(a0, a1, b0, b1)
            if best is None or r[0] < best[0]:
                best = r
    return best


def centerline_gap(polys_a, polys_b, radius_a, radius_b, clearance=0.0):
    """เทียบเหล็ก A (หลาย polyline = หลายตำแหน่งในชุด) กับ B
    gap = ระยะเส้นศูนย์กลาง - รัศมีรวม ; จุดชน = จำนวนคู่ polyline ที่ gap <= 0
    (หรือ < clearance ถ้ายังไม่ชน) — คืน dict:
      min_gap, hits, nears, loc (จุดกึ่งกลางที่ใกล้สุด), pairs_checked
    หรือ None ถ้าไม่มี polyline ให้เทียบ"""
    pad = radius_a + radius_b + max(clearance, 0.0)
    boxes_b = [(_poly_box(p, 0.0), p) for p in polys_b if len(p) >= 1]
    best = None
    hits = nears = checked = 0
    for pa in polys_a:
        if len(pa) < 1:
            continue
        ba = _poly_box(pa, pad)
        for bb, pb in boxes_b:
            if not boxes_overlap(ba, bb, 0.0):
                continue
            r = polyline_distance(pa, pb)
            if r is None:
                continue
            checked += 1
            gap = r[0] - radius_a - radius_b
            if gap <= EPS:
                hits += 1
            elif gap < clearance:
                nears += 1
            if best is None or gap < best[0]:
                best = (gap, tuple((r[1][k] + r[2][k]) / 2.0 for k in range(3)))
    if best is None:
        return {"min_gap": None, "hits": 0, "nears": 0, "loc": None,
                "pairs_checked": 0}
    return {"min_gap": best[0], "hits": hits, "nears": nears, "loc": best[1],
            "pairs_checked": checked}


def classify(gap, clearance=0.0):
    """None = ไม่ต้องรายงาน"""
    if gap is None:
        return None
    if gap <= EPS:
        return STATUS_HIT
    if gap < clearance:
        return STATUS_NEAR
    return None


# ---------------------------------------------------------- รายงาน
def host_pair_key(host_a, host_b):
    """คีย์กลุ่มแบบไม่สนลำดับ; host ไม่ทราบ = None"""
    ka = -1 if host_a is None else host_a
    kb = -1 if host_b is None else host_b
    return (ka, kb) if ka <= kb else (kb, ka)


def group_by_host_pair(records):
    """records: list ของ dict ที่มี host_a, host_b, status, points (จำนวนจุดชน), gap
    คืนกลุ่ม [{key, host_a, host_b, records, points, hits, nears}] เรียงจำนวนจุดมาก→น้อย
    ในกลุ่มเรียง gap น้อยสุดก่อน"""
    groups = {}
    for r in records:
        key = host_pair_key(r["host_a"], r["host_b"])
        g = groups.get(key)
        if g is None:
            ha, hb = (r["host_a"], r["host_b"])
            if (-1 if ha is None else ha) > (-1 if hb is None else hb):
                ha, hb = hb, ha
            g = {"key": key, "host_a": ha, "host_b": hb, "records": [],
                 "points": 0, "hits": 0, "nears": 0}
            groups[key] = g
        g["records"].append(r)
        g["points"] += int(r.get("points", 1))
        if r["status"] == STATUS_HIT:
            g["hits"] += 1
        elif r["status"] == STATUS_NEAR:
            g["nears"] += 1
    out = sorted(groups.values(), key=lambda g: (-g["points"], g["key"]))
    for g in out:
        g["records"].sort(key=lambda r: (r["gap"] is None, r["gap"] or 0.0))
    return out


# --------------------------------------------------------------- CSV
def csv_cell(v):
    s = u"" if v is None else (v if not isinstance(v, bytes) else v.decode("utf-8"))
    if not isinstance(s, type(u"")):
        s = u"%s" % s
    if any(ch in s for ch in u',"\r\n'):
        s = u'"' + s.replace(u'"', u'""') + u'"'
    return s


def to_csv_text(header, rows):
    lines = [u",".join(csv_cell(c) for c in header)]
    for r in rows:
        lines.append(u",".join(csv_cell(c) for c in r))
    return u"\r\n".join(lines) + u"\r\n"


def write_csv(path, header, rows):
    """UTF-8 BOM เพื่อให้ Excel อ่านภาษาไทยถูก"""
    with io.open(path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(to_csv_text(header, rows))
