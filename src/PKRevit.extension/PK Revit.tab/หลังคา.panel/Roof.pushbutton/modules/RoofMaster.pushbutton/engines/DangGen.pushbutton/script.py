# -*- coding: utf-8 -*-
"""Dang Gen — วางดั้ง (เสาสั้นรับอกไก่/จุดรวมตะเข้สัน) แนวดิ่งลงถึงโครงรับ

หลักการ (ยังไม่เคยรันใน Revit — ดู docs/accept-dang-gen.md):
1) หาตะเข้สัน/อกไก่ที่ Hip Ridge Gen วางไว้ (ชื่อ type มี "ตะเข้"/"อกไก่")
   เฉพาะที่อยู่ในกรอบหลังคาที่เลือก
2) หาจุดรวม: ปลายบนตะเข้สัน + ปลายอกไก่ ที่มาชุมนุมกัน ≥2 เส้น
   (ปลายอกไก่ทุกจุดนับด้วย) — คำนวณใน dang_calc.py (ทดสอบนอก Revit ได้)
3) ยิงรังสีลงจากใต้ท้องคาน หาผิวบนของโครงรับ/คาน/พื้น ใกล้สุดใต้จุด
   ไม่เจอ → ใช้ความยาวที่กรอก (FALLBACK_LENGTH_MM)
4) วางดั้งเป็น Structural Column (type ชื่อมี "ดั้ง"; ไม่มี → duplicate
   จาก column type ที่มี แล้วตั้งชื่อ "ดั้ง")
"""

import math
import os
import sys
from System.Collections.Generic import List
from pyrevit import revit, DB, forms, script

doc = revit.doc
out = script.get_output()

# ===================== CONFIG =====================
TYPE_KEYWORDS = [u"ดั้ง"]          # type ดั้ง (Column ก่อน แล้ว Framing)
HIP_TYPE_KEYWORDS = [u"ตะเข้"]     # ตะเข้สัน (ไม่นับที่มีคำว่า ราง)
RIDGE_TYPE_KEYWORDS = [u"อกไก่"]
NEW_TYPE_NAME = u"ดั้ง"            # ชื่อ type ที่ duplicate ให้เมื่อไม่มี
FALLBACK_LENGTH_MM = 1000.0        # หาโครงรับไม่เจอ → ดั้งยาวเท่านี้ (ใต้ท้องคาน)
MEMBER_DEPTH_MM = 100.0            # ความลึกคานอกไก่/ตะเข้ (ยอดดั้งอยู่ใต้ท้องคาน)
MIN_LEN_MM = 200.0                 # ดั้งสั้นกว่านี้ไม่วาง
MAX_LEN_MM = 4000.0                # โครงรับที่อยู่ลึกกว่านี้ไม่นับ → ใช้ fallback
CLUSTER_XY_MM = 300.0              # ปลายคานในแปลนห่างกันไม่เกินนี้ = จุดรวมเดียวกัน
CLUSTER_Z_MM = 600.0
MIN_MEMBERS = 2                    # จุดรวมต้องมีคานมาชน ≥ นี้
RIDGE_ENDS_ALWAYS = True           # ปลายอกไก่ทุกจุดมีดั้ง แม้ไม่มีตะเข้มาชน
RIDGE_MAX_SPAN_MM = 0.0            # >0 = เพิ่มดั้งกลางอกไก่ทุกช่วงไม่เกินนี้ (0=ปิด)
SUPPORT_CATEGORIES = ["framing", "floors"]   # สิ่งที่ถือเป็นโครงรับ
SEARCH_MARGIN_MM = 500.0           # ขยายกรอบหลังคาตอนกรองคาน
DELETE_OLD = True                  # ลบดั้งเดิม (type ชื่อมี "ดั้ง") ในกรอบหลังคา
# ==================================================
try:
    globals().update(CONFIG_OVERRIDE)
except NameError:
    pass

try:
    _here = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _here = os.getcwd()
if _here not in sys.path:
    sys.path.insert(0, _here)
import dang_calc as dc

FT_TO_MM = 304.8
# ชื่อ type ของโครงหลังคา — ไม่นับเป็นโครงรับของดั้ง
ROOF_WORDS = [u"แป", u"จันทัน", u"ตะเข้", u"อกไก่", u"รางน้ำ", u"ดั้ง"]


def ename(e):
    try:
        return e.Name
    except Exception:
        try:
            return DB.Element.Name.__get__(e)
        except Exception:
            return u""


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


def eid_val(i):
    try:
        return i.Value
    except Exception:
        return i.IntegerValue


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


def match_kw(name, kws):
    low = name.lower()
    return all(k.lower() in low for k in kws)


def is_roof(e):
    return cat_id(e) == int(DB.BuiltInCategory.OST_Roofs)


# ---------- หลังคา + กรอบค้นหา ----------
sel_roofs = [e for e in revit.get_selection().elements if is_roof(e)]
if sel_roofs:
    roofs = sel_roofs
else:
    roofs = list(DB.FilteredElementCollector(doc)
                 .OfCategory(DB.BuiltInCategory.OST_Roofs)
                 .WhereElementIsNotElementType().ToElements())
if not roofs:
    forms.alert(u"ไม่พบ Roof ในโมเดล", exitscript=True)

boxes = []
_mg = mm_to_ft(SEARCH_MARGIN_MM)
for r in roofs:
    try:
        bb = r.get_BoundingBox(None)
        if bb is not None:
            boxes.append((bb.Min.X - _mg, bb.Min.Y - _mg,
                          bb.Max.X + _mg, bb.Max.Y + _mg))
    except Exception:
        pass


def in_boxes(p):
    if not boxes:
        return True
    return any(b[0] <= p.X <= b[2] and b[1] <= p.Y <= b[3] for b in boxes)


# ---------- รวบรวมตะเข้สัน/อกไก่ ----------
members, member_ids = [], set()
for e in DB.FilteredElementCollector(doc) \
           .OfCategory(DB.BuiltInCategory.OST_StructuralFraming) \
           .WhereElementIsNotElementType():
    tn = type_name(e)
    if match_kw(tn, RIDGE_TYPE_KEYWORDS):
        kind = "ridge"
    elif match_kw(tn, HIP_TYPE_KEYWORDS) and u"ราง" not in tn:
        kind = "hip"
    else:
        continue
    try:
        crv = e.Location.Curve
        a, b = crv.GetEndPoint(0), crv.GetEndPoint(1)
    except Exception:
        continue
    if not (in_boxes(a) or in_boxes(b)):
        continue
    members.append({"id": len(members), "kind": kind,
                    "p0": (a.X * FT_TO_MM, a.Y * FT_TO_MM, a.Z * FT_TO_MM),
                    "p1": (b.X * FT_TO_MM, b.Y * FT_TO_MM, b.Z * FT_TO_MM)})
    member_ids.add(eid_val(e.Id))

if not members:
    forms.alert(u"ไม่พบตะเข้สัน/อกไก่ (type ชื่อมี \"ตะเข้\"/\"อกไก่\") ในกรอบหลังคา — "
                u"รัน Hip Ridge Gen ก่อน", exitscript=True)

nodes = dc.find_nodes(members, CLUSTER_XY_MM, CLUSTER_Z_MM, MIN_MEMBERS,
                      RIDGE_ENDS_ALWAYS, MEMBER_DEPTH_MM)
nodes = dc.merge_nodes(nodes, dc.ridge_mid_nodes(
    members, RIDGE_MAX_SPAN_MM, MEMBER_DEPTH_MM), CLUSTER_XY_MM)
if not nodes:
    forms.alert(u"ไม่พบจุดรวมตะเข้สัน/อกไก่ที่ต้องมีดั้ง", exitscript=True)


# ---------- หา type ดั้ง ----------
def find_type(cat):
    for t in DB.FilteredElementCollector(doc).OfCategory(cat) \
               .WhereElementIsElementType():
        if match_kw(ename(t), TYPE_KEYWORDS):
            return t
    return None


dang_sym = find_type(DB.BuiltInCategory.OST_StructuralColumns)
dang_is_column = dang_sym is not None
if dang_sym is None:
    dang_sym = find_type(DB.BuiltInCategory.OST_StructuralFraming)
need_dup = dang_sym is None
dup_base = None
if need_dup:
    cols = [t for t in DB.FilteredElementCollector(doc)
            .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
            .WhereElementIsElementType()]
    if not cols:
        forms.alert(u"ไม่มี type ชื่อ \"ดั้ง\" และไม่มี Structural Column type "
                    u"ให้ duplicate — โหลด family เสาเหล็ก (Rectangular/Square "
                    u"Hollow) แล้วรันใหม่", exitscript=True)
    pref = [t for t in cols if any(
        w in ename(t).lower() for w in (u"hollow", u"hss", u"square",
                                        u"rect", u"ท่อ", u"จันทัน"))]
    dup_base = (pref or cols)[0]
    dang_is_column = True

# ---------- level ----------
levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level).ToElements(),
                key=lambda l: l.Elevation)
if not levels:
    forms.alert(u"ไม่พบ Level ในโปรเจกต์", exitscript=True)


def level_at_or_below(z_ft):
    best = levels[0]
    for lv in levels:
        if lv.Elevation <= z_ft + 1e-6:
            best = lv
    return best


# ---------- ยิงรังสีลงหาโครงรับ ----------
def find_view3d():
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View3D):
        try:
            if not v.IsTemplate:
                return v
        except Exception:
            pass
    return None


view3d = find_view3d()
ri = None
if view3d is not None:
    try:
        cats = List[DB.BuiltInCategory]()
        if "framing" in SUPPORT_CATEGORIES:
            cats.Add(DB.BuiltInCategory.OST_StructuralFraming)
        if "floors" in SUPPORT_CATEGORIES:
            cats.Add(DB.BuiltInCategory.OST_Floors)
        ri = DB.ReferenceIntersector(DB.ElementMulticategoryFilter(cats),
                                     DB.FindReferenceTarget.Element, view3d)
        ri.FindReferencesInRevitLinks = False
    except Exception:
        ri = None


def hits_below(n):
    """ระดับ (มม.) ผิวโครงรับที่ยิงเจอใต้จุด n — ตัดโครงหลังคาเอง/ดั้งออก"""
    zs = []
    if ri is None:
        return zs
    org = DB.XYZ(n["x"] / FT_TO_MM, n["y"] / FT_TO_MM,
                 (n["top_z"] - 10.0) / FT_TO_MM)
    try:
        res = ri.Find(org, DB.XYZ(0, 0, -1))
    except Exception:
        return zs
    for rc in res:
        try:
            ref = rc.GetReference()
            el = doc.GetElement(ref.ElementId)
            if eid_val(el.Id) in member_ids:
                continue
            if any(w in type_name(el) for w in ROOF_WORDS):
                continue
            zs.append(ref.GlobalPoint.Z * FT_TO_MM)
        except Exception:
            continue
    return zs


hit_lists = [hits_below(n) for n in nodes]
plan = dc.plan_dang(nodes, hit_lists, FALLBACK_LENGTH_MM, MIN_LEN_MM, MAX_LEN_MM)
if not plan:
    forms.alert(u"คำนวณแล้วไม่มีจุดไหนได้ดั้งยาวถึง {:.0f} มม.".format(MIN_LEN_MM),
                exitscript=True)

# ---------- สร้าง ----------
old = []
if DELETE_OLD:
    for cat in (DB.BuiltInCategory.OST_StructuralColumns,
                DB.BuiltInCategory.OST_StructuralFraming):
        for e in DB.FilteredElementCollector(doc).OfCategory(cat) \
                   .WhereElementIsNotElementType():
            if match_kw(type_name(e), TYPE_KEYWORDS):
                try:
                    p = e.Location.Point if hasattr(e.Location, "Point") \
                        else e.Location.Curve.GetEndPoint(0)
                    if in_boxes(p):
                        old.append(e.Id)
                except Exception:
                    pass

created, err, n_support, n_fallback = 0, 0, 0, 0
made_type = False
with revit.Transaction("REVOTECH - Dang Gen (สร้าง)", swallow_errors=True):
    for oid in old:
        try:
            doc.Delete(oid)
        except Exception:
            pass
    if need_dup:
        try:
            newt = doc.GetElement(dup_base.Duplicate(NEW_TYPE_NAME).Id)
            dang_sym = newt
            made_type = True
        except Exception:
            forms.alert(u"duplicate type ดั้งไม่สำเร็จ — สร้าง type ชื่อ \"ดั้ง\" "
                        u"เองแล้วรันใหม่", exitscript=True)
    if not dang_sym.IsActive:
        dang_sym.Activate()
    doc.Regenerate()
    for p in plan:
        x, y = p["x"] / FT_TO_MM, p["y"] / FT_TO_MM
        zb, zt = p["bottom_z"] / FT_TO_MM, p["top_z"] / FT_TO_MM
        try:
            lv_b = level_at_or_below(zb)
            if dang_is_column:
                inst = doc.Create.NewFamilyInstance(
                    DB.XYZ(x, y, zb), dang_sym, lv_b,
                    DB.Structure.StructuralType.Column)
                lv_t = level_at_or_below(zt)
                for bip, val in (
                        (DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM, lv_b.Id),
                        (DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM, lv_t.Id),
                        (DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM,
                         zb - lv_b.Elevation),
                        (DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM,
                         zt - lv_t.Elevation)):
                    try:
                        pr = inst.get_Parameter(bip)
                        if pr is not None and not pr.IsReadOnly:
                            pr.Set(val)
                    except Exception:
                        pass
            else:
                # type ดั้งเป็น Framing: ลองวางคานแนวดิ่ง (Revit อาจไม่ยอม)
                inst = doc.Create.NewFamilyInstance(
                    DB.Line.CreateBound(DB.XYZ(x, y, zb), DB.XYZ(x, y, zt)),
                    dang_sym, lv_b, DB.Structure.StructuralType.Beam)
            created += 1
            if p["source"] == "support":
                n_support += 1
            else:
                n_fallback += 1
        except Exception:
            err += 1

out.print_md(u"## Dang Gen เสร็จแล้ว")
out.print_md(u"- ตะเข้สัน/อกไก่ที่พบ: **{} เส้น** → จุดรวม **{} จุด**".format(
    len(members), len(nodes)))
if old:
    out.print_md(u"- ลบดั้งเดิม: **{} ตัว**".format(len(old)))
out.print_md(u"- วางดั้ง: **{} ตัว** (ลงถึงโครงรับ {} / ใช้ความยาวที่กรอก "
             u"{:.0f} มม. {})".format(created, n_support, FALLBACK_LENGTH_MM,
                                       n_fallback))
if made_type:
    out.print_md(u"- ⚠ ไม่มี type ชื่อ \"ดั้ง\" — สร้างจาก `{}` (ปรับขนาดหน้าตัดเอง)".format(
        ename(dup_base)))
if ri is None:
    out.print_md(u"- ⚠ ยิงหาโครงรับไม่ได้ (ไม่มี 3D view) — ใช้ความยาวที่กรอกทุกตัว")
if not dang_is_column:
    out.print_md(u"- ⚠ type ดั้งเป็น Structural Framing — ถ้า Revit ไม่ยอมคานแนวดิ่ง "
                 u"ให้ใช้ type ในหมวด Structural Column")
if err:
    out.print_md(u"- สร้างไม่สำเร็จ: {} ตัว".format(err))
out.print_md(u"\nไม่พอใจผลลัพธ์ → **Ctrl+Z** ครั้งเดียวย้อนได้ทั้งหมด")
