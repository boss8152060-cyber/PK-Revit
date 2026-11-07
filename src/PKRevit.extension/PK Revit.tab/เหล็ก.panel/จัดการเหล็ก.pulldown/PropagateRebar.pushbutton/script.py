# -*- coding: utf-8 -*-
"""Propagate Rebar — คัดลอกการใส่เหล็กจาก host ต้นทางไปยัง host ตัวอื่นชนิดเดียวกัน

แนวคิดเดียวกับ Propagate Rebar ของ PK Tool:
  1. เลือก host ต้นทาง (เสา/คาน/ฐานราก/พื้น/บันได) ที่เคยใส่เหล็กด้วย PK Revit
  2. อ่านค่าฟอร์มที่จำไว้ที่ host นั้น (ExtensibleStorage — revotech.hostconfig)
  3. เลือก host ปลายทาง (ชนิดเดียวกัน) แล้วรันโมดูลเหล็กเดิมด้วยค่าเหล่านั้น
     โดยไม่เปิดฟอร์ม (CONFIG_OVERRIDE) → คำนวณใหม่จากขนาดจริงของแต่ละตัวเอง
     (ต่างจาก Propagate Rebar ของ Revit ที่ปลอก/เหล็กรูปทรงไม่ปรับตามขนาดปลายทาง)
  4. ถ้าต้นทางไม่เคยมีค่าที่จำไว้ (ใส่เหล็กด้วยวิธีอื่น) → เลือกเหล็กของต้นทาง
     แล้วสั่ง "Propagate Rebar" ของ Revit เอง (ID_PROPAGATE_REBAR) ให้
     ถ้าสั่งไม่ได้ จะแจ้งให้กดเองที่แท็บ Rebar

ทั้งชุดห่อ TransactionGroup เดียว → Ctrl+Z ครั้งเดียวย้อนทั้งหมด
ปลายทางจะ "แทนที่" เหล็ก PK Revit เดิมของตัวนั้นเสมอ (ไม่ซ้อนทับ)
"""

import os
import traceback
from System.Collections.Generic import List
from pyrevit import revit, DB, forms, script

from revotech import dispatch
from revotech import hostconfig
from revotech import hostpick
from revotech import ui
from revotech.rvt import ename, id_value, cat_id

doc = revit.doc
uidoc = revit.uidoc
out = script.get_output()
TITLE = u"PK Revit — Propagate Rebar"

BIC = DB.BuiltInCategory


def kind_of(e):
    """ชนิดโมดูลเหล็กของ element (None = ไม่รองรับ)"""
    c = cat_id(e)
    if c == int(BIC.OST_StructuralColumns):
        return "column"
    if c == int(BIC.OST_StructuralFraming):
        try:
            if e.StructuralType == DB.Structure.StructuralType.Beam:
                return "beam"
        except Exception:
            pass
        return None
    if c == int(BIC.OST_StructuralFoundation):
        return "footing"
    if c == int(BIC.OST_Floors):
        return "slab"
    if c == int(BIC.OST_Stairs):
        return "stair"
    return None


def _ids(seq):
    lst = List[DB.ElementId]()
    for i in seq:
        lst.Add(i)
    return lst


def _native_propagate(source):
    """ต้นทางไม่มีค่าที่จำไว้ → เลือกเหล็กของมัน แล้วสั่ง Propagate Rebar ของ Revit"""
    rebar_ids = []
    for r in DB.FilteredElementCollector(doc).OfClass(DB.Structure.Rebar):
        try:
            if id_value(r.GetHostId()) == id_value(source.Id):
                rebar_ids.append(r.Id)
        except Exception:
            continue
    if not rebar_ids:
        forms.alert(u"host ต้นทางนี้ไม่มีเหล็กเลย (จากทุกที่มา) จึงไม่มีอะไรให้ propagate",
                    title=TITLE)
        return
    uidoc.Selection.SetElementIds(_ids(rebar_ids))
    manual = (u"host ต้นทางนี้ไม่เคยใส่เหล็กด้วย PK Revit (ไม่มีค่าที่จำไว้)\n\n"
              u"เลือกเหล็กของมันไว้ให้แล้ว {} ชิ้น — ไปที่แท็บ Rebar แล้วกด "
              u"Propagate Rebar ของ Revit เอง".format(len(rebar_ids)))
    cmd = None
    try:
        from Autodesk.Revit.UI import RevitCommandId
        cmd = RevitCommandId.LookupCommandId("ID_PROPAGATE_REBAR")
    except Exception:
        cmd = None
    if cmd is None:
        forms.alert(manual, title=TITLE)
        return
    try:
        revit.uidoc.Application.PostCommand(cmd)
    except Exception:
        forms.alert(manual, title=TITLE)


def _module_path(kind):
    """หาสคริปต์โมดูลเหล็ก: เก็บอยู่ที่ <panel>/Rebar.pushbutton/modules/<โมดูล>.pushbutton
    (script.py หรือ <ชื่อโมดูล>.py) — ลองโฟลเดอร์พี่น้องแบบเดิมเป็นทางสำรอง"""
    here = os.path.dirname(os.path.abspath(__file__))
    panel = os.path.dirname(os.path.dirname(here))      # เหล็ก.panel
    dirs = [os.path.join(panel, u"Rebar.pushbutton", u"modules"),
            os.path.dirname(here)]
    return dispatch.find_in_dirs(dirs, hostconfig.KINDS[kind])


# ------------------------------------------------------------ 1) ต้นทาง
src_ids = hostpick.resolve(uidoc, doc, lambda e: kind_of(e) is not None,
                           u"host ต้นทาง (เสา/คาน/ฐานราก/พื้น/บันได)",
                           offer_by_mark=False)
if not src_ids:
    script.exit()
if len(src_ids) > 1:
    forms.alert(u"เลือก host ต้นทางได้ครั้งละ 1 ตัวเท่านั้น (เลือกอยู่ {} ตัว) — "
                u"เลือกใหม่แล้วกดปุ่มอีกครั้ง".format(len(src_ids)), title=TITLE,
                exitscript=True)
source = doc.GetElement(src_ids[0])
src_kind = kind_of(source)

saved = hostconfig.load(source)
if saved is None:
    _native_propagate(source)
    script.exit()
kind, values = saved
if kind != src_kind:
    forms.alert(u"ค่าที่จำไว้เป็นของ{} แต่ host ที่เลือกเป็น{} — ใช้ต่อไม่ได้".format(
        hostconfig.KIND_LABELS.get(kind, kind),
        hostconfig.KIND_LABELS.get(src_kind, src_kind)), title=TITLE, exitscript=True)

path = _module_path(kind)
if path is None:
    forms.alert(u"ไม่พบโมดูลเหล็กของ{}ในชุดติดตั้ง".format(
        hostconfig.KIND_LABELS[kind]), title=TITLE, exitscript=True)

# ------------------------------------------------------------ 2) ปลายทาง
# เคลียร์ selection ที่ใช้เป็นต้นทาง ไม่งั้นขั้นเลือกปลายทางจะนึกว่าเลือกไว้แล้ว
uidoc.Selection.SetElementIds(_ids([]))
label = hostconfig.KIND_LABELS[kind]
tgt_ids = hostpick.resolve(uidoc, doc, lambda e: kind_of(e) == kind,
                           u"{}ปลายทาง".format(label), offer_by_mark=False)
if not tgt_ids:
    script.exit()
src_val = id_value(source.Id)
tgt_ids = [i for i in tgt_ids if id_value(i) != src_val]
if not tgt_ids:
    forms.alert(u"ไม่ได้เลือก{}ปลายทาง (นอกจากตัวต้นทางเอง)".format(label),
                title=TITLE, exitscript=True)

# ------------------------------------------------------------ 3) รันโมดูลเดิม
values = dict(values)
values["replace"] = True    # ปลายทางมีเหล็ก PK Revit เดิม → แทนที่ ไม่ซ้อน
values["same"] = False
if "view" in values:
    values["view"] = False  # บันได: ไม่สร้าง 3D view ซ้ำทุกครั้ง

out.print_md(u"# Propagate Rebar — {} {} ตัว".format(label, len(tgt_ids)))
tg = DB.TransactionGroup(doc, "PK Revit - Propagate Rebar")
tg.Start()
ok = False
try:
    g = {"__file__": path, "__name__": "__main__",
         "CONFIG_OVERRIDE": {"values": values, "hosts": tgt_ids}}
    execfile(path, g)
    ok = True
except SystemExit:
    # โมดูลหยุดเอง (แจ้งเหตุผลไปแล้ว เช่น ไม่มี Bar Type) — ไม่มีอะไรค้าง
    out.print_md(u"⚠ โมดูลหยุดกลางทาง (ดูข้อความที่แจ้งไว้)")
except Exception:
    out.print_md(u"❌ **ผิดพลาด:**\n```\n{}\n```".format(traceback.format_exc()))
try:
    if ok:
        tg.Assimilate()
    else:
        tg.RollBack()
except Exception:
    pass
