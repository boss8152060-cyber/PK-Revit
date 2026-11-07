# -*- coding: utf-8 -*-
"""เลือก — ปุ่มเดียวแทน Select Rebar + Select Host (ตรรกะอยู่ใน revotech/selecttool.py)

เลือก host อยู่ → เลือกเหล็กบน host; เลือกเหล็กอยู่ → เลือก host ของมัน; ไม่ได้เลือก → ถามทาง
"""

import traceback
from pyrevit import revit

from revotech import selecttool, ui

try:
    selecttool.run(revit.uidoc, revit.doc)
except Exception:
    ui.summary(u"เลือก — PK Revit", u"เกิดข้อผิดพลาด (ยังไม่ได้เปลี่ยนอะไรในโมเดล)",
               [traceback.format_exc().splitlines()[-1]],
               ui.write_log("Select.txt", traceback.format_exc().splitlines()))
