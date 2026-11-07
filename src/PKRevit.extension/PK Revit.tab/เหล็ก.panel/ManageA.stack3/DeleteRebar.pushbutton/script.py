# -*- coding: utf-8 -*-
"""Delete Rebar — ลบเหล็กบน host ที่เลือก (ดีกว่า PK Tool: ยืนยันก่อนลบ + ค่าตั้งต้นปลอดภัย)

1. เลือก host (hostpick: ใช้ที่เลือกอยู่ / ทีละตัว / ตาม Mark)
2. รวบรวมของที่ลบได้ (reinforcement.deletable_on_hosts — Area/Path คืนทั้งระบบเพราะ Revit
   ลบ RebarInSystem ทีละเส้นไม่ได้)
3. กล่องยืนยันแสดงจำนวนแยกตามชนิด เลือก "เฉพาะที่ PK Revit สร้าง" (Comments ขึ้นต้น PKRevit:
   — ค่าตั้งต้น) หรือ "ทั้งหมดทุกที่มา"
4. Transaction เดียว ย้อนด้วย Ctrl+Z ครั้งเดียว; สรุปผลพร้อมเตือนเรื่องลบทั้งระบบ Area/Path
"""

import os
import traceback
from pyrevit import revit, DB, forms
from System.Collections.Generic import List

from revotech import hostpick, ui, reinforcement as rf
from revotech import manage, managecalc as mc

doc = revit.doc
uidoc = revit.uidoc
TITLE = u"Delete Rebar — PK Revit"


class ConfirmForm(ui.RevoWindow):
    def __init__(self, n_hosts, items):
        body = os.path.join(os.path.dirname(os.path.abspath(__file__)), "body.xaml")
        ui.RevoWindow.__init__(
            self, body, u"DELETE ", u"REBAR",
            u"ยืนยันก่อนลบเหล็กบน host — PK Revit", u"ลบ", width=480)
        self.items = items
        self.tb_info.Text = u"host ที่เลือก {} ตัว — พบเหล็กทั้งหมด {} รายการ".format(
            n_hosts, len(items))
        for rb, tb, only_pk, label in (
                (self.rb_pk, self.tb_pk, True,
                 u"ลบเฉพาะที่ PK Revit สร้าง (Comments ขึ้นต้น PKRevit:)"),
                (self.rb_all, self.tb_all, False,
                 u"ลบทั้งหมดทุกที่มา (รวมที่สร้างด้วยมือ/เครื่องมืออื่น)")):
            rb.Content = label
            c = mc.delete_counts(items, only_pk)
            tb.Text = u"\n".join(mc.count_lines(c, u"")) if c else u"ไม่มีรายการ"
        self.rb_pk.Click += self._refresh
        self.rb_all.Click += self._refresh
        self._refresh(None, None)

    def _only_pk(self):
        return bool(self.rb_pk.IsChecked)

    def _refresh(self, sender, args):
        c = mc.delete_counts(self.items, self._only_pk())
        self.tb_warn.Text = mc.system_warning(c) or u""
        self.run_btn.IsEnabled = bool(c)

    def collect(self):
        return {"only_pk": self._only_pk()}


try:
    host_ids = hostpick.resolve(uidoc, doc, manage.is_host_candidate, u"host")
    if host_ids is None:
        pass
    elif not host_ids:
        forms.alert(u"ไม่ได้เลือก host", title=TITLE)
    else:
        targets = rf.deletable_on_hosts(doc, host_ids)
        if not targets:
            forms.alert(u"ไม่พบเหล็กบน host ที่เลือก ({} ตัว) — ไม่มีอะไรให้ลบ".format(
                len(host_ids)), title=TITLE)
        else:
            items = [(rf.kind(e), manage.comment_of(e)) for e in targets]
            vals = ConfirmForm(len(host_ids), items).show()
            if vals is not None:
                idx = mc.delete_indices(items, vals["only_pk"])
                chosen = [targets[i] for i in idx]
                counts = mc.delete_counts(items, vals["only_pk"])
                deleted = 0
                err = None
                t = DB.Transaction(doc, u"PK Revit: Delete Rebar")
                t.Start()
                try:
                    res = doc.Delete(List[DB.ElementId]([e.Id for e in chosen]))
                    deleted = res.Count if res is not None else len(chosen)
                    t.Commit()
                except Exception:
                    err = traceback.format_exc()
                    t.RollBack()
                if err:
                    path = ui.write_log("DeleteRebar.txt", err.splitlines())
                    ui.summary(TITLE, u"ลบไม่สำเร็จ — ย้อนกลับแล้ว ไม่มีอะไรเปลี่ยนในโมเดล",
                               [err.splitlines()[-1]], path)
                else:
                    lines = mc.count_lines(counts)
                    warn = mc.system_warning(counts)
                    if warn:
                        lines += [u"", u"⚠ " + warn]
                    lines += [u"", u"Ctrl+Z ครั้งเดียวย้อนกลับได้"]
                    ui.summary(TITLE, u"ลบเหล็กแล้ว {} รายการ (Revit รายงานลบรวมชิ้นที่พึ่งพา {} รายการ)".format(
                        len(chosen), deleted), lines)
except Exception:
    ui.summary(TITLE, u"เกิดข้อผิดพลาด",
               [traceback.format_exc().splitlines()[-1]],
               ui.write_log("DeleteRebar.txt", traceback.format_exc().splitlines()))
