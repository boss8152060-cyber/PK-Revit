# -*- coding: utf-8 -*-
"""หาเหล็ก (Rebar / RebarInSystem / FabricSheet) ที่อยู่บน host และหา host ของเหล็ก

พอร์ตแนวคิดจาก PK Tool (`Core/ReinforcementLookup.cs`) ครอบคลุม 3 คลาสของ Revit:
  - Rebar            host ผ่าน Rebar.GetHostId()
  - FabricSheet      host ผ่าน FabricSheet.HostId
  - RebarInSystem    เป็นลูกของ AreaReinforcement / PathReinforcement (ไม่มี back-reference
                     ตรงไปหา host → ค้นผ่าน host.GetDependentElements)

ข้อควรรู้ (PK Tool ยืนยันด้วยการทดสอบจริง): Revit ไม่ยอมลบ RebarInSystem ทีละเส้น
ต้องลบ AreaReinforcement/PathReinforcement ที่เป็นเจ้าของทั้งระบบ → ใช้ deletable_on_host()
"""

import clr
from pyrevit import DB
from Autodesk.Revit.DB.Structure import (
    Rebar, RebarInSystem, AreaReinforcement, PathReinforcement, FabricSheet)

from revotech.rvt import id_value

_AREA_PATH_HOST_CATS = (
    DB.BuiltInCategory.OST_Floors,
    DB.BuiltInCategory.OST_Walls,
    DB.BuiltInCategory.OST_StructuralFoundation,
)


def _clr(t):
    return clr.GetClrType(t)


def _of_class(doc, cls):
    return DB.FilteredElementCollector(doc).OfClass(_clr(cls))


def _dependents(host, cls):
    return host.GetDependentElements(DB.ElementClassFilter(_clr(cls)))


def on_host(doc, host_id):
    """เหล็กทุกชนิดที่ผูกกับ host หนึ่งตัว (list ของ Element)"""
    host = doc.GetElement(host_id)
    if host is None:
        return []
    hid = id_value(host_id)
    out = []
    for r in _of_class(doc, Rebar):
        try:
            if id_value(r.GetHostId()) == hid:
                out.append(r)
        except Exception:
            continue
    for f in _of_class(doc, FabricSheet):
        try:
            if id_value(f.HostId) == hid:
                out.append(f)
        except Exception:
            continue
    for dep in _dependents(host, AreaReinforcement):
        ar = doc.GetElement(dep)
        if ar is not None:
            for rid in ar.GetRebarInSystemIds():
                ris = doc.GetElement(rid)
                if ris is not None:
                    out.append(ris)
    for dep in _dependents(host, PathReinforcement):
        pr = doc.GetElement(dep)
        if pr is not None:
            for rid in pr.GetRebarInSystemIds():
                ris = doc.GetElement(rid)
                if ris is not None:
                    out.append(ris)
    return out


def on_hosts(doc, host_ids):
    out, seen = [], set()
    for hid in host_ids:
        for e in on_host(doc, hid):
            k = id_value(e.Id)
            if k not in seen:
                seen.add(k)
                out.append(e)
    return out


def deletable_on_host(doc, host_id):
    """เหมือน on_host แต่ส่งให้ doc.Delete ได้เลย: ระบบ Area/Path Reinforcement
    คืนตัว AreaReinforcement/PathReinforcement แทนเหล็กทีละเส้น"""
    host = doc.GetElement(host_id)
    if host is None:
        return []
    hid = id_value(host_id)
    out = []
    for r in _of_class(doc, Rebar):
        try:
            if id_value(r.GetHostId()) == hid:
                out.append(r)
        except Exception:
            continue
    for f in _of_class(doc, FabricSheet):
        try:
            if id_value(f.HostId) == hid:
                out.append(f)
        except Exception:
            continue
    for cls in (AreaReinforcement, PathReinforcement):
        for dep in _dependents(host, cls):
            e = doc.GetElement(dep)
            if e is not None:
                out.append(e)
    return out


def deletable_on_hosts(doc, host_ids):
    out, seen = [], set()
    for hid in host_ids:
        for e in deletable_on_host(doc, hid):
            k = id_value(e.Id)
            if k not in seen:
                seen.add(k)
                out.append(e)
    return out


def host_of(doc, el):
    """ElementId ของ host (หรือ None ถ้าหาไม่ได้)"""
    if isinstance(el, Rebar):
        hid = el.GetHostId()
        return hid if hid != DB.ElementId.InvalidElementId else None
    if isinstance(el, FabricSheet):
        hid = el.HostId
        return hid if hid != DB.ElementId.InvalidElementId else None
    if isinstance(el, RebarInSystem):
        return _host_of_rebar_in_system(doc, el.Id)
    return None


def _host_of_rebar_in_system(doc, ris_id):
    target = id_value(ris_id)
    for bic in _AREA_PATH_HOST_CATS:
        for host in DB.FilteredElementCollector(doc).OfCategory(bic) \
                .WhereElementIsNotElementType():
            for cls in (AreaReinforcement, PathReinforcement):
                for dep in _dependents(host, cls):
                    e = doc.GetElement(dep)
                    if e is None:
                        continue
                    for rid in e.GetRebarInSystemIds():
                        if id_value(rid) == target:
                            return host.Id
    return None


def is_reinforcement(el):
    return isinstance(el, (Rebar, RebarInSystem, FabricSheet,
                           AreaReinforcement, PathReinforcement))


def kind(el):
    """ชื่อชนิดสั้นๆ สำหรับสรุปผล"""
    for cls, name in ((Rebar, u"Rebar"), (RebarInSystem, u"RebarInSystem"),
                      (FabricSheet, u"FabricSheet"),
                      (AreaReinforcement, u"AreaReinforcement"),
                      (PathReinforcement, u"PathReinforcement")):
        if isinstance(el, cls):
            return name
    return u"?"
