# -*- coding: utf-8 -*-
"""คำนวณสรุปปริมาณวัสดุโครงหลังคา/วัสดุมุง (ไม่พึ่ง Revit — ทดสอบนอก Revit ได้)

ข้อมูลเข้า (สร้างโดย script.py จากโมเดล):
  framing: [{"type": ชื่อ type, "length_m": ม., "kg_per_m": กก./ม. หรือ None}]
  cover:   [{"material": ชื่อ material (หรือ ""), "area_m2": ตร.ม.}]
"""
from __future__ import unicode_literals
import io

try:
    text_type = unicode  # noqa: F821  (IronPython 2)
except NameError:
    text_type = str

# (key, ป้าย, คำค้นในชื่อ type) — เรียงลำดับสำคัญ: ตัวที่เฉพาะกว่าต้องมาก่อน
# (ตะเฆ่/ตะเข้ สะกดได้ทั้งสองแบบ; "แป" สั้นสุดจึงตรวจเป็นตัวสุดท้าย)
FRAME_KINDS = [
    ("ridge", "อกไก่", ["อกไก่"]),
    ("valley_hip", "ตะเฆ่ราง", ["ตะเฆ่ราง", "ตะเข้ราง"]),
    ("gutter", "รางน้ำ", ["รางน้ำ"]),
    ("hip", "ตะเฆ่สัน", ["ตะเฆ่สัน", "ตะเข้สัน", "ตะเฆ่", "ตะเข้"]),
    ("rafter", "จันทัน", ["จันทัน"]),
    ("king", "ดั้ง", ["ดั้ง"]),
    ("purlin", "แป", ["แป"]),
]
FRAME_LABEL = dict((k, lb) for k, lb, _ in FRAME_KINDS)
# ลำดับแสดงผลในตาราง
DISPLAY_ORDER = ["purlin", "rafter", "hip", "ridge", "gutter", "valley_hip", "king"]

# วัสดุมุง: ใช้ชื่อ material ที่ Roof Cover ทาไว้ (DirectShape ไม่เก็บชนิดชิ้นงาน)
COVER_KINDS = [
    ("ridge_cap", "ครอบสัน/ครอบ", ["ridge", "ครอบ", "cap"]),
    ("verge", "ครอบข้าง/ปั้นลม", ["verge", "ปั้นลม"]),
    ("fascia", "เชิงชาย", ["fascia", "เชิงชาย"]),
    ("sheet", "แผ่นมุง", ["monier", "prestige", "oriental", "metal", "sheet",
                          "แผ่น", "กระเบื้อง", "เมทัล", "หลังคา"]),
]
COVER_LABEL = dict((k, lb) for k, lb, _ in COVER_KINDS)
COVER_UNKNOWN = "other"
COVER_LABEL[COVER_UNKNOWN] = "ชิ้นมุงแยกชนิดไม่ได้ (material ไม่ระบุ/ไม่ตรงคำค้น)"
COVER_ORDER = ["sheet", "ridge_cap", "verge", "fascia", COVER_UNKNOWN]

# ชื่อพารามิเตอร์ type ที่ถือเป็น "น้ำหนักต่อเมตร" (เทียบแบบไม่สนตัวพิมพ์/ช่องว่าง)
WEIGHT_PARAM_NAMES = ["น้ำหนักต่อเมตร", "น้ำหนัก/ม.", "น้ำหนักต่อเมตร (กก./ม.)",
                      "Weight per meter", "Weight per metre", "Weight/m",
                      "Weight per Unit Length", "kg/m", "Unit Weight"]


def _norm(s):
    return "".join((s or "").lower().split())


def classify_framing(type_name):
    """key ชนิดโครง จากชื่อ type — None ถ้าไม่ตรงชนิดไหน"""
    n = _norm(type_name)
    for key, _lb, kws in FRAME_KINDS:
        for kw in kws:
            if _norm(kw) in n:
                return key
    return None


def classify_cover(material_name):
    n = _norm(material_name)
    if n:
        for key, _lb, kws in COVER_KINDS:
            for kw in kws:
                if _norm(kw) in n:
                    return key
    return COVER_UNKNOWN


def is_weight_param(name):
    n = _norm(name)
    return any(n == _norm(w) for w in WEIGHT_PARAM_NAMES)


def summarize_framing(items):
    """→ (kinds, types, unknown)
    kinds:   {key: {pieces, length_m, weight_kg, no_weight_pieces}} (เฉพาะที่มีชิ้นงาน)
    types:   [{kind, type, pieces, length_m, kg_per_m, weight_kg}] เรียงตามชนิด/ชื่อ
    unknown: {type: pieces} ของ type ที่ไม่ตรงคำค้นชนิดใด (ไม่นับรวม)
    weight_kg ของแถวที่ไม่มี kg_per_m = None (ห้ามเดา)"""
    kinds, tmap, unknown = {}, {}, {}
    for it in items:
        key = classify_framing(it["type"])
        if key is None:
            unknown[it["type"]] = unknown.get(it["type"], 0) + 1
            continue
        L = float(it.get("length_m") or 0.0)
        kpm = it.get("kg_per_m")
        t = tmap.setdefault((key, it["type"]),
                            {"kind": key, "type": it["type"], "pieces": 0,
                             "length_m": 0.0, "kg_per_m": kpm})
        t["pieces"] += 1
        t["length_m"] += L
        if t["kg_per_m"] is None and kpm is not None:
            t["kg_per_m"] = kpm
    types = []
    for (key, name), t in tmap.items():
        k = kinds.setdefault(key, {"pieces": 0, "length_m": 0.0,
                                   "weight_kg": 0.0, "no_weight_pieces": 0})
        k["pieces"] += t["pieces"]
        k["length_m"] += t["length_m"]
        if t["kg_per_m"] is None:
            t["weight_kg"] = None
            k["no_weight_pieces"] += t["pieces"]
        else:
            t["weight_kg"] = t["length_m"] * t["kg_per_m"]
            k["weight_kg"] += t["weight_kg"]
        types.append(t)
    types.sort(key=lambda t: (DISPLAY_ORDER.index(t["kind"]), t["type"]))
    return kinds, types, unknown


def summarize_cover(items):
    """→ {key: {pieces, area_m2}} เฉพาะชนิดที่มีชิ้นงาน"""
    out = {}
    for it in items:
        k = out.setdefault(classify_cover(it.get("material")),
                           {"pieces": 0, "area_m2": 0.0})
        k["pieces"] += 1
        k["area_m2"] += float(it.get("area_m2") or 0.0)
    return out


def fmt(v, nd):
    return "" if v is None else ("{:." + str(nd) + "f}").format(v)


HEAD_FRAME = ["ชนิด", "type", "จำนวนท่อน", "ความยาวรวม (ม.)", "กก./ม.", "น้ำหนักรวม (กก.)"]
HEAD_COVER = ["ชนิด", "จำนวนชิ้น", "พื้นที่ (ตร.ม.)"]


def frame_rows(kinds, types):
    """แถวตาราง (ข้อความ) ของโครง: แถวละ type + แถวรวมของชนิด + รวมทั้งหมด
    ช่องน้ำหนักว่าง = ไม่มี kg/m ใน type; เครื่องหมาย * = น้ำหนักรวมไม่ครบ"""
    rows = []
    tot_p = tot_l = tot_w = 0.0
    tot_nw = 0
    for key in DISPLAY_ORDER:
        if key not in kinds:
            continue
        for t in [t for t in types if t["kind"] == key]:
            rows.append([FRAME_LABEL[key], t["type"], t["pieces"],
                         fmt(t["length_m"], 2), fmt(t["kg_per_m"], 3),
                         fmt(t["weight_kg"], 1)])
        k = kinds[key]
        rows.append([FRAME_LABEL[key] + " (รวม)", "", k["pieces"],
                     fmt(k["length_m"], 2), "",
                     fmt(k["weight_kg"], 1) + (" *" if k["no_weight_pieces"] else "")])
        tot_p += k["pieces"]
        tot_l += k["length_m"]
        tot_w += k["weight_kg"]
        tot_nw += k["no_weight_pieces"]
    if rows:
        rows.append(["รวมโครงหลังคา", "", int(tot_p), fmt(tot_l, 2), "",
                     fmt(tot_w, 1) + (" *" if tot_nw else "")])
    return rows


def cover_rows(cover):
    rows = []
    for key in COVER_ORDER:
        if key in cover:
            rows.append([COVER_LABEL[key], cover[key]["pieces"],
                         fmt(cover[key]["area_m2"], 2)])
    return rows


def weight_note(kinds):
    """ข้อความเตือนเมื่อบางชนิดไม่มีน้ำหนักต่อเมตร — "" ถ้าครบ"""
    miss = sum(k["no_weight_pieces"] for k in kinds.values())
    if not miss:
        return ""
    return ("* น้ำหนักรวมไม่ครบ: {} ท่อนอยู่ใน type ที่ไม่มีพารามิเตอร์น้ำหนักต่อเมตร "
            "(เว้นว่าง ไม่เดา) — เพิ่มพารามิเตอร์ type เช่น \"น้ำหนักต่อเมตร\" แล้วรันใหม่"
            .format(miss))


def csv_tables(kinds, types, cover, unknown):
    """[(ชื่อตาราง, rows)] สำหรับ write_csv"""
    out = [("โครงหลังคา", [HEAD_FRAME] + frame_rows(kinds, types)),
           ("วัสดุมุง (Roof Cover)", [HEAD_COVER] + cover_rows(cover))]
    if unknown:
        out.append(("Structural Framing ที่ไม่นับ (ชื่อ type ไม่ตรงชนิด)",
                    [["type", "จำนวนท่อน"]] + [[n, c] for n, c in sorted(unknown.items())]))
    return out


def _csv_cell(v):
    if v is None:
        return ""
    s = text_type(v)
    if any(c in s for c in ',"\n\r'):
        s = '"' + s.replace('"', '""') + '"'
    return s


def write_csv(path, tables):
    """CSV UTF-8 มี BOM; หลายตารางต่อกันในไฟล์เดียว คั่นด้วยแถว "# ชื่อ" """
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write("﻿")
        for name, rows in tables:
            f.write(_csv_cell("# " + name) + "\r\n")
            for row in rows:
                f.write(",".join(_csv_cell(v) for v in row) + "\r\n")
            f.write("\r\n")
    return path
