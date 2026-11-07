# -*- coding: utf-8 -*-
"""Rebar — ปุ่มเดียวใส่เหล็กเสริมทุกชนิด (เสา/คาน/ฐานราก/พื้น/บันได)

ตรวจ selection ปัจจุบัน แล้วเรียก "โมดูลเดิม" ที่เก็บไว้ใน modules/ ด้วย execfile
(ฟอร์ม/พฤติกรรมของแต่ละโมดูลไม่เปลี่ยน):
  - เลือกชนิดเดียว            → เปิดโมดูลนั้นเลย
  - ไม่ได้เลือกอะไร           → หน้าต่างเลือกชนิด (ปุ่มใหญ่) → ให้เลือกชิ้นงาน → เปิดโมดูล
  - เลือกปนหลายชนิด           → จัดกลุ่มตามชนิด ถามว่าทำทีละชนิดตามลำดับ
                                เสา → คาน → ฐานราก → พื้น → บันได
โมดูลหาไฟล์ได้ทั้ง script.py และ <ชื่อโมดูล>.py (เช่น RebarColumn.py)
ตรรกะจัดกลุ่ม/หาไฟล์อยู่ใน lib/revotech/dispatch.py (ทดสอบนอก Revit ได้)
"""

import os
import traceback
from pyrevit import revit, forms, script

from revotech import dispatch
from revotech import hostpick
from revotech.hubwindow import HubWindow
from revotech.rvt import id_value

doc = revit.doc
uidoc = revit.uidoc
out = script.get_output()
TITLE = u"PK Revit — Rebar"
HERE = os.path.dirname(os.path.abspath(__file__))
MODULES = os.path.join(HERE, "modules")


def selected_groups():
    """selection ปัจจุบัน → [(kind, [ElementId...]), ...] เรียงตามลำดับชนิด"""
    pairs = []
    for eid in uidoc.Selection.GetElementIds():
        e = doc.GetElement(eid)
        if e is None:
            continue
        pairs.append((dispatch.kind_of(e), eid))
    return dispatch.group_by_kind(pairs)


def choose_kind():
    """หน้าต่างเลือกชนิด 5 ปุ่มใหญ่ → kind หรือ None"""
    win = HubWindow(os.path.join(HERE, "body.xaml"), u"REBAR ", u"เลือกชนิด",
                    u"ใส่เหล็กเสริม — PK Revit",
                    list(dispatch.KIND_ORDER),
                    u"ยังไม่ได้เลือกชิ้นงาน — เลือกชนิดที่จะใส่เหล็ก "
                    u"แล้วระบบจะให้เลือกชิ้นงานต่อ")
    return win.ask()


def pick_hosts(kind):
    """ให้ผู้ใช้เลือกชิ้นงานของชนิดนั้น (เหมือน Propagate Rebar) → list ElementId หรือ None"""
    label = dispatch.KIND_LABELS[kind]
    return hostpick.resolve(uidoc, doc, lambda e: dispatch.kind_of(e) == kind,
                            label, offer_by_mark=False)


def run_module(kind, ids):
    """ตั้ง selection เป็นชิ้นงานของชนิดนั้น แล้วรันโมดูล — คืน False ถ้าควรหยุดทั้งชุด"""
    path = dispatch.find_script(MODULES, dispatch.KIND_FOLDERS[kind])
    if path is None:
        forms.alert(u"ไม่พบโมดูลเหล็ก{}ในชุดติดตั้ง (modules/{})".format(
            dispatch.KIND_LABELS[kind], dispatch.KIND_FOLDERS[kind]), title=TITLE)
        return False
    dispatch.set_selection(uidoc, ids)
    try:
        dispatch.run_script(path)
    except SystemExit:
        # โมดูลจบด้วย script.exit() ทั้งตอนเสร็จและตอนยกเลิก — ถือว่าจบขั้นนี้
        pass
    except Exception:
        out.print_md(u"❌ **โมดูล{} ผิดพลาด:**\n```\n{}\n```".format(
            dispatch.KIND_LABELS[kind], traceback.format_exc()))
        forms.alert(u"โมดูลเหล็ก{}ผิดพลาด — ดูรายละเอียดในหน้าต่าง output".format(
            dispatch.KIND_LABELS[kind]), title=TITLE)
        return False
    return True


groups = selected_groups()

if not groups:
    kind = choose_kind()
    if kind is None:
        script.exit()
    ids = pick_hosts(kind)
    if not ids:
        script.exit()
    groups = [(kind, ids)]
elif len(groups) > 1:
    if not forms.alert(dispatch.plan_text(groups), title=TITLE,
                       yes=True, no=True):
        script.exit()

for i, (kind, ids) in enumerate(groups):
    if i > 0:
        nxt = u"{} {} ตัว".format(dispatch.KIND_LABELS[kind], len(ids))
        if not forms.alert(u"ต่อไป: {}\n\nทำต่อไหม?".format(nxt), title=TITLE,
                           yes=True, no=True):
            break
    if not run_module(kind, ids):
        break
script.exit()
