# -*- coding: utf-8 -*-
"""บาร์คัท: คำนวณล้วน (ไม่พึ่ง Revit) — จัดกลุ่มเลขบาร์, น้ำหนัก, แผนตัดจากท่อนสต็อก (FFD)

หน่วย: ความยาวเป็น มม., น้ำหนักเป็น กก. เข้ากันได้ทั้ง IronPython 2.7 และ Python 3
ค่าน้ำหนัก kg/m ด้านล่าง **ต้องให้วิศวกร/ผู้ใช้ยืนยัน** กับตารางมาตรฐานเหล็กไทย (มอก.20/24) ก่อนใช้สั่งซื้อจริง
"""
from __future__ import division

import re

PREFIX = u"PKRevit:"
KINDS = [u"column", u"beam", u"footing", u"slab", u"stair"]
KIND_LABEL = {u"column": u"เสา", u"beam": u"คาน", u"footing": u"ฐานราก",
              u"slab": u"พื้น", u"stair": u"บันได"}
# คำนำหน้าเลขชีตต่อชนิด (ตามคลิป: FT-xx ฐานราก, BC-x คาน, SL-xx พื้น, ST-01 บันได; เสา = ตีความเอง)
SHEET_PREFIX = {u"column": u"CL", u"beam": u"BC", u"footing": u"FT",
                u"slab": u"SL", u"stair": u"ST"}

# น้ำหนักหน่วย kg/m — ค่าตั้งต้นตามตารางเหล็กไทย (ปรับได้ / รอยืนยัน)
UNIT_WEIGHT = {u"RB6": 0.222, u"RB9": 0.499, u"DB10": 0.617, u"DB12": 0.888,
               u"DB16": 1.578, u"DB20": 2.466, u"DB25": 3.853, u"DB28": 4.834,
               u"DB32": 6.313}
STOCK_CHOICES_M = [10.0, 12.0]
DEFAULT_KERF_MM = 3.0
LEN_ROUND_MM = 5.0   # ปัดความยาวตัดเพื่อจัดกลุ่ม (กันเศษทศนิยมจากฟุต)


def parse_kind(comment):
    """'PKRevit:column' -> 'column'; ไม่ใช่ของเรา -> None"""
    c = comment or u""
    if not c.startswith(PREFIX):
        return None
    rest = c[len(PREFIX):].split(u":")[0].strip()
    return rest or None


def dia_of(size):
    m = re.search(r"(\d+(?:\.\d+)?)", size or u"")
    return float(m.group(1)) if m else 0.0


def unit_weight(size, table=None):
    """kg/m: ตาราง (ถ้ามีชื่อ) ไม่งั้นสูตร d^2/162.2"""
    t = table if table is not None else UNIT_WEIGHT
    if size in t:
        return float(t[size])
    d = dia_of(size)
    return d * d / 162.2


def round_len(mm, step=LEN_ROUND_MM):
    return round(float(mm) / step) * step


def shape_signature(segs, step=5.0):
    """segs = [(ความยาวส่วนตรง มม., มุมเลี้ยวถึงส่วนถัดไป องศา)] (ส่วนสุดท้ายมุม 0)
    -> tuple เทียบกันได้ ปัดความยาวทีละ step มุมทีละ 5° และเลือกทิศทางที่ลำดับน้อยกว่า
    (เหล็กรูปเดียวกันที่เส้นเริ่มคนละปลายจะได้เลขเดียวกัน) เหล็กตรง = ((L, 0),)"""
    lens = [round_len(ln, step) for ln, _ in segs]
    turns = [int(round(abs(a) / 5.0)) * 5 for _, a in segs[:-1]]
    fwd = tuple(zip(lens, turns + [0]))
    rl = lens[::-1]
    rt = turns[::-1]
    rev = tuple(zip(rl, rt + [0]))
    return min(fwd, rev)


def shape_label(sig):
    """ข้อความ 'ตรง 3200' หรือ '300 + 3200 + 300 (90°)'"""
    if not sig:
        return u""
    if len(sig) == 1:
        return u"ตรง {:.0f}".format(sig[0][0])
    lens = u" + ".join(u"{:.0f}".format(s[0]) for s in sig)
    angs = sorted(set(int(abs(s[1])) for s in sig[:-1] if abs(s[1]) > 0))
    if angs:
        lens += u" ({})".format(u"/".join(u"{}°".format(a) for a in angs))
    return lens


def group_bars(records, weights=None):
    """records: list of dict {size, shape(tuple), length_mm, count, kind, host}
    -> list ของเลขบาร์ [{no, size, shape, length_mm, count, total_m, weight_kg, kinds, hosts}]
    เรียงตามขนาด (เล็ก->ใหญ่) แล้วความยาวมาก->น้อย เลขเริ่มที่ 1"""
    groups = {}
    for r in records:
        key = (r["size"], tuple(r.get("shape") or ()), round_len(r["length_mm"]))
        g = groups.setdefault(key, {"size": r["size"], "shape": key[1],
                                    "length_mm": key[2], "count": 0,
                                    "kinds": set(), "hosts": set()})
        g["count"] += int(r["count"])
        if r.get("kind"):
            g["kinds"].add(r["kind"])
        if r.get("host") is not None:
            g["hosts"].add(r["host"])
    rows = sorted(groups.values(),
                  key=lambda g: (dia_of(g["size"]), g["size"], -g["length_mm"],
                                 g["shape"]))
    for i, g in enumerate(rows):
        g["no"] = i + 1
        g["total_m"] = g["count"] * g["length_mm"] / 1000.0
        g["weight_kg"] = g["total_m"] * unit_weight(g["size"], weights)
        g["kinds"] = sorted(g["kinds"])
    return rows


def ffd_plan(pieces_mm, stock_mm, kerf_mm=0.0):
    """first-fit-decreasing: pieces_mm = ความยาวท่อนที่ต้องตัด
    คืน (bins, oversize); bin = {pieces, used_mm, waste_mm}
    รอยตัด: คั่นระหว่างท่อน kerf ต่อการตัด 1 ครั้ง (n ชิ้น = n-1 รอย) ชิ้นสุดท้ายถือว่าที่เหลือเป็นเศษ
    ชิ้นที่ยาวกว่าสต็อกแยกเป็น oversize (ต้องต่อทาบ — ไม่วางแผนให้)"""
    bins = []
    oversize = []
    for p in sorted(pieces_mm, reverse=True):
        if p > stock_mm + 1e-6:
            oversize.append(p)
            continue
        placed = False
        for b in bins:
            need = b["used"] + p + kerf_mm
            if need <= stock_mm + 1e-6:
                b["pieces"].append(p)
                b["used"] = need
                placed = True
                break
        if not placed:
            bins.append({"pieces": [p], "used": float(p)})
    for b in bins:
        b["used_mm"] = b.pop("used")
        b["waste_mm"] = stock_mm - b["used_mm"]
    return bins, oversize


def pattern_name(i):
    """0->A, 25->Z, 26->AA"""
    s = u""
    i += 1
    while i > 0:
        i, r = divmod(i - 1, 26)
        s = u"ABCDEFGHIJKLMNOPQRSTUVWXYZ"[r] + s
    return s


def cutting_plan(rows, stock_m, kerf_mm=DEFAULT_KERF_MM, weights=None):
    """แผนตัดแยกตามขนาด จาก rows ของ group_bars
    เศษ = สต็อกที่สั่ง - ความยาวชิ้นที่ใช้จริง (รอยตัดนับเป็นเศษ)"""
    stock_mm = float(stock_m) * 1000.0
    sizes = sorted(set(r["size"] for r in rows), key=lambda s: (dia_of(s), s))
    by_size = []
    patterns = []
    tot = {"stock": 0, "stock_len_m": 0.0, "use_len_m": 0.0, "stock_kg": 0.0,
           "use_kg": 0.0, "oversize": 0, "oversize_m": 0.0}
    for size in sizes:
        pieces = []
        for r in rows:
            if r["size"] == size:
                pieces.extend([r["length_mm"]] * r["count"])
        bins, over = ffd_plan(pieces, stock_mm, kerf_mm)
        uw = unit_weight(size, weights)
        use_m = sum(sum(b["pieces"]) for b in bins) / 1000.0
        stock_len_m = len(bins) * stock_mm / 1000.0
        by_size.append({
            "size": size, "n_stock": len(bins), "stock_len_m": stock_len_m,
            "use_len_m": use_m, "waste_len_m": stock_len_m - use_m,
            "waste_pct": ((stock_len_m - use_m) / stock_len_m * 100.0)
            if stock_len_m else 0.0,
            "stock_kg": stock_len_m * uw, "use_kg": use_m * uw,
            "waste_kg": (stock_len_m - use_m) * uw,
            "oversize": sorted(over, reverse=True)})
        # รวมท่อนที่มีแบบตัดเหมือนกัน -> แบบ A/B/C (ต่อขนาด)
        pat = {}
        for b in bins:
            k = tuple(b["pieces"])
            e = pat.setdefault(k, {"size": size, "pieces": list(k), "n": 0,
                                   "waste_mm": b["waste_mm"]})
            e["n"] += 1
        for i, e in enumerate(sorted(pat.values(), key=lambda e: -e["n"])):
            e["name"] = pattern_name(i)
            patterns.append(e)
        tot["stock"] += len(bins)
        tot["stock_len_m"] += stock_len_m
        tot["use_len_m"] += use_m
        tot["stock_kg"] += stock_len_m * uw
        tot["use_kg"] += use_m * uw
        tot["oversize"] += len(over)
        tot["oversize_m"] += sum(over) / 1000.0
    tot["waste_len_m"] = tot["stock_len_m"] - tot["use_len_m"]
    tot["waste_kg"] = tot["stock_kg"] - tot["use_kg"]
    tot["waste_pct_len"] = (tot["waste_len_m"] / tot["stock_len_m"] * 100.0
                            if tot["stock_len_m"] else 0.0)
    tot["waste_pct_kg"] = (tot["waste_kg"] / tot["stock_kg"] * 100.0
                           if tot["stock_kg"] else 0.0)
    return {"stock_m": float(stock_m), "kerf_mm": float(kerf_mm),
            "by_size": by_size, "patterns": patterns, "total": tot}


def summary_totals(rows, plan, hosts):
    """ตัวเลขสรุปทั้งชุด: hosts = จำนวน element ต้นแบบ (แนว/ชิ้นงาน)"""
    return {"hosts": int(hosts), "marks": len(rows),
            "pieces": sum(r["count"] for r in rows),
            "weight_kg": sum(r["weight_kg"] for r in rows),
            "stock_m": plan["stock_m"], "stock_n": plan["total"]["stock"]}


def summary_text(s):
    """เช่น '32 แนว · 207 เลข · 7,407 กก. · 10 ม. 615 ท่อน'"""
    return u"{:,} แนว · {:,} เลข · {:,.0f} กก. · {:g} ม. {:,} ท่อน".format(
        s["hosts"], s["marks"], s["weight_kg"], s["stock_m"], s["stock_n"])


def sheet_numbers(kinds_present, existing=()):
    """เลขชีตต่อชนิด 'FT-01' ฯลฯ (ชนกับ existing -> เลื่อนเลข) + key 'all' = สรุปรวม 'BC-00'"""
    used = set(existing)
    out = {}
    for k in kinds_present:
        pre = SHEET_PREFIX.get(k, u"BC")
        n = 1
        while u"{}-{:02d}".format(pre, n) in used:
            n += 1
        out[k] = u"{}-{:02d}".format(pre, n)
        used.add(out[k])
    base = u"BC-00"
    n = 0
    while base in used:
        n += 1
        base = u"BC-00.{}".format(n)
    out["all"] = base
    return out
