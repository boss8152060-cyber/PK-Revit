# -*- coding: utf-8 -*-
"""วิธีเลือก host element แบบเดียวกันทุกปุ่ม (พอร์ตแนวคิดจาก PK Tool `HostSelectionHelper`)

  1. ถ้ามีของที่เลือกไว้ใน Revit อยู่แล้ว → ใช้เลย (ไม่ถามอะไร)
  2. ถ้าไม่มี → ถามว่า "คลิกเลือกทีละตัว" หรือ "เลือก 1 ตัว แล้วเอาทุกตัวที่ Mark เหมือนกัน"
  3. คืน list ของ ElementId หรือ None ถ้าผู้ใช้ยกเลิก
"""

from pyrevit import DB, forms
from Autodesk.Revit.UI import TaskDialog, TaskDialogCommandLinkId, TaskDialogResult
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException


class _Filter(ISelectionFilter):
    def __init__(self, predicate):
        self._p = predicate

    def AllowElement(self, e):
        try:
            return bool(self._p(e))
        except Exception:
            return False

    def AllowReference(self, ref, pos):
        return False


def _mark(e):
    p = e.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
    return p.AsString() if p is not None else None


def _pick_by_mark(uidoc, doc, flt, predicate, label):
    try:
        ref = uidoc.Selection.PickObject(
            ObjectType.Element, flt, u"เลือก{} 1 ตัว เพื่อหาตัวที่ Mark เหมือนกัน".format(label))
    except OperationCanceledException:
        return None
    picked = doc.GetElement(ref)
    mark = _mark(picked)
    if not mark or not mark.strip():
        forms.alert(u"ตัวที่เลือกไม่มีค่า Mark จึงใช้เฉพาะตัวนี้ตัวเดียว", title=u"PK Revit")
        return [picked.Id]
    out = []
    for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType():
        try:
            if predicate(e) and _mark(e) == mark:
                out.append(e.Id)
        except Exception:
            continue
    return out


def resolve(uidoc, doc, predicate, label, offer_by_mark=True):
    """predicate(element)->bool กรองหมวดที่ต้องการ; label ใช้ในข้อความ (เช่น u'เสา')"""
    pre = [i for i in uidoc.Selection.GetElementIds()
           if doc.GetElement(i) is not None and predicate(doc.GetElement(i))]
    if pre:
        return pre
    flt = _Filter(predicate)
    if not offer_by_mark:
        return _pick_many(uidoc, flt, label)
    td = TaskDialog(u"เลือก" + label)
    td.MainInstruction = u"จะเลือก{}แบบไหน?".format(label)
    td.AllowCancellation = True
    td.AddCommandLink(TaskDialogCommandLinkId.CommandLink1, u"คลิกเลือกทีละตัว",
                      u"คลิกเลือกหลายตัวได้ แล้วกด Finish")
    td.AddCommandLink(TaskDialogCommandLinkId.CommandLink2, u"เลือก 1 ตัว แล้วเอาตัวที่ Mark เหมือนกันทั้งหมด",
                      u"ทุกชิ้นในโปรเจกต์ที่มีค่า Mark เดียวกับตัวที่คลิก")
    choice = td.Show()
    if choice == TaskDialogResult.CommandLink1:
        return _pick_many(uidoc, flt, label)
    if choice == TaskDialogResult.CommandLink2:
        return _pick_by_mark(uidoc, doc, flt, predicate, label)
    return None


def _pick_many(uidoc, flt, label):
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, flt, u"คลิกเลือก{} แล้วกด Finish".format(label))
    except OperationCanceledException:
        return None
    return [r.ElementId for r in refs]
