# -*- coding: utf-8 -*-
"""ตรรกะล้วน (ไม่พึ่ง Revit) ของกลุ่มปุ่มจัดการเหล็ก: Select Rebar / Select Host /
Delete Rebar / Show-Hide Obscured — ทดสอบนอก Revit ได้ (py2.7 / py3)

kind ที่ใช้ = ชื่อชนิดจาก revotech.reinforcement.kind(): Rebar, RebarInSystem,
FabricSheet, AreaReinforcement, PathReinforcement
"""

PK_PREFIX = u"PKRevit:"

KIND_ORDER = (u"Rebar", u"FabricSheet", u"RebarInSystem",
              u"AreaReinforcement", u"PathReinforcement")

KIND_TH = {
    u"Rebar": u"เหล็กเส้น (Rebar)",
    u"FabricSheet": u"ไวร์เมช (Fabric Sheet)",
    u"RebarInSystem": u"เหล็ก Area/Path (RebarInSystem)",
    u"AreaReinforcement": u"ระบบ Area Reinforcement",
    u"PathReinforcement": u"ระบบ Path Reinforcement",
}

SYSTEM_KINDS = (u"AreaReinforcement", u"PathReinforcement")

# หมวด host ของ Show/Hide Obscured (คีย์ = ชื่อ BuiltInCategory)
HOST_CATS = (
    (u"OST_StructuralFraming", u"คาน"),
    (u"OST_StructuralColumns", u"เสา"),
    (u"OST_StructuralFoundation", u"ฐานราก"),
    (u"OST_Floors", u"พื้น"),
    (u"OST_Walls", u"ผนัง"),
)
# หมวดที่ Revit ให้วาง Area/Path Reinforcement และ Fabric Sheet
AREA_PATH_CATS = (u"OST_Floors", u"OST_Walls", u"OST_StructuralFoundation")

T_REBAR, T_AREAPATH, T_FABRIC = u"rebar", u"areapath", u"fabric"


def is_pk(comment):
    """Comments ขึ้นต้นด้วย PKRevit: หรือไม่"""
    return bool(comment) and comment.strip().startswith(PK_PREFIX)


def count_kinds(kinds):
    """list ของชื่อชนิด -> [(kind, n)] เรียงตาม KIND_ORDER ตัดชนิดที่ไม่มีออก
    (ชนิดแปลกๆ ต่อท้ายตามชื่อ)"""
    d = {}
    for k in kinds:
        d[k] = d.get(k, 0) + 1
    out = [(k, d.pop(k)) for k in KIND_ORDER if k in d]
    out.extend((k, d[k]) for k in sorted(d))
    return out


def count_lines(counts, indent=u"  "):
    """[(kind, n)] -> บรรทัดข้อความไทย"""
    return [u"{}{}: {} รายการ".format(indent, KIND_TH.get(k, k), n)
            for k, n in counts]


def delete_indices(items, only_pk):
    """items = [(kind, comment)] -> ดัชนีที่จะลบ
    only_pk=True: เฉพาะที่ Comments ขึ้นต้น PKRevit: ; False: ทั้งหมด"""
    return [i for i, (_k, c) in enumerate(items) if (not only_pk) or is_pk(c)]


def delete_counts(items, only_pk):
    return count_kinds([items[i][0] for i in delete_indices(items, only_pk)])


def system_warning(counts):
    """ข้อความเตือนเมื่อจะลบ Area/Path Reinforcement (ทั้งระบบ) — None ถ้าไม่มี"""
    n = sum(c for k, c in counts if k in SYSTEM_KINDS)
    if not n:
        return None
    return (u"มีระบบ Area/Path Reinforcement {} ชุดอยู่ในรายการลบ — Revit ลบเหล็กทีละเส้น"
            u"ของระบบนี้ไม่ได้ จึงต้องลบทั้งระบบ เหล็กทุกเส้นในระบบเดียวกัน"
            u"(รวมส่วนที่ครอบคลุม host อื่นด้วย ถ้ามี) จะหายไปด้วย").format(n)


def skipped_summary(n_total_hosts, n_hosts_with_found):
    """host ที่หาเหล็กไม่เจอ -> ข้อความสุภาพ (หรือ None)"""
    miss = n_total_hosts - n_hosts_with_found
    if miss <= 0:
        return None
    return u"ข้าม {} ตัวที่ไม่พบเหล็ก".format(miss)


def obscured_types(want_rebar, want_areapath, want_fabric):
    return [t for t, w in ((T_REBAR, want_rebar), (T_AREAPATH, want_areapath),
                           (T_FABRIC, want_fabric)) if w]


def obscured_needs_area_path_hosts(cat_names, types):
    """ต้องไล่หา RebarInSystem ผ่าน host หรือไม่ (ติ๊ก Area/Path และมีหมวดที่รองรับ)"""
    return T_AREAPATH in types and any(c in AREA_PATH_CATS for c in cat_names)


def validate_obscured(cat_names, types):
    """ข้อความผิดพลาดของฟอร์ม Obscured (หรือ None ถ้าใช้ได้)"""
    if not cat_names:
        return u"กรุณาติ๊กหมวด host อย่างน้อย 1 หมวด"
    if not types:
        return u"กรุณาติ๊กชนิดเหล็กอย่างน้อย 1 ชนิด"
    if T_AREAPATH in types and len(types) == 1 \
            and not any(c in AREA_PATH_CATS for c in cat_names):
        return (u"Area/Path Reinforcement วางได้เฉพาะพื้น ผนัง ฐานราก — "
                u"กรุณาติ๊กหมวดเหล่านั้น หรือเลือกชนิดเหล็กอื่นเพิ่ม")
    return None


def split_by_cat(items, wanted_cats):
    """items = [(id, cat_name)] -> id ที่ cat_name อยู่ใน wanted_cats"""
    w = set(wanted_cats)
    return [i for i, c in items if c in w]
