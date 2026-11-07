# -*- coding: utf-8 -*-
"""ส่วนที่แตะ Revit ของกลุ่มปุ่มจัดการเหล็ก (ตรรกะล้วนอยู่ใน managecalc.py)

เสริมจาก reinforcement.py (ไม่แก้ไฟล์นั้น):
  - hosts_of_many: หา host ของเหล็กหลายเส้นพร้อมกัน — RebarInSystem สแกน host ครั้งเดียว
    (reinforcement.host_of ทีละเส้นสแกนใหม่ทุกครั้ง ช้าเมื่อเลือกเยอะ)
  - view_ris_ids_on_hosts: RebarInSystem ที่ผูกกับ host หมวดที่ต้องการจริงๆ (แม่นกว่า PK Tool
    ที่เหมารวมทุกเส้นใน view)
"""

from pyrevit import DB
from Autodesk.Revit.DB.Structure import (
    Rebar, RebarInSystem, AreaReinforcement, PathReinforcement, FabricSheet)

from revotech.rvt import id_value
from revotech import reinforcement as rf
from revotech import managecalc as mc

COMMENTS = DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS
_INVALID = DB.ElementId.InvalidElementId


def comment_of(el):
    try:
        p = el.get_Parameter(COMMENTS)
        return p.AsString() if p is not None else None
    except Exception:
        return None


def is_host_candidate(e):
    """element แบบจำลองที่เป็น host ได้ (ไม่ใช่เหล็ก/ไม่ใช่ type/มีหมวด)"""
    try:
        if e is None or e.Category is None or rf.is_reinforcement(e):
            return False
        return e.Category.CategoryType == DB.CategoryType.Model
    except Exception:
        return False


def is_bar_element(e):
    """เหล็กที่ผู้ใช้เลือกได้ (ตัวเหล็กจริง ไม่รวมตัวระบบ Area/Path)"""
    return isinstance(e, (Rebar, RebarInSystem, FabricSheet))


def _system_hosts(doc, cats=None):
    """{id ของ AreaReinforcement/PathReinforcement/RebarInSystem: host ElementId}
    สแกน host หมวด Floors/Walls/Foundation ครั้งเดียว"""
    out = {}
    bics = cats or (DB.BuiltInCategory.OST_Floors, DB.BuiltInCategory.OST_Walls,
                    DB.BuiltInCategory.OST_StructuralFoundation)
    for bic in bics:
        for host in DB.FilteredElementCollector(doc).OfCategory(bic) \
                .WhereElementIsNotElementType():
            for cls in (AreaReinforcement, PathReinforcement):
                try:
                    deps = host.GetDependentElements(
                        DB.ElementClassFilter(rf._clr(cls)))
                except Exception:
                    continue
                for dep in deps:
                    s = doc.GetElement(dep)
                    if s is None:
                        continue
                    out[id_value(dep)] = host.Id
                    try:
                        for rid in s.GetRebarInSystemIds():
                            out[id_value(rid)] = host.Id
                    except Exception:
                        pass
    return out


def hosts_of_many(doc, elements):
    """-> (list ElementId ของ host ไม่ซ้ำ, จำนวนเหล็กที่หา host ไม่เจอ)"""
    sys_map = None
    seen, hosts, missing = set(), [], 0
    for el in elements:
        hid = None
        if isinstance(el, (Rebar, FabricSheet)):
            hid = rf.host_of(doc, el)
        elif isinstance(el, (RebarInSystem, AreaReinforcement, PathReinforcement)):
            if sys_map is None:
                sys_map = _system_hosts(doc)
            hid = sys_map.get(id_value(el.Id))
        if hid is None or hid == _INVALID:
            missing += 1
            continue
        k = id_value(hid)
        if k not in seen:
            seen.add(k)
            hosts.append(hid)
    return hosts, missing


def cat_name_of(doc, hid):
    """ชื่อ BuiltInCategory ของ host (เช่น 'OST_Floors') หรือ None"""
    try:
        e = doc.GetElement(hid)
        if e is None or e.Category is None:
            return None
        import System
        return str(System.Enum.ToObject(DB.BuiltInCategory,
                                        int(id_value(e.Category.Id))))
    except Exception:
        return None


def view_ris_ids_on_hosts(doc, cat_names):
    """id (int) ของ RebarInSystem ที่ host อยู่ในหมวด cat_names (ต้องเป็น Floors/Walls/Foundation)"""
    bics = []
    for n in cat_names:
        if n in mc.AREA_PATH_CATS:
            bics.append(getattr(DB.BuiltInCategory, n))
    if not bics:
        return set()
    m = _system_hosts(doc, tuple(bics))
    return set(m.keys())
