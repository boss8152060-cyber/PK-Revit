# -*- coding: utf-8 -*-
"""Select Rebar — เลือก host แล้วเลือกเหล็กทุกชนิดบน host (Rebar / FabricSheet / RebarInSystem)

host: ถ้ามีของที่เลือกอยู่แล้วใช้เลย ไม่งั้นเลือกทีละตัว หรือ 1 ตัวแล้วเอาตัวที่ Mark เหมือนกัน
ผลลัพธ์: ตั้ง Selection ของ Revit เป็นเหล็กที่พบ + สรุปจำนวนแยกตามชนิด ข้ามกรณีหาไม่เจอโดยไม่ error
"""

import traceback
from pyrevit import revit, DB, forms
from System.Collections.Generic import List

from revotech import hostpick, ui, reinforcement as rf
from revotech import manage, managecalc as mc
from revotech.rvt import id_value

doc = revit.doc
uidoc = revit.uidoc
TITLE = u"Select Rebar — PK Revit"

try:
    host_ids = hostpick.resolve(uidoc, doc, manage.is_host_candidate, u"host")
    if host_ids is None:
        pass    # ผู้ใช้ยกเลิก
    elif not host_ids:
        forms.alert(u"ไม่ได้เลือก host", title=TITLE)
    else:
        found, hosts_hit = [], 0
        for hid in host_ids:
            els = rf.on_host(doc, hid)
            if els:
                hosts_hit += 1
                found.extend(els)
        seen, uniq = set(), []
        for e in found:
            k = id_value(e.Id)
            if k not in seen:
                seen.add(k)
                uniq.append(e)
        if not uniq:
            forms.alert(u"ไม่พบเหล็กบน host ที่เลือก ({} ตัว)".format(len(host_ids)),
                        title=TITLE)
        else:
            ids = List[DB.ElementId]([e.Id for e in uniq])
            uidoc.Selection.SetElementIds(ids)
            counts = mc.count_kinds([rf.kind(e) for e in uniq])
            lines = mc.count_lines(counts)
            skip = mc.skipped_summary(len(host_ids), hosts_hit)
            if skip:
                lines.append(u"")
                lines.append(skip)
            ui.summary(TITLE, u"เลือกเหล็กแล้ว {} รายการ จาก host {} ตัว".format(
                len(uniq), hosts_hit), lines)
except Exception:
    ui.summary(TITLE, u"เกิดข้อผิดพลาด (ยังไม่ได้เปลี่ยนอะไรในโมเดล)",
               [traceback.format_exc().splitlines()[-1]],
               ui.write_log("SelectRebar.txt", traceback.format_exc().splitlines()))
