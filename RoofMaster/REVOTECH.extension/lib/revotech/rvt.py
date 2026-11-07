# -*- coding: utf-8 -*-
"""Helper ค้นหา element/type ใน Revit (รวมโค้ดที่ engine v2 ก๊อปซ้ำ 4 ไฟล์)"""

from pyrevit import DB


def ename(e):
    """ชื่อ element/type (Element.Name บางกรณี property ใช้ตรงๆ ไม่ได้ใน IronPython)"""
    try:
        return e.Name
    except Exception:
        try:
            return DB.Element.Name.__get__(e)
        except Exception:
            return u"(ไม่ทราบชื่อ)"


def id_value(eid):
    """ค่า int ของ ElementId — Revit 2024+ ใช้ .Value, รุ่นเก่า .IntegerValue"""
    try:
        return eid.Value
    except Exception:
        return eid.IntegerValue


def cat_id(e):
    try:
        c = e.Category
        if c is None:
            return None
        return id_value(c.Id)
    except Exception:
        return None


def is_category(e, bic):
    return cat_id(e) == int(bic)


def type_name(doc, e):
    try:
        t = doc.GetElement(e.GetTypeId())
        if t is not None:
            return ename(t)
    except Exception:
        pass
    return u""


def selected(uidoc, doc, bic):
    """element ที่ผู้ใช้เลือกอยู่ เฉพาะหมวด bic (BuiltInCategory)"""
    out = []
    for eid in uidoc.Selection.GetElementIds():
        e = doc.GetElement(eid)
        if e is not None and is_category(e, bic):
            out.append(e)
    return out


def types_of(doc, bic):
    """type ทั้งหมดของหมวด bic เป็น {ชื่อ: element}"""
    d = {}
    for t in DB.FilteredElementCollector(doc).OfCategory(bic) \
              .WhereElementIsElementType():
        d[ename(t)] = t
    return d


def find_named(names, wanted):
    """หาชื่อใน names ที่ตรงกับ wanted ก่อนแบบเป๊ะ แล้วค่อยแบบ case-insensitive"""
    for n in names:
        if n == wanted:
            return n
    low = wanted.lower()
    for n in names:
        if n.lower() == low:
            return n
    return None


def param_mm(e, names):
    """ค่าพารามิเตอร์ความยาว (มม.) จากชื่อแรกที่เจอ — None ถ้าไม่เจอ"""
    from revotech.units import ft_to_mm
    for nm in names:
        p = e.LookupParameter(nm)
        if p is not None and p.HasValue:
            try:
                return ft_to_mm(p.AsDouble())
            except Exception:
                continue
    return None
