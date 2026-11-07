# -*- coding: utf-8 -*-
"""Select Host — เลือกเหล็ก (Rebar / FabricSheet / RebarInSystem) แล้วเลือก host ของเหล็กนั้น

เหล็กที่หา host ไม่เจอจะถูกข้าม (แจ้งจำนวน) ไม่ error; RebarInSystem สแกน host ครั้งเดียวทั้งชุด
"""

import traceback
from pyrevit import revit, DB, forms
from System.Collections.Generic import List

from revotech import hostpick, ui, reinforcement as rf
from revotech import manage, managecalc as mc

doc = revit.doc
uidoc = revit.uidoc
TITLE = u"Select Host — PK Revit"

try:
    ids = hostpick.resolve(uidoc, doc, manage.is_bar_element, u"เหล็ก")
    if ids is None:
        pass
    elif not ids:
        forms.alert(u"ไม่ได้เลือกเหล็ก", title=TITLE)
    else:
        bars = [doc.GetElement(i) for i in ids]
        bars = [b for b in bars if b is not None]
        host_ids, missing = manage.hosts_of_many(doc, bars)
        if not host_ids:
            forms.alert(u"หา host ของเหล็กที่เลือกไม่พบ ({} เส้น) — "
                        u"อาจเป็นเหล็กที่ host ถูกลบหรือไม่มีความสัมพันธ์กับ host".format(
                            len(bars)), title=TITLE)
        else:
            uidoc.Selection.SetElementIds(List[DB.ElementId](host_ids))
            counts = {}
            for h in host_ids:
                el = doc.GetElement(h)
                n = el.Category.Name if el is not None and el.Category is not None else u"?"
                counts[n] = counts.get(n, 0) + 1
            lines = [u"  {}: {} ตัว".format(k, counts[k]) for k in sorted(counts)]
            lines.append(u"  เหล็กที่เลือก: " + u", ".join(
                u"{} {}".format(mc.KIND_TH.get(k, k), n)
                for k, n in mc.count_kinds([rf.kind(b) for b in bars])))
            if missing:
                lines.append(u"")
                lines.append(u"ข้าม {} เส้นที่หา host ไม่เจอ".format(missing))
            ui.summary(TITLE, u"เลือก host แล้ว {} ตัว".format(len(host_ids)), lines)
except Exception:
    ui.summary(TITLE, u"เกิดข้อผิดพลาด (ยังไม่ได้เปลี่ยนอะไรในโมเดล)",
               [traceback.format_exc().splitlines()[-1]],
               ui.write_log("SelectHost.txt", traceback.format_exc().splitlines()))
