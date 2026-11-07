# -*- coding: utf-8 -*-
"""สิทธิ์การใช้งาน — ป้อนรหัส ดูสถานะ/รหัสเครื่อง เลือกภาษา (TH/EN/LO)

ยังไม่เชื่อมกับโมดูลอื่น (ไม่บล็อกอะไร) ตรรกะอยู่ใน lib/revotech/license.py และ i18n.py
ยังไม่ได้ทดสอบใน Revit
"""

import os
from pyrevit import script

from revotech import ui
from revotech import i18n
from revotech import license as lic
from revotech.i18n import t


class LicenseForm(ui.RevoWindow):
    def __init__(self):
        body = os.path.join(os.path.dirname(__file__), "body.xaml")
        ui.RevoWindow.__init__(
            self, body, u"LICEN", u"SE", t("license.subtitle"),
            t("license.activate"))
        self.lb_status.Text = t("license.status_label")
        self.lb_machine.Text = t("license.machine_label")
        self.lb_key.Text = t("license.key_label")
        self.lb_lang.Text = t("license.language_label")
        self.tb_note.Text = t("license.lang_note") + u"\n" + \
            t("license.note_not_enforced")
        self.mid = lic.machine_id()
        self.tb_machine.Text = self.mid
        self._refresh_status()
        self._langs = list(i18n.LANGS)
        names = [i18n.LANG_NAMES[c] for c in self._langs]
        ui.combo_fill(self.cmb_lang, names,
                      i18n.LANG_NAMES[i18n.get_language()])
        self.cmb_lang.SelectionChanged += self._on_lang

    def _refresh_status(self):
        code, masked = lic.current_status()
        self.tb_status.Text = t("license.status." + code, key=masked)

    def _on_lang(self, sender, args):
        i = self.cmb_lang.SelectedIndex
        if 0 <= i < len(self._langs):
            i18n.set_language(self._langs[i])

    def collect(self):
        res = lic.activate(self.tb_key.Text, mid=self.mid)
        if res.ok:
            self._refresh_status()
            self.tb_msg.Text = t("license.msg.ok")
            return {"ok": True}
        self.tb_msg.Text = res.message()
        return None   # None = ไม่ปิดหน้าต่าง ให้แก้รหัส


form = LicenseForm()
form.show()
script.exit()
