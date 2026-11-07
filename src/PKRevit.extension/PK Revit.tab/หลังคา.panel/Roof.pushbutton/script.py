# -*- coding: utf-8 -*-
"""Roof — ปุ่มเดียวรวมเครื่องมือหลังคา: โครงหลังคา (Roof Master) กับ วัสดุมุง (Roof Cover)

เปิดหน้าต่างเลือก 2 ปุ่มใหญ่ แล้ว execfile สคริปต์เดิมของแต่ละตัวจาก modules/
(ฟอร์ม/พฤติกรรมไม่เปลี่ยน) — Roof Master ยังหา engines/ ของตัวเองเจอเหมือนเดิม
หาไฟล์ได้ทั้ง script.py และ <ชื่อโมดูล>.py (เช่น RoofMaster.py)
"""

import os
import traceback
from pyrevit import revit, DB, forms, script

from revotech import dispatch
from revotech.hubwindow import HubWindow
from revotech.rvt import cat_id

doc = revit.doc
uidoc = revit.uidoc
out = script.get_output()
TITLE = u"PK Revit — Roof"
HERE = os.path.dirname(os.path.abspath(__file__))
MODULES = os.path.join(HERE, "modules")
FOLDERS = {"master": u"RoofMaster.pushbutton", "cover": u"RoofCover.pushbutton"}
LABELS = {"master": u"โครงหลังคา (Roof Master)", "cover": u"วัสดุมุง (Roof Cover)"}


def roof_count():
    n = 0
    for eid in uidoc.Selection.GetElementIds():
        e = doc.GetElement(eid)
        if e is not None and cat_id(e) == int(DB.BuiltInCategory.OST_Roofs):
            n += 1
    return n


n = roof_count()
info = (u"เลือกหลังคาไว้ {} หลัง — เลือกเครื่องมือที่จะใช้".format(n) if n else
        u"ยังไม่ได้เลือกหลังคา — คลิกหลังคา (Roof) ในโมเดลก่อน "
        u"แล้วค่อยกดปุ่มด้านล่าง (ทำโครงก่อน แล้วค่อยวัสดุมุง)")
win = HubWindow(os.path.join(HERE, "body.xaml"), u"ROOF ", u"เครื่องมือหลังคา",
                u"โครงหลังคา และ วัสดุมุง — PK Revit", ["master", "cover"], info)
choice = win.ask()
if choice is None:
    script.exit()

path = dispatch.find_script(MODULES, FOLDERS[choice])
if path is None:
    forms.alert(u"ไม่พบโมดูล {} ในชุดติดตั้ง (modules/{})".format(
        LABELS[choice], FOLDERS[choice]), title=TITLE, exitscript=True)
try:
    dispatch.run_script(path)
except SystemExit:
    pass
except Exception:
    out.print_md(u"❌ **{} ผิดพลาด:**\n```\n{}\n```".format(
        LABELS[choice], traceback.format_exc()))
    forms.alert(u"{} ผิดพลาด — ดูรายละเอียดในหน้าต่าง output".format(LABELS[choice]),
                title=TITLE)
